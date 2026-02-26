import uuid
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_category_id, resolve_budget_id, is_uuid
from bud.schemas.budget import BudgetCreate
from bud.schemas.category import CategoryCreate
from bud.schemas.forecast import ForecastCreate, ForecastUpdate
from bud.services import budgets as budget_service
from bud.services import categories as category_service
from bud.services import forecasts as forecast_service


@click.group()
def forecast():
    """Manage forecasts."""
    pass


async def _resolve_budget_id(db, budget_id, project_id):
    """Resolve budget_id string (UUID or month name) to a UUID. Does NOT auto-create."""
    if is_uuid(budget_id):
        return uuid.UUID(budget_id)
    pid = await resolve_project_id(db, project_id)
    if not pid:
        click.echo("Error: --project required when using month name for budget.", err=True)
        return None
    bid = await resolve_budget_id(db, budget_id, pid)
    if not bid:
        click.echo(f"Budget not found: {budget_id}", err=True)
        return None
    return bid


async def _resolve_or_create_budget_id(db, budget_id, project_id):
    """Resolve budget to a UUID for forecast creation.

    - No budget given → use active/current month, look up or auto-create.
    - Month name given → look up or auto-create.
    - UUID given → use directly (must exist).
    """
    from bud.commands.utils import require_month

    if budget_id is not None and is_uuid(budget_id):
        return uuid.UUID(budget_id)

    # Need a project for lookup / creation
    pid = await resolve_project_id(db, project_id)
    if not pid:
        click.echo("Error: --project required to resolve or create budget.", err=True)
        return None

    month = budget_id if budget_id else require_month()

    existing = await budget_service.get_budget_by_name(db, pid, month)
    if existing:
        return existing.id

    b = await budget_service.create_budget(db, BudgetCreate(name=month, project_id=pid))
    click.echo(f"Auto-created budget: {b.name}")
    return b.id


@forecast.command("list")
@click.option("--budget", "budget_id", default=None, help="Budget UUID or month name (YYYY-MM); defaults to current month")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.option("--show-id", is_flag=True, default=False, help="Show forecast UUIDs")
def list_forecasts(budget_id, project_id, show_id):
    """List all forecasts for a budget. Defaults to the current month's budget."""
    async def _run():
        from bud.commands.utils import require_month
        async with get_session() as db:
            if budget_id is None or not is_uuid(budget_id):
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("Error: --project required to resolve budget.", err=True)
                    return
                month = budget_id if budget_id else require_month()
                existing = await budget_service.get_budget_by_name(db, pid, month)
                if not existing:
                    click.echo("No forecasts found.")
                    return
                bid = existing.id
            else:
                bid = await _resolve_budget_id(db, budget_id, project_id)
                if not bid:
                    return
            items = await forecast_service.list_forecasts(db, bid)
            if not items:
                click.echo("No forecasts found.")
                return
            if show_id:
                rows = [[i + 1, str(f.id), f.description or "", f.value, f.category.name if f.category else "", ", ".join(f.tags) if f.tags else "", "Yes" if f.is_recurrent else ""] for i, f in enumerate(items)]
                headers = ["#", "ID", "Description", "Value", "Category", "Tags", "Recurrent"]
            else:
                rows = [[i + 1, f.description or "", f.value, f.category.name if f.category else "", ", ".join(f.tags) if f.tags else "", "Yes" if f.is_recurrent else ""] for i, f in enumerate(items)]
                headers = ["#", "Description", "Value", "Category", "Tags", "Recurrent"]
            click.echo(tabulate(rows, headers=headers, tablefmt="psql", floatfmt=".2f"))

    run_async(_run())


