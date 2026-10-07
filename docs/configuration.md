# Configuration Model

`Confease` stores configuration values as flattened `Confitem` leaves. Each item has a key, a value, and an origin that records where the value came from.

## Source Origins

The supported origins are:

- `CLI`: values from an `argparse.Namespace` passed to `load_sources()` or `reload_cli()`.
- `ENV`: environment variables loaded by `reload_env()`.
- `SYS`: config files outside the current user's home directory.
- `USR`: config files inside the current user's home directory and values assigned with `set()`.
- `DEF`: keyword defaults or values read from a configured template.

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

### Templates And Explicit Reset

Alternatively, provide an existing template file instead of keyword defaults:

```python
conf = Confease("settings.yaml", template="defaults.yaml")
```

Both files use the configured active parser. Template values become `DEF` defaults and provide fallbacks for keys absent from the target. Existing target values load as `USR`. Initializing or reading configuration does not create a missing target or overwrite an existing one.

To deliberately restore the persisted file, call:

```python
conf.reset()
```

With a template, this is a destructive restore: it validates the template, copies its exact bytes over the configured path, and reloads the restored values as `USR`. Comments, formatting, and key order are preserved. Missing parent directories are created. Missing or invalid templates and copy failures leave prior file content and entries unchanged.

Template restoration requires a configured target path; a template-backed runtime-only instance raises `FileNotFoundError` on `reset()`. Without a template, `reset()` only restores keyword defaults in memory and does not write or delete a file. Templates cannot be combined with keyword defaults.

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

`save()` preserves destination comments in YAML, TOML, INI-family, and XML files.
YAML and TOML use native round-trip documents; INI uses an `iniparse` presentation
tree with the existing stdlib/YAML value semantics; XML keeps comment nodes inside
the root and in the document prolog and epilog. JSON and CSV retain their existing
formats without introducing comment conventions.

Saving reads and validates the current destination document, so comment edits
made externally after loading are retained. The selected in-memory values remain
authoritative: externally added or changed values are not implicitly merged.
Values excluded by user-only origin filtering are removed from the destination
together with their attached comments. Document headers and footers survive.
Unaffected ordering and presentation are retained where the backend supports it;
structured writes do not promise byte-identical formatting.

Complete candidate files are serialized, reloaded, and checked for supported
structure and faithful value representation before replacement. Invalid existing
destinations, serialization errors, or replacement failures leave the existing
file intact. Failed `load()` validation also leaves previous in-memory entries
intact. General concurrent-writer merging and locking are not provided.

### Deleting Values

```python
conf.delete("database.host")  # remove a leaf
conf.delete("database")       # remove all leaves in a section
conf.save()
```

`delete()` returns true when it removes at least one effective entry, including
entries with null values; it returns false for missing keys. With `reload=True`,
it reads the current file and saves through the validated comment-preserving
path. Failed automatic saves restore the entries before deletion. A deleted
default can reappear after a later load or reset; deletion does not create a
defaults tombstone.

Deleting a key removes its inline and clearly attached leading comments.
Deleting a section also removes descendant annotations. Document boundary
comments take priority over first/last-key ownership and are preserved.

### CLI Creation And Repair

```bash
confease init settings.yaml -i debug=true -i database.host=localhost
confease edit settings.yaml
confease settings.yaml -u debug=false -d database.host
```

`init` requires a missing destination; `edit` requires an existing one. `-f FMT`
overrides suffix inference without changing the path. Extensionless initialization
defaults to YAML; unknown suffixes and extensionless edits require a format.
Initial items and updates use YAML-typed `KEY=VALUE` arguments in every format;
retain value quotes with shell quoting, for example `-u 'label="true"'`.

Interactive CLI editing opens a draft even when the original file is invalid.
Validation failures report errors and reopen that same draft for correction.
Successful editor exit accepts valid content, which is installed as exact draft
bytes. Ctrl-C or editor failure cancels installation. Scripted updates and
deletions operate as one validated batch and require a valid source document.
Application-specific rules are not validated without an application schema.

## Editing Files Manually

Use `edit_file()` when you want users or maintainers to edit the configured file manually:

```python
from confease import Confease, TextEditor

conf = Confease("~/.config/my-app/conf.yaml", DEBUG=False)
conf.editor = TextEditor("code")
conf.edit_file()
```

`edit_file()` opens the actual configured path without generating a draft or rewriting its content. Comments and formatting remain under user control. The library creates missing parent directories but leaves creation of the file to a manual editor save. Closing without saving a missing file leaves it absent.

After the editor exits successfully, valid file contents are reloaded. Invalid manually saved content raises a parser or key-validation error and stays on disk; the last valid in-memory entries are retained. Fix and save the file before calling `load()` again. With `reload=True`, subsequent reads also attempt to load that file and will continue to raise until it is fixed.

### Migrating Existing Calls

Replace `conf.edit_file(user_only=True)` and `conf.edit_file(user_only=False)` with `conf.edit_file()`. Entry-origin filtering has been removed from editing because it opens the real file directly. The `user_only` parameter on `save()` is unchanged.

## Limitations

- Nested configuration keys support one level only.
- Environment loading only considers keys already known from defaults or loaded files.
- `save()` writes only `USR` entries by default; use `save(user_only=False)` to write the full effective configuration.
- Runtime-only configurations created without a path do not persist when saved.
- `__str__()` and `to_str()` are reserved for future printable representations and are not currently implemented.
