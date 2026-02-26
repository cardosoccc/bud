"""Tests for the 'forecast' CLI command group.

Covers:
- Creating forecasts with optional description
- Validation: at least one of description/category/tags required
- Auto-creating unknown categories on confirmation
- Listing forecasts shows category and tags columns
- Deleting by counter without --budget defaults to current month
- Report transaction matching with AND logic across description, category, tags
"""

import asyncio
import uuid
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
from bud.commands.forecasts import forecast
from bud.database import Base
from bud.models.account import AccountType
from bud.schemas.account import AccountCreate
from bud.schemas.budget import BudgetCreate
from bud.schemas.category import CategoryCreate
from bud.schemas.forecast import ForecastCreate
from bud.schemas.project import ProjectCreate
from bud.schemas.transaction import TransactionCreate
from bud.services import accounts as account_service
from bud.services import budgets as budget_service
from bud.services import categories as category_service
from bud.services import forecasts as forecast_service
from bud.services import projects as project_service
from bud.services import reports as report_service


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


async def _seed_project(db_url, name, *, is_default=False):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        p = await project_service.create_project(session, ProjectCreate(name=name))
        if is_default:
            await project_service.set_default_project(session, p.id)
        result = (p.id, p.name)
    await engine.dispose()
    return result


async def _seed_account(db_url, project_id, name):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        a = await account_service.create_account(
            session,
            AccountCreate(name=name, type=AccountType.debit, project_id=project_id, initial_balance=0),
        )
        result = (a.id, a.name)
    await engine.dispose()
    return result


async def _seed_category(db_url, name):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        c = await category_service.create_category(session, CategoryCreate(name=name))
        result = (c.id, c.name)
    await engine.dispose()
    return result


async def _seed_budget(db_url, project_id, month="2025-01"):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        b = await budget_service.create_budget(session, BudgetCreate(name=month, project_id=project_id))
        result = (b.id, b.name)
    await engine.dispose()
    return result


async def _seed_forecast(db_url, budget_id, *, value=-100, description=None, category_id=None, tags=None):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        f = await forecast_service.create_forecast(
            session,
            ForecastCreate(
                description=description,
                value=Decimal(str(value)),
                budget_id=budget_id,
                category_id=category_id,
                tags=tags or [],
            ),
        )
        result = f.id
    await engine.dispose()
    return result


async def _seed_transaction(db_url, project_id, account_id, *, value=-50, description="Test", txn_date=date(2025, 1, 15), category_id=None, tags=None):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        t = await account_service.create_account  # placeholder
        t = await asyncio.coroutine(lambda: None)()  # not needed
    await engine.dispose()


async def _create_transaction(db_url, project_id, account_id, *, value=-50, description="Test", txn_date=date(2025, 1, 15), category_id=None, tags=None):
    from bud.services import transactions as txn_service
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        t = await txn_service.create_transaction(
            session,
            TransactionCreate(
                value=Decimal(str(value)),
                description=description,
                date=txn_date,
                account_id=account_id,
                project_id=project_id,
                category_id=category_id,
                tags=tags or [],
            ),
        )
        result = t.id
    await engine.dispose()
    return result


async def _generate_report(db_url, budget_id):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        r = await report_service.generate_report(session, budget_id)
    await engine.dispose()
    return r


def _invoke(runner, cli_db, args):
    with patch("bud.commands.forecasts.get_session", _make_get_session(cli_db)):
        return runner.invoke(forecast, args)


# ---------------------------------------------------------------------------
# Create: description optional
# ---------------------------------------------------------------------------

