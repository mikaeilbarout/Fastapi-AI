from typing import Optional

from schemas import Token, Userlogin
from fastapi import APIRouter, status, Depends, HTTPException, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from database import get_async_db
from utils import hash_password, create_access_token, create_refresh_token, _set_refresh_cookie, verify_password, UserCreate
import models
from config import settings


router = APIRouter(prefix="", tags=["auth"])


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate, response: Response, db: AsyncSession =Depends(get_async_db)):
    email = user.email.lower().strip()
    result = await db.execute(select(models.Users).where(models.Users.email == email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered. Log in or use a different email.",
        )

    new_user = models.Users(
        full_name=user.username,
        email=email,
        hashed_password=hash_password(user.password),
        is_admin=(email == settings.admin_email.lower()),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    access_token = create_access_token(data={"sub": str(new_user.id)})
    refresh_token = await create_refresh_token({"user_id": new_user.id, "sub": str(new_user.id)}, db)

    _set_refresh_cookie(response, refresh_token)

    return Token(access_token=access_token, token_type="bearer", user_id=new_user.id)


@router.post("/login", response_model=Token)
async def login(response: Response, payload: Userlogin, db: AsyncSession = Depends(get_async_db)) -> Token:
    email = payload.email.lower().strip()
    user = (await db.execute(select(models.Users).where(models.Users.email == email))).scalar_one_or_none()
    if not user or not verify_password(payload.password, str(user.hashed_password)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.")
        
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = await create_refresh_token({"sub": str(user.id)}, db)
    _set_refresh_cookie(response, refresh_token)
    return Token(access_token=access_token, user_id=int(user.id))


@router.post("/refresh", response_model=Token)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_async_db),
    refresh_token: Optional[str] = Cookie(default=None),
):
    if refresh_token is None:
        raise HTTPException(status_code=401, detail="No refresh token.")

    try:
        payload = jwt.decode(refresh_token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type.")

    stored = (
        await db.execute(select(models.RefreshToken).where(models.RefreshToken.token == refresh_token))
    ).scalar_one_or_none()
    if stored is None:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked.")

    user_id = int(payload["sub"])

    # Rotate: the old refresh token is single-use, so delete it and issue a
    # fresh one alongside the new access token.
    await db.delete(stored)
    await db.commit()

    new_access_token = create_access_token({"sub": str(user_id)})
    new_refresh_token = await create_refresh_token({"sub": str(user_id)}, db)
    _set_refresh_cookie(response, new_refresh_token)

    return Token(access_token=new_access_token, user_id=user_id)


@router.post("/logout")
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_async_db),
    refresh_token: Optional[str] = Cookie(default=None),
):
    if refresh_token is not None:
        stored = (
            await db.execute(select(models.RefreshToken).where(models.RefreshToken.token == refresh_token))
        ).scalar_one_or_none()
        if stored is not None:
            await db.delete(stored)
            await db.commit()

    response.delete_cookie("refresh_token", path="/")
    return {"detail": "Logged out."}