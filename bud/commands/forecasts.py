import uuid
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import require_user_id, resolve_project_id, resolve_category_id, resolve_budget_id, is_uuid
from bud.schemas.forecast import ForecastCreate, ForecastUpdate
from bud.services import forecasts as forecast_service


@click.group()
def forecast():
    """Manage forecasts."""
    pass


@forecast.command("list")
@click.option("--budget", "budget_id", required=True, help="Budget UUID or month name (YYYY-MM)")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when --budget is a month name)")
def list_forecasts(budget_id, project_id):
    """List all forecasts for a budget."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            if is_uuid(budget_id):
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
            items = await forecast_service.list_forecasts(db, bid)
            if not items:
                click.echo("No forecasts found.")
                return
            rows = [[str(f.id)[:8], f.description, f.value, "Yes" if f.is_recurrent else ""] for f in items]
            click.echo(tabulate(rows, headers=["ID", "Description", "Value", "Recurrent"], tablefmt="psql", floatfmt=".2f"))

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
        user_id = require_user_id()
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        async with get_session() as db:
            if is_uuid(budget_id):
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

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id, user_id)
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
def edit_forecast(forecast_id, description, value, category_id, tags, min_value, max_value):
    """Edit a forecast."""
    async def _run():
        user_id = require_user_id()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        async with get_session() as db:
            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id, user_id)
                if not cat:
                    click.echo(f"Category not found: {category_id}", err=True)
                    return

            f = await forecast_service.update_forecast(db, uuid.UUID(forecast_id), ForecastUpdate(
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
@click.confirmation_option(prompt="Delete this forecast?")
def delete_forecast(forecast_id):
    """Delete a forecast."""
    async def _run():
        require_user_id()
        async with get_session() as db:
            ok = await forecast_service.delete_forecast(db, uuid.UUID(forecast_id))
            if not ok:
                click.echo("Forecast not found.", err=True)
                return
            click.echo("Forecast deleted.")

    run_async(_run())
