# confease documentation

`confease` is a small Python configuration helper for applications that need predictable configuration precedence across defaults, files, environment variables, and CLI arguments.

Use it when you want one shared configuration object that can:

- Start from in-code defaults.
- Load user and system configuration files.
- Accept environment-variable overrides for known keys.
- Accept `argparse.Namespace` CLI overrides.
- Persist user-origin values back to disk.
- Work with common configuration formats through a simple parser interface.

```{toctree}
:maxdepth: 2
:caption: User Guide

installation
quickstart
configuration
file-formats
examples
changelog
license
```

```{toctree}
:maxdepth: 2
:caption: Reference

api/index
```

## Project Status

`confease` is currently an alpha Python prototype. The public API is small and focused, but behavior may still evolve before a stable release.
