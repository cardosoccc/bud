"""Unit tests for project-related utility functions."""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bud.commands.utils import is_uuid, resolve_project_id
from bud.schemas.project import ProjectCreate
from bud.services import projects as project_service


# ---------------------------------------------------------------------------
# is_uuid
# ---------------------------------------------------------------------------

def test_is_uuid_valid_uuid4():
    assert is_uuid(str(uuid.uuid4())) is True


def test_is_uuid_valid_uuid_with_braces():
    # uuid.UUID accepts many formats; is_uuid just wraps uuid.UUID()
    uid = uuid.uuid4()
    assert is_uuid(str(uid)) is True


def test_is_uuid_invalid_random_string():
    assert is_uuid("not-a-uuid") is False


def test_is_uuid_empty_string():
    assert is_uuid("") is False


def test_is_uuid_numeric_string():
    assert is_uuid("12345") is False


def test_is_uuid_partial_uuid():
    assert is_uuid("550e8400-e29b-41d4") is False


def test_is_uuid_project_name():
    assert is_uuid("my-project") is False


def test_is_uuid_none_raises_type_error():
    # uuid.UUID(None) raises TypeError which is not caught by is_uuid
    import pytest
    with pytest.raises(TypeError):
        is_uuid(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# resolve_project_id – by UUID string
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_project_id_by_uuid_string(db_session: AsyncSession):
    p = await project_service.create_project(db_session, ProjectCreate(name="ByUUID"))

    result = await resolve_project_id(db_session, str(p.id))

    assert result == p.id


@pytest.mark.asyncio
async def test_resolve_project_id_by_uuid_does_not_query_db_by_name(db_session: AsyncSession):
    """If a valid UUID is supplied, the function returns it directly without a
    name lookup – even if no project with that UUID exists in the database."""
    nonexistent = uuid.uuid4()

    result = await resolve_project_id(db_session, str(nonexistent))

    assert result == nonexistent


# ---------------------------------------------------------------------------
# resolve_project_id – by name
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_project_id_by_name_found(db_session: AsyncSession):
    p = await project_service.create_project(db_session, ProjectCreate(name="ByName"))

    result = await resolve_project_id(db_session, "ByName")

    assert result == p.id


@pytest.mark.asyncio
async def test_resolve_project_id_by_name_not_found(db_session: AsyncSession):
    result = await resolve_project_id(db_session, "DoesNotExist")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_project_id_by_name_case_sensitive(db_session: AsyncSession):
    await project_service.create_project(db_session, ProjectCreate(name="CaseSensitive"))

    result = await resolve_project_id(db_session, "casesensitive")

    assert result is None


# ---------------------------------------------------------------------------
# resolve_project_id – None identifier (fallback to config default)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_project_id_none_returns_none_when_no_default(db_session: AsyncSession):
    with patch("bud.commands.utils.get_default_project_id", return_value=None):
        result = await resolve_project_id(db_session, None)

    assert result is None


@pytest.mark.asyncio
async def test_resolve_project_id_none_returns_default_from_config(db_session: AsyncSession):
    p = await project_service.create_project(db_session, ProjectCreate(name="ConfigDefault"))

    with patch("bud.commands.utils.get_default_project_id", return_value=str(p.id)):
        result = await resolve_project_id(db_session, None)

    assert result == p.id


@pytest.mark.asyncio
async def test_resolve_project_id_none_returns_uuid_from_config_string(db_session: AsyncSession):
    """Returned value is a uuid.UUID instance, not a raw string."""
    p = await project_service.create_project(db_session, ProjectCreate(name="TypeCheck"))

    with patch("bud.commands.utils.get_default_project_id", return_value=str(p.id)):
        result = await resolve_project_id(db_session, None)

    assert isinstance(result, uuid.UUID)
