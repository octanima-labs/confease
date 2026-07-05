"""
Class to set a conf file programatically
Supports several parsers:
- yaml
- json
- cnf
- toml
- xml
- csv (no headings)

Conf is overriden in this way:
CLI > ENV > USER CONF > DEFAULT CONF
"""
from argparse import Namespace
from collections.abc import Mapping
import os
from pathlib import Path
import tempfile
from typing import Any

import yaml

from confease.editors import TextEditor
from confease.parsers import PARSER_CLASSES, PARSERS, Parser, Yaml



CLI = 'cli' # cli params
ENV = 'env' # Environment variables
SYS = 'system' # A file is SYS if it does not live in the home dir of the user
USR = 'user' # A file is SYS if it does live in the home dir of the user
DEF = 'default' # Bundled configuration
ORIGINS = [
    CLI,
    ENV,
    SYS,
    USR,
    DEF
]

class Confitem:
    """Single flattened configuration value with its source origin."""

    def __init__(self, key: str, value: Any, origin: str):
        """Create a config item, validating that the origin is supported."""
        self._key = str(key)
        self._value = value
        if origin in ORIGINS:
            self._origin = origin
        else:
            raise ValueError(f"Unknown origin '{origin}'. Allowed: {ORIGINS}")
    
    @property
    def key(self):
        """Return the flattened config key."""
        return self._key
    
    @property
    def value(self):
        """Return the stored value without coercion."""
        return self._value

    @property
    def origin(self):
        """Return the source origin that provided this value."""
        return self._origin
    
    def __eq__(self, other):
        """Compare by key for strings or by all fields for other items."""
        if isinstance(other, str):
            return other == self._key
        elif isinstance(other, Confitem):
            return (other.key, other.value, other.origin) == (self._key, self._value, self._origin)
        else:
            return False
    
    def __repr__(self):
        """Return a developer-friendly representation."""
        return f"Confitem<{self._key}, {self._value}, {self._origin}>"
    
    def __str__(self):
        """Return the string form of the stored value."""
        return str(self._value)
    


