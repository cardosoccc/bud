"""Tests for the recurrences feature.

Covers:
- Creating a forecast with installments creates N forecasts with suffixed names
- Creating a forecast with --recurrent creates forecasts in existing budgets
- Creating a forecast with --recurrence-end bounds the range
- Budget creation triggers forecast creation for applicable recurrences
- Installment numbering is correct
- Open-ended recurrences (no end) propagate to new budgets
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import date
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bud.models  # noqa: F401
from bud.commands.forecasts import forecast
from bud.commands.budgets import budget
from bud.database import Base
from bud.models.forecast import Forecast
from bud.models.recurrence import Recurrence
from bud.schemas.budget import BudgetCreate
from bud.schemas.category import CategoryCreate
from bud.schemas.forecast import ForecastCreate
from bud.schemas.project import ProjectCreate
from bud.schemas.recurrence import RecurrenceCreate
from bud.services import budgets as budget_service
from bud.services import categories as category_service
from bud.services import forecasts as forecast_service
from bud.services import projects as project_service
from bud.services import recurrences as recurrence_service


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


async def _seed_budget(db_url, project_id, month="2025-01"):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        b = await budget_service.create_budget(session, BudgetCreate(name=month, project_id=project_id))
        result = (b.id, b.name)
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


async def _list_forecasts(db_url, budget_id):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        items = await forecast_service.list_forecasts(session, budget_id)
        result = [(f.description, float(f.value), f.installment, f.recurrence_id) for f in items]
    await engine.dispose()
    return result


async def _list_all_budgets(db_url, project_id):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        items = await budget_service.list_budgets(session, project_id)
        result = [(b.id, b.name) for b in items]
    await engine.dispose()
    return result


async def _count_recurrences(db_url):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        res = await session.execute(select(Recurrence))
        result = len(list(res.scalars().all()))
    await engine.dispose()
    return result


def _invoke_forecast(runner, cli_db, args):
    with patch("bud.commands.forecasts.get_session", _make_get_session(cli_db)):
        return runner.invoke(forecast, args)


def _invoke_budget(runner, cli_db, args):
    with patch("bud.commands.budgets.get_session", _make_get_session(cli_db)):
        return runner.invoke(budget, args)


# ---------------------------------------------------------------------------
# Installment-based recurrences
# ---------------------------------------------------------------------------

class TestInstallmentRecurrence:
    def test_creates_correct_number_of_forecasts(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        result = _invoke_forecast(runner, cli_db, [
            "create", "--value", "-120", "--description", "Annual Plan",
            "--budget", "2025-01", "--project", "proj",
            "--installments", "3",
        ])
        assert result.exit_code == 0
        assert "3 installments" in result.output

        # Should have created budgets 2025-01, 2025-02, 2025-03
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        assert len(budgets) == 3
        budget_names = [b[1] for b in budgets]
        assert "2025-01" in budget_names
        assert "2025-02" in budget_names
        assert "2025-03" in budget_names

    def test_installment_suffixes_in_description(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Netflix",
            "--budget", "2025-01", "--project", "proj",
            "--installments", "3",
        ])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            assert len(forecasts) == 1
            desc, val, installment, rec_id = forecasts[0]
            expected_num = int(bname.split("-")[1])  # month number = installment
            assert desc == "Netflix"
            assert val == -100.0
            assert installment == expected_num
            assert rec_id is not None

    def test_installment_creates_one_recurrence(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-60", "--description", "Sub",
            "--budget", "2025-01", "--project", "proj",
            "--installments", "3",
        ])

        count = asyncio.run(_count_recurrences(cli_db))
        assert count == 1

    def test_installment_with_category_and_tags(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-06"))
        cat_id, _ = asyncio.run(_seed_category(cli_db, "Subscriptions"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-50", "--description", "Service",
            "--category", str(cat_id), "--tags", "monthly,auto",
            "--budget", "2025-06", "--project", "proj",
            "--installments", "2",
        ])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        assert len(budgets) == 2
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            assert len(forecasts) == 1


# ---------------------------------------------------------------------------
# Open-ended recurrences (with --recurrent flag)
# ---------------------------------------------------------------------------

class TestOpenEndedRecurrence:
    def test_recurrent_creates_forecasts_in_existing_budgets(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-02"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-03"))

        result = _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Rent",
            "--budget", "2025-01", "--project", "proj",
            "--recurrent",
        ])
        assert result.exit_code == 0
        assert "recurrent" in result.output.lower()

        # Should have forecast in 2025-01, 2025-02, 2025-03
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            assert len(forecasts) == 1
            desc, val, installment, rec_id = forecasts[0]
            assert desc == "Rent"
            assert val == -100.0
            assert installment is None

    def test_recurrent_with_end_limits_range(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-02"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-03"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-04"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Rent",
            "--budget", "2025-01", "--project", "proj",
            "--recurrence-end", "2025-03",
        ])

        # 2025-01, 2025-02, 2025-03 should have forecasts, 2025-04 should not
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            if bname <= "2025-03":
                assert len(forecasts) == 1, f"Expected forecast in {bname}"
            else:
                assert len(forecasts) == 0, f"Should not have forecast in {bname}"

    def test_recurrent_does_not_create_in_prior_budgets(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-02"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-03"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-50", "--description", "Insurance",
            "--budget", "2025-02", "--project", "proj",
            "--recurrent",
        ])

        # 2025-01 should NOT have the forecast, 2025-02 and 2025-03 should
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            if bname >= "2025-02":
                assert len(forecasts) == 1, f"Expected forecast in {bname}"
            else:
                assert len(forecasts) == 0, f"Should not have forecast in {bname}"


# ---------------------------------------------------------------------------
# Budget creation triggers recurrence population
# ---------------------------------------------------------------------------

class TestBudgetCreationPopulatesRecurrences:
    def test_new_budget_gets_open_ended_recurrence_forecast(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        # Create a recurrent forecast
        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-200", "--description", "Salary",
            "--budget", "2025-01", "--project", "proj",
            "--recurrent",
        ])

        # Now create a new budget — should auto-get the forecast
        _invoke_budget(runner, cli_db, ["create", "2025-02", "--project", "proj"])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        feb_bid = [b[0] for b in budgets if b[1] == "2025-02"][0]
        forecasts = asyncio.run(_list_forecasts(cli_db, feb_bid))
        assert len(forecasts) == 1
        assert forecasts[0][0] == "Salary"
        assert forecasts[0][1] == -200.0

    def test_new_budget_respects_recurrence_end(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Temp",
            "--budget", "2025-01", "--project", "proj",
            "--recurrence-end", "2025-02",
        ])

        # 2025-02 should get the forecast
        _invoke_budget(runner, cli_db, ["create", "2025-02", "--project", "proj"])
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        feb_bid = [b[0] for b in budgets if b[1] == "2025-02"][0]
        forecasts = asyncio.run(_list_forecasts(cli_db, feb_bid))
        assert len(forecasts) == 1

        # 2025-03 should NOT get the forecast
        _invoke_budget(runner, cli_db, ["create", "2025-03", "--project", "proj"])
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        mar_bid = [b[0] for b in budgets if b[1] == "2025-03"][0]
        forecasts = asyncio.run(_list_forecasts(cli_db, mar_bid))
        assert len(forecasts) == 0

    def test_new_budget_gets_installment_recurrence_forecast(self, runner, cli_db):
        """If a budget is deleted and recreated, installment forecast should be recreated."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-300", "--description", "Amazon",
            "--budget", "2025-01", "--project", "proj",
            "--installments", "3",
        ])

        # Budget 2025-02 was auto-created by installments. Delete it and recreate.
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        feb_bid = [b[0] for b in budgets if b[1] == "2025-02"][0]

        # Delete 2025-02 budget (cascades its forecasts)
        _invoke_budget(runner, cli_db, ["delete", str(feb_bid), "--yes"])

        # Recreate 2025-02
        _invoke_budget(runner, cli_db, ["create", "2025-02", "--project", "proj"])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        feb_bid = [b[0] for b in budgets if b[1] == "2025-02"][0]
        forecasts = asyncio.run(_list_forecasts(cli_db, feb_bid))
        assert len(forecasts) == 1
        assert forecasts[0][0] == "Amazon"
        assert forecasts[0][2] == 2  # installment number

    def test_budget_before_recurrence_start_gets_no_forecast(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-03"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Late Start",
            "--budget", "2025-03", "--project", "proj",
            "--recurrent",
        ])

        # Creating a budget before the start should not get the forecast
        _invoke_budget(runner, cli_db, ["create", "2025-01", "--project", "proj"])
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        jan_bid = [b[0] for b in budgets if b[1] == "2025-01"][0]
        forecasts = asyncio.run(_list_forecasts(cli_db, jan_bid))
        assert len(forecasts) == 0


