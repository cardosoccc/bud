import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from bud.models.user import User
from bud.models.account import Account, AccountType
from bud.models.project import Project
from bud.schemas.user import UserCreate, UserUpdate
from bud.auth import get_password_hash


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    hashed_password = get_password_hash(data.password) if data.password else None
    user = User(email=data.email, name=data.name, hashed_password=hashed_password)
    db.add(user)
    await db.flush()

    # Create default project and nil account
    nil_account = Account(name="nil", type=AccountType.nil)
    db.add(nil_account)
    await db.flush()

    default_project = Project(name="main", is_default=True, user_id=user.id)
    default_project.accounts.append(nil_account)
    db.add(default_project)

    await db.commit()
    result = await db.execute(
        select(User).where(User.id == user.id).options(selectinload(User.projects))
    )
    return result.scalar_one()


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def update_user(db: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> Optional[User]:
    user = await get_user(db, user_id)
    if not user:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
