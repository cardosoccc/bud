"""Async database session helper for CLI commands."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bud.commands.config_store import get_db_url


def get_engine():
    url = get_db_url()
    eng = create_async_engine(url, echo=False)

    @event.listens_for(eng.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return eng


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    # Ensure ~/.bud exists and tables are created on first use
    Path.home().joinpath(".bud").mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        from bud.database import Base
        import bud.models  # noqa: F401 - ensure all models are registered
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_migrations)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


def _apply_migrations(connection):
    """Lightweight schema migrations for SQLite (no ALTER COLUMN support).

    SQLite cannot alter column constraints in-place, so we recreate affected
    tables when the schema drifts from what the models declare.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(connection)

    # Migration: forecasts.description NOT NULL → nullable
    if "forecasts" in inspector.get_table_names():
        cols = {c["name"]: c for c in inspector.get_columns("forecasts")}
        if "description" in cols and not cols["description"]["nullable"]:
            connection.execute(text(
                "ALTER TABLE forecasts RENAME TO _forecasts_old"
            ))
            from bud.database import Base
            Base.metadata.tables["forecasts"].create(connection)
            # Copy data from old table
            old_cols = ", ".join(cols.keys())
            connection.execute(text(
                f"INSERT INTO forecasts ({old_cols}) SELECT {old_cols} FROM _forecasts_old"
            ))
            connection.execute(text("DROP TABLE _forecasts_old"))


def run_async(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.run(coro)
