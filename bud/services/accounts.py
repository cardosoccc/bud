import uuid
from typing import Optional, List

from sqlalchemy import select, delete, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bud.models.account import Account, AccountType
from bud.models.project import Project, project_accounts
from bud.schemas.account import AccountCreate, AccountUpdate


async def list_accounts(db: AsyncSession, user_id: uuid.UUID, project_id: Optional[uuid.UUID] = None) -> List[Account]:
    if project_id:
        result = await db.execute(
            select(Account)
            .join(project_accounts, Account.id == project_accounts.c.account_id)
            .join(Project, project_accounts.c.project_id == Project.id)
            .where(Project.id == project_id, Project.user_id == user_id)
        )
    else:
        result = await db.execute(
            select(Account)
            .join(project_accounts, Account.id == project_accounts.c.account_id)
            .join(Project, project_accounts.c.project_id == Project.id)
            .where(Project.user_id == user_id)
            .distinct()
        )
    return list(result.scalars().all())


async def get_account_by_name(db: AsyncSession, name: str, user_id: uuid.UUID, project_id: uuid.UUID) -> Optional[Account]:
    result = await db.execute(
        select(Account)
        .join(project_accounts, Account.id == project_accounts.c.account_id)
        .join(Project, project_accounts.c.project_id == Project.id)
        .where(Account.name == name, Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_account(db: AsyncSession, account_id: uuid.UUID) -> Optional[Account]:
    result = await db.execute(select(Account).where(Account.id == account_id))
    return result.scalar_one_or_none()


async def create_account(db: AsyncSession, data: AccountCreate, user_id: uuid.UUID) -> Account:
    # Verify project belongs to user
    proj_result = await db.execute(
        select(Project).where(Project.id == data.project_id, Project.user_id == user_id)
    )
    project = proj_result.scalar_one_or_none()
    if not project:
        raise ValueError("Project not found")

    account = Account(name=data.name, type=data.type)
    db.add(account)
    await db.flush()
    await db.execute(insert(project_accounts).values(project_id=project.id, account_id=account.id))
    await db.commit()
    await db.refresh(account)
    return account


async def update_account(db: AsyncSession, account_id: uuid.UUID, data: AccountUpdate) -> Optional[Account]:
    account = await get_account(db, account_id)
    if not account:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(account, field, value)
    await db.commit()
    await db.refresh(account)
    return account


async def delete_account(db: AsyncSession, account_id: uuid.UUID) -> bool:
    account = await get_account(db, account_id)
    if not account:
        return False
    await db.delete(account)
    await db.commit()
    return True


async def get_nil_account(db: AsyncSession, user_id: uuid.UUID) -> Optional[Account]:
    result = await db.execute(
        select(Account)
        .join(project_accounts, Account.id == project_accounts.c.account_id)
        .join(Project, project_accounts.c.project_id == Project.id)
        .where(Project.user_id == user_id, Account.type == AccountType.nil)
        .limit(1)
    )
    return result.scalar_one_or_none()
