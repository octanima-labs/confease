"""Internal presentation-aware documents and validated file replacement.

Semantic loaders remain authoritative. Document trees carry presentation only;
they never participate in configuration source precedence.
"""

import csv
import io
import json
import math
import os
import stat
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import tomlkit
import yaml
from iniparse import INIConfig
from iniparse.ini import CommentLine, EmptyLine, LineContainer, OptionLine, SectionLine
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.resolver import VersionedResolver
from ruamel.yaml.tokens import CommentToken
from tomlkit.items import Array, Comment, Table, Whitespace

from confease.parsers import Csv, Ini, Json, Parser, Toml, Xml, Yaml, _dump_value


def equivalent(left: Any, right: Any) -> bool:
    """Compare configuration values without equating booleans and numbers."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(equivalent(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(equivalent(a, b) for a, b in zip(left, right))
    if type(left) is not type(right):
        return False
    if isinstance(left, float) and math.isnan(left) and math.isnan(right):
        return True
    return left == right


def normalized(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate supported structure and canonicalize dotted keys."""
    # Lazy import avoids coupling parser registration to model initialization.
    from confease.model import Confease

    return Confease._nest_mapping(Confease._flatten_mapping(data))


def document_layout(keys: Any, values: Mapping[str, Any]) -> dict[str, Any]:
    """Retain existing literal dotted-key nodes instead of dropping comments.

    Both dotted and section forms describe the same supported leaves. Keeping an
    existing document's spelling avoids unnecessarily removing surviving nodes.
    """
    result = {key: dict(value) if isinstance(value, Mapping) else value
              for key, value in values.items()}
    for raw_key in keys:
        key = str(raw_key)
        parts = key.split(".")
        if len(parts) != 2:
            continue
        parent, child = parts
        section = result.get(parent)
        if isinstance(section, dict) and child in section:
            result[key] = section.pop(child)
            if not section:
                del result[parent]
    return result


class Document:
    """Internal adapter: retain presentation, reconcile values, emit text."""

    def __init__(self, source: str, values: Mapping[str, Any]):
        self.source = source
        self.values = values

    def render(self, desired: Mapping[str, Any]) -> str:
        raise NotImplementedError


class LegacyYamlResolver(VersionedResolver):
    """Retain PyYAML's existing scalar resolution in round-trip nodes."""

    @property
    def versioned_resolver(self):
        return yaml.SafeLoader.yaml_implicit_resolvers


