import uuid
from typing import Optional

from sqlalchemy import select
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
    await db.refresh(user)
    return user


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_google_id(db: AsyncSession, google_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.google_id == google_id))
    return result.scalar_one_or_none()


async def create_or_update_google_user(db: AsyncSession, google_info: dict) -> User:
    google_id = google_info["id"]
    email = google_info["email"]
    name = google_info.get("name", email)

    user = await get_user_by_google_id(db, google_id)
    if user:
        return user

    user = await get_user_by_email(db, email)
    if user:
        user.google_id = google_id
        await db.commit()
        await db.refresh(user)
        return user

    return await create_user(db, UserCreate(email=email, name=name))


async def update_user(db: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> Optional[User]:
    user = await get_user(db, user_id)
    if not user:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
