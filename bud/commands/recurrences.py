import uuid

import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_category_id, is_uuid
from bud.schemas.category import CategoryCreate
from bud.services import categories as category_service
from bud.services import recurrences as recurrence_service


def _sort_key_unnamed_last(description):
    """Sort key: named items first (insertion order), unnamed last."""
    return 0 if description else 1


@click.group()
def recurrence():
    """Manage recurrences."""
    pass


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

    if items:
        items.sort(key=lambda r: _sort_key_unnamed_last(r.base_description))
    return pid, items


@recurrence.command("list")
@click.argument("month", default=None, required=False)
@click.option("--all", "-a", "show_all", is_flag=True, default=False, help="Show all recurrences")
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
@click.option("--show-id", "-s", is_flag=True, default=False, help="Show recurrence UUIDs")
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
                     r.start, r.end or "", r.installments or ""]
                    for i, r in enumerate(items)
                ]
                headers = ["#", "id", "description", "value", "category", "tags", "start", "end", "installments"]
            else:
                rows = [
                    [i + 1, r.base_description or "", r.value,
                     r.category.name if r.category else "",
                     ", ".join(r.tags) if r.tags else "",
                     r.start, r.end or "", r.installments or ""]
                    for i, r in enumerate(items)
                ]
                headers = ["#", "description", "value", "category", "tags", "start", "end", "installments"]
            click.echo(tabulate(rows, headers=headers, tablefmt="presto", floatfmt=".2f"))

    run_async(_run())


@recurrence.command("edit")
@click.argument("counter", required=False, type=int, default=None)
@click.option("--id", "record_id", default=None, help="Recurrence UUID")
@click.option("--description", "-d", default=None)
@click.option("--value", "-v", type=float, default=None)
@click.option("--category", "-c", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", "-t", default=None, help="Comma-separated tags")
@click.option("--start", "-s", default=None, help="Start month (YYYY-MM)")
@click.option("--end", "-e", default=None, help="End month (YYYY-MM)")
@click.option("--installments", "-i", type=int, default=None)
@click.option("--propagate", is_flag=True, default=False, help="Propagate changes to linked forecasts")
@click.argument("month", default=None, required=False)
@click.option("--all", "-a", "show_all", is_flag=True, default=False, help="Use counter from full list")
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
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
                    if is_uuid(category_id):
                        click.echo(f"category not found: {category_id}", err=True)
                        return
                    if click.confirm(f"category '{category_id}' not found. create it?", default=False):
                        new_cat = await category_service.create_category(db, CategoryCreate(name=category_id))
                        cat = new_cat.id
                        click.echo(f"created category: {new_cat.name}")
                    else:
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
@click.option("--all", "-a", "show_all", is_flag=True, default=False, help="Use counter from full list")
@click.option("--cascade", "-c", is_flag=True, default=False, help="Delete all linked forecasts too")
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
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
