import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from bud.database import get_db
from bud.schemas.report import ReportRead
from bud.services import reports as report_service
from bud.auth import get_current_user_id

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{budget_id}", response_model=ReportRead)
async def get_report(
    budget_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await report_service.generate_report(db, budget_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
