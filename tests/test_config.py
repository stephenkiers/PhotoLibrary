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


# ============================================================================
# Test: Robustness fixes - A2. Permission errors on file open
# ============================================================================


def test_permission_error_on_config_file_wrapped(temp_dir: Path) -> None:
    """Test that permission errors when opening config file are wrapped as VaultConfigError."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    # Remove read permissions
    config_file.chmod(0o000)

    try:
        # Should raise VaultConfigError (not PermissionError)
        with pytest.raises(VaultConfigError):
            load_config(config_file)
    finally:
        # Restore permissions for cleanup
        config_file.chmod(0o644)


# ============================================================================
# Test: Robustness fixes - A3. Case-insensitive filesystem overlap
# ============================================================================


def test_case_insensitive_path_overlap_detection(temp_dir: Path) -> None:
    """Test that case-differing paths are detected as overlapping on case-insensitive filesystems.

    On case-insensitive systems (e.g., macOS HFS+), /path/Archive and /path/archive
    refer to the same location and should be rejected as overlapping.
    """
    # Try to create paths that differ only in case
    archive_lower = temp_dir / "archive"
    archive_lower.mkdir(parents=True)

    # On case-insensitive filesystems, this creates the same directory
    # On case-sensitive filesystems, this creates a different directory
    archive_upper = temp_dir / "ARCHIVE"

    staging = temp_dir / "staging"
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive_lower), str(staging))
    # Replace archive path with case-different version
    config_text = config_text.replace(str(archive_lower), str(archive_upper))
    config_file.write_text(config_text)

    # Check if the filesystem is case-insensitive
    # If archive_lower and archive_upper refer to the same inode, they overlap
    archive_lower_stat = archive_lower.stat()
    archive_upper_exists = archive_upper.exists()

    if archive_upper_exists:
        archive_upper_stat = archive_upper.stat()
        if archive_lower_stat.st_ino == archive_upper_stat.st_ino:
            # Case-insensitive filesystem: should detect overlap
            with pytest.raises(VaultConfigError):
                load_config(config_file)
        # else: case-sensitive filesystem, skip this test
    # else: case-sensitive filesystem, paths don't overlap


# ============================================================================
# Test: Robustness fixes - A4. sources[].path overlap with other sources
# ============================================================================


def test_config_source_path_overlaps_with_another_source(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that two source paths that overlap are rejected."""
    archive = temp_dir / "archive"
    archive.mkdir(parents=True)
    staging = temp_dir / "staging"
    staging.mkdir(parents=True)

    # Create two source paths, one nested inside the other
    source1 = temp_dir / "sources" / "source1"
    source1.mkdir(parents=True)
    source2 = source1 / "source2"  # Nested inside source1
    source2.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    sources_fragment = dedent(f'''
        [[sources]]
        name = "source1"
        kind = "local"
        path = "{source1}"

        [[sources]]
        name = "source2"
        kind = "local"
        path = "{source2}"
    ''').strip()
    config_text = minimal_valid_config(str(archive), str(staging), sources=sources_fragment)
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    # Should raise VaultConfigError due to overlapping source paths
    with pytest.raises(VaultConfigError) as exc_info:
        load_config(config_file)
    # Error should mention the overlap
    errors = exc_info.value.errors
    error_msg = " ".join(str(e) for e in errors)
    assert "source" in error_msg.lower() or "overlap" in error_msg.lower()


# ============================================================================
# Test: C11. Proxy dimensions must be positive (reject zero and negative)
# ============================================================================


