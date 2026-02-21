import uuid
from typing import Optional

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[uuid.UUID] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None
