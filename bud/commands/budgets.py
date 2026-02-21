import uuid
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import require_user_id, require_project_id
from bud.schemas.budget import BudgetCreate, BudgetUpdate
from bud.services import budgets as budget_service


@click.group()
def budget():
    """Manage budgets."""
    pass


@budget.command("list")
@click.option("--project", "project_id", default=None)
def list_budgets(project_id):
    """List all budgets for a project."""
    async def _run():
        require_user_id()
        pid = require_project_id(project_id)
        async with get_session() as db:
            items = await budget_service.list_budgets(db, pid)
            if not items:
                click.echo("No budgets found.")
                return
            rows = [[str(b.id), b.name, str(b.start_date), str(b.end_date)] for b in items]
            click.echo(tabulate(rows, headers=["ID", "Month", "Start", "End"]))

    run_async(_run())


@budget.command("create")
@click.option("--month", required=True, help="YYYY-MM")
@click.option("--project", "project_id", default=None)
def create_budget(month, project_id):
    """Create a budget for a month."""
    async def _run():
        require_user_id()
        pid = require_project_id(project_id)
        async with get_session() as db:
            b = await budget_service.create_budget(db, BudgetCreate(name=month, project_id=pid))
            click.echo(f"Created budget: {b.name} (id: {b.id})")

    run_async(_run())


@budget.command("edit")
@click.argument("budget_id")
@click.option("--month", default=None, help="YYYY-MM")
def edit_budget(budget_id, month):
    """Edit a budget."""
    async def _run():
        require_user_id()
        async with get_session() as db:
            b = await budget_service.update_budget(db, uuid.UUID(budget_id), BudgetUpdate(name=month))
            if not b:
                click.echo("Budget not found.", err=True)
                return
            click.echo(f"Updated budget: {b.name}")

    run_async(_run())


@budget.command("delete")
@click.argument("budget_id")
@click.confirmation_option(prompt="Delete this budget?")
def delete_budget(budget_id):
    """Delete a budget."""
    async def _run():
        require_user_id()
        async with get_session() as db:
            ok = await budget_service.delete_budget(db, uuid.UUID(budget_id))
            if not ok:
                click.echo("Budget not found.", err=True)
                return
            click.echo("Budget deleted.")

    run_async(_run())
