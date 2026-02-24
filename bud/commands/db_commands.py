"""Database management commands."""
import click

from bud.commands.config_store import DB_PATH
from bud.commands.db import get_engine, run_async
from bud.commands.sync import push, pull


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
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        engine = get_engine()
        async with engine.begin() as conn:
            from bud.database import Base
            import bud.models  # noqa: F401
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        click.echo(f"Database initialized at {DB_PATH}")

    run_async(_run())


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
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        engine = get_engine()
        async with engine.begin() as conn:
            from bud.database import Base
            import bud.models  # noqa: F401
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        click.echo(f"Database initialized at {DB_PATH}")

    run_async(_run())
    click.echo("Database reset complete.")
