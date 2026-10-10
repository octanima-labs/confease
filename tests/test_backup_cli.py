"""CLI snapshot and recovery tests avoid launching a real editor."""

from datetime import datetime

import pytest
from edital import EditResult

from confease import Json, Yaml
from confease.cli import main


@pytest.fixture
def frozen_time(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 7, 14, 30, 52)

    monkeypatch.setattr("confease.backups.datetime", Clock)


@pytest.fixture
def no_editor(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Scripted edit/restore must not launch an editor")

    monkeypatch.setattr("confease.cli.TuiEditor.edit", unexpected)


@pytest.mark.parametrize("flag", ["-b", "--backup"])
@pytest.mark.parametrize("explicit", [False, True])
def test_scripted_batch_snapshot_once(tmp_path, flag, explicit, no_editor):
    path = tmp_path / "settings.yaml"
    original = b"# header\r\nkey: old # inline\r\nremove: null\r\n"
    path.write_bytes(original)
    args = ["edit"] if explicit else []
    assert main([*args, str(path), flag, "-u", "key=new", "-u", "other=3", "-d", "remove"]) == 0
    backups = list(tmp_path.glob("*.bkp"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert Yaml.load(path) == {"key": "new", "other": 3}


def test_interactive_repair_snapshot_only_at_acceptance(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    original = b"key: [\r\n"
    repaired = b'# retained\r\nkey: "fixed" # inline\r\n'
    path.write_bytes(original)
    calls = []

    def edit(self, text, *, title, validator):
        assert text.encode() == original
        assert path.read_bytes() == original
        assert list(tmp_path.glob("*.bkp")) == []
        calls.append(text)
        assert validator("key: [\n") is not None
        assert list(tmp_path.glob("*.bkp")) == []
        assert validator(repaired.decode()) is None
        return EditResult("accepted", repaired.decode())

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main([str(path), "--backup"]) == 0
    assert len(calls) == 1
    assert path.read_bytes() == repaired
    assert next(tmp_path.glob("*.bkp")).read_bytes() == original
    assert list(tmp_path.glob(".*")) == []


def test_cancelled_protected_edit_has_no_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    path.write_text("key: old\n")

    def cancel(self, text, **kwargs):
        return EditResult("cancelled")

    monkeypatch.setattr("confease.cli.TuiEditor.edit", cancel)
    assert main([str(path), "-b"]) == 130
    assert path.read_text() == "key: old\n"
    assert list(tmp_path.glob("*.bkp")) == []
    assert list(tmp_path.glob(".*")) == []


@pytest.mark.parametrize("operation", ["scripted", "interactive", "restore"])
def test_cli_backup_failure_preserves_target(tmp_path, monkeypatch, capsys, operation):
    path = tmp_path / "settings.yaml"
    path.write_text("key: old\n")

    def fail(target):
        raise OSError("snapshot failed")

    monkeypatch.setattr("confease.backups.create_backup", fail)
    if operation == "scripted":
        args = [str(path), "-u", "key=new", "-b"]
    elif operation == "interactive":
        monkeypatch.setattr("confease.cli.TuiEditor.edit", lambda self, text, **kwargs: EditResult("accepted", "key: new\n"))
        args = [str(path), "-b"]
    else:
        source = tmp_path / "historical"
        source.write_text("key: new\n")
        args = ["restore", str(path), "--from", str(source), "-b"]
    assert main(args) == 1
    diagnostic = capsys.readouterr().err
    assert "snapshot failed" in diagnostic
    assert path.read_text() == "key: old\n"
    if operation == "interactive":
        drafts = list(tmp_path.glob(".*"))
        assert len(drafts) == 1
        assert drafts[0].read_text() == "key: new\n"
        assert str(drafts[0]) in diagnostic
    else:
        assert list(tmp_path.glob(".*")) == []


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("flag", ["-b", "--backup"])
def test_restore_missing_or_malformed_destination(tmp_path, existing, flag, no_editor):
    path = tmp_path / "settings.yaml"
    original = b"key: [\r\n"
    if existing:
        path.write_bytes(original)
    source = tmp_path / "settings-20261006-143052.yaml.bkp"
    restored = b"key: restored # inline\r\n"
    source.write_bytes(restored)
    assert main(["restore", str(path), flag]) == 0
    assert path.read_bytes() == restored == source.read_bytes()
    others = [p for p in tmp_path.glob("*.bkp") if p != source]
    assert len(others) == int(existing)
    if existing:
        assert others[0].read_bytes() == original


def test_explicit_source_extensionless_format(tmp_path, no_editor):
    path = tmp_path / "settings"
    source = tmp_path / "arbitrary.snapshot"
    source.write_bytes(b'{ "key": 3 }\r\n')
    assert main(["restore", str(path), "--from", str(source), "-f", "json"]) == 0
    assert path.read_bytes() == source.read_bytes()
    assert Json.load(path) == {"key": 3}
    assert list(tmp_path.glob("*.bkp")) == []
    assert not path.with_suffix(".json").exists()


def test_cli_restore_toggle_same_second(tmp_path, frozen_time, no_editor):
    path = tmp_path / "settings.yaml"
    source = tmp_path / "settings-20261007-143052.yaml.bkp"
    source.write_bytes(b"key: A\r\n")
    path.write_bytes(b"key: B\r\n")
    assert main(["restore", str(path), "-b"]) == 0
    assert path.read_bytes() == b"key: A\r\n"
    assert main(["restore", str(path), "-b"]) == 0
    assert path.read_bytes() == b"key: B\r\n"
    assert len(list(tmp_path.glob("*.bkp"))) == 3


@pytest.mark.parametrize("case", ["no_backups", "missing_source", "invalid_source", "unknown_format"])
def test_restore_errors_are_nonzero_and_preserve_destination(tmp_path, capsys, no_editor, case):
    path = tmp_path / ("settings" if case == "unknown_format" else "settings.yaml")
    path.write_text("key: current\n")
    args = ["restore", str(path), "-b"]
    if case in ("missing_source", "invalid_source"):
        source = tmp_path / "historical"
        if case == "invalid_source":
            source.write_text("key: [\n")
        args += ["--from", str(source)]
    assert main(args) == 1
    assert "Error:" in capsys.readouterr().err
    assert path.read_text() == "key: current\n"
    assert list(tmp_path.glob("*.bkp")) == []


def test_command_named_path_uses_explicit_relative_shorthand(tmp_path, monkeypatch, no_editor):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "restore"
    path.write_text("key: old\n")
    assert main(["./restore", "-f", "yaml", "-u", "key=new", "-b"]) == 0
    assert Yaml.load(path) == {"key": "new"}
    assert len(list(tmp_path.glob("*.bkp"))) == 1