class YamlDocument(Document):
    """Keep native YAML nodes and move native comment tokens to their owners."""

    def __init__(self, source: str, values: Mapping[str, Any]):
        super().__init__(source, values)
        self.yaml = YAML(typ="rt")
        self.yaml.version = (1, 1)
        self.yaml.Resolver = LegacyYamlResolver
        self.yaml.preserve_quotes = True
        self.tree = self.yaml.load(source) if source.strip() else None
        self.header = ""
        if self.tree is None:
            self.tree = CommentedMap()
            # A comments-only document has no native mapping node to hold its
            # annotations. There is no value text to confuse with comments.
            self.header = "".join(line for line in source.splitlines(keepends=True)
                                  if not line.strip() or line.lstrip().startswith("#"))
        self.footer: list[str] = []
        self._own_comments(self.tree, root=True)

    def _own_comments(self, node: Any, *, root: bool = False, following: Any = None):
        if isinstance(node, CommentedSeq):
            for index, info in list(node.ca.items.items()):
                token = info[0]
                if token is None:
                    continue
                lines = token.value.splitlines(keepends=True)
                inline = token.start_mark.line == node.lc.item(index)[0] and not token.value.startswith("\n")
                first = lines.pop(0) if inline else ""
                comments = [line for line in lines if line.strip()]
                if not comments:
                    continue
                if index + 1 < len(node):
                    target = node.ca.items.setdefault(index + 1, [None, None, None, None])
                    target[1] = (target[1] or []) + [
                        CommentToken(line.lstrip(), CommentMark(node.lc.item(index + 1)[1]))
                        for line in comments
                    ]
                elif following is not None:
                    parent, key = following
                    target = parent.ca.items.setdefault(key, [None, None, None, None])
                    target[1] = (target[1] or []) + [
                        CommentToken(line.lstrip(), CommentMark(parent.lc.key(key)[1]))
                        for line in comments
                    ]
                elif all(len(line) - len(line.lstrip()) == 0 for line in comments):
                    self.footer.extend(comments)
                else:
                    continue
                info[0] = CommentToken(first, token.start_mark) if first else None
            return
        if not isinstance(node, CommentedMap):
            return
        keys = list(node)
        for index, key in enumerate(keys):
            info = node.ca.items.get(key)
            child = node[key]
            next_key = (node, keys[index + 1]) if index + 1 < len(keys) else following
            if (info and info[2] and isinstance(child, CommentedMap)
                    and child.ca.comment and child.ca.comment[0] is info[2]):
                # The section header token is shared with its child map; it
                # contains the child's leading annotations, not a root footer.
                self._own_comments(child, following=next_key)
                continue
            if info and info[2]:
                token = info[2]
                lines = token.value.splitlines(keepends=True)
                # A comment starting on the value's line is inline. The rest
                # of the token belongs to the following key or document end.
                value_line = node.lc.value(key)[0]
                inline = token.start_mark.line in (value_line, node.lc.key(key)[0]) and not token.value.startswith("\n")
                first = lines.pop(0) if inline else ""
                info[2] = CommentToken(first, token.start_mark) if first else None
                comments = [line for line in lines if line.strip()]
                if comments:
                    if index + 1 < len(keys):
                        target = keys[index + 1]
                        indent = node.lc.key(target)[1]
                        before = node.ca.items.setdefault(target, [None, None, None, None])
                        before[1] = (before[1] or []) + [
                            CommentToken(line.lstrip(), CommentMark(indent)) for line in comments
                        ]
                    elif root or all(len(line) - len(line.lstrip()) == 0 for line in comments):
                        self.footer.extend(comments)
                    else:
                        # Section-local trailing comments stay with the section.
                        info[2] = CommentToken(first + "".join(lines), token.start_mark)
            self._own_comments(node[key], following=next_key)

    def _value(self, value: Any) -> Any:
        # Use the existing codec to retain PyYAML's scalar interpretation.
        return self.yaml.load(yaml.safe_dump(value, sort_keys=False))

    def _reconcile(self, node: Any, old: Any, desired: Any):
        if isinstance(node, CommentedMap) and isinstance(desired, Mapping):
            raw_keys = {str(k): k for k in node}
            for text, key in list(raw_keys.items()):
                if text not in desired:
                    node.ca.items.pop(key, None)
                    del node[key]
            for key, value in desired.items():
                raw = raw_keys.get(key, key)
                if raw in node and key in old:
                    if isinstance(old[key], Mapping) != isinstance(value, Mapping):
                        node.ca.items.pop(raw, None)
                    node[raw] = self._reconcile(node[raw], old[key], value)
                else:
                    node[raw] = self._value(value)
            return node
        if equivalent(old, desired):
            return node
        if isinstance(node, CommentedSeq) and isinstance(desired, list) and isinstance(old, list):
            result = CommentedSeq()
            result.ca.comment = deepcopy(node.ca.comment)
            used: set[int] = set()
            for value in desired:
                match = next((i for i, previous in enumerate(old)
                              if i not in used and equivalent(previous, value)), None)
                if match is None:
                    result.append(self._value(value))
                else:
                    used.add(match)
                    result.append(node[match])
                    if match in node.ca.items:
                        result.ca.items[len(result) - 1] = deepcopy(node.ca.items[match])
            return result
        return self._value(desired)

    def render(self, desired: Mapping[str, Any]) -> str:
        self._reconcile(self.tree, document_layout(self.tree, self.values),
                        document_layout(self.tree, desired))
        stream = io.StringIO()
        self.yaml.dump(self.tree, stream)
        return self.header + stream.getvalue() + "".join(self.footer)


