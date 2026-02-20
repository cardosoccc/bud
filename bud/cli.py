import click


@click.group()
def cli():
    """bud - CLI"""
    pass


@cli.command()
def help():
    """Show available commands."""
    ctx = click.get_current_context()
    click.echo(ctx.parent.get_help())


if __name__ == "__main__":
    cli()
