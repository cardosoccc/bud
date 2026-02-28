import uuid

import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_category_id, is_uuid
from bud.services import recurrences as recurrence_service


@click.group()
def recurrence():
    """Manage recurrences."""
    pass


def _recurrence_type_label(r):
    if r.installments:
        return f"{r.installments} installments"
    if r.end:
        return f"until {r.end}"
    return "open"


async def _resolve_items(db, project_id, month, show_all):
    """Return the list of recurrences based on --all flag or month scope."""
    from bud.commands.utils import require_month

    pid = await resolve_project_id(db, project_id)
    if not pid:
        click.echo("error: no project specified. use --project or set a default.", err=True)
        return None, None

    if show_all:
        items = await recurrence_service.list_recurrences(db, pid)
    else:
        m = month if month else require_month()
        items = await recurrence_service.get_recurrences_for_month(db, pid, m)

    return pid, items


@recurrence.command("list")
@click.argument("month", default=None, required=False)
@click.option("--all", "show_all", is_flag=True, default=False, help="Show all recurrences")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.option("--show-id", is_flag=True, default=False, help="Show recurrence UUIDs")
def list_recurrences(month, show_all, project_id, show_id):
    """List recurrences. Defaults to those active in the current month."""
    async def _run():
        async with get_session() as db:
            pid, items = await _resolve_items(db, project_id, month, show_all)
            if pid is None:
                return
            if not items:
                click.echo("no recurrences found.")
                return

            if show_id:
                rows = [
                    [i + 1, str(r.id), r.base_description or "", r.value,
                     r.category.name if r.category else "",
                     ", ".join(r.tags) if r.tags else "",
                     r.start, _recurrence_type_label(r)]
                    for i, r in enumerate(items)
                ]
                headers = ["#", "id", "description", "value", "category", "tags", "start", "type"]
            else:
                rows = [
                    [i + 1, r.base_description or "", r.value,
                     r.category.name if r.category else "",
                     ", ".join(r.tags) if r.tags else "",
                     r.start, _recurrence_type_label(r)]
                    for i, r in enumerate(items)
                ]
                headers = ["#", "description", "value", "category", "tags", "start", "type"]
            click.echo(tabulate(rows, headers=headers, tablefmt="presto", floatfmt=".2f"))

    run_async(_run())


@recurrence.command("edit")
@click.argument("counter", required=False, type=int, default=None)
@click.option("--id", "record_id", default=None, help="Recurrence UUID")
@click.option("--description", default=None)
@click.option("--value", type=float, default=None)
@click.option("--category", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None, help="Comma-separated tags")
@click.option("--start", default=None, help="Start month (YYYY-MM)")
@click.option("--end", default=None, help="End month (YYYY-MM)")
@click.option("--installments", type=int, default=None)
@click.option("--propagate", is_flag=True, default=False, help="Propagate changes to linked forecasts")
@click.argument("month", default=None, required=False)
@click.option("--all", "show_all", is_flag=True, default=False, help="Use counter from full list")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def edit_recurrence(counter, record_id, description, value, category_id, tags,
                    start, end, installments, propagate, month, show_all, project_id):
    """Edit a recurrence. Specify by list counter (default) or --id."""
    async def _run():
        from decimal import Decimal
        from bud.schemas.recurrence import RecurrenceUpdate

        async with get_session() as db:
            if record_id:
                rid = uuid.UUID(record_id)
            elif counter is not None:
                pid, items = await _resolve_items(db, project_id, month, show_all)
                if pid is None:
                    return
                if counter < 1 or counter > len(items):
                    click.echo(f"recurrence #{counter} not found in list.", err=True)
                    return
                rid = items[counter - 1].id
            else:
                click.echo("error: provide a counter or --id.", err=True)
                return

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    click.echo(f"category not found: {category_id}", err=True)
                    return

            tag_list = [t.strip() for t in tags.split(",")] if tags else None

            update_data = {}
            if description is not None:
                update_data["base_description"] = description
            if value is not None:
                update_data["value"] = Decimal(str(value))
            if cat is not None:
                update_data["category_id"] = cat
            if tag_list is not None:
                update_data["tags"] = tag_list
            if start is not None:
                update_data["start"] = start
            if end is not None:
                update_data["end"] = end
            if installments is not None:
                update_data["installments"] = installments

            rec = await recurrence_service.update_recurrence(
                db, rid, RecurrenceUpdate(**update_data)
            )
            if not rec:
                click.echo("recurrence not found.", err=True)
                return

            if propagate:
                count = await recurrence_service.propagate_to_forecasts(db, rec)
                click.echo(f"updated recurrence: {rec.base_description} ({count} forecasts updated)")
            else:
                click.echo(f"updated recurrence: {rec.base_description}")

    run_async(_run())


@recurrence.command("delete")
@click.argument("recurrence_id")
@click.argument("month", default=None, required=False)
@click.option("--all", "show_all", is_flag=True, default=False, help="Use counter from full list")
@click.option("--cascade", is_flag=True, default=False, help="Delete all linked forecasts too")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_recurrence(recurrence_id, month, show_all, cascade, project_id, yes):
    """Delete a recurrence. RECURRENCE_ID can be a UUID or list counter (#)."""
    async def _run():
        async with get_session() as db:
            if recurrence_id.isdigit():
                pid, items = await _resolve_items(db, project_id, month, show_all)
                if pid is None:
                    return
                n = int(recurrence_id)
                if n < 1 or n > len(items):
                    click.echo(f"recurrence #{n} not found in list.", err=True)
                    return
                r = items[n - 1]
                rid = r.id
                prompt = f"delete recurrence #{n} ({r.base_description or rid})?"
            else:
                rid = uuid.UUID(recurrence_id)
                prompt = f"delete recurrence id: {rid}?"

            if cascade:
                prompt = prompt.rstrip("?") + " and all linked forecasts?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await recurrence_service.delete_recurrence(db, rid, cascade=cascade)
            if not ok:
                click.echo("recurrence not found.", err=True)
                return
            click.echo("recurrence deleted.")

    run_async(_run())
