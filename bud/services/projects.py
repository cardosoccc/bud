import uuid
from typing import Optional, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bud.models.project import Project
from bud.schemas.project import ProjectCreate, ProjectUpdate


async def list_projects(db: AsyncSession, user_id: uuid.UUID) -> List[Project]:
    result = await db.execute(
        select(Project).where(Project.user_id == user_id).order_by(Project.created_at)
    )
    return list(result.scalars().all())


async def get_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Project]:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_project(db: AsyncSession, data: ProjectCreate, user_id: uuid.UUID) -> Project:
    project = Project(name=data.name, user_id=user_id)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def update_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, data: ProjectUpdate) -> Optional[Project]:
    project = await get_project(db, project_id, user_id)
    if not project:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    project = await get_project(db, project_id, user_id)
    if not project:
        return False
    await db.delete(project)
    await db.commit()
    return True


async def set_default_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Project]:
    # Unset all defaults first
    await db.execute(
        update(Project).where(Project.user_id == user_id).values(is_default=False)
    )
    project = await get_project(db, project_id, user_id)
    if not project:
        await db.rollback()
        return None
    project.is_default = True
    await db.commit()
    await db.refresh(project)
    return project


async def get_default_project(db: AsyncSession, user_id: uuid.UUID) -> Optional[Project]:
    result = await db.execute(
        select(Project).where(Project.user_id == user_id, Project.is_default == True)  # noqa: E712
    )
    return result.scalar_one_or_none()
