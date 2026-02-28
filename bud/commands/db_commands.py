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
            await conn.run_sync(_migrate_recurrences_schema)

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


def _migrate_recurrences_schema(conn):
    """Migrate recurrences table: add value/category_id/tags, populate from original_forecast, drop original_forecast_id."""
    from sqlalchemy import text

    cursor = conn.execute(text("PRAGMA table_info(recurrences)"))
    columns = {row[1] for row in cursor.fetchall()}

    if not columns:
        return

    if "value" not in columns:
        conn.execute(text("ALTER TABLE recurrences ADD COLUMN value NUMERIC(15, 2) DEFAULT 0 NOT NULL"))

    if "category_id" not in columns:
        conn.execute(text("ALTER TABLE recurrences ADD COLUMN category_id CHAR(32) REFERENCES categories(id) ON DELETE SET NULL"))

    if "tags" not in columns:
        conn.execute(text("ALTER TABLE recurrences ADD COLUMN tags JSON DEFAULT '[]' NOT NULL"))

    # Populate new columns from original_forecast if the FK still exists
    if "original_forecast_id" in columns:
        conn.execute(text("""
            UPDATE recurrences SET
                value = COALESCE((SELECT f.value FROM forecasts f WHERE f.id = recurrences.original_forecast_id), 0),
                category_id = (SELECT f.category_id FROM forecasts f WHERE f.id = recurrences.original_forecast_id),
                tags = COALESCE((SELECT f.tags FROM forecasts f WHERE f.id = recurrences.original_forecast_id), '[]')
            WHERE value = 0
        """))

        # Recreate table without original_forecast_id
        keep_cols = "id, start, \"end\", installments, base_description, value, category_id, tags, project_id, created_at"

        conn.execute(text("""
            CREATE TABLE recurrences_new (
                id CHAR(32) NOT NULL PRIMARY KEY,
                start VARCHAR(7) NOT NULL,
                "end" VARCHAR(7),
                installments INTEGER,
                base_description VARCHAR(500),
                value NUMERIC(15, 2) NOT NULL DEFAULT 0,
                category_id CHAR(32) REFERENCES categories(id) ON DELETE SET NULL,
                tags JSON NOT NULL DEFAULT '[]',
                project_id CHAR(32) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        conn.execute(text(f"INSERT INTO recurrences_new ({keep_cols}) SELECT {keep_cols} FROM recurrences"))
        conn.execute(text("DROP TABLE recurrences"))
        conn.execute(text("ALTER TABLE recurrences_new RENAME TO recurrences"))


async def _migrate_recurrent_forecasts_data(db):
    """Convert old is_recurrent=1 forecasts (without a recurrence_id) into
    proper recurrence records, then deduplicate recurrences.

    Groups forecasts by description+value+project_id so that identical
    recurring forecasts across months share a single recurrence record.
    """
    from sqlalchemy import text, select
    from bud.models.recurrence import Recurrence
    from bud.models.forecast import Forecast
    from bud.models.budget import Budget
    from decimal import Decimal
    import uuid as uuid_mod

    # Check if the old is_recurrent column still exists
    result = await db.execute(text("PRAGMA table_info(forecasts)"))
    columns = {row[1] for row in result.fetchall()}

    migrated = 0

    if "is_recurrent" in columns:
        # Find old recurrent forecasts that haven't been migrated yet
        rows = await db.execute(
            text("SELECT id, budget_id, recurrent_start, recurrent_end FROM forecasts WHERE is_recurrent = 1 AND recurrence_id IS NULL")
        )
        old_recurrents = rows.fetchall()

        # Group by description+value+project to reuse recurrences
        rec_cache = {}  # (description, value_str, project_id) -> recurrence

        for row in old_recurrents:
            forecast_id_str, budget_id_str, recurrent_start, recurrent_end = row
            forecast_id = uuid_mod.UUID(forecast_id_str)
            budget_id = uuid_mod.UUID(budget_id_str)

            budget_result = await db.execute(select(Budget).where(Budget.id == budget_id))
            budget_obj = budget_result.scalar_one_or_none()
            if not budget_obj:
                continue

            end_month = None
            if recurrent_end:
                from datetime import date
                if isinstance(recurrent_end, str):
                    end_month = recurrent_end[:7]
                elif isinstance(recurrent_end, date):
                    end_month = recurrent_end.strftime("%Y-%m")

            forecast_result = await db.execute(select(Forecast).where(Forecast.id == forecast_id))
            forecast_obj = forecast_result.scalar_one_or_none()
            if not forecast_obj:
                continue

            key = (forecast_obj.description, str(forecast_obj.value), str(budget_obj.project_id))

            if key in rec_cache:
                rec = rec_cache[key]
                # Update start to earliest month
                if budget_obj.name < rec.start:
                    rec.start = budget_obj.name
            else:
                rec = Recurrence(
                    id=uuid_mod.uuid4(),
                    start=budget_obj.name,
                    end=end_month,
                    base_description=forecast_obj.description,
                    value=Decimal(str(forecast_obj.value)),
                    category_id=forecast_obj.category_id,
                    tags=forecast_obj.tags or [],
                    project_id=budget_obj.project_id,
                )
                db.add(rec)
                await db.flush()
                rec_cache[key] = rec

            forecast_obj.recurrence_id = rec.id
            migrated += 1

        await db.commit()

    # Deduplicate existing recurrences: group by base_description+value+project_id,
    # keep the one with the earliest start, re-link all forecasts to it
    deduped = await _deduplicate_recurrences(db)

    # Re-link orphaned forecasts that lost their recurrence_id (e.g. from
    # a previous broken migration where ondelete=SET NULL fired)
    relinked = await _relink_orphaned_forecasts(db)

    return migrated + deduped + relinked


async def _relink_orphaned_forecasts(db):
    """Re-link forecasts that have recurrence_id=NULL but match a recurrence
    by description+value+project_id. This fixes data left broken by previous
    migrations where ondelete=SET NULL cascade wiped recurrence_id values.
    """
    from sqlalchemy import text

    result = await db.execute(text("""
        UPDATE forecasts SET recurrence_id = (
            SELECT r.id FROM recurrences r
            JOIN budgets b ON b.id = forecasts.budget_id
            WHERE r.base_description = forecasts.description
              AND CAST(r.value AS TEXT) = CAST(forecasts.value AS TEXT)
              AND r.project_id = b.project_id
            LIMIT 1
        )
        WHERE recurrence_id IS NULL
          AND EXISTS (
            SELECT 1 FROM recurrences r
            JOIN budgets b ON b.id = forecasts.budget_id
            WHERE r.base_description = forecasts.description
              AND CAST(r.value AS TEXT) = CAST(forecasts.value AS TEXT)
              AND r.project_id = b.project_id
          )
    """))
    relinked = result.rowcount
    if relinked:
        await db.commit()
    return relinked


async def _deduplicate_recurrences(db):
    """Merge duplicate recurrences (same base_description+value+project_id).

    Keeps the recurrence with the earliest start, re-links forecasts from
    duplicates to the keeper, then deletes the duplicates.

    Uses raw SQL to avoid ondelete="SET NULL" cascade on the FK.
    """
    from sqlalchemy import text

    # Get all recurrences ordered by start
    result = await db.execute(text(
        "SELECT id, base_description, value, project_id, start FROM recurrences ORDER BY start"
    ))
    all_recs = result.fetchall()

    # Group by (base_description, value_str, project_id)
    groups = {}
    for row in all_recs:
        rec_id, desc, value, project_id, start = row
        key = (desc, str(value), str(project_id))
        groups.setdefault(key, []).append(rec_id)

    deduped = 0
    for key, rec_ids in groups.items():
        if len(rec_ids) <= 1:
            continue

        keeper_id = rec_ids[0]
        dup_ids = rec_ids[1:]

        for dup_id in dup_ids:
            # Re-link forecasts using raw SQL (bypasses FK cascade)
            result = await db.execute(
                text("UPDATE forecasts SET recurrence_id = :keeper WHERE recurrence_id = :dup"),
                {"keeper": keeper_id, "dup": dup_id},
            )
            deduped += result.rowcount

        # Delete all duplicates at once using raw SQL (bypasses FK cascade)
        placeholders = ", ".join(f":id{i}" for i in range(len(dup_ids)))
        params = {f"id{i}": did for i, did in enumerate(dup_ids)}
        await db.execute(
            text(f"DELETE FROM recurrences WHERE id IN ({placeholders})"),
            params,
        )

    if deduped:
        await db.commit()
    return deduped


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
