"""Shared CLI utilities."""
import functools
import uuid
import sys
from typing import Optional
import click

from bud.commands.config_store import get_default_project_id, get_active_month, get_auto_push


def require_project_id(project_id: str = None) -> uuid.UUID:
    pid = project_id or get_default_project_id()
    if not pid:
        click.echo("error: no project specified. use --project or set a default with `bud project set-default`.", err=True)
        sys.exit(1)
    return uuid.UUID(pid)


def require_month(month: str = None) -> str:
    return month or get_active_month()


def is_uuid(s: str) -> bool:
    """Return True if s is a valid UUID string."""
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


async def resolve_project_id(db, identifier: Optional[str]) -> Optional[uuid.UUID]:
    """Resolve a project name or UUID to a UUID. Falls back to default project if None."""
    from bud.services import projects as project_service

    if identifier is None:
        pid_str = get_default_project_id()
        if not pid_str:
            return None
        return uuid.UUID(pid_str)

    if is_uuid(identifier):
        return uuid.UUID(identifier)

    project = await project_service.get_project_by_name(db, identifier)
    return project.id if project else None


async def resolve_account_id(
    db, identifier: str, project_id: Optional[uuid.UUID] = None
) -> Optional[uuid.UUID]:
    """Resolve an account name or UUID to a UUID."""
    from bud.services import accounts as account_service

    if is_uuid(identifier):
        return uuid.UUID(identifier)

    if project_id is None:
        return None

    account = await account_service.get_account_by_name(db, identifier, project_id)
    return account.id if account else None


async def resolve_category_id(db, identifier: str) -> Optional[uuid.UUID]:
    """Resolve a category name or UUID to a UUID."""
    from bud.services import categories as category_service

    if is_uuid(identifier):
        return uuid.UUID(identifier)

    category = await category_service.get_category_by_name(db, identifier)
    return category.id if category else None


async def resolve_budget_id(db, identifier: str, project_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Resolve a budget month name (YYYY-MM) or UUID to a UUID."""
    from bud.services import budgets as budget_service

    if is_uuid(identifier):
        return uuid.UUID(identifier)

    budget = await budget_service.get_budget_by_name(db, project_id, identifier)
    return budget.id if budget else None


def maybe_auto_push(auto_push_flag: bool) -> None:
    """Push to cloud storage if auto-push is enabled (via flag or config)."""
    if auto_push_flag or get_auto_push():
        from bud.commands.sync import run_push
        from bud.services.storage import CloudAuthError

        try:
            run_push()
        except CloudAuthError as exc:
            click.echo(f"auto-push failed: {exc}", err=True)


def with_auto_push(fn):
    """Decorator that adds --auto-push flag and triggers push after the command."""
    @click.option("--auto-push", is_flag=True, default=False,
                  help="push to cloud storage after this operation")
    @functools.wraps(fn)
    def wrapper(*args, auto_push, **kwargs):
        result = fn(*args, **kwargs)
        maybe_auto_push(auto_push)
        return result
    return wrapper
