"""Integration tests for the 'transaction' CLI command group and all subcommands.

Strategy
--------
The transaction commands call ``get_session()`` (imported into the command
module) to obtain a database connection.  Each command wraps its async body in
``run_async()`` which calls ``asyncio.run()``.

Because ``asyncio.run()`` creates a new event loop on every invocation, we
cannot share a single SQLAlchemy ``AsyncSession`` across multiple
``runner.invoke()`` calls.  Instead we use a *file-backed* SQLite database
(via pytest's ``tmp_path``) so that every ``asyncio.run()`` call gets a fresh
connection to the same on-disk data.

``get_session`` in ``bud.commands.transactions`` is patched with a factory that
opens this file database, then closes it after the context exits.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bud.models  # noqa: F401 – ensures all models are registered with Base
from bud.cli import cli
from bud.commands.transactions import transaction
from bud.database import Base
from bud.models.account import AccountType
from bud.schemas.account import AccountCreate
from bud.schemas.category import CategoryCreate
from bud.schemas.project import ProjectCreate
from bud.schemas.transaction import TransactionCreate
from bud.services import accounts as account_service
from bud.services import categories as category_service
from bud.services import projects as project_service
from bud.services import transactions as transaction_service


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


async def _seed_category(db_url: str, name: str) -> tuple[uuid.UUID, str]:
    """Create a category in the test DB and return (id, name)."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        c = await category_service.create_category(session, CategoryCreate(name=name))
        result = (c.id, c.name)
    await engine.dispose()
    return result


async def _seed_transaction(
    db_url: str,
    project_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    value: Decimal = Decimal("-50.00"),
    description: str = "Groceries",
    txn_date: date = date(2025, 1, 15),
    category_id: uuid.UUID = None,
    tags: list = None,
) -> tuple[uuid.UUID, str]:
    """Create a transaction in the test DB and return (id, description)."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        t = await transaction_service.create_transaction(
            session,
            TransactionCreate(
                value=value,
                description=description,
                date=txn_date,
                account_id=account_id,
                project_id=project_id,
                category_id=category_id,
                tags=tags or [],
            ),
        )
        result = (t.id, t.description)
    await engine.dispose()
    return result


async def _fetch_all_transactions(db_url: str, project_id: uuid.UUID) -> list:
    """Return all transactions for a project from the test DB."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        result = await transaction_service.list_transactions(session, project_id)
    await engine.dispose()
    return result


