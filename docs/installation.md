# Installation

Install the package from PyPI when it is available:

```bash
pip install confease
```

For local development, run commands from the `public/` project directory:

```bash
hatch run pytest
```

## Python Support

`confease` requires Python 3.11 or newer.

## Optional Development Commands

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
