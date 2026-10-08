import configparser
import csv
import json
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

YAML = '.yaml'
YML = '.yml'
JSON = '.json'
CFG = '.cfg' # ConfigParser
CONF = '.conf'
CONFIG = '.config'
TOML = '.toml' # tomllib
INI = '.ini'
XML = '.xml'
CSV = '.csv'

PARSERS = [
    YAML,
    YML,
    JSON,
    CFG,
    CONF,
    CONFIG,
    TOML,
    INI,
    XML,
    CSV
]


def _dump_value(value: Any) -> str:
    """Serialize a scalar value as compact YAML text for flat formats."""
    dumped = yaml.safe_dump(value, default_flow_style=True).strip()
    return dumped.removesuffix("\n...")


def _load_value(value: str) -> Any:
    """Parse YAML scalar text back into a Python value."""
    return yaml.safe_load(value)


def _save_document(parser: type["Parser"], path: str | Path, data: Mapping[str, Any], *, backup: bool = False):
    """Use a fresh document baseline and validated replacement for writes."""
    from confease.documents import save_document

    save_document(parser, path, data, backup=backup)


class Parser:
    """Base parser interface for file-format implementations.

    Parser classes expose static ``save()`` and ``load()`` methods. ``Confease``
    calls parser classes directly and can infer a parser from
    :data:`PARSER_CLASSES` when ``parser=None`` is used.
    """

    extensions: tuple[str, ...] = ()
    
    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Save mapping data to a path.

        Args:
            path: Destination file path.
            data: Mapping to serialize. Nested-capable parsers accept one-level
                nested mappings.
            **kwargs: Reserved for parser-specific options.

        Raises:
            NotImplementedError: Always raised by the base class.
        """
        raise NotImplementedError("This parser is not implemented for saving yet")
    
    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Load mapping data from a path.

        Args:
            path: Source file path.
            **kwargs: Reserved for parser-specific options.

        Returns:
            A dictionary containing scalar values or one-level nested mappings.

        Raises:
            NotImplementedError: Always raised by the base class.
        """
        raise NotImplementedError("This parser is not implemented for loading yet")


class Yaml(Parser):
    """YAML semantic loader with comment-preserving round-trip writes.

    YAML files must contain a top-level mapping. Empty files load as an empty
    mapping.
    """

    extensions = (YAML, YML)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Write validated YAML while preserving existing comments."""
        _save_document(Yaml, path, data, backup=kwargs.get("backup", False))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Read YAML data and require a top-level mapping.

        Raises:
            ValueError: If the file does not contain a top-level mapping.
        """
        load_path = Path(path).expanduser()
        with load_path.open() as file:
            data = yaml.safe_load(file)

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration file must contain a key-value mapping: {load_path}")  # noqa: TRY004 - invalid document shape is a value error
        return {str(key): value for key, value in data.items()}


