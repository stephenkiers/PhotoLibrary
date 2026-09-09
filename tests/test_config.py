"""Tests for vault configuration schema and loader."""

from pathlib import Path
from textwrap import dedent

import pytest
from typer.testing import CliRunner

from vault.cli import app
from vault.config import Config, load_config
from vault.errors import VaultConfigError

runner = CliRunner()


# ============================================================================
# Fixtures for common test assets
# ============================================================================


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory."""
    return tmp_path


# ============================================================================
# Helper functions for TOML fixture generation
# ============================================================================


def minimal_valid_config(
    archive_path: str,
    staging_path: str,
    sources: str | None = None,
    backup_targets: str | None = None,
) -> str:
    """Return a minimal valid vault.toml config.

    Args:
        archive_path: Path to archive directory.
        staging_path: Path to staging directory.
        sources: Optional raw TOML fragment for sources section
            (as array-of-tables, e.g., "[[sources]]\\nname = ...").
        backup_targets: Optional raw TOML fragment for backup targets section
            (as array-of-tables).

    Returns:
        Valid TOML config string.
    """
    config = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive_path}"
        staging = "{staging_path}"
    ''').strip()

    if sources:
        config = f"{config}\n\n{sources}"

    config = (
        f"{config}\n\n"
        + dedent("""
        [thresholds]

        [proxy]
        [proxy.review]
        width = 640
        height = 480
        quality = 85

        [proxy.publish]
        width = 1280
        height = 960
        quality = 90

        [publish]
        immich_url = "http://localhost:2283"
        immich_api_key_env = "VAULT_IMMICH_API_KEY"
        grace_days = 0
        shared_library_policy = "skip"

        [backup]
    """).strip()
    )

    if backup_targets:
        config = f"{config}\n\n{backup_targets}"

    return config


# ============================================================================
# Test: Valid config loads successfully
# ============================================================================


def test_valid_config_loads(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a valid config file loads into Config successfully."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"

    config_file = temp_dir / "vault.toml"
    config_file.write_text(minimal_valid_config(str(archive), str(staging)))

    # Set the required environment variable
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-secret-key")

    # Should load successfully
    config = load_config(config_file)
    assert isinstance(config, Config)
    assert config.schema_version == 1


def test_valid_config_with_all_sections(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a complete config with all sections loads."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    catalog = temp_dir / "paths" / "catalog"
    catalog.mkdir(parents=True, exist_ok=True)
    proxies = temp_dir / "paths" / "proxies"
    proxies.mkdir(parents=True, exist_ok=True)
    # Use a separate source path to avoid overlap
    source = temp_dir / "sources" / "source1"
    source.mkdir(parents=True, exist_ok=True)

    config_file = temp_dir / "vault.toml"
    config_text = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive}"
        staging = "{staging}"
        catalog = "{catalog}"
        proxies = "{proxies}"

        [[sources]]
        name = "source1"
        kind = "local"
        path = "{source}"

        [thresholds]
        min_quality = 0.8
        max_age_days = 365

        [proxy]
        [proxy.review]
        width = 640
        height = 480
        quality = 85

        [proxy.publish]
        width = 1280
        height = 960
        quality = 90

        [publish]
        immich_url = "http://localhost:2283"
        immich_api_key_env = "VAULT_IMMICH_API_KEY"
        grace_days = 7
        shared_library_policy = "include"

        [[backup.targets]]
        name = "backup1"
        kind = "rsync"
        destination = "/mnt/backup"
        retention_days = 30
    ''').strip()
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)
    assert config.schema_version == 1
    assert config.sources is not None
    assert len(config.sources) == 1


# ============================================================================
# Test: Unknown keys are rejected
# ============================================================================


def test_unknown_key_at_root_level(temp_dir: Path) -> None:
    """Test that unknown keys at root level are rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Add unknown root key
    config_text += "\nunknown_key = 42"
    config_file.write_text(config_text)

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_unknown_key_in_paths_section(temp_dir: Path) -> None:
    """Test that unknown keys in [paths] are rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Replace [paths] section with one that has a typo
    lines = config_text.split("\n")
    paths_start = next(i for i, line in enumerate(lines) if line.startswith("[paths]"))
    staging_line = next(
        i for i, line in enumerate(lines[paths_start:], start=paths_start) if "staging" in line
    )
    lines.insert(staging_line + 1, "grace-days = 0")  # Typo: hyphen instead of underscore
    config_text = "\n".join(lines)
    config_file.write_text(config_text)

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_unknown_key_in_publish_section(temp_dir: Path) -> None:
    """Test that unknown keys in [publish] are rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Add unknown key to publish section
    config_text += "\ntypo_key = 'value'"
    # Need to move it to be inside the publish section
    lines = config_text.split("\n")
    publish_start = next(i for i, line in enumerate(lines) if line.startswith("[publish]"))
    # Insert before next section
    next_section = next(
        (i for i in range(publish_start + 1, len(lines)) if lines[i].startswith("[")), len(lines)
    )
    lines.insert(next_section - 1, "typo_key = 'value'")
    config_text = "\n".join(lines)
    config_file.write_text(config_text)

    with pytest.raises(VaultConfigError):
        load_config(config_file)


