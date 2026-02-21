import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bud.database import get_db
from bud.schemas.forecast import ForecastCreate, ForecastRead, ForecastUpdate
from bud.services import forecasts as forecast_service
from bud.auth import get_current_user_id

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("", response_model=List[ForecastRead])
async def list_forecasts(
    budget_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await forecast_service.list_forecasts(db, budget_id)


@router.post("", response_model=ForecastRead, status_code=status.HTTP_201_CREATED)
async def create_forecast(
    data: ForecastCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await forecast_service.create_forecast(db, data)


@router.get("/{forecast_id}", response_model=ForecastRead)
async def get_forecast(
    forecast_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    forecast = await forecast_service.get_forecast(db, forecast_id)
    if not forecast:
        raise HTTPException(status_code=404, detail="Forecast not found")
    return forecast


@router.patch("/{forecast_id}", response_model=ForecastRead)
async def update_forecast(
    forecast_id: uuid.UUID,
    data: ForecastUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    forecast = await forecast_service.update_forecast(db, forecast_id, data)
    if not forecast:
        raise HTTPException(status_code=404, detail="Forecast not found")
    return forecast


@router.delete("/{forecast_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_forecast(
    forecast_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await forecast_service.delete_forecast(db, forecast_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Forecast not found")
