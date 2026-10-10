# Configuration Model

`Confease` stores configuration values as flattened `Confitem` leaves. Each item has a key, a value, and an origin that records where the value came from.

## Source Origins

The supported origins are:

- `CLI`: values from an `argparse.Namespace` passed to `load_sources()` or `reload_cli()`.
- `ENV`: environment variables loaded by `reload_env()`.
- `SYS`: config files outside the current user's home directory.
- `USR`: config files inside the current user's home directory and values assigned with `set()`.
- `DEF`: defaults supplied through `items` or values read from a configured template.

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

Defaults are passed in the `items` dictionary:

```python
conf = Confease(
    items={
        "DEBUG": False,
        "PORT": 8000,
        "database": {"host": "localhost", "port": 5432},
    },
)
```

Defaults are memory-only unless explicitly saved. By default, `save()` writes only user-origin entries. Use `save(user_only=False)` to write all current entries, including defaults and loaded overrides.

Omitted `items`, `items=None`, and `items={}` provide no defaults. Other input types
raise `TypeError`. Configuration keys can use any constructor option name:

```python
conf = Confease(
    "settings.yaml",
    backup=True,
    items={"backup": "daily", "path": "/srv/data", "items": "application-value"},
)
conf["backup"]  # "daily", independently of the enabled backup policy
```

For the constructor migration, replace `Confease(DEBUG=False)` with
`Confease(items={"DEBUG": False})`, and replace `__backup__=True` with `backup=True`.
The old constructor keywords raise `TypeError`; there is no legacy alias.

### Templates And Explicit Reset

Alternatively, provide an existing template file instead of `items` defaults:

```python
conf = Confease("settings.yaml", template="defaults.yaml")
```

Both files use the configured active parser. Template values become `DEF` defaults and provide fallbacks for keys absent from the target. Existing target values load as `USR`. Initializing or reading configuration does not create a missing target or overwrite an existing one.

To deliberately restore the persisted file, call:

```python
conf.reset()
```

With a template, this is a destructive restore: it validates the template, copies its exact bytes over the configured path, and reloads the restored values as `USR`. Comments, formatting, and key order are preserved. Missing parent directories are created. Missing or invalid templates and copy failures leave prior file content and entries unchanged.

Template restoration requires a configured target path; a template-backed runtime-only instance raises `FileNotFoundError` on `reset()`. Without a template, `reset()` only restores `items` defaults in memory and does not write or delete a file. Templates cannot be combined with nonempty `items`; omitted, `None`, or empty `items` are allowed.

## Deferred Loading And Recovery

Construction normally loads an existing destination immediately. The keyword-only
`autoload=False` option binds the destination without parsing it or creating any
files, directories, or backups. Parser, preference, `items`, and configured
template validation still occur.

The first ordinary operation loads an existing destination or initializes defaults
if it is absent. This includes reads, indexed access, `set()`, `delete()`, `save()`,
and all source-overlay methods. Unrelated destination values initialize before a
mutation or save; known file keys are available for environment overlays. Failed
loading leaves deferred state intact and can be retried after external repair.

Recovery bypasses ordinary initialization:

```python
conf = Confease("settings.yaml", autoload=False, backup=True)
conf.edit_file()  # repair exact malformed text transactionally

conf = Confease("settings.yaml", template="defaults.yaml", autoload=False)
conf.reset(backup=True)  # install exact validated template bytes

conf = Confease("settings.yaml", autoload=False)
conf.restore(backup=True)  # latest matching backup
# conf.restore("historical.snapshot", backup=True)  # explicit source
```

Cancellation or failed recovery preserves deferred state and original content.
Successful recovery or explicit `load(alternate_path)` establishes initialized
entries; later ordinary access with `reload=False` does not load over them. Without
a template, `reset()` deliberately initializes defaults without reading the target.

With `reload=True`, first ordinary use initializes once and later operations retain
their automatic reload/save behavior. A missing target supplies defaults on first
use without being created; subsequent automatic reads require the target to exist.

Keep application defaults named `autoload` in `items`, independently of the option:

```python
conf = Confease(autoload=False, items={"autoload": "application-value"})
```

## Environment Variables

`reload_env()` imports only environment variables whose keys are already known from defaults or loaded files. Values are parsed with `yaml.safe_load`, so common scalar text recovers Python types:

