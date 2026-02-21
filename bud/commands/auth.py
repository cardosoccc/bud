import click

from bud.commands.config_store import load_config, save_config, set_config_value, get_user_id
from bud.commands.db import get_session, run_async
from bud.services import users as user_service
from bud.schemas.user import UserCreate
from bud.auth import verify_password


@click.group()
def auth():
    """Authentication commands."""
    pass


@auth.command()
@click.option("--email", prompt=True)
@click.option("--name", prompt=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, default=None)
def register(email, name, password):
    """Register a new user account."""
    async def _run():
        async with get_session() as db:
            existing = await user_service.get_user_by_email(db, email)
            if existing:
                click.echo("Error: email already registered.", err=True)
                return
            user = await user_service.create_user(db, UserCreate(email=email, name=name, password=password or None))
            set_config_value("user_id", str(user.id))
            set_config_value("default_project_id", str(user.projects[0].id) if user.projects else None)
            click.echo(f"Registered and logged in as {user.email} (id: {user.id})")

    run_async(_run())


@auth.command()
@click.option("--email", prompt=True)
@click.option("--password", prompt=True, hide_input=True)
def login(email, password):
    """Log in with email and password."""
    async def _run():
        async with get_session() as db:
            user = await user_service.get_user_by_email(db, email)
            if not user or not user.hashed_password:
                click.echo("Error: invalid credentials.", err=True)
                return
            if not verify_password(password, user.hashed_password):
                click.echo("Error: invalid credentials.", err=True)
                return
            set_config_value("user_id", str(user.id))
            click.echo(f"Logged in as {user.email}")

    run_async(_run())


@auth.command()
def logout():
    """Log out (clear stored credentials)."""
    config = load_config()
    config.pop("user_id", None)
    save_config(config)
    click.echo("Logged out.")


@auth.command()
def whoami():
    """Show current logged-in user."""
    async def _run():
        user_id = get_user_id()
        if not user_id:
            click.echo("Not logged in.")
            return
        import uuid
        async with get_session() as db:
            user = await user_service.get_user(db, uuid.UUID(user_id))
            if not user:
                click.echo("Not logged in (user not found).")
                return
            click.echo(f"Logged in as: {user.name} <{user.email}> (id: {user.id})")

    run_async(_run())
