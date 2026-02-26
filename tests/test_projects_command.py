"""Integration tests for the 'project' CLI command group and all subcommands.

Strategy
--------
The project commands call ``get_session()`` (imported into the command module)
to obtain a database connection.  Each command wraps its async body in
``run_async()`` which calls ``asyncio.run()``.

Because ``asyncio.run()`` creates a new event loop on every invocation, we
cannot share a single SQLAlchemy ``AsyncSession`` across multiple
``runner.invoke()`` calls.  Instead we use a *file-backed* SQLite database
(via pytest's ``tmp_path``) so that every ``asyncio.run()`` call gets a fresh
connection to the same on-disk data.

``get_session`` in ``bud.commands.projects`` is patched with a factory that
opens this file database, then closes it after the context exits.

Configuration mutations (``set_config_value``) are mocked so that the real
``~/.bud/config.json`` is never touched during testing.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from unittest.mock import ANY, patch

import pytest
from click.testing import CliRunner
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bud.models  # noqa: F401 – ensures all models are registered with Base
from bud.commands.projects import project
from bud.cli import cli
from bud.database import Base
from bud.schemas.project import ProjectCreate
from bud.services import projects as project_service


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_db(tmp_path):
    """Provision a file-backed SQLite database and return its async URL."""
    db_file = tmp_path / "cli_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _init():
        engine = create_async_engine(db_url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_init())
    return db_url


def _make_get_session(db_url: str):
    """Return an async-context-manager factory that yields an AsyncSession
    backed by *db_url*.  A fresh engine is created and disposed on each call
    so that SQLAlchemy is always bound to the current event loop."""

    @asynccontextmanager
    async def _get_session():
        engine = create_async_engine(db_url, echo=False)

        @event.listens_for(engine.sync_engine, "connect")
        def _set_pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            yield session
        await engine.dispose()

    return _get_session


async def _seed(db_url: str, name: str, *, is_default: bool = False) -> tuple[uuid.UUID, str]:
    """Create a project in the test DB and return (id, name)."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        p = await project_service.create_project(session, ProjectCreate(name=name))
        if is_default:
            await project_service.set_default_project(session, p.id)
        result = (p.id, p.name)
    await engine.dispose()
    return result


