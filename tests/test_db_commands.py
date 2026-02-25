"""Unit and integration tests for the 'db' CLI command group and subcommands.

Strategy
--------
The db commands (init, destroy, reset) interact with the filesystem and the
SQLite database.  To avoid touching the real ``~/.bud/bud.db``:

* ``bud.commands.db_commands.DB_PATH`` is patched to a pytest ``tmp_path``
  file for every test.
* ``bud.commands.db_commands.get_engine`` is patched to return an
  async engine backed by the same tmp_path file so all SQLAlchemy operations
  go to the isolated test database.
* ``bud.commands.db_commands.set_config_value`` is patched so the real
  ``~/.bud/config.json`` is never touched.

push/pull subcommands are already thoroughly tested in ``test_sync.py``;
this file adds a small set of smoke tests that verify those commands are
accessible via the ``db`` command group and via the top-level ``cli``.
"""

import asyncio
import uuid
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bud.models  # noqa: F401 – registers all models with Base
from bud.cli import cli
from bud.commands.db_commands import db as db_cmd
from bud.database import Base
from bud.services import projects as project_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_get_engine(db_url: str):
    """Return a ``get_engine`` replacement that creates engines for *db_url*."""

    def _get_engine():
        eng = create_async_engine(db_url, echo=False)

        @event.listens_for(eng.sync_engine, "connect")
        def _set_pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return eng

    return _get_engine


