import uuid
from decimal import Decimal

import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_category_id, resolve_budget_id, is_uuid
from bud.schemas.budget import BudgetCreate
from bud.schemas.category import CategoryCreate
from bud.schemas.forecast import ForecastCreate, ForecastUpdate
from bud.schemas.recurrence import RecurrenceCreate
from bud.services import budgets as budget_service
from bud.services import categories as category_service
from bud.services import forecasts as forecast_service
from bud.services import recurrences as recurrence_service


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
        click.echo("error: --project required when using month name for budget.", err=True)
        return None
    bid = await resolve_budget_id(db, budget_id, pid)
    if not bid:
        click.echo(f"budget not found: {budget_id}", err=True)
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
        click.echo("error: --project required to resolve or create budget.", err=True)
        return None

    month = budget_id if budget_id else require_month()

    existing = await budget_service.get_budget_by_name(db, pid, month)
    if existing:
        return existing.id

    b = await budget_service.create_budget(db, BudgetCreate(name=month, project_id=pid))
    click.echo(f"auto-created budget: {b.name}")
    return b.id


@forecast.command("list")
@click.argument("budget_id", default=None, required=False)
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
@click.option("--show-id", "-s", is_flag=True, default=False, help="Show forecast UUIDs")
def list_forecasts(budget_id, project_id, show_id):
    """List all forecasts for a budget. Defaults to the current month's budget."""
    async def _run():
        from bud.commands.utils import require_month
        async with get_session() as db:
            if budget_id is None or not is_uuid(budget_id):
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("error: --project required to resolve budget.", err=True)
                    return
                month = budget_id if budget_id else require_month()
                existing = await budget_service.get_budget_by_name(db, pid, month)
                if not existing:
                    click.echo("no forecasts found.")
                    return
                bid = existing.id
            else:
                bid = await _resolve_budget_id(db, budget_id, project_id)
                if not bid:
                    return
            items = await forecast_service.list_forecasts(db, bid)
            if not items:
                click.echo("no forecasts found.")
                return

            def _display_description(f):
                desc = (f.recurrence.base_description if f.recurrence and f.recurrence.base_description else f.description) or ""
                if f.installment is not None and f.recurrence and f.recurrence.installments:
                    desc = f"{desc} ({f.installment}/{f.recurrence.installments})".strip()
                return desc

            def _recurrence_label(f):
                if f.recurrence_id is None:
                    return ""
                if f.installment is not None:
                    return f"{f.installment}/{f.recurrence.installments}" if f.recurrence and f.recurrence.installments else str(f.installment)
                return "yes"

            if show_id:
                rows = [[i + 1, str(f.id), _display_description(f), f.value, f.category.name if f.category else "", ", ".join(f.tags) if f.tags else "", _recurrence_label(f)] for i, f in enumerate(items)]
                headers = ["#", "id", "description", "value", "category", "tags", "recurrence"]
            else:
                rows = [[i + 1, _display_description(f), f.value, f.category.name if f.category else "", ", ".join(f.tags) if f.tags else "", _recurrence_label(f)] for i, f in enumerate(items)]
                headers = ["#", "description", "value", "category", "tags", "recurrence"]
            click.echo(tabulate(rows, headers=headers, tablefmt="presto", floatfmt=".2f"))

    run_async(_run())


