import uuid
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_category_id, resolve_budget_id, is_uuid
from bud.schemas.forecast import ForecastCreate, ForecastUpdate
from bud.services import forecasts as forecast_service


@click.group()
def forecast():
    """Manage forecasts."""
    pass


async def _resolve_budget_id(db, budget_id, project_id):
    """Resolve budget_id string (UUID or month name) to a UUID."""
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


@forecast.command("list")
@click.option("--budget", "budget_id", required=True, help="Budget UUID or month name (YYYY-MM)")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when --budget is a month name)")
@click.option("--show-id", is_flag=True, default=False, help="Show forecast UUIDs")
def list_forecasts(budget_id, project_id, show_id):
    """List all forecasts for a budget."""
    async def _run():
        async with get_session() as db:
            bid = await _resolve_budget_id(db, budget_id, project_id)
            if not bid:
                return
            items = await forecast_service.list_forecasts(db, bid)
            if not items:
                click.echo("No forecasts found.")
                return
            if show_id:
                rows = [[i + 1, str(f.id), f.description, f.value, "Yes" if f.is_recurrent else ""] for i, f in enumerate(items)]
                headers = ["#", "ID", "Description", "Value", "Recurrent"]
            else:
                rows = [[i + 1, f.description, f.value, "Yes" if f.is_recurrent else ""] for i, f in enumerate(items)]
                headers = ["#", "Description", "Value", "Recurrent"]
            click.echo(tabulate(rows, headers=headers, tablefmt="psql", floatfmt=".2f"))

    run_async(_run())


@forecast.command("create")
@click.option("--budget", "budget_id", required=True, help="Budget UUID or month name (YYYY-MM)")
@click.option("--description", required=True)
@click.option("--value", required=True, type=float)
@click.option("--category", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None, help="Comma-separated tags")
@click.option("--min", "min_value", type=float, default=None)
@click.option("--max", "max_value", type=float, default=None)
@click.option("--recurrent", is_flag=True, default=False)
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when --budget is a month name)")
def create_forecast(budget_id, description, value, category_id, tags, min_value, max_value, recurrent, project_id):
    """Create a forecast."""
    async def _run():
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        async with get_session() as db:
            bid = await _resolve_budget_id(db, budget_id, project_id)
            if not bid:
                return

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    click.echo(f"Category not found: {category_id}", err=True)
                    return

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
            click.echo(f"Created forecast: {f.description} ({f.value}) id: {f.id}")

    run_async(_run())


@forecast.command("edit")
@click.argument("forecast_id")
@click.option("--description", default=None)
@click.option("--value", type=float, default=None)
@click.option("--category", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None)
@click.option("--min", "min_value", type=float, default=None)
@click.option("--max", "max_value", type=float, default=None)
@click.option("--budget", "budget_id", default=None, help="Budget UUID or month name (required when FORECAST_ID is a counter)")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when --budget is a month name)")
def edit_forecast(forecast_id, description, value, category_id, tags, min_value, max_value, budget_id, project_id):
    """Edit a forecast. FORECAST_ID can be a UUID or list counter (#)."""
    async def _run():
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        async with get_session() as db:
            if forecast_id.isdigit():
                if not budget_id:
                    click.echo("Error: --budget required when using forecast counter.", err=True)
                    return
                bid = await _resolve_budget_id(db, budget_id, project_id)
                if not bid:
                    return
                items = await forecast_service.list_forecasts(db, bid)
                n = int(forecast_id)
                if n < 1 or n > len(items):
                    click.echo(f"Forecast #{n} not found in list.", err=True)
                    return
                fid = items[n - 1].id
            else:
                fid = uuid.UUID(forecast_id)

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
@click.option("--budget", "budget_id", default=None, help="Budget UUID or month name (required when FORECAST_ID is a counter)")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when --budget is a month name)")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_forecast(forecast_id, budget_id, project_id, yes):
    """Delete a forecast. FORECAST_ID can be a UUID or list counter (#)."""
    async def _run():
        async with get_session() as db:
            if forecast_id.isdigit():
                if not budget_id:
                    click.echo("Error: --budget required when using forecast counter.", err=True)
                    return
                bid = await _resolve_budget_id(db, budget_id, project_id)
                if not bid:
                    return
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
