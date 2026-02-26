import uuid
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bud.models.forecast import Forecast
from bud.schemas.forecast import ForecastCreate, ForecastUpdate


async def list_forecasts(db: AsyncSession, budget_id: uuid.UUID) -> List[Forecast]:
    result = await db.execute(
        select(Forecast)
        .where(Forecast.budget_id == budget_id)
        .options(selectinload(Forecast.category))
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
        min_value=data.min_value,
        max_value=data.max_value,
        is_recurrent=data.is_recurrent,
        recurrent_start=data.recurrent_start,
        recurrent_end=data.recurrent_end,
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