class TomlDocument(Document):
    """Update TOML items without rebuilding their containing tables."""

    def __init__(self, source: str, values: Mapping[str, Any]):
        super().__init__(source, values)
        self.tree = tomlkit.parse(source)
        self.footer: list[Any] = []
        last = self.tree
        while last:
            key = list(last)[-1]
            if not isinstance(last[key], Table):
                break
            last = last[key].value
        if last:
            start = len(last.body)
            while start and last.body[start - 1][0] is None:
                start -= 1
            self.footer = [item for _, item in last.body[start:]]
            del last._body[start:]

    @staticmethod
    def _array(node: Array, old: list[Any], desired: list[Any]) -> Array:
        parts = []
        used: set[int] = set()
        multiline = node._multiline or any("\n" in item.as_string() for item in node._iter_items())
        for value in desired:
            match = next((i for i, previous in enumerate(old)
                          if i not in used and equivalent(previous, value)), None)
            if match is None:
                parts.extend([Whitespace("\n" if multiline else " "),
                              tomlkit.item(value), Whitespace(",")])
            else:
                used.add(match)
                group = deepcopy(node._value[node._index_map[match]])
                if multiline and (group.indent is None or "\n" not in group.indent.s):
                    group.indent = Whitespace("\n")
                # A comma before a retained inline comment also makes moving
                # a formerly final item into the middle syntactically valid.
                group.comma = Whitespace(",")
                parts.extend(group)
        if node._value and node._value[-1].is_whitespace():
            parts.extend(deepcopy(list(node._value[-1])))
        return Array(parts, deepcopy(node.trivia), multiline=node._multiline)

    @staticmethod
    def _remove(container: Any, key: str, *, root=False):
        # TOML leading comments are standalone body items. Remove the block
        # preceding a removed key, except at the document's beginning.
        body = container.body
        index = next(i for i, (k, _) in enumerate(body) if k is not None and k.key == key)
        start = index
        while start and body[start - 1][0] is None:
            start -= 1
        if start or not root:
            for i in range(start, index):
                if isinstance(body[i][1], (Comment, Whitespace)):
                    container._body[i] = (None, Whitespace(""))
        del container[key]

    def _reconcile(self, container: Any, old: Mapping[str, Any], desired: Mapping[str, Any], *, root=False):
        for key in list(container):
            if key not in desired:
                self._remove(container, key, root=root)
        for key, value in desired.items():
            if key in container and isinstance(value, Mapping) and isinstance(container[key], Table):
                self._reconcile(container[key].value, old.get(key, {}), value)
            elif key not in old or not equivalent(old[key], value):
                if key in old and isinstance(old[key], Mapping) != isinstance(value, Mapping):
                    self._remove(container, key, root=root)
                if (key in container and isinstance(container[key], Array)
                        and isinstance(old.get(key), list) and isinstance(value, list)):
                    container[key] = self._array(container[key], old[key], value)
                else:
                    container[key] = value

    def render(self, desired: Mapping[str, Any]) -> str:
        self._reconcile(self.tree, document_layout(self.tree, self.values),
                        document_layout(self.tree, desired), root=True)
        for item in self.footer:
            self.tree.append(None, item)
        return tomlkit.dumps(self.tree)


class IndentedOptionLine(OptionLine):
    """Retain option indentation so updates do not turn peers into continuations."""

    indent = ""

    def to_string(self):
        return self.indent + super().to_string()


class IniTree(INIConfig):
    """Presentation tree using modern stdlib/YAML comment semantics."""

    _option_indent: int | None = None

    def _parse(self, line: str):
        if line.lstrip().startswith(("#", ";")):
            return CommentLine(line=line)
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        section = SectionLine.parse(stripped)
        if section is not None:
            self._option_indent = None
            section.line = line.rstrip("\n")
            return section
        previous_indent = getattr(self, "_option_indent", None)
        result = (OptionLine.parse(stripped)
                  if previous_indent is None or indent <= previous_indent else None)
        if result is not None:
            self._option_indent = indent
        else:
            result = super()._parse(line)
        if isinstance(result, CommentLine):
            # Legacy iniparse recognizes "rem" even in keys like "remove".
            result = OptionLine.parse(line)
        if isinstance(result, OptionLine):
            result = IndentedOptionLine(result.name, result.value, separator=result.separator)
            result.indent = line[:indent]
            # iniparse's legacy parser strips ';' suffixes. Modern ConfigParser
            # does not: they are part of the YAML-encoded value.
            match = OptionLine.regex.match(stripped.rstrip())
            raw = match.group("value")
            result.comment = None
            result.comment_separator = None
            result.value = raw
            # YAML tokens identify comments outside quoted and flow values.
            try:
                tokens = list(yaml.scan(raw))
            except yaml.YAMLError:
                tokens = []  # a flow value can continue on subsequent lines
            meaningful = [token for token in tokens if token.end_mark.index > token.start_mark.index]
            end = max((token.end_mark.index for token in meaningful), default=0)
            suffix = raw[end:]
            if tokens and suffix.lstrip().startswith("#"):
                offset = raw.index("#", end)
                result.value = raw[:offset].rstrip()
                result.comment = raw[offset + 1:]
                result.comment_separator = "#"
                result.comment_offset = stripped.index(raw) + offset
            result.line = line.rstrip("\n")
        return result


