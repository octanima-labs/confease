"""Format-independent configuration paths and canonical nested mappings.

Dots separate path segments. Lists are whole values; empty mappings are
terminals so they retain both their presence and their source origin.
"""

from collections.abc import Iterable, Mapping
from typing import Any


def validate_key(key: str) -> None:
    """Reject empty path segments without imposing a nesting-depth limit."""
    if any(not part for part in key.split(".")):
        raise ValueError(f"Configuration keys require nonempty path segments: {key!r}")


def validate_paths(keys: Iterable[str]) -> None:
    """Reject duplicate terminals and terminal/descendant collisions."""
    terminals: set[str] = set()
    sections: set[str] = set()
    for key in keys:
        validate_key(key)
        if key in terminals:
            raise ValueError(f"Duplicate configuration key: {key}")
        parts = key.split(".")
        parents = {".".join(parts[:index]) for index in range(1, len(parts))}
        collisions = parents & terminals
        if key in sections or collisions:
            conflict = key if key in sections else min(collisions)
            raise ValueError(f"Configuration key collides with nested section: {conflict}")
        terminals.add(key)
        sections.update(parents)


def flatten_items(items: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    """Flatten pairs, retaining duplicate detection before dict accumulation."""
    flat: dict[str, Any] = {}
    active: set[int] = set()

    def visit(raw_key: str, value: Any, prefix: str = "") -> None:
        key = str(raw_key)
        validate_key(key)
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping) and value:
            identity = id(value)
            if identity in active:
                raise ValueError(f"Cyclic configuration mapping: {path}")
            active.add(identity)
            try:
                for child, item in value.items():
                    visit(child, item, path)
            finally:
                active.remove(identity)
        else:
            if path in flat:
                raise ValueError(f"Duplicate configuration key: {path}")
            flat[path] = {} if isinstance(value, Mapping) else value

    for key, value in items:
        visit(key, value)
    validate_paths(flat)
    return flat


def flatten(data: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten nested mappings and dotted keys into terminal paths."""
    return flatten_items(data.items())


def nest(data: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct a nested mapping from validated terminal paths."""
    validate_paths(data)
    nested: dict[str, Any] = {}
    for key, value in data.items():
        parts = key.split(".")
        section = nested
        for part in parts[:-1]:
            section = section.setdefault(part, {})
        section[parts[-1]] = {} if isinstance(value, Mapping) and not value else value
    return nested


def normalized(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return canonical nested mapping data without mutating the input."""
    return nest(flatten(data))
