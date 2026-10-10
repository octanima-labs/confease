# Installation

`confease` requires Python 3.11 or newer.

Edital provides the Textual editor as a Python dependency. Interactive editing requires terminal
input and output, but no separately installed editor executable. Scripted CLI
updates and ordinary configuration access do not initialize the TUI.

Edital 0.2.0 is available on PyPI. Confease declares `edital>=0.2.0,<0.3`, so pip
and Hatch install the published editor dependency automatically. No sibling
checkout or local source override is needed.

For pip-based development, install Confease in editable mode:

```bash
python -m pip install -e /path/to/confease/public
```

Install the package from PyPI when it is available:

```bash
pip install confease
```

## From Source

For local development, clone the repository and run commands from the `public/` project directory:

```bash
git clone https://github.com/octanima-labs/confease.git
cd confease/public
hatch run pytest
```

The outer repository is an agent-facing workspace. The Python package, tests, build metadata, README, and docs live under `public/`.

## Development Commands

The project uses Hatch environments for common checks:

```bash
hatch run pytest
hatch run ruff check .
hatch run mypy src
hatch build
```

Build these docs with:

```bash
hatch run docs:build
```

This command runs Sphinx with warnings treated as errors.