class Confease:
    """Configuration container with defaults, persistence, and source precedence."""

    def __init__(self, path: str | Path | None = None, reload: bool = False, parser: type[Parser] | None = Yaml, template: str | Path | None = None, preference = [CLI, ENV, SYS, USR, DEF], **kwargs):
        """Initialize a configuration object from optional defaults and file path."""
        if path is None:
            self._path: Path | None = None
            print("[-] Runtime-only configuration. No path provided, so conf file will not persist")
        else:
            self._path = Path(path).expanduser()
        self._reload = bool(reload) # if reload, changes are saved instantly and each time conf is accessed, it is readed from file; in this way the conf 'reloads' itself
        self._defaults: list[Confitem] = [Confitem(k, v, DEF) for k, v in self._flatten_mapping(kwargs).items()]
        self._entries: list[Confitem] | None = None
        self._preference: list[str] | None = None
        self._template: Path | None = None
        self._parser: type[Parser]
        self.editor = TextEditor()
        self.preference = preference


        if template:
            if len(kwargs.keys()) == 0:
                self._template = Path(template)
            else:
                raise AttributeError("Template and default values are not compatible. Use a single default source")
        if parser is None:
            if self._path is not None and self._path.suffix in PARSER_CLASSES:
                self._parser = PARSER_CLASSES[self._path.suffix]
            else:
                raise ValueError(f"Unknown parser '{parser}'. Allowed: {PARSERS}")
        else:
            if isinstance(parser, type) and issubclass(parser, Parser):
                self._parser = parser
            else:
                raise ValueError(f"Unknown parser '{parser}'. Allowed: {PARSERS}")

        if self._path is not None and self._path.exists():
            self.load()

    @property
    def preference(self):
        """Return source origins ordered from highest to lowest priority."""
        return self._preference

    @preference.setter
    def preference(self, value):
        """Set source precedence, appending any omitted origins after the provided ones."""
        if value is None:
            self._preference = list(ORIGINS)
        else:
            preference = list(value)
            unknown = [origin for origin in preference if origin not in ORIGINS]
            if unknown:
                raise ValueError(f"Unknown origin in preference: {unknown}. Allowed: {ORIGINS}")
            duplicates = [origin for origin in preference if preference.count(origin) > 1]
            if duplicates:
                raise ValueError(f"Duplicate origin in preference: {duplicates}")
            self._preference = preference + [origin for origin in ORIGINS if origin not in preference]

    def _origin_priority(self, origin: str) -> int:
        """Return the numeric precedence index for an origin."""
        if self._preference is None:
            self.preference = None
        if self._preference is None:
            raise RuntimeError("Preference was not initialized")
        return self._preference.index(origin)

    @staticmethod
    def _validate_key(key: str):
        """Validate that a key is scalar or one-level dotted notation."""
        parts = key.split(".")
        if len(parts) > 2 or any(part == "" for part in parts):
            raise ValueError(f"Nested configuration keys support one level only: {key}")

    @classmethod
    def _ensure_no_key_collisions(cls, keys):
        """Reject mixed scalar and section keys such as `database` and `database.host`."""
        scalar_keys: set[str] = set()
        section_keys: set[str] = set()
        for key in keys:
            cls._validate_key(key)
            parts = key.split(".")
            if len(parts) == 1:
                scalar_keys.add(key)
            else:
                section_keys.add(parts[0])
        collisions = sorted(scalar_keys & section_keys)
        if collisions:
            raise ValueError(f"Configuration key collides with nested section: {collisions}")

    @classmethod
    def _flatten_mapping(cls, data: Mapping[str, Any]) -> dict[str, Any]:
        """Flatten a mapping with one-level nested sections into dotted keys."""
        flat: dict[str, Any] = {}

        def add_item(key: str, value: Any):
            """Add a flattened item while detecting invalid or duplicate keys."""
            cls._validate_key(key)
            if key in flat:
                raise ValueError(f"Duplicate configuration key: {key}")
            flat[key] = value

        for raw_key, value in data.items():
            key = str(raw_key)
            if isinstance(value, Mapping):
                if "." in key:
                    raise ValueError(f"Nested configuration keys support one level only: {key}")
                for raw_subkey, subvalue in value.items():
                    if isinstance(subvalue, Mapping):
                        raise ValueError(f"Nested configuration keys support one level only: {key}.{raw_subkey}")
                    add_item(f"{key}.{raw_subkey}", subvalue)
            else:
                add_item(key, value)

        cls._ensure_no_key_collisions(flat.keys())
        return flat

    @classmethod
    def _nest_mapping(cls, data: Mapping[str, Any]) -> dict[str, Any]:
        """Convert flat dotted keys back into one-level nested sections."""
        cls._ensure_no_key_collisions(data.keys())
        nested: dict[str, Any] = {}
        for key, value in data.items():
            parts = key.split(".")
            if len(parts) == 1:
                nested[key] = value
            else:
                parent, child = parts
                section = nested.setdefault(parent, {})
                if not isinstance(section, dict):
                    raise ValueError(f"Configuration key collides with nested section: {parent}")
                section[child] = value
        return nested

    def _ensure_key_does_not_collide(self, key: str):
        """Reject setting a key that conflicts with existing scalar or section entries."""
        self._validate_key(key)
        if self._entries is None:
            return
        parts = key.split(".")
        if len(parts) == 1:
            prefix = f"{key}."
            if any(entry.key.startswith(prefix) for entry in self._entries):
                raise ValueError(f"Configuration key collides with nested section: {key}")
        else:
            parent = parts[0]
            if any(entry.key == parent for entry in self._entries):
                raise ValueError(f"Configuration key collides with nested section: {parent}")

    def _set_item(self, key: str, value: Any, origin: str, *, force: bool = False):
        """Set an item if allowed by precedence, or always when forced."""
        if self._entries is None:
            self.reset()
        if self._entries is None:
            self._entries = []

        self._ensure_key_does_not_collide(key)
        incoming = Confitem(key, value, origin)

        for index, entry in enumerate(self._entries):
            if entry == key:
                if force or self._origin_priority(incoming.origin) <= self._origin_priority(entry.origin):
                    self._entries[index] = incoming
                return
        self._entries.append(incoming)
    
    def load(self, path: str | Path | None = None):
        """Load configuration values from a file as user-origin entries."""
        # param path allows to override the load file
        load_path = Path(path).expanduser() if path is not None else self._path
        if load_path is None:
            raise FileNotFoundError("No configuration path provided")
        if not load_path.exists():
            raise FileNotFoundError(load_path)
        data = self._parser.load(load_path)

        self._entries = list(self._defaults)
        for key, value in self._flatten_mapping(data).items():
            self._set_item(str(key), value, USR, force=True)
        return
    
    def _data_for_save(self, user_only: bool = True) -> dict[str, Any]:
        """Return nested mapping data for persistence."""
        if self._entries is None:
            self.reset()
        entries = self._entries or []
        return self._nest_mapping(
            {entry.key: entry.value for entry in entries if not user_only or entry.origin == USR}
        )

    def save(self, user_only: bool = True):
        """Persist configuration to the instance path, optionally including all origins."""
        if self._path is None:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = self._data_for_save(user_only)
        self._parser.save(self._path, data)

    def reset(self):
        """Reset entries to defaults or reload from the configured template."""
        print("Setting default configuration...")
        if self._template:
            # TODO: copy self._template to self._path 
            self.load()
            return
        else:
            self._entries = list(self._defaults)
            return

    def get(self, key: str, default = None, cast = None):
        """Return a value or section by key, optionally casting the result."""
        item = self.get_item(key)
        val = item.value if item is not None else self._get_section(key)
        if val is None:
            return default
        if cast:
            try:
                val = cast(val)
            except Exception as e:
                print(f"[!] Unable to cast '{val}' into {cast}. {e}")
        return val
    
    def get_item(self, key: str) -> Confitem | None:
        """Return the matching config item, or None if no leaf item exists."""
        if self._entries is None:
            self.reset()
        elif self._reload:
            self.load()
        if self._entries is None:
            return None
        for entry in self._entries:
            if entry == key:
                return entry
        return None

    def _get_section(self, key: str) -> dict[str, Any] | None:
        """Return a plain dict for a one-level section, or None when absent."""
        if self._entries is None:
            return None
        self._validate_key(key)
        prefix = f"{key}."
        section = {entry.key.removeprefix(prefix): entry.value for entry in self._entries if entry.key.startswith(prefix)}
        return section or None

    def set(self, key: str, value: Any):
        """Store a user-origin value, supporting dotted keys and nested dict values."""
        items = self._flatten_mapping({key: value})
        for item_key, item_value in items.items():
            self._set_item(item_key, item_value, USR, force=True)
        if self._reload:
            self.save()

    def __getitem__(self, key: str):
        """Return `get(key)` so missing keys produce None."""
        return self.get(key)

    def __setitem__(self, key: str, value: Any):
        """Assign through `set(key, value)`."""
        self.set(key, value)
    
    def __str__(self):
        """Return a printable configuration representation (short version) once implemented."""
        # print the configuration in the console
        pass

    def to_str(self):
        """Return a printable configuration representation (detailed version) once implemented."""
        # print the configuration in the console
        pass
    
    def text_edit(self, user_only: bool = True):
        """Open the configured editor, validate changes, and persist them."""
        if self._path is None:
            raise FileNotFoundError("No configuration path provided")

        edit_path = self._path.expanduser()
        edit_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._data_for_save(user_only)
        draft_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=edit_path.suffix,
                prefix=f".{edit_path.name}.",
                dir=edit_path.parent,
                delete=False,
            ) as draft_file:
                draft_path = Path(draft_file.name)

            self._parser.save(draft_path, data)
            self.editor.open(draft_path)
            edited_data = self._parser.load(draft_path)
            self._flatten_mapping(edited_data)
            draft_path.replace(edit_path)
        finally:
            if draft_path is not None and draft_path.exists():
                draft_path.unlink()

        self.load()
        return self

    
    def load_sources(self, cli: Namespace | None = None, *files, preference: list[str] | None = None):
        """Reload file, environment, and CLI sources using configured precedence."""
        if preference is not None:
            self.preference = preference
        self.reload_files(*files)
        self.reload_env()
        if cli:
            self.reload_cli(cli)

    def reload_files(self, *paths):
        """Load additional config files as system or user origins."""
        for path in paths:
            load_path = Path(path).expanduser()
            if not load_path.exists():
                raise FileNotFoundError(load_path)

            parser = PARSER_CLASSES.get(load_path.suffix)
            if parser is None:
                raise ValueError(f"Unknown parser for '{load_path}'. Allowed: {PARSERS}")

            origin = USR if load_path.resolve().is_relative_to(Path.home().resolve()) else SYS
            for key, value in self._flatten_mapping(parser.load(load_path)).items():
                self._set_item(key, value, origin)
    
    def reload_cli(self, namespace: Namespace):
        """Load non-None argparse namespace values as CLI-origin entries."""
        data = {key: value for key, value in vars(namespace).items() if value is not None}
        for key, value in self._flatten_mapping(data).items():
            self._set_item(key, value, CLI)

    def reload_env(self):
        """Load known environment variables as ENV-origin entries with YAML parsing."""
        if self._entries is None:
            self.reset()
        entries = self._entries or []
        for key in {entry.key for entry in entries}:
            if key in os.environ:
                self._set_item(key, yaml.safe_load(os.environ[key]), ENV)
