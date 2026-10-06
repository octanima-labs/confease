import subprocess
from pathlib import Path

import pytest
import yaml

from confease import Confease, TextEditor


class WritingEditor:
    def __init__(self, content: str | None):
        self.content = content
        self.initial_content: str | None = None
        self.path: Path | None = None

    def open(self, path: str | Path) -> str:
        edit_path = Path(path)
        self.path = edit_path
        self.initial_content = edit_path.read_text() if edit_path.exists() else None
        if self.content is not None:
            edit_path.write_text(self.content)
        return str(edit_path)


def test_text_editor_accepts_custom_command_strings(monkeypatch):
    monkeypatch.setattr("confease.editors.shutil.which", lambda command: f"/usr/bin/{command}")

    assert TextEditor("nano -w")._editor_command() == ["nano", "-w"]


def test_text_editor_adds_known_visual_wait_flags(monkeypatch):
    monkeypatch.setattr("confease.editors.shutil.which", lambda command: f"/usr/bin/{command}")

    assert TextEditor("code --reuse-window")._editor_command() == [
        "code",
        "--wait",
        "--reuse-window",
    ]
    assert TextEditor("code --wait")._editor_command() == ["code", "--wait"]


@pytest.mark.parametrize("content", ["- invalid\n", "KEY: [\n", "a.b.c: invalid\n", "a: scalar\na.b: collision\n"])
def test_edit_file_keeps_invalid_save_and_previous_memory(tmp_path, content):
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: original\n")
    conf = Confease(path)
    conf.editor = WritingEditor(content)

    with pytest.raises((ValueError, yaml.YAMLError)):
        conf.edit_file()

    assert path.read_text() == content
    assert conf.get("KEY") == "original"


def test_edit_file_persists_valid_user_config_edits(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, DEFAULT="default")
    conf.set("USER", "old")
    content = "# Saved by user\nUSER: new # keep this\n"
    conf.editor = WritingEditor(content)

    conf.edit_file()

    assert yaml.safe_load(path.read_text()) == {"USER": "new"}
    assert path.read_text() == content
    assert conf.get("DEFAULT") == "default"
    assert conf.get("USER") == "new"


@pytest.mark.parametrize("save", [False, True])
def test_edit_file_missing_target_requires_manual_save(tmp_path, save):
    path = tmp_path / "nested" / "conf.yaml"
    editor = WritingEditor("KEY: edited\n" if save else None)
    conf = Confease(path, KEY="default")
    conf.editor = editor

    assert conf.edit_file() is conf

    assert editor.initial_content is None
    assert editor.path == path
    assert path.exists() is save
    assert conf.get("KEY") == ("edited" if save else "default")


def test_edit_file_opens_exact_commented_target_without_rewriting(tmp_path):
    path = tmp_path / "conf.yaml"
    content = b'# Header\r\nKEY: "original" # inline\r\n'
    path.write_bytes(content)
    conf = Confease(path)
    editor = WritingEditor(None)
    conf.editor = editor
    conf.edit_file()
    assert editor.path == path
    assert path.read_bytes() == content
    assert conf.get("KEY") == "original"


def test_editor_launch_does_not_create_missing_path(tmp_path, monkeypatch):
    path = tmp_path / "missing.yaml"
    monkeypatch.setattr("confease.editors.shutil.which", lambda command: command)

    def run(command, *, check):
        assert command == ["nano", "-w", str(path)]
        assert check
        assert not path.exists()

    monkeypatch.setattr("confease.editors.subprocess.run", run)
    assert TextEditor("nano -w").open(path) == str(path)
    assert not path.exists()


def test_edit_file_requires_configured_path():
    with pytest.raises(FileNotFoundError, match="path"):
        Confease().edit_file()


@pytest.mark.parametrize("error", [OSError("launch failed"), subprocess.CalledProcessError(1, ["nano"])])
def test_editor_failure_does_not_create_file(tmp_path, monkeypatch, error):
    path = tmp_path / "missing.yaml"
    monkeypatch.setattr("confease.editors.shutil.which", lambda command: command)

    def fail_run(*args, **kwargs):
        raise error

    monkeypatch.setattr("confease.editors.subprocess.run", fail_run)
    with pytest.raises(Exception, match="(could not open text editor|text editor process failed)"):
        TextEditor("nano").open(path)
    assert not path.exists()


def test_edit_file_rejects_removed_user_only_parameter(tmp_path):
    with pytest.raises(TypeError, match="user_only"):
        Confease(tmp_path / "conf.yaml").edit_file(user_only=False)
