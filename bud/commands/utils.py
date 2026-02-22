"""Shared CLI utilities."""
import uuid
import sys
from typing import Optional
import click

from bud.commands.config_store import get_default_project_id, get_active_month


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
