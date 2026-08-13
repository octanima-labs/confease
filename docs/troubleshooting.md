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

`edit_file()` validates the edited draft with the active parser before replacing the real file. Parser errors mean the previous file was kept. Re-open the file and fix the format-specific issue, such as a non-mapping YAML file, a missing CSV `key,value` header, or invalid XML shape.

If no editor opens, configure one explicitly:

```python
from confease import TextEditor

conf.editor = TextEditor("nano")
```
