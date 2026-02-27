"""Integration tests for the 'account' CLI command group and all subcommands.

Strategy
--------
The account commands call ``get_session()`` (imported into the command module)
to obtain a database connection.  Each command wraps its async body in
``run_async()`` which calls ``asyncio.run()``.

Because ``asyncio.run()`` creates a new event loop on every invocation, we
cannot share a single SQLAlchemy ``AsyncSession`` across multiple
``runner.invoke()`` calls.  Instead we use a *file-backed* SQLite database
(via pytest's ``tmp_path``) so that every ``asyncio.run()`` call gets a fresh
connection to the same on-disk data.

``get_session`` in ``bud.commands.accounts`` is patched with a factory that
opens this file database, then closes it after the context exits.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bud.models  # noqa: F401 – ensures all models are registered with Base
from bud.cli import cli
from bud.commands.accounts import account
from bud.database import Base
from bud.models.account import AccountType
from bud.schemas.account import AccountCreate
from bud.schemas.project import ProjectCreate
from bud.services import accounts as account_service
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


async def _seed_project(
    db_url: str, name: str, *, is_default: bool = False
) -> tuple[uuid.UUID, str]:
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


async def _seed_account(
    db_url: str,
    project_id: uuid.UUID,
    name: str,
    account_type: AccountType = AccountType.debit,
    initial_balance: float = 0.0,
) -> tuple[uuid.UUID, str]:
    """Create an account in the test DB and return (id, name)."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        a = await account_service.create_account(
            session,
            AccountCreate(
                name=name,
                type=account_type,
                project_id=project_id,
                initial_balance=initial_balance,
            ),
        )
        result = (a.id, a.name)
    await engine.dispose()
    return result


