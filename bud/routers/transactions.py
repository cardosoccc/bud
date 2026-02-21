import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bud.database import get_db
from bud.schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate
from bud.services import transactions as transaction_service
from bud.auth import get_current_user_id

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=List[TransactionRead])
async def list_transactions(
    project_id: uuid.UUID = Query(...),
    month: Optional[str] = Query(None, description="YYYY-MM"),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.list_transactions(db, user_id, project_id, month)


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.create_transaction(db, data)


@router.get("/{transaction_id}", response_model=TransactionRead)
async def get_transaction(
    transaction_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    txn = await transaction_service.get_transaction(db, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: uuid.UUID,
    data: TransactionUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    txn = await transaction_service.update_transaction(db, transaction_id, data)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await transaction_service.delete_transaction(db, transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
