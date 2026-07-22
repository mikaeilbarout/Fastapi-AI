# FastAPI AI Chat Backend

A FastAPI backend for an AI chat app, backed by Gemini (with an OpenAI client also available), with JWT authentication, multi-session chat history, and Redis-backed rate limiting.

## Features

- **Chat** — talks to Gemini, with per-session conversation context.
- **AI image generation** — generate images from a text prompt (Gemini); the file is saved under `static/photos/` and its URL is persisted in the session's history like any other message.
- **Auth** — signup/login with JWT access tokens, httpOnly refresh-token cookies with rotation, and logout revocation.
- **Multi-session chat history** — logged-in users can have multiple named chat sessions (Postgres-backed), with a sidebar to switch between them, plus rename and delete.
- **Guest chat** — anonymous visitors can chat too; each browser gets its own isolated, ephemeral (Redis-only) conversation via a cookie, with no account required.
- **Rate limiting** — per-identity request limits (stricter for guests, looser for logged-in users), enforced with Redis.

## Tech stack

- FastAPI + Uvicorn
- PostgreSQL (via SQLAlchemy async + asyncpg) for users, sessions, and message history
- Redis for chat context caching and rate limiting
- Google Gemini API (`google-genai`) — chat and image generation — with an OpenAI client also available
- pytest + pytest-asyncio for tests

## Setup

1. **Clone and install dependencies**

   ```
   pip install -r requirements.txt
   ```

2. **Configure environment variables**

   Copy `.env.example` to `.env` and fill in the values:

   ```
   cp .env.example .env
   ```

   | Variable | Description |
   |---|---|
   | `GEMINI_API_KEY` | Google Gemini API key |
   | `OPENAI_API_KEY` | OpenAI API key |
   | `SECRET_KEY` | JWT signing secret — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `ALGORITHM` | JWT algorithm (e.g. `HS256`) |
   | `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime |
   | `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime |
   | `ADMIN_EMAIL` | Email that gets `is_admin=True` on signup |
   | `GLOBAL_RATE_LIMIT` | Requests per window for guests |
   | `AUTH_RATE_LIMIT` | Requests per window for logged-in users |
   | `TIME_WINDOW_SECONDS` | Rate-limit window length |
   | `REDIS_URL` | Redis connection string |
   | `DATABASE_URL` | PostgreSQL connection string (SQLAlchemy async DSN) |

3. **Start Redis and PostgreSQL**

   ```
   docker compose up -d
   ```

   > **Windows note:** if a container's port fails to bind with a
   > permissions-style error even though nothing else is using it, the
   > port likely falls in a Hyper-V/WSL2 reserved range. Check with
   > `netsh interface ipv4 show excludedportrange protocol=tcp` and pick a
   > host port outside those ranges (this is why Redis defaults to host
   > port `16379` and Postgres to `5433` here instead of their standard
   > ports).

4. **Run the app**

   ```
   uvicorn main:app --reload
   ```

   The app creates its database tables automatically on startup.

### Running with Docker

A `Dockerfile` is included for the app itself:

```
docker build -t fastapi-ai .
docker run --env-file .env --network fastapi-ai_default -p 8000:8000 fastapi-ai
```

(`--network fastapi-ai_default` is the network created by `docker compose up -d`, so the app container can reach the `redis`/`postgres` containers by name — update `REDIS_URL`/`DATABASE_URL` accordingly if you do this.)

## Running tests

```
pytest -v
```

Tests run against an isolated SQLite database and a separate Redis logical DB — they don't touch your dev data.

## API overview

| Method | Path | Description |
|---|---|---|
| POST | `/signup` | Create an account |
| POST | `/login` | Log in |
| POST | `/refresh` | Rotate the refresh-token cookie for a new access token |
| POST | `/logout` | Revoke the current refresh token |
| POST | `/chat` | Send a chat message (`session_id` required if logged in) |
| POST | `/generate-image` | Generate an image from a prompt (`session_id` required if logged in) |
| POST | `/sessions` | Create a new chat session (logged-in only) |
| GET | `/sessions` | List your chat sessions |
| GET | `/sessions/{id}/messages` | Get a session's message history |
| PATCH | `/sessions/{id}` | Rename a session |
| DELETE | `/sessions/{id}` | Delete a session |

## CI

GitHub Actions runs the pytest suite (with a Redis service container) on every push and pull request — see `.github/workflows/tests.yml`.