class Json(Parser):
    """JSON parser using the Python standard library.

    JSON files must contain a top-level object. Files are written with stable
    key order and two-space indentation.
    """

    extensions = (JSON,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Replace the file with complete validated JSON."""
        _save_document(Json, path, data, backup=kwargs.get("backup", False))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Read JSON data and require a top-level mapping.

        Raises:
            ValueError: If the file does not contain a top-level object.
        """
        load_path = Path(path).expanduser()
        with load_path.open() as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(f"Configuration file must contain a key-value mapping: {load_path}")  # noqa: TRY004 - invalid document shape is a value error
        return {str(key): value for key, value in data.items()}


class Toml(Parser):
    """TOML semantic loader with ``tomlkit`` round-trip writes.

    TOML naturally supports one-level sections as tables.
    """

    extensions = (TOML,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Write validated TOML while preserving existing comments."""
        _save_document(Toml, path, data, backup=kwargs.get("backup", False))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Read TOML mapping data."""
        with Path(path).expanduser().open("rb") as file:
            return tomllib.load(file)


class Ini(Parser):
    """INI-family parser using ConfigParser sections for one-level nesting.

    Top-level values are stored in ``DEFAULT``. Section values are stored as
    ordinary INI sections. Individual values are serialized as YAML scalar text
    so booleans, numbers, nulls, and simple lists can round-trip as Python
    values.
    """

    extensions: tuple[str, ...] = (INI, CFG, CONF, CONFIG)

    @staticmethod
    def _new_config() -> configparser.ConfigParser:
        """Create a case-preserving ConfigParser without interpolation."""
        config = configparser.ConfigParser(interpolation=None)
        setattr(config, "optionxform", str)  # noqa: B010 - ConfigParser supports this hook; direct method assignment fails type checking
        return config

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Write mapping data as INI, storing values as YAML scalar text.

        Raises:
            ValueError: If nested mappings exceed one level.
        """
        _save_document(Ini, path, data, backup=kwargs.get("backup", False))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Read INI data and parse values from YAML scalar text."""
        config = Ini._new_config()
        load_path = Path(path).expanduser()
        with load_path.open() as file:
            config.read_file(file)

        data: dict[str, Any] = {key: _load_value(value) for key, value in config.defaults().items()}
        sections: dict[str, dict[str, str]] = getattr(config, "_sections")  # noqa: B009 - private attribute is absent from ConfigParser type stubs
        for section in config.sections():
            section_items = {
                key: _load_value(value)
                for key, value in sections[section].items()
                if key != "__name__"
            }
            data[section] = section_items
        return data


class Cfg(Ini):
    """Compatibility alias for INI-style parsing."""

    extensions: tuple[str, ...] = ()


class Xml(Parser):
    """XML parser using ``entry`` leaves and one-level ``section`` elements.

    XML files use a ``<config>`` root. Entry text is serialized as YAML scalar
    text so supported scalar values can round-trip as Python values.
    """

    extensions = (XML,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Write mapping data as XML with YAML-typed entry text.

        Raises:
            ValueError: If nested mappings exceed one level.
        """
        _save_document(Xml, path, data, backup=kwargs.get("backup", False))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Read XML data and validate the supported config shape.

        Raises:
            ValueError: If the XML root, element names, required attributes, or
                duplicate keys do not match the supported configuration shape.
        """
        load_path = Path(path).expanduser()
        root = ET.parse(load_path).getroot()
        if root.tag != "config":
            raise ValueError(f"XML configuration root must be <config>: {load_path}")

        data: dict[str, Any] = {}
        for element in root:
            if element.tag == "entry":
                key, value = Xml._read_entry(element)
                if key in data:
                    raise ValueError(f"Duplicate XML configuration key: {key}")
                data[key] = value
            elif element.tag == "section":
                name = element.attrib.get("name")
                if not name:
                    raise ValueError("XML section elements must define a name attribute")
                if name in data:
                    raise ValueError(f"Duplicate XML configuration key: {name}")
                section: dict[str, Any] = {}
                for child in element:
                    if child.tag != "entry":
                        raise ValueError(f"XML sections may only contain entry elements: {name}")
                    key, value = Xml._read_entry(child)
                    if key in section:
                        raise ValueError(f"Duplicate XML configuration key: {name}.{key}")
                    section[key] = value
                data[name] = section
            else:
                raise ValueError(f"Unsupported XML configuration element: {element.tag}")
        return data

    @staticmethod
    def _append_entry(parent: ET.Element, key: str, value: Any):
        """Append an XML entry element under a parent element."""
        entry = ET.SubElement(parent, "entry", {"key": key})
        entry.text = _dump_value(value)

    @staticmethod
    def _read_entry(element: ET.Element) -> tuple[str, Any]:
        """Read an XML entry element into a key and typed Python value."""
        key = element.attrib.get("key")
        if not key:
            raise ValueError("XML entry elements must define a key attribute")
        if len(element):
            raise ValueError(f"XML entry elements cannot contain child elements: {key}")
        return key, yaml.safe_load(element.text or "")


class Csv(Parser):
    """CSV parser with a ``key,value`` header and flat dotted keys.

    CSV stores every value as a flat row. Nested sections are written as dotted
    keys such as ``database.host``. Values are serialized as YAML scalar text so
    simple Python values can round-trip.
    """

    extensions = (CSV,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Write mapping data as CSV, flattening nested sections.

        Raises:
            ValueError: If nested mappings exceed one level.
        """
        _save_document(Csv, path, data, backup=kwargs.get("backup", False))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Read CSV data and parse each value from YAML scalar text.

        Raises:
            ValueError: If the header is not exactly ``key,value`` or a row is
                malformed.
        """
        load_path = Path(path).expanduser()
        with load_path.open(newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames != ["key", "value"]:
                raise ValueError(f"CSV configuration file must use header: key,value: {load_path}")
            data: dict[str, Any] = {}
            for row in reader:
                if set(row) != {"key", "value"} or row["key"] in [None, ""] or row["value"] is None:
                    raise ValueError(f"Malformed CSV configuration row: {row}")
                data[str(row["key"])] = _load_value(row["value"])
        return data

    @staticmethod
    def _flatten(data: Mapping[str, Any]) -> dict[str, Any]:
        """Flatten nested mapping sections into dotted keys for CSV output."""
        flat: dict[str, Any] = {}
        for raw_key, value in data.items():
            key = str(raw_key)
            if isinstance(value, Mapping):
                for raw_subkey, subvalue in value.items():
                    if isinstance(subvalue, Mapping):
                        raise ValueError(f"CSV configuration keys support one nested level only: {key}.{raw_subkey}")  # noqa: TRY004 - invalid config shape is a value error
                    flat[f"{key}.{raw_subkey}"] = subvalue
            else:
                flat[key] = value
        return flat


PARSER_CLASSES: dict[str, type[Parser]] = {
    extension: parser
    for parser in (Yaml, Json, Toml, Ini, Xml, Csv)
    for extension in parser.extensions
}
