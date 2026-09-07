"""CLI for vault."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, NamedTuple

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


class CommandSpec(NamedTuple):
    """Command specification."""

    name: str
    panel: Literal["Pipeline", "Safety", "Operations"]
    issue: int
    help_text: str
    requires_confirmation: bool = False


# Command specification table
COMMANDS = [
    # Pipeline panel
    CommandSpec("ingest", "Pipeline", 36, "Ingest photos from sources"),
    CommandSpec("fingerprint", "Pipeline", 45, "Compute fingerprints for objects"),
    CommandSpec("group", "Pipeline", 50, "Group similar photos together"),
    CommandSpec("select", "Pipeline", 52, "Select photos for publication"),
    CommandSpec("proxy", "Pipeline", 59, "Generate proxy files"),
    CommandSpec("review", "Pipeline", 61, "Review and approve operations"),
    CommandSpec("publish", "Pipeline", 68, "Publish photos to Immich"),
    CommandSpec("backup", "Pipeline", 77, "Backup vault to storage"),
    CommandSpec("sync", "Pipeline", 81, "Sync vault state"),
    # Safety panel
    CommandSpec("verify", "Safety", 69, "Verify vault integrity"),
    CommandSpec("retire", "Safety", 70, "Retire photos from archive", requires_confirmation=True),
    CommandSpec("scrub", "Safety", 78, "Scrub sensitive data"),
    CommandSpec("restore", "Safety", 79, "Restore from backup"),
    # Operations panel
    CommandSpec("status", "Operations", 84, "Show vault status"),
    CommandSpec("rebuild", "Operations", 21, "Rebuild catalog from archive"),
    CommandSpec("report", "Operations", 60, "Generate vault report"),
    CommandSpec("config", "Operations", 17, "Manage vault configuration"),
]


def _stub_command(name: str, issue_number: int) -> None:
    """Exit with NOT_IMPLEMENTED for a stub command.

    Raises typer.Exit with ExitCode.NOT_IMPLEMENTED.
    """
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


def _get_options(ctx: typer.Context) -> GlobalOptions:
    """Get and validate the global options from context.

    Raises:
        AssertionError: If ctx.obj is not an instance of GlobalOptions.
    """
    assert isinstance(ctx.obj, GlobalOptions), (
        f"Expected ctx.obj to be GlobalOptions, got {type(ctx.obj)}"
    )
    return ctx.obj


# Register all stub commands
def _make_command(spec: CommandSpec) -> None:
    """Factory function to create a command from a CommandSpec."""

    def command(ctx: typer.Context) -> None:
        opts = _get_options(ctx)

        # This guard predates full implementation of the command it protects: it's a
        # safety gate bolted onto a stub, not a sign the stub is half-implemented.
        # retire alone is gated behind --yes because it's destructive once implemented
        # (see M0-01: no unattended runs against Photos).
        if spec.requires_confirmation and not opts.yes:
            msg = f"vault: `{spec.name}` requires --yes to proceed"
            typer.echo(msg, err=True)
            raise typer.Exit(ExitCode.CONFIRMATION_REQUIRED)

        _stub_command(spec.name, spec.issue)

    app.command(name=spec.name, rich_help_panel=spec.panel, help=spec.help_text)(command)


for spec in COMMANDS:
    _make_command(spec)
