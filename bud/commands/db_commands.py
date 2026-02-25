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
