import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from confease import Confease, TextEditor


class DraftEditor:
    def __init__(self, action):
        self.action = action
        self.path = None
        self.initial = None

    def open(self, path):
        self.path = Path(path)
        self.initial = self.path.read_bytes()
        self.action(self.path)


@pytest.mark.parametrize("save", ["abandon", "unchanged", "edited"])
def test_template_draft_requires_save_and_preserves_exact_bytes(tmp_path, save):
    target = tmp_path / "nested" / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    initial = b'# Header\r\nKEY: "template" # inline\r\n'
    template.write_bytes(initial)
    conf = Confease(target, backup=True, items={"DEFAULT": "memory"})
    conf.set("KEY", "unsaved")
    previous = conf._entries

    def edit(draft):
        assert not target.exists()
        assert draft.suffix == target.suffix
        if save == "unchanged":
            # Atomic replacement is also how many real editors save files.
            replacement = draft.with_suffix(".replacement")
            replacement.write_bytes(initial)
            replacement.replace(draft)
        elif save == "edited":
            draft.write_bytes(b"# Edited\r\nKEY: edited # keep\r\n")

    editor = DraftEditor(edit)
    conf.editor = editor
    assert conf.edit_file(template=template) is conf
    assert editor.initial == initial
    assert template.read_bytes() == initial
    assert not editor.path.exists()
    assert not list(target.parent.glob("*.bkp"))
    assert conf._template is None
    if save == "abandon":
        assert not target.exists()
        assert conf._entries is previous
    else:
        assert target.read_bytes() == (initial if save == "unchanged"
                                       else b"# Edited\r\nKEY: edited # keep\r\n")
        assert conf.get("KEY") == ("template" if save == "unchanged" else "edited")
        assert conf.get("DEFAULT") == "memory"


@pytest.mark.parametrize("failure", ["invalid", "collision", "launch", "saved_launch", "install"])
def test_failed_template_edit_preserves_target_memory_and_saved_work(tmp_path, monkeypatch, failure):
    target = tmp_path / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    template.write_text("KEY: template\n")
    conf = Confease(target, items={"KEY": "memory"})
    previous = conf._entries

    def edit(draft):
        if failure == "launch":
            raise RuntimeError("launch failed")
        draft.write_text("KEY: [\n" if failure == "invalid" else "KEY: saved\n")
        if failure == "collision":
            target.write_text("KEY: concurrent\n")
        if failure == "saved_launch":
            raise RuntimeError("editor failed after saving")

    if failure == "install":
        def fail_install(*args, **kwargs):
            raise OSError("installation failed")
        monkeypatch.setattr("confease.model.install_draft", fail_install)
    editor = DraftEditor(edit)
    conf.editor = editor
    with pytest.raises((yaml.YAMLError, OSError, RuntimeError)) as caught:
        conf.edit_file(template=template)
    assert conf._entries is previous
    assert target.exists() is (failure == "collision")
    if failure == "collision":
        assert target.read_text() == "KEY: concurrent\n"
    if failure == "launch":
        assert not editor.path.exists()
    else:
        assert editor.path.exists()
        assert str(editor.path) in " ".join(caught.value.__notes__)


@pytest.mark.parametrize("content", [None, "KEY: [\n", "KEY: scalar\nKEY.child: collision\n"])
def test_template_errors_prevent_launch(tmp_path, content):
    template = tmp_path / "template.yaml"
    if content is not None:
        template.write_text(content)
    conf = Confease(tmp_path / "settings.yaml")
    conf.editor = DraftEditor(lambda path: pytest.fail("Unexpected launch"))
    with pytest.raises((FileNotFoundError, ValueError, yaml.YAMLError)):
        conf.edit_file(template=template)
    assert conf.editor.path is None


def test_existing_target_ignores_edit_template(tmp_path):
    target = tmp_path / "settings.yaml"
    target.write_text("KEY: original\n")
    conf = Confease(target)
    editor = DraftEditor(lambda path: None)
    conf.editor = editor
    conf.edit_file(template=tmp_path / "nonexistent.yaml")
    assert editor.path == target
    assert editor.initial == b"KEY: original\n"


