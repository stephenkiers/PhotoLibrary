"""Configuration schema and loader for vault.

This module provides a single vault.toml loader with pydantic v2 validation,
environment variable resolution for secrets, and preflight checks.
"""

import hashlib
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from vault.errors import VaultConfigError


class Secret:
    """Wrapper for secret values that redacts repr() and str()."""

    def __init__(self, value: str) -> None:
        """Initialize a secret with the given value."""
        self._value = value

    def get_secret_value(self) -> str:
        """Return the actual secret value."""
        return self._value

    def __repr__(self) -> str:
        """Return a redacted representation."""
        return "<Secret: redacted>"

    def __str__(self) -> str:
        """Return a redacted string."""
        return "<Secret: redacted>"


# Custom type for non-negative integers
NonNegativeInt = Annotated[int, Field(ge=0)]


class PathsConfig(BaseModel):
    """Configuration for vault storage paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    archive: Path
    staging: Path
    proxies: Path | None = None
    catalog: Path | None = None

    @field_validator("archive", "staging", "proxies", "catalog", mode="before")
    @classmethod
    def resolve_paths(cls, v: str | Path | None) -> Path | None:
        """Resolve and normalize path values."""
        if v is None:
            return None
        if isinstance(v, Path):
            return v.expanduser().resolve()
        return Path(v).expanduser().resolve()


class SourceConfig(BaseModel):
    """Configuration for a photo source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: str
    path: Path
    immich_api_key_env: str | None = None

    @field_validator("path", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path) -> Path:
        """Resolve and normalize path value."""
        if isinstance(v, Path):
            return v.expanduser().resolve()
        return Path(v).expanduser().resolve()

    @field_validator("immich_api_key_env")
    @classmethod
    def validate_env_var_name(cls, v: str | None) -> str | None:
        """Validate that env var names match ^[A-Z][A-Z0-9_]*$."""
        if v is None:
            return None
        if not re.match(r"^[A-Z][A-Z0-9_]*$", v):
            raise ValueError(f"Invalid env var name: {v}")
        return v


class ThresholdsConfig(BaseModel):
    """Configuration for quality thresholds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_quality: float | None = None
    max_age_days: NonNegativeInt | None = None

    @field_validator("min_quality")
    @classmethod
    def validate_quality(cls, v: float | None) -> float | None:
        """Validate quality is between 0 and 1."""
        if v is not None and not (0 <= v <= 1):
            raise ValueError("min_quality must be between 0 and 1")
        return v


class ProxyProfile(BaseModel):
    """Configuration for a proxy generation profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    width: int
    height: int
    quality: Annotated[int, Field(ge=1, le=100)]


class ProxyConfig(BaseModel):
    """Configuration for proxy generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review: ProxyProfile | None = None
    publish: ProxyProfile | None = None


class PublishConfig(BaseModel):
    """Configuration for publishing to Immich."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    immich_url: str | None = None
    immich_api_key_env: str | None = None
    grace_days: NonNegativeInt = 0
    shared_library_policy: Literal["skip", "include", "include_no_retire"] = "skip"

    @field_validator("immich_api_key_env")
    @classmethod
    def validate_env_var_name(cls, v: str | None) -> str | None:
        """Validate that env var names match ^[A-Z][A-Z0-9_]*$."""
        if v is None:
            return None
        if not re.match(r"^[A-Z][A-Z0-9_]*$", v):
            raise ValueError(f"Invalid env var name: {v}")
        return v


class BackupTarget(BaseModel):
    """Configuration for a backup target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: Literal["rsync", "restic"]
    destination: str
    retention_days: NonNegativeInt | None = None


class BackupConfig(BaseModel):
    """Configuration for backup operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    targets: list[BackupTarget] | None = None


