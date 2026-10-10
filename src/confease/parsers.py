import configparser
import csv
import json
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from confease.mappings import flatten, flatten_items, nest, normalized, validate_key

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
    return yaml.load(value, Loader=ConfigurationLoader)


class ConfigurationLoader(yaml.SafeLoader):
    """Retain safe YAML semantics while rejecting duplicate explicit keys."""

    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, (str, int, float, bool, type(None))):
                if key in keys:
                    raise ValueError(f"Duplicate configuration key: {key}")
                keys.add(key)
        return super().construct_mapping(node, deep=deep)


def _json_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject JSON duplicate keys before object construction loses them."""
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = value
    return result


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
            data: Mapping to serialize, with arbitrary-depth mappings, dotted
                paths, empty mappings, and format-supported terminal values.
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
            A canonical nested dictionary. Dotted file paths are reconstructed
            into hierarchy, including CSV row keys and INI section names.

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
            data = yaml.load(file, Loader=ConfigurationLoader)

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration file must contain a key-value mapping: {load_path}")  # noqa: TRY004 - invalid document shape is a value error
        return normalized(data)


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
            data = json.load(file, object_pairs_hook=_json_object)

        if not isinstance(data, dict):
            raise ValueError(f"Configuration file must contain a key-value mapping: {load_path}")  # noqa: TRY004 - invalid document shape is a value error
        return normalized(data)


class Toml(Parser):
    """TOML semantic loader with ``tomlkit`` round-trip writes.

    TOML supports arbitrary-depth native tables. Unsupported values such as
    ``None`` raise on save rather than being coerced or marker-encoded.
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
            return normalized(tomllib.load(file))


class Ini(Parser):
    """INI-family parser using dotted section names for arbitrary nesting.

    Top-level values are stored in ``DEFAULT``. Section values are stored as
    ordinary INI sections named by their full parent path. Individual values
    use YAML text so booleans, numbers, nulls, lists containing mappings, and
    empty mappings can round-trip. Loading merges section paths into a tree.
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
            ValueError: If paths conflict or emitted values cannot round-trip.
        """
        _save_document(Ini, path, data, backup=kwargs.get("backup", False))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Read INI data and parse values from YAML scalar text."""
        config = Ini._new_config()
        load_path = Path(path).expanduser()
        with load_path.open() as file:
            config.read_file(file)

        items = [(key, _load_value(value)) for key, value in config.defaults().items()]
        empty_sections = []
        sections: dict[str, dict[str, str]] = getattr(config, "_sections")  # noqa: B009 - private attribute is absent from ConfigParser type stubs
        for section in config.sections():
            validate_key(section)
            section_items = [
                (f"{section}.{key}", _load_value(value))
                for key, value in sections[section].items()
                if key != "__name__"
            ]
            items.extend(section_items)
            if not section_items:
                empty_sections.append(section)
        flat = flatten_items(items)
        for section in empty_sections:
            # An empty parent header with a child section declares hierarchy,
            # not an extra terminal that would collide with its descendants.
            if any(key.startswith(f"{section}.") for key in flat):
                continue
            if any(other.startswith(f"{section}.") for other in empty_sections):
                continue
            items.append((section, {}))
        return nest(flatten_items(items))


class Cfg(Ini):
    """Compatibility alias for INI-style parsing."""

    extensions: tuple[str, ...] = ()


class Xml(Parser):
    """XML parser using ``entry`` leaves and recursive ``section`` elements.

    XML files use a ``<config>`` root. Entry text is serialized as YAML scalar
    text so supported scalar values can round-trip as Python values.
    """

    extensions = (XML,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Write mapping data as XML with YAML-typed entry text.

        Raises:
            ValueError: If paths conflict or emitted values cannot round-trip.
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

        def read_mapping(parent: ET.Element) -> dict[str, Any]:
            items: list[tuple[str, Any]] = []
            seen: set[str] = set()
            for element in parent:
                if element.tag == "entry":
                    key, value = Xml._read_entry(element)
                elif element.tag == "section":
                    name = element.attrib.get("name")
                    if not name:
                        raise ValueError("XML section elements must define a name attribute")
                    key, value = name, read_mapping(element)
                else:
                    raise ValueError(f"Unsupported XML configuration element: {element.tag}")
                if key in seen:
                    raise ValueError(f"Duplicate XML configuration key: {key}")
                seen.add(key)
                items.append((key, value))
            return nest(flatten_items(items))

        return read_mapping(root)

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
        return key, _load_value(element.text or "")


class Csv(Parser):
    """CSV parser with a ``key,value`` header and flat dotted keys.

    CSV stores every value as a flat row. Nested sections are written as dotted
    keys such as ``database.host``. Values are serialized as YAML scalar text so
    supported Python values, including lists and empty mappings, can round-trip.
    Loading returns reconstructed nested dictionaries, not flat row keys.
    """

    extensions = (CSV,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        """Write mapping data as CSV, flattening nested sections.

        Raises:
            ValueError: If paths conflict or emitted values cannot round-trip.
        """
        _save_document(Csv, path, data, backup=kwargs.get("backup", False))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        """Read YAML-typed rows and reconstruct their dotted paths into a tree.

        Raises:
            ValueError: If the header is not exactly ``key,value`` or a row is
                malformed, duplicates a logical path, or conflicts with a section.
        """
        load_path = Path(path).expanduser()
        with load_path.open(newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames != ["key", "value"]:
                raise ValueError(f"CSV configuration file must use header: key,value: {load_path}")
            items: list[tuple[str, Any]] = []
            for row in reader:
                if set(row) != {"key", "value"} or row["key"] in [None, ""] or row["value"] is None:
                    raise ValueError(f"Malformed CSV configuration row: {row}")
                items.append((str(row["key"]), _load_value(row["value"])))
        return nest(flatten_items(items))

    @staticmethod
    def _flatten(data: Mapping[str, Any]) -> dict[str, Any]:
        """Flatten nested mapping sections into dotted keys for CSV output."""
        return flatten(data)


PARSER_CLASSES: dict[str, type[Parser]] = {
    extension: parser
    for parser in (Yaml, Json, Toml, Ini, Xml, Csv)
    for extension in parser.extensions
}