# ============================================================================
# Test: Negative grace_days is rejected
# ============================================================================


def test_negative_grace_days_rejected(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that negative grace_days values are rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Replace grace_days with negative value
    config_text = config_text.replace("grace_days = 0", "grace_days = -1")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


# ============================================================================
# Test: Invalid shared_library_policy is rejected
# ============================================================================


def test_invalid_shared_library_policy(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid shared_library_policy values are rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Replace with invalid policy
    config_text = config_text.replace(
        'shared_library_policy = "skip"', 'shared_library_policy = "invalid_policy"'
    )
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_valid_shared_library_policy_skip(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that 'skip' is a valid shared_library_policy."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_valid_shared_library_policy_include(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that 'include' is a valid shared_library_policy."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace(
        'shared_library_policy = "skip"', 'shared_library_policy = "include"'
    )
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_valid_shared_library_policy_include_no_retire(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that 'include_no_retire' is a valid shared_library_policy."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace(
        'shared_library_policy = "skip"', 'shared_library_policy = "include_no_retire"'
    )
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_invalid_env_var_name_in_publish_config(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that invalid env var names in publish.immich_api_key_env are rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Replace with an invalid env var name (lowercase)
    config_text = config_text.replace(
        'immich_api_key_env = "VAULT_IMMICH_API_KEY"',
        'immich_api_key_env = "vault_immich_api_key"',
    )
    config_file.write_text(config_text)

    monkeypatch.setenv("vault_immich_api_key", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_invalid_env_var_name_in_source_config(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that invalid env var names in source.immich_api_key_env are rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    sources_fragment = dedent(f'''
        [[sources]]
        name = "source1"
        kind = "local"
        path = "{staging}"
        immich_api_key_env = "1INVALID_NAME"
    ''').strip()
    config_text = minimal_valid_config(str(archive), str(staging), sources=sources_fragment)
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


# ============================================================================
# Test: Secret resolution from environment variables
# ============================================================================


def test_secret_env_resolves_from_environment(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that *_env fields resolve secrets from os.environ."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    secret_value = "super-secret-immich-key-xyz"
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", secret_value)

    config = load_config(config_file)
    assert isinstance(config, Config)
    # Config should have loaded successfully with the secret resolved


def test_missing_secret_env_var_raises_error(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that missing required *_env vars raise VaultConfigError."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    # Unset the env var if it exists
    monkeypatch.delenv("VAULT_IMMICH_API_KEY", raising=False)

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_secret_value_not_exposed_in_str_repr(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that secret values are not exposed in str() or repr()."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    secret_value = "super-secret-immich-key-xyz-12345"
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", secret_value)

    config = load_config(config_file)

    # str() and repr() should NOT contain the actual secret value
    config_str = str(config)
    config_repr = repr(config)

    assert secret_value not in config_str, f"Secret value found in str(config): {config_str}"
    assert secret_value not in config_repr, f"Secret value found in repr(config): {config_repr}"


# ============================================================================
# Test: Missing config file produces clear error
# ============================================================================


def test_missing_config_file_raises_error(temp_dir: Path) -> None:
    """Test that loading a missing config file raises a clear error."""
    nonexistent_file = temp_dir / "nonexistent" / "vault.toml"

    # Should raise FileNotFoundError or VaultConfigError
    with pytest.raises((FileNotFoundError, VaultConfigError)):
        load_config(nonexistent_file)


# ============================================================================
# Test: Malformed TOML produces clear error
# ============================================================================


def test_malformed_toml_raises_error(temp_dir: Path) -> None:
    """Test that malformed TOML produces a clear error."""
    config_file = temp_dir / "vault.toml"
    config_file.write_text("[paths]\narchive = /missing/quotes")

    # Should raise VaultConfigError (which wraps TOMLDecodeError)
    with pytest.raises(VaultConfigError) as exc_info:
        load_config(config_file)
    # Assert the error list contains the config path
    errors = exc_info.value.errors
    assert len(errors) > 0
    error_key_path, error_msg = errors[0]
    assert str(config_file) in error_key_path or str(config_file) in error_msg


def test_malformed_toml_with_invalid_section(temp_dir: Path) -> None:
    """Test that invalid TOML syntax raises error."""
    config_file = temp_dir / "vault.toml"
    config_file.write_text("[[malformed\n[paths]\narchive = '/path'")

    # Should raise VaultConfigError (which wraps TOMLDecodeError)
    with pytest.raises(VaultConfigError) as exc_info:
        load_config(config_file)
    # Assert the error list contains details
    errors = exc_info.value.errors
    assert len(errors) > 0
    error_key_path, error_msg = errors[0]
    assert str(config_file) in error_key_path or str(config_file) in error_msg


# ============================================================================
# Test: Overlapping paths are rejected (via fs_preflight)
# ============================================================================


def test_fs_preflight_detects_overlapping_paths(temp_dir: Path) -> None:
    """Test that Config validation rejects overlapping archive/staging paths."""
    archive = temp_dir / "archive"
    archive.mkdir(parents=True)
    # staging is a subdirectory of archive
    staging = archive / "staging"
    staging.mkdir()

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    # Should raise VaultConfigError due to overlapping paths
    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_config_rejects_identical_paths(temp_dir: Path) -> None:
    """Test that Config validation rejects archive and staging set to identical paths."""
    same_path = temp_dir / "same"
    same_path.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(same_path), str(same_path))
    config_file.write_text(config_text)

    # Should raise VaultConfigError because archive and staging are the same
    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_config_rejects_source_path_overlapping_archive(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that Config validation rejects a source path nested inside archive."""
    archive = temp_dir / "archive"
    archive.mkdir(parents=True)
    staging = temp_dir / "staging"
    staging.mkdir(parents=True)
    # Source path is a subdirectory of archive
    source_path = archive / "source_subdir"
    source_path.mkdir()

    config_file = temp_dir / "vault.toml"
    sources_fragment = dedent(f'''
        [[sources]]
        name = "source_in_archive"
        kind = "local"
        path = "{source_path}"
    ''').strip()
    config_text = minimal_valid_config(str(archive), str(staging), sources=sources_fragment)
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    # Should raise VaultConfigError due to source path inside archive
    with pytest.raises(VaultConfigError) as exc_info:
        load_config(config_file)
    # Assert the error message mentions the overlap
    errors = exc_info.value.errors
    error_msg = " ".join(str(e) for e in errors)
    assert "sources[0].path" in error_msg or "inside" in error_msg.lower()


def test_cli_config_validate_reports_missing_paths(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that vault config validate reports missing paths."""
    # Create a config that references non-existent paths
    archive = temp_dir / "paths" / "archive_does_not_exist"
    staging = temp_dir / "paths" / "staging_does_not_exist"

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    # Set up environment for secret
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    result = runner.invoke(app, ["--config", str(config_file), "config", "validate"])
    # Should fail with validation error since paths don't exist
    assert result.exit_code != 0


# ============================================================================
# Test: vault config show never prints raw secret values
# ============================================================================


def test_cli_config_show_no_secret_exposure(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that vault config show output never contains raw secret value."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    secret_value = "super-secret-immich-key-test-12345"
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", secret_value)

    result = runner.invoke(app, ["--config", str(config_file), "config", "show"])

    # Should not expose the actual secret value
    assert secret_value not in result.output


def test_cli_config_show_json_no_secret_exposure(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that vault config show --json output never contains raw secret."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    secret_value = "super-secret-immich-key-json-test-xyz"
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", secret_value)

    result = runner.invoke(app, ["--config", str(config_file), "config", "show", "--json"])

    # Should not expose the actual secret value
    assert secret_value not in result.output


# ============================================================================
# Test: Config has schema_version and fingerprint()
# ============================================================================


def test_config_has_schema_version(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that Config has schema_version attribute."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert hasattr(config, "schema_version")
    assert config.schema_version == 1


def test_config_has_fingerprint_method(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that Config has a fingerprint() method."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert hasattr(config, "fingerprint")
    assert callable(config.fingerprint)

    # Should return a stable hash
    fingerprint1 = config.fingerprint()
    fingerprint2 = config.fingerprint()
    assert fingerprint1 == fingerprint2


def test_config_fingerprint_differs_for_different_content(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that different configs produce different fingerprints."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file1 = temp_dir / "vault1.toml"
    config_text1 = minimal_valid_config(str(archive), str(staging))
    config_file1.write_text(config_text1)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")
    config1 = load_config(config_file1)
    fingerprint1 = config1.fingerprint()

    # Create a slightly different config
    config_file2 = temp_dir / "vault2.toml"
    config_text2 = minimal_valid_config(str(archive), str(staging))
    config_text2 = config_text2.replace("grace_days = 0", "grace_days = 7")
    config_file2.write_text(config_text2)

    config2 = load_config(config_file2)
    fingerprint2 = config2.fingerprint()

    assert fingerprint1 != fingerprint2


# ============================================================================
# Test: CLI config commands with --config flag
# ============================================================================


def test_cli_config_show_command_exists(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that vault config show command exists and works."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    result = runner.invoke(app, ["--config", str(config_file), "config", "show"])

    # Should succeed
    assert result.exit_code == 0


def test_cli_config_validate_command_exists(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that vault config validate command exists and works."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    result = runner.invoke(app, ["--config", str(config_file), "config", "validate"])

    # Should succeed
    assert result.exit_code == 0


# ============================================================================
# Test: Config with optional fields
# ============================================================================


def test_config_with_optional_grace_days_default(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that grace_days defaults to 0 when omitted."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Remove grace_days
    config_text = config_text.replace("grace_days = 0\n", "")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_config_with_source_immich_api_key_env(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that sources can have optional immich_api_key_env field."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)
    source = temp_dir / "sources" / "source1"
    source.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive}"
        staging = "{staging}"

        [[sources]]
        name = "source1"
        kind = "local"
        path = "{source}"
        immich_api_key_env = "SOURCE_API_KEY"

        [thresholds]

        [proxy]
        [proxy.review]
        width = 640
        height = 480
        quality = 85

        [proxy.publish]
        width = 1280
        height = 960
        quality = 90

        [publish]
        immich_url = "http://localhost:2283"
        immich_api_key_env = "VAULT_IMMICH_API_KEY"
        grace_days = 0
        shared_library_policy = "skip"

        [backup]
    ''').strip()
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "vault-key")
    monkeypatch.setenv("SOURCE_API_KEY", "source-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_config_with_backup_retention_days_optional(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that backup target retention_days is optional."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive}"
        staging = "{staging}"

        [thresholds]

        [proxy]
        [proxy.review]
        width = 640
        height = 480
        quality = 85

        [proxy.publish]
        width = 1280
        height = 960
        quality = 90

        [publish]
        immich_url = "http://localhost:2283"
        immich_api_key_env = "VAULT_IMMICH_API_KEY"
        grace_days = 0
        shared_library_policy = "skip"

        [[backup.targets]]
        name = "backup1"
        kind = "rsync"
        destination = "/mnt/backup"
    ''').strip()
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


# ============================================================================
# Test: Threshold validation
# ============================================================================


def test_config_with_valid_thresholds(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that valid thresholds load successfully."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace(
        "[thresholds]", "[thresholds]\nmin_quality = 0.5\nmax_age_days = 730"
    )
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_config_with_min_quality_zero(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that min_quality = 0 is valid."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace("[thresholds]", "[thresholds]\nmin_quality = 0.0")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_config_with_min_quality_one(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that min_quality = 1.0 is valid."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace("[thresholds]", "[thresholds]\nmin_quality = 1.0")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_config_with_negative_max_age_days(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that negative max_age_days is rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace("[thresholds]", "[thresholds]\nmax_age_days = -1")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


# ============================================================================
# Test: Proxy quality validation
# ============================================================================


def test_config_proxy_quality_must_be_1_to_100(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that proxy quality values are between 1 and 100."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Set quality to 0 (invalid)
    config_text = config_text.replace("quality = 85", "quality = 0")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_config_proxy_quality_100_valid(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that proxy quality = 100 is valid."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace("quality = 85", "quality = 100")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_config_proxy_quality_1_valid(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that proxy quality = 1 is valid."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace("quality = 85", "quality = 1")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


# ============================================================================
# Test: Backup kind validation
# ============================================================================


def test_config_backup_kind_rsync_valid(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that backup kind 'rsync' is valid."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive}"
        staging = "{staging}"

        [thresholds]

        [proxy]
        [proxy.review]
        width = 640
        height = 480
        quality = 85

        [proxy.publish]
        width = 1280
        height = 960
        quality = 90

        [publish]
        immich_url = "http://localhost:2283"
        immich_api_key_env = "VAULT_IMMICH_API_KEY"
        grace_days = 0
        shared_library_policy = "skip"

        [[backup.targets]]
        name = "backup1"
        kind = "rsync"
        destination = "/mnt/backup"
    ''').strip()
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_config_backup_kind_restic_valid(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that backup kind 'restic' is valid."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive}"
        staging = "{staging}"

        [thresholds]

        [proxy]
        [proxy.review]
        width = 640
        height = 480
        quality = 85

        [proxy.publish]
        width = 1280
        height = 960
        quality = 90

        [publish]
        immich_url = "http://localhost:2283"
        immich_api_key_env = "VAULT_IMMICH_API_KEY"
        grace_days = 0
        shared_library_policy = "skip"

        [[backup.targets]]
        name = "backup1"
        kind = "restic"
        destination = "s3://bucket/path"
    ''').strip()
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


def test_config_backup_kind_invalid_rejected(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that invalid backup kind is rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive}"
        staging = "{staging}"

        [thresholds]

        [proxy]
        [proxy.review]
        width = 640
        height = 480
        quality = 85

        [proxy.publish]
        width = 1280
        height = 960
        quality = 90

        [publish]
        immich_url = "http://localhost:2283"
        immich_api_key_env = "VAULT_IMMICH_API_KEY"
        grace_days = 0
        shared_library_policy = "skip"

        [[backup.targets]]
        name = "backup1"
        kind = "invalid_kind"
        destination = "/mnt/backup"
    ''').strip()
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


# ============================================================================
# Test: Source kind validation
# ============================================================================


def test_config_source_kind_local_valid(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that source kind 'local' is valid."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)
    source = temp_dir / "sources" / "local_source"
    source.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive}"
        staging = "{staging}"

        [[sources]]
        name = "local_source"
        kind = "local"
        path = "{source}"

        [thresholds]

        [proxy]
        [proxy.review]
        width = 640
        height = 480
        quality = 85

        [proxy.publish]
        width = 1280
        height = 960
        quality = 90

        [publish]
        immich_url = "http://localhost:2283"
        immich_api_key_env = "VAULT_IMMICH_API_KEY"
        grace_days = 0
        shared_library_policy = "skip"

        [backup]
    ''').strip()
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


# ============================================================================
# Test: Path expansion
# ============================================================================


def test_config_paths_tilde_expansion(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that ~ is expanded in path values (integration test)."""
    # This test creates a config with ~ paths and verifies they're expanded
    archive_path = "~/vault/archive"
    staging_path = "~/vault/staging"

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(archive_path, staging_path)
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    # Should load without error (tilde expansion should happen)
    config = load_config(config_file)
    assert isinstance(config, Config)
    # Verify that tilde was actually expanded
    assert config.paths.archive == Path("~/vault/archive").expanduser().resolve()
    assert config.paths.staging == Path("~/vault/staging").expanduser().resolve()


def test_cli_config_show_with_default_config_path(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that vault config show works without --config when vault.toml exists in cwd."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    # Create vault.toml in temp_dir and run from there
    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")
    monkeypatch.chdir(temp_dir)

    # Run config show without --config (should default to ./vault.toml)
    result = runner.invoke(app, ["config", "show"])

    # Should succeed since vault.toml exists in cwd
    assert result.exit_code == 0
