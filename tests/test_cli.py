"""Tests for vault CLI."""

from typer.testing import CliRunner

from vault.cli import COMMANDS, app
from vault.errors import ExitCode

runner = CliRunner()


def test_command_surface() -> None:
    """Test that registered command names match the spec table."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

    expected_commands = {name for name, _, _, _ in COMMANDS}

    # Extract command names from help output by looking for them between panel lines
    help_output = result.output
    registered_commands = set()

    # Split by panel markers and look for commands in each section
    for line in help_output.split("\n"):
        line_stripped = line.strip()
        # Look for lines that start with a command name followed by spaces
        for name, _, _, _ in COMMANDS:
            # Match command name followed by spaces and then description (with box chars)
            if line_stripped.startswith(name + " ") or line_stripped.startswith("│ " + name + " "):
                registered_commands.add(name)

    assert registered_commands == expected_commands


def test_help_exits_zero() -> None:
    """Test that --help exits 0 and shows all command names."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

    help_output = result.output
    for name, _, _, _ in COMMANDS:
        assert name in help_output


def test_stub_exits_nonzero() -> None:
    """Test that a stub command exits with code 3 and shows issue URL."""
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED

    output = result.output
    assert "ingest" in output
    assert "https://github.com/stephenkiers/PhotoLibrary/issues/36" in output


def test_retire_requires_yes() -> None:
    """Test that retire without --yes fails."""
    result = runner.invoke(app, ["retire"])
    assert result.exit_code != 0
    assert result.exit_code != ExitCode.NOT_IMPLEMENTED
