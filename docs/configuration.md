# Configuration Model

`Confease` stores configuration values as flattened `Confitem` leaves. Each item has a key, a value, and an origin that records where the value came from.

## Source Origins

The supported origins are:

- `CLI`: values from an `argparse.Namespace` passed to `load_sources()` or `reload_cli()`.
- `ENV`: environment variables loaded by `reload_env()`.
- `SYS`: config files outside the current user's home directory.
- `USR`: config files inside the current user's home directory and values assigned with `set()`.
- `DEF`: defaults passed as keyword arguments to `Confease(...)`.

By default, precedence is ordered from highest to lowest priority:

```text
CLI > ENV > SYS > USR > DEF
```

Higher-priority origins replace lower-priority origins for the same key.

## Custom Precedence

Customize precedence with the `preference` argument:

```python
from confease import Confease

conf = Confease(
    "conf.yaml",
    preference=["env", "cli", "user", "default"],
)
```

You can also override precedence while loading sources:

```python
conf.load_sources(
    args,
    "conf.yaml",
    preference=["cli", "env", "user", "default"],
)
```

Origins omitted from the preference list are appended after the origins you provide.

## Defaults

Defaults are passed as keyword arguments:

```python
conf = Confease(
    DEBUG=False,
    PORT=8000,
    database={"host": "localhost", "port": 5432},
)
```

Defaults are memory-only unless explicitly saved. By default, `save()` writes only user-origin entries. Use `save(user_only=False)` to write all current entries, including defaults and loaded overrides.

## Environment Variables

`reload_env()` imports only environment variables whose keys are already known from defaults or loaded files. Values are parsed with `yaml.safe_load`, so common scalar text recovers Python types:

```bash
export DEBUG=true
export PORT=5432
```

```python
conf = Confease(DEBUG=False, PORT=8000)
conf.reload_env()

conf["DEBUG"]
conf["PORT"]
```

## CLI Values

`reload_cli()` accepts an `argparse.Namespace` and imports values whose namespace value is not `None`:

```python
from argparse import Namespace

conf.reload_cli(Namespace(DEBUG=True, PORT=None))
```

In this example, `DEBUG` is loaded as a CLI value and `PORT` is ignored.

For nested values, pass a one-level dictionary in the namespace value. It is flattened into dotted keys:

```python
conf.reload_cli(Namespace(database={"host": "db.internal"}))

conf["database.host"]
```

## Persistence

Call `save()` to persist configuration back to the path configured on the `Confease` instance:

```python
conf = Confease("~/.config/my-app/conf.yaml", DEBUG=False)
conf.set("DEBUG", True)
conf.save()
```

If the instance was created without a path, `save()` is a no-op.

## Editing Files Safely

Use `edit_file()` when you want users or maintainers to edit the configured file manually:

```python
from confease import Confease, TextEditor

conf = Confease("~/.config/my-app/conf.yaml", DEBUG=False)
conf.editor = TextEditor("code")
conf.edit_file(user_only=True)
```

`edit_file()` writes a temporary draft first, opens it in the configured editor, parses the edited draft, and only replaces the real file after validation succeeds. Invalid edits raise an error and leave the previous file and in-memory values unchanged.

## Limitations

- Nested configuration keys support one level only.
- Environment loading only considers keys already known from defaults or loaded files.
- `save()` writes only `USR` entries by default; use `save(user_only=False)` to write the full effective configuration.
- Runtime-only configurations created without a path do not persist when saved.
- `__str__()` and `to_str()` are reserved for future printable representations and are not currently implemented.
