# File Formats

`confease` can load and save several common configuration file formats. The parser is inferred from the path suffix when `parser=None` is used, or you can pass a parser class explicitly.

## Supported Suffixes

- `.yaml`, `.yml`
- `.json`
- `.toml`
- `.ini`, `.cfg`, `.conf`, `.config`
- `.xml`
- `.csv`

Pass `parser=None` to infer one of these parsers from the configured path suffix:

```python
from confease import Confease

conf = Confease("settings.toml", parser=None)
```

Pass a parser class when you want to be explicit:

```python
from confease import Confease, Json

conf = Confease("settings.json", parser=Json)
```

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

TOML uses `tomllib` for semantic reading and `tomlkit` for comment-preserving writing:

```toml
DEBUG = true

[database]
host = "localhost"
port = 5432
```

## INI, CFG, CONF, and CONFIG

INI-family formats use `configparser`. Top-level values are stored in `DEFAULT`, and nested parent paths become dotted INI section names:

```ini
[DEFAULT]
DEBUG = true

[database]
host = localhost
port = 5432
```

Individual values are serialized as YAML scalar text and loaded with `yaml.safe_load`, so numbers, booleans, nulls, and simple lists recover their Python types.

## XML

XML uses a `<config>` root, `<entry>` leaves, and recursively nested `<section>` elements:

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

All built-in formats support arbitrary-depth configuration paths. YAML, JSON, and
TOML use native hierarchy, XML nests sections recursively, INI encodes parent paths
in section names such as `[database.primary.connection]`, and CSV writes full
terminal paths such as `database.primary.connection.host`. INI section order does
not change the reconstructed mapping. Internally, each terminal has a dotted key
and its own origin. Lists, including lists containing mappings, remain whole values.

Dots are reserved path separators, including in mapping keys. Empty path segments,
duplicate logical paths, and scalar/section collisions at any depth are rejected.
For example, a config cannot contain both `database.primary` as a scalar and
`database.primary.host` as a descendant value.

Empty mappings survive round trips. INI and CSV can encode them as YAML `{}`
values: `units = {}` in `[DEFAULT]` or the CSV row `units,{}`. An existing empty INI
header also represents an empty mapping; an empty parent header with descendant
sections represents the parent hierarchy instead. YAML/JSON/TOML/XML retain
native empty mapping, table, or section nodes.

## Direct Parser API And CSV Migration

Every built-in parser accepts the same nested mapping for saving and returns a
canonical nested mapping on load, including when the input uses dotted keys.
Direct `Csv.load()` previously returned flat dotted keys; migrate those callers
to nested access:

```python
from confease import Csv, Toml

data = Csv.load("settings.csv")
data["database"]["host"]  # formerly data["database.host"]
Toml.save("settings.toml", data)
```

Dotted lookups through `Confease` remain available. For a complete deep example
in YAML, TOML, INI, XML, and CSV, see the README's File Formats section.

## Type Round-Tripping

YAML, JSON, and TOML rely on their native type systems. INI, XML, and CSV store individual values as YAML scalar text and parse them with `yaml.safe_load`, which preserves common scalar values such as booleans, numbers, nulls, and simple lists.

This means strings that look like YAML scalars may load as non-string Python values. Quote values in the file when you need to force a string representation.

Round-trip validation compares types as well as values. Format conversion is
lossless for supported values, not a universal conversion of arbitrary Python
objects. TOML has no null value; saving a configuration containing `None` as TOML
fails explicitly without replacing the destination. No marker encoding or silent
string conversion is used. JSON similarly cannot represent native Python dates.
