# confease documentation

`confease` is a small Python configuration helper for applications that need predictable configuration precedence across defaults, files, environment variables, and CLI arguments.

Use it when you want one shared configuration object that can:

- Start from in-code defaults.
- Load user and system configuration files.
- Accept environment-variable overrides for known keys.
- Accept `argparse.Namespace` CLI overrides.
- Persist user-origin values back to disk.
- Work with common configuration formats through a simple parser interface.

Start with the [installation guide](installation.md) if you are setting up the package, or jump to the [quickstart](quickstart.md) for the first working example.

```{toctree}
:maxdepth: 2
:caption: User Guide

installation
quickstart
configuration
file-formats
examples
troubleshooting
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

## Project Links

- Repository: <https://github.com/octanima-labs/confease>
- Issues: <https://github.com/octanima-labs/confease/issues>
- Documentation: <https://octanima-labs.github.io/confease>
