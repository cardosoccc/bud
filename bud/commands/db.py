"""Async database session helper for CLI commands."""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bud.commands.config_store import get_db_url


def get_engine():
    return create_async_engine(get_db_url(), echo=False)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


def run_async(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.run(coro)
