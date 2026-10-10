# Quickstart

Create one shared configuration object near your application entry point:

```python
from argparse import ArgumentParser

from confease import Confease

parser = ArgumentParser()
parser.add_argument("--debug", dest="DEBUG", action="store_true")
args = parser.parse_args()

CONF = Confease(
    "~/.config/my-app/conf.yaml",
    items={
        "APP_DIR": "~/Apps",
        "DEBUG": False,
        "database": {"host": "localhost", "port": 5432},
    },
)

CONF.load_sources(args, "/etc/my-app/conf.yaml")
```

`load_sources()` loads files first, then known environment variables, then non-`None` values from the `argparse.Namespace`. Source precedence decides which value wins when multiple sources define the same key.

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

## Nested Keys

`Confease` supports one nested level. Nested leaves are stored internally as dotted keys:

```python
CONF.set("database", {"host": "localhost", "port": 5432})

CONF.get("database.host")
CONF["database.host"]
CONF.get("database")
CONF["database"]["host"]
```

Section access returns a plain snapshot dictionary. Use dotted keys or `set()` to write nested values:

```python
CONF["database.port"] = 5433
```

Keys can only nest one level. A config cannot contain both a scalar key and a section with the same name, such as `database` and `database.host`.

## Parser Selection

The parser can be inferred from the configured path suffix by passing `parser=None`:

```python
from confease import Confease

conf = Confease("conf.toml", parser=None)
```

You can also pass a parser class explicitly:

```python
from confease import Confease, Json

conf = Confease("conf.json", parser=Json)
```

See [File Formats](file-formats.md) for the exact on-disk shape of each parser.