async def _get_all_projects(db_url: str):
    """Return all Project rows from *db_url*."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        projects = await project_service.list_projects(session)
    await engine.dispose()
    return projects


async def _table_names(db_url: str) -> list:
    """Return a list of table names present in *db_url*."""
    engine = create_async_engine(db_url, echo=False)
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        names = [row[0] for row in result.fetchall()]
    await engine.dispose()
    return names


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_file(tmp_path):
    """Return a Path for a test database file (the file is NOT created yet)."""
    return tmp_path / "test.db"


@pytest.fixture
def db_url(db_file):
    return f"sqlite+aiosqlite:///{db_file}"


# ---------------------------------------------------------------------------
# db init – unit tests
# ---------------------------------------------------------------------------

class TestDbInit:

    def test_init_exits_successfully(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["init"])
        assert result.exit_code == 0

    def test_init_creates_db_file(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
        assert db_file.exists()

    def test_init_prints_db_path(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["init"])
        assert str(db_file) in result.output

    def test_init_prints_initialized_message(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["init"])
        assert "initialized" in result.output.lower()

    def test_init_creates_projects_table(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
        tables = asyncio.run(_table_names(db_url))
        assert "projects" in tables

    def test_init_creates_accounts_table(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
        tables = asyncio.run(_table_names(db_url))
        assert "accounts" in tables

    def test_init_creates_transactions_table(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
        tables = asyncio.run(_table_names(db_url))
        assert "transactions" in tables

    def test_init_creates_default_project(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
        projects = asyncio.run(_get_all_projects(db_url))
        assert any(p.name == "default" for p in projects)

    def test_init_default_project_is_marked_as_default(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
        projects = asyncio.run(_get_all_projects(db_url))
        defaults = [p for p in projects if p.is_default]
        assert len(defaults) == 1
        assert defaults[0].name == "default"

    def test_init_only_one_project_created(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
        projects = asyncio.run(_get_all_projects(db_url))
        assert len(projects) == 1

    def test_init_saves_default_project_id_to_config(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value") as mock_cfg:
            runner.invoke(db_cmd, ["init"])
        mock_cfg.assert_called_once()
        key, val = mock_cfg.call_args.args
        assert key == "default_project_id"
        uuid.UUID(val)  # raises ValueError if not a valid UUID

    def test_init_config_project_id_matches_db(self, runner, db_file, db_url):
        """The project_id written to config matches the project row in the DB."""
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value") as mock_cfg:
            runner.invoke(db_cmd, ["init"])
        saved_id = mock_cfg.call_args.args[1]
        projects = asyncio.run(_get_all_projects(db_url))
        assert str(projects[0].id) == saved_id

    def test_init_idempotent_exit_code(self, runner, db_file, db_url):
        """Running init twice does not raise an error."""
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
            result = runner.invoke(db_cmd, ["init"])
        assert result.exit_code == 0

    def test_init_idempotent_single_default_project(self, runner, db_file, db_url):
        """Running init twice does not create a duplicate 'default' project."""
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["init"])
            runner.invoke(db_cmd, ["init"])
        projects = asyncio.run(_get_all_projects(db_url))
        named_default = [p for p in projects if p.name == "default"]
        assert len(named_default) == 1

    def test_init_via_cli_group(self, runner, db_file, db_url):
        """db init is reachable via the top-level cli group."""
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(cli, ["db", "init"])
        assert result.exit_code == 0
        assert db_file.exists()


# ---------------------------------------------------------------------------
# db destroy – unit tests
# ---------------------------------------------------------------------------

class TestDbDestroy:

    def test_destroy_with_yes_flag_exits_successfully(self, runner, db_file):
        db_file.write_bytes(b"fake-db-content")
        with patch("bud.commands.db_commands.DB_PATH", db_file):
            result = runner.invoke(db_cmd, ["destroy", "--yes"])
        assert result.exit_code == 0

    def test_destroy_removes_db_file(self, runner, db_file):
        db_file.write_bytes(b"fake-db-content")
        with patch("bud.commands.db_commands.DB_PATH", db_file):
            runner.invoke(db_cmd, ["destroy", "--yes"])
        assert not db_file.exists()

    def test_destroy_outputs_deleted_message(self, runner, db_file):
        db_file.write_bytes(b"fake-db-content")
        with patch("bud.commands.db_commands.DB_PATH", db_file):
            result = runner.invoke(db_cmd, ["destroy", "--yes"])
        assert "Database deleted" in result.output

    def test_destroy_outputs_db_path(self, runner, db_file):
        db_file.write_bytes(b"data")
        with patch("bud.commands.db_commands.DB_PATH", db_file):
            result = runner.invoke(db_cmd, ["destroy", "--yes"])
        assert str(db_file) in result.output

    def test_destroy_nonexistent_db_outputs_message(self, runner, db_file):
        # db_file does not exist
        with patch("bud.commands.db_commands.DB_PATH", db_file):
            result = runner.invoke(db_cmd, ["destroy", "--yes"])
        assert result.exit_code == 0
        assert "does not exist" in result.output.lower()

    def test_destroy_aborts_on_no_confirmation(self, runner, db_file):
        db_file.write_bytes(b"keep-me")
        with patch("bud.commands.db_commands.DB_PATH", db_file):
            result = runner.invoke(db_cmd, ["destroy"], input="n\n")
        assert result.exit_code != 0
        assert db_file.exists()

    def test_destroy_proceeds_on_yes_confirmation(self, runner, db_file):
        db_file.write_bytes(b"delete-me")
        with patch("bud.commands.db_commands.DB_PATH", db_file):
            result = runner.invoke(db_cmd, ["destroy"], input="y\n")
        assert result.exit_code == 0
        assert not db_file.exists()

    def test_destroy_via_cli_group(self, runner, db_file):
        db_file.write_bytes(b"to-be-deleted")
        with patch("bud.commands.db_commands.DB_PATH", db_file):
            result = runner.invoke(cli, ["db", "destroy", "--yes"])
        assert result.exit_code == 0
        assert not db_file.exists()


# ---------------------------------------------------------------------------
# db reset – unit tests
# ---------------------------------------------------------------------------

class TestDbReset:

    def test_reset_exits_successfully(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["reset", "--yes"])
        assert result.exit_code == 0

    def test_reset_creates_db_file(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["reset", "--yes"])
        assert db_file.exists()

    def test_reset_creates_default_project(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["reset", "--yes"])
        projects = asyncio.run(_get_all_projects(db_url))
        assert any(p.name == "default" for p in projects)

    def test_reset_default_project_is_marked_as_default(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["reset", "--yes"])
        projects = asyncio.run(_get_all_projects(db_url))
        defaults = [p for p in projects if p.is_default]
        assert len(defaults) == 1
        assert defaults[0].name == "default"

    def test_reset_only_one_project_created(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["reset", "--yes"])
        projects = asyncio.run(_get_all_projects(db_url))
        assert len(projects) == 1

    def test_reset_outputs_initialized_message(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["reset", "--yes"])
        assert "initialized" in result.output.lower()

    def test_reset_outputs_reset_complete_message(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["reset", "--yes"])
        assert "reset complete" in result.output.lower()

    def test_reset_deletes_old_db_when_present(self, runner, db_file, db_url):
        db_file.write_bytes(b"old-data")
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["reset", "--yes"])
        assert "Database deleted" in result.output

    def test_reset_saves_default_project_id_to_config(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value") as mock_cfg:
            runner.invoke(db_cmd, ["reset", "--yes"])
        mock_cfg.assert_called_once()
        key, val = mock_cfg.call_args.args
        assert key == "default_project_id"
        uuid.UUID(val)  # raises ValueError if not a valid UUID

    def test_reset_aborts_on_no_confirmation(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["reset"], input="n\n")
        assert result.exit_code != 0

    def test_reset_proceeds_on_yes_input(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(db_cmd, ["reset"], input="y\n")
        assert result.exit_code == 0

    def test_reset_via_cli_group(self, runner, db_file, db_url):
        """db reset is reachable via the top-level cli group."""
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            result = runner.invoke(cli, ["db", "reset", "--yes"])
        assert result.exit_code == 0
        assert db_file.exists()

    def test_reset_creates_tables(self, runner, db_file, db_url):
        with patch("bud.commands.db_commands.DB_PATH", db_file), \
             patch("bud.commands.db_commands.get_engine", new=_make_test_get_engine(db_url)), \
             patch("bud.commands.db_commands.set_config_value"):
            runner.invoke(db_cmd, ["reset", "--yes"])
        tables = asyncio.run(_table_names(db_url))
        assert "projects" in tables
        assert "accounts" in tables
        assert "transactions" in tables


# ---------------------------------------------------------------------------
# db push / pull – smoke tests (full coverage in test_sync.py)
# ---------------------------------------------------------------------------

class TestDbPushPullRegistered:
    """Verify push and pull are accessible as subcommands of 'db'."""

    def test_push_subcommand_exists(self):
        assert "push" in db_cmd.commands

    def test_pull_subcommand_exists(self):
        assert "pull" in db_cmd.commands

    def test_push_requires_db_to_exist(self, runner, tmp_path, monkeypatch):
        bud_dir = tmp_path / ".bud"
        bud_dir.mkdir()
        db_file = bud_dir / "bud.db"  # intentionally does not exist
        config_file = bud_dir / "config.json"
        config_file.write_text('{"bucket": "s3://test-bucket"}')

        monkeypatch.setattr("bud.commands.sync.DB_PATH", db_file)
        monkeypatch.setattr("bud.commands.sync.CONFIG_DIR", bud_dir)
        monkeypatch.setattr("bud.commands.sync.SYNC_META_FILE", bud_dir / "sync_meta.json")
        monkeypatch.setattr("bud.commands.config_store.CONFIG_DIR", bud_dir)
        monkeypatch.setattr("bud.commands.config_store.CONFIG_FILE", config_file)

        result = runner.invoke(cli, ["db", "push"])
        assert result.exit_code != 0
        assert "does not exist" in result.output.lower()

    def test_pull_requires_bucket_configured(self, runner, tmp_path, monkeypatch):
        bud_dir = tmp_path / ".bud"
        bud_dir.mkdir()
        config_file = bud_dir / "config.json"
        config_file.write_text("{}")

        monkeypatch.setattr("bud.commands.sync.CONFIG_DIR", bud_dir)
        monkeypatch.setattr("bud.commands.sync.DB_PATH", bud_dir / "bud.db")
        monkeypatch.setattr("bud.commands.sync.SYNC_META_FILE", bud_dir / "sync_meta.json")
        monkeypatch.setattr("bud.commands.config_store.CONFIG_DIR", bud_dir)
        monkeypatch.setattr("bud.commands.config_store.CONFIG_FILE", config_file)

        result = runner.invoke(cli, ["db", "pull"])
        assert result.exit_code != 0
        assert "no bucket configured" in result.output.lower()