async def _fetch_all_accounts(db_url: str, project_id: uuid.UUID):
    """Return all accounts for a project from the test DB."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        result = await account_service.list_accounts(session, project_id)
    await engine.dispose()
    return result


# ---------------------------------------------------------------------------
# account list
# ---------------------------------------------------------------------------

def test_list_empty(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["list"])

    assert result.exit_code == 0
    assert "no accounts found." in result.output


def test_list_shows_account_names(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_account(cli_db, pid, "Savings"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["list"])

    assert result.exit_code == 0
    assert "Checking" in result.output
    assert "Savings" in result.output


def test_list_shows_table_headers(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["list"])

    assert result.exit_code == 0
    assert "id" not in result.output.split("\n")[0]
    assert "name" in result.output
    assert "type" in result.output
    assert "initial balance" in result.output
    assert "current balance" in result.output


def test_list_does_not_show_uuid_by_default(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "WithUUID"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["list"])

    assert str(aid) not in result.output


def test_list_shows_uuid_with_show_id_flag(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "WithUUID"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["list", "--show-id"])

    assert result.exit_code == 0
    assert "id" in result.output
    assert str(aid) in result.output


def test_list_sorted_by_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "Zebra"))
    asyncio.run(_seed_account(cli_db, pid, "Alpha"))
    asyncio.run(_seed_account(cli_db, pid, "Mango"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["list"])

    assert result.exit_code == 0
    pos_alpha = result.output.index("Alpha")
    pos_mango = result.output.index("Mango")
    pos_zebra = result.output.index("Zebra")
    assert pos_alpha < pos_mango < pos_zebra


def test_list_shows_account_type(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "CreditCard", AccountType.credit))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["list"])

    assert "credit" in result.output


def test_list_by_project_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "NamedProject"))
    asyncio.run(_seed_account(cli_db, pid, "ByName"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["list", "--project", "NamedProject"])

    assert result.exit_code == 0
    assert "ByName" in result.output


def test_list_by_project_uuid(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "UUIDProject"))
    asyncio.run(_seed_account(cli_db, pid, "ByUUID"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["list", "--project", str(pid)])

    assert result.exit_code == 0
    assert "ByUUID" in result.output


def test_list_no_project_shows_error(runner, cli_db):
    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=None):
        result = runner.invoke(account, ["list"])

    assert result.exit_code == 0
    assert "error" in result.stderr
    assert "no project specified" in result.stderr


def test_list_only_shows_project_accounts(runner, cli_db):
    pid1, _ = asyncio.run(_seed_project(cli_db, "Proj1"))
    pid2, _ = asyncio.run(_seed_project(cli_db, "Proj2"))
    asyncio.run(_seed_account(cli_db, pid1, "Proj1Account"))
    asyncio.run(_seed_account(cli_db, pid2, "Proj2Account"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["list", "--project", str(pid1)])

    assert "Proj1Account" in result.output
    assert "Proj2Account" not in result.output


# ---------------------------------------------------------------------------
# account create
# ---------------------------------------------------------------------------

def test_create_success_message(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["create", "NewAccount"])

    assert result.exit_code == 0
    assert "created account: NewAccount" in result.output


def test_create_prints_uuid(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["create", "HasUUID"])

    assert result.exit_code == 0
    assert "id:" in result.output


def test_create_default_type_is_debit(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["create", "DebitAcc"])

    assert result.exit_code == 0
    assert "debit" in result.output


def test_create_credit_type(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["create", "CreditCard", "--type", "credit"])

    assert result.exit_code == 0
    assert "credit" in result.output


def test_create_with_initial_balance(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["create", "WithBalance", "--initial-balance", "500"])

    assert result.exit_code == 0
    assert "created account: WithBalance" in result.output


def test_create_persists_to_db(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        runner.invoke(account, ["create", "Persisted"])

    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    assert any(a.name == "Persisted" for a in accounts)


def test_create_by_project_name(runner, cli_db):
    asyncio.run(_seed_project(cli_db, "NamedProj"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["create", "ViaName", "--project", "NamedProj"])

    assert result.exit_code == 0
    assert "created account: ViaName" in result.output


def test_create_by_project_uuid(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "UUIDProj"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["create", "ViaUUID", "--project", str(pid)])

    assert result.exit_code == 0
    assert "created account: ViaUUID" in result.output


def test_create_missing_name_fails(runner, cli_db):
    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["create"])

    assert result.exit_code != 0


def test_create_invalid_type_fails(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["create", "BadType", "--type", "savings"])

    assert result.exit_code != 0


def test_create_duplicate_name_shows_error(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "Existing"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(account, ["create", "Existing"])

    assert result.exit_code == 0
    assert "error" in result.stderr
    assert "already exists" in result.stderr


def test_create_no_project_shows_error(runner, cli_db):
    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=None):
        result = runner.invoke(account, ["create", "NoProject"])

    assert result.exit_code == 0
    assert "error" in result.stderr
    assert "no project specified" in result.stderr


def test_create_multiple_accounts(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        runner.invoke(account, ["create", "Acc1"])
        runner.invoke(account, ["create", "Acc2"])

    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    names = {a.name for a in accounts}
    assert {"Acc1", "Acc2"}.issubset(names)


# ---------------------------------------------------------------------------
# account edit
# ---------------------------------------------------------------------------

def test_edit_by_uuid_renames_account(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "OldName"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["edit", str(aid), "--name", "NewName"])

    assert result.exit_code == 0
    assert "updated: NewName" in result.output


def test_edit_by_uuid_persists_change(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Before"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        runner.invoke(account, ["edit", str(aid), "--name", "After"])

    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    names = {a.name for a in accounts}
    assert "After" in names
    assert "Before" not in names


def test_edit_by_name_renames_account(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "ByName"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            account, ["edit", "ByName", "--name", "Renamed", "--project", str(pid)]
        )

    assert result.exit_code == 0
    assert "updated: Renamed" in result.output


def test_edit_by_name_with_project_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "EditProject"))
    asyncio.run(_seed_account(cli_db, pid, "EditMe"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            account, ["edit", "EditMe", "--name", "Edited", "--project", "EditProject"]
        )

    assert result.exit_code == 0
    assert "updated: Edited" in result.output


def test_edit_changes_type(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "TypeChange", AccountType.debit))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["edit", str(aid), "--type", "credit"])

    assert result.exit_code == 0
    assert "credit" in result.output


def test_edit_nonexistent_uuid_outputs_error(runner, cli_db):
    fake_id = str(uuid.uuid4())

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["edit", fake_id, "--name", "X"])

    assert "account not found" in result.stderr or result.exit_code != 0


def test_edit_by_name_no_project_shows_error(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "NeedProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=None):
        result = runner.invoke(account, ["edit", "NeedProject", "--name", "New"])

    assert result.exit_code == 0
    assert "error" in result.stderr
    assert "--project required" in result.stderr


def test_edit_initial_balance(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "BalanceAcc", initial_balance=100.0))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["edit", str(aid), "--initial-balance", "250"])

    assert result.exit_code == 0
    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    acc = next(a for a in accounts if a.id == aid)
    assert float(acc.initial_balance) == 250.0


def test_edit_current_balance(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "CurrBalAcc", initial_balance=50.0))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["edit", str(aid), "--current-balance", "999"])

    assert result.exit_code == 0
    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    acc = next(a for a in accounts if a.id == aid)
    assert float(acc.current_balance) == 999.0


def test_edit_both_balances(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "BothBalAcc"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["edit", str(aid), "--initial-balance", "10", "--current-balance", "20"])

    assert result.exit_code == 0
    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    acc = next(a for a in accounts if a.id == aid)
    assert float(acc.initial_balance) == 10.0
    assert float(acc.current_balance) == 20.0


def test_edit_by_name_not_found_in_project(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            account, ["edit", "GhostAccount", "--name", "X", "--project", str(pid)]
        )

    assert result.exit_code == 0
    assert "account not found" in result.stderr


# ---------------------------------------------------------------------------
# account delete
# ---------------------------------------------------------------------------

def test_delete_by_uuid_with_yes_flag(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "DeleteMe"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["delete", str(aid), "--yes"])

    assert result.exit_code == 0
    assert "account deleted." in result.output


def test_delete_by_uuid_removes_from_db(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Gone"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        runner.invoke(account, ["delete", str(aid), "--yes"])

    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    assert all(a.id != aid for a in accounts)


def test_delete_by_name_with_yes_flag(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "DeleteByName"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            account, ["delete", "DeleteByName", "--project", str(pid), "--yes"]
        )

    assert result.exit_code == 0
    assert "account deleted." in result.output


def test_delete_by_name_removes_from_db(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "ByNameGone"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        runner.invoke(account, ["delete", "ByNameGone", "--project", str(pid), "--yes"])

    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    assert all(a.name != "ByNameGone" for a in accounts)


def test_delete_nonexistent_uuid_outputs_error(runner, cli_db):
    fake_id = str(uuid.uuid4())

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["delete", fake_id, "--yes"])

    assert "account not found" in result.stderr


def test_delete_nonexistent_name_outputs_error(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            account, ["delete", "NoSuchAccount", "--project", str(pid), "--yes"]
        )

    assert "account not found" in result.stderr


def test_delete_confirmation_prompt_abort(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "SafeAccount"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["delete", str(aid)], input="n\n")

    assert result.exit_code != 0
    # Account must still exist in DB
    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    assert any(a.id == aid for a in accounts)


def test_delete_confirmation_prompt_accept(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "ConfirmDelete"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(account, ["delete", str(aid)], input="y\n")

    assert result.exit_code == 0
    assert "account deleted." in result.output


def test_delete_leaves_other_accounts_intact(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "Keep"))
    aid2, _ = asyncio.run(_seed_account(cli_db, pid, "Remove"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        runner.invoke(account, ["delete", str(aid2), "--yes"])

    accounts = asyncio.run(_fetch_all_accounts(cli_db, pid))
    assert any(a.name == "Keep" for a in accounts)


def test_delete_by_name_no_project_shows_error(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "NeedProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=None):
        result = runner.invoke(account, ["delete", "NeedProject", "--yes"])

    assert result.exit_code == 0
    assert "error" in result.stderr
    assert "--project required" in result.stderr


# ---------------------------------------------------------------------------
# Alias: acc (account command group alias registered on the top-level cli)
# ---------------------------------------------------------------------------

def test_acc_alias_creates_account(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(cli, ["acc", "create", "ViaAlias"])

    assert result.exit_code == 0
    assert "created account: ViaAlias" in result.output


def test_acc_alias_lists_accounts(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "AliasAccount"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(cli, ["acc", "list"])

    assert result.exit_code == 0
    assert "AliasAccount" in result.output


# ---------------------------------------------------------------------------
# Shortcut: accs (lists accounts directly from top-level cli)
# ---------------------------------------------------------------------------

def test_accs_shortcut_lists_accounts(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "ShortcutAccount"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(cli, ["accs"])

    assert result.exit_code == 0
    assert "ShortcutAccount" in result.output


def test_accs_shortcut_empty(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(cli, ["accs"])

    assert result.exit_code == 0
    assert "no accounts found." in result.output


def test_accs_shortcut_with_project_option(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "SpecificProject"))
    asyncio.run(_seed_account(cli_db, pid, "SpecificAccount"))

    with patch("bud.commands.accounts.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(cli, ["accs", "--project", str(pid)])

    assert result.exit_code == 0
    assert "SpecificAccount" in result.output
