"""Backup policy integrates with each persisted model operation."""

import pytest
import yaml

from confease import CLI, DEF, Confease, Csv, Ini, Json, Toml, Xml, Yaml


def snapshots(path):
    return list(path.parent.glob("*.bkp"))


def test_default_policy_and_save_overrides(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("key: 1\n")
    conf = Confease(path)
    conf.save()
    assert snapshots(path) == []
    conf.set("key", 2)
    conf.save(backup=True)
    assert len(snapshots(path)) == 1
    conf.save()
    assert len(snapshots(path)) == 1
    protected = Confease(path, __backup__=True)
    assert protected.get("backup") is None
    protected.save(backup=False)
    assert len(snapshots(path)) == 1
    protected.save()
    assert len(snapshots(path)) == 2


@pytest.mark.parametrize("policy", [False, True])
def test_constructor_policy_is_independent_of_backup_config_default(tmp_path, policy):
    path = tmp_path / "settings.yaml"
    path.write_text("key: 1\n")
    conf = Confease(path, __backup__=policy, backup="daily")
    assert conf.get("backup") == "daily"
    assert conf.get_item("backup").origin == DEF
    assert conf.get("__backup__") is None
    conf.save()
    assert len(snapshots(path)) == int(policy)
    assert Yaml.load(path) == {"key": 1}
    conf.save(backup=not policy)
    assert len(snapshots(path)) == 1
    assert conf.get("backup") == "daily"
    conf.save(user_only=False, backup=False)
    assert Yaml.load(path) == {"backup": "daily", "key": 1}


def test_plain_backup_keyword_remains_a_default_without_enabling_policy(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("key: 1\n")
    conf = Confease(path, backup=True)
    assert conf.get("backup") is True
    assert conf.get_item("backup").origin == DEF
    conf.save()
    assert snapshots(path) == []


def test_automatic_saves_snapshot_each_previous_document(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("key: 1\nremove: null\n")
    conf = Confease(path, reload=True, __backup__=True)
    originals = []
    originals.append(path.read_bytes())
    conf.set("key", 2)
    originals.append(path.read_bytes())
    conf["key"] = 3
    originals.append(path.read_bytes())
    assert conf.delete("remove")
    assert not conf.delete("absent")
    assert sorted(p.read_bytes() for p in snapshots(path)) == sorted(originals)
    assert Yaml.load(path) == {"key": 3}


def test_memory_only_and_missing_destinations(tmp_path):
    conf = Confease(__backup__=True, key=1)
    conf.save()
    conf.reset()
    path = tmp_path / "new.yaml"
    conf = Confease(path, __backup__=True, key=1)
    conf.reset()
    assert not path.exists()
    conf.save(user_only=False)
    assert snapshots(path) == []
    conf.reset()
    assert snapshots(path) == []


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", '# header\r\nkey: "old" # inline\r\n'),
    (Json, ".json", '{ "key" : "old" }\r\n'),
    (Toml, ".toml", '# header\r\nkey = "old" # inline\r\n'),
    (Ini, ".ini", '[DEFAULT]\r\n# header\r\nkey = old\r\n'),
    (Xml, ".xml", '<config><!-- header --><entry key="key">old</entry></config>\r\n'),
    (Csv, ".csv", 'key,value\r\nkey,old\r\n'),
])
def test_all_formats_preserve_original_and_filter_origins(tmp_path, parser, suffix, text):
    path = tmp_path / f"settings{suffix}"
    original = text.encode()
    path.write_bytes(original)
    conf = Confease(path, parser=parser, __backup__=True, fallback=1)
    conf.set("key", "new")
    conf._set_item("cli_only", True, CLI)
    conf.save()
    assert snapshots(path)[0].read_bytes() == original
    assert parser.load(path) == {"key": "new"}
    assert conf.get_item("fallback").origin == DEF
    assert conf.get_item("cli_only").origin == CLI


@pytest.mark.parametrize("override,count", [(None, 1), (False, 0), (True, 1)])
def test_template_reset_backup_and_exact_copy(tmp_path, override, count):
    path = tmp_path / "settings.yaml"
    template = tmp_path / "template.yaml"
    original = b"key: original\r\n"
    template_bytes = b'# header\r\nkey: "default" # inline\r\n'
    path.write_bytes(original)
    template.write_bytes(template_bytes)
    conf = Confease(path, template=template, __backup__=True)
    conf.reset(backup=override)
    assert path.read_bytes() == template_bytes
    assert len(snapshots(path)) == count
    if count:
        assert snapshots(path)[0].read_bytes() == original


def test_reset_missing_target_has_no_backup(tmp_path):
    template = tmp_path / "template.yaml"
    template.write_text("key: default\n")
    path = tmp_path / "settings.yaml"
    Confease(path, template=template, __backup__=True).reset()
    assert snapshots(path) == []


@pytest.mark.parametrize("override,count", [(None, 1), (False, 0), (True, 1)])
def test_direct_editor_snapshot_precedes_launch(tmp_path, monkeypatch, override, count):
    path = tmp_path / "settings.yaml"
    path.write_bytes(b"key: original\r\n")
    conf = Confease(path, __backup__=True)
    previous = conf._entries

    from confease import TextEditor
    conf.editor = TextEditor()

    def edit(target):
        assert target == path
        assert len(snapshots(path)) == count
        if count:
            assert snapshots(path)[0].read_bytes() == path.read_bytes()
        target.write_text("key: [\n")

    monkeypatch.setattr(conf.editor, "open", edit)
    with pytest.raises(yaml.YAMLError):
        conf.edit_file(backup=override)
    assert path.read_text() == "key: [\n"
    assert conf._entries is previous


def test_direct_editor_missing_target_and_unchanged_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    conf = Confease(path, __backup__=True)
    from confease import TextEditor
    conf.editor = TextEditor()
    monkeypatch.setattr(conf.editor, "open", lambda target: None)
    conf.edit_file()
    assert not path.exists()
    assert snapshots(path) == []
    path.write_text("key: original\n")
    conf.edit_file()
    assert len(snapshots(path)) == 1


@pytest.mark.parametrize("operation", ["save", "reset", "edit_file"])
def test_backup_failure_prevents_mutation_or_editor(tmp_path, monkeypatch, operation):
    path = tmp_path / "settings.yaml"
    template = tmp_path / "template.yaml"
    path.write_text("key: original\n")
    template.write_text("key: default\n")
    conf = Confease(path, template=template, __backup__=True)
    conf.set("key", "unsaved")
    previous = conf._entries.copy()
    from confease import TextEditor
    conf.editor = TextEditor()

    def fail(target):
        raise OSError("snapshot failed")

    def unexpected_editor(target):
        pytest.fail("Editor must not launch")

    monkeypatch.setattr("confease.backups.create_backup", fail)
    monkeypatch.setattr("confease.model.create_backup", fail)
    monkeypatch.setattr(conf.editor, "open", unexpected_editor)
    with pytest.raises(OSError, match="snapshot failed"):
        getattr(conf, operation)()
    assert path.read_text() == "key: original\n"
    assert conf._entries == previous
    assert snapshots(path) == []
    assert list(tmp_path.glob(".*")) == []


def test_invalid_candidates_do_not_create_backups(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text("key = 1\n")
    conf = Confease(path, parser=Toml, __backup__=True)
    conf.set("key", None)
    with pytest.raises(ValueError):
        conf.save()
    assert path.read_text() == "key = 1\n"
    assert snapshots(path) == []
    template = tmp_path / "template.toml"
    template.write_text("key = 2\n")
    conf = Confease(path, parser=Toml, template=template, __backup__=True)
    template.write_text("key = [\n")
    with pytest.raises(ValueError):
        conf.reset()
    assert path.read_text() == "key = 1\n"
    assert snapshots(path) == []
