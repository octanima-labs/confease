"""Historical restoration commits exact validated bytes and coherent state."""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from confease import DEF, USR, Confease, Csv, Ini, Json, Toml, Xml, Yaml
from confease.backups import create_backup


@pytest.fixture
def frozen_time(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 7, 14, 30, 52)

    monkeypatch.setattr("confease.backups.datetime", Clock)


def test_restore_retains_source_defaults_template_and_policy(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("key: current\n")
    template = tmp_path / "template.yaml"
    template.write_text("key: default\nfallback: 3\n")
    conf = Confease(path, template=template, __backup__=True)
    defaults = conf._defaults
    source = tmp_path / "elsewhere" / "recovery.snapshot"
    source.parent.mkdir()
    content = b'# header\r\nkey: "historical" # inline\r\n'
    source.write_bytes(content)
    conf.restore(str(source), backup=False)
    assert source.read_bytes() == content == path.read_bytes()
    assert conf.get("key") == "historical"
    assert conf.get_item("key").origin == USR
    assert conf.get("fallback") == 3
    assert conf.get_item("fallback").origin == DEF
    assert conf._defaults is defaults
    assert conf._template == template
    assert conf._path == path
    assert conf._backup is True
    assert list(tmp_path.glob("*.bkp")) == []


@pytest.mark.parametrize("parser,suffix", [
    (Yaml, ".yaml"), (Json, ".json"), (Toml, ".toml"),
    (Ini, ".ini"), (Xml, ".xml"), (Csv, ".csv"),
])
def test_restore_uses_active_parser_not_backup_extension(tmp_path, parser, suffix):
    path = tmp_path / f"settings{suffix}"
    parser.save(path, {"key": 1})
    source = create_backup(path)
    original = source.read_bytes()
    conf = Confease(path, parser=parser)
    conf.set("key", 2)
    conf.save()
    conf.restore(source)
    assert path.read_bytes() == original
    assert source.read_bytes() == original
    assert conf.get("key") == 1


@pytest.mark.parametrize("existing", [False, True])
def test_recover_missing_or_malformed_destination(tmp_path, existing):
    path = tmp_path / "settings.yaml"
    conf = Confease(path, __backup__=True, fallback=1)
    if existing:
        path.write_text("key: [\n")
    source = tmp_path / "settings-20261006-143052.yaml.bkp"
    source.write_text("key: restored\n")
    conf.restore()
    assert path.read_bytes() == source.read_bytes()
    assert conf.get("key") == "restored"
    others = [p for p in tmp_path.glob("*.bkp") if p != source]
    assert len(others) == int(existing)
    if existing:
        assert others[0].read_text() == "key: [\n"


@pytest.mark.parametrize("content", ["key: [\n", "- invalid\n", "a.b.c: invalid\n", "key.child: collision\n"])
def test_invalid_latest_source_preserves_live_state_without_fallback(tmp_path, content):
    path = tmp_path / "settings.yaml"
    path.write_text("key: current\n")
    conf = Confease(path, __backup__=True, key="default")
    previous = conf._entries
    (tmp_path / "settings-20261006-143052.yaml.bkp").write_text("key: older\n")
    latest = tmp_path / "settings-20261007-143052.yaml.bkp"
    latest.write_text(content)
    with pytest.raises((ValueError, yaml.YAMLError)):
        conf.restore()
    assert path.read_text() == "key: current\n"
    assert conf._entries is previous
    assert len(list(tmp_path.glob("*.bkp"))) == 2
    assert list(tmp_path.glob(".*")) == []


def test_missing_source_or_target_path(tmp_path):
    path = tmp_path / "settings.yaml"
    conf = Confease(path, __backup__=True, key=1)
    for source in (None, tmp_path / "absent"):
        with pytest.raises(FileNotFoundError):
            conf.restore(source)
    assert not path.exists()
    assert list(tmp_path.iterdir()) == []
    source = tmp_path / "source"
    source.write_text("key: 1\n")
    runtime = Confease(__backup__=True, key=2)
    previous = runtime.get_item("key")
    with pytest.raises(FileNotFoundError, match="path"):
        runtime.restore(source)
    assert runtime.get_item("key") == previous


def test_repeated_restore_toggles_same_second(tmp_path, frozen_time):
    path = tmp_path / "settings.yaml"
    a, b = b"key: A # original\r\n", b"key: B\r\n"
    path.write_bytes(a)
    source = create_backup(path)
    path.write_bytes(b)
    conf = Confease(path, __backup__=True)
    for expected in (a, b, a, b):
        conf.restore()
        assert path.read_bytes() == expected
        assert conf.get("key") == Yaml.load(path)["key"]
    assert source.read_bytes() == a
    assert len(list(tmp_path.glob("*.bkp"))) == 5
    assert (tmp_path / "settings-20261007-143052-001.yaml.bkp").read_bytes() == b
    assert (tmp_path / "settings-20261007-143052-002.yaml.bkp").read_bytes() == a


@pytest.mark.parametrize("policy,override,count", [(False, None, 0), (False, True, 1), (True, False, 0), (True, None, 1)])
def test_restore_policy_overrides(tmp_path, policy, override, count):
    path = tmp_path / "settings.yaml"
    path.write_text("key: current\n")
    source = tmp_path / "historical"
    source.write_text("key: historical\n")
    conf = Confease(path, __backup__=policy)
    conf.restore(source, backup=override)
    assert len(list(tmp_path.glob("*.bkp"))) == count
    assert conf._backup is policy


@pytest.mark.parametrize("stage", ["copy", "validation", "backup", "replace"])
def test_restore_failures_preserve_file_and_entries(tmp_path, monkeypatch, stage):
    path = tmp_path / "settings.yaml"
    path.write_text("key: current\n")
    source = tmp_path / "historical"
    source.write_text("key: old\n")
    conf = Confease(path, __backup__=True)
    previous = conf._entries

    def fail(*args, **kwargs):
        if stage == "copy":
            args[1].write_text("partial")
        raise OSError(f"{stage} failed")

    if stage == "copy":
        monkeypatch.setattr("confease.model.shutil.copyfile", fail)
    elif stage == "validation":
        monkeypatch.setattr(conf, "_entries_for_load", fail)
    elif stage == "backup":
        monkeypatch.setattr("confease.backups.create_backup", fail)
    else:
        monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match=f"{stage} failed"):
        conf.restore(source)
    assert path.read_text() == "key: current\n"
    assert source.read_text() == "key: old\n"
    assert conf._entries is previous
    assert list(tmp_path.glob(".*")) == []
    snapshots = list(tmp_path.glob("*.bkp"))
    assert len(snapshots) == int(stage == "replace")
    if snapshots:
        assert snapshots[0].read_bytes() == path.read_bytes()
