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
conf = Confease(DEBUG=False)
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

`edit_file()` opens the real file and validates it after the editor exits. If you manually save invalid content, that content remains on disk and the error is reported; the library does not restore the previous file. Previous in-memory entries remain intact. Re-open the file, fix the issue, save, and call `load()` again. Common causes include a non-mapping YAML file, unsupported nesting, a missing CSV `key,value` header, or invalid XML shape. With `reload=True`, reads continue to report the invalid file until it is fixed.

A missing file stays absent when the editor closes without saving. Save manually to create it. If an old call raises `TypeError` for `user_only`, replace `edit_file(user_only=...)` with `edit_file()`; `save(user_only=...)` is still supported.

If no editor opens, configure one explicitly:

```python
from confease import TextEditor

conf.editor = TextEditor("nano")
```

## Template Restoration Fails

Template defaults are read without creating the target. Call `reset()` explicitly only when you want to overwrite the target with the exact template content. Check that the template exists, is valid for the configured parser, and uses supported keys. Invalid or missing templates leave previous file content and entries unchanged. A template-backed runtime-only configuration needs a target path before it can restore a file.
