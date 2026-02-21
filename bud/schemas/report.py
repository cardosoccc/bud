import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel


class AccountBalance(BaseModel):
    account_id: uuid.UUID
    account_name: str
    balance: Decimal


class ForecastActual(BaseModel):
    forecast_id: uuid.UUID
    description: str
    forecast_value: Decimal
    actual_value: Decimal
    difference: Decimal
    category_id: Optional[uuid.UUID] = None


class ReportRead(BaseModel):
    budget_id: uuid.UUID
    budget_name: str
    start_date: date
    end_date: date
    account_balances: List[AccountBalance]
    total_balance: Decimal
    total_earnings: Decimal
    total_expenses: Decimal
    forecasts: List[ForecastActual]
