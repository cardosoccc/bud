"""CLI commands for configuring cloud provider credentials."""
from __future__ import annotations

import os

import click


@click.command("aws")
@click.option("--access-key-id", prompt="aws access key id", help="aws access key id.")
@click.option(
    "--secret-access-key",
    prompt="aws secret access key",
    hide_input=True,
    help="aws secret access key.",
)
def configure_aws(access_key_id: str, secret_access_key: str) -> None:
    """store aws credentials for push/pull operations."""
    from bud.credentials import set_credential

    set_credential("aws_access_key_id", access_key_id)
    set_credential("aws_secret_access_key", secret_access_key)
    click.echo("aws credentials saved.")


@click.command("gcp")
@click.option(
    "--key-file",
    prompt="path to gcp service-account key file",
    help="absolute path to a gcp service-account json key file.",
)
def configure_gcp(key_file: str) -> None:
    """store gcp service-account key file path for push/pull operations."""
    path = os.path.expanduser(key_file)
    if not os.path.isfile(path):
        click.echo(f"error: file not found: {path}", err=True)
        raise SystemExit(1)

    from bud.credentials import set_credential

    set_credential("gcp_service_account_key_file", os.path.abspath(path))
    click.echo("gcp credentials saved.")
