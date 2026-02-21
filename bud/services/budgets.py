import uuid
import calendar
from datetime import date
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bud.models.budget import Budget
from bud.schemas.budget import BudgetCreate, BudgetUpdate


def _parse_month_dates(name: str):
    """Parse YYYY-MM into start and end dates."""
    year, month = map(int, name.split("-"))
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)
    return start, end


async def list_budgets(db: AsyncSession, project_id: uuid.UUID) -> List[Budget]:
    result = await db.execute(
        select(Budget).where(Budget.project_id == project_id).order_by(Budget.name)
    )
    return list(result.scalars().all())


async def get_budget(db: AsyncSession, budget_id: uuid.UUID) -> Optional[Budget]:
    result = await db.execute(select(Budget).where(Budget.id == budget_id))
    return result.scalar_one_or_none()


async def get_budget_by_name(db: AsyncSession, project_id: uuid.UUID, name: str) -> Optional[Budget]:
    result = await db.execute(
        select(Budget).where(Budget.project_id == project_id, Budget.name == name)
    )
    return result.scalar_one_or_none()


async def create_budget(db: AsyncSession, data: BudgetCreate) -> Budget:
    start_date, end_date = _parse_month_dates(data.name)
    budget = Budget(
        name=data.name,
        start_date=start_date,
        end_date=end_date,
        project_id=data.project_id,
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return budget


async def update_budget(db: AsyncSession, budget_id: uuid.UUID, data: BudgetUpdate) -> Optional[Budget]:
    budget = await get_budget(db, budget_id)
    if not budget:
        return None
    if data.name:
        budget.name = data.name
        budget.start_date, budget.end_date = _parse_month_dates(data.name)
    await db.commit()
    await db.refresh(budget)
    return budget


async def delete_budget(db: AsyncSession, budget_id: uuid.UUID) -> bool:
    budget = await get_budget(db, budget_id)
    if not budget:
        return False
    await db.delete(budget)
    await db.commit()
    return True
