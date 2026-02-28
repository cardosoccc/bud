import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel


class RecurrenceCreate(BaseModel):
    start: str  # YYYY-MM
    end: Optional[str] = None  # YYYY-MM
    installments: Optional[int] = None
    base_description: Optional[str] = None
    value: Decimal
    category_id: Optional[uuid.UUID] = None
    tags: List[str] = []
    project_id: uuid.UUID


class RecurrenceRead(BaseModel):
    id: uuid.UUID
    start: str
    end: Optional[str] = None
    installments: Optional[int] = None
    base_description: Optional[str] = None
    value: Decimal
    category_id: Optional[uuid.UUID] = None
    tags: List[str] = []
    project_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class RecurrenceUpdate(BaseModel):
    base_description: Optional[str] = None
    value: Optional[Decimal] = None
    category_id: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = None
    start: Optional[str] = None
    end: Optional[str] = None
    installments: Optional[int] = None
