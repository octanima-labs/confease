"""Fresh deferred instances recover destinations through public APIs."""

from pathlib import Path

import pytest
import yaml
from edital import EditResult

from confease import DEF, USR, Confease, Confitem


def fail(*args, **kwargs):
    raise OSError("installation failed")


@pytest.mark.parametrize("accept", [False, True])
def test_deferred_edit_repairs_or_cancels_exact_malformed_text(tmp_path, monkeypatch, accept):
    path = tmp_path / "settings.yaml"
    original = b"# broken\r\nkey: [\r\n"
    accepted = '# repaired\r\nkey: "new" # inline\r\n'
    path.write_bytes(original)
    conf = Confease(path, autoload=False, backup=True, items={"fallback": 3})

    def edit(text, *, title, validator):
        assert text == original.decode()
        assert title == str(path)
        assert conf._entries is None
        assert list(tmp_path.glob("*.bkp")) == []
        assert validator(text) is not None
        assert validator(accepted) is None
        return EditResult("accepted", accepted) if accept else EditResult("cancelled")

    monkeypatch.setattr(conf.editor, "edit", edit)
    assert conf.edit_file() is conf
    snapshots = list(tmp_path.glob("*.bkp"))
    if accept:
        assert path.read_bytes() == accepted.encode()
        assert len(snapshots) == 1
        assert snapshots[0].read_bytes() == original
        path.write_text("key: changed-outside\n")
        assert conf.get_item("key") == Confitem("key", "new", USR)
        assert conf.get_item("fallback") == Confitem("fallback", 3, DEF)
    else:
        assert path.read_bytes() == original
        assert conf._entries is None
        assert snapshots == []
        with pytest.raises(yaml.YAMLError):
            conf["key"]


@pytest.mark.parametrize("accept", [False, True])
def test_deferred_missing_edit_template_acceptance_and_cancellation(tmp_path, monkeypatch, accept):
    path = tmp_path / "absent" / "settings.yaml"
    template = tmp_path / "edit-template.yaml"
    initial = '# template\r\nkey: "template"\r\n'
    template.write_bytes(initial.encode())
    conf = Confease(path, autoload=False, items={"fallback": 1})
    defaults = conf._defaults

    def edit(text, **kwargs):
        assert text == initial
        assert not path.parent.exists()
        return EditResult("accepted", text) if accept else EditResult("cancelled")

    monkeypatch.setattr(conf.editor, "edit", edit)
    conf.edit_file(template=template)
    assert conf._defaults is defaults
    if accept:
        assert path.read_bytes() == initial.encode()
        assert conf.get_item("key") == Confitem("key", "template", USR)
        assert conf["fallback"] == 1
    else:
        assert conf._entries is None
        assert not path.parent.exists()


@pytest.mark.parametrize("stage", ["backup", "replace"])
def test_deferred_edit_failure_retains_recovery_text_and_deferred_state(tmp_path, monkeypatch, stage):
    path = tmp_path / "settings.yaml"
    original = b"key: [\n"
    path.write_bytes(original)
    conf = Confease(path, autoload=False, backup=True)
    accepted = "# accepted\r\nkey: repaired\r\n"
    monkeypatch.setattr(conf.editor, "edit", lambda *args, **kwargs: EditResult("accepted", accepted))
    if stage == "backup":
        monkeypatch.setattr("confease.backups.create_backup", fail)
    else:
        monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError) as caught:
        conf.edit_file()
    assert conf._entries is None
    assert path.read_bytes() == original
    recovery = Path(caught.value.__notes__[0].split("retained at: ", 1)[1])
    assert recovery.read_bytes() == accepted.encode()
    assert len(list(tmp_path.glob("*.bkp"))) == int(stage == "replace")


@pytest.mark.parametrize("backup", [False, True])
def test_deferred_template_reset_over_malformed_destination(tmp_path, backup):
    path = tmp_path / "settings.yaml"
    original = b"key: [\r\n"
    path.write_bytes(original)
    template = tmp_path / "defaults.yaml"
    restored = b'# defaults\r\nkey: "default" # inline\r\n'
    template.write_bytes(restored)
    conf = Confease(path, template=template, autoload=False)
    conf.reset(backup=backup)
    assert path.read_bytes() == restored
    snapshots = list(tmp_path.glob("*.bkp"))
    assert len(snapshots) == int(backup)
    if snapshots:
        assert snapshots[0].read_bytes() == original
    path.write_text("key: changed-outside\n")
    assert conf.get_item("key") == Confitem("key", "default", USR)


