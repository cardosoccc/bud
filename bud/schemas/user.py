import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: str
    name: str
    password: Optional[str] = None


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    google_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
