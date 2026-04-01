import uuid
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bud.models.budget import Budget
from bud.models.forecast import Forecast
from bud.models.recurrence import Recurrence
from bud.models.transaction import Transaction
from bud.schemas.forecast import ForecastCreate, ForecastUpdate


async def list_forecasts(db: AsyncSession, budget_id: uuid.UUID) -> List[Forecast]:
    result = await db.execute(
        select(Forecast)
        .where(Forecast.budget_id == budget_id)
        .options(selectinload(Forecast.category), selectinload(Forecast.recurrence))
        .order_by(Forecast.created_at)
    )
    return list(result.scalars().all())


async def get_forecast(db: AsyncSession, forecast_id: uuid.UUID) -> Optional[Forecast]:
    result = await db.execute(select(Forecast).where(Forecast.id == forecast_id))
    return result.scalar_one_or_none()


async def create_forecast(db: AsyncSession, data: ForecastCreate) -> Forecast:
    forecast = Forecast(
        description=data.description,
        value=data.value,
        budget_id=data.budget_id,
        category_id=data.category_id,
        tags=data.tags,
        recurrence_id=data.recurrence_id,
        installment=data.installment,
    )
    db.add(forecast)
    await db.commit()
    await db.refresh(forecast)
    return forecast


async def update_forecast(db: AsyncSession, forecast_id: uuid.UUID, data: ForecastUpdate) -> Optional[Forecast]:
    forecast = await get_forecast(db, forecast_id)
    if not forecast:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(forecast, field, value)
    await db.commit()
    await db.refresh(forecast)
    return forecast


async def delete_forecast(db: AsyncSession, forecast_id: uuid.UUID) -> bool:
    forecast = await get_forecast(db, forecast_id)
    if not forecast:
        return False
    await db.delete(forecast)
    await db.commit()
    return True


def compute_forecast_actual(forecast: Forecast, transactions: list) -> Decimal:
    """Compute the actual (current) value for a forecast by matching transactions.

    Uses the same AND logic as the status report:
    - category: exact match on category_id
    - description: case-insensitive substring match
    - tags: all forecast tags must be present in the transaction
    """
    has_criteria = forecast.description or forecast.category_id or forecast.tags
    if not has_criteria:
        return Decimal("0")

    actual = Decimal("0")
    for t in transactions:
        if forecast.category_id and t.category_id != forecast.category_id:
            continue
        if forecast.description and forecast.description.lower() not in t.description.lower():
            continue
        if forecast.tags and not all(tag in (t.tags or []) for tag in forecast.tags):
            continue
        actual += Decimal(str(t.value))
    return actual


async def get_budget_transactions(db: AsyncSession, budget_id: uuid.UUID) -> List[Transaction]:
    """Get all transactions for a budget's period."""
    budget_result = await db.execute(select(Budget).where(Budget.id == budget_id))
    budget = budget_result.scalar_one_or_none()
    if not budget:
        return []

    txns_result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.project_id == budget.project_id,
                Transaction.date >= budget.start_date,
                Transaction.date <= budget.end_date,
            )
        )
    )
    return list(txns_result.scalars().all())


async def forecast_exists_for_recurrence(
    db: AsyncSession, recurrence_id: uuid.UUID, budget_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(Forecast.id).where(
            Forecast.recurrence_id == recurrence_id,
            Forecast.budget_id == budget_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _get_forecast_for_recurrence_in_budget(
    db: AsyncSession, recurrence_id: uuid.UUID, budget_id: uuid.UUID
) -> Optional[Forecast]:
    result = await db.execute(
        select(Forecast).where(
            Forecast.recurrence_id == recurrence_id,
            Forecast.budget_id == budget_id,
        )
    )
    return result.scalar_one_or_none()


async def move_forecast(
    db: AsyncSession,
    forecast_id: uuid.UUID,
    target_budget_id: uuid.UUID,
    source_budget_name: str,
) -> Optional[Forecast]:
    """Move a forecast to a different budget, handling recurrence logic.

    - Non-recurrent: simple budget_id update.
    - Installment-based: move and replace auto-populated forecast in target.
    - Simple recurrent: detach from recurrence, append source month to description.
    """
    forecast = await get_forecast(db, forecast_id)
    if not forecast:
        return None
    if forecast.budget_id == target_budget_id:
        return None

    if forecast.recurrence_id:
        if forecast.installment:
            # Installment-based: delete auto-populated forecast in target, move this one
            existing = await _get_forecast_for_recurrence_in_budget(
                db, forecast.recurrence_id, target_budget_id
            )
            if existing:
                await db.delete(existing)
            forecast.budget_id = target_budget_id
        else:
            # Simple recurrent: detach and rename
            rec_result = await db.execute(
                select(Recurrence).where(Recurrence.id == forecast.recurrence_id)
            )
            rec_obj = rec_result.scalar_one_or_none()
            base = rec_obj.base_description if rec_obj else forecast.description
            forecast.description = f"{base} ({source_budget_name})"
            forecast.recurrence_id = None
            forecast.budget_id = target_budget_id
    else:
        forecast.budget_id = target_budget_id

    await db.commit()
    await db.refresh(forecast)
    return forecast
