import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bud.auth import verify_password, get_password_hash
from bud.schemas.user import UserCreate
from bud.services import users as user_service


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession):
    user = await user_service.create_user(
        db_session,
        UserCreate(email="test@example.com", name="Test User", password="secret123"),
    )
    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.name == "Test User"
    assert user.hashed_password is not None


@pytest.mark.asyncio
async def test_get_user_by_email(db_session: AsyncSession):
    await user_service.create_user(
        db_session,
        UserCreate(email="find@example.com", name="Find Me", password="pass"),
    )
    found = await user_service.get_user_by_email(db_session, "find@example.com")
    assert found is not None
    assert found.email == "find@example.com"

    missing = await user_service.get_user_by_email(db_session, "nobody@example.com")
    assert missing is None


@pytest.mark.asyncio
async def test_login_valid_password(db_session: AsyncSession):
    user = await user_service.create_user(
        db_session,
        UserCreate(email="login@example.com", name="Login User", password="mypassword"),
    )
    assert verify_password("mypassword", user.hashed_password)


@pytest.mark.asyncio
async def test_login_invalid_password(db_session: AsyncSession):
    user = await user_service.create_user(
        db_session,
        UserCreate(email="wrong@example.com", name="Wrong Pass", password="correct"),
    )
    assert not verify_password("wrong", user.hashed_password)


@pytest.mark.asyncio
async def test_create_user_sets_up_default_project(db_session: AsyncSession):
    user = await user_service.create_user(
        db_session,
        UserCreate(email="proj@example.com", name="Proj User", password="pass"),
    )
    # Refresh to load relationships
    await db_session.refresh(user, ["projects"])
    assert len(user.projects) == 1
    assert user.projects[0].name == "main"
    assert user.projects[0].is_default is True


@pytest.mark.asyncio
async def test_password_hash_roundtrip():
    hashed = get_password_hash("hunter2")
    assert verify_password("hunter2", hashed)
    assert not verify_password("wrong", hashed)
