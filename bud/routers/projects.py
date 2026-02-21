import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from bud.database import get_db
from bud.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from bud.services import projects as project_service
from bud.auth import get_current_user_id

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=List[ProjectRead])
async def list_projects(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.list_projects(db, user_id)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.create_project(db, data, user_id)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get_project(db, project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.update_project(db, project_id, user_id, data)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await project_service.delete_project(db, project_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/{project_id}/set-default", response_model=ProjectRead)
async def set_default_project(
    project_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.set_default_project(db, project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
