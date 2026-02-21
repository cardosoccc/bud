import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str


class ProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    is_default: Optional[bool] = None
