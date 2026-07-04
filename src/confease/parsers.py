from collections.abc import Mapping
import csv
import json
from pathlib import Path
from typing import Any
import tomllib

import tomli_w
import yaml


YAML = '.yaml'
YML = '.yml'
JSON = '.json'
CFG = '.cfg' # ConfigParser
TOML = '.toml' # tomllib
INI = '.ini'
XML = '.xml'
CSV = '.csv'

PARSERS = [
    YAML,
    YML,
    JSON,
    CFG,
    TOML,
    INI,
    XML,
    CSV
]

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

class Cfg(Parser):
    extensions = (CFG,)

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
    extensions = (INI,)

class Xml(Parser):
    extensions = (XML,)

class Csv(Parser):
    extensions = (CSV,)

    @staticmethod
    def save(path: str | Path, data: Mapping[str, Any], **kwargs):
        save_path = Path(path).expanduser()
        with save_path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["key", "value"])
            writer.writeheader()
            for key, value in Csv._flatten(data).items():
                writer.writerow({"key": key, "value": str(value)})

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
                data[str(row["key"])] = row["value"]
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
    for parser in (Yaml, Json, Cfg, Toml, Ini, Xml, Csv)
    for extension in parser.extensions
}
