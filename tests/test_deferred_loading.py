"""Ordinary first use loads deferred destinations before reads and overlays."""

from argparse import Namespace

import pytest
import yaml

from confease import CLI, DEF, ENV, USR, Confease, Confitem, Yaml


def test_eager_default_and_deferred_binding(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("key: original\n")
    eager = Confease(path)
    assert eager._entries == [Confitem("key", "original", USR)]
    path.write_text("key: [\n")
    with pytest.raises(yaml.YAMLError):
        Confease(path)
    deferred = Confease(path, autoload=False, backup=True)
    assert deferred._entries is None
    assert path.read_text() == "key: [\n"
    assert list(tmp_path.glob("*.bkp")) == []


@pytest.mark.parametrize("content", ["key: disk\n", ""])
def test_first_read_loads_valid_or_empty_target_once(tmp_path, content):
    path = tmp_path / "settings.yaml"
    path.write_text(content)
    conf = Confease(path, autoload=False)
    assert conf["key"] == ("disk" if content else None)
    path.write_text("key: externally-changed\n")
    assert conf["key"] == ("disk" if content else None)
    assert conf._entries is not None


@pytest.mark.parametrize("reload", [False, True])
def test_missing_target_first_read_uses_defaults_without_creating_parents(tmp_path, reload):
    path = tmp_path / "absent" / "settings.yaml"
    conf = Confease(path, autoload=False, reload=reload, backup=True, items={"key": 1})
    assert not path.parent.exists()
    assert conf.get_item("key") == Confitem("key", 1, DEF)
    assert not path.parent.exists()
    if reload:
        with pytest.raises(FileNotFoundError):
            conf.get("key")


def test_runtime_only_deferred_defaults_and_autoload_data_are_independent():
    conf = Confease(autoload=False, items={"autoload": "app", "key": 1})
    assert conf._entries is None
    conf.save()
    assert conf.get_item("autoload") == Confitem("autoload", "app", DEF)
    assert conf["key"] == 1


@pytest.mark.parametrize("options, error", [
    ({"parser": object}, ValueError),
    ({"preference": ["unknown"]}, ValueError),
    ({"items": []}, TypeError),
    ({"items": {"a..b": 1}}, ValueError),
])
def test_deferred_constructor_still_validates_controls_and_defaults(tmp_path, options, error):
    path = tmp_path / "settings.yaml"
    path.write_text("invalid: [\n")
    with pytest.raises(error):
        Confease(path, autoload=False, **options)


@pytest.mark.parametrize("content, error", [(None, FileNotFoundError), ("key: [\n", yaml.YAMLError)])
def test_deferred_constructor_still_validates_template(tmp_path, content, error):
    path = tmp_path / "absent" / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    if content is not None:
        template.write_text(content)
    with pytest.raises(error):
        Confease(path, template=template, autoload=False)
    assert not path.parent.exists()


def test_autoload_is_keyword_only():
    with pytest.raises(TypeError):
        Confease(None, False, Yaml, None, None, False, None, False)


@pytest.mark.parametrize("operation", ["get", "get_item", "index", "set", "assign", "delete", "save",
                                       "cli", "env", "files", "sources"])
def test_malformed_target_blocks_every_ordinary_first_operation_and_allows_retry(tmp_path, operation):
    path = tmp_path / "settings.yaml"
    original = b"key: [\n"
    path.write_bytes(original)
    conf = Confease(path, autoload=False, backup=True, items={"fallback": 3})
    operations = {
        "get": lambda: conf.get("key"),
        "get_item": lambda: conf.get_item("key"),
        "index": lambda: conf["key"],
        "set": lambda: conf.set("new", 2),
        "assign": lambda: conf.__setitem__("new", 2),
        "delete": lambda: conf.delete("key"),
        "save": conf.save,
        "cli": lambda: conf.reload_cli(Namespace()),
        "env": conf.reload_env,
        "files": conf.reload_files,
        "sources": conf.load_sources,
    }
    with pytest.raises(yaml.YAMLError):
        operations[operation]()
    assert conf._entries is None
    assert path.read_bytes() == original
    assert list(tmp_path.glob("*.bkp")) == []
    path.write_text("key: repaired\n")
    assert conf["key"] == "repaired"
    assert conf.get_item("fallback") == Confitem("fallback", 3, DEF)


@pytest.mark.parametrize("operation", ["set", "assign", "save", "delete"])
def test_first_mutation_or_save_retains_unrelated_disk_values(tmp_path, operation):
    path = tmp_path / "settings.yaml"
    path.write_text("key: original\nunrelated: 42\n")
    conf = Confease(path, autoload=False)
    if operation == "set":
        conf.set("key", "changed")
    elif operation == "assign":
        conf["key"] = "changed"
    elif operation == "delete":
        assert conf.delete("key")
    conf.save()
    assert Yaml.load(path)["unrelated"] == 42
    expected = "original" if operation == "save" else "changed"
    if operation == "delete":
        assert "key" not in Yaml.load(path)
    else:
        assert Yaml.load(path)["key"] == expected


@pytest.mark.parametrize("overlay", ["cli", "env", "files", "sources"])
def test_source_overlays_initialize_destination_and_respect_preference(tmp_path, monkeypatch, overlay):
    path = tmp_path / "settings.yaml"
    path.write_text("key: disk\nunrelated: retained\n")
    source = tmp_path / "overlay.yaml"
    source.write_text("key: overlay\n")
    monkeypatch.setenv("key", "overlay")
    monkeypatch.setattr("confease.model.Path.home", lambda: tmp_path)
    conf = Confease(path, autoload=False, items={"fallback": 1})
    if overlay == "cli":
        conf.reload_cli(Namespace(key="overlay"))
        origin = CLI
    elif overlay == "env":
        conf.reload_env()
        origin = ENV
    elif overlay == "files":
        conf.reload_files(source)
        origin = USR
    else:
        conf.load_sources(Namespace(key="cli"), source, preference=[ENV, CLI, USR, DEF])
        origin = ENV
    assert conf.get_item("key") == Confitem("key", "overlay", origin)
    assert conf["unrelated"] == "retained"
    assert conf.get_item("fallback") == Confitem("fallback", 1, DEF)


def test_missing_template_target_overlays_do_not_copy_template(tmp_path):
    path = tmp_path / "absent" / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    template.write_text("key: default\n")
    conf = Confease(path, template=template, autoload=False)
    conf.reload_cli(Namespace(key="cli"))
    assert conf.get_item("key") == Confitem("key", "cli", CLI)
    assert not path.parent.exists()


@pytest.mark.parametrize("content", ["", "key: alternate\n"])
def test_explicit_alternate_load_establishes_authoritative_state(tmp_path, content):
    path = tmp_path / "settings.yaml"
    path.write_text("invalid: [\n")
    source = tmp_path / "alternate.yaml"
    source.write_text(content)
    conf = Confease(path, autoload=False)
    conf.load(source)
    assert conf["key"] == ("alternate" if content else None)


def test_failed_explicit_load_preserves_deferred_state(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("key: [\n")
    conf = Confease(path, autoload=False, items={"fallback": 1})
    with pytest.raises(yaml.YAMLError):
        conf.load()
    assert conf._entries is None
    assert conf._defaults == [Confitem("fallback", 1, DEF)]


@pytest.mark.parametrize("operation", ["read", "set", "delete", "save"])
def test_first_automatic_reload_operation_loads_once(tmp_path, monkeypatch, operation):
    path = tmp_path / "settings.yaml"
    original = "key: original\nunrelated: 42\n"
    path.write_text(original)
    conf = Confease(path, autoload=False, reload=True, backup=True)
    calls = []
    load = conf.load

    def tracked_load(*args):
        calls.append(args)
        return load(*args)

    monkeypatch.setattr(conf, "load", tracked_load)
    if operation == "read":
        assert conf["key"] == "original"
        path.write_text("key: updated\n")
        assert len(calls) == 1
        assert conf["key"] == "updated"
        assert len(calls) == 2
    else:
        if operation == "set":
            conf.set("key", "changed")
        elif operation == "delete":
            assert conf.delete("key")
        else:
            conf.save()
        assert len(calls) == 1
        assert Yaml.load(path)["unrelated"] == 42
        snapshots = list(tmp_path.glob("*.bkp"))
        assert len(snapshots) == 1
        assert snapshots[0].read_text() == original