class TestCreateDescriptionOptional:
    def test_create_with_description_only(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        result = _invoke(runner, cli_db, [
            "create", "--value", "-100", "--description", "Rent",
            "--budget", "2025-01", "--project", "proj",
        ])
        assert result.exit_code == 0
        assert "Created forecast" in result.output

    def test_create_with_category_only(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Food"))
        result = _invoke(runner, cli_db, [
            "create", "--value", "-200", "--category", str(cat_id),
            "--budget", "2025-01", "--project", "proj",
        ])
        assert result.exit_code == 0
        assert "Created forecast" in result.output

    def test_create_with_tags_only(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        result = _invoke(runner, cli_db, [
            "create", "--value", "-50", "--tags", "groceries,weekly",
            "--budget", "2025-01", "--project", "proj",
        ])
        assert result.exit_code == 0
        assert "Created forecast" in result.output

    def test_create_no_criteria_fails(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        result = _invoke(runner, cli_db, [
            "create", "--value", "-100",
            "--budget", "2025-01", "--project", "proj",
        ])
        assert result.exit_code == 0  # click doesn't set exit_code=1 for echo
        assert "at least one of" in result.output

    def test_create_with_all_criteria(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Transport"))
        result = _invoke(runner, cli_db, [
            "create", "--value", "-80", "--description", "Uber",
            "--category", str(cat_id), "--tags", "ride",
            "--budget", "2025-01", "--project", "proj",
        ])
        assert result.exit_code == 0
        assert "Created forecast" in result.output


# ---------------------------------------------------------------------------
# Create: auto-create unknown category
# ---------------------------------------------------------------------------

class TestCreateAutoCategory:
    def test_create_auto_creates_category_on_confirm(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        result = _invoke(runner, cli_db, [
            "create", "--value", "-100", "--category", "NewCat",
            "--budget", "2025-01", "--project", "proj",
        ])
        # click.confirm will read 'y' from default input (empty → abort)
        # Use runner with input='y\n'
        with patch("bud.commands.forecasts.get_session", _make_get_session(cli_db)):
            result = runner.invoke(forecast, [
                "create", "--value", "-100", "--category", "NewCat",
                "--budget", "2025-01", "--project", "proj",
            ], input="y\n")
        assert result.exit_code == 0
        assert "Created category: NewCat" in result.output
        assert "Created forecast" in result.output

    def test_create_aborts_when_category_declined(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        with patch("bud.commands.forecasts.get_session", _make_get_session(cli_db)):
            result = runner.invoke(forecast, [
                "create", "--value", "-100", "--category", "NewCat",
                "--budget", "2025-01", "--project", "proj",
            ], input="n\n")
        assert "Created forecast" not in result.output


# ---------------------------------------------------------------------------
# List: shows category and tags
# ---------------------------------------------------------------------------

class TestListShowsCategoryAndTags:
    def test_list_shows_category_column(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Food"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-200, description="Groceries", category_id=cat_id))
        result = _invoke(runner, cli_db, ["list", "--budget", "2025-01", "--project", "proj"])
        assert result.exit_code == 0
        assert "Category" in result.output
        assert "Food" in result.output

    def test_list_shows_tags_column(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-50, description="Snacks", tags=["weekly", "food"]))
        result = _invoke(runner, cli_db, ["list", "--budget", "2025-01", "--project", "proj"])
        assert result.exit_code == 0
        assert "Tags" in result.output
        assert "weekly" in result.output
        assert "food" in result.output

    def test_list_no_description_shows_empty(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-100, tags=["rent"]))
        result = _invoke(runner, cli_db, ["list", "--budget", "2025-01", "--project", "proj"])
        assert result.exit_code == 0
        assert "rent" in result.output


# ---------------------------------------------------------------------------
# Delete by counter without --budget defaults to current month
# ---------------------------------------------------------------------------

class TestDeleteDefaultsToCurrentMonth:
    def test_delete_by_counter_uses_current_month(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        today = date.today()
        month = today.strftime("%Y-%m")
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, month))
        asyncio.run(_seed_forecast(cli_db, bid, value=-100, description="ToDelete"))

        with patch("bud.commands.forecasts.get_session", _make_get_session(cli_db)):
            result = runner.invoke(forecast, [
                "delete", "1", "--project", "proj", "--yes",
            ])
        assert result.exit_code == 0
        assert "Forecast deleted" in result.output


# ---------------------------------------------------------------------------
# Report: transaction matching with AND logic
# ---------------------------------------------------------------------------

class TestReportTransactionMatching:
    def test_match_by_category_only(self, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Food"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-200, category_id=cat_id))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-80, description="Supermarket", category_id=cat_id, txn_date=date(2025, 1, 10)))
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-30, description="Other", txn_date=date(2025, 1, 12)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert len(r.forecasts) == 1
        assert r.forecasts[0].actual_value == Decimal("-80")

    def test_match_by_description_only(self, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-100, description="Netflix"))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-15, description="Netflix subscription", txn_date=date(2025, 1, 5)))
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-50, description="Spotify", txn_date=date(2025, 1, 6)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert len(r.forecasts) == 1
        # "Netflix" is a substring of "Netflix subscription" (case-insensitive)
        assert r.forecasts[0].actual_value == Decimal("-15")

    def test_match_by_tags_only(self, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-150, tags=["groceries"]))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-40, description="Market", tags=["groceries", "weekly"], txn_date=date(2025, 1, 8)))
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-20, description="Gas", tags=["transport"], txn_date=date(2025, 1, 9)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert len(r.forecasts) == 1
        assert r.forecasts[0].actual_value == Decimal("-40")

    def test_match_by_category_and_description(self, cli_db):
        """Both category AND description must match."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Subscriptions"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-50, description="Netflix", category_id=cat_id))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        # Matches both
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-15, description="Netflix monthly", category_id=cat_id, txn_date=date(2025, 1, 5)))
        # Matches category but not description
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-10, description="Spotify", category_id=cat_id, txn_date=date(2025, 1, 6)))
        # Matches description but not category
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-15, description="Netflix extra", txn_date=date(2025, 1, 7)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert len(r.forecasts) == 1
        assert r.forecasts[0].actual_value == Decimal("-15")

    def test_match_by_category_and_tags(self, cli_db):
        """Both category AND tags must match."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Food"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-200, category_id=cat_id, tags=["weekly"]))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        # Matches both
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-60, description="Market", category_id=cat_id, tags=["weekly"], txn_date=date(2025, 1, 10)))
        # Matches category but not tags
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-30, description="Restaurant", category_id=cat_id, tags=["dining"], txn_date=date(2025, 1, 11)))
        # Matches tags but not category
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-20, description="Other", tags=["weekly"], txn_date=date(2025, 1, 12)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert len(r.forecasts) == 1
        assert r.forecasts[0].actual_value == Decimal("-60")

    def test_match_by_all_three_criteria(self, cli_db):
        """Description AND category AND tags must all match."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Food"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-300, description="Market", category_id=cat_id, tags=["weekly"]))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        # Matches all three
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-70, description="Market run", category_id=cat_id, tags=["weekly", "essentials"], txn_date=date(2025, 1, 10)))
        # Missing category
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-20, description="Market snack", tags=["weekly"], txn_date=date(2025, 1, 11)))
        # Missing tags
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-25, description="Market lunch", category_id=cat_id, txn_date=date(2025, 1, 12)))
        # Missing description
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-15, description="Other", category_id=cat_id, tags=["weekly"], txn_date=date(2025, 1, 13)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert len(r.forecasts) == 1
        assert r.forecasts[0].actual_value == Decimal("-70")

    def test_no_criteria_forecast_has_zero_actual(self, cli_db):
        """A forecast with no criteria should report zero actual."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        # Directly seed via service (bypassing CLI validation)
        asyncio.run(_seed_forecast(cli_db, bid, value=-100))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-50, description="Anything", txn_date=date(2025, 1, 10)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert len(r.forecasts) == 1
        assert r.forecasts[0].actual_value == Decimal("0")

    def test_description_match_is_case_insensitive(self, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-100, description="netflix"))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-15, description="NETFLIX Premium", txn_date=date(2025, 1, 5)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert r.forecasts[0].actual_value == Decimal("-15")

    def test_tags_must_all_be_present(self, cli_db):
        """Forecast with multiple tags: transaction must have ALL of them."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-100, tags=["groceries", "weekly"]))
        aid, _ = asyncio.run(_seed_account(cli_db, pid, "Checking"))
        # Has both tags → matches
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-40, description="Shop", tags=["groceries", "weekly", "extra"], txn_date=date(2025, 1, 10)))
        # Has only one tag → no match
        asyncio.run(_create_transaction(cli_db, pid, aid, value=-20, description="Quick buy", tags=["groceries"], txn_date=date(2025, 1, 11)))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert r.forecasts[0].actual_value == Decimal("-40")

    def test_report_includes_category_name_and_tags(self, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Transport"))
        asyncio.run(_seed_forecast(cli_db, bid, value=-200, category_id=cat_id, tags=["commute"]))

        r = asyncio.run(_generate_report(cli_db, bid))
        assert r.forecasts[0].category_name == "Transport"
        assert r.forecasts[0].tags == ["commute"]
