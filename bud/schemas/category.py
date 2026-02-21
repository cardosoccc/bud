import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str


class CategoryRead(BaseModel):
    id: uuid.UUID
    name: str
    user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
