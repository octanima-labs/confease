# Troubleshooting

This page collects common issues that come from `confease`'s intentionally small configuration model.

## A Saved File Is Empty Or Missing Defaults

By default, `save()` writes only user-origin entries. Defaults passed to `Confease(...)` stay in memory unless you explicitly save the full effective configuration:

```python
conf.save(user_only=False)
```

Use the default behavior when your application should keep built-in defaults in code and only persist user preferences.

## Environment Variables Are Ignored

`reload_env()` only loads environment variables for keys that are already known from defaults or loaded files. Add a default or load a file containing the key before calling `reload_env()`:

```python
conf = Confease(items={"DEBUG": False})
conf.reload_env()
```

Environment values are parsed with `yaml.safe_load`, so `true` becomes `True`, `5432` becomes `5432`, and `null` becomes `None`.

## Nested Keys Raise A Collision Error

Nested keys support one level only, and scalar keys cannot share a name with a section. These shapes are invalid together:

```yaml
database: sqlite
database.host: localhost
```

Use either a scalar key or a section:

```yaml
database:
  host: localhost
  port: 5432
```

## A CLI Value Did Not Override A File

`reload_cli()` skips namespace attributes whose value is `None`. This is useful for optional flags because omitted CLI options do not erase lower-priority values.

If a non-`None` CLI value still does not win, check the configured `preference` order. The default order is:

```text
CLI > ENV > SYS > USR > DEF
```

## Editing A File Fails

Default editing validates on F2 or F3 (Accept & close). Invalid candidates stay in the same
session for correction without changing the destination. Common causes include a
non-mapping YAML file, unsupported nesting, a missing CSV `key,value` header, or
invalid XML shape. Ctrl+Q cancels; a missing target remains absent on cancellation.
Escape only dismisses an interaction; use F1 for keyboard help.

The embedded editor needs interactive terminal input and output. Run it in a
terminal rather than with redirected streams; use CLI updates/deletions for
scripts. The Edital dependency supplies Textual. Mixed LF/CRLF line endings and
bare-CR separators must be converted to uniform LF or CRLF before editing.

Edital 0.2.0 is available on PyPI and installed automatically as a dependency;
see [installation](installation.md) for setup instructions. Editor APIs must be imported
from `edital`, not `confease` or the removed `confease.tui_editor` module.

After an installation or backup failure, look for `Accepted editor text retained
at:` in CLI diagnostics or exception notes. That recovery file contains the
accepted candidate; correct the filesystem issue before retrying installation.

If an old call raises `TypeError` for `user_only`, replace
`edit_file(user_only=...)` with `edit_file()`; `save(user_only=...)` is still supported.

Library callers can choose an external editor explicitly:

```python
from confease import TextEditor

conf.editor = TextEditor("nano")
```

This requires the external executable and edits the real file. Invalid saves
remain on disk; fix them before `load()` or automatic reload. The explicit
external choice does not change the CLI's embedded editor.

## Template Restoration Fails

Template defaults are read without creating the target. Call `reset()` explicitly only when you want to overwrite the target with the exact template content. Check that the template exists, is valid for the configured parser, and uses supported keys. Invalid or missing templates leave previous file content and entries unchanged. A template-backed runtime-only configuration needs a target path before it can restore a file.
