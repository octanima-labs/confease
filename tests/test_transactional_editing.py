"""Library integration: explicit text outcomes, atomic persistence, and backups."""

from importlib.util import find_spec
from pathlib import Path

import pytest
import yaml
from edital import EditResult, TuiEditor

from confease import Confease


def test_editor_api_is_owned_only_by_edital():
    import edital

    import confease

    assert not any(hasattr(confease, name) for name in ("EditResult", "TuiEditor", "Validator", "edit_text"))
    assert find_spec("confease.tui_editor") is None
    assert all(hasattr(edital, name) for name in ("EditResult", "TuiEditor", "Validator", "edit_text"))


@pytest.mark.parametrize("existing", [False, True])
def test_cancel_keeps_destination_and_unsaved_memory(tmp_path, monkeypatch, existing):
    path = tmp_path / "settings.yaml"
    if existing:
        path.write_bytes(b"key: old\r\n")
    conf = Confease(path, backup=True, items={"fallback": 1})
    conf.set("key", "unsaved")
    previous = conf._entries
    assert isinstance(conf.editor, TuiEditor)

    def edit(text, *, title, validator):
        assert text == ("key: old\r\n" if existing else "")
        assert title == str(path)
        assert validator("key: [\n") is not None
        assert conf._entries is previous
        return EditResult("cancelled")

    monkeypatch.setattr(conf.editor, "edit", edit)
    assert conf.edit_file() is conf
    assert conf._entries is previous
    assert conf.get("key") == "unsaved"
    assert path.exists() is existing
    if existing:
        assert path.read_bytes() == b"key: old\r\n"
    assert not list(tmp_path.glob("*.bkp"))
    assert not list(tmp_path.glob(".*"))


@pytest.mark.parametrize("backup,count", [(None, 1), (False, 0), (True, 1)])
def test_accept_validates_before_backup_and_preserves_exact_text(tmp_path, monkeypatch, backup, count):
    path = tmp_path / "settings.yaml"
    original = b"# original\r\nkey: old\r\n"
    accepted = '# edited\r\nkey: "new" # inline'
    path.write_bytes(original)
    conf = Confease(path, backup=True, items={"fallback": 1})
    previous = conf._entries

    def edit(text, *, title, validator):
        assert text.encode() == original
        assert validator("key: [\n") is not None
        assert validator("a.b.c: invalid\n") is not None
        assert validator("key: new\n") is None
        assert conf._entries is previous
        assert path.read_bytes() == original
        assert not list(tmp_path.glob("*.bkp"))
        return EditResult("accepted", accepted)

    monkeypatch.setattr(conf.editor, "edit", edit)
    conf.edit_file(template=tmp_path / "ignored-missing-template", backup=backup)
    assert path.read_bytes() == accepted.encode()
    assert conf.get("key") == "new"
    assert conf.get("fallback") == 1
    backups = list(tmp_path.glob("*.bkp"))
    assert len(backups) == count
    if count:
        assert backups[0].read_bytes() == original
    assert not list(tmp_path.glob(".*"))


@pytest.mark.parametrize("accept", [False, True])
def test_template_acceptance_is_explicit_and_keeps_defaults(tmp_path, monkeypatch, accept):
    template = tmp_path / "seed.yaml"
    template.write_bytes(b"# seed\r\nkey: seed\r\n")
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("key: default\nother: retained\n")
    path = tmp_path / "nested" / "settings.yaml"
    conf = Confease(path, template=defaults, backup=True)
    conf.set("key", "unsaved")
    previous = conf._entries
    previous_defaults = conf._defaults

    def edit(text, **kwargs):
        assert text.encode() == template.read_bytes()
        assert not path.exists()
        return EditResult("accepted", text) if accept else EditResult("cancelled")

    monkeypatch.setattr(conf.editor, "edit", edit)
    conf.edit_file(template=template)
    assert path.exists() is accept
    assert conf._defaults is previous_defaults
    assert conf._template == defaults
    if accept:
        assert path.read_bytes() == template.read_bytes()
        assert conf.get("key") == "seed"
    else:
        assert conf._entries is previous
        assert conf.get("key") == "unsaved"
    assert conf.get("other") == "retained"
    assert not list(tmp_path.rglob("*.bkp"))


