import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class BudgetCreate(BaseModel):
    name: str  # YYYY-MM
    project_id: uuid.UUID


class BudgetRead(BaseModel):
    id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    project_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class BudgetUpdate(BaseModel):
    name: Optional[str] = None
