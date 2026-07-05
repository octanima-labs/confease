# confease

Small Python configuration helper for combining defaults, files, environment variables, and CLI arguments with predictable precedence.

## Installation

```bash
pip install confease
```

For local development, run commands from this `public/` project:

```bash
hatch run pytest
```

## Quickstart

Create one shared configuration object near your application entry point:

```python
from argparse import ArgumentParser

from confease import Confease

args = ArgumentParser().parse_args()

CONF = Confease(
    "~/.config/my-app/conf.yaml",
    APP_DIR="~/Apps",
    DEBUG=False,
    database={"host": "localhost", "port": 5432},
)

CONF.load_sources(args, "/etc/my-app/conf.yaml")
```

Read values with `get()` or indexed access:

```python
CONF.get("APP_DIR")          # "~/Apps"
CONF["APP_DIR"]             # "~/Apps"
CONF.get("MISSING")          # None
CONF["MISSING"]             # None
CONF.get("DEBUG", cast=bool) # False
```

Update values with `set()` or indexed assignment:

```python
CONF.set("DEBUG", True)
CONF["APP_DIR"] = "/srv/app"
CONF.save()
```

Edit the configured file in a blocking text editor:

```python
from confease import TextEditor

CONF.editor = TextEditor("code")
CONF.edit_file(user_only=True)
```

`edit_file()` writes a temporary draft first, opens it in the editor, validates the edited content with the active parser, and only then replaces the real config file. Invalid edited content raises an error and leaves the previous file and in-memory values unchanged. Pass `user_only=False` to edit the full effective config instead of only user-origin values.

## Nested Keys

Confease supports one nested level. Internally, nested leaves are stored as dotted keys.

```python
CONF.set("database", {"host": "localhost", "port": 5432})

CONF.get("database.host")    # "localhost"
CONF["database.host"]        # "localhost"
CONF.get("database")         # {"host": "localhost", "port": 5432}
CONF["database"]["host"]     # "localhost"
```

Section access returns a plain read-only snapshot dict. Missing subkeys raise `KeyError`, so write nested values through dotted keys or `set()`:

```python
CONF["database.port"] = 5433
```

## Source Precedence

By default, sources are resolved in this order:

```text
CLI > ENV > SYS > USR > DEF
```

Origins mean:

- `CLI`: values from an `argparse.Namespace` passed to `load_sources()` or `reload_cli()`.
- `ENV`: environment variables loaded by `reload_env()`.
- `SYS`: config files outside the current user home directory.
- `USR`: config files inside the current user home directory and values assigned with `set()`.
- `DEF`: defaults passed as keyword arguments to `Confease(...)`.

Customize precedence with `preference`:

```python
CONF = Confease("conf.yaml", preference=["env", "cli", "user", "default"])
CONF.load_sources(args, "conf.yaml", preference=["cli", "env", "user", "default"])
```

Omitted origins are appended after the origins you provide.

## Environment Variables

`reload_env()` only imports environment variables whose keys are already known from defaults or loaded files. Values are parsed with `yaml.safe_load`, so common scalar text recovers Python types:

```bash
export DEBUG=true
export PORT=5432
```

```python
CONF = Confease(DEBUG=False, PORT=8000)
CONF.reload_env()

CONF["DEBUG"] # True
CONF["PORT"]  # 5432
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

## License

MIT
