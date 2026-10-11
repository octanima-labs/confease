"""Empty sections grow without permitting mapping/value shape changes."""

from argparse import Namespace
from copy import deepcopy

import pytest
from edital import EditResult

from confease import CLI, DEF, ENV, SYS, USR, Confease, Csv, Ini, Json, Toml, Xml, Yaml
from confease.cli import assignments, main
from confease.mappings import flatten, flatten_items, nest

FORMATS = [(Yaml, ".yaml"), (Json, ".json"), (Toml, ".toml"),
           (Ini, ".ini"), (Xml, ".xml"), (Csv, ".csv")]


@pytest.mark.parametrize("reverse", [False, True])
def test_empty_parent_normalization_preserves_input_and_detects_duplicates(reverse):
    pairs = [("a", {}), ("a.inner", {}), ("a.inner.child", 2)]
    if reverse:
        pairs.reverse()
    data = dict(pairs)
    original = deepcopy(data)
    assert flatten(data) == {"a.inner.child": 2}
    assert nest(data) == {"a": {"inner": {"child": 2}}}
    assert data == original
    with pytest.raises(ValueError, match="Duplicate"):
        flatten_items([*pairs, ("a", {})])


@pytest.mark.parametrize("key", ["a", "a.inner"])
@pytest.mark.parametrize("mapping", [False, True])
def test_population_snapshots_origins_and_reset(key, mapping):
    conf = Confease(items={key: {}, "sibling": {}})
    conf.set(key if mapping else f"{key}.b", {"b": 2} if mapping else 2)
    assert conf[key] == {"b": 2}
    assert conf.get_item(key) is None
    assert conf.get_item(f"{key}.b").origin == USR
    snapshot = conf[key]
    snapshot["b"] = 99
    conf.set(key, {})
    assert conf[key] == {"b": 2}
    assert conf._data_for_save() == nest({f"{key}.b": 2})
    assert conf.get_item("sibling").origin == DEF
    conf.reset()
    assert conf[key] == {}
    assert conf.get_item(key).origin == DEF


@pytest.mark.parametrize("scalar", [2, "hello", True, None, [], [{"b": 2}]])
@pytest.mark.parametrize("mapping", [{}, {"b": 2}])
@pytest.mark.parametrize("reverse", [False, True])
def test_shape_changes_rejected_without_partial_assignment(scalar, mapping, reverse):
    old, new = (scalar, mapping) if reverse else (mapping, scalar)
    conf = Confease(items={"a": {"target": old}})
    conf.get("a")
    previous = conf._entries
    with pytest.raises(ValueError, match="collides"):
        conf.set("a", {"added": 3, "target": new})
    assert conf._entries is previous
    assert conf["a"] == {"target": old}


def test_leaf_type_changes_and_explicit_structural_redefinition():
    conf = Confease(items={"a": 2})
    conf.set("a", "hello")
    assert conf["a"] == "hello"
    assert conf.delete("a")
    conf.set("a", {})
    conf.set("a.b", 2)
    assert conf["a"] == {"b": 2}


@pytest.mark.parametrize("source", ["load", "file", "cli", "env"])
def test_source_population_and_conflict_atomicity(tmp_path, monkeypatch, source):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    conf = Confease(items={"a.inner": {}, "z": 1}, preference=[DEF])
    path = tmp_path / "source.yaml"

    def overlay(data):
        if source == "cli":
            conf.reload_cli(Namespace(**data))
        elif source == "env":
            monkeypatch.setenv("a.inner", "{child: 2}")
            monkeypatch.setenv("z", "{}" if isinstance(data["z"], dict) else "1")
            conf.reload_env()
        else:
            Yaml.save(path, data)
            conf.load(path) if source == "load" else conf.reload_files(path)

    conf.get("a")
    previous = conf._entries
    with pytest.raises(ValueError, match="collides"):
        overlay({"a.inner": {"child": 2}, "z": {}})
    assert conf._entries is previous
    overlay({"a.inner": {"child": 2}, "z": 1})
    assert conf["a.inner"] == {"child": 2}
    origin = {"load": USR, "file": SYS, "cli": CLI, "env": ENV}[source]
    assert conf.get_item("a.inner.child").origin == origin
    assert conf.get_item("z").origin == (USR if source == "load" else DEF)
    if source in {"file", "cli"}:
        overlay({"a.inner": {}, "z": 1})
        assert conf["a.inner"] == {"child": 2}
        assert conf.get_item("a.inner.child").origin == origin


