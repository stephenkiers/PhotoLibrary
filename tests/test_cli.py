"""Tests for vault CLI."""

from typer.testing import CliRunner

from vault.cli import COMMANDS, app
from vault.errors import ExitCode

runner = CliRunner()


def test_command_surface() -> None:
    """Test that registered command names match the spec table.

    This is the deliberate AC #1 verification mechanism: parsing Rich's box-drawing
    output to confirm command registration.
    """
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

    expected_commands = {spec.name for spec in COMMANDS}

    # Extract command names from help output by looking for them between panel lines
    help_output = result.output
    registered_commands = set()

    # Split by panel markers and look for commands in each section
    for line in help_output.split("\n"):
        line_stripped = line.strip()
        # Look for lines that start with a command name followed by spaces
        for spec in COMMANDS:
            # Match command name followed by spaces and then description (with box chars)
            if line_stripped.startswith(spec.name + " ") or line_stripped.startswith(
                "│ " + spec.name + " "
            ):
                registered_commands.add(spec.name)

    assert registered_commands == expected_commands


def test_help_exits_zero() -> None:
    """Test that --help exits 0 and shows all command names."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

    help_output = result.output
    for spec in COMMANDS:
        assert spec.name in help_output


def test_stub_exits_nonzero() -> None:
    """Test that a stub command exits with code 3 and shows issue URL."""
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED

    output = result.output
    assert "ingest" in output
    assert "https://github.com/stephenkiers/PhotoLibrary/issues/36" in output


def test_bare_vault_shows_help() -> None:
    """Test that bare `vault` with no args shows help."""
    result = runner.invoke(app, [])
    # Should display help with command names visible
    assert "ingest" in result.output, "Should show at least one command name in help"


def test_all_commands_exit_with_issue_number() -> None:
    """Test that all 17 commands exit with code 3 and reference their issue numbers.

    Note: retire requires --yes before it can proceed to the stub exit.
    """
    for spec in COMMANDS:
        if spec.requires_confirmation:
            # Commands requiring confirmation need --yes flag
            result = runner.invoke(app, ["--yes", spec.name])
        else:
            result = runner.invoke(app, [spec.name])

        assert result.exit_code == ExitCode.NOT_IMPLEMENTED, (
            f"'{spec.name}' exit code: expected {ExitCode.NOT_IMPLEMENTED}, got {result.exit_code}"
        )
        assert str(spec.issue) in result.output, (
            f"'{spec.name}' output missing issue number {spec.issue}: {result.output}"
        )
        assert "github.com" in result.output, (
            f"'{spec.name}' output missing GitHub URL: {result.output}"
        )


def test_panel_groupings_in_help() -> None:
    """Test that help output shows correct panel groupings."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    help_output = result.output

    # Extract panel names from COMMANDS spec
    panels = set()
    for spec in COMMANDS:
        panels.add(spec.panel)

    # Verify each panel appears in help
    for panel in panels:
        assert panel in help_output, (
            f"Panel '{panel}' should appear in help output. Output: {help_output}"
        )


def _registered_panel(name: str) -> str | None:
    """Look up the rich_help_panel Typer actually registered a command under."""
    for command_info in app.registered_commands:
        if command_info.name == name:
            return command_info.rich_help_panel
    return None


def test_pipeline_commands_in_correct_panel() -> None:
    """Test that Pipeline commands are registered under the Pipeline panel."""
    pipeline_commands = [spec.name for spec in COMMANDS if spec.panel == "Pipeline"]
    for cmd in pipeline_commands:
        assert _registered_panel(cmd) == "Pipeline", (
            f"'{cmd}' should be registered under the Pipeline panel"
        )


def test_safety_commands_in_correct_panel() -> None:
    """Test that Safety commands are registered under the Safety panel."""
    safety_commands = [spec.name for spec in COMMANDS if spec.panel == "Safety"]
    for cmd in safety_commands:
        assert _registered_panel(cmd) == "Safety", (
            f"'{cmd}' should be registered under the Safety panel"
        )


def test_operations_commands_in_correct_panel() -> None:
    """Test that Operations commands are registered under the Operations panel."""
    ops_commands = [spec.name for spec in COMMANDS if spec.panel == "Operations"]
    for cmd in ops_commands:
        assert _registered_panel(cmd) == "Operations", (
            f"'{cmd}' should be registered under the Operations panel"
        )


def test_retire_with_yes_flag_bypasses_guard() -> None:
    """Test that retire --yes (as global flag) bypasses the guard and hits the stub exit."""
    result = runner.invoke(app, ["--yes", "retire"])
    # Should exit with NOT_IMPLEMENTED, not the "requires --yes" error
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "70" in result.output, "Should reference issue 70"


def test_retire_without_yes_flag_fails() -> None:
    """Test that retire without --yes exits with CONFIRMATION_REQUIRED error."""
    result = runner.invoke(app, ["retire"])
    assert result.exit_code == ExitCode.CONFIRMATION_REQUIRED


def test_config_global_flag() -> None:
    """Test that --config global flag is recognized."""
    result = runner.invoke(app, ["--config", "/path/to/config", "ingest"])
    # Should get past config parsing and hit the stub exit
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED


def test_dry_run_global_flag() -> None:
    """Test that --dry-run global flag is recognized."""
    result = runner.invoke(app, ["--dry-run", "ingest"])
    # Should get past dry-run parsing and hit the stub exit
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED


def test_verbose_flag_single() -> None:
    """Test that -v (single verbose) is recognized."""
    result = runner.invoke(app, ["-v", "ingest"])
    # Should get past verbose parsing and hit the stub exit
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED


def test_verbose_flag_multiple() -> None:
    """Test that -vvv (multiple verbose) is recognized."""
    result = runner.invoke(app, ["-vvv", "ingest"])
    # Should get past verbose parsing and hit the stub exit
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED


def test_verbose_long_form() -> None:
    """Test that --verbose is recognized."""
    result = runner.invoke(app, ["--verbose", "ingest"])
    # Should get past verbose parsing and hit the stub exit
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED


def test_yes_flag_long_form() -> None:
    """Test that --yes is recognized."""
    result = runner.invoke(app, ["--yes", "ingest"])
    # Should get past yes parsing and hit the stub exit
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED


def test_yes_flag_short_form() -> None:
    """Test that -y (short yes) is recognized."""
    result = runner.invoke(app, ["-y", "ingest"])
    # Should get past yes parsing and hit the stub exit
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED


def test_multiple_global_flags() -> None:
    """Test that multiple global flags can be combined."""
    result = runner.invoke(app, ["--dry-run", "-vv", "--config", "/path", "--yes", "ingest"])
    # Should get past all flag parsing and hit the stub exit
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED


def test_status_specific_exit_code() -> None:
    """Test that status command exits with code 3 for issue 84."""
    result = runner.invoke(app, ["status"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "84" in result.output


def test_rebuild_specific_exit_code() -> None:
    """Test that rebuild command exits with code 3 for issue 21."""
    result = runner.invoke(app, ["rebuild"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "21" in result.output


def test_report_specific_exit_code() -> None:
    """Test that report command exits with code 3 for issue 60."""
    result = runner.invoke(app, ["report"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "60" in result.output


def test_config_specific_exit_code() -> None:
    """Test that config command exits with code 3 for issue 17."""
    result = runner.invoke(app, ["config"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "17" in result.output


def test_stubs_write_to_output() -> None:
    """Test that stub commands write error messages to output (captured by CliRunner)."""
    result = runner.invoke(app, ["ingest"])
    # Check that the message is in the output
    assert result.output, "Stub should write to output"
    assert "ingest" in result.output.lower() or "36" in result.output