async def _fetch_transaction(db_url: str, transaction_id: uuid.UUID):
    """Return a single transaction by ID from the test DB."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        result = await transaction_service.get_transaction(session, transaction_id)
    await engine.dispose()
    return result


# ---------------------------------------------------------------------------
# transaction list
# ---------------------------------------------------------------------------

def test_list_empty(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)), \
         patch("bud.commands.utils.get_active_month", return_value="2025-01"):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "No transactions found." in result.output


def test_list_shows_transaction_descriptions(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="Groceries", txn_date=date(2025, 1, 10)))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="Rent", txn_date=date(2025, 1, 5)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "Groceries" in result.output
    assert "Rent" in result.output


def test_list_shows_table_headers(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "#" in result.output
    assert "Date" in result.output
    assert "Description" in result.output
    assert "Value" in result.output
    assert "Account" in result.output


def test_list_does_not_show_uuid_by_default(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert str(tid) not in result.output


def test_list_shows_uuid_with_show_id_flag(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["list", "--month", "2025-01", "--show-id"])

    assert result.exit_code == 0
    assert "ID" in result.output
    assert str(tid) in result.output


def test_list_shows_account_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "MyBank"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "MyBank" in result.output


def test_list_shows_transaction_value(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, value=Decimal("-99.99"), txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "99.99" in result.output


def test_list_by_project_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "NamedProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="ByName", txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            transaction, ["list", "--month", "2025-01", "--project", "NamedProject"]
        )

    assert result.exit_code == 0
    assert "ByName" in result.output


def test_list_by_project_uuid(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "UUIDProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="ByUUID", txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            transaction, ["list", "--month", "2025-01", "--project", str(pid)]
        )

    assert result.exit_code == 0
    assert "ByUUID" in result.output


def test_list_no_project_shows_error(runner, cli_db):
    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=None):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "Error" in result.stderr
    assert "no project specified" in result.stderr


def test_list_filters_by_month(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="JanTx", txn_date=date(2025, 1, 15)))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="FebTx", txn_date=date(2025, 2, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "JanTx" in result.output
    assert "FebTx" not in result.output


def test_list_only_shows_project_transactions(runner, cli_db):
    pid1, _ = asyncio.run(_seed_project(cli_db, "Proj1"))
    pid2, _ = asyncio.run(_seed_project(cli_db, "Proj2"))
    aid1, _ = asyncio.run(_seed_account(cli_db, pid1, "Acc1"))
    aid2, _ = asyncio.run(_seed_account(cli_db, pid2, "Acc2"))
    asyncio.run(_seed_transaction(cli_db, pid1, aid1, description="Proj1Tx", txn_date=date(2025, 1, 10)))
    asyncio.run(_seed_transaction(cli_db, pid2, aid2, description="Proj2Tx", txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            transaction, ["list", "--month", "2025-01", "--project", str(pid1)]
        )

    assert result.exit_code == 0
    assert "Proj1Tx" in result.output
    assert "Proj2Tx" not in result.output


def test_list_uses_default_month(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="MarchTx", txn_date=date(2025, 3, 15)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)), \
         patch("bud.commands.utils.get_active_month", return_value="2025-03"):
        result = runner.invoke(transaction, ["list"])

    assert result.exit_code == 0
    assert "MarchTx" in result.output


def test_list_no_month_defaults_to_current_month(runner, cli_db):
    from datetime import date
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    current_month = date.today().strftime("%Y-%m")

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)), \
         patch("bud.commands.utils.get_active_month", return_value=current_month):
        result = runner.invoke(transaction, ["list"])

    assert result.exit_code == 0
    assert "Error" not in result.output and "Error" not in result.stderr


# ---------------------------------------------------------------------------
# transaction show
# ---------------------------------------------------------------------------

def test_show_displays_transaction_details(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "MyBank"))
    tid, _ = asyncio.run(
        _seed_transaction(
            cli_db, pid, aid,
            value=Decimal("-150.00"),
            description="Electric Bill",
            txn_date=date(2025, 1, 20),
        )
    )

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["show", str(tid)])

    assert result.exit_code == 0
    assert "Electric Bill" in result.output
    assert "MyBank" in result.output
    assert str(tid) in result.output


def test_show_displays_date(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(
        _seed_transaction(cli_db, pid, aid, txn_date=date(2025, 6, 15))
    )

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["show", str(tid)])

    assert result.exit_code == 0
    assert "2025-06-15" in result.output


def test_show_displays_value(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(
        _seed_transaction(cli_db, pid, aid, value=Decimal("500.00"), txn_date=date(2025, 1, 5))
    )

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["show", str(tid)])

    assert result.exit_code == 0
    assert "500" in result.output


def test_show_displays_tags(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(
        _seed_transaction(cli_db, pid, aid, tags=["food", "weekly"], txn_date=date(2025, 1, 5))
    )

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["show", str(tid)])

    assert result.exit_code == 0
    assert "food" in result.output
    assert "weekly" in result.output


def test_show_displays_category_id(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    cid, _ = asyncio.run(_seed_category(cli_db, "Groceries"))
    tid, _ = asyncio.run(
        _seed_transaction(cli_db, pid, aid, category_id=cid, txn_date=date(2025, 1, 5))
    )

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["show", str(tid)])

    assert result.exit_code == 0
    assert str(cid) in result.output


def test_show_no_tags_displays_dash(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(
        _seed_transaction(cli_db, pid, aid, tags=[], txn_date=date(2025, 1, 5))
    )

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["show", str(tid)])

    assert result.exit_code == 0
    assert "Tags:" in result.output


def test_show_not_found(runner, cli_db):
    fake_id = str(uuid.uuid4())

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["show", fake_id])

    assert result.exit_code == 0
    assert "Transaction not found" in result.stderr


def test_show_displays_field_labels(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 5)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["show", str(tid)])

    assert result.exit_code == 0
    assert "ID:" in result.output
    assert "Date:" in result.output
    assert "Description:" in result.output
    assert "Value:" in result.output
    assert "Account:" in result.output
    assert "Category:" in result.output
    assert "Tags:" in result.output


# ---------------------------------------------------------------------------
# transaction create
# ---------------------------------------------------------------------------

def test_create_success_message(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-50.00",
            "--description", "Coffee",
            "--account", str(aid),
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Created transaction" in result.output
    assert "Coffee" in result.output


def test_create_prints_id(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-10.00",
            "--description", "Tea",
            "--account", str(aid),
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "id:" in result.output


def test_create_persists_to_db(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        runner.invoke(transaction, [
            "create",
            "--value", "-25.00",
            "--description", "Persisted",
            "--account", str(aid),
            "--date", "2025-01-10",
        ])

    txns = asyncio.run(_fetch_all_transactions(cli_db, pid))
    assert any(t.description == "Persisted" for t in txns)


def test_create_with_account_by_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    asyncio.run(_seed_account(cli_db, pid, "Savings"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-30.00",
            "--description", "ViaName",
            "--account", "Savings",
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Created transaction" in result.output


def test_create_with_project_by_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "NamedProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-20.00",
            "--description", "ViaProjectName",
            "--account", str(aid),
            "--project", "NamedProject",
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Created transaction" in result.output


def test_create_with_project_by_uuid(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "UUIDProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-20.00",
            "--description", "ViaProjectUUID",
            "--account", str(aid),
            "--project", str(pid),
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Created transaction" in result.output


def test_create_with_category(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    cid, _ = asyncio.run(_seed_category(cli_db, "Food"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-50.00",
            "--description", "WithCategory",
            "--account", str(aid),
            "--category", str(cid),
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Created transaction" in result.output

    txns = asyncio.run(_fetch_all_transactions(cli_db, pid))
    cat_txn = next((t for t in txns if t.description == "WithCategory"), None)
    assert cat_txn is not None
    assert cat_txn.category_id == cid


def test_create_with_category_by_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_category(cli_db, "Transport"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-30.00",
            "--description", "CategoryByName",
            "--account", str(aid),
            "--category", "Transport",
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Created transaction" in result.output


def test_create_with_tags(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-15.00",
            "--description", "Tagged",
            "--account", str(aid),
            "--tags", "food,weekly",
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    txns = asyncio.run(_fetch_all_transactions(cli_db, pid))
    tagged_txn = next((t for t in txns if t.description == "Tagged"), None)
    assert tagged_txn is not None
    assert "food" in tagged_txn.tags
    assert "weekly" in tagged_txn.tags


def test_create_positive_value_income(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "1000.00",
            "--description", "Salary",
            "--account", str(aid),
            "--date", "2025-01-01",
        ])

    assert result.exit_code == 0
    assert "Created transaction" in result.output

    txns = asyncio.run(_fetch_all_transactions(cli_db, pid))
    salary = next((t for t in txns if t.description == "Salary"), None)
    assert salary is not None
    assert salary.value == Decimal("1000.00")


def test_create_no_project_shows_error(runner, cli_db):
    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=None):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-50.00",
            "--description", "NoProject",
            "--account", str(uuid.uuid4()),
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Error" in result.stderr
    assert "no project specified" in result.stderr


def test_create_account_not_found_shows_error(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-50.00",
            "--description", "BadAccount",
            "--account", "nonexistent-account-name",
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Account not found" in result.stderr


def test_create_missing_value_fails(runner, cli_db):
    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, [
            "create",
            "--description", "MissingValue",
            "--account", str(uuid.uuid4()),
        ])

    assert result.exit_code != 0


def test_create_missing_description_fails(runner, cli_db):
    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-50.00",
            "--account", str(uuid.uuid4()),
        ])

    assert result.exit_code != 0


def test_create_missing_account_fails(runner, cli_db):
    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-50.00",
            "--description", "MissingAccount",
        ])

    assert result.exit_code != 0


def test_create_new_category_via_confirm(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(
            transaction,
            [
                "create",
                "--value", "-10.00",
                "--description", "NewCatTx",
                "--account", str(aid),
                "--category", "NewCategory",
                "--date", "2025-01-10",
            ],
            input="y\n",
        )

    assert result.exit_code == 0
    assert "Created category" in result.output or "Created transaction" in result.output


def test_create_new_category_decline_aborts(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(
            transaction,
            [
                "create",
                "--value", "-10.00",
                "--description", "AbortedCatTx",
                "--account", str(aid),
                "--category", "UnknownCategory",
                "--date", "2025-01-10",
            ],
            input="n\n",
        )

    assert result.exit_code == 0
    txns = asyncio.run(_fetch_all_transactions(cli_db, pid))
    assert all(t.description != "AbortedCatTx" for t in txns)


def test_create_category_uuid_not_found_errors(runner, cli_db):
    # resolve_category_id returns the UUID directly without verifying existence;
    # the DB then raises an FK IntegrityError, so the command exits non-zero.
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, [
            "create",
            "--value", "-10.00",
            "--description", "BadCatUUID",
            "--account", str(aid),
            "--category", str(uuid.uuid4()),
            "--date", "2025-01-10",
        ])

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# transaction edit
# ---------------------------------------------------------------------------

def test_edit_description(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, description="OldDescription"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["edit", "--id", str(tid), "--description", "NewDescription"])

    assert result.exit_code == 0
    assert "Updated transaction" in result.output
    assert "NewDescription" in result.output


def test_edit_persists_description(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, description="Before"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        runner.invoke(transaction, ["edit", "--id", str(tid), "--description", "After"])

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched.description == "After"


def test_edit_value(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, value=Decimal("-50.00")))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["edit", "--id", str(tid), "--value", "-99.99"])

    assert result.exit_code == 0

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched.value == Decimal("-99.99")


def test_edit_date(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 1)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["edit", "--id", str(tid), "--date", "2025-06-15"])

    assert result.exit_code == 0

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched.date == date(2025, 6, 15)


def test_edit_tags(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, tags=["old"]))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["edit", "--id", str(tid), "--tags", "new,updated"])

    assert result.exit_code == 0

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert "new" in fetched.tags
    assert "updated" in fetched.tags


def test_edit_category_by_uuid(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    cid, _ = asyncio.run(_seed_category(cli_db, "Transport"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["edit", "--id", str(tid), "--category", str(cid)])

    assert result.exit_code == 0

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched.category_id == cid


def test_edit_category_by_name(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    cid, _ = asyncio.run(_seed_category(cli_db, "Housing"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["edit", "--id", str(tid), "--category", "Housing"])

    assert result.exit_code == 0

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched.category_id == cid


def test_edit_partial_preserves_other_fields(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(
        _seed_transaction(
            cli_db, pid, aid,
            value=Decimal("-50.00"),
            description="Original",
            txn_date=date(2025, 1, 15),
        )
    )

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        runner.invoke(transaction, ["edit", "--id", str(tid), "--description", "Changed"])

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched.description == "Changed"
    assert fetched.value == Decimal("-50.00")
    assert fetched.date == date(2025, 1, 15)


def test_edit_not_found(runner, cli_db):
    fake_id = str(uuid.uuid4())

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["edit", "--id", fake_id, "--description", "Ghost"])

    assert result.exit_code == 0
    assert "Transaction not found" in result.stderr


def test_edit_new_category_via_confirm(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(
            transaction, ["edit", "--id", str(tid), "--category", "BrandNewCat"],
            input="y\n",
        )

    assert result.exit_code == 0
    assert "Created category" in result.output or "Updated transaction" in result.output


def test_edit_new_category_decline_aborts(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, description="NoChange"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        runner.invoke(
            transaction, ["edit", "--id", str(tid), "--category", "DeclinedCat"],
            input="n\n",
        )

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched.category_id is None


def test_edit_category_uuid_not_found_errors(runner, cli_db):
    # resolve_category_id returns a UUID without verifying existence;
    # update_transaction then hits an FK IntegrityError, so exit_code != 0.
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["edit", "--id", str(tid), "--category", str(uuid.uuid4())])

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# transaction delete
# ---------------------------------------------------------------------------

def test_delete_with_yes_flag(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["delete", str(tid), "--yes"])

    assert result.exit_code == 0
    assert "Transaction deleted." in result.output


def test_delete_removes_from_db(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        runner.invoke(transaction, ["delete", str(tid), "--yes"])

    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched is None


def test_delete_confirmation_prompt_accept(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["delete", str(tid)], input="y\n")

    assert result.exit_code == 0
    assert "Transaction deleted." in result.output


def test_delete_confirmation_prompt_abort(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["delete", str(tid)], input="n\n")

    assert result.exit_code != 0
    fetched = asyncio.run(_fetch_transaction(cli_db, tid))
    assert fetched is not None


def test_delete_not_found(runner, cli_db):
    fake_id = str(uuid.uuid4())

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(transaction, ["delete", fake_id, "--yes"])

    assert "Transaction not found" in result.stderr


def test_delete_leaves_other_transactions_intact(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid1, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, description="Keep"))
    tid2, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, description="Remove"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        runner.invoke(transaction, ["delete", str(tid2), "--yes"])

    txns = asyncio.run(_fetch_all_transactions(cli_db, pid))
    ids = [t.id for t in txns]
    assert tid1 in ids
    assert tid2 not in ids


def test_delete_by_counter_deletes_correct_transaction(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    # list is ordered date desc; seed with different dates so order is deterministic
    tid1, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, description="First", txn_date=date(2025, 1, 20)))
    tid2, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, description="Second", txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["delete", "1", "--month", "2025-01", "--yes"])

    assert result.exit_code == 0
    assert "Transaction deleted." in result.output
    txns = asyncio.run(_fetch_all_transactions(cli_db, pid))
    ids = [t.id for t in txns]
    assert tid1 not in ids  # #1 = most recent (2025-01-20)
    assert tid2 in ids


def test_delete_by_counter_confirmation_shows_counter_and_id(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 15)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["delete", "1", "--month", "2025-01"], input="n\n")

    assert "#1" in result.output
    assert str(tid) in result.output


def test_delete_by_counter_out_of_range(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 15)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["delete", "99", "--month", "2025-01", "--yes"])

    assert result.exit_code == 0
    assert "not found" in result.stderr


def test_list_shows_counter_column(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, txn_date=date(2025, 1, 15)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(transaction, ["list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "1" in result.output  # counter value


# ---------------------------------------------------------------------------
# Alias: txn (transaction command group alias registered on the top-level cli)
# ---------------------------------------------------------------------------

def test_txn_alias_creates_transaction(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(cli, [
            "txn", "create",
            "--value", "-10.00",
            "--description", "ViaAlias",
            "--account", str(aid),
            "--date", "2025-01-10",
        ])

    assert result.exit_code == 0
    assert "Created transaction" in result.output
    assert "ViaAlias" in result.output


def test_txn_alias_lists_transactions(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="AliasTx", txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(cli, ["txn", "list", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "AliasTx" in result.output


def test_txn_alias_shows_transaction(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    tid, _ = asyncio.run(_seed_transaction(cli_db, pid, aid, description="AliasShow"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(cli, ["txn", "show", str(tid)])

    assert result.exit_code == 0
    assert "AliasShow" in result.output


# ---------------------------------------------------------------------------
# Shortcut: txns (lists transactions directly from top-level cli)
# ---------------------------------------------------------------------------

def test_txns_shortcut_lists_transactions(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="ShortcutTx", txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(cli, ["txns", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "ShortcutTx" in result.output


def test_txns_shortcut_empty(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)):
        result = runner.invoke(cli, ["txns", "--month", "2025-01"])

    assert result.exit_code == 0
    assert "No transactions found." in result.output


def test_txns_shortcut_with_project_option(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "SpecificProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="SpecificTx", txn_date=date(2025, 1, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)):
        result = runner.invoke(cli, ["txns", "--month", "2025-01", "--project", str(pid)])

    assert result.exit_code == 0
    assert "SpecificTx" in result.output


def test_txns_shortcut_uses_default_month(runner, cli_db):
    pid, _ = asyncio.run(_seed_project(cli_db, "MyProject"))
    aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
    asyncio.run(_seed_transaction(cli_db, pid, aid, description="DefaultMonthTx", txn_date=date(2025, 5, 10)))

    with patch("bud.commands.transactions.get_session", new=_make_get_session(cli_db)), \
         patch("bud.commands.utils.get_default_project_id", return_value=str(pid)), \
         patch("bud.commands.utils.get_active_month", return_value="2025-05"):
        result = runner.invoke(cli, ["txns"])

    assert result.exit_code == 0
    assert "DefaultMonthTx" in result.output
