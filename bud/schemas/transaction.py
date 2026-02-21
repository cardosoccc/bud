import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel


class TransactionCreate(BaseModel):
    value: Decimal
    description: str
    date: date
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    project_id: uuid.UUID
    category_id: Optional[uuid.UUID] = None
    tags: List[str] = []


class TransactionRead(BaseModel):
    id: uuid.UUID
    value: Decimal
    description: str
    date: date
    source_account_id: uuid.UUID
    destination_account_id: uuid.UUID
    project_id: uuid.UUID
    category_id: Optional[uuid.UUID] = None
    tags: List[str] = []
    is_counterpart: bool
    counterpart_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionUpdate(BaseModel):
    value: Optional[Decimal] = None
    description: Optional[str] = None
    date: Optional[date] = None
    source_account_id: Optional[uuid.UUID] = None
    destination_account_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = None
