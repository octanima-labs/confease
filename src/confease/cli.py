"""Create, repair, modify, and restore configuration documents from the CLI."""

import argparse
import configparser
import shutil
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from confease.documents import equivalent, install_draft, normalized, render_document
from confease.editors import TextEditor
from confease.model import Confease
from confease.parsers import PARSER_CLASSES, Parser, Yaml


def argument_parser() -> argparse.ArgumentParser:
    """Build help and arguments for the explicit command forms."""
    parser = argparse.ArgumentParser(
        prog="confease",
        description="Create, edit, and restore configuration files while preserving comments.",
        epilog="Shorthand: confease PATH [edit options]. Values use YAML syntax.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a new configuration in your editor.")
    edit = commands.add_parser("edit", help="Edit or repair an existing configuration.")
    restore = commands.add_parser("restore", help="Restore an explicit or latest configuration backup.")
    for command in (init, edit, restore):
        command.add_argument("path", type=Path, help="Configuration file path.")
        command.add_argument("-f", "--format", metavar="FMT",
                             help="Override the format: yaml, yml, json, toml, ini, cfg, conf, config, xml, csv.")
    init.add_argument("-i", "--item", action="append", default=[], metavar="KEY=VALUE",
                      help="Seed the editor draft with a typed value; repeat as needed.")
    edit.add_argument("-u", "--update", action="append", default=[], metavar="KEY=VALUE",
                      help="Add or replace a typed value without opening an editor.")
    edit.add_argument("-d", "--delete", action="append", default=[], metavar="KEY",
                      help="Delete a leaf or section without opening an editor; repeat as needed.")
    for command in (edit, restore):
        command.add_argument("-b", "--backup", action="store_true",
                             help="Keep an exact sibling backup before replacing the configuration.")
    restore.add_argument("--from", dest="source", type=Path, metavar="BACKUP",
                         help="Restore this file; otherwise select a sibling backup by filename timestamp and sequence.")
    return parser


def resolve_format(path: Path, explicit: str | None, *, initializing: bool) -> type[Parser]:
    """Resolve an override, recognized suffix, or extensionless init default."""
    suffix = "." + explicit.lower().lstrip(".") if explicit else path.suffix.lower()
    if not suffix and initializing:
        return Yaml
    parser = PARSER_CLASSES.get(suffix)
    if parser is None:
        raise ValueError(f"Cannot determine a supported format for {path}; use --format FMT")
    return parser


def assignments(items: Sequence[str]) -> dict[str, Any]:
    """Parse typed assignments; the last assignment to a leaf wins."""
    leaves = {}
    for item in items:
        key, separator, text = item.partition("=")
        if not separator or not key:
            raise ValueError(f"Expected a nonempty KEY=VALUE assignment, received {item!r}")
        value = yaml.safe_load(text)
        leaves.update(Confease._flatten_mapping({key: value}))
    Confease._ensure_no_key_collisions(leaves)
    return leaves


def scripted_edit(path: Path, parser: type[Parser], updates: Sequence[str], deletes: Sequence[str],
                  *, backup: bool = False):
    """Apply deletions and updates as one validated, comment-preserving batch."""
    leaves = assignments(updates)
    try:
        conf = Confease(path, parser=parser)
    except (ValueError, yaml.YAMLError, configparser.Error, ET.ParseError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"Invalid configuration: {error}. Repair it with confease edit {path}") from error
    for key in deletes:
        Confease._validate_key(key)
        is_section = conf.get_item(key) is None and conf.get(key) is not None
        if key in leaves or (is_section and any(leaf.startswith(f"{key}.") for leaf in leaves)):
            raise ValueError(f"Conflicting update and deletion for {key!r}")
    for key in deletes:
        if not conf.delete(key):
            print(f"Warning: key {key!r} does not exist", file=sys.stderr)
    for key, value in leaves.items():
        conf.set(key, value)
    conf.save(backup=backup)


def interactive_edit(path: Path, parser: type[Parser], *, initializing: bool,
                     items: Sequence[str] = (), backup: bool = False):
    """Retain invalid draft edits for correction and install exact valid bytes."""
    desired = Confease._nest_mapping(assignments(items)) if initializing else {}
    initial = render_document(parser, "", {}, desired) if initializing else None
    path.parent.mkdir(parents=True, exist_ok=True)
    draft = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=parser.extensions[0],
                                         delete=False, newline="") as file:
            draft = Path(file.name)
            if initial is not None:
                file.write(initial)
        if initializing:
            # Invalid/unrepresentable initial items fail before opening an editor.
            if not equivalent(normalized(parser.load(draft)), desired):
                raise ValueError(f"Initial values cannot be faithfully represented by {parser.__name__}")
        else:
            shutil.copyfile(path, draft)
        editor = TextEditor()
        while True:
            editor.open(draft)
            try:
                normalized(parser.load(draft))
            except (ValueError, yaml.YAMLError, configparser.Error, ET.ParseError, tomllib.TOMLDecodeError) as error:
                print(f"Invalid draft: {error}\nReopening the draft for correction; press Ctrl-C to cancel.",
                      file=sys.stderr)
                continue
            install_draft(draft, path, create_only=initializing, backup=backup)
            return
    finally:
        if draft is not None:
            draft.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI, returning zero on success and nonzero on failure."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] not in ("init", "edit", "restore", "-h", "--help"):
        args.insert(0, "edit")
    options = argument_parser().parse_args(args)
    initializing = options.command == "init"
    try:
        path = options.path.expanduser()
        if initializing and path.exists():
            raise FileExistsError(f"Configuration already exists: {path}")
        if options.command == "edit" and not path.exists():
            raise FileNotFoundError(f"Configuration does not exist: {path}")
        parser = resolve_format(path, options.format, initializing=initializing)
        if options.command == "restore":
            # Recovery must not load a potentially malformed destination first.
            conf = Confease(parser=parser)
            conf._path = path
            conf.restore(options.source, backup=options.backup)
        elif not initializing and (options.update or options.delete):
            scripted_edit(path, parser, options.update, options.delete, backup=options.backup)
        else:
            interactive_edit(path, parser, initializing=initializing,
                             items=options.item if initializing else (),
                             backup=False if initializing else options.backup)
    except KeyboardInterrupt:
        print("Cancelled; no draft installed.", file=sys.stderr)
        return 130
    except Exception as error:  # noqa: BLE001 - CLI boundary reports backend/editor failures without tracebacks
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
