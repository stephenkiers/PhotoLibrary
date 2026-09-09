# Architecture Decisions

This document tracks architectural and design decisions for the vault project.

## M0-05

**Configuration: Single vault.toml with pydantic v2 validation and env-var secret resolution.**

- **Single shared config file**: One `vault.toml` at project root. No per-host overlays or layered configuration.
- **Unknown keys are forbidden**: Pydantic `extra="forbid"` at every level catches typos immediately rather than silently using defaults.
- **No general env-var override mechanism**: Environment variables are used for exactly one purpose — resolving named secrets (`*_env` fields like `immich_api_key_env`). There is no `VAULT_<SECTION>__<KEY>` override for arbitrary config values.
- **Pydantic v2, plain (no pydantic-settings)**: TOML parsing via stdlib `tomllib` (Python 3.12), validation via pydantic v2.
- **All six sections ship now**: `paths`, `sources`, `thresholds`, `proxy`, `publish`, `backup` — including a provisional `backup.targets` shape, documented as subject to change.
- **Secret resolution is implemented now**: Schema fields marked with the `EnvVarSecretRef` type-level annotation (e.g. `immich_api_key_env`) are validated as environment variable names (`^[A-Z][A-Z0-9_]*$`), then resolved from `os.environ` into a `pydantic.SecretStr` that redacts `repr()`/`str()`.
- **`vault config show` never prints resolved secret values**: Output shows that a secret resolved and which env var it came from (e.g. `<set from VAULT_IMMICH_API_KEY>`), never the value itself.
- **`load_config` fails fast if *_env variables are not set**: Any `*_env` field that references a missing environment variable causes `load_config` to raise `VaultConfigError` immediately. This means even `vault config show` requires all referenced secrets to be present in the environment, not just commands that use them.
- **`vault config validate` checks the filesystem** (separate from schema validation): Validates schema, then runs a preflight check (paths exist/reachable, no overlapping paths). Schema validation itself only touches the filesystem to resolve symlinks/case for the path-overlap check (`os.path.samefile()`, with a pure-string fallback when a path doesn't exist yet), so an unmounted NAS still won't break commands that don't run the full preflight.
- **`Config.fingerprint()` method**: Stable canonical serialization + SHA-256 hash for recording which config governed a destructive operation. Included now for future M0-08 (append-only journal).
- **macOS Keychain integration deferred** (tracked in M0-21): Secret resolution currently uses only environment variables. Keychain support is a future enhancement, not blocking this ticket.

## M0-12

Decision pending — see issue tracker.

## M0-13

Decision pending — see issue tracker.

## M0-14

Decision pending — see issue tracker.

## M0-15

Decision pending — see issue tracker.

## M0-16

Decision pending — see issue tracker.

## M0-17

Decision pending — see issue tracker.

## M0-18

Decision pending — see issue tracker.

## M0-19

Decision pending — see issue tracker.

## M0-20

Decision pending — see issue tracker.
