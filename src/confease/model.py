"""Core configuration model for ``confease``.

The module exposes :class:`Confease`, a small configuration container that
combines in-code defaults, configuration files, environment variables, and
``argparse`` namespaces. Conflicts are resolved by origin precedence, which
defaults to ``CLI > ENV > SYS > USR > DEF``.
"""
import os
import shutil
import tempfile
from argparse import Namespace
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from edital import TuiEditor

from confease.backups import create_backup, latest_backup
from confease.documents import install_draft
from confease.editing import install_text, read_text, text_validator
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
    """Single flattened configuration value with its source origin.

    ``Confease`` stores effective configuration as ``Confitem`` leaves. Nested
    values use dotted keys such as ``"database.host"`` while preserving the
    original Python value type.
    """

    def __init__(self, key: str, value: Any, origin: str):
        """Create a configuration item.

        Args:
            key: Configuration key. Nested leaves are represented with one
                dotted level, for example ``"database.host"``.
            value: Stored Python value. Values are not coerced to strings.
            origin: Source origin for the value. Must be one of
                :data:`ORIGINS`.

        Raises:
            ValueError: If ``origin`` is not a supported source origin.
        """
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
    """Configuration container with defaults, persistence, and precedence.

    ``Confease`` keeps one effective value per key. Values can come from
    defaults, files, environment variables, or command-line namespaces, and the
    configured ``preference`` decides which origin wins when multiple sources
    define the same key.

    The container supports one nested level. Nested mappings are flattened into
    dotted ``Confitem`` leaves internally, while nested-capable file formats are
    saved and loaded as ordinary nested mappings.
    """

    def __init__(self, path: str | Path | None = None, reload: bool = False, parser: type[Parser] | None = Yaml, template: str | Path | None = None, preference = (CLI, ENV, SYS, USR, DEF), __backup__: bool = False, **kwargs):
        """Initialize a configuration object.

        Args:
            path: Configuration file path. When omitted, the instance is
                runtime-only and ``save()`` does not persist anything.
            reload: If true, reload the configured file before value reads and
                save immediately after ``set()``.
            parser: Parser class used for ``path``. Pass ``None`` to infer the
                parser from the file suffix.
            template: Optional default configuration file, read with the active
                parser as default-origin values without copying to ``path``.
                Cannot be combined with keyword defaults. Explicit ``reset()``
                restores its exact content to ``path`` and reloads it.
            preference: Origins ordered from highest to lowest priority.
                Omitted origins are appended after the provided ones.
            __backup__: Keep an exact sibling snapshot before persisted changes to
                an existing file. Disabled by default; automatic saves inherit
                this policy. Individual persistence operations can override it.
                The ordinary ``backup`` keyword remains a configuration default.
            **kwargs: In-code default configuration values. One-level nested
                dictionaries are accepted.

        Raises:
            AttributeError: If both ``template`` and keyword defaults are given.
            FileNotFoundError: If the configured template is missing.
            ValueError: If the parser or source preference is invalid.
        """
        if path is None:
            self._path: Path | None = None
            print("[-] Runtime-only configuration. No path provided, so conf file will not persist")
        else:
            self._path = Path(path).expanduser()
        self._reload = bool(reload) # if reload, changes are saved instantly and each time conf is accessed, it is readed from file; in this way the conf 'reloads' itself
        self._backup = bool(__backup__)
        self._defaults: list[Confitem] = [Confitem(k, v, DEF) for k, v in self._flatten_mapping(kwargs).items()]
        self._entries: list[Confitem] | None = None
        self._preference: list[str] | None = None
        self._template: Path | None = None
        self._parser: type[Parser]
        self.editor: Any = TuiEditor()
        self.preference = preference


        if template:
            if len(kwargs.keys()) == 0:
                self._template = Path(template).expanduser()
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

        if self._template is not None:
            self._defaults = [Confitem(key, value, DEF) for key, value in
                              self._flatten_mapping(self._parser.load(self._template)).items()]

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
                        raise ValueError(f"Nested configuration keys support one level only: {key}.{raw_subkey}")  # noqa: TRY004 - invalid config shape is a value error
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
            self._initialize_entries()
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
        """Load configuration values from a file as user-origin entries.

        Validate all content and keys before replacing in-memory entries.
        Failed loads preserve the previous entries; defaults supply keys not
        defined by the file.

        Args:
            path: Optional file path to load instead of the instance path.

        Raises:
            FileNotFoundError: If no path is available or the target file does
                not exist.
            ValueError: If the parser rejects the file shape or keys collide.
        """
        # param path allows to override the load file
        load_path = Path(path).expanduser() if path is not None else self._path
        if load_path is None:
            raise FileNotFoundError("No configuration path provided")
        if not load_path.exists():
            raise FileNotFoundError(load_path)
        data = self._parser.load(load_path)

        self._entries = self._entries_for_load(data)

    def _entries_for_load(self, data: Mapping[str, Any]) -> list[Confitem]:
        """Build and validate loaded entries without changing live state."""
        entries = {entry.key: entry for entry in self._defaults}
        entries.update({key: Confitem(key, value, USR)
                        for key, value in self._flatten_mapping(data).items()})
        self._ensure_no_key_collisions(entries.keys())
        return list(entries.values())

    def _initialize_entries(self):
        """Initialize defaults in memory without invoking persistent reset."""
        self._entries = list(self._defaults)
    
    def _data_for_save(self, user_only: bool = True) -> dict[str, Any]:
        """Return nested mapping data for persistence."""
        entries = self._defaults if self._entries is None else self._entries
        return self._nest_mapping(
            {entry.key: entry.value for entry in entries if not user_only or entry.origin == USR}
        )

    def _backup_enabled(self, backup: bool | None) -> bool:
        """Resolve a per-operation override without changing instance policy."""
        return self._backup if backup is None else backup

    def save(self, user_only: bool = True, *, backup: bool | None = None):
        """Persist configuration to the instance path.

        Args:
            user_only: When true, write only ``USR`` entries. When false, write
                all effective entries, including defaults and overrides from
                other origins.
            backup: ``None`` inherits the instance policy; a boolean overrides
                it for this save only. After candidate validation, snapshot the
                previous bytes before replacement. Backup failure aborts saving.

        Notes:
            Runtime-only configurations created without ``path`` are a no-op
            when saved. Existing YAML, TOML, INI-family, and XML comments are
            preserved using the latest destination document. Selected in-memory
            values are authoritative; external values are not merged. Invalid
            destinations or unrepresentable values raise without replacing the
            file. Complete candidates are validated before replacement.
        """
        if self._path is None:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = self._data_for_save(user_only)
        if self._backup_enabled(backup):
            self._parser.save(self._path, data, backup=True)
        else:
            self._parser.save(self._path, data)

    def reset(self, *, backup: bool | None = None):
        """Restore keyword defaults in memory, or copy the template to disk.

        With a template, explicitly overwrite the configured path with exact
        template bytes and reload them as user-origin values. Validation or
        copy failures leave the previous file and in-memory entries unchanged.
        Without a template, reset only memory and do not write the file.

        Args:
            backup: Override the instance backup policy for template restoration.
                ``None`` inherits it. Memory-only reset never creates a backup.

        Raises:
            FileNotFoundError: If template restoration lacks a target path or
                the template is missing.
            ValueError: If the template has invalid shape or keys.
            OSError: If copying or replacing the target fails.
        """
        print("Setting default configuration...")
        if self._template is None:
            self._initialize_entries()
            return
        if self._path is None:
            raise FileNotFoundError("No configuration path provided")

        self._flatten_mapping(self._parser.load(self._template))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        draft_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=self._path.suffix, prefix=f".{self._path.name}.",
                dir=self._path.parent, delete=False,
            ) as draft_file:
                draft_path = Path(draft_file.name)
            shutil.copyfile(self._template, draft_path)
            # Validate the exact copied document before installing it.
            values = self._flatten_mapping(self._parser.load(draft_path))
            defaults = [Confitem(key, value, DEF) for key, value in values.items()]
            install_draft(draft_path, self._path, backup=self._backup_enabled(backup))
        finally:
            if draft_path is not None and draft_path.exists():
                draft_path.unlink()

        self._defaults = defaults
        self.load()

    def restore(self, path: str | Path | None = None, *, backup: bool | None = None):
        """Restore exact backup bytes while retaining existing defaults.

        Args:
            path: Explicit source file, irrespective of filename or directory.
                When omitted, select the latest matching sibling backup by its
                embedded timestamp and collision sequence, not modification time.
            backup: Override the instance backup policy for this operation.
                ``None`` inherits it. Select and validate the source before
                backing up the destination so a subsequent restore can undo this
                one. The source backup is retained.

        Raises:
            FileNotFoundError: If no destination, source, or matching backup exists.
            ValueError: If source structure or keys conflict with retained defaults.
            OSError: If copying, backing up, or replacing the destination fails.

        Notes:
            Validation uses the active parser. Malformed or missing destinations
            can be recovered; failures preserve the destination and live entries.
            Defaults, template, configured path, and instance policy are unchanged.
        """
        if self._path is None:
            raise FileNotFoundError("No configuration path provided")
        source = Path(path).expanduser() if path is not None else latest_backup(self._path)
        if not source.exists():
            raise FileNotFoundError(source)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        draft_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=self._path.suffix, prefix=f".{self._path.name}.",
                dir=self._path.parent, delete=False,
            ) as draft_file:
                draft_path = Path(draft_file.name)
            shutil.copyfile(source, draft_path)
            entries = self._entries_for_load(self._parser.load(draft_path))
            install_draft(draft_path, self._path, backup=self._backup_enabled(backup))
        finally:
            if draft_path is not None:
                draft_path.unlink(missing_ok=True)
        self._entries = entries

    def get(self, key: str, default = None, cast = None):
        """Return a value or one-level section by key.

        Args:
            key: Scalar key, dotted nested key, or section name.
            default: Value returned when neither a leaf nor a section exists.
            cast: Optional callable used to coerce the returned value. Cast
                failures are reported and the original value is returned.

        Returns:
            The stored value, a plain dictionary snapshot for section reads, or
            ``default`` when the key is missing.
        """
        item = self.get_item(key)
        val = item.value if item is not None else self._get_section(key)
        if val is None:
            return default
        if cast:
            try:
                val = cast(val)
            except Exception as e:  # noqa: BLE001 - user-provided casts can raise arbitrary exceptions
                print(f"[!] Unable to cast '{val}' into {cast}. {e}")
        return val
    
    def get_item(self, key: str) -> Confitem | None:
        """Return the matching leaf item.

        Args:
            key: Scalar or dotted key to look up.

        Returns:
            The matching ``Confitem``, or ``None`` when no leaf exists. Section
            names do not return an item; use ``get()`` for section snapshots.
        """
        if self._entries is None:
            self._initialize_entries()
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
        """Store a user-origin value.

        Args:
            key: Scalar key, dotted nested key, or section name when ``value``
                is a one-level mapping.
            value: Python value to store. Nested dictionaries are flattened into
                dotted leaves.

        Raises:
            ValueError: If nested keys exceed one level or a scalar key collides
                with a section key.
        """
        items = self._flatten_mapping({key: value})
        for item_key, item_value in items.items():
            self._set_item(item_key, item_value, USR, force=True)
        if self._reload:
            self.save()

    def delete(self, key: str) -> bool:
        """Remove an effective leaf or all leaves in a one-level section.

        Returns true when at least one entry was removed, including null-valued
        entries, and false for a missing key. With ``reload=True``, read the
        current file first and persist through comment-preserving ``save()``.
        A failed automatic save restores the entries before deletion.

        Deletion does not create a defaults tombstone: a later load or reset
        can supply a deleted default again. Invalid key shapes raise ValueError.
        """
        self._validate_key(key)
        if self._entries is None:
            self._initialize_entries()
        elif self._reload:
            self.load()
        previous = self._entries or []
        remaining = [entry for entry in previous
                     if entry.key != key and not entry.key.startswith(f"{key}.")]
        if len(remaining) == len(previous):
            return False
        self._entries = remaining
        try:
            if self._reload:
                self.save()
        except Exception:
            self._entries = previous
            raise
        return True

    def __getitem__(self, key: str):
        """Return ``get(key)`` so missing keys produce ``None``."""
        return self.get(key)

    def __setitem__(self, key: str, value: Any):
        """Assign through ``set(key, value)``."""
        self.set(key, value)
    
    def __str__(self):
        """Reserved for a future short printable representation."""
        # print the configuration in the console

    def to_str(self):
        """Reserved for a future detailed printable representation."""
        # print the configuration in the console
    
    def edit_file(self, *, template: str | Path | None = None, backup: bool | None = None):
        """Edit exact file text transactionally in the embedded terminal editor.

        F2 or F3 validates and accepts text; Ctrl+Q cancels, confirming discard
        if changed. Escape dismisses interactions; F1 shows help, F4 opens Find,
        and F5 opens Find/Replace. Invalid candidates stay in the same session. Only
        accepted valid text is installed, without reserialization. Cancellation
        preserves destination content and live entries, including unsaved values.

        Args:
            template: Seed a missing target with this file's exact content.
                This edit-only template does not change configured defaults.
                Explicit acceptance creates the target even if text is unchanged.
                Existing targets ignore this argument.
            backup: ``None`` inherits the instance policy. When enabled, copy
                the existing file after acceptance and validation, immediately
                before installation. Cancellation creates no backup.

        Returns:
            The current ``Confease`` instance.

        Raises:
            FileNotFoundError: If the instance has no configured path or a
                template needed for a missing target does not exist.
            ValueError: If a needed template is invalid or line endings are mixed.
            RuntimeError: If no interactive terminal is available.
            Exception: If the editor or installation fails.

        Notes:
            Accepted candidates are retained with a recovery path in exception
            notes on installation failure. Missing-target installation refuses
            to overwrite a target created during editing. An explicitly assigned
            external ``TextEditor`` retains direct-file editing, pre-launch backup,
            and invalid-saved-bytes behavior, with best-effort template drafts for
            non-Vim/Neovim commands.
        """
        if self._path is None:
            raise FileNotFoundError("No configuration path provided")

        edit_path = self._path.expanduser()
        if hasattr(self.editor, "edit"):
            missing = not edit_path.exists()
            if template is not None and missing:
                source = Path(template).expanduser()
                self._entries_for_load(self._parser.load(source))
                initial = read_text(source)
            else:
                initial = "" if missing else read_text(edit_path)
            result = self.editor.edit(initial, title=str(edit_path),
                                      validator=text_validator(self._parser, self._entries_for_load))
            if result.outcome == "accepted":
                if result.text is None:
                    raise ValueError("Accepted editor result has no text")
                entries = install_text(result.text, edit_path, self._parser, self._entries_for_load,
                                       create_only=missing, backup=self._backup_enabled(backup))
                self._entries = entries
            return self
        if template is not None and not edit_path.exists():
            return self._edit_missing_from_template(edit_path, Path(template).expanduser())
        edit_path.parent.mkdir(parents=True, exist_ok=True)
        if self._backup_enabled(backup):
            create_backup(edit_path)
        self.editor.open(edit_path)
        if edit_path.exists():
            self.load()
        else:
            self._initialize_entries()
        return self

    def _edit_missing_from_template(self, target: Path, template: Path):
        """Preload a missing file, retaining saved fallback drafts on failure."""
        # Validate before launch, without incorporating these values as defaults.
        self._entries_for_load(self._parser.load(template))
        target.parent.mkdir(parents=True, exist_ok=True)
        preload = getattr(self.editor, "_open_preloaded", None)
        if preload is not None and preload(target, template):
            if target.exists():
                self.load()
            return self

        draft: Path | None = None
        retain = False
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.",
                                             suffix=target.suffix, delete=False) as file:
                draft = Path(file.name)
            shutil.copyfile(template, draft)
            initial = self._draft_signature(draft)
            try:
                self.editor.open(draft)
            finally:
                # Preserve written work even when the editor exits unsuccessfully.
                retain = draft.exists() and self._draft_signature(draft) != initial
            if not retain:
                return self
            entries = self._entries_for_load(self._parser.load(draft))
            install_draft(draft, target, create_only=True)
            retain = False
            self._entries = entries
        except BaseException as error:
            if retain:
                error.add_note(f"Saved editor draft retained at: {draft}")
            raise
        finally:
            if draft is not None and not retain:
                draft.unlink(missing_ok=True)
        return self

    @staticmethod
    def _draft_signature(path: Path):
        """Detect in-place and replacement saves, including unchanged bytes."""
        info = path.stat()
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, path.read_bytes())

    
    def load_sources(self, cli: Namespace | None = None, *files, preference: list[str] | None = None):
        """Reload file, environment, and CLI sources.

        Sources are loaded in file, environment, then CLI order. When the same
        key appears more than once, the configured origin preference determines
        the effective value.

        Args:
            cli: Optional ``argparse.Namespace`` whose non-``None`` values are
                loaded with ``CLI`` origin.
            *files: Additional config files. Files under the current user's home
                directory are ``USR`` origin; all others are ``SYS`` origin.
            preference: Optional source precedence override.

        Raises:
            FileNotFoundError: If any file path does not exist.
            ValueError: If a file suffix, preference, or key shape is invalid.
        """
        if preference is not None:
            self.preference = preference
        self.reload_files(*files)
        self.reload_env()
        if cli:
            self.reload_cli(cli)

    def reload_files(self, *paths):
        """Load additional config files as system or user origins.

        Args:
            *paths: Config file paths. Parser selection is inferred from each
                suffix.

        Raises:
            FileNotFoundError: If a path does not exist.
            ValueError: If a suffix is unsupported or loaded keys collide.
        """
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
        """Load non-``None`` argparse namespace values as CLI-origin entries.

        Args:
            namespace: Parsed command-line namespace. Attribute names become
                config keys, and nested dictionaries are flattened one level.
        """
        data = {key: value for key, value in vars(namespace).items() if value is not None}
        for key, value in self._flatten_mapping(data).items():
            self._set_item(key, value, CLI)

    def reload_env(self):
        """Load known environment variables as ENV-origin entries.

        Only keys already present in defaults or loaded entries are considered.
        Values are parsed with ``yaml.safe_load`` so common scalar text such as
        ``true``, ``5432``, ``null``, or ``[1, 2]`` becomes the corresponding
        Python value.
        """
        if self._entries is None:
            self._initialize_entries()
        entries = self._entries or []
        for key in {entry.key for entry in entries}:
            if key in os.environ:
                self._set_item(key, yaml.safe_load(os.environ[key]), ENV)
