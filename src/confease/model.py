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
from pathlib import Path

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
    def __init__(self, key: str, value, origin: str):
        self._key = str(key)
        self._value = str(value)
        if origin in ORIGINS:
            self._origin = origin
        else:
            raise ValueError(f"Unknown origin '{origin}'. Allowed: {ORIGINS}")
    
    @property
    def key(self):
        return self._key
    
    @property
    def value(self):
        return self._value

    @property
    def origin(self):
        return self._origin
    
    def __eq__(self, other):
        if isinstance(other, str):
            return other == self._key
        elif isinstance(other, Confitem):
            return (other.key, other.value, other.origin) == (self._key, self._value, self._origin)
        else:
            return False
    
    def __repr__(self):
        return f"Confitem<{self._key}, {self._value}, {self._origin}>"
    
    def __str__(self):
        return self._value
    


class Confease:
    def __init__(self, path: str | Path | None = None, reload: bool = False, parser: type[Parser] | None = Yaml, template: str | Path | None = None, preference = [CLI, ENV, SYS, USR, DEF], **kwargs):
        if path is None:
            self._path: Path | None = None
            print("[-] Runtime-only configuration. No path provided, so conf file will not persist")
        else:
            self._path = Path(path).expanduser()
        self._reload = bool(reload) # if reload, changes are saved instantly and each time conf is accessed, it is readed from file; in this way the conf 'reloads' itself
        self._defaults: list[Confitem] = [Confitem(k, v, DEF) for k, v in kwargs.items()]
        self._entries: list[Confitem] | None = None
        self._preference: list[str] | None = None
        self._template: Path | None = None
        self._parser: type[Parser]
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
        return self._preference

    @preference.setter
    def preference(self, value):
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
        if self._preference is None:
            self.preference = None
        if self._preference is None:
            raise RuntimeError("Preference was not initialized")
        return self._preference.index(origin)

    def _set_item(self, key: str, value, origin: str, *, force: bool = False):
        incoming = Confitem(key, value, origin)
        if self._entries is None:
            self.reset()
        if self._entries is None:
            self._entries = []

        for index, entry in enumerate(self._entries):
            if entry == key:
                if force or self._origin_priority(incoming.origin) <= self._origin_priority(entry.origin):
                    self._entries[index] = incoming
                return
        self._entries.append(incoming)
    
    def load(self, path: str | Path | None = None):
        # param path allows to override the load file
        load_path = Path(path).expanduser() if path is not None else self._path
        if load_path is None:
            raise FileNotFoundError("No configuration path provided")
        if not load_path.exists():
            raise FileNotFoundError(load_path)
        data = self._parser.load(load_path)

        self._entries = list(self._defaults)
        for key, value in data.items():
            self._set_item(str(key), value, USR, force=True)
        return
    
    def save(self):
        if self._path is None:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        entries = self._entries or []
        data = {entry.key: entry.value for entry in entries if entry.origin == USR}
        self._parser.save(self._path, data)

    def reset(self):
        print("Setting default configuration...")
        if self._template:
            # TODO: copy self._template to self._path 
            self.load()
            return
        else:
            self._entries = list(self._defaults)
            return

    def get(self, key: str, default = None, cast = None):
        item = self.get_item(key)
        if item is None:
            return default
        val = item.value
        if cast:
            try:
                val = cast(val)
            except Exception as e:
                print(f"[!] Unable to cast '{val}' into {cast}. {e}")
        return val
    
    def get_item(self, key: str) -> Confitem | None:
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

    def set(self, key: str, value: str):
        self._set_item(key, value, USR, force=True)
        if self._reload:
            self.save()
    
    def __str__(self):
        # print the configuration in the console
        pass
    
    def text_edit(self):
        # open terminal text-editor to edit the configuration in real-time
        pass

    
    def load_sources(self, cli: Namespace | None = None, preference: list[str] | None = None, *files):
        self.preference = preference
        self.reload_files(*files)
        self.reload_env()
        if cli:
            self.reload_cli(cli)

    def reload_files(self, *paths):
        # Read all paths, initialize values in order. Update values in self
        # if path is within user's home dir => user file => origin = USR
        # else => system file => origin = SYS
        pass
    
    def reload_cli(self, namespace: Namespace):
        # depending on self._preference, decide if overwrite the value or not
        # origin = CLI
        pass

    def reload_env(self):
        # depending on self._preference, decide if overwrite the value or not
        # origin = ENV
        pass
