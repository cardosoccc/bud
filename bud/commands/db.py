"""Async database session helper for CLI commands."""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bud.commands.config_store import get_config_dir, get_db_url


def get_engine():
    from bud.database import _make_engine
    return _make_engine(get_db_url())


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    # Ensure user config dir exists and tables are created on first use
    get_config_dir().mkdir(parents=True, exist_ok=True)
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