def test_load_empty_mapping_merges_with_populated_defaults(tmp_path):
    path = tmp_path / "source.yaml"
    path.write_text("a: {}\n")
    conf = Confease(items={"a.b": 2})
    conf.load(path)
    assert conf["a"] == {"b": 2}
    assert conf.get_item("a.b").origin == DEF


def test_environment_only_looks_up_known_keys(monkeypatch):
    conf = Confease(items={"a": {}})
    monkeypatch.setenv("a.b", "2")
    conf.reload_env()
    assert conf["a"] == {}
    monkeypatch.setenv("a", "{b: 2}")
    conf.reload_env()
    assert conf["a"] == {"b": 2}
    assert conf.get_item("a.b").origin == ENV


@pytest.mark.parametrize("updates", [["a={}", "a.b=2"], ["a.b=2", "a={}"]])
def test_scripted_cli_normalizes_empty_sections(tmp_path, updates):
    assert assignments(updates) == {"a.b": 2}
    path = tmp_path / "config.yaml"
    path.write_text("a: {}\n")
    assert main([str(path), *[arg for update in updates for arg in ("-u", update)]]) == 0
    assert Yaml.load(path) == {"a": {"b": 2}}
    with pytest.raises(ValueError, match="collides"):
        assignments(["a={}", "a=2"])


@pytest.mark.parametrize("parser,suffix", FORMATS)
def test_population_round_trip_and_user_filtering(tmp_path, parser, suffix):
    path = tmp_path / f"config{suffix}"
    parser.save(path, {"a": {"b": 2}, "user_empty": {}})
    conf = Confease(path, parser=parser, items={"a": {}, "default_empty": {}})
    assert conf["a"] == {"b": 2}
    conf.set("a.c", 3)
    conf.save()
    assert parser.load(path) == {"a": {"b": 2, "c": 3}, "user_empty": {}}
    conf.save(user_only=False)
    assert parser.load(path) == {
        "a": {"b": 2, "c": 3}, "user_empty": {}, "default_empty": {},
    }


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("parser,suffix,parts", [
    (Yaml, ".yaml", ["a: {}\n", "a.b: 2\n"]),
    (Json, ".json", ['"a": {}', '"a.b": 2']),
    (Toml, ".toml", ["a = {}\n", '"a.b" = 2\n']),
    (Ini, ".ini", ["a = {}\n", "a.b = 2\n"]),
    (Xml, ".xml", ['<section name="a"/>', '<entry key="a.b">2</entry>']),
    (Csv, ".csv", ["a,{}\n", "a.b,2\n"]),
])
def test_parser_empty_ancestor_declarations(tmp_path, reverse, parser, suffix, parts):
    parts = list(reversed(parts)) if reverse else parts
    text = "".join(parts)
    if parser is Json:
        text = "{" + ",".join(parts) + "}"
    elif parser is Xml:
        text = "<config>" + text + "</config>"
    elif parser is Ini:
        text = "[DEFAULT]\n" + text
    elif parser is Csv:
        text = "key,value\n" + text
    path = tmp_path / f"input{suffix}"
    path.write_text(text)
    assert parser.load(path) == {"a": {"b": 2}}


def test_restore_and_editor_validate_population_before_installation(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("a: {}\n")
    conf = Confease(path, items={"a": {}, "scalar": 1})
    source = tmp_path / "snapshot"
    source.write_text("a.b: 2\n")
    conf.restore(source)
    assert conf["a"] == {"b": 2}
    previous = conf._entries
    exact = path.read_bytes()
    source.write_text("a.b: 3\nscalar.child: 4\n")
    with pytest.raises(ValueError, match="collides"):
        conf.restore(source)
    assert conf._entries is previous
    assert path.read_bytes() == exact

    def edit(text, *, title, validator):
        assert validator("a.c: 3\nscalar.child: 4\n") is not None
        assert validator("a.c: 3\n") is None
        assert conf._entries is previous
        assert path.read_bytes() == exact
        return EditResult("accepted", "a.c: 3\n")

    monkeypatch.setattr(conf.editor, "edit", edit)
    conf.edit_file()
    assert conf["a"] == {"c": 3}
    assert path.read_text() == "a.c: 3\n"
