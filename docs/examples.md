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

Let a user edit the actual file while keeping fallback defaults in code:

```python
from confease import Confease, TextEditor

conf = Confease("~/.config/my-app/conf.yaml", THEME="light")
conf.editor = TextEditor("nano")

conf.edit_file()
```

Save manually in the editor. Existing comments are preserved without serialization. A missing file is not created unless the editor saves it. Valid saves update the configuration object; invalid saves remain on disk and raise an error while preserving previous in-memory entries.

## Restore A Template

Given an existing `defaults.yaml`:

```yaml
# Default appearance
THEME: light
```

```python
conf = Confease("settings.yaml", template="defaults.yaml")
conf.get("THEME")  # template fallback if missing from settings.yaml
conf.reset()       # deliberately replaces settings.yaml, preserving the comment
```

Reading template defaults does not create `settings.yaml`. Explicit `reset()` validates the template and restores its exact bytes to the target.
