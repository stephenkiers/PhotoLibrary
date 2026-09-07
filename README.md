# vault — Personal Photo Library Manager

A command-line tool for managing and organizing personal photo archives.

## About

`vault` is a photo library management CLI built with Python and [uv](https://docs.astral.sh/uv/). It provides tools for organizing, ingesting, and maintaining photo collections with a focus on safety and integrity.

The tool is organized around three operational panels:
- **Pipeline**: Import and ingest photos
- **Safety**: Verification, integrity checks, and backups
- **Operations**: Organization, querying, and maintenance

For a complete list of available commands, see `uv run vault --help`.

## Getting Started

### Prerequisites

- Python ≥ 3.12
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

Clone the repository and set up the development environment:

```bash
uv sync
```

### Usage

View available commands:

```bash
uv run vault --help
```

### Development

Set up pre-commit hooks for linting, formatting, and testing:

```bash
pre-commit install --install-hooks
```

This installs hooks that:
- Run on commit (pre-commit stage): `ruff check`, `ruff format`, secret detection
- Run on push (pre-push stage): type checking (`mypy`), tests (`pytest`)

For more details, see `.pre-commit-config.yaml`.

## Project Structure

- `src/vault/` — Main package
- `tests/` — Test suite
- `docs/` — Architecture and decision documentation

## License

Not yet decided (see issue #98, milestone M9-03).
