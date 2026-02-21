"""Shared CLI utilities."""
import uuid
import sys
import click

from bud.commands.config_store import get_user_id, get_default_project_id, get_active_month


def require_user_id() -> uuid.UUID:
    uid = get_user_id()
    if not uid:
        click.echo("Error: not logged in. Run `bud auth login` first.", err=True)
        sys.exit(1)
    return uuid.UUID(uid)


def require_project_id(project_id: str = None) -> uuid.UUID:
    pid = project_id or get_default_project_id()
    if not pid:
        click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
        sys.exit(1)
    return uuid.UUID(pid)


def require_month(month: str = None) -> str:
    m = month or get_active_month()
    if not m:
        click.echo("Error: no month specified. Use --month or set active month with `bud config set-month`.", err=True)
        sys.exit(1)
    return m
