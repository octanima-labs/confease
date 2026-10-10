"""Constructor controls and default configuration data have separate inputs."""

from collections import UserDict
from copy import deepcopy

import pytest

from confease import CLI, DEF, ORIGINS, USR, Confease, Confitem, Json, Yaml


def test_constructor_option_names_are_ordinary_configuration_keys(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"saved": 1}\n')
    items = {
        "path": "/srv/data",
        "reload": "manual",
        "parser": "application-parser",
        "template": "application-template",
        "preference": "application-preference",
        "backup": "daily",
        "items": "application-items",
        "__backup__": "ordinary-key",
        "autoload": "future-option-key",
    }
    conf = Confease(path, reload=True, parser=Json, preference=[USR, DEF], backup=True, items=items)

    for key, value in items.items():
        assert conf.get_item(key) == Confitem(key, value, DEF)
    assert conf.preference == [USR, DEF, CLI, "env", "system"]
    conf.set("saved", 2)
    assert Json.load(path) == {"saved": 2}
    snapshots = list(tmp_path.glob("*.bkp"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text() == '{"saved": 1}\n'
    assert not (tmp_path / "settings.yaml").exists()


def test_positional_constructor_options_keep_their_order(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"saved": 1}\n')
    conf = Confease(path, True, Json, None, [USR, DEF], True, {"backup": "daily"})

    assert conf.preference == [USR, DEF, CLI, "env", "system"]
    assert conf.get_item("backup") == Confitem("backup", "daily", DEF)
    conf.set("saved", 2)
    assert Json.load(path) == {"saved": 2}
    assert len(list(tmp_path.glob("*.bkp"))) == 1


def test_items_preserve_types_origins_and_caller_dictionary():
    items = {
        "number": 12,
        "enabled": False,
        "optional": None,
        "servers": ["alpha", "beta"],
        "database": {"host": "localhost", "port": 5432},
        "cache.enabled": True,
    }
    original = deepcopy(items)
    conf = Confease(items=items)

    for key in ("number", "enabled", "optional", "servers"):
        item = conf.get_item(key)
        assert item == Confitem(key, items[key], DEF)
        assert type(item.value) is type(items[key])
    assert conf["database"] == {"host": "localhost", "port": 5432}
    assert conf.get_item("database.port") == Confitem("database.port", 5432, DEF)
    assert conf.get_item("cache.enabled") == Confitem("cache.enabled", True, DEF)
    assert items == original


@pytest.mark.parametrize("options", [{}, {"items": None}, {"items": {}}])
def test_empty_items_provide_no_defaults(options):
    conf = Confease(**options)

    assert conf._defaults == []
    assert conf.get_item("items") is None
    assert conf.get_item("backup") is None
    assert conf.preference == ORIGINS


@pytest.mark.parametrize("items", [[], [1], "", "key", False, True, 0, 1, (), UserDict(), object()])
def test_items_reject_non_dictionary_inputs(items):
    with pytest.raises(TypeError, match="items must be a dictionary or None"):
        Confease(items=items)


def test_items_accept_dictionary_subclasses():
    class Defaults(dict):
        pass

    conf = Confease(items=Defaults(key=1))

    assert conf.get_item("key") == Confitem("key", 1, DEF)


@pytest.mark.parametrize("items", [
    {"a": {"b": {"c": 1}}},
    {"a.b.c": 1},
    {"database": "sqlite", "database.host": "localhost"},
    {"database": {"host": "localhost"}, "database.host": "remote"},
])
def test_items_retain_key_validation(items):
    with pytest.raises(ValueError):
        Confease(items=items)


@pytest.mark.parametrize("options", [{}, {"items": None}, {"items": {}}])
def test_template_allows_empty_items(tmp_path, options):
    template = tmp_path / "defaults.yaml"
    template.write_text("key: fallback\n")
    path = tmp_path / "settings.yaml"
    conf = Confease(path, template=template, **options)

    assert conf.get_item("key") == Confitem("key", "fallback", DEF)
    assert not path.exists()


def test_template_rejects_nonempty_items(tmp_path):
    template = tmp_path / "defaults.yaml"
    template.write_text("key: fallback\n")

    with pytest.raises(AttributeError, match="single default source"):
        Confease(template=template, items={"key": "other"})


@pytest.mark.parametrize("options", [{"DEBUG": False}, {"__backup__": True}])
def test_legacy_constructor_keywords_are_rejected(options):
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        Confease(**options)


def test_items_defaults_remain_memory_only_and_resettable(tmp_path):
    path = tmp_path / "settings.yaml"
    conf = Confease(path, items={"key": "fallback"})

    assert conf.get_item("key") == Confitem("key", "fallback", DEF)
    conf.set("key", "changed")
    conf.reset()
    assert conf.get_item("key") == Confitem("key", "fallback", DEF)
    assert not path.exists()
    conf.save()
    assert Yaml.load(path) == {}
    conf.save(user_only=False)
    assert Yaml.load(path) == {"key": "fallback"}