@forecast.command("create")
@click.option("--budget", "budget_id", default=None, help="Budget UUID or month name (YYYY-MM); defaults to current month, auto-created if needed")
@click.option("--description", default=None)
@click.option("--value", required=True, type=float)
@click.option("--category", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None, help="Comma-separated tags")
@click.option("--min", "min_value", type=float, default=None)
@click.option("--max", "max_value", type=float, default=None)
@click.option("--recurrent", is_flag=True, default=False)
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def create_forecast(budget_id, description, value, category_id, tags, min_value, max_value, recurrent, project_id):
    """Create a forecast. Budget defaults to the current month and is auto-created if missing.

    At least one of --description, --category, or --tags must be provided.
    Forecasts match transactions using all provided criteria (AND logic).
    """
    async def _run():
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        if not description and not category_id and not tag_list:
            click.echo("Error: at least one of --description, --category, or --tags is required.", err=True)
            return
        async with get_session() as db:
            bid = await _resolve_or_create_budget_id(db, budget_id, project_id)
            if not bid:
                return

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    if not click.confirm(f"Category '{category_id}' not found. Create it?"):
                        return
                    new_cat = await category_service.create_category(db, CategoryCreate(name=category_id))
                    click.echo(f"Created category: {new_cat.name}")
                    cat = new_cat.id

            f = await forecast_service.create_forecast(db, ForecastCreate(
                description=description,
                value=value,
                budget_id=bid,
                category_id=cat,
                tags=tag_list,
                min_value=min_value,
                max_value=max_value,
                is_recurrent=recurrent,
            ))
            label = f.description or f"id: {f.id}"
            click.echo(f"Created forecast: {label} ({f.value})")

    run_async(_run())


@forecast.command("edit")
@click.argument("counter", required=False, type=int, default=None)
@click.option("--id", "record_id", default=None, help="Forecast UUID")
@click.option("--description", default=None)
@click.option("--value", type=float, default=None)
@click.option("--category", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None)
@click.option("--min", "min_value", type=float, default=None)
@click.option("--max", "max_value", type=float, default=None)
@click.option("--budget", "budget_id", default=None, help="Budget UUID or month name; defaults to current month")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when --budget is a month name)")
def edit_forecast(counter, record_id, description, value, category_id, tags, min_value, max_value, budget_id, project_id):
    """Edit a forecast. Specify by list counter (default) or --id."""
    async def _run():
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        async with get_session() as db:
            if record_id:
                fid = uuid.UUID(record_id)
            elif counter is not None:
                if budget_id:
                    bid = await _resolve_budget_id(db, budget_id, project_id)
                    if not bid:
                        return
                else:
                    from bud.commands.utils import require_month
                    pid = await resolve_project_id(db, project_id)
                    if not pid:
                        click.echo("Error: --project required to resolve budget.", err=True)
                        return
                    month = require_month()
                    existing = await budget_service.get_budget_by_name(db, pid, month)
                    if not existing:
                        click.echo(f"Budget not found: {month}", err=True)
                        return
                    bid = existing.id
                items = await forecast_service.list_forecasts(db, bid)
                if counter < 1 or counter > len(items):
                    click.echo(f"Forecast #{counter} not found in list.", err=True)
                    return
                fid = items[counter - 1].id
            else:
                click.echo("Error: provide a counter or --id.", err=True)
                return

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    click.echo(f"Category not found: {category_id}", err=True)
                    return

            f = await forecast_service.update_forecast(db, fid, ForecastUpdate(
                description=description,
                value=value,
                category_id=cat,
                tags=tag_list,
                min_value=min_value,
                max_value=max_value,
            ))
            if not f:
                click.echo("Forecast not found.", err=True)
                return
            click.echo(f"Updated forecast: {f.description}")

    run_async(_run())


@forecast.command("delete")
@click.argument("forecast_id")
@click.option("--budget", "budget_id", default=None, help="Budget UUID or month name; defaults to current month")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when --budget is a month name)")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_forecast(forecast_id, budget_id, project_id, yes):
    """Delete a forecast. FORECAST_ID can be a UUID or list counter (#)."""
    async def _run():
        async with get_session() as db:
            if forecast_id.isdigit():
                if budget_id:
                    bid = await _resolve_budget_id(db, budget_id, project_id)
                    if not bid:
                        return
                else:
                    from bud.commands.utils import require_month
                    pid = await resolve_project_id(db, project_id)
                    if not pid:
                        click.echo("Error: --project required to resolve budget.", err=True)
                        return
                    month = require_month()
                    existing = await budget_service.get_budget_by_name(db, pid, month)
                    if not existing:
                        click.echo(f"Budget not found: {month}", err=True)
                        return
                    bid = existing.id
                items = await forecast_service.list_forecasts(db, bid)
                n = int(forecast_id)
                if n < 1 or n > len(items):
                    click.echo(f"Forecast #{n} not found in list.", err=True)
                    return
                fid = items[n - 1].id
                prompt = f"Delete forecast #{n} (id: {fid})?"
            else:
                fid = uuid.UUID(forecast_id)
                prompt = f"Delete forecast id: {fid}?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await forecast_service.delete_forecast(db, fid)
            if not ok:
                click.echo("Forecast not found.", err=True)
                return
            click.echo("Forecast deleted.")

    run_async(_run())