@forecast.command("create")
@click.argument("budget_id", default=None, required=False)
@click.option("--description", "-d", default=None)
@click.option("--value", "-v", required=True, type=float)
@click.option("--category", "-c", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", "-t", default=None, help="Comma-separated tags")
@click.option("--recurrent", "-r", is_flag=True, default=False, help="Mark as recurrent")
@click.option("--recurrence-end", "-e", default=None, help="Last month for recurrence (YYYY-MM)")
@click.option("--installments", "-i", type=int, default=None, help="Number of installments")
@click.option("--current-installment", type=int, default=None, help="Current installment number (e.g. 5 means this is the 5th of N)")
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
def create_forecast(budget_id, description, value, category_id, tags, recurrent, recurrence_end, installments, current_installment, project_id):
    """Create a forecast. Budget defaults to the current month and is auto-created if missing.

    At least one of --description, --category, or --tags must be provided.
    Forecasts match transactions using all provided criteria (AND logic).
    """
    async def _run():
        tag_list = [t.strip() for t in tags.split(",")] if tags else []
        if not description and not category_id and not tag_list:
            click.echo("error: at least one of --description, --category, or --tags is required.", err=True)
            return
        async with get_session() as db:
            bid = await _resolve_or_create_budget_id(db, budget_id, project_id)
            if not bid:
                return

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    if not click.confirm(f"category '{category_id}' not found. create it?"):
                        return
                    new_cat = await category_service.create_category(db, CategoryCreate(name=category_id))
                    click.echo(f"created category: {new_cat.name}")
                    cat = new_cat.id

            # Resolve the budget to get its month name and project_id
            budget_obj = await budget_service.get_budget(db, bid)

            is_recurrent = recurrent or recurrence_end is not None or installments is not None

            if current_installment is not None and not installments:
                click.echo("error: --current-installment requires --installments.", err=True)
                return
            if current_installment is not None and (current_installment < 1 or current_installment > installments):
                click.echo(f"error: --current-installment must be between 1 and {installments}.", err=True)
                return

            if is_recurrent and installments:
                first_inst = current_installment or 1

                # Installment-based: create original forecast with base description (no suffix)
                first_forecast = await forecast_service.create_forecast(db, ForecastCreate(
                    description=description,
                    value=value,
                    budget_id=bid,
                    category_id=cat,
                    tags=tag_list,
                    installment=first_inst,
                ))

                # Calculate theoretical start (month where installment 1 would have been)
                theoretical_start = recurrence_service._month_offset(budget_obj.name, -(first_inst - 1))

                # Create recurrence with template values
                rec = await recurrence_service.create_recurrence(db, RecurrenceCreate(
                    start=theoretical_start,
                    installments=installments,
                    base_description=description,
                    value=value,
                    category_id=cat,
                    tags=tag_list,
                    project_id=budget_obj.project_id,
                ))

                # Link first forecast to recurrence
                first_forecast.recurrence_id = rec.id
                await db.commit()

                # Create remaining installments
                for i in range(first_inst + 1, installments + 1):
                    month = recurrence_service._month_offset(budget_obj.name, i - first_inst)
                    target_budget = await budget_service.get_budget_by_name(db, budget_obj.project_id, month)
                    if not target_budget:
                        target_budget = await budget_service.create_budget(
                            db, BudgetCreate(name=month, project_id=budget_obj.project_id)
                        )
                        # create_budget calls _populate_recurrent_forecasts which may
                        # have already created this forecast
                        already = await forecast_service.forecast_exists_for_recurrence(db, rec.id, target_budget.id)
                        if already:
                            continue

                    await forecast_service.create_forecast(db, ForecastCreate(
                        description=description,
                        value=value,
                        budget_id=target_budget.id,
                        category_id=cat,
                        tags=tag_list,
                        recurrence_id=rec.id,
                        installment=i,
                    ))

                label = description or f"id: {first_forecast.id}"
                remaining = installments - first_inst + 1
                click.echo(f"created recurrent forecast: {label} ({remaining} installments, {first_inst}/{installments} to {installments}/{installments})")

            elif is_recurrent:
                # Open-ended or end-bounded recurrence
                first_forecast = await forecast_service.create_forecast(db, ForecastCreate(
                    description=description,
                    value=value,
                    budget_id=bid,
                    category_id=cat,
                    tags=tag_list,
                ))

                rec = await recurrence_service.create_recurrence(db, RecurrenceCreate(
                    start=budget_obj.name,
                    end=recurrence_end,
                    base_description=description,
                    value=value,
                    category_id=cat,
                    tags=tag_list,
                    project_id=budget_obj.project_id,
                ))

                # Link first forecast to recurrence
                first_forecast.recurrence_id = rec.id
                await db.commit()

                # Create forecasts in existing budgets within range
                all_budgets = await budget_service.list_budgets(db, budget_obj.project_id)
                for b in all_budgets:
                    if b.name <= budget_obj.name:
                        continue
                    if recurrence_end and b.name > recurrence_end:
                        continue
                    already = await forecast_service.forecast_exists_for_recurrence(db, rec.id, b.id)
                    if already:
                        continue
                    await forecast_service.create_forecast(db, ForecastCreate(
                        description=description,
                        value=value,
                        budget_id=b.id,
                        category_id=cat,
                        tags=tag_list,
                        recurrence_id=rec.id,
                    ))

                label = description or f"id: {first_forecast.id}"
                end_info = f" until {recurrence_end}" if recurrence_end else ""
                click.echo(f"created recurrent forecast: {label} ({value}){end_info}")

            else:
                # Simple non-recurrent forecast
                f = await forecast_service.create_forecast(db, ForecastCreate(
                    description=description,
                    value=value,
                    budget_id=bid,
                    category_id=cat,
                    tags=tag_list,
                ))
                label = f.description or f"id: {f.id}"
                click.echo(f"created forecast: {label} ({f.value})")

    run_async(_run())


@forecast.command("edit")
@click.argument("counter", required=False, type=int, default=None)
@click.option("--id", "record_id", default=None, help="Forecast UUID")
@click.option("--description", "-d", default=None)
@click.option("--value", "-v", type=float, default=None)
@click.option("--category", "-c", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", "-t", default=None)
@click.option("--recurrent", "-r", is_flag=True, default=False, help="Turn into a recurrent forecast")
@click.option("--recurrence-end", "-e", default=None, help="Last month for recurrence (YYYY-MM)")
@click.argument("budget_id", default=None, required=False)
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
def edit_forecast(counter, record_id, description, value, category_id, tags, recurrent, recurrence_end, budget_id, project_id):
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
                        click.echo("error: --project required to resolve budget.", err=True)
                        return
                    month = require_month()
                    existing = await budget_service.get_budget_by_name(db, pid, month)
                    if not existing:
                        click.echo(f"budget not found: {month}", err=True)
                        return
                    bid = existing.id
                items = await forecast_service.list_forecasts(db, bid)
                if counter < 1 or counter > len(items):
                    click.echo(f"forecast #{counter} not found in list.", err=True)
                    return
                fid = items[counter - 1].id
            else:
                click.echo("error: provide a counter or --id.", err=True)
                return

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    click.echo(f"category not found: {category_id}", err=True)
                    return

            f = await forecast_service.update_forecast(db, fid, ForecastUpdate(
                description=description,
                value=value,
                category_id=cat,
                tags=tag_list,
            ))
            if not f:
                click.echo("forecast not found.", err=True)
                return

            # If description changed on a recurrent forecast, update the recurrence's base_description
            if description is not None and f.recurrence_id is not None:
                from bud.services.recurrences import get_recurrence
                rec = await get_recurrence(db, f.recurrence_id)
                if rec:
                    rec.base_description = description
                    await db.commit()

            is_recurrent = recurrent or recurrence_end is not None
            if is_recurrent:
                if f.recurrence_id is not None:
                    click.echo("error: forecast is already recurrent.", err=True)
                    return

                budget_obj = await budget_service.get_budget(db, f.budget_id)

                rec = await recurrence_service.create_recurrence(db, RecurrenceCreate(
                    start=budget_obj.name,
                    end=recurrence_end,
                    base_description=f.description,
                    value=Decimal(str(f.value)),
                    category_id=f.category_id,
                    tags=f.tags or [],
                    project_id=budget_obj.project_id,
                ))

                f.recurrence_id = rec.id
                await db.commit()

                # Create forecasts in existing budgets within range
                all_budgets = await budget_service.list_budgets(db, budget_obj.project_id)
                created = 0
                for b in all_budgets:
                    if b.name <= budget_obj.name:
                        continue
                    if recurrence_end and b.name > recurrence_end:
                        continue
                    already = await forecast_service.forecast_exists_for_recurrence(db, rec.id, b.id)
                    if already:
                        continue
                    await forecast_service.create_forecast(db, ForecastCreate(
                        description=f.description,
                        value=Decimal(str(f.value)),
                        budget_id=b.id,
                        category_id=f.category_id,
                        tags=f.tags or [],
                        recurrence_id=rec.id,
                    ))
                    created += 1

                end_info = f" until {recurrence_end}" if recurrence_end else ""
                click.echo(f"updated forecast: {f.description} (now recurrent{end_info}, {created} forecasts added)")
            else:
                click.echo(f"updated forecast: {f.description}")

    run_async(_run())


@forecast.command("delete")
@click.argument("forecast_id")
@click.argument("budget_id", default=None, required=False)
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
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
                        click.echo("error: --project required to resolve budget.", err=True)
                        return
                    month = require_month()
                    existing = await budget_service.get_budget_by_name(db, pid, month)
                    if not existing:
                        click.echo(f"budget not found: {month}", err=True)
                        return
                    bid = existing.id
                items = await forecast_service.list_forecasts(db, bid)
                n = int(forecast_id)
                if n < 1 or n > len(items):
                    click.echo(f"forecast #{n} not found in list.", err=True)
                    return
                fid = items[n - 1].id
                prompt = f"delete forecast #{n} (id: {fid})?"
            else:
                fid = uuid.UUID(forecast_id)
                prompt = f"delete forecast id: {fid}?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await forecast_service.delete_forecast(db, fid)
            if not ok:
                click.echo("forecast not found.", err=True)
                return
            click.echo("forecast deleted.")

    run_async(_run())
