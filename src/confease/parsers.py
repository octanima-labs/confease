from collections.abc import Mapping
import configparser
import csv
import json
from pathlib import Path
from typing import Any
import tomllib
import xml.etree.ElementTree as ET

import tomli_w
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
    dumped = yaml.safe_dump(value, default_flow_style=True).strip()
    if dumped.endswith("\n..."):
        dumped = dumped[:-4]
    return dumped


def _load_value(value: str) -> Any:
    return yaml.safe_load(value)

class Parser:
    extensions: tuple[str, ...] = ()
    
    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        raise NotImplementedError("This parser is not implemented for saving yet")
    
    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        raise NotImplementedError("This parser is not implemented for loading yet")
    
class Yaml(Parser):
    extensions = (YAML, YML)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        with Path(path).expanduser().open("w") as file:
            yaml.safe_dump(dict(data), file, sort_keys=True)

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        load_path = Path(path).expanduser()
        with load_path.open() as file:
            data = yaml.safe_load(file)

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration file must contain a key-value mapping: {load_path}")
        return {str(key): value for key, value in data.items()}

class Json(Parser):
    extensions = (JSON,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        with Path(path).expanduser().open("w") as file:
            json.dump(dict(data), file, indent=2, sort_keys=True)
            file.write("\n")

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        load_path = Path(path).expanduser()
        with load_path.open() as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(f"Configuration file must contain a key-value mapping: {load_path}")
        return {str(key): value for key, value in data.items()}

class Toml(Parser):
    extensions = (TOML,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        Path(path).expanduser().write_text(tomli_w.dumps(dict(data)))

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        with Path(path).expanduser().open("rb") as file:
            return tomllib.load(file)

class Ini(Parser):
    extensions: tuple[str, ...] = (INI, CFG, CONF, CONFIG)

    @staticmethod
    def _new_config() -> configparser.ConfigParser:
        config = configparser.ConfigParser(interpolation=None)
        setattr(config, "optionxform", str)
        return config

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        config = Ini._new_config()
        for raw_key, value in data.items():
            key = str(raw_key)
            if isinstance(value, Mapping):
                config[key] = {}
                for raw_subkey, subvalue in value.items():
                    if isinstance(subvalue, Mapping):
                        raise ValueError(f"INI configuration keys support one nested level only: {key}.{raw_subkey}")
                    config[key][str(raw_subkey)] = _dump_value(subvalue)
            else:
                config["DEFAULT"][key] = _dump_value(value)

        with Path(path).expanduser().open("w") as file:
            config.write(file)

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
        config = Ini._new_config()
        load_path = Path(path).expanduser()
        with load_path.open() as file:
            config.read_file(file)

        data: dict[str, Any] = {key: _load_value(value) for key, value in config.defaults().items()}
        sections: dict[str, dict[str, str]] = getattr(config, "_sections")
        for section in config.sections():
            section_items = {
                key: _load_value(value)
                for key, value in sections[section].items()
                if key != "__name__"
            }
            data[section] = section_items
        return data


class Cfg(Ini):
    extensions: tuple[str, ...] = ()

class Xml(Parser):
    extensions = (XML,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        root = ET.Element("config")
        for raw_key, value in data.items():
            key = str(raw_key)
            if isinstance(value, Mapping):
                section = ET.SubElement(root, "section", {"name": key})
                for raw_subkey, subvalue in value.items():
                    if isinstance(subvalue, Mapping):
                        raise ValueError(f"XML configuration keys support one nested level only: {key}.{raw_subkey}")
                    Xml._append_entry(section, str(raw_subkey), subvalue)
            else:
                Xml._append_entry(root, key, value)

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(Path(path).expanduser(), encoding="unicode", xml_declaration=True)

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
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
        entry = ET.SubElement(parent, "entry", {"key": key})
        entry.text = _dump_value(value)

    @staticmethod
    def _read_entry(element: ET.Element) -> tuple[str, Any]:
        key = element.attrib.get("key")
        if not key:
            raise ValueError("XML entry elements must define a key attribute")
        if len(element):
            raise ValueError(f"XML entry elements cannot contain child elements: {key}")
        return key, yaml.safe_load(element.text or "")

class Csv(Parser):
    extensions = (CSV,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        save_path = Path(path).expanduser()
        with save_path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["key", "value"])
            writer.writeheader()
            for key, value in Csv._flatten(data).items():
                writer.writerow({"key": key, "value": _dump_value(value)})

    @staticmethod
    def load(path: str | Path, **kwargs) -> dict[str, Any]:
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
        flat: dict[str, Any] = {}
        for raw_key, value in data.items():
            key = str(raw_key)
            if isinstance(value, Mapping):
                for raw_subkey, subvalue in value.items():
                    if isinstance(subvalue, Mapping):
                        raise ValueError(f"CSV configuration keys support one nested level only: {key}.{raw_subkey}")
                    flat[f"{key}.{raw_subkey}"] = subvalue
            else:
                flat[key] = value
        return flat


PARSER_CLASSES: dict[str, type[Parser]] = {
    extension: parser
    for parser in (Yaml, Json, Toml, Ini, Xml, Csv)
    for extension in parser.extensions
}
