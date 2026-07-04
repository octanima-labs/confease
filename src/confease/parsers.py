from collections.abc import Mapping
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


PARSER_CLASSES: dict[str, type[Parser]] = {
    extension: parser
    for parser in (Yaml, Json, Cfg, Toml, Ini, Xml, Csv)
    for extension in parser.extensions
}