class IniDocument(Document):
    """Edit iniparse line containers with explicit leading-comment ownership."""

    def __init__(self, source: str, values: Mapping[str, Any]):
        super().__init__(source, values)
        self.tree = IniTree(io.StringIO(source), optionxformvalue=None)

    @staticmethod
    def _reconcile_lines(container: Any, desired: Mapping[str, Any], old: Mapping[str, Any], *, root=False):
        lines = container.contents
        remaining = []
        pending = []
        seen = False
        for node in lines:
            if isinstance(node, (CommentLine, EmptyLine)):
                pending.append(node)
                continue
            if isinstance(node, LineContainer) and isinstance(node.contents[0], OptionLine):
                key = node.name
                if key in desired:
                    remaining.extend(pending)
                    if key not in old or not equivalent(old[key], desired[key]):
                        annotations = [line for line in node.contents if isinstance(line, CommentLine)]
                        node.value = _dump_value(desired[key])
                        node.contents[1:1] = annotations
                    remaining.append(node)
                elif not seen and root:
                    remaining.extend(pending)
                seen = True
            else:
                remaining.extend(pending)
                remaining.append(node)
            pending = []
        remaining.extend(pending)
        existing = {n.name for n in remaining
                    if isinstance(n, LineContainer) and isinstance(n.contents[0], OptionLine)}
        # Append before trailing comments rather than after a footer.
        insert = len(remaining)
        while insert and isinstance(remaining[insert - 1], (CommentLine, EmptyLine)):
            insert -= 1
        for key, value in desired.items():
            if key not in existing:
                remaining.insert(insert, LineContainer(OptionLine(key, _dump_value(value))))
                insert += 1
        container.contents = remaining

    def render(self, desired: Mapping[str, Any]) -> str:
        keys = [node.name for section in self.tree._data.contents
                if isinstance(section, LineContainer) and section.name == "DEFAULT"
                for node in section.contents
                if isinstance(node, LineContainer) and isinstance(node.contents[0], OptionLine)]
        desired = document_layout(keys, desired)
        old = document_layout(keys, self.values)
        sections = {key: value for key, value in desired.items() if isinstance(value, Mapping)}
        defaults = {key: value for key, value in desired.items() if not isinstance(value, Mapping)}
        wanted = {"DEFAULT": defaults, **sections}
        old_defaults = {key: value for key, value in old.items() if not isinstance(value, Mapping)}
        result = []
        pending = []
        seen = False
        existing = set()
        for node in self.tree._data.contents:
            if isinstance(node, (CommentLine, EmptyLine)):
                pending.append(node)
                continue
            name = node.name
            if name in wanted:
                result.extend(pending)
                self._reconcile_lines(node, wanted[name], old_defaults if name == "DEFAULT"
                                      else old.get(name, {}))
                result.append(node)
                existing.add(name)
            elif not seen:
                result.extend(pending)  # document header
            seen = True
            pending = []
        footer = pending
        for name, values in wanted.items():
            if name not in existing and values:
                section = LineContainer(SectionLine(name))
                self._reconcile_lines(section, values, {})
                result.append(section)
        self.tree._data.contents = result + footer
        text = str(self.tree)
        return text if text.endswith("\n") or not text else text + "\n"


class XmlBuilder(ET.TreeBuilder):
    """Keep comments inside and outside the XML root using parser events."""

    def __init__(self):
        super().__init__(insert_comments=True, insert_pis=True)
        self.depth = 0
        self.started = False
        self.before: list[ET.Element] = []
        self.after: list[ET.Element] = []

    def start(self, tag, attrs):
        self.started = True
        self.depth += 1
        return super().start(tag, attrs)

    def end(self, tag):
        node = super().end(tag)
        self.depth -= 1
        return node

    def comment(self, text):
        node = super().comment(text)
        if not self.depth:
            (self.after if self.started else self.before).append(node)
        return node

    def pi(self, target, text=None):
        node = super().pi(target, text)
        if not self.depth:
            (self.after if self.started else self.before).append(node)
        return node


