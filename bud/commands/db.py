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
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


def run_async(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.run(coro)
