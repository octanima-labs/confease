"""Shared path behavior, independent of persistence format."""

from argparse import Namespace
from copy import deepcopy

import pytest

from confease import CLI, DEF, ENV, SYS, USR, Confease, Confitem
from confease.mappings import flatten, flatten_items, nest


def test_example_defaults_and_recursive_section_snapshots():
    data = {"key": {"one": 1, "subkey": {"two": 2, "subsubkey": {
        "three": 3, "subsubsubkey": "hello"}}}}
    original = deepcopy(data)
    conf = Confease(items=data)
    assert conf["key"] == data["key"]
    assert conf["key.subkey"] == data["key"]["subkey"]
    assert conf["key.subkey.subsubkey.three"] == 3
    assert conf.get_item("key.subkey.two") == Confitem("key.subkey.two", 2, DEF)
    snapshot = conf["key"]
    snapshot["subkey"]["subsubkey"]["three"] = 99
    assert conf["key.subkey.subsubkey.three"] == 3
    conf["key.subkey.subsubkey.three"] = 4
    conf.set("key.subkey", {"added": False})
    assert conf["key.subkey.two"] == 2
    assert conf["key.subkey.added"] is False
    assert data == original


def test_mixed_dotted_mapping_keys_and_opaque_lists():
    value = [{"name": "example", "settings": {"enabled": True}}]
    conf = Confease(items={"a.b": {"c.d": 1, "list": value}})
    assert conf["a"] == {"b": {"c": {"d": 1}, "list": value}}
    assert conf["a.b.list.0.name"] is None
    conf.set("a.b.c", {"other.leaf": 2})
    assert conf["a.b.c"] == {"d": 1, "other": {"leaf": 2}}


@pytest.mark.parametrize("key", ["", ".a", "a.", "a..b", "a.b..c"])
def test_malformed_paths_rejected(key):
    with pytest.raises(ValueError, match="nonempty"):
        Confease(items={key: 1})
    conf = Confease()
    with pytest.raises(ValueError, match="nonempty"):
        conf.set(key, 1)


@pytest.mark.parametrize("first,second", [
    ("a.b", "a.b.c"), ("a.b.c", "a.b"), ("a.b.c.d", "a.b.c"),
])
def test_ancestor_collisions_at_any_depth(first, second):
    conf = Confease()
    conf.set(first, 1)
    with pytest.raises(ValueError, match="collides"):
        conf.set(second, 2)
    assert conf[first] == 1


def test_duplicate_logical_paths_and_failed_mapping_assignment():
    with pytest.raises(ValueError, match="Duplicate"):
        Confease(items={"a.b.c": 1, "a": {"b": {"c": 2}}})
    with pytest.raises(ValueError, match="Duplicate"):
        flatten_items([("a.b.c", 1), ("a.b.c", 2)])
    conf = Confease(items={"a.b": 1})
    with pytest.raises(ValueError, match="collides"):
        conf.set("a", {"new": 2, "b": {"child": 3}})
    assert conf["a.new"] is None
    assert conf["a.b"] == 1


def test_empty_mapping_presence_origins_filtering_and_deletion():
    conf = Confease(items={"default": {}, "a": {"empty": {}}})
    conf.set("user.empty", {})
    assert conf["default"] == {}
    snapshot = conf["default"]
    snapshot["new"] = 1
    assert conf["default"] == {}
    assert conf.get_item("a.empty") == Confitem("a.empty", {}, DEF)
    assert conf.get_item("user.empty") == Confitem("user.empty", {}, USR)
    assert conf._data_for_save() == {"user": {"empty": {}}}
    assert conf._data_for_save(False) == {
        "default": {}, "a": {"empty": {}}, "user": {"empty": {}},
    }
    assert conf.delete("a.empty") is True
    assert conf.delete("a.empty") is False
    assert conf["a"] is None
    conf.set("key", {"subkey": {"two": 2, "subsubkey": {"three": 3}}})
    assert conf.delete("key.subkey.subsubkey") is True
    assert conf["key"] == {"subkey": {"two": 2}}


def test_cycles_rejected_but_shared_mapping_aliases_allowed():
    cyclic = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="Cyclic"):
        flatten(cyclic)
    shared = {"leaf": 1}
    assert nest(flatten({"a": shared, "b": shared})) == {
        "a": {"leaf": 1}, "b": {"leaf": 1},
    }


def test_deep_source_overlays_keep_sibling_origins(tmp_path, monkeypatch):
    path = tmp_path / "system.yaml"
    path.write_text("key:\n  subkey:\n    two: 2\n")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("key.subkey.two", "3")
    conf = Confease(items={"key": {"subkey": {"two": 1, "sibling": 4}}})
    conf.reload_files(path)
    assert conf.get_item("key.subkey.two").origin == SYS
    conf.reload_env()
    assert conf.get_item("key.subkey.two") == Confitem("key.subkey.two", 3, ENV)
    conf.reload_cli(Namespace(key={"subkey": {"two": 5}}))
    assert conf.get_item("key.subkey.two") == Confitem("key.subkey.two", 5, CLI)
    assert conf.get_item("key.subkey.sibling") == Confitem("key.subkey.sibling", 4, DEF)
