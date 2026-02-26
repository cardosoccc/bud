import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RecurrenceCreate(BaseModel):
    start: str  # YYYY-MM
    end: Optional[str] = None  # YYYY-MM
    installments: Optional[int] = None
    base_description: Optional[str] = None
    original_forecast_id: uuid.UUID
    project_id: uuid.UUID


class RecurrenceRead(BaseModel):
    id: uuid.UUID
    start: str
    end: Optional[str] = None
    installments: Optional[int] = None
    base_description: Optional[str] = None
    original_forecast_id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
