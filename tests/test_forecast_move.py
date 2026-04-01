"""Tests for moving forecasts between budgets.

Covers:
- Moving a non-recurrent forecast to another budget
- Moving a simple recurrent forecast detaches and renames with source month
- Moving an installment forecast replaces auto-populated in target
- Moving to the same budget returns None (error)
- Target budget auto-created when missing (via CLI)
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
from bud.database import Base
from bud.models.forecast import Forecast
from bud.models.recurrence import Recurrence
from bud.schemas.budget import BudgetCreate
from bud.schemas.forecast import ForecastCreate
from bud.schemas.project import ProjectCreate
from bud.schemas.recurrence import RecurrenceCreate
from bud.services import budgets as budget_service
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


async def _seed_project(db_url, name="test", *, is_default=True):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        p = await project_service.create_project(session, ProjectCreate(name=name))
        if is_default:
            await project_service.set_default_project(session, p.id)
        result = p.id
    await engine.dispose()
    return result


async def _seed_budget(db_url, project_id, month="2026-04"):
    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        b = await budget_service.create_budget(session, BudgetCreate(name=month, project_id=project_id))
        result = b.id
    await engine.dispose()
    return result


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------

class TestMoveForecastService:
    """Tests for forecast_service.move_forecast()."""

    async def test_move_non_recurrent(self, db_session):
        p = await project_service.create_project(db_session, ProjectCreate(name="test"))
        b1 = await budget_service.create_budget(db_session, BudgetCreate(name="2026-04", project_id=p.id))
        b2 = await budget_service.create_budget(db_session, BudgetCreate(name="2026-05", project_id=p.id))
        f = await forecast_service.create_forecast(db_session, ForecastCreate(
            description="spotify", value=Decimal("-30"), budget_id=b1.id,
        ))

        result = await forecast_service.move_forecast(db_session, f.id, b2.id, b1.name)

        assert result is not None
        assert result.budget_id == b2.id
        assert result.description == "spotify"
        assert result.recurrence_id is None

    async def test_move_simple_recurrent_detaches_and_renames(self, db_session):
        p = await project_service.create_project(db_session, ProjectCreate(name="test"))
        b1 = await budget_service.create_budget(db_session, BudgetCreate(name="2026-04", project_id=p.id))
        b2 = await budget_service.create_budget(db_session, BudgetCreate(name="2026-05", project_id=p.id))

        rec = await recurrence_service.create_recurrence(db_session, RecurrenceCreate(
            start="2026-04", base_description="spotify", value=Decimal("-30"),
            project_id=p.id, tags=[],
        ))
        f = await forecast_service.create_forecast(db_session, ForecastCreate(
            description="spotify", value=Decimal("-30"), budget_id=b1.id,
            recurrence_id=rec.id,
        ))

        result = await forecast_service.move_forecast(db_session, f.id, b2.id, "2026-04")

        assert result is not None
        assert result.budget_id == b2.id
        assert result.description == "spotify (2026-04)"
        assert result.recurrence_id is None

    async def test_move_installment_detaches_and_renames(self, db_session):
        p = await project_service.create_project(db_session, ProjectCreate(name="test"))
        b1 = await budget_service.create_budget(db_session, BudgetCreate(name="2026-04", project_id=p.id))
        b2 = await budget_service.create_budget(db_session, BudgetCreate(name="2026-05", project_id=p.id))

        rec = await recurrence_service.create_recurrence(db_session, RecurrenceCreate(
            start="2026-04", installments=3, base_description="laptop",
            value=Decimal("-500"), project_id=p.id, tags=[],
        ))
        # Forecast in source budget (installment 1)
        f1 = await forecast_service.create_forecast(db_session, ForecastCreate(
            description="laptop", value=Decimal("-500"), budget_id=b1.id,
            recurrence_id=rec.id, installment=1,
        ))
        # Auto-populated forecast in target budget (installment 2)
        f2 = await forecast_service.create_forecast(db_session, ForecastCreate(
            description="laptop", value=Decimal("-500"), budget_id=b2.id,
            recurrence_id=rec.id, installment=2,
        ))

        result = await forecast_service.move_forecast(db_session, f1.id, b2.id, "2026-04")

        assert result is not None
        assert result.budget_id == b2.id
        assert result.description == "laptop (1/3) (2026-04)"
        assert result.recurrence_id is None
        assert result.installment is None

        # The auto-populated forecast in target should remain untouched
        remaining = await forecast_service.list_forecasts(db_session, b2.id)
        assert len(remaining) == 2
        descs = {r.description for r in remaining}
        assert "laptop (1/3) (2026-04)" in descs
        assert "laptop" in descs

    async def test_move_to_same_budget_returns_none(self, db_session):
        p = await project_service.create_project(db_session, ProjectCreate(name="test"))
        b = await budget_service.create_budget(db_session, BudgetCreate(name="2026-04", project_id=p.id))
        f = await forecast_service.create_forecast(db_session, ForecastCreate(
            description="rent", value=Decimal("-1000"), budget_id=b.id,
        ))

        result = await forecast_service.move_forecast(db_session, f.id, b.id, "2026-04")
        assert result is None


# ---------------------------------------------------------------------------
# CLI-level tests
# ---------------------------------------------------------------------------

class TestMoveForecastCLI:
    """Tests for `bud forecast edit --budget`."""

    def test_move_non_recurrent_via_cli(self, runner, cli_db):
        pid = asyncio.run(_seed_project(cli_db, "proj"))
        bid_src = asyncio.run(_seed_budget(cli_db, pid, "2026-04"))
        asyncio.run(_seed_budget(cli_db, pid, "2026-05"))

        get_session = _make_get_session(cli_db)

        async def _create():
            async with get_session() as db:
                await forecast_service.create_forecast(db, ForecastCreate(
                    description="spotify", value=Decimal("-30"), budget_id=bid_src,
                ))
        asyncio.run(_create())

        with patch("bud.commands.forecasts.get_session", get_session):
            result = runner.invoke(forecast, [
                "edit", "1", "2026-04", "--project", "proj", "--budget", "2026-05",
            ])

        assert result.exit_code == 0, result.output
        assert "moved forecast to 2026-05" in result.output

    def test_move_auto_creates_target_budget(self, runner, cli_db):
        pid = asyncio.run(_seed_project(cli_db, "proj"))
        bid_src = asyncio.run(_seed_budget(cli_db, pid, "2026-04"))

        get_session = _make_get_session(cli_db)

        async def _create():
            async with get_session() as db:
                await forecast_service.create_forecast(db, ForecastCreate(
                    description="gym", value=Decimal("-50"), budget_id=bid_src,
                ))
        asyncio.run(_create())

        with patch("bud.commands.forecasts.get_session", get_session):
            result = runner.invoke(forecast, [
                "edit", "1", "2026-04", "--project", "proj", "--budget", "2026-06",
            ])

        assert result.exit_code == 0, result.output
        assert "auto-created budget: 2026-06" in result.output
        assert "moved forecast to 2026-06" in result.output
