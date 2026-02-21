import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import require_user_id, resolve_project_id, resolve_budget_id
from bud.schemas.budget import BudgetCreate, BudgetUpdate
from bud.services import budgets as budget_service


@click.group()
def budget():
    """Manage budgets."""
    pass


@budget.command("list")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def list_budgets(project_id):
    """List all budgets for a project."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id, user_id)
            if not pid:
                click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
                return
            items = await budget_service.list_budgets(db, pid)
            if not items:
                click.echo("No budgets found.")
                return
            rows = [[str(b.id), b.name, str(b.start_date), str(b.end_date)] for b in items]
            click.echo(tabulate(rows, headers=["ID", "Month", "Start", "End"]))

    run_async(_run())


@budget.command("create")
@click.option("--month", required=True, help="YYYY-MM")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def create_budget(month, project_id):
    """Create a budget for a month."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id, user_id)
            if not pid:
                click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
                return
            b = await budget_service.create_budget(db, BudgetCreate(name=month, project_id=pid))
            click.echo(f"Created budget: {b.name} (id: {b.id})")

    run_async(_run())


@budget.command("edit")
@click.argument("budget_id")
@click.option("--month", default=None, help="YYYY-MM")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when BUDGET_ID is a month name)")
def edit_budget(budget_id, month, project_id):
    """Edit a budget. BUDGET_ID can be a UUID or month name (YYYY-MM)."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            from bud.commands.utils import is_uuid
            if is_uuid(budget_id):
                import uuid
                bid = uuid.UUID(budget_id)
            else:
                pid = await resolve_project_id(db, project_id, user_id)
                if not pid:
                    click.echo("Error: --project required when using month name for budget.", err=True)
                    return
                bid = await resolve_budget_id(db, budget_id, pid)
                if not bid:
                    click.echo(f"Budget not found: {budget_id}", err=True)
                    return
            b = await budget_service.update_budget(db, bid, BudgetUpdate(name=month))
            if not b:
                click.echo("Budget not found.", err=True)
                return
            click.echo(f"Updated budget: {b.name}")

    run_async(_run())


@budget.command("delete")
@click.argument("budget_id")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when BUDGET_ID is a month name)")
@click.confirmation_option(prompt="Delete this budget?")
def delete_budget(budget_id, project_id):
    """Delete a budget. BUDGET_ID can be a UUID or month name (YYYY-MM)."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            from bud.commands.utils import is_uuid
            if is_uuid(budget_id):
                import uuid
                bid = uuid.UUID(budget_id)
            else:
                pid = await resolve_project_id(db, project_id, user_id)
                if not pid:
                    click.echo("Error: --project required when using month name for budget.", err=True)
                    return
                bid = await resolve_budget_id(db, budget_id, pid)
                if not bid:
                    click.echo(f"Budget not found: {budget_id}", err=True)
                    return
            ok = await budget_service.delete_budget(db, bid)
            if not ok:
                click.echo("Budget not found.", err=True)
                return
            click.echo("Budget deleted.")

    run_async(_run())
