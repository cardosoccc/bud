import uuid
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bud.models.category import Category
from bud.schemas.category import CategoryCreate, CategoryUpdate


async def list_categories(db: AsyncSession, user_id: uuid.UUID) -> List[Category]:
    result = await db.execute(
        select(Category).where(Category.user_id == user_id).order_by(Category.name)
    )
    return list(result.scalars().all())


async def get_category(db: AsyncSession, category_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Category]:
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_category(db: AsyncSession, data: CategoryCreate, user_id: uuid.UUID) -> Category:
    category = Category(name=data.name, user_id=user_id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def update_category(db: AsyncSession, category_id: uuid.UUID, user_id: uuid.UUID, data: CategoryUpdate) -> Optional[Category]:
    category = await get_category(db, category_id, user_id)
    if not category:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(category, field, value)
    await db.commit()
    await db.refresh(category)
    return category


async def delete_category(db: AsyncSession, category_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    category = await get_category(db, category_id, user_id)
    if not category:
        return False
    await db.delete(category)
    await db.commit()
    return True
