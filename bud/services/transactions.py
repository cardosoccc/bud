import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bud.models.transaction import Transaction
from bud.schemas.transaction import TransactionCreate, TransactionUpdate


async def list_transactions(
    db: AsyncSession,
    project_id: uuid.UUID,
    month: Optional[str] = None,  # YYYY-MM
) -> List[Transaction]:
    conditions = [
        Transaction.project_id == project_id,
    ]
    if month:
        year, m = month.split("-")
        start = date(int(year), int(m), 1)
        if int(m) == 12:
            end = date(int(year) + 1, 1, 1)
        else:
            end = date(int(year), int(m) + 1, 1)
        conditions.append(Transaction.date >= start)
        conditions.append(Transaction.date < end)

    result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.account))
        .where(and_(*conditions))
        .order_by(Transaction.date.desc())
    )
    return list(result.scalars().all())


async def get_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> Optional[Transaction]:
    result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.account))
        .where(Transaction.id == transaction_id)
    )
    return result.scalar_one_or_none()


async def create_transaction(db: AsyncSession, data: TransactionCreate) -> Transaction:
    txn = Transaction(
        value=data.value,
        description=data.description,
        date=data.date,
        account_id=data.account_id,
        project_id=data.project_id,
        category_id=data.category_id,
        tags=data.tags,
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return txn


async def update_transaction(
    db: AsyncSession, transaction_id: uuid.UUID, data: TransactionUpdate
) -> Optional[Transaction]:
    txn = await get_transaction(db, transaction_id)
    if not txn:
        return None

    update_data = data.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(txn, field, value)

    await db.commit()
    await db.refresh(txn)
    return txn


async def delete_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> bool:
    txn = await get_transaction(db, transaction_id)
    if not txn:
        return False

    await db.delete(txn)
    await db.commit()
    return True
