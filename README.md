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

The package requires Python 3.11 or newer. The `edital` dependency provides the
Textual editor. Interactive editing needs terminal input and output; no separately
installed editor application is required. Scripted edits do not start the TUI.

Edital 0.2.0 is available on PyPI and is installed automatically as a dependency
(`edital>=0.2.0,<0.3`). Hatch uses this published dependency for local development.
For pip-based development, install Confease in editable mode:

```bash
python -m pip install -e /path/to/confease/public
```

## Quickstart

### Command line

The installed `confease` command creates, edits, and restores configuration files:

```bash
# Open a new, preloaded buffer in the embedded terminal editor
confease init settings.yaml -i debug=true -i database.port=5432

# Preload an exact template; leave the target absent if you abandon the edit
confease init settings.yaml --template defaults.yaml

# Edit or repair an existing file interactively
confease edit settings.yaml
confease settings.yaml                 # shorthand for edit

# Apply a validated batch without opening an editor
confease settings.yaml -u database.host=localhost -u retries=3
confease edit settings.yaml -d obsolete -d database.port

# Keep the original before an interactive or scripted edit
confease edit settings.yaml -b
confease settings.yaml --backup -u retries=5

# Restore the latest matching backup, or choose a source explicitly
confease restore settings.yaml
confease restore settings.yaml --from settings-20261007-143052.yaml.bkp

# Back up the current version too, so another restore can undo this restore
confease restore settings.yaml -b
```

`-i/--item`, `-u/--update`, and `-d/--delete` are repeatable. Updates add or replace
values; the last assignment to the same leaf wins. A deletion names a leaf or an
entire section. Missing keys produce warnings and the batch continues. Supplying
any update or deletion selects noninteractive editing. A batch cannot update a
deleted leaf or a child of a deleted section, but deleting a scalar and adding a
child can convert it into a section.

`init --template PATH` is mutually exclusive with `--item`. It preloads exact
template text, using the format selected from the destination or `--format`
regardless of the template's suffix. **F2/F3 (Accept & close)** explicitly accepts the
buffer, including an unchanged template. Cancellation leaves the target absent.
Invalid templates fail before launch; invalid edits stay available for correction.

`init` refuses existing destinations, and `edit` requires an existing file. Format
selection uses `-f/--format` first, then a recognized suffix. Extensionless `init`
defaults to YAML; extensionless `edit`/`restore` and unknown suffixes require an override:

```bash
confease init settings -f toml -i debug=true
confease edit settings -f toml -u debug=false
```

Supported format names are `yaml`, `yml`, `json`, `toml`, `ini`, `cfg`, `conf`,
`config`, `xml`, and `csv`. A format override keeps the path unchanged; INI-family
suffixes use INI syntax. Use `./init`, `./edit`, or `./restore` to disambiguate files named after
commands, and `--` before paths starting with a dash.

Values use YAML syntax regardless of the file format:

```bash
confease settings.yaml -u enabled=true -u 'servers=[alpha, beta]'
confease settings.yaml -u 'label="true"' -u 'token=a=b=c'
```

Shell quoting differs from value quoting: `label="true"` reaches the command as
`label=true` and becomes a boolean, whereas `'label="true"'` retains the inner
quotes and becomes a string. YAML also interprets tokens such as `yes` as booleans.
Assignments split at the first `=`. Invalid keys and values that the destination
cannot represent (such as TOML `null`) are rejected before replacement.

Interactive `init` and `edit` use one embedded Textual session:

| Key | Action |
| --- | --- |
| **F1** | Show contextual keyboard help. |
| **F2 / F3** | Validate and accept the current text, then close. |
| **Ctrl-Q** | Cancel; changed text requires discard confirmation. |
| **Esc** | Dismiss help, a dialog, or search; otherwise leave the session open. |
| **F4** | Find text; Enter locates the next occurrence, wrapping to the start. |
| **F5** | Find/Replace, with replace-one and replace-all actions. |
| **Ctrl-Z / Ctrl-Y** | Undo / redo. |
| **Shift + arrows** | Select text. |
| **F7** | Select all. |

