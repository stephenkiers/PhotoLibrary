"""CLI for vault."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from vault.errors import ExitCode

app = typer.Typer(no_args_is_help=True)


@dataclass(frozen=True)
class GlobalOptions:
    """Global options for the vault CLI."""

    config: Path | None
    dry_run: bool
    yes: bool
    verbose: int


# Command specification table: (name, panel, issue_number, help_text)
COMMANDS = [
    # Pipeline panel
    ("ingest", "Pipeline", 36, "Ingest photos from sources"),
    ("fingerprint", "Pipeline", 45, "Compute fingerprints for objects"),
    ("group", "Pipeline", 50, "Group similar photos together"),
    ("select", "Pipeline", 52, "Select photos for publication"),
    ("proxy", "Pipeline", 59, "Generate proxy files"),
    ("review", "Pipeline", 61, "Review and approve operations"),
    ("publish", "Pipeline", 68, "Publish photos to Immich"),
    ("backup", "Pipeline", 77, "Backup vault to storage"),
    ("sync", "Pipeline", 81, "Sync vault state"),
    # Safety panel
    ("verify", "Safety", 69, "Verify vault integrity"),
    ("retire", "Safety", 70, "Retire photos from archive"),
    ("scrub", "Safety", 78, "Scrub sensitive data"),
    ("restore", "Safety", 79, "Restore from backup"),
    # Operations panel
    ("status", "Operations", 84, "Show vault status"),
    ("rebuild", "Operations", 21, "Rebuild catalog from archive"),
    ("report", "Operations", 60, "Generate vault report"),
    ("config", "Operations", 17, "Manage vault configuration"),
]


def _stub_command(name: str, issue_number: int) -> None:
    """Raise NotImplementedError for a stub command."""
    msg = f"vault: `{name}` is not implemented yet\n       tracked in https://github.com/stephenkiers/PhotoLibrary/issues/{issue_number}"
    typer.echo(msg, err=True)
    raise typer.Exit(ExitCode.NOT_IMPLEMENTED)


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to vault configuration file"),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Run without making changes")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Assume yes for all prompts")] = False,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="Increase verbosity"),
    ] = 0,
) -> None:
    """Vault: photo library management CLI."""
    ctx.obj = GlobalOptions(config=config, dry_run=dry_run, yes=yes, verbose=verbose)


# Register all stub commands
def _make_command(name: str, panel: str, issue: int, help_text: str) -> None:
    """Factory function to create a command."""

    def command(ctx: typer.Context) -> None:
        opts: GlobalOptions = ctx.obj
        if name == "retire" and not opts.yes:
            typer.echo("retire: requires --yes flag", err=True)
            raise typer.Exit(1)
        _stub_command(name, issue)

    command.__doc__ = help_text
    app.command(name=name, rich_help_panel=panel, help=help_text)(command)


for name, panel, issue, help_text in COMMANDS:
    _make_command(name, panel, issue, help_text)
