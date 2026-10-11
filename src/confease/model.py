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
from confease.mappings import (
    flatten,
    nest,
    normalize_flat,
    validate_key,
    validate_merge,
    validate_paths,
)
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
            key: Configuration path. Nested leaves use dotted segments at any
                depth, for example ``"database.primary.host"``.
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

    Nested mappings support arbitrary depth and are flattened into dotted
    ``Confitem`` leaves internally, with placeholders for empty mappings until
    descendants populate them. Mapping/non-mapping structural changes are
    rejected, while ordinary leaf type changes remain valid. Parsers encode
    hierarchy for their format and return canonical nested mappings on load.
    Dots are reserved path separators; lists remain whole values.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        reload: bool = False,
        parser: type[Parser] | None = Yaml,
        template: str | Path | None = None,
        preference = (CLI, ENV, SYS, USR, DEF),
        backup: bool = False,
        items: dict[str, Any] | None = None,
        *,
        autoload: bool = True,
    ):
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
                Cannot be combined with nonempty ``items``. Explicit ``reset()``
                restores its exact content to ``path`` and reloads it.
            preference: Origins ordered from highest to lowest priority.
                Omitted origins are appended after the provided ones.
            backup: Keep an exact sibling snapshot before persisted changes to
                an existing file. Disabled by default; automatic saves inherit
                this policy. Individual persistence operations can override it.
            items: In-code default configuration values. Arbitrarily nested
                dictionaries and empty mappings are accepted. Keys may use
                constructor option names without affecting those options. ``None`` or an empty dictionary
                provides no defaults. Replaces the former keyword-default API.
            autoload: Load an existing destination during construction by default.
                When false, defer loading until the first ordinary read, mutation,
                save, or source overlay. Recovery through transactional editing,
                reset, or restore bypasses this initial destination load. Parser,
                defaults, preference, and template validation still occur.

        Raises:
            AttributeError: If both ``template`` and nonempty ``items`` are given.
            TypeError: If ``items`` is neither a dictionary nor ``None``, or a
                legacy/unknown constructor keyword is supplied.
            FileNotFoundError: If the configured template is missing.
            ValueError: If the parser or source preference is invalid.
        """
        if items is not None and not isinstance(items, dict):
            raise TypeError("items must be a dictionary or None")
        items = {} if items is None else items
        if path is None:
            self._path: Path | None = None
            print("[-] Runtime-only configuration. No path provided, so conf file will not persist")
        else:
            self._path = Path(path).expanduser()
        self._reload = bool(reload) # if reload, changes are saved instantly and each time conf is accessed, it is readed from file; in this way the conf 'reloads' itself
        self._backup = bool(backup)
        self._defaults: list[Confitem] = [Confitem(k, v, DEF) for k, v in self._flatten_mapping(items).items()]
        self._entries: list[Confitem] | None = None
        self._preference: list[str] | None = None
        self._template: Path | None = None
        self._parser: type[Parser]
        self.editor: Any = TuiEditor()
        self.preference = preference


        if template:
            if not items:
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

        if autoload and self._path is not None and self._path.exists():
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
        """Validate nonempty segments in a scalar or dotted path."""
        validate_key(key)

    @classmethod
    def _ensure_no_key_collisions(cls, keys):
        """Reject terminal/section collisions at any depth."""
        validate_paths(keys)

    @classmethod
    def _flatten_mapping(cls, data: Mapping[str, Any]) -> dict[str, Any]:
        """Flatten arbitrary-depth mappings, retaining empty terminals."""
        return flatten(data)

    @classmethod
    def _nest_mapping(cls, data: Mapping[str, Any]) -> dict[str, Any]:
        """Reconstruct arbitrary-depth sections from dotted terminal paths."""
        return nest(data)

    def _set_item(self, key: str, value: Any, origin: str, *, force: bool = False):
        """Set an item if allowed by precedence, or always when forced."""
        if self._entries is None:
            self._ensure_entries()
        if self._entries is None:
            self._entries = []

        self._entries = self._merge_entries(self._entries, {key: value}, origin, force=force)

    def _merge_entries(self, entries: list[Confitem], data: Mapping[str, Any],
                       origin: str, *, force: bool = False) -> list[Confitem]:
        """Stage a structurally compatible overlay before publishing any leaves."""
        incoming = self._flatten_mapping(data)
        current = {entry.key: entry for entry in entries}
        validate_merge({key: entry.value for key, entry in current.items()}, incoming)
        for key, value in incoming.items():
            previous = current.get(key)
            if (previous is None or force
                    or self._origin_priority(origin) <= self._origin_priority(previous.origin)):
                current[key] = Confitem(key, value, origin)
        effective = normalize_flat({key: entry.value for key, entry in current.items()})
        return [current[key] for key in effective]
    
    def load(self, path: str | Path | None = None):
        """Load configuration values from a file as user-origin entries.

        Validate all content and keys before replacing in-memory entries.
        Failed loads preserve the previous entries; defaults supply keys not
        defined by the file. Successful loading, including from an alternate
        path, satisfies deferred initialization. With ``reload=False``, later
        ordinary access keeps those entries rather than loading the destination.

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
        return self._merge_entries(self._defaults, data, USR, force=True)

    def _initialize_entries(self):
        """Initialize defaults in memory without invoking persistent reset."""
        self._entries = list(self._defaults)

    def _ensure_entries(self):
        """Initialize ordinary use from the destination or memory-only defaults."""
        if self._entries is None:
            if self._path is not None and self._path.exists():
                self.load()
            else:
                self._initialize_entries()
    
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
            A deferred instance initializes from its existing destination before
            saving, so unaccessed file values are retained. Initialization errors
            abort saving without changing the file or publishing partial entries.
            Runtime-only configurations created without ``path`` are a no-op
            when saved. Existing YAML, TOML, INI-family, and XML comments are
            preserved using the latest destination document. Selected in-memory
            values are authoritative; external values are not merged. Invalid
            destinations or unrepresentable values raise without replacing the
            file. Complete candidates are validated before replacement.
        """
        previous = self._entries
        try:
            self._ensure_entries()
            if self._path is None:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = self._data_for_save(user_only)
            if self._backup_enabled(backup):
                self._parser.save(self._path, data, backup=True)
            else:
                self._parser.save(self._path, data)
        except Exception:
            if previous is None:
                self._entries = previous
            raise

    def reset(self, *, backup: bool | None = None):
        """Restore ``items`` defaults in memory, or copy the template to disk.

        With a template, explicitly overwrite the configured path with exact
        template bytes and reload them as user-origin values. Validation or
        copy failures leave the previous file and in-memory entries unchanged.
        Without a template, reset only memory and do not write the file. Reset
        bypasses deferred destination loading, including for malformed files.

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
        self._entries = [Confitem(key, value, USR) for key, value in values.items()]

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
            Construct with ``autoload=False`` to recover a malformed destination
            using a fresh instance without parsing it during construction.
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
        """Return a value or recursive section snapshot by path.

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
        if isinstance(val, Mapping):
            val = self._nest_mapping(self._flatten_mapping(val))
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
            self._ensure_entries()
        elif self._reload:
            self.load()
        if self._entries is None:
            return None
        for entry in self._entries:
            if entry == key:
                return entry
        return None

    def _get_section(self, key: str) -> dict[str, Any] | None:
        """Reconstruct descendants as a nested plain dict, or None when absent."""
        if self._entries is None:
            return None
        self._validate_key(key)
        prefix = f"{key}."
        section = {entry.key.removeprefix(prefix): entry.value for entry in self._entries if entry.key.startswith(prefix)}
        return self._nest_mapping(section) if section else None

    def set(self, key: str, value: Any):
        """Store a user-origin value.

        Args:
            key: Scalar key, dotted nested key, or section name when ``value``
                is an arbitrary-depth mapping.
            value: Python value to store. Nested dictionaries are flattened into
                dotted leaves and merged with compatible sections. Empty mappings
                can acquire descendants; assigning an empty mapping to a populated
                section preserves its descendants. Delete a path before changing
                between mapping and non-mapping structure. Other leaf type changes
                remain allowed.

        Raises:
            ValueError: If paths contain empty segments, duplicate logical keys,
                or mapping/non-mapping conflicts at any depth. Rejected mapping
                assignments leave effective entries unchanged.
        """
        self._ensure_entries()
        self._entries = self._merge_entries(self._entries or [], {key: value}, USR, force=True)
        if self._reload:
            self.save()

    def delete(self, key: str) -> bool:
        """Remove an effective terminal or every descendant of a section.

        Returns true when at least one entry was removed, including null-valued
        entries, and false for a missing key. With ``reload=True``, read the
        current file first and persist through comment-preserving ``save()``.
        A failed automatic save restores the entries before deletion.

        Deletion does not create a defaults tombstone: a later load or reset
        can supply a deleted default again. Invalid key shapes raise ValueError.
        """
        self._validate_key(key)
        if self._entries is None:
            self._ensure_entries()
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
            With ``autoload=False``, a fresh instance can repair malformed text
            without ordinary destination loading. Cancellation preserves deferred
            state; successful installation satisfies initialization.
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
        self._ensure_entries()
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
        self._ensure_entries()
        for path in paths:
            load_path = Path(path).expanduser()
            if not load_path.exists():
                raise FileNotFoundError(load_path)

            parser = PARSER_CLASSES.get(load_path.suffix)
            if parser is None:
                raise ValueError(f"Unknown parser for '{load_path}'. Allowed: {PARSERS}")

            origin = USR if load_path.resolve().is_relative_to(Path.home().resolve()) else SYS
            self._entries = self._merge_entries(self._entries or [], parser.load(load_path), origin)
    
    def reload_cli(self, namespace: Namespace):
        """Load non-``None`` argparse namespace values as CLI-origin entries.

        Args:
            namespace: Parsed command-line namespace. Attribute names become
                config paths, and nested dictionaries are flattened recursively.
        """
        self._ensure_entries()
        data = {key: value for key, value in vars(namespace).items() if value is not None}
        self._entries = self._merge_entries(self._entries or [], data, CLI)

    def reload_env(self):
        """Load known environment variables as ENV-origin entries.

        Only keys already present in defaults or loaded entries are considered.
        Values are parsed with ``yaml.safe_load`` so common scalar text such as
        ``true``, ``5432``, ``null``, or ``[1, 2]`` becomes the corresponding
        Python value.
        """
        self._ensure_entries()
        entries = self._entries or []
        data = {key: yaml.safe_load(os.environ[key])
                for key in {entry.key for entry in entries} if key in os.environ}
        self._entries = self._merge_entries(entries, data, ENV)