Find and Find/Replace support literal text or Python regular expressions.
Replacements are undoable and must pass configuration validation on acceptance.
Editing uses an in-memory buffer without cached or resumable drafts: accept to
install the changes, or cancel to discard them.

Validation errors appear in the same session, preserving text, cursor, and undo
history. Only accepted valid text is installed, preserving comments, formatting,
uniform LF/CRLF line endings, and final-newline presence. Mixed line endings and
bare-CR separators are rejected rather than silently normalized. Existing invalid
files can be opened for repair. Cancellation returns CLI status 130; other failures
return nonzero. The original destination stays untouched until installation.

If installation or backup fails after acceptance, the CLI reports a recovery file
containing the accepted text. Interactive invocation with redirected input or
output reports a terminal error; use `--update`/`--delete` for scripted editing.

Scripted edits require a valid source document and preserve comments through
round-trip document adapters. Unaffected order and formatting are retained where
supported, but structured edits are not byte-for-byte formatting guarantees.
Deleting a key removes its attached comments; document headers and footers remain.
Validation checks file syntax, supported key structure, and representability;
application-specific rules still belong to your application.

### Python library

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

`save()` preserves comments in existing YAML, TOML, INI-family, and XML files. It
reads the destination's latest document to retain externally edited comments,
then applies the selected in-memory values. External values are not implicitly
merged. Invalid destinations or unrepresentable output cause an error without
replacing the file. JSON has no comment syntax; CSV retains its `key,value` format.
Concurrent-writer merging and locking are not provided.

## Backups And Restore

Enable backups for an instance or for a single operation:

```python
conf = Confease("settings.yaml", __backup__=True)
conf.set("retries", 5)
conf.save()                       # inherits the instance policy
conf.save(backup=False)           # skips the snapshot for this save only
conf.edit_file(backup=True)       # snapshots after acceptance, before installation
conf.reset(backup=True)           # snapshots when restoring a template to disk

conf.restore()                   # latest matching sibling; inherits backup=True
conf.restore("older.snapshot", backup=False)  # explicit source, any filename
```

The constructor's `__backup__` option controls the instance policy; ordinary
`backup=` remains a configuration default. Backups are disabled by default.
On `save()`, `edit_file()`, `reset()`, and `restore()`, `backup=None`
inherits the instance policy; `True` or `False` overrides that operation only.
With `reload=True, __backup__=True`, every automatic save triggered by `set()`, indexed
assignment, or a successful `delete()` snapshots the previous file. Memory-only
operations and first writes to missing files have no previous document to back up.

The policy and a config key named `backup` can coexist:

```python
conf = Confease("settings.yaml", __backup__=True, backup="daily")
conf.get("backup")               # "daily" as a default unless the file overrides it
conf.save(backup=False)           # skips a snapshot; does not change the config key
```

Snapshots copy exact bytes, preserving original comments, formatting, and even
malformed content being repaired. They live beside the destination:

```text
settings-20261007-143052.yaml.bkp
settings-20261007-143052-001.yaml.bkp   # another snapshot in the same second
settings-20261007-143052-002.yaml.bkp
```

The timestamp uses local time in `YYYYMMDD-HHMMSS` form. Increasing collision
suffixes are padded to at least three digits; existing backups are never
overwritten. For `settings`, the name is `settings-20261007-143052.bkp`; for
`app.settings.toml`, it is `app.settings-20261007-143052.toml.bkp`.

Draft-based writes validate first, then back up immediately before replacement.
Cancelled or rejected embedded editing creates no snapshot, for both CLI and API
sessions. Explicit external API editing backs up before launching its editor, so
its snapshot remains even if no changes are saved. A backup failure aborts
replacement or direct editor launch. Complete
snapshots remain available if subsequent installation fails. Backups are not
pruned automatically; manage their retention as needed.