def test_unchanged_in_place_save_detected_without_content_difference(tmp_path):
    template = tmp_path / "defaults.yaml"
    template.write_text("KEY: template\n")
    target = tmp_path / "settings.yaml"
    conf = Confease(target)

    def save(draft):
        before = draft.stat()
        draft.write_bytes(draft.read_bytes())
        # Avoid reliance on timestamp resolution or scheduler timing in this test.
        os.utime(draft, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))

    conf.editor = DraftEditor(save)
    conf.edit_file(template=template)
    assert target.read_bytes() == template.read_bytes()


def test_edit_only_template_does_not_replace_configured_defaults(tmp_path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("KEY: default\nOTHER: retained\n")
    seed = tmp_path / "seed.yaml"
    seed.write_text("KEY: seed\n")
    target = tmp_path / "settings.yaml"
    conf = Confease(target, template=defaults)
    previous_defaults = conf._defaults
    conf.editor = DraftEditor(lambda draft: draft.write_text("KEY: saved\n"))
    conf.edit_file(template=seed)
    assert conf._template == defaults
    assert conf._defaults is previous_defaults
    assert conf.get("KEY") == "saved"
    assert conf.get("OTHER") == "retained"


def test_deleted_draft_is_abandoned(tmp_path):
    template = tmp_path / "defaults.yaml"
    template.write_text("KEY: template\n")
    target = tmp_path / "settings.yaml"
    conf = Confease(target)
    conf.editor = DraftEditor(lambda draft: draft.unlink())
    conf.edit_file(template=template)
    assert not target.exists()


@pytest.mark.parametrize("command", ["nano -w", "vi", "code --reuse-window", "custom-editor"])
def test_non_native_commands_automatically_open_seeded_draft(tmp_path, monkeypatch, command):
    target = tmp_path / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    template.write_text("KEY: template\n")
    conf = Confease(target)
    conf.editor = TextEditor(command)
    monkeypatch.setattr("confease.editors.shutil.which", lambda name: name)
    calls = []

    def run(args, *, check):
        calls.append(args)
        draft = Path(args[-1])
        assert draft != target
        assert draft.read_bytes() == template.read_bytes()
        assert not target.exists()
        draft.write_text("KEY: saved\n")

    monkeypatch.setattr("confease.editors.subprocess.run", run)
    conf.edit_file(template=template)
    assert len(calls) == 1
    if command.startswith("code"):
        assert "--wait" in calls[0]
    assert conf.get("KEY") == "saved"


@pytest.mark.parametrize("executable", ["vim", "nvim"])
@pytest.mark.parametrize("save", [False, True])
def test_real_native_editor_has_modified_target_buffer(tmp_path, monkeypatch, executable, save):
    if shutil.which(executable) is None:
        pytest.skip(f"{executable} is not installed")
    target = tmp_path / "target ' | % settings.yaml"
    template = tmp_path / "template ' | % defaults.yaml"
    initial = b'# Header\r\nKEY: "template" # inline\r\n'
    template.write_bytes(initial)
    conf = Confease(target, items={"KEY": "memory"})
    conf.editor = TextEditor(f"{executable} -u NONE -n -es")
    original_run = subprocess.run

    def run(args, *, check):
        assert not target.exists()
        assert args[-1] == str(target)
        # Verify preload marked the target buffer modified before saving/quitting.
        finish = "if !&modified | cquit | endif | " + ("wq" if save else "qa!")
        original_run([*args[:-2], "-c", finish, *args[-2:]], check=check,
                     stdin=subprocess.DEVNULL, capture_output=True, timeout=10)

    monkeypatch.setattr("confease.editors.subprocess.run", run)
    assert conf.edit_file(template=template) is conf
    assert template.read_bytes() == initial
    assert target.exists() is save
    if save:
        assert target.read_bytes() == initial
        assert conf.get("KEY") == "template"
    else:
        assert conf.get("KEY") == "memory"
    assert set(tmp_path.iterdir()) == ({template, target} if save else {template})
