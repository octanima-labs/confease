# confease

`confease` is a small Python configuration helper for applications that need predictable precedence across defaults, configuration files, environment variables, and CLI arguments.

Use it when you want one shared configuration object that can load user and system config files, accept `argparse` overrides, read typed environment values, and persist user preferences without building a full settings framework.

> Status: `confease` is an alpha prototype. The public API is intentionally small, but behavior may still change before a stable release.

## Installation

When published, install from PyPI:

```bash
pip install confease
```

For local development from this repository:

```bash
git clone https://github.com/octanima-labs/confease.git
cd confease
hatch run pytest
```

The package requires Python 3.11 or newer.

## Quickstart

Create one shared configuration object near your application entry point:

```python
from argparse import ArgumentParser

from confease import Confease

parser = ArgumentParser()
parser.add_argument("--debug", dest="DEBUG", action="store_true")
parser.add_argument("--database-host", dest="database", action="store_const", const={"host": "db.internal"})
args = parser.parse_args()

conf = Confease(
    "~/.config/my-app/conf.yaml",
    APP_DIR="~/Apps",
    DEBUG=False,
    database={"host": "localhost", "port": 5432},
)

conf.load_sources(args, "/etc/my-app/conf.yaml")
```

Read values with `get()` or indexed access:

```python
conf.get("APP_DIR")          # "~/Apps"
conf["APP_DIR"]             # "~/Apps"
conf.get("MISSING")          # None
conf["MISSING"]             # None
conf.get("DEBUG", cast=bool) # False
```

Update values with `set()` or indexed assignment:

```python
conf.set("DEBUG", True)
conf["APP_DIR"] = "/srv/app"
conf.save()
```

By default, `save()` writes only user-origin values. Use `save(user_only=False)` when you want to persist the full effective configuration, including defaults and overrides.

## Nested Keys

`Confease` supports one nested level. Internally, nested leaves are stored as dotted keys:

```python
conf.set("database", {"host": "localhost", "port": 5432})

conf.get("database.host")    # "localhost"
conf["database.host"]        # "localhost"
conf.get("database")         # {"host": "localhost", "port": 5432}
conf["database"]["host"]     # "localhost"
```

Section access returns a plain snapshot dictionary. Missing subkeys raise `KeyError`, so write nested values through dotted keys or `set()`:

```python
conf["database.port"] = 5433
```

## Source Precedence

By default, sources are resolved in this order:

```text
CLI > ENV > SYS > USR > DEF
```

Origins mean:

- `CLI`: values from an `argparse.Namespace` passed to `load_sources()` or `reload_cli()`.
- `ENV`: known environment variables loaded by `reload_env()`.
- `SYS`: config files outside the current user home directory.
- `USR`: config files inside the current user home directory and values assigned with `set()`.
- `DEF`: keyword defaults or values read from a configured template.

Customize precedence with `preference`:

```python
conf = Confease("conf.yaml", preference=["env", "cli", "user", "default"])
conf.load_sources(args, "conf.yaml", preference=["cli", "env", "user", "default"])
```

Omitted origins are appended after the origins you provide.

## Environment Variables

`reload_env()` only imports environment variables whose keys are already known from defaults or loaded files. Values are parsed with `yaml.safe_load`, so common scalar text recovers Python types:

```bash
export DEBUG=true
export PORT=5432
```

```python
conf = Confease(DEBUG=False, PORT=8000)
conf.reload_env()

conf["DEBUG"] # True
conf["PORT"]  # 5432
```

## File Formats

The parser is inferred from the path suffix when `parser=None` is used, or you can pass a parser class explicitly.

Supported suffixes:

- `.yaml`, `.yml`
- `.json`
- `.toml`
- `.ini`, `.cfg`, `.conf`, `.config`
- `.xml`
- `.csv`

```python
from confease import Confease, Json

yaml_conf = Confease("conf.yaml", parser=None)
json_conf = Confease("conf.json", parser=Json)
```

YAML, JSON, TOML, INI, and XML persist one-level nested sections. CSV persists flat dotted keys with a `key,value` header.

## Edit Config Files

`edit_file()` opens the real configured path in a blocking text editor without serializing it first, preserving comments and formatting:

```python
from confease import TextEditor

conf.editor = TextEditor("code")
conf.edit_file()
```

Save manually in the editor. A missing file stays missing if you close without saving; parent directories are created as needed. Valid saved content is reloaded. Invalid saved content raises an error and remains on disk, while the previous in-memory entries stay intact.

**Upgrading:** Replace `edit_file(user_only=...)` with `edit_file()`. The removed argument no longer applies because editing opens the actual file rather than generating filtered content. `save(user_only=...)` is unchanged.

## Templates And Reset

Use a template instead of keyword defaults when defaults belong in a file:

```python
conf = Confease("conf.yaml", template="defaults.yaml")  # defaults.yaml must exist
conf.get("DEBUG")  # falls back to the template if absent from conf.yaml
conf.reset()       # explicitly overwrites conf.yaml with exact template content
```

Template values are `DEF` defaults in memory; initialization and reads do not copy them to the target. Explicit template-backed `reset()` validates the template, restores its exact bytes (including comments), and reloads the target as `USR` values. Missing or invalid templates leave the existing file and entries unchanged. Without a template, `reset()` resets keyword defaults only in memory.

See [configuration guidance](docs/configuration.md) for details.

## Documentation

- Documentation: <https://octanima-labs.github.io/confease>
- Repository: <https://github.com/octanima-labs/confease>
- Issues: <https://github.com/octanima-labs/confease/issues>

## License

MIT