Without a source path, `restore()` selects a backup matching the destination's
exact name and extension, ordered by embedded timestamp and numeric suffix,
not modification time. With an explicit source it accepts any filename or
directory. It validates the exact candidate with the active parser, installs
the bytes without reserialization, retains the source, and reloads restored
values as user-origin entries with existing default fallbacks. Defaults and the
configured template do not change. Missing or invalid sources raise an error;
an invalid latest backup does not silently fall back to an older one.

Restore can create a missing destination or replace malformed content. The CLI
supports recovery without loading a broken destination first and chooses the
parser from the destination or `--format`, not from the backup's `.bkp` suffix:

```bash
confease restore settings --from history.json.bkp -f json -b
```

With backups enabled, restore selects its source **before** snapshotting the
current destination. Consecutive latest-backup restores therefore toggle
between versions, including within the same second. This assumes chronological
backup timestamps; a clock rollback or future-dated imported backup can change
which file is latest. Use an explicit source for deterministic recovery in that
case. Backups do not add locking or concurrent-writer merging.

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

Delete a leaf or a section explicitly:

```python
conf.delete("database.port")  # True if present, including a null-valued leaf
conf.delete("database")       # removes all leaves in the section
conf.delete("absent")         # False
conf.save()
```

With `reload=True`, deletion reads the current file and saves immediately. A
failed automatic save restores the entries before deletion. Deleting an
effective default does not create a tombstone: a later `load()` or `reset()` can
provide that default again. Origin-filtered values omitted by a user-only save
follow the same comment-removal policy as deleted values.

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

`edit_file()` preloads exact file text in the embedded editor without serializing
in-memory values. It returns the same configuration instance after acceptance or
cancellation:

```python
conf = Confease("settings.yaml", retries=3)
conf.edit_file()
```

F2 or F3 accepts validated text and installs it before updating live entries. Ctrl+Q
cancels, preserving the file and live entries, including unsaved in-memory values.
A missing file stays absent on cancellation. Parent directories are created when
needed for installation. Installation failure retains accepted text in a recovery
file and adds its path to the exception notes.

### Preload a missing file

Pass an edit-only template to show its contents automatically when the target
does not exist:

```python
conf = Confease("settings.yaml")
conf.edit_file(template="defaults.yaml")
```

The template is validated with the active parser before launch. Existing targets
open normally and ignore the template argument. This argument does not change the
instance's configured defaults or constructor template; to use the same file for
both, pass it explicitly to both the constructor and `edit_file()`. F2 or F3 creates the
target even if the preloaded text is unchanged. Installation refuses to overwrite
a target created during editing. First creation has no previous file to back up.

### Edital integration

The reusable editor now lives in the independent `edital` package. Import
`edit_text`, `TuiEditor`, `EditResult`, and `Validator` directly from `edital`;
Confease no longer exports editor APIs or contains a `confease.tui_editor` module.
See Edital's documentation for standalone text editing. Confease supplies its
parser/key validator and owns installation, backups, recovery files, and live
configuration synchronization. UI imports remain lazy.

### Explicit external editors

The public external launcher remains available for library consumers:

```python
from confease import TextEditor

conf.editor = TextEditor("code")
conf.edit_file()
```

This explicitly selected path edits the real file and validates after editor exit.
Invalid saves remain on disk while previous live entries are retained; enabled
backups happen before launch. External command discovery uses `EDITOR`, then
`VISUAL`, then available fallbacks, adding wait flags for known graphical editors.
It does not configure the default TUI or the CLI.

For missing-target template preloading, Vim/Neovim use native unsaved buffers;
other external commands use seeded drafts with best-effort filesystem save
detection. A detected save is validated before create-only installation. Saving
unchanged text is reliable in the TUI but best-effort for external draft editors.
Written fallback drafts are retained on failure with recovery paths in exception
notes. The external launcher still requires its executable to be installed.

**Upgrading:** Embedded transactional editing is now the default; explicitly
assign `TextEditor(...)` to keep direct-file behavior. Default backups now happen
after acceptance, not before launch. Replace `edit_file(user_only=...)` with
`edit_file()`; `save(user_only=...)` is unchanged.

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
