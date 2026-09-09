"""Error types and exit codes."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Exit codes for the vault CLI."""

    OK = 0
    CONFIRMATION_REQUIRED = 1
    CONFIG_ERROR = 2
    NOT_IMPLEMENTED = 3


class VaultError(Exception):
    """Base exception class for vault errors."""

    pass


class VaultConfigError(VaultError):
    """Configuration loading error with detailed error list."""

    def __init__(self, errors: list[tuple[str, str]]) -> None:
        """Initialize with a list of (key_path, message) error tuples.

        Args:
            errors: List of (key_path, message) tuples describing validation failures.
        """
        self.errors = errors
        super().__init__(f"Configuration error: {len(errors)} validation error(s)")
