import uuid
from typing import List, Optional

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bud.models.recurrence import Recurrence
from bud.schemas.recurrence import RecurrenceCreate


def _month_offset(start: str, n: int) -> str:
    """Return the YYYY-MM string that is n months after start."""
    year, month = map(int, start.split("-"))
    month += n
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def _months_between(start: str, end: str) -> int:
    """Return number of months from start to end (inclusive count - 1)."""
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    return (ey - sy) * 12 + (em - sm)


async def get_recurrence(db: AsyncSession, recurrence_id: uuid.UUID) -> Optional[Recurrence]:
    result = await db.execute(select(Recurrence).where(Recurrence.id == recurrence_id))
    return result.scalar_one_or_none()


async def create_recurrence(db: AsyncSession, data: RecurrenceCreate) -> Recurrence:
    recurrence = Recurrence(
        start=data.start,
        end=data.end,
        installments=data.installments,
        base_description=data.base_description,
        original_forecast_id=data.original_forecast_id,
        project_id=data.project_id,
    )
    db.add(recurrence)
    await db.commit()
    await db.refresh(recurrence)
    return recurrence


async def get_recurrences_for_month(
    db: AsyncSession, project_id: uuid.UUID, month: str
) -> List[Recurrence]:
    """Find all recurrences that should have a forecast in the given month.

    A recurrence applies if:
    - start <= month
    - AND one of:
      - has installments and month is within start..start+installments-1
      - no installments and (no end or end >= month)
    """
    result = await db.execute(
        select(Recurrence)
        .where(
            Recurrence.project_id == project_id,
            Recurrence.start <= month,
        )
        .options(selectinload(Recurrence.original_forecast))
    )
    recurrences = list(result.scalars().all())

    applicable = []
    for r in recurrences:
        if r.installments:
            last_month = _month_offset(r.start, r.installments - 1)
            if month <= last_month:
                applicable.append(r)
        else:
            if r.end is None or month <= r.end:
                applicable.append(r)
    return applicable


def get_installment_number(recurrence: Recurrence, month: str) -> int:
    """Calculate the installment number (1-based) for a given month."""
    return _months_between(recurrence.start, month) + 1
