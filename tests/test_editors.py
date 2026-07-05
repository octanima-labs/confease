from pathlib import Path

import pytest
import yaml

from confease import Confease, TextEditor


class WritingEditor:
    def __init__(self, content: str):
        self.content = content
        self.initial_content: str | None = None

    def open(self, path: str | Path) -> str:
        edit_path = Path(path)
        self.initial_content = edit_path.read_text()
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


def test_text_edit_validates_draft_before_replacing_file(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: original\n")
    conf = Confease(path)
    conf.editor = WritingEditor("- invalid\n")

    with pytest.raises(ValueError, match="key-value mapping"):
        conf.text_edit()

    assert path.read_text() == "KEY: original\n"
    assert conf.get("KEY") == "original"


def test_text_edit_persists_valid_user_config_edits(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, DEFAULT="default")
    conf.set("USER", "old")
    conf.editor = WritingEditor("USER: new\n")

    conf.text_edit()

    assert yaml.safe_load(path.read_text()) == {"USER": "new"}
    assert conf.get("DEFAULT") == "default"
    assert conf.get("USER") == "new"


def test_text_edit_can_create_missing_file_from_effective_config(tmp_path):
    path = tmp_path / "conf.yaml"
    editor = WritingEditor("KEY: edited\n")
    conf = Confease(path, KEY="default")
    conf.editor = editor

    conf.text_edit(user_only=False)

    assert yaml.safe_load(editor.initial_content) == {"KEY": "default"}
    assert yaml.safe_load(path.read_text()) == {"KEY": "edited"}
    assert conf.get("KEY") == "edited"
