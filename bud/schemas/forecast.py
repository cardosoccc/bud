import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel


class ForecastCreate(BaseModel):
    description: Optional[str] = None
    value: Decimal
    budget_id: uuid.UUID
    category_id: Optional[uuid.UUID] = None
    tags: List[str] = []
    recurrence_id: Optional[uuid.UUID] = None
    installment: Optional[int] = None


class ForecastRead(BaseModel):
    id: uuid.UUID
    description: Optional[str] = None
    value: Decimal
    budget_id: uuid.UUID
    category_id: Optional[uuid.UUID] = None
    tags: List[str] = []
    recurrence_id: Optional[uuid.UUID] = None
    installment: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ForecastUpdate(BaseModel):
    description: Optional[str] = None
    value: Optional[Decimal] = None
    category_id: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = None