```bash
export DEBUG=true
export PORT=5432
```

```python
conf = Confease(items={"DEBUG": False, "PORT": 8000})
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

For nested values, pass an arbitrary-depth dictionary in the namespace value. It is flattened into dotted paths:

```python
conf.reload_cli(Namespace(database={"host": "db.internal"}))

conf["database.host"]
```

## Persistence

Call `save()` to persist configuration back to the path configured on the `Confease` instance:

```python
conf = Confease("~/.config/my-app/conf.yaml", items={"DEBUG": False})
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

Interactive CLI editing preloads exact text even when the original file is invalid.
F2 or F3 validates and accepts it; errors stay in the same session with
text, cursor, and undo history intact. Ctrl+Q cancels with discard confirmation
for changed text; Escape dismisses interactions. F1 shows keyboard help, F4 opens
Find, and F5 opens Find/Replace, with literal and Python-regex modes. Only accepted valid text is installed without
reserialization. Cancellation returns status 130; editor failures do not install
content. Scripted updates and
deletions operate as one validated batch and require a valid source document.
Application-specific rules are not validated without an application schema.
Editing buffers are memory-only: changes are accepted or discarded, without
cached or resumable drafts. Backups preserve previous committed file content.

## Editing Files Manually

Use `edit_file()` when you want users or maintainers to edit the configured file manually:

```python
from confease import Confease

conf = Confease("~/.config/my-app/conf.yaml", items={"DEBUG": False})
conf.edit_file()
```

The embedded Textual editor preloads the exact document, preserving comments,
whitespace, uniform LF/CRLF line endings, and trailing-newline presence. Mixed line
endings and bare-CR separators are rejected before launch. F2 or F3 validates and accepts
the buffer, then Confease installs it atomically and updates live entries. Ctrl+Q cancels and
preserves destination content and prior live entries, including unsaved values.
Missing targets stay absent on cancellation. No external editor executable is needed.

`conf.edit_file(template="defaults.yaml")` preloads a validated edit-only template
for a missing target. Accepting unchanged text still creates the target; an existing
target ignores the template. This does not change configured defaults. Create-only
installation refuses a target created during editing.

Enabled backups are taken after acceptance and validation, immediately before
installation; cancellation creates none. If backup or installation fails, previous
content and live entries remain intact, and exception notes identify a recovery
file containing accepted text.

To retain external direct-file behavior explicitly:

```python
from confease import TextEditor

conf.editor = TextEditor("code")
conf.edit_file()
```

That path backs up before launch and validates after editor exit. Invalid saves
remain on disk with previous live entries intact. With `reload=True`, subsequent
reads continue to report invalid file content until repaired. Native Vim/Neovim
template preloading and best-effort seeded drafts for other external commands
remain available. They do not affect default CLI editing.

Confease imports its editor from the independent `edital` package. Editor APIs
(`edit_text`, `TuiEditor`, `EditResult`, and `Validator`) are exported only by
`edital`; standalone usage and canonical editor API contracts are documented
there. Confease owns configuration validation, installation, backups, recovery,
and live-entry synchronization. Its [external launcher reference](api/editors.rst)
remains generated from Confease's source docstrings.

### Migrating Existing Calls

Embedded transactional editing replaces the default external/direct-file workflow.
Assign `TextEditor(...)` explicitly if that behavior is needed. Default manual-edit
backups now happen just before installation rather than before launch. Replace
`conf.edit_file(user_only=...)` with `conf.edit_file()`; editing preloads document
text rather than origin-filtered values. The `user_only` parameter on `save()` is unchanged.

## Limitations

- Dots are reserved path separators; empty segments, duplicate logical paths, and scalar/section collisions at any depth are rejected.
- Lists remain whole values without indexed configuration paths. Empty mappings retain presence and origins.
- Persistence requires values supported by the target format; TOML nulls and JSON native Python dates are unsupported.
- Environment loading only considers keys already known from defaults or loaded files.
- `save()` writes only `USR` entries by default; use `save(user_only=False)` to write the full effective configuration.
- Runtime-only configurations created without a path do not persist when saved.
- `__str__()` and `to_str()` are reserved for future printable representations and are not currently implemented.