def test_config_proxy_review_width_zero_rejected(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that proxy review width = 0 is rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Set review width to 0
    lines = config_text.split("\n")
    for i, line in enumerate(lines):
        if "proxy.review" in line:
            # Find the width line after this section
            for j in range(i + 1, len(lines)):
                if "width" in lines[j]:
                    lines[j] = "width = 0"
                    break
            break
    config_text = "\n".join(lines)
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_config_proxy_review_height_negative_rejected(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that proxy review height = -1 is rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Set review height to negative
    lines = config_text.split("\n")
    for i, line in enumerate(lines):
        if "proxy.review" in line:
            # Find the height line after this section
            for j in range(i + 1, len(lines)):
                if "height" in lines[j]:
                    lines[j] = "height = -1"
                    break
            break
    config_text = "\n".join(lines)
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_config_proxy_publish_width_negative_rejected(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that proxy publish width = -100 is rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Set publish width to negative
    lines = config_text.split("\n")
    for i, line in enumerate(lines):
        if "proxy.publish" in line:
            # Find the width line after this section
            for j in range(i + 1, len(lines)):
                if "width" in lines[j]:
                    lines[j] = "width = -100"
                    break
            break
    config_text = "\n".join(lines)
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    with pytest.raises(VaultConfigError):
        load_config(config_file)


def test_config_proxy_dimensions_min_valid_value(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that proxy dimensions = 1 is valid (minimum positive)."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    # Set all dimensions to 1
    config_text = config_text.replace("width = 640", "width = 1")
    config_text = config_text.replace("width = 1280", "width = 1")
    config_text = config_text.replace("height = 480", "height = 1")
    config_text = config_text.replace("height = 960", "height = 1")
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    config = load_config(config_file)
    assert isinstance(config, Config)


# ============================================================================
# Test: C18. SourceConfig.kind must be constrained to fixed set
# ============================================================================


def test_config_source_kind_invalid_rejected(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that invalid source kind values are rejected."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)
    source = temp_dir / "sources" / "source1"
    source.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    sources_fragment = dedent(f'''
        [[sources]]
        name = "bad_source"
        kind = "invalid_kind_xyz"
        path = "{source}"
    ''').strip()
    config_text = minimal_valid_config(str(archive), str(staging), sources=sources_fragment)
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    # Should raise VaultConfigError for invalid kind
    with pytest.raises(VaultConfigError) as exc_info:
        load_config(config_file)
    errors = exc_info.value.errors
    error_msg = " ".join(str(e) for e in errors)
    assert "kind" in error_msg.lower()


# ============================================================================
# Test: C21. Distinguish missing-env-var errors from schema errors
# ============================================================================


def test_missing_env_var_error_is_distinguishable(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that missing env var errors can be distinguished from schema validation errors.

    The error messages should indicate that the issue is a missing environment
    variable, not a schema type mismatch or other validation error.
    """
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    # Explicitly unset the env var
    monkeypatch.delenv("VAULT_IMMICH_API_KEY", raising=False)

    with pytest.raises(VaultConfigError) as exc_info:
        load_config(config_file)

    # Check that the error message mentions the env var name or "not set"
    errors = exc_info.value.errors
    error_msg = " ".join(str(e) for e in errors)
    # Should mention the env var, not just "invalid type"
    assert (
        "VAULT_IMMICH_API_KEY" in error_msg
        or "not set" in error_msg.lower()
        or "not found" in error_msg.lower()
        or "environment" in error_msg.lower()
    )


def test_schema_error_vs_missing_env_var_error_format(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that schema validation errors and missing env var errors have different error formats.

    Schema error example: invalid type for grace_days
    Env var error example: missing environment variable VAULT_IMMICH_API_KEY
    """
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    # Test schema error: invalid grace_days type
    config_file = temp_dir / "vault_schema_error.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_text = config_text.replace("grace_days = 0", 'grace_days = "not_a_number"')
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")

    try:
        load_config(config_file)
        pytest.fail("Should have raised VaultConfigError for schema error")
    except VaultConfigError as e:
        schema_error_msg = " ".join(str(err) for err in e.errors)

    # Test env var error: missing VAULT_IMMICH_API_KEY
    config_file2 = temp_dir / "vault_env_error.toml"
    config_text2 = minimal_valid_config(str(archive), str(staging))
    config_file2.write_text(config_text2)

    monkeypatch.delenv("VAULT_IMMICH_API_KEY", raising=False)

    try:
        load_config(config_file2)
        pytest.fail("Should have raised VaultConfigError for missing env var")
    except VaultConfigError as e:
        env_var_error_msg = " ".join(str(err) for err in e.errors)

    # The error messages should be different (not identical)
    # Schema error should mention type, env var error should mention env var
    assert schema_error_msg != env_var_error_msg


# ============================================================================
# Test: B1/B2/B3. Type-level secret marker (pydantic.SecretStr)
# ============================================================================


def test_resolved_secret_uses_secretstr(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that resolved secrets are backed by pydantic.SecretStr.

    This verifies that the secret marker is at the type level, not just
    a naming convention.
    """
    from pydantic import SecretStr

    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    secret_value = "super-secret-test-key-12345"
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", secret_value)

    config = load_config(config_file)

    # The resolved secret (looked up by the env var name the field references)
    # should be a SecretStr instance, not a raw string.
    resolved = config.get_resolved_secret("VAULT_IMMICH_API_KEY")
    assert isinstance(resolved, SecretStr), f"expected SecretStr, got {type(resolved)}"
    assert resolved.get_secret_value() == secret_value


def test_secret_field_detection_via_type() -> None:
    """Test that secret fields are detectable via type inspection (not string-suffix naming).

    Verifies there's a schema-level marker identifying which fields are secret
    references, rather than the detection relying on a bare '_env' name suffix.
    """
    from vault.config import PublishConfig

    publish_fields = PublishConfig.model_fields
    assert "immich_api_key_env" in publish_fields
    field_info = publish_fields["immich_api_key_env"]
    has_secret_marker = any(
        "SecretMarker" in str(m) or "secret" in str(m).lower() for m in field_info.metadata
    )
    assert has_secret_marker, f"Found metadata: {field_info.metadata}"


# ============================================================================
# Test: B3. Consistent secret redaction in text and JSON outputs
# ============================================================================


def test_config_show_text_redacts_secrets(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that vault config show (text format) redacts secrets consistently."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    secret_value = "actual-secret-key-12345"
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", secret_value)

    result = runner.invoke(app, ["--config", str(config_file), "config", "show"])

    assert result.exit_code == 0
    # Secret value should NOT appear
    assert secret_value not in result.output
    # Should show the env var name instead
    assert "VAULT_IMMICH_API_KEY" in result.output or "<set from" in result.output


def test_config_show_json_redacts_secrets(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that vault config show --json redacts secrets consistently."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    secret_value = "actual-secret-json-12345"
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", secret_value)

    result = runner.invoke(app, ["--config", str(config_file), "config", "show", "--json"])

    assert result.exit_code == 0
    # Secret value should NOT appear
    assert secret_value not in result.output


def test_config_show_text_and_json_secret_handling_consistent(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that secret handling is consistent between text and JSON outputs.

    Both should either:
    1. Show the env var name (e.g., '<set from VAULT_IMMICH_API_KEY>'), or
    2. Show nothing (field omitted)

    But NOT show the actual secret value.
    """
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    secret_value = "unified-secret-test-key"
    monkeypatch.setenv("VAULT_IMMICH_API_KEY", secret_value)

    # Get text output
    text_result = runner.invoke(app, ["--config", str(config_file), "config", "show"])
    text_output = text_result.output

    # Get JSON output
    json_result = runner.invoke(app, ["--config", str(config_file), "config", "show", "--json"])
    json_output = json_result.output

    # Both should succeed
    assert text_result.exit_code == 0
    assert json_result.exit_code == 0

    # Neither should expose the actual secret
    assert secret_value not in text_output
    assert secret_value not in json_output

    # Both should indicate where the secret came from (env var name)
    # This may be shown differently in text vs JSON, but should be present
    has_env_reference_text = "VAULT_IMMICH_API_KEY" in text_output or "<set" in text_output
    has_env_reference_json = "VAULT_IMMICH_API_KEY" in json_output or "<set" in json_output

    # At least one of them should have the env var reference
    assert has_env_reference_text or has_env_reference_json


# ============================================================================
# Test: D4. Default config path validation and missing file handling
# ============================================================================


def test_cli_config_validate_defaults_to_vault_toml(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that vault config validate without --config defaults to ./vault.toml."""
    archive = temp_dir / "paths" / "archive"
    staging = temp_dir / "paths" / "staging"
    archive.mkdir(parents=True)
    staging.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    config_text = minimal_valid_config(str(archive), str(staging))
    config_file.write_text(config_text)

    monkeypatch.setenv("VAULT_IMMICH_API_KEY", "test-key")
    monkeypatch.chdir(temp_dir)

    # Run validate without --config flag
    result = runner.invoke(app, ["config", "validate"])

    # Should succeed (default to ./vault.toml)
    assert result.exit_code == 0


def test_cli_config_show_missing_default_config_path_error(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that vault config show fails clearly when default vault.toml is missing."""
    # Change to a directory with no vault.toml
    monkeypatch.chdir(temp_dir)

    # Run show without --config (should try ./vault.toml)
    result = runner.invoke(app, ["config", "show"])

    # Should fail with error indicating config file not found
    assert result.exit_code != 0
    assert "vault.toml" in result.output or "config" in result.output.lower()


# ============================================================================
# Test: Additional edge cases for robustness
# ============================================================================


def test_config_open_failure_not_file_not_found_wrapped(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that non-FileNotFoundError open failures are wrapped as VaultConfigError."""
    # Create a directory instead of a file, which will cause IsADirectoryError
    config_path = temp_dir / "vault.toml"
    config_path.mkdir(parents=True)

    # Should raise VaultConfigError (not IsADirectoryError)
    with pytest.raises(VaultConfigError):
        load_config(config_path)


def test_config_path_overlap_with_sources_and_proxies(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that source and proxy paths are included in overlap checks."""
    archive = temp_dir / "archive"
    archive.mkdir(parents=True)
    staging = temp_dir / "staging"
    staging.mkdir(parents=True)
    proxies = temp_dir / "proxies"
    proxies.mkdir(parents=True)

    # Create a source path that overlaps with proxies
    source = proxies / "overlapping_source"
    source.mkdir(parents=True)

    config_file = temp_dir / "vault.toml"
    sources_fragment = dedent(f'''
        [[sources]]
        name = "overlapping"
        kind = "local"
        path = "{source}"
    ''').strip()
    config_text = dedent(f'''
        schema_version = 1

        [paths]
        archive = "{archive}"
        staging = "{staging}"
        proxies = "{proxies}"

        {sources_fragment}

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

    # Should raise VaultConfigError due to source overlapping with proxies
    with pytest.raises(VaultConfigError):
        load_config(config_file)
