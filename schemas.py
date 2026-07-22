from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class Userlogin(BaseModel):
    email: EmailStr
    password: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None


class ChatResponse(BaseModel):
    response: str


class SessionCreate(BaseModel):
    title: Optional[str] = None


class SessionOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionRename(BaseModel):
    new_session_name: str


class MessageOut(BaseModel):
    role: str
    content: str


class ImageRequest(BaseModel):
    prompt: str
    session_id: Optional[int] = None


class ImageResponse(BaseModel):
    image_url: str


class AIplatform(ABC):
    @abstractmethod
    def chat(self, prompt: str) -> str:
        pass


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    
    class Config:
        from_attributes = True