@pytest.mark.parametrize("problem", ["missing", "invalid", "default_collision"])
def test_bad_template_prevents_session(tmp_path, monkeypatch, problem):
    template = tmp_path / "template.yaml"
    if problem != "missing":
        template.write_text("key: [\n" if problem == "invalid" else "key.child: 1\n")
    conf = Confease(tmp_path / "settings.yaml", items={"key": "default"})
    monkeypatch.setattr(conf.editor, "edit", lambda *args, **kwargs: pytest.fail("must not launch"))
    with pytest.raises((FileNotFoundError, ValueError, yaml.YAMLError)):
        conf.edit_file(template=template)
    assert not conf._path.exists()


def test_validator_checks_default_collisions_without_mutation(tmp_path, monkeypatch):
    conf = Confease(tmp_path / "settings.yaml", items={"key": "default"})
    previous = conf._entries

    def edit(text, *, title, validator):
        assert validator("key.child: 1\n") is not None
        assert conf._entries is previous
        return EditResult("cancelled")

    monkeypatch.setattr(conf.editor, "edit", edit)
    conf.edit_file()
    assert conf._entries is previous


@pytest.mark.parametrize("failure", ["backup", "install", "concurrent"])
def test_install_failure_retains_accepted_text_and_memory(tmp_path, monkeypatch, failure):
    path = tmp_path / "settings.yaml"
    if failure != "concurrent":
        path.write_bytes(b"key: old\r\n")
    conf = Confease(path, backup=True)
    previous = conf._entries

    def edit(text, **kwargs):
        if failure == "concurrent":
            path.write_text("key: concurrent\n")
        return EditResult("accepted", "# accepted\r\nkey: new\r\n")

    monkeypatch.setattr(conf.editor, "edit", edit)
    if failure == "backup":
        def fail(target):
            raise OSError("backup failed")
        monkeypatch.setattr("confease.backups.create_backup", fail)
    elif failure == "install":
        def fail(source, target):
            raise OSError("replace failed")
        monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError) as caught:
        conf.edit_file()
    assert conf._entries is previous
    assert path.read_bytes() == (b"key: concurrent\n" if failure == "concurrent" else b"key: old\r\n")
    drafts = list(tmp_path.glob(".*"))
    assert len(drafts) == 1
    assert drafts[0].read_bytes() == b"# accepted\r\nkey: new\r\n"
    assert str(drafts[0]) in " ".join(caught.value.__notes__)
    assert len(list(tmp_path.glob("*.bkp"))) == int(failure == "install")


def test_accept_empty_buffer_creates_empty_yaml(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    conf = Confease(path, items={"fallback": 1})
    monkeypatch.setattr(conf.editor, "edit", lambda text, **kwargs: EditResult("accepted", ""))
    conf.edit_file()
    assert path.read_bytes() == b""
    assert conf.get("fallback") == 1


def test_directory_failure_recovers_accepted_text_outside_destination(tmp_path, monkeypatch):
    path = tmp_path / "unavailable" / "settings.yaml"
    conf = Confease(path)
    previous = conf._entries
    monkeypatch.setattr(conf.editor, "edit", lambda text, **kwargs: EditResult("accepted", "key: saved\n"))
    original_mkdir = Path.mkdir

    def fail(target, *args, **kwargs):
        if target == path.parent:
            raise PermissionError("directory unavailable")
        return original_mkdir(target, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(PermissionError) as caught:
        conf.edit_file()
    assert not path.exists()
    assert conf._entries is previous
    recovery = Path(caught.value.__notes__[0].split("retained at: ", 1)[1])
    try:
        assert recovery.parent != path.parent
        assert recovery.read_text() == "key: saved\n"
    finally:
        recovery.unlink()
