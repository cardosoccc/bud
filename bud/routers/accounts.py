import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bud.database import get_db
from bud.schemas.account import AccountCreate, AccountRead, AccountUpdate
from bud.services import accounts as account_service
from bud.auth import get_current_user_id

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=List[AccountRead])
async def list_accounts(
    project_id: Optional[uuid.UUID] = Query(None),
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await account_service.list_accounts(db, user_id, project_id)


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await account_service.create_account(db, data, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(
    account_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    account = await account_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: uuid.UUID,
    data: AccountUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    account = await account_service.update_account(db, account_id, data)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await account_service.delete_account(db, account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Account not found")
