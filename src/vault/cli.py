"""CLI for vault."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple

import typer

from vault.config import (
    Config,
    format_config_errors,
    format_preflight_errors,
    fs_preflight,
    load_config,
    secret_env_field_names,
)
from vault.errors import ExitCode, VaultConfigError

app = typer.Typer(no_args_is_help=True)


@dataclass(frozen=True)
class GlobalOptions:
    """Global options for the vault CLI."""

    config: Path
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
    # Default to ./vault.toml if not specified
    if config is None:
        config = Path("vault.toml")
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


def _load_config_or_exit(opts: GlobalOptions) -> Config:
    """Load config from the specified path, or exit with an error.

    Args:
        opts: Global options containing config path.

    Returns:
        Loaded and validated Config instance.

    Raises:
        typer.Exit: If config cannot be loaded.
    """
    try:
        return load_config(opts.config)
    except VaultConfigError as e:
        msg = format_config_errors(opts.config, e.errors)
        typer.echo(msg, err=True)
        raise typer.Exit(ExitCode.CONFIG_ERROR) from e
    except FileNotFoundError:
        msg = f"vault: config file not found: `{opts.config}`"
        typer.echo(msg, err=True)
        raise typer.Exit(ExitCode.CONFIG_ERROR) from None


# Create the config sub-app
config_app = typer.Typer(no_args_is_help=True, help="Manage vault configuration")


@config_app.command()
def show(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show the effective vault configuration with secrets redacted."""
    opts = _get_options(ctx)
    config = _load_config_or_exit(opts)

    if json_output:
        # Output as JSON with secrets redacted/annotated
        output = _format_json_output(config)
        typer.echo(output)
    else:
        # Human-readable output
        output = _format_config_output(config)
        typer.echo(output)

    raise typer.Exit(ExitCode.OK)


@config_app.command()
def validate(ctx: typer.Context) -> None:
    """Validate vault configuration and check filesystem preflight."""
    opts = _get_options(ctx)
    config = _load_config_or_exit(opts)

    # Run filesystem preflight
    problems = fs_preflight(config)
    if problems:
        msg = format_preflight_errors(opts.config, problems)
        typer.echo(msg, err=True)
        raise typer.Exit(ExitCode.CONFIG_ERROR)

    typer.echo(f"vault: config OK (`{opts.config}`)")
    raise typer.Exit(ExitCode.OK)


def _format_json_output(config: Config) -> str:
    """Format a Config object for JSON output with secrets redacted.

    Args:
        config: The Config instance to format.

    Returns:
        JSON string representation of the config.
    """
    config_dict = config.model_dump(mode="json")
    secret_fields = secret_env_field_names(config)

    # Helper to recursively update dict with resolved secret information
    def _annotate_secrets(obj: dict[str, Any]) -> None:
        for key, value in list(obj.items()):
            if key in secret_fields and isinstance(value, str):
                # Check if this env var was actually resolved
                if config.get_resolved_secret(value):
                    # Replace with annotation showing it's resolved and from which env var
                    obj[key] = f"<set from {value}>"

            elif isinstance(value, dict):
                _annotate_secrets(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        _annotate_secrets(item)

    _annotate_secrets(config_dict)
    return json.dumps(config_dict, indent=2)


def _format_config_output(config: Config) -> str:
    """Format a Config object for human-readable display."""
    lines: list[str] = []
    secret_fields = secret_env_field_names(config)

    lines.append(f"schema_version: {config.schema_version}")
    lines.append("")

    # Paths section
    lines.append("[paths]")
    lines.append(f"  archive: {config.paths.archive}")
    lines.append(f"  staging: {config.paths.staging}")
    if config.paths.proxies:
        lines.append(f"  proxies: {config.paths.proxies}")
    if config.paths.catalog:
        lines.append(f"  catalog: {config.paths.catalog}")
    lines.append("")

    # Sources section
    if config.sources:
        lines.append("[sources]")
        for source in config.sources:
            lines.append(f"  [[sources.{source.name}]]")
            lines.append(f"    kind: {source.kind}")
            lines.append(f"    path: {source.path}")
            if (
                "immich_api_key_env" in secret_fields
                and source.immich_api_key_env
                and config.get_resolved_secret(source.immich_api_key_env)
            ):
                # Only show "set from" if the env var was actually resolved
                lines.append(f"    immich_api_key_env: <set from {source.immich_api_key_env}>")
        lines.append("")

    # Thresholds section
    if config.thresholds:
        lines.append("[thresholds]")
        if config.thresholds.min_quality is not None:
            lines.append(f"  min_quality: {config.thresholds.min_quality}")
        if config.thresholds.max_age_days is not None:
            lines.append(f"  max_age_days: {config.thresholds.max_age_days}")
        lines.append("")

    # Proxy section
    if config.proxy:
        lines.append("[proxy]")
        if config.proxy.review:
            lines.append("  [proxy.review]")
            lines.append(f"    width: {config.proxy.review.width}")
            lines.append(f"    height: {config.proxy.review.height}")
            lines.append(f"    quality: {config.proxy.review.quality}")
        if config.proxy.publish:
            lines.append("  [proxy.publish]")
            lines.append(f"    width: {config.proxy.publish.width}")
            lines.append(f"    height: {config.proxy.publish.height}")
            lines.append(f"    quality: {config.proxy.publish.quality}")
        lines.append("")

    # Publish section
    if config.publish:
        lines.append("[publish]")
        if config.publish.immich_url:
            lines.append(f"  immich_url: {config.publish.immich_url}")
        if (
            "immich_api_key_env" in secret_fields
            and config.publish.immich_api_key_env
            and config.get_resolved_secret(config.publish.immich_api_key_env)
        ):
            # Only show "set from" if the env var was actually resolved
            lines.append(f"  immich_api_key_env: <set from {config.publish.immich_api_key_env}>")
        lines.append(f"  grace_days: {config.publish.grace_days}")
        lines.append(f"  shared_library_policy: {config.publish.shared_library_policy}")
        lines.append("")

    # Backup section
    if config.backup:
        lines.append("[backup]")
        if config.backup.targets:
            for target in config.backup.targets:
                lines.append(f"  [[backup.targets.{target.name}]]")
                lines.append(f"    kind: {target.kind}")
                lines.append(f"    destination: {target.destination}")
                if target.retention_days is not None:
                    lines.append(f"    retention_days: {target.retention_days}")
        lines.append("")

    return "\n".join(lines)


# Register config sub-app (replaces stub)
app.add_typer(config_app, name="config", rich_help_panel="Operations")


# Register all other stub commands
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


# Register all stub commands except config (which is now a sub-app)
for spec in COMMANDS:
    if spec.name != "config":
        _make_command(spec)
