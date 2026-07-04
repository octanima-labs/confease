# File Formats

`confease` can load and save several common configuration file formats. The parser is inferred from the path suffix when `parser=None` is used, or you can pass a parser class explicitly.

## Supported Suffixes

- `.yaml`, `.yml`
- `.json`
- `.toml`
- `.ini`, `.cfg`, `.conf`, `.config`
- `.xml`
- `.csv`

## YAML

YAML uses PyYAML and stores nested sections as ordinary YAML mappings:

```yaml
DEBUG: true
database:
  host: localhost
  port: 5432
```

## JSON

JSON uses the Python standard library and requires a top-level object:

```json
{
  "DEBUG": true,
  "database": {
    "host": "localhost",
    "port": 5432
  }
}
```

## TOML

TOML uses `tomllib` for reading and `tomli-w` for writing:

```toml
DEBUG = true

[database]
host = "localhost"
port = 5432
```

## INI, CFG, CONF, and CONFIG

INI-family formats use `configparser`. Top-level values are stored in `DEFAULT`, and one-level nested sections are stored as INI sections:

```ini
[DEFAULT]
DEBUG = true

[database]
host = localhost
port = 5432
```

Individual values are serialized as YAML scalar text and loaded with `yaml.safe_load`, so numbers, booleans, nulls, and simple lists recover their Python types.

## XML

XML uses a `<config>` root, `<entry>` leaves, and `<section>` elements for one-level nesting:

```xml
<?xml version="1.0"?>
<config>
  <entry key="DEBUG">true</entry>
  <section name="database">
    <entry key="host">localhost</entry>
    <entry key="port">5432</entry>
  </section>
</config>
```

Entry text is parsed with `yaml.safe_load`.

## CSV

CSV persists flat dotted keys with a `key,value` header:

```text
key,value
DEBUG,true
database.host,localhost
database.port,5432
```

CSV values are serialized as YAML scalar text and loaded with `yaml.safe_load`.

## Nesting Rules

All formats support at most one nested level. Internally, nested leaves are represented as dotted keys such as `database.host`.

Scalar keys and section keys cannot collide. For example, a config cannot contain both `database` and `database.host` as separate values.
