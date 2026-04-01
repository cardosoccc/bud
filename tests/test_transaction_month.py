"""Tests for moving transactions between months via --move-month.

Covers:
- Moving a transaction to a different month changes the date
- Day is clamped to last valid day of shorter month
"""

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import date
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bud.models  # noqa: F401
from bud.commands.transactions import transaction
from bud.database import Base
from bud.models.account import AccountType
from bud.schemas.account import AccountCreate
from bud.schemas.budget import BudgetCreate
from bud.schemas.project import ProjectCreate
from bud.schemas.transaction import TransactionCreate
from bud.services import accounts as account_service
from bud.services import budgets as budget_service
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


async def _seed(db_url):
    """Seed a project, account, budget, and transaction. Returns (project_id, account_id, budget_id, transaction_id)."""
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        p = await project_service.create_project(session, ProjectCreate(name="proj"))
        a = await account_service.create_account(session, AccountCreate(
            name="checking", type=AccountType.debit, project_id=p.id, initial_balance=Decimal("0"),
        ))
        b = await budget_service.create_budget(session, BudgetCreate(name="2026-03", project_id=p.id))
        t = await transaction_service.create_transaction(session, TransactionCreate(
            value=Decimal("-100"), description="rent", date=date(2026, 3, 31),
            account_id=a.id, project_id=p.id,
        ))
        result = (p.id, a.id, b.id, t.id)
    await engine.dispose()
    return result


# ---------------------------------------------------------------------------
# CLI-level tests
# ---------------------------------------------------------------------------

def test_move_transaction_to_different_month(runner, cli_db):
    pid, aid, bid, tid = asyncio.run(_seed(cli_db))
    get_session = _make_get_session(cli_db)

    with patch("bud.commands.transactions.get_session", get_session):
        result = runner.invoke(transaction, [
            "edit", "1", "2026-03", "--project", "proj", "--move-month", "2026-04",
        ])

    assert result.exit_code == 0, result.output
    assert "updated transaction" in result.output

    # Verify the date was changed
    async def _check():
        async with get_session() as db:
            t = await transaction_service.get_transaction(db, tid)
            return t.date

    new_date = asyncio.run(_check())
    # March 31 -> April has only 30 days, should clamp to 30
    assert new_date == date(2026, 4, 30)


def test_move_transaction_day_clamped_to_feb(runner, cli_db):
    """March 31 -> February should clamp to Feb 28 (non-leap year)."""
    pid, aid, bid, tid = asyncio.run(_seed(cli_db))
    get_session = _make_get_session(cli_db)

    with patch("bud.commands.transactions.get_session", get_session):
        result = runner.invoke(transaction, [
            "edit", "1", "2026-03", "--project", "proj", "--move-month", "2026-02",
        ])

    assert result.exit_code == 0, result.output

    async def _check():
        async with get_session() as db:
            t = await transaction_service.get_transaction(db, tid)
            return t.date

    new_date = asyncio.run(_check())
    assert new_date == date(2026, 2, 28)
