import uuid
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_budget_id, is_uuid
from bud.schemas.budget import BudgetCreate, BudgetUpdate
from bud.services import budgets as budget_service


@click.group()
def budget():
    """Manage budgets."""
    pass


@budget.command("list")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.option("--show-id", is_flag=True, default=False, help="Show budget UUIDs")
def list_budgets(project_id, show_id):
    """List all budgets for a project."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("error: no project specified. use --project or set a default with `bud project set-default`.", err=True)
                return
            items = await budget_service.list_budgets(db, pid)
            if not items:
                click.echo("no budgets found.")
                return
            if show_id:
                rows = [[i + 1, str(b.id), b.name, str(b.start_date), str(b.end_date)] for i, b in enumerate(items)]
                headers = ["#", "id", "month", "start", "end"]
            else:
                rows = [[i + 1, b.name, str(b.start_date), str(b.end_date)] for i, b in enumerate(items)]
                headers = ["#", "month", "start", "end"]
            click.echo(tabulate(rows, headers=headers, tablefmt="presto"))

    run_async(_run())


@budget.command("create")
@click.argument("month")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def create_budget(month, project_id):
    """Create a budget for a month (YYYY-MM)."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("error: no project specified. use --project or set a default with `bud project set-default`.", err=True)
                return
            b = await budget_service.create_budget(db, BudgetCreate(name=month, project_id=pid))
            click.echo(f"created budget: {b.name} (id: {b.id})")

    run_async(_run())


@budget.command("edit")
@click.argument("counter", required=False, type=int, default=None)
@click.option("--id", "record_id", default=None, help="Budget UUID")
@click.option("--month", default=None, help="YYYY-MM")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def edit_budget(counter, record_id, month, project_id):
    """Edit a budget. Specify by list counter (default) or --id."""
    async def _run():
        async with get_session() as db:
            if record_id:
                bid = uuid.UUID(record_id)
            elif counter is not None:
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("error: --project required when using counter.", err=True)
                    return
                items = await budget_service.list_budgets(db, pid)
                if counter < 1 or counter > len(items):
                    click.echo(f"budget #{counter} not found in list.", err=True)
                    return
                bid = items[counter - 1].id
            else:
                click.echo("error: provide a counter or --id.", err=True)
                return
            b = await budget_service.update_budget(db, bid, BudgetUpdate(name=month))
            if not b:
                click.echo("budget not found.", err=True)
                return
            click.echo(f"updated budget: {b.name}")

    run_async(_run())


@budget.command("delete")
@click.argument("budget_id")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when BUDGET_ID is a month name or counter)")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_budget(budget_id, project_id, yes):
    """Delete a budget. BUDGET_ID can be a UUID, month name (YYYY-MM), or list counter (#)."""
    async def _run():
        async with get_session() as db:
            if budget_id.isdigit():
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("error: --project required when using budget counter.", err=True)
                    return
                items = await budget_service.list_budgets(db, pid)
                n = int(budget_id)
                if n < 1 or n > len(items):
                    click.echo(f"budget #{n} not found in list.", err=True)
                    return
                bid = items[n - 1].id
                prompt = f"delete budget #{n} (id: {bid})?"
            elif is_uuid(budget_id):
                bid = uuid.UUID(budget_id)
                prompt = f"delete budget id: {bid}?"
            else:
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("error: --project required when using month name for budget.", err=True)
                    return
                bid = await resolve_budget_id(db, budget_id, pid)
                if not bid:
                    click.echo(f"budget not found: {budget_id}", err=True)
                    return
                prompt = f"delete budget id: {bid}?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await budget_service.delete_budget(db, bid)
            if not ok:
                click.echo("budget not found.", err=True)
                return
            click.echo("budget deleted.")

    run_async(_run())
