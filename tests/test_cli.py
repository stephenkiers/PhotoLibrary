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


def test_bare_vault_shows_help() -> None:
    """Test that bare `vault` with no args shows help."""
    result = runner.invoke(app, [])
    # Should display help, even if exit code is non-zero
    assert "Usage" in result.output or "Commands" in result.output


def test_all_commands_exit_with_issue_number() -> None:
    """Test that all 17 commands exit with code 3 and reference their issue numbers.

    Note: retire is special and requires --yes before it can proceed to the stub exit.
    """
    for name, _panel, issue_num, _ in COMMANDS:
        if name == "retire":
            # retire requires --yes flag, test separately
            result = runner.invoke(app, ["--yes", name])
        else:
            result = runner.invoke(app, [name])

        assert result.exit_code == ExitCode.NOT_IMPLEMENTED, (
            f"'{name}' exit code: expected {ExitCode.NOT_IMPLEMENTED}, got {result.exit_code}"
        )
        assert str(issue_num) in result.output, (
            f"'{name}' output missing issue number {issue_num}: {result.output}"
        )
        assert "github.com" in result.output, f"'{name}' output missing GitHub URL: {result.output}"


def test_panel_groupings_in_help() -> None:
    """Test that help output shows correct panel groupings."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    help_output = result.output

    # Extract panel names from COMMANDS spec
    panels = set()
    for _, panel, _, _ in COMMANDS:
        panels.add(panel)

    # Verify each panel appears in help
    for panel in panels:
        assert panel in help_output, (
            f"Panel '{panel}' should appear in help output. Output: {help_output}"
        )


def test_pipeline_commands_in_correct_panel() -> None:
    """Test that Pipeline commands are listed in help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    help_output = result.output

    pipeline_commands = [name for name, panel, _, _ in COMMANDS if panel == "Pipeline"]
    for cmd in pipeline_commands:
        assert cmd in help_output, f"Pipeline command '{cmd}' should be in help"


def test_safety_commands_in_correct_panel() -> None:
    """Test that Safety commands are listed in help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    help_output = result.output

    safety_commands = [name for name, panel, _, _ in COMMANDS if panel == "Safety"]
    for cmd in safety_commands:
        assert cmd in help_output, f"Safety command '{cmd}' should be in help"


def test_operations_commands_in_correct_panel() -> None:
    """Test that Operations commands are listed in help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    help_output = result.output

    ops_commands = [name for name, panel, _, _ in COMMANDS if panel == "Operations"]
    for cmd in ops_commands:
        assert cmd in help_output, f"Operations command '{cmd}' should be in help"


def test_retire_with_yes_flag_bypasses_guard() -> None:
    """Test that retire --yes (as global flag) bypasses the guard and hits the stub exit."""
    result = runner.invoke(app, ["--yes", "retire"])
    # Should exit with NOT_IMPLEMENTED, not the "requires --yes" error
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "70" in result.output, "Should reference issue 70"


def test_retire_without_yes_flag_fails() -> None:
    """Test that retire without --yes exits with error before stub."""
    result = runner.invoke(app, ["retire"])
    assert result.exit_code != ExitCode.NOT_IMPLEMENTED
    assert result.exit_code != 0


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


def test_ingest_specific_exit_code() -> None:
    """Test that ingest command specifically exits with code 3 for issue 36."""
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "36" in result.output


def test_fingerprint_specific_exit_code() -> None:
    """Test that fingerprint command exits with code 3 for issue 45."""
    result = runner.invoke(app, ["fingerprint"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "45" in result.output


def test_group_specific_exit_code() -> None:
    """Test that group command exits with code 3 for issue 50."""
    result = runner.invoke(app, ["group"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "50" in result.output


def test_select_specific_exit_code() -> None:
    """Test that select command exits with code 3 for issue 52."""
    result = runner.invoke(app, ["select"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "52" in result.output


def test_proxy_specific_exit_code() -> None:
    """Test that proxy command exits with code 3 for issue 59."""
    result = runner.invoke(app, ["proxy"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "59" in result.output


def test_review_specific_exit_code() -> None:
    """Test that review command exits with code 3 for issue 61."""
    result = runner.invoke(app, ["review"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "61" in result.output


def test_publish_specific_exit_code() -> None:
    """Test that publish command exits with code 3 for issue 68."""
    result = runner.invoke(app, ["publish"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "68" in result.output


def test_backup_specific_exit_code() -> None:
    """Test that backup command exits with code 3 for issue 77."""
    result = runner.invoke(app, ["backup"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "77" in result.output


def test_sync_specific_exit_code() -> None:
    """Test that sync command exits with code 3 for issue 81."""
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "81" in result.output


def test_verify_specific_exit_code() -> None:
    """Test that verify command exits with code 3 for issue 69."""
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "69" in result.output


def test_scrub_specific_exit_code() -> None:
    """Test that scrub command exits with code 3 for issue 78."""
    result = runner.invoke(app, ["scrub"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "78" in result.output


def test_restore_specific_exit_code() -> None:
    """Test that restore command exits with code 3 for issue 79."""
    result = runner.invoke(app, ["restore"])
    assert result.exit_code == ExitCode.NOT_IMPLEMENTED
    assert "79" in result.output


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
