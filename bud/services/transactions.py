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
        Transaction.is_counterpart == False,  # noqa: E712
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
        .options(
            selectinload(Transaction.source_account),
            selectinload(Transaction.destination_account),
        )
        .where(and_(*conditions))
        .order_by(Transaction.date.desc())
    )
    return list(result.scalars().all())


async def get_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> Optional[Transaction]:
    result = await db.execute(
        select(Transaction)
        .options(
            selectinload(Transaction.source_account),
            selectinload(Transaction.destination_account),
        )
        .where(Transaction.id == transaction_id)
    )
    return result.scalar_one_or_none()


async def create_transaction(db: AsyncSession, data: TransactionCreate) -> Transaction:
    txn = Transaction(
        value=data.value,
        description=data.description,
        date=data.date,
        source_account_id=data.source_account_id,
        destination_account_id=data.destination_account_id,
        project_id=data.project_id,
        category_id=data.category_id,
        tags=data.tags,
        is_counterpart=False,
    )
    db.add(txn)
    await db.flush()

    # Create counterpart
    counterpart = Transaction(
        value=-data.value,
        description=data.description,
        date=data.date,
        source_account_id=data.destination_account_id,
        destination_account_id=data.source_account_id,
        project_id=data.project_id,
        category_id=data.category_id,
        tags=data.tags,
        is_counterpart=True,
        counterpart_id=txn.id,
    )
    db.add(counterpart)
    await db.flush()

    txn.counterpart_id = counterpart.id
    await db.commit()
    await db.refresh(txn)
    return txn


async def update_transaction(
    db: AsyncSession, transaction_id: uuid.UUID, data: TransactionUpdate
) -> Optional[Transaction]:
    txn = await get_transaction(db, transaction_id)
    if not txn or txn.is_counterpart:
        return None

    update_data = data.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(txn, field, value)

    # Sync counterpart
    if txn.counterpart_id:
        counterpart = await get_transaction(db, txn.counterpart_id)
        if counterpart:
            if "value" in update_data:
                counterpart.value = -data.value
            if "description" in update_data:
                counterpart.description = data.description
            if "date" in update_data:
                counterpart.date = data.date
            if "category_id" in update_data:
                counterpart.category_id = data.category_id
            if "tags" in update_data:
                counterpart.tags = data.tags
            if "source_account_id" in update_data:
                counterpart.destination_account_id = data.source_account_id
            if "destination_account_id" in update_data:
                counterpart.source_account_id = data.destination_account_id

    await db.commit()
    await db.refresh(txn)
    return txn


async def delete_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> bool:
    txn = await get_transaction(db, transaction_id)
    if not txn or txn.is_counterpart:
        return False

    # Delete counterpart first
    if txn.counterpart_id:
        counterpart = await get_transaction(db, txn.counterpart_id)
        if counterpart:
            txn.counterpart_id = None
            await db.flush()
            await db.delete(counterpart)
            await db.flush()

    await db.delete(txn)
    await db.commit()
    return True