async def _fetch_all(db_url: str):
    """Return all projects from the test DB."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        result = await project_service.list_projects(session)
    await engine.dispose()
    return result


# ---------------------------------------------------------------------------
# project list
# ---------------------------------------------------------------------------

def test_list_empty(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["list"])

    assert result.exit_code == 0
    assert "No projects found." in result.output


def test_list_shows_project_names(runner, cli_db):
    asyncio.run(_seed(cli_db, "Alpha"))
    asyncio.run(_seed(cli_db, "Beta"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["list"])

    assert result.exit_code == 0
    assert "Alpha" in result.output
    assert "Beta" in result.output


def test_list_shows_table_headers(runner, cli_db):
    asyncio.run(_seed(cli_db, "Omega"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["list"])

    assert result.exit_code == 0
    assert "#" in result.output
    assert "Name" in result.output
    assert "Default" in result.output


def test_list_marks_default_project(runner, cli_db):
    asyncio.run(_seed(cli_db, "Regular"))
    asyncio.run(_seed(cli_db, "DefaultOne", is_default=True))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["list"])

    assert result.exit_code == 0
    assert "Yes" in result.output


def test_list_shows_project_uuid_with_show_id(runner, cli_db):
    pid, _ = asyncio.run(_seed(cli_db, "WithUUID"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["list", "--show-id"])

    assert str(pid) in result.output


# ---------------------------------------------------------------------------
# project create
# ---------------------------------------------------------------------------

def test_create_success_message(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["create", "--name", "NewProj"])

    assert result.exit_code == 0
    assert "Created project: NewProj" in result.output


def test_create_prints_uuid(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["create", "--name", "HasUUID"])

    assert result.exit_code == 0
    assert "id:" in result.output


def test_create_persists_to_db(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        runner.invoke(project, ["create", "--name", "Persisted"])

    projects = asyncio.run(_fetch_all(cli_db))
    assert any(p.name == "Persisted" for p in projects)


def test_create_missing_name_fails(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["create"])

    assert result.exit_code != 0


def test_create_multiple_projects(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        runner.invoke(project, ["create", "--name", "P1"])
        runner.invoke(project, ["create", "--name", "P2"])

    projects = asyncio.run(_fetch_all(cli_db))
    names = {p.name for p in projects}
    assert {"P1", "P2"}.issubset(names)


# ---------------------------------------------------------------------------
# project edit
# ---------------------------------------------------------------------------

def test_edit_by_name_renames_project(runner, cli_db):
    asyncio.run(_seed(cli_db, "OldName"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["edit", "OldName", "--name", "NewName"])

    assert result.exit_code == 0
    assert "Updated project: NewName" in result.output


def test_edit_by_name_persists_change(runner, cli_db):
    asyncio.run(_seed(cli_db, "Before"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        runner.invoke(project, ["edit", "Before", "--name", "After"])

    projects = asyncio.run(_fetch_all(cli_db))
    names = {p.name for p in projects}
    assert "After" in names
    assert "Before" not in names


def test_edit_by_uuid_renames_project(runner, cli_db):
    pid, _ = asyncio.run(_seed(cli_db, "EditByUUID"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["edit", str(pid), "--name", "Renamed"])

    assert result.exit_code == 0
    assert "Updated project: Renamed" in result.output


def test_edit_nonexistent_project_outputs_error(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["edit", "GhostProject", "--name", "X"])

    assert result.exit_code == 0  # click.echo(..., err=True) does not set exit code
    assert "Project not found" in result.stderr


def test_edit_nonexistent_uuid_outputs_error(runner, cli_db):
    fake_id = str(uuid.uuid4())

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["edit", fake_id, "--name", "X"])

    # A UUID that doesn't exist resolves immediately (is_uuid returns True) but
    # update_project returns None → "Project not found." on stderr.
    assert "Project not found" in result.stderr or result.exit_code != 0


# ---------------------------------------------------------------------------
# project delete
# ---------------------------------------------------------------------------

def test_delete_by_name_with_yes_flag(runner, cli_db):
    asyncio.run(_seed(cli_db, "DeleteMe"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["delete", "DeleteMe", "--yes"])

    assert result.exit_code == 0
    assert "Project deleted." in result.output


def test_delete_by_name_removes_from_db(runner, cli_db):
    asyncio.run(_seed(cli_db, "Gone"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        runner.invoke(project, ["delete", "Gone", "--yes"])

    projects = asyncio.run(_fetch_all(cli_db))
    assert all(p.name != "Gone" for p in projects)


def test_delete_by_uuid_with_yes_flag(runner, cli_db):
    pid, _ = asyncio.run(_seed(cli_db, "DeleteByID"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["delete", str(pid), "--yes"])

    assert result.exit_code == 0
    assert "Project deleted." in result.output


def test_delete_nonexistent_outputs_error(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["delete", "NoSuchProject", "--yes"])

    assert "Project not found" in result.stderr


def test_delete_confirmation_prompt_abort(runner, cli_db):
    asyncio.run(_seed(cli_db, "SafeProject"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        # Answer 'n' to the confirmation prompt → Abort
        result = runner.invoke(project, ["delete", "SafeProject"], input="n\n")

    assert result.exit_code != 0
    # Project must still exist in DB
    projects = asyncio.run(_fetch_all(cli_db))
    assert any(p.name == "SafeProject" for p in projects)


def test_delete_confirmation_prompt_accept(runner, cli_db):
    asyncio.run(_seed(cli_db, "ConfirmDelete"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(project, ["delete", "ConfirmDelete"], input="y\n")

    assert result.exit_code == 0
    assert "Project deleted." in result.output


def test_delete_leaves_other_projects_intact(runner, cli_db):
    asyncio.run(_seed(cli_db, "Keep"))
    asyncio.run(_seed(cli_db, "Remove"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        runner.invoke(project, ["delete", "Remove", "--yes"])

    projects = asyncio.run(_fetch_all(cli_db))
    assert any(p.name == "Keep" for p in projects)


# ---------------------------------------------------------------------------
# project set-default
# ---------------------------------------------------------------------------

def test_set_default_by_name(runner, cli_db):
    asyncio.run(_seed(cli_db, "MainProject"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.projects.set_config_value") as mock_cfg:
        result = runner.invoke(project, ["set-default", "MainProject"])

    assert result.exit_code == 0
    assert "Default project set to: MainProject" in result.output


def test_set_default_updates_config(runner, cli_db):
    pid, _ = asyncio.run(_seed(cli_db, "ConfigProject"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.projects.set_config_value") as mock_cfg:
        runner.invoke(project, ["set-default", "ConfigProject"])

    mock_cfg.assert_called_once_with("default_project_id", str(pid))


def test_set_default_by_uuid(runner, cli_db):
    pid, _ = asyncio.run(_seed(cli_db, "UUIDDefault"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.projects.set_config_value"):
        result = runner.invoke(project, ["set-default", str(pid)])

    assert result.exit_code == 0
    assert "Default project set to: UUIDDefault" in result.output


def test_set_default_marks_project_in_db(runner, cli_db):
    pid, _ = asyncio.run(_seed(cli_db, "WillBeDefault"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.projects.set_config_value"):
        runner.invoke(project, ["set-default", "WillBeDefault"])

    projects = asyncio.run(_fetch_all(cli_db))
    defaults = [p for p in projects if p.is_default]
    assert len(defaults) == 1
    assert defaults[0].name == "WillBeDefault"


def test_set_default_switches_default(runner, cli_db):
    asyncio.run(_seed(cli_db, "OldDefault", is_default=True))
    asyncio.run(_seed(cli_db, "NewDefault"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.projects.set_config_value"):
        runner.invoke(project, ["set-default", "NewDefault"])

    projects = asyncio.run(_fetch_all(cli_db))
    defaults = [p for p in projects if p.is_default]
    assert len(defaults) == 1
    assert defaults[0].name == "NewDefault"


def test_set_default_nonexistent_outputs_error(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.projects.set_config_value"):
        result = runner.invoke(project, ["set-default", "GhostProject"])

    assert "Project not found" in result.stderr


def test_set_default_nonexistent_does_not_call_set_config(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.projects.set_config_value") as mock_cfg:
        runner.invoke(project, ["set-default", "NoSuchProject"])

    mock_cfg.assert_not_called()


# ---------------------------------------------------------------------------
# Alias: prjs (project list shortcut registered on the top-level cli)
# ---------------------------------------------------------------------------

def test_prjs_alias_lists_projects(runner, cli_db):
    asyncio.run(_seed(cli_db, "AliasProject"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(cli, ["prjs"])

    assert result.exit_code == 0
    assert "AliasProject" in result.output


def test_prjs_alias_empty(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(cli, ["prjs"])

    assert result.exit_code == 0
    assert "No projects found." in result.output


# ---------------------------------------------------------------------------
# Alias: prj (registered as an alias for the project command group)
# ---------------------------------------------------------------------------

def test_prj_alias_create(runner, cli_db):
    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(cli, ["prj", "create", "--name", "ViaAlias"])

    assert result.exit_code == 0
    assert "Created project: ViaAlias" in result.output


def test_prj_alias_list(runner, cli_db):
    asyncio.run(_seed(cli_db, "PrjAlias"))

    with patch("bud.commands.projects.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(cli, ["prj", "list"])

    assert result.exit_code == 0
    assert "PrjAlias" in result.output