class XmlDocument(Document):
    """Reconcile the constrained XML vocabulary while retaining annotations."""

    def __init__(self, source: str, values: Mapping[str, Any]):
        super().__init__(source, values)
        builder = XmlBuilder()
        self.tree = ET.fromstring(source, parser=ET.XMLParser(target=builder)) if source else ET.Element("config")
        self.before, self.after = builder.before, builder.after

    def _reconcile(self, parent: ET.Element, desired: Mapping[str, Any], old: Mapping[str, Any], *, root=False):
        children = list(parent)
        kept = []
        pending = []
        seen = False
        existing = set()
        previous = None
        previous_kept = False
        for child in children:
            if child.tag in (ET.Comment, ET.ProcessingInstruction):
                # A same-line comment belongs to the previous entry.
                if previous is not None and not (previous.tail or "").count("\n"):
                    if previous_kept:
                        kept.append(child)
                else:
                    pending.append(child)
                previous = child
                continue
            key = child.get("name") if child.tag == "section" else child.get("key")
            if key is None:
                raise ValueError("XML configuration element has no key/name attribute")
            same_shape = key in desired and (child.tag == "section") == isinstance(desired[key], Mapping)
            if same_shape:
                kept.extend(pending)
                value = desired[key]
                if isinstance(value, Mapping):
                    if child.tag != "section":
                        child.tag = "section"
                        child.attrib = {"name": key}
                        child.text = "\n"
                    self._reconcile(child, value, old.get(key, {}) if isinstance(old.get(key), Mapping) else {})
                else:
                    if child.tag != "entry":
                        child.tag = "entry"
                        child.attrib = {"key": key}
                        child[:] = []
                    if key not in old or not equivalent(old[key], value):
                        child.text = _dump_value(value)
                        for annotation in child:
                            annotation.tail = ""
                kept.append(child)
                existing.add(key)
            elif not seen and root:
                kept.extend(pending)
            seen = True
            pending = []
            previous = child
            previous_kept = same_shape
        for key, value in desired.items():
            if key not in existing:
                if isinstance(value, Mapping):
                    node = ET.Element("section", {"name": key})
                    self._reconcile(node, value, {})
                else:
                    node = ET.Element("entry", {"key": key})
                    node.text = _dump_value(value)
                node.tail = "\n"
                kept.append(node)
        parent[:] = kept + pending

    def render(self, desired: Mapping[str, Any]) -> str:
        keys = [child.get("key") for child in self.tree if child.tag == "entry"]
        self._reconcile(self.tree, document_layout(keys, desired),
                        document_layout(keys, self.values), root=True)
        if not self.source:
            ET.indent(self.tree, space="  ")
        pieces = ["<?xml version='1.0' encoding='utf-8'?>\n"]
        pieces.extend(ET.tostring(node, encoding="unicode") + "\n" for node in self.before)
        pieces.append(ET.tostring(self.tree, encoding="unicode"))
        pieces.extend("\n" + ET.tostring(node, encoding="unicode") for node in self.after)
        return "".join(pieces) + "\n"


class JsonDocument(Document):
    def render(self, desired: Mapping[str, Any]) -> str:
        return json.dumps(dict(desired), indent=2, sort_keys=True) + "\n"


class CsvDocument(Document):
    def render(self, desired: Mapping[str, Any]) -> str:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=["key", "value"])
        writer.writeheader()
        for key, value in Csv._flatten(desired).items():
            writer.writerow({"key": key, "value": _dump_value(value)})
        return stream.getvalue()


ADAPTERS = {Yaml: YamlDocument, Toml: TomlDocument, Ini: IniDocument,
            Xml: XmlDocument, Json: JsonDocument, Csv: CsvDocument}


def render_document(parser: type[Parser], source: str, values: Mapping[str, Any],
                    desired: Mapping[str, Any]) -> str:
    """Emit a reconciled candidate without touching the destination."""
    adapter = next((cls for base, cls in ADAPTERS.items() if issubclass(parser, base)), None)
    if adapter is None:
        raise ValueError(f"No document adapter for {parser.__name__}")
    return adapter(source, values).render(desired)


def install_draft(draft: Path, target: Path, *, create_only: bool = False):
    """Install complete bytes; initialization never overwrites a raced target."""
    if target.exists():
        draft.chmod(stat.S_IMODE(target.stat().st_mode))
    if create_only:
        # Hard-link creation is atomic and fails if the destination exists.
        os.link(draft, target)
        draft.unlink()
    else:
        draft.replace(target)


def save_document(parser: type[Parser], path: str | Path, data: Mapping[str, Any]):
    """Validate, reconcile the latest document, and replace it atomically."""
    target = Path(path).expanduser()
    desired = normalized(data)
    source = target.read_text() if target.exists() else ""
    values = normalized(parser.load(target)) if target.exists() else {}
    text = render_document(parser, source, values, desired)
    target.parent.mkdir(parents=True, exist_ok=True)
    draft = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=f".{target.name}.", suffix=target.suffix,
                                         delete=False, newline="") as file:
            draft = Path(file.name)
            file.write(text)
        actual = normalized(parser.load(draft))
        if not equivalent(actual, desired):
            raise ValueError(f"Values cannot be faithfully represented by {parser.__name__}")
        install_draft(draft, target)
    finally:
        if draft is not None:
            draft.unlink(missing_ok=True)
