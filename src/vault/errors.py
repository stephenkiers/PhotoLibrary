"""Error types and exit codes."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Exit codes for the vault CLI."""

    OK = 0
    NOT_IMPLEMENTED = 3


class VaultError(Exception):
    """Base exception class for vault errors."""

    pass
