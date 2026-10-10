"""Configuration-owned validation and installation for text editor sessions."""

import configparser
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypeVar

import yaml
from edital import Validator

from confease.documents import install_draft
from confease.parsers import Parser

T = TypeVar("T")
VALIDATION_ERRORS = (ValueError, yaml.YAMLError, configparser.Error, ET.ParseError, tomllib.TOMLDecodeError)


class EditCancelled(Exception):
    """An interactive CLI session was explicitly cancelled."""


def read_text(path: Path) -> str:
    """Read UTF-8 without universal-newline conversion."""
    return path.read_bytes().decode("utf-8")


def validate_text(text: str, parser: type[Parser],
                  validate: Callable[[Mapping[str, Any]], T]) -> T:
    """Bridge path-based parsers without changing live entries or destinations."""
    with tempfile.TemporaryDirectory(prefix="confease-validate-") as directory:
        candidate = Path(directory) / ("candidate" + (parser.extensions[0] if parser.extensions else ".config"))
        candidate.write_bytes(text.encode("utf-8"))
        return validate(parser.load(candidate))


def text_validator(parser: type[Parser], validate: Callable[[Mapping[str, Any]], T]) -> Validator:
    """Translate expected syntax/structure errors into in-session diagnostics."""
    def check(text: str) -> str | None:
        try:
            validate_text(text, parser, validate)
        except VALIDATION_ERRORS as error:
            return str(error)
        return None
    return check


def install_text(text: str, target: Path, parser: type[Parser],
                 validate: Callable[[Mapping[str, Any]], T], *,
                 create_only: bool = False, backup: bool = False) -> T:
    """Validate exact staged bytes, install them, and retain accepted work on failure.

    The returned validated state is safe to publish only after this call succeeds.
    Completed backups remain available if installation subsequently fails.
    """
    draft: Path | None = None
    complete = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.",
                                         suffix=parser.extensions[0] if parser.extensions else target.suffix,
                                         delete=False) as file:
            draft = Path(file.name)
            file.write(text.encode("utf-8"))
        complete = True
        state = validate(parser.load(draft))
        install_draft(draft, target, create_only=create_only, backup=backup)
    except BaseException as error:
        if not complete:
            # The destination directory can fail before a complete sibling draft
            # exists. Keep accepted work in the system temporary directory instead.
            try:
                with tempfile.NamedTemporaryFile(prefix="confease-recovery-", suffix=target.suffix,
                                                 delete=False) as recovery:
                    recovery_path = Path(recovery.name)
                    recovery.write(text.encode("utf-8"))
            except OSError as recovery_error:
                error.add_note(f"Could not retain accepted editor text: {recovery_error}")
            else:
                if draft is not None:
                    try:
                        draft.unlink(missing_ok=True)
                    except OSError:
                        pass
                draft = recovery_path
                complete = True
        if complete and draft is not None and draft.exists():
            error.add_note(f"Accepted editor text retained at: {draft}")
        raise
    else:
        draft.unlink(missing_ok=True)
        return state