class Config(BaseModel):
    """Top-level vault configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    paths: PathsConfig
    sources: list[SourceConfig] | None = None
    thresholds: ThresholdsConfig | None = None
    proxy: ProxyConfig | None = None
    publish: PublishConfig | None = None
    backup: BackupConfig | None = None

    @model_validator(mode="after")
    def check_no_overlapping_paths(self) -> "Config":
        """Verify that configured paths don't overlap."""

        def _is_subpath(a: Path, b: Path) -> bool:
            """Check if path a is a subpath of path b (including equal paths)."""
            try:
                a.relative_to(b)
                return True
            except ValueError:
                return False

        # Collect all paths
        all_paths: dict[str, Path] = {}

        # Add paths from PathsConfig (archive and staging are always present)
        all_paths["archive"] = self.paths.archive
        all_paths["staging"] = self.paths.staging
        if self.paths.proxies is not None:
            all_paths["proxies"] = self.paths.proxies
        if self.paths.catalog is not None:
            all_paths["catalog"] = self.paths.catalog

        # Check for overlaps
        paths_list = list(all_paths.items())
        for i, (name1, path1) in enumerate(paths_list):
            for name2, path2 in paths_list[i + 1 :]:
                # Check if path1 is inside path2 or vice versa
                if _is_subpath(path1, path2):
                    raise ValueError(f"Path '{name1}' ({path1}) is inside '{name2}' ({path2})")
                if _is_subpath(path2, path1):
                    raise ValueError(f"Path '{name2}' ({path2}) is inside '{name1}' ({path1})")

        return self

    def fingerprint(self) -> str:
        """Return a stable hash of the canonical config serialization."""
        # Convert to JSON with sorted keys for canonical form
        config_dict = self.model_dump(mode="json")
        canonical_json = json.dumps(config_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode()).hexdigest()

    def get_resolved_secret(self, env_var_name: str) -> Secret | None:
        """Get a resolved secret by its environment variable name.

        Args:
            env_var_name: Name of the environment variable (e.g., 'VAULT_IMMICH_API_KEY').

        Returns:
            The Secret object if resolved and present, None otherwise.
        """
        resolved_secrets: dict[str, Secret] = getattr(self, "_resolved_secrets", {})
        return resolved_secrets.get(env_var_name)


def load_config(path: Path) -> Config:
    """Load and validate configuration from a TOML file.

    Args:
        path: Path to vault.toml file.

    Returns:
        Validated Config instance.

    Raises:
        VaultConfigError: If validation fails, containing all errors.
        FileNotFoundError: If the config file does not exist.
        tomllib.TOMLDecodeError: If the TOML is malformed.
    """
    # Read TOML file
    try:
        with open(path, "rb") as f:
            raw_config = tomllib.load(f)
    except FileNotFoundError:
        raise
    except tomllib.TOMLDecodeError as e:
        raise VaultConfigError([(str(path), str(e))]) from e

    # Validate with pydantic
    try:
        config = Config(**raw_config)
    except Exception as e:
        # Convert pydantic validation errors to VaultConfigError
        errors: list[tuple[str, str]] = []

        # Check if it's a pydantic validation error
        if hasattr(e, "errors"):
            for error_info in e.errors():
                # Build dotted path from error location
                loc = error_info.get("loc", ())
                key_path = ".".join(str(x) for x in loc)
                msg = error_info.get("msg", str(error_info))
                errors.append((key_path, msg))
        else:
            # Fallback for non-pydantic errors
            errors.append(("", str(e)))

        raise VaultConfigError(errors) from e

    # Resolve secrets from environment
    _resolve_secrets(config)

    return config