# ---------------------------------------------------------------------------
# Recurrence service unit tests
# ---------------------------------------------------------------------------

class TestRecurrenceServiceHelpers:
    def test_month_offset_basic(self):
        assert recurrence_service._month_offset("2025-01", 1) == "2025-02"
        assert recurrence_service._month_offset("2025-01", 11) == "2025-12"
        assert recurrence_service._month_offset("2025-01", 12) == "2026-01"
        assert recurrence_service._month_offset("2025-12", 1) == "2026-01"
        assert recurrence_service._month_offset("2025-06", 0) == "2025-06"

    def test_months_between(self):
        assert recurrence_service._months_between("2025-01", "2025-01") == 0
        assert recurrence_service._months_between("2025-01", "2025-03") == 2
        assert recurrence_service._months_between("2025-01", "2026-01") == 12

    def test_get_installment_number(self):
        class FakeRecurrence:
            start = "2025-01"
        r = FakeRecurrence()
        assert recurrence_service.get_installment_number(r, "2025-01") == 1
        assert recurrence_service.get_installment_number(r, "2025-02") == 2
        assert recurrence_service.get_installment_number(r, "2025-12") == 12


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_installment_crossing_year_boundary(self, runner, cli_db):
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-11"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "YearCross",
            "--budget", "2025-11", "--project", "proj",
            "--installments", "3",
        ])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        budget_names = sorted([b[1] for b in budgets])
        assert budget_names == ["2025-11", "2025-12", "2026-01"]

    def test_no_duplicate_forecasts_on_budget_create(self, runner, cli_db):
        """When installments auto-create a budget, it shouldn't double-create forecasts."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-50", "--description", "NoDup",
            "--budget", "2025-01", "--project", "proj",
            "--installments", "2",
        ])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            assert len(forecasts) == 1, f"Expected exactly 1 forecast in {bname}, got {len(forecasts)}"

    def test_recurrent_without_description(self, runner, cli_db):
        """Recurrent forecast with tags only (no description) should work."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-02"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-75", "--tags", "utilities",
            "--budget", "2025-01", "--project", "proj",
            "--recurrent",
        ])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            assert len(forecasts) == 1

    def test_edit_turns_forecast_into_recurrent(self, runner, cli_db):
        """Editing a forecast with --recurrent creates a recurrence and replicates."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        bid1, _ = asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-02"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-03"))

        # Create a non-recurrent forecast
        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Gym",
            "--budget", "2025-01", "--project", "proj",
        ])

        # Edit it to be recurrent
        result = _invoke_forecast(runner, cli_db, [
            "edit", "1", "--recurrent",
            "--budget", "2025-01", "--project", "proj",
        ])
        assert result.exit_code == 0
        assert "now recurrent" in result.output
        assert "2 forecasts added" in result.output

        # All 3 budgets should have the forecast
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            assert len(forecasts) == 1, f"Expected forecast in {bname}"
            assert forecasts[0][0] == "Gym"
            assert forecasts[0][1] == -100.0

    def test_edit_recurrent_with_end(self, runner, cli_db):
        """Editing with --recurrence-end limits the range."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-02"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-03"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-04"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-50", "--description", "Temp Sub",
            "--budget", "2025-01", "--project", "proj",
        ])

        result = _invoke_forecast(runner, cli_db, [
            "edit", "1", "--recurrence-end", "2025-03",
            "--budget", "2025-01", "--project", "proj",
        ])
        assert result.exit_code == 0
        assert "until 2025-03" in result.output

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            if bname <= "2025-03":
                assert len(forecasts) == 1, f"Expected forecast in {bname}"
            else:
                assert len(forecasts) == 0, f"Should not have forecast in {bname}"

    def test_edit_already_recurrent_fails(self, runner, cli_db):
        """Cannot turn an already-recurrent forecast into recurrent again."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Rent",
            "--budget", "2025-01", "--project", "proj",
            "--recurrent",
        ])

        result = _invoke_forecast(runner, cli_db, [
            "edit", "1", "--recurrent",
            "--budget", "2025-01", "--project", "proj",
        ])
        assert "already recurrent" in result.output

    def test_edit_recurrent_new_budget_gets_forecast(self, runner, cli_db):
        """After editing to recurrent, new budgets should pick up the recurrence."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-200", "--description", "Insurance",
            "--budget", "2025-01", "--project", "proj",
        ])

        _invoke_forecast(runner, cli_db, [
            "edit", "1", "--recurrent",
            "--budget", "2025-01", "--project", "proj",
        ])

        # Create a new budget — should auto-get the forecast
        _invoke_budget(runner, cli_db, ["create", "2025-02", "--project", "proj"])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        feb_bid = [b[0] for b in budgets if b[1] == "2025-02"][0]
        forecasts = asyncio.run(_list_forecasts(cli_db, feb_bid))
        assert len(forecasts) == 1
        assert forecasts[0][0] == "Insurance"

    def test_edit_recurrent_also_applies_field_changes(self, runner, cli_db):
        """Editing with --recurrent and --value should update the forecast and make it recurrent."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))
        asyncio.run(_seed_budget(cli_db, pid, "2025-02"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Gym",
            "--budget", "2025-01", "--project", "proj",
        ])

        _invoke_forecast(runner, cli_db, [
            "edit", "1", "--recurrent", "--value", "-150",
            "--budget", "2025-01", "--project", "proj",
        ])

        # Original forecast should have updated value
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        jan_bid = [b[0] for b in budgets if b[1] == "2025-01"][0]
        jan_forecasts = asyncio.run(_list_forecasts(cli_db, jan_bid))
        assert jan_forecasts[0][1] == -150.0

        # Replicated forecast should use the updated value
        feb_bid = [b[0] for b in budgets if b[1] == "2025-02"][0]
        feb_forecasts = asyncio.run(_list_forecasts(cli_db, feb_bid))
        assert len(feb_forecasts) == 1
        assert feb_forecasts[0][1] == -150.0

    def test_current_installment_creates_remaining_forecasts(self, runner, cli_db):
        """--current-installment 5 --installments 10 creates only installments 5-10."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-06"))

        result = _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Washer",
            "--budget", "2025-06", "--project", "proj",
            "--installments", "10", "--current-installment", "5",
        ])
        assert result.exit_code == 0
        assert "6 installments" in result.output
        assert "5/10 to 10/10" in result.output

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        budget_names = sorted([b[1] for b in budgets])
        # Should create 2025-06 through 2025-11 (6 months for installments 5-10)
        assert len(budget_names) == 6
        assert budget_names[0] == "2025-06"
        assert budget_names[-1] == "2025-11"

        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            assert len(forecasts) == 1
            desc, val, installment, rec_id = forecasts[0]
            assert desc == "Washer"
            assert val == -100.0
            assert rec_id is not None
            # installment numbers should be 5, 6, 7, 8, 9, 10
            expected_inst = 5 + (sorted(budget_names).index(bname))
            assert installment == expected_inst

    def test_current_installment_budget_creation_populates_correctly(self, runner, cli_db):
        """New budget after --current-installment recurrence gets correct installment number."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-06"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-50", "--description", "Phone",
            "--budget", "2025-06", "--project", "proj",
            "--installments", "8", "--current-installment", "3",
        ])

        # Installments 3-8 created (2025-06 to 2025-11). Delete 2025-08 and recreate.
        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        aug_bid = [b[0] for b in budgets if b[1] == "2025-08"][0]
        _invoke_budget(runner, cli_db, ["delete", str(aug_bid), "--yes"])
        _invoke_budget(runner, cli_db, ["create", "2025-08", "--project", "proj"])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        aug_bid = [b[0] for b in budgets if b[1] == "2025-08"][0]
        forecasts = asyncio.run(_list_forecasts(cli_db, aug_bid))
        assert len(forecasts) == 1
        # 2025-08 is 2 months after 2025-06 (installment 3), so installment = 5
        assert forecasts[0][2] == 5

    def test_current_installment_requires_installments(self, runner, cli_db):
        """--current-installment without --installments should fail."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        result = _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Bad",
            "--budget", "2025-01", "--project", "proj",
            "--current-installment", "3",
        ])
        assert result.exit_code == 0
        assert "requires --installments" in result.output

    def test_current_installment_out_of_range(self, runner, cli_db):
        """--current-installment > --installments should fail."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        result = _invoke_forecast(runner, cli_db, [
            "create", "--value", "-100", "--description", "Bad",
            "--budget", "2025-01", "--project", "proj",
            "--installments", "5", "--current-installment", "7",
        ])
        assert result.exit_code == 0
        assert "must be between 1 and 5" in result.output

    def test_installments_without_description_no_suffix(self, runner, cli_db):
        """Installment forecast without description should have None description."""
        pid, _ = asyncio.run(_seed_project(cli_db, "proj", is_default=True))
        asyncio.run(_seed_budget(cli_db, pid, "2025-01"))

        _invoke_forecast(runner, cli_db, [
            "create", "--value", "-50", "--tags", "sub",
            "--budget", "2025-01", "--project", "proj",
            "--installments", "2",
        ])

        budgets = asyncio.run(_list_all_budgets(cli_db, pid))
        for bid, bname in budgets:
            forecasts = asyncio.run(_list_forecasts(cli_db, bid))
            assert len(forecasts) == 1
            assert forecasts[0][0] is None  # no description
