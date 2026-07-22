import os
import models
import asyncio
import glob
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import mimetypes
import uuid

from schemas import ChatRequest, ChatResponse, ImageRequest, ImageResponse
from aimodel import Gemini, Myopenai
from routers_auth import router as auth_router
from routers_sessions import router as sessions_router, get_owned_session
from database import init_db, get_async_db
from utils import get_user_identifier, apply_limit_rate
from redis_client import get_history, add_message
from google.genai import errors
from starlette.types import Scope
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings

app = FastAPI() #APP Initialaization

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)


class RevalidateStaticFiles(StaticFiles):
    """Serves /static/* with Cache-Control: no-cache instead of the
    browser's default caching heuristics.

    Without this, browsers can and do keep serving an old cached copy of
    e.g. index.js/style.css indefinitely after you replace the files on
    disk and restart the server — no error, no console warning, it just
    silently keeps running the stale JS (which is exactly what "I changed
    the chat page but it still behaves like before" looks like: an old
    cached index.js from before some fix). "no-cache" doesn't mean "don't
    cache" — the browser still caches the file, it just always asks the
    server "is this still current?" first (a cheap 304 if unchanged, the
    fresh file immediately if it changed), so this doesn't meaningfully
    hurt load times.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # API calls (fetch/XHR, which don't prioritize text/html in Accept)
    # should keep getting JSON errors; browser page navigations get a
    # friendly 404 page instead of raw JSON.
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        return FileResponse("templates/404.html", status_code=404)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

templates = Jinja2Templates(directory="templates")

app.mount("/static", RevalidateStaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup():
    await init_db()

app.include_router(auth_router)
app.include_router(sessions_router)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTOS_DIR = os.path.join(BASE_DIR, "static", "photos")


def save_generated_image(image_bytes: bytes, mime_type: str) -> str:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    extension = mimetypes.guess_extension(mime_type) or ".png"
    filename = f"{uuid.uuid4().hex}{extension}"
    with open(os.path.join(PHOTOS_DIR, filename), "wb") as f:
        f.write(image_bytes)
    return f"/static/photos/{filename}"


def load_system_prompt() -> str:
    files = glob.glob(os.path.join(BASE_DIR, "prompt", "*.md"))
    system_prompt = []
    for path in files:
        with open(path, "r", encoding="utf-8") as file:
            system_prompt.append(file.read().strip())
    if system_prompt == []:
        system_prompt = ["there is no system prompt."]
    for i in system_prompt:
        systemprompt = f"{i}\n"
    return systemprompt


system_prompt = load_system_prompt()


gemini_api_key = settings.gemini_api_key
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")

openai_api_key = settings.openai_api_key
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set.")

ai_platform_gemini = Gemini(api_key=gemini_api_key, system_prompt=system_prompt)
ai_platform_openai = Myopenai(api_key=openai_api_key, system_prompt=system_prompt)


@app.get("/")
def read_firstpage():
    return FileResponse("templates/index.html")


@app.get("/login")
async def read_login():
    return FileResponse("templates/login.html")


@app.get("/signup")
def read_signup():
    return FileResponse("templates/signup.html")


async def resolve_chat_context(user_id, session_id, db: AsyncSession):
    """Returns (redis_key, session_or_none) for a chat-like request.

    Guests just get their own Redis key; logged-in users must supply a
    session they own, since that session is what their history is filed
    under in Postgres.
    """
    if not isinstance(user_id, int):
        return user_id, None
    if session_id is None:
        raise HTTPException(status_code=400, detail="session_id is required.")
    session = await get_owned_session(db, user_id, session_id)
    return f"{user_id}:{session_id}", session


async def persist_turn(db: AsyncSession, user_id, session, session_id: int, userprompt: str, response: str):
    if not isinstance(user_id, int):
        return
    existing_count = (
        await db.execute(
            select(func.count()).select_from(models.Prompts).where(models.Prompts.session_id == session_id)
        )
    ).scalar()

    prompt = models.Prompts(user_id=user_id, session_id=session_id, userprompt=userprompt, response=response)
    db.add(prompt)
    if existing_count == 0:
        session.title = userprompt[:60]
    await db.commit()
    await db.refresh(prompt)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user_id=Depends(get_user_identifier), db: AsyncSession = Depends(get_async_db)):
    await apply_limit_rate(user_id)

    redis_key, session = await resolve_chat_context(user_id, request.session_id, db)

    history = await get_history(redis_key)
    historytext = "\n".join(
        f"user prompt: {m['content']}" if m["role"] == "user" else f"AI response: {m['content']}"
        for m in history
    )
    full_prompt = f"{historytext}\n\nuser prompt: {request.message}"

    responsetext = None 
    for k in range(3):
        try:
            responsetext = ai_platform_gemini.chat(full_prompt)
            break
        except errors.ClientError as e:
            if "429" in str(e):
                # Free-tier 429s here are the daily quota, not a per-minute
                # limit, so retrying seconds later within this same request
                # can't help — fail straight to the fallback message.
                break
            raise
        except errors.ServerError:
            await asyncio.sleep(1)
            continue
        
    if responsetext is None:
        responsetext = "you reach the request limit"

    await add_message(redis_key, "user", request.message)
    await add_message(redis_key, "assistant", responsetext)
    await persist_turn(db, user_id, session, request.session_id, request.message, responsetext)

    return ChatResponse(response=responsetext)


@app.post("/generate-image", response_model=ImageResponse)
async def generate_image(request: ImageRequest, user_id=Depends(get_user_identifier), db: AsyncSession = Depends(get_async_db)):
    await apply_limit_rate(user_id)

    redis_key, session = await resolve_chat_context(user_id, request.session_id, db)

    try:
        image_bytes, mime_type = ai_platform_gemini.generate_image(request.prompt)
    except (errors.ClientError, errors.ServerError, ValueError):
        raise HTTPException(status_code=502, detail="Image generation failed. Please try again later.")

    image_url = save_generated_image(image_bytes, mime_type)

    await add_message(redis_key, "user", request.prompt)
    await add_message(redis_key, "assistant", image_url)
    await persist_turn(db, user_id, session, request.session_id, request.prompt, image_url)

    return ImageResponse(image_url=image_url)



            