def _resolve_secrets(config: Config) -> None:
    """Resolve secret environment variables in the config.

    Walks the config tree, finds all *_env fields, and resolves them from
    environment variables. Stores resolved secrets in a _resolved_secrets dict
    keyed by environment variable name. Raises VaultConfigError if any
    referenced env vars are missing.

    Args:
        config: The Config instance to resolve secrets for.

    Raises:
        VaultConfigError: If any environment variables referenced in *_env fields
            are not set in the environment.
    """
    resolved_secrets: dict[str, Secret] = {}
    missing_env_vars: list[tuple[str, str]] = []

    # Helper to recursively process the config tree
    def _process_model(obj: BaseModel, path_prefix: str = "") -> None:
        for field_name in obj.model_fields:
            field_value = getattr(obj, field_name, None)
            current_path = f"{path_prefix}.{field_name}" if path_prefix else field_name

            if isinstance(field_value, BaseModel):
                _process_model(field_value, current_path)
            elif isinstance(field_value, list):
                for i, item in enumerate(field_value):
                    if isinstance(item, BaseModel):
                        _process_model(item, f"{current_path}[{i}]")

            # Handle *_env fields: resolve from environment
            if field_name.endswith("_env") and isinstance(field_value, str):
                env_var_name = field_value
                env_value = os.environ.get(env_var_name)
                if env_value is None:
                    missing_env_vars.append((current_path, env_var_name))
                else:
                    # Key by env var name for easy lookup in CLI
                    resolved_secrets[env_var_name] = Secret(env_value)

    _process_model(config)

    # If any env vars were missing, raise an error with all missing ones
    if missing_env_vars:
        errors = [
            (path, f"environment variable '{env_var}' not set")
            for path, env_var in missing_env_vars
        ]
        raise VaultConfigError(errors)

    # Attach resolved secrets to the frozen config using object.__setattr__
    object.__setattr__(config, "_resolved_secrets", resolved_secrets)


def fs_preflight(config: Config) -> list[str]:
    """Check that configured paths exist and are reachable.

    Args:
        config: The loaded configuration.

    Returns:
        List of problem strings (empty if all OK).
    """
    problems: list[str] = []

    # Check archive path (always present)
    if not config.paths.archive.exists():
        problems.append(f"archive path does not exist: {config.paths.archive}")
    elif not config.paths.archive.is_dir():
        problems.append(f"archive path is not a directory: {config.paths.archive}")

    # Check staging path (always present)
    if not config.paths.staging.exists():
        problems.append(f"staging path does not exist: {config.paths.staging}")
    elif not config.paths.staging.is_dir():
        problems.append(f"staging path is not a directory: {config.paths.staging}")

    # Check proxies path (optional)
    if config.paths.proxies is not None:
        if not config.paths.proxies.exists():
            problems.append(f"proxies path does not exist: {config.paths.proxies}")
        elif not config.paths.proxies.is_dir():
            problems.append(f"proxies path is not a directory: {config.paths.proxies}")

    # Check catalog path (optional)
    if config.paths.catalog is not None:
        if not config.paths.catalog.exists():
            problems.append(f"catalog path does not exist: {config.paths.catalog}")
        elif not config.paths.catalog.is_file():
            problems.append(f"catalog path is not a file: {config.paths.catalog}")

    # Check source paths
    if config.sources:
        for source in config.sources:
            if not source.path.exists():
                problems.append(f"source '{source.name}' path does not exist: {source.path}")
            elif not source.path.is_dir():
                problems.append(f"source '{source.name}' path is not a directory: {source.path}")

    return problems


def format_config_errors(config_path: Path, errors: list[tuple[str, str]]) -> str:
    """Format VaultConfigError for display to the user.

    Args:
        config_path: Path to the config file.
        errors: List of (key_path, message) tuples.

    Returns:
        Formatted error message string.
    """
    lines: list[str] = []
    for key_path, msg in errors:
        if key_path:
            lines.append(f"vault: `{config_path}`: {key_path}: {msg}")
        else:
            lines.append(f"vault: `{config_path}`: {msg}")
    return "\n".join(lines)


def format_preflight_errors(config_path: Path, problems: list[str]) -> str:
    """Format preflight check problems for display to the user.

    Args:
        config_path: Path to the config file.
        problems: List of problem descriptions.

    Returns:
        Formatted error message string.
    """
    lines: list[str] = []
    for problem in problems:
        lines.append(f"vault: `{config_path}`: {problem}")
    return "\n".join(lines)
