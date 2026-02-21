import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bud.database import get_db
from bud.schemas.budget import BudgetCreate, BudgetRead, BudgetUpdate
from bud.services import budgets as budget_service
from bud.auth import get_current_user_id

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=List[BudgetRead])
async def list_budgets(
    project_id: uuid.UUID = Query(...),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await budget_service.list_budgets(db, project_id)


@router.post("", response_model=BudgetRead, status_code=status.HTTP_201_CREATED)
async def create_budget(
    data: BudgetCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await budget_service.create_budget(db, data)


@router.get("/{budget_id}", response_model=BudgetRead)
async def get_budget(
    budget_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    budget = await budget_service.get_budget(db, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.patch("/{budget_id}", response_model=BudgetRead)
async def update_budget(
    budget_id: uuid.UUID,
    data: BudgetUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    budget = await budget_service.update_budget(db, budget_id, data)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await budget_service.delete_budget(db, budget_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Budget not found")
