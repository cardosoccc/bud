"""Push and pull commands for syncing the database with cloud storage."""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import click

from bud.commands.config_store import CONFIG_DIR, DB_PATH, get_config_value

SYNC_META_FILE = CONFIG_DIR / "sync_meta.json"
REMOTE_DB_KEY = "bud.db"
REMOTE_META_KEY = "sync_meta.json"


def _load_local_meta() -> dict:
    if SYNC_META_FILE.exists():
        with open(SYNC_META_FILE) as f:
            return json.load(f)
    return {"version": 0}


def _save_local_meta(meta: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SYNC_META_FILE, "w") as f:
        json.dump(meta, f, indent=2)


def _get_bucket_url() -> str:
    url = get_config_value("bucket")
    if not url:
        click.echo(
            "Error: no bucket configured. Set one with:\n"
            '  bud config set bucket s3://my-bucket/path\n'
            '  bud config set bucket gs://my-bucket/path',
            err=True,
        )
        sys.exit(1)
    return url


def _handle_auth_error(err) -> None:
    """Print a user-friendly authentication error and exit."""
    click.echo(
        f"Error: {err.provider} authentication failed.\n"
        f"  {err}\n\n"
        f"To configure {err.provider} credentials, run:\n"
        f"  {err.configure_hint}",
        err=True,
    )
    sys.exit(1)


@click.command("push")
@click.option("--force", "-f", is_flag=True, help="Push even if remote has a newer version.")
def push(force: bool) -> None:
    """Push the local database to cloud storage."""
    from bud.services.storage import CloudAuthError, get_provider

    if not DB_PATH.exists():
        click.echo("Error: local database does not exist. Run `bud db init` first.", err=True)
        sys.exit(1)

    bucket_url = _get_bucket_url()

    try:
        provider = get_provider(bucket_url)
    except CloudAuthError as exc:
        _handle_auth_error(exc)

    try:
        local_meta = _load_local_meta()
        local_version = local_meta.get("version", 0)

        remote_meta = provider.read_json(REMOTE_META_KEY)
        remote_version = remote_meta.get("version", 0) if remote_meta else 0

        if remote_version > local_version and not force:
            click.echo(
                f"Error: remote version ({remote_version}) is newer than local ({local_version}).\n"
                "Pull the latest version first, or use --force to overwrite.",
                err=True,
            )
            sys.exit(1)

        new_version = max(local_version, remote_version) + 1
        new_meta = {"version": new_version, "pushed_at": time.time()}

        provider.upload(DB_PATH, REMOTE_DB_KEY)
        provider.upload_json(new_meta, REMOTE_META_KEY)
        _save_local_meta(new_meta)

        click.echo(f"Pushed database to {bucket_url} (version {new_version}).")
    except CloudAuthError as exc:
        _handle_auth_error(exc)


@click.command("pull")
@click.option("--force", "-f", is_flag=True, help="Pull even if local has a newer version.")
def pull(force: bool) -> None:
    """Pull the database from cloud storage."""
    from bud.services.storage import CloudAuthError, get_provider

    bucket_url = _get_bucket_url()

    try:
        provider = get_provider(bucket_url)
    except CloudAuthError as exc:
        _handle_auth_error(exc)

    try:
        remote_meta = provider.read_json(REMOTE_META_KEY)
        if remote_meta is None:
            click.echo("Error: no database found in remote storage. Push first.", err=True)
            sys.exit(1)

        remote_version = remote_meta.get("version", 0)

        local_meta = _load_local_meta()
        local_version = local_meta.get("version", 0)

        if local_version > remote_version and not force:
            click.echo(
                f"Error: local version ({local_version}) is newer than remote ({remote_version}).\n"
                "Push your changes first, or use --force to overwrite.",
                err=True,
            )
            sys.exit(1)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        if DB_PATH.exists():
            backup = DB_PATH.with_suffix(".db.bak")
            shutil.copy2(DB_PATH, backup)

        provider.download(REMOTE_DB_KEY, DB_PATH)
        _save_local_meta(remote_meta)

        click.echo(f"Pulled database from {bucket_url} (version {remote_version}).")
    except CloudAuthError as exc:
        _handle_auth_error(exc)
