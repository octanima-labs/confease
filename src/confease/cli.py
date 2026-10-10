"""Create, repair, modify, and restore configuration documents from the CLI."""

import argparse
import configparser
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from edital import TuiEditor

from confease.documents import equivalent, normalized, render_document
from confease.editing import (
    EditCancelled,
    install_text,
    read_text,
    text_validator,
    validate_text,
)
from confease.model import Confease
from confease.parsers import PARSER_CLASSES, Parser, Yaml


def argument_parser() -> argparse.ArgumentParser:
    """Build help and arguments for the explicit command forms."""
    parser = argparse.ArgumentParser(
        prog="confease",
        description="Create, edit, and restore configuration files while preserving comments.",
        epilog="Shorthand: confease PATH [edit options]. Values use YAML syntax. "
               "Interactive editor: F2/F3 accepts and closes; Ctrl+Q cancels; Escape dismisses; "
               "F1 shows help; F4 finds; F5 replaces.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a new configuration in the embedded terminal editor.")
    edit = commands.add_parser("edit", help="Edit or repair an existing configuration.")
    restore = commands.add_parser("restore", help="Restore an explicit or latest configuration backup.")
    for command in (init, edit, restore):
        command.add_argument("path", type=Path, help="Configuration file path.")
        command.add_argument("-f", "--format", metavar="FMT",
                             help="Override the format: yaml, yml, json, toml, ini, cfg, conf, config, xml, csv.")
    seed = init.add_mutually_exclusive_group()
    seed.add_argument("-i", "--item", action="append", default=[], metavar="KEY=VALUE",
                      help="Seed the editor draft with a typed value; repeat as needed.")
    seed.add_argument("--template", type=Path, metavar="PATH",
                      help="Preload a template; create the target only on accept & close (F2/F3).")
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
                     items: Sequence[str] = (), backup: bool = False,
                     template: Path | None = None):
    """Edit one buffer, validate in-session, and install only explicit acceptance."""
    if initializing:
        if template is not None:
            initial = read_text(template.expanduser())
            validate_text(initial, parser, normalized)
        else:
            desired = Confease._nest_mapping(assignments(items))
            initial = "%YAML 1.1\n---\n" if not desired and issubclass(parser, Yaml) else render_document(parser, "", {}, desired)
            if not equivalent(validate_text(initial, parser, normalized), desired):
                raise ValueError(f"Initial values cannot be faithfully represented by {parser.__name__}")
    else:
        initial = read_text(path)
    result = TuiEditor().edit(initial, title=str(path), validator=text_validator(parser, normalized))
    if result.outcome == "cancelled":
        raise EditCancelled()
    if result.text is None:
        raise ValueError("Accepted editor result has no text")
    install_text(result.text, path, parser, normalized, create_only=initializing, backup=backup)


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
            conf = Confease(path, parser=parser, autoload=False)
            conf.restore(options.source, backup=options.backup)
        elif not initializing and (options.update or options.delete):
            scripted_edit(path, parser, options.update, options.delete, backup=options.backup)
        else:
            interactive_edit(path, parser, initializing=initializing,
                             items=options.item if initializing else (),
                             backup=False if initializing else options.backup,
                             template=options.template if initializing else None)
    except (KeyboardInterrupt, EditCancelled) as error:
        print("Cancelled.", file=sys.stderr)
        for note in getattr(error, "__notes__", ()):
            print(note, file=sys.stderr)
        return 130
    except Exception as error:  # noqa: BLE001 - CLI boundary reports backend/editor failures without tracebacks
        print(f"Error: {error}", file=sys.stderr)
        for note in getattr(error, "__notes__", ()):
            print(note, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