@pytest.mark.parametrize("stage", ["invalid", "copy", "backup", "replace"])
def test_deferred_reset_failure_preserves_file_defaults_and_state(tmp_path, monkeypatch, stage):
    path = tmp_path / "settings.yaml"
    original = b"key: [\n"
    path.write_bytes(original)
    template = tmp_path / "defaults.yaml"
    template.write_text("key: default\n")
    conf = Confease(path, template=template, autoload=False, backup=True)
    defaults = conf._defaults
    if stage == "invalid":
        template.write_text("key: [\n")
    elif stage == "copy":
        monkeypatch.setattr("confease.model.shutil.copyfile", fail)
    elif stage == "backup":
        monkeypatch.setattr("confease.backups.create_backup", fail)
    else:
        monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises((OSError, yaml.YAMLError)):
        conf.reset()
    assert path.read_bytes() == original
    assert conf._entries is None
    assert conf._defaults is defaults
    assert list(tmp_path.glob(".*")) == []
    assert len(list(tmp_path.glob("*.bkp"))) == int(stage == "replace")


def test_deferred_memory_reset_bypasses_malformed_destination(tmp_path):
    path = tmp_path / "settings.yaml"
    original = b"key: [\n"
    path.write_bytes(original)
    conf = Confease(path, autoload=False, backup=True, items={"key": "default"})
    conf.reset()
    assert conf.get_item("key") == Confitem("key", "default", DEF)
    assert path.read_bytes() == original
    assert list(tmp_path.glob("*.bkp")) == []


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_deferred_restore_retains_defaults_source_and_initialized_state(tmp_path, explicit, existing):
    path = tmp_path / "settings.yaml"
    original = b"key: [\r\n"
    if existing:
        path.write_bytes(original)
    source = tmp_path / ("arbitrary.snapshot" if explicit else "settings-20261007-143052.yaml.bkp")
    restored = b'# backup\r\nkey: "restored"\r\n'
    source.write_bytes(restored)
    conf = Confease(path, autoload=False, backup=True, items={"fallback": 3})
    defaults = conf._defaults
    conf.restore(source if explicit else None)
    assert conf._defaults is defaults
    assert source.read_bytes() == path.read_bytes() == restored
    snapshots = [p for p in tmp_path.glob("*.bkp") if p != source]
    assert len(snapshots) == int(existing)
    if snapshots:
        assert snapshots[0].read_bytes() == original
    path.write_text("key: changed-outside\n")
    assert conf.get_item("key") == Confitem("key", "restored", USR)
    assert conf.get_item("fallback") == Confitem("fallback", 3, DEF)


@pytest.mark.parametrize("stage", ["invalid", "collision", "missing", "copy", "backup", "replace"])
def test_deferred_restore_failure_preserves_destination_and_state(tmp_path, monkeypatch, stage):
    path = tmp_path / "settings.yaml"
    original = b"key: [\n"
    path.write_bytes(original)
    source = tmp_path / "arbitrary.snapshot"
    if stage != "missing":
        source.write_text("key: [\n" if stage == "invalid" else
                          "key.child: 1\n" if stage == "collision" else "key: restored\n")
    conf = Confease(path, autoload=False, backup=True, items={"key": "default"})
    if stage == "copy":
        monkeypatch.setattr("confease.model.shutil.copyfile", fail)
    elif stage == "backup":
        monkeypatch.setattr("confease.backups.create_backup", fail)
    elif stage == "replace":
        monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises((OSError, yaml.YAMLError, ValueError)):
        conf.restore(source)
    assert path.read_bytes() == original
    assert conf._entries is None
    assert conf._defaults == [Confitem("key", "default", DEF)]
    assert list(tmp_path.glob(".*")) == []
    assert len(list(tmp_path.glob("*.bkp"))) == int(stage == "replace")
