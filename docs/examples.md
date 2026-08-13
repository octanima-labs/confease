# Examples

## Application Configuration

Use defaults for required application keys, then load system, user, environment, and CLI values:

```python
from argparse import ArgumentParser

from confease import Confease

parser = ArgumentParser()
parser.add_argument("--debug", dest="DEBUG", action="store_true")
parser.add_argument("--log-level", dest="LOG_LEVEL")
args = parser.parse_args()

conf = Confease(
    "~/.config/my-app/conf.yaml",
    DEBUG=False,
    LOG_LEVEL="INFO",
    database={"host": "localhost", "port": 5432},
)

conf.load_sources(args, "/etc/my-app/conf.yaml")
```

If `--debug` is provided, the CLI-origin value wins over values from environment variables, files, and defaults under the default precedence.

## Save User Preferences

Values assigned with `set()` or indexed assignment are user-origin values. By default, `save()` writes only user-origin values:

```python
conf = Confease("~/.config/my-app/conf.yaml", THEME="light")

conf["THEME"] = "dark"
conf.save()
```

## Load a Specific Format

Pass `parser=None` to infer the parser from the suffix:

```python
from confease import Confease

conf = Confease("settings.toml", parser=None)
```

Pass a parser class when you want to be explicit:

```python
from confease import Confease, Json

conf = Confease("settings.json", parser=Json)
```

## Runtime-Only Configuration

Create a configuration object without a path when persistence is not needed:

```python
from confease import Confease

conf = Confease(DEBUG=False)
conf["DEBUG"] = True
```

Calling `save()` on a runtime-only configuration does not write a file.

## Read Sections

Nested sections can be read as plain dictionaries:

```python
conf = Confease(database={"host": "localhost", "port": 5432})

database = conf["database"]
host = database["host"]
```

Section dictionaries are snapshots. Write nested values through dotted keys:

```python
conf["database.host"] = "db.internal"
```

## Edit a Config File

Let a user edit only persisted user preferences while keeping defaults in code:

```python
from confease import Confease, TextEditor

conf = Confease("~/.config/my-app/conf.yaml", THEME="light")
conf.set("THEME", "dark")
conf.editor = TextEditor("nano")

conf.edit_file(user_only=True)
```

The edit happens in a temporary draft. If the edited file is invalid for the active parser, the original file is kept.
