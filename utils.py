
import secrets
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
import models
from typing import Optional, Union
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException,Depends
from bcrypt import checkpw, hashpw, gensalt
from jose import JWTError, jwt
from config import settings
from pydantic import BaseModel, EmailStr, Field, field_validator
from fastapi import Cookie, HTTPException, Response
from redis_client import redis_client

GUEST_COOKIE_NAME = "guest_id"
GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year



_COMMON_WEAK_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789",
    "qwertyui", "qwerty123", "11111111", "abc12345", "letmein11",
    "iloveyou", "admin1234", "welcome1", "changeme", "passw0rd",
    "222222222", "monkey123", "dragon12", "sunshine", "princess",
    "football", "baseball", "superman", "batman", "starwars", "trustno1", "shadow", "master", "hello123",
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login", auto_error=False)

def validate_password_strength(password: str) -> str:
    if password.lower() in _COMMON_WEAK_PASSWORDS:
        raise ValueError("This password is too common. Please choose a stronger one.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password) or not any (c.isupper() for c in password):
        raise ValueError("Password must contain at least one uppercase letter, one lowercase letter, and one number.")
    return password


def hash_password(password: str) -> str:
    # Hash the password using bcrypt
    hashed = hashpw(password.encode('utf-8'), gensalt())
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Verify the password using bcrypt
    return checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(data: dict) -> str:
    secret_key = settings.secret_key
    algorithm = settings.algorithm
    access_token_expire_minutes = settings.access_token_expire_minutes
    payload = data.copy()
    # Create a JWT token for the user with an expiration time
    expiretime = datetime.now(timezone.utc) + timedelta(minutes=access_token_expire_minutes)
    payload["exp"] = expiretime 
    payload["type"] = "access"
    return jwt.encode(payload, secret_key, algorithm=algorithm)


async def create_refresh_token(data: dict, db: AsyncSession) -> str:
    secret_key = settings.secret_key
    algorithm = settings.algorithm
    refresh_token_expire_days = settings.refresh_token_expire_days
    payload = data.copy()
    # Create a JWT token for the user with an expiration time
    expires_at = datetime.now(timezone.utc) + timedelta(days=refresh_token_expire_days)

    payload["exp"] = expires_at
    payload["type"] = "refresh"
    refresh_token = jwt.encode(payload, secret_key, algorithm=algorithm)

    db.add(
        models.RefreshToken(
            user_id=int(data["sub"]),
            token=(refresh_token),
            expires_at=expires_at,
        )
    )
    await db.commit()
    return refresh_token


async def get_user_identifier(
    response: Response,
    token: Optional[str] = Depends(oauth2_scheme),
    guest_id: Optional[str] = Cookie(default=None),
) -> Union[int, str]:
    if token is not None:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            return int(payload.get("sub"))
        except (JWTError, TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid or expired token.")

    # No account — give this browser its own identity instead of lumping
    # every anonymous visitor into one shared "global_user" bucket, so
    # guests don't share history or a rate-limit budget with each other.
    if guest_id is None:
        guest_id = secrets.token_urlsafe(16)
        response.set_cookie(
            key=GUEST_COOKIE_NAME,
            value=guest_id,
            max_age=GUEST_COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
    return f"guest:{guest_id}"


async def apply_limit_rate(user_id: Union[int, str]) -> bool:
    rate_limit = settings.AUTH_RATE_LIMIT if isinstance(user_id, int) else settings.GLOBAL_RATE_LIMIT
    time_window = settings.TIME_WINDOW_SECONDS

    key = f"rate_limit:{user_id}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, time_window)

    if count > rate_limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    return True


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key="refresh_token",    
        value=raw_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/",
    )


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, password: str) -> str:
        return validate_password_strength(password)


