"""Database management commands."""
import click

from bud.commands.config_store import DB_PATH, set_config_value
from bud.commands.db import get_engine, run_async
from bud.commands.sync import push, pull
from bud.schemas.project import ProjectCreate
from bud.services.projects import create_project, get_project_by_name, set_default_project


@click.group("db")
def db():
    """Database management commands."""
    pass


db.add_command(push)
db.add_command(pull)


@db.command("init")
def init():
    """Create the database and all tables."""
    async def _run():
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import sessionmaker

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        engine = get_engine()
        async with engine.begin() as conn:
            from bud.database import Base
            import bud.models  # noqa: F401
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            existing = await get_project_by_name(session, "default")
            if existing:
                pid = str(existing.id)
            else:
                project = await create_project(session, ProjectCreate(name="default"))
                await set_default_project(session, project.id)
                pid = str(project.id)

        await engine.dispose()
        return pid

    project_id = run_async(_run())
    set_config_value("default_project_id", project_id)
    click.echo(f"Database initialized at {DB_PATH}")


@db.command("migrate")
def migrate():
    """Run pending database migrations."""
    async def _run():
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import sessionmaker

        engine = get_engine()
        async with engine.begin() as conn:
            from bud.database import Base
            import bud.models  # noqa: F401
            # Create any new tables
            await conn.run_sync(Base.metadata.create_all)
            # Add new columns to existing tables
            await conn.run_sync(_migrate_forecasts_schema)

        # Data migration: convert old is_recurrent forecasts to recurrence records
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            migrated = await _migrate_recurrent_forecasts_data(session)

        await engine.dispose()
        return migrated

    migrated = run_async(_run())
    if migrated:
        click.echo(f"Migrated {migrated} recurrent forecasts to recurrence records.")
    click.echo("Database migrated successfully.")


def _migrate_forecasts_schema(conn):
    """Add recurrence columns to forecasts table if missing (SQLite migration)."""
    from sqlalchemy import text

    cursor = conn.execute(text("PRAGMA table_info(forecasts)"))
    columns = {}
    for row in cursor.fetchall():
        # row: (cid, name, type, notnull, dflt_value, pk)
        columns[row[1]] = {"notnull": row[3], "default": row[4]}

    if "recurrence_id" not in columns:
        conn.execute(text("ALTER TABLE forecasts ADD COLUMN recurrence_id CHAR(32) REFERENCES recurrences(id) ON DELETE SET NULL"))

    if "installment" not in columns:
        conn.execute(text("ALTER TABLE forecasts ADD COLUMN installment INTEGER"))

    # Old is_recurrent column may have NOT NULL without a default, which breaks
    # new INSERTs since the model no longer sets it. Add a default value.
    if "is_recurrent" in columns and columns["is_recurrent"]["default"] is None:
        # SQLite doesn't support ALTER COLUMN, so we read the current schema,
        # patch it, and recreate the table.
        schema_row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='forecasts'")
        ).fetchone()
        old_sql = schema_row[0]

        # Replace "is_recurrent BOOLEAN" (with possible NOT NULL) to add DEFAULT 0
        import re
        new_sql = re.sub(
            r"is_recurrent\s+BOOLEAN(?:\s+NOT\s+NULL)?",
            "is_recurrent BOOLEAN DEFAULT 0",
            old_sql,
            flags=re.IGNORECASE,
        )
        new_sql = new_sql.replace("CREATE TABLE forecasts", "CREATE TABLE forecasts_new", 1)

        conn.execute(text(new_sql))

        # Copy all data
        col_names = ", ".join(columns.keys())
        conn.execute(text(f"INSERT INTO forecasts_new ({col_names}) SELECT {col_names} FROM forecasts"))
        conn.execute(text("DROP TABLE forecasts"))
        conn.execute(text("ALTER TABLE forecasts_new RENAME TO forecasts"))


async def _migrate_recurrent_forecasts_data(db):
    """Convert old is_recurrent=1 forecasts (without a recurrence_id) into
    proper recurrence records.

    For each such forecast, creates a recurrence with start = budget month
    and end = recurrent_end (if set), then links the forecast to it.
    Forecasts sharing the same description+value+budget are grouped so that
    each unique recurrent forecast gets one recurrence.
    """
    from sqlalchemy import text
    from bud.models.recurrence import Recurrence
    from bud.models.forecast import Forecast
    from bud.models.budget import Budget
    import uuid as uuid_mod

    # Check if the old is_recurrent column still exists
    result = await db.execute(text("PRAGMA table_info(forecasts)"))
    columns = {row[1] for row in result.fetchall()}
    if "is_recurrent" not in columns:
        return 0

    # Find old recurrent forecasts that haven't been migrated yet
    rows = await db.execute(
        text("SELECT id, budget_id, recurrent_start, recurrent_end FROM forecasts WHERE is_recurrent = 1 AND recurrence_id IS NULL")
    )
    old_recurrents = rows.fetchall()
    if not old_recurrents:
        return 0

    from sqlalchemy import select

    migrated = 0
    for row in old_recurrents:
        forecast_id_str, budget_id_str, recurrent_start, recurrent_end = row
        forecast_id = uuid_mod.UUID(forecast_id_str)
        budget_id = uuid_mod.UUID(budget_id_str)

        # Get the budget to determine the start month
        budget_result = await db.execute(select(Budget).where(Budget.id == budget_id))
        budget_obj = budget_result.scalar_one_or_none()
        if not budget_obj:
            continue

        # Convert recurrent_end date to YYYY-MM string if present
        end_month = None
        if recurrent_end:
            from datetime import date
            if isinstance(recurrent_end, str):
                end_month = recurrent_end[:7]
            elif isinstance(recurrent_end, date):
                end_month = recurrent_end.strftime("%Y-%m")

        # Get the forecast to read its description for base_description
        forecast_result = await db.execute(select(Forecast).where(Forecast.id == forecast_id))
        forecast_obj = forecast_result.scalar_one_or_none()
        if not forecast_obj:
            continue

        # Create a recurrence record
        rec = Recurrence(
            id=uuid_mod.uuid4(),
            start=budget_obj.name,
            end=end_month,
            base_description=forecast_obj.description,
            original_forecast_id=forecast_id,
            project_id=budget_obj.project_id,
        )
        db.add(rec)
        await db.flush()

        # Link the forecast to the recurrence
        forecast_obj.recurrence_id = rec.id
        migrated += 1

    await db.commit()
    return migrated


@db.command("destroy")
@click.confirmation_option(prompt="This will permanently delete the database. Continue?")
def destroy():
    """Delete the database."""
    if DB_PATH.exists():
        DB_PATH.unlink()
        click.echo(f"Database deleted: {DB_PATH}")
    else:
        click.echo("Database does not exist.")


@db.command("reset")
@click.confirmation_option(prompt="This will delete and recreate the database. Continue?")
def reset():
    """Delete and recreate the database."""
    if DB_PATH.exists():
        DB_PATH.unlink()
        click.echo(f"Database deleted: {DB_PATH}")

    async def _run():
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import sessionmaker

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        engine = get_engine()
        async with engine.begin() as conn:
            from bud.database import Base
            import bud.models  # noqa: F401
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            project = await create_project(session, ProjectCreate(name="default"))
            await set_default_project(session, project.id)
            pid = str(project.id)

        await engine.dispose()
        return pid

    project_id = run_async(_run())
    set_config_value("default_project_id", project_id)
    click.echo(f"Database initialized at {DB_PATH}")
    click.echo("Database reset complete.")
