"""Template init preserves explicit save control and reports recovery paths."""

import pytest

from confease import Json, Yaml
from confease.cli import main


@pytest.fixture
def fallback(monkeypatch):
    monkeypatch.setattr("confease.cli.TextEditor._open_preloaded", lambda self, path, template: False)


@pytest.mark.parametrize("save", ["abandon", "unchanged", "edited"])
def test_template_init_only_installs_saved_draft(tmp_path, monkeypatch, fallback, save):
    target = tmp_path / "nested" / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    initial = b'# Header\r\nkey: "original" # inline\r\n'
    edited = b"# Edited\r\nkey: saved # keep\r\n"
    template.write_bytes(initial)
    calls = []

    def open_draft(self, draft):
        calls.append(draft)
        assert not target.exists()
        assert draft.read_bytes() == initial
        if save == "unchanged":
            replacement = draft.with_suffix(".replacement")
            replacement.write_bytes(initial)
            replacement.replace(draft)
        elif save == "edited":
            draft.write_bytes(edited)

    monkeypatch.setattr("confease.cli.TextEditor.open", open_draft)
    assert main(["init", str(target), "--template", str(template)]) == 0
    assert len(calls) == 1
    assert template.read_bytes() == initial
    assert not calls[0].exists()
    assert target.exists() is (save != "abandon")
    if target.exists():
        assert target.read_bytes() == (initial if save == "unchanged" else edited)


@pytest.mark.parametrize("save", [False, True])
def test_template_init_uses_native_preloading_when_available(tmp_path, monkeypatch, save):
    target = tmp_path / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    template.write_text("key: template\n")
    calls = []

    def preload(self, path, source):
        assert path == target and source == template
        assert not path.exists()
        calls.append(path)
        if save:
            path.write_bytes(source.read_bytes())
        return True

    def unexpected_open(*args):
        pytest.fail("Native preload must not open a fallback draft")

    monkeypatch.setattr("confease.cli.TextEditor._open_preloaded", preload)
    monkeypatch.setattr("confease.cli.TextEditor.open", unexpected_open)
    assert main(["init", str(target), "--template", str(template)]) == 0
    assert calls == [target]
    assert target.exists() is save


@pytest.mark.parametrize("failure", ["invalid", "collision", "launch", "saved_launch", "interrupt"])
def test_template_init_reports_retained_work(tmp_path, monkeypatch, fallback, capsys, failure):
    target = tmp_path / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    template.write_text("key: template\n")
    drafts = []

    def open_draft(self, draft):
        drafts.append(draft)
        if failure == "launch":
            raise RuntimeError("launch failed")
        draft.write_text("key: [\n" if failure == "invalid" else "key: saved\n")
        if failure == "collision":
            target.write_text("key: concurrent\n")
        elif failure == "saved_launch":
            raise RuntimeError("editor failed after save")
        elif failure == "interrupt":
            raise KeyboardInterrupt

    monkeypatch.setattr("confease.cli.TextEditor.open", open_draft)
    assert main(["init", str(target), "--template", str(template)]) == (130 if failure == "interrupt" else 1)
    error = capsys.readouterr().err
    assert target.exists() is (failure == "collision")
    if failure == "collision":
        assert target.read_text() == "key: concurrent\n"
    if failure == "launch":
        assert not drafts[0].exists()
        assert "retained" not in error
    else:
        assert drafts[0].exists()
        assert "Saved editor draft retained at:" in error
        assert str(drafts[0]) in error


@pytest.mark.parametrize("problem", ["missing", "invalid", "existing"])
def test_template_init_rejects_bad_inputs_before_launch(tmp_path, monkeypatch, capsys, problem):
    target = tmp_path / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    if problem != "missing":
        template.write_text("key: [\n" if problem == "invalid" else "key: template\n")
    if problem == "existing":
        target.write_text("key: original\n")

    def unexpected_launch(*args):
        pytest.fail("Invalid inputs must fail before launch")

    monkeypatch.setattr("confease.cli.TextEditor._open_preloaded", unexpected_launch)
    assert main(["init", str(target), "--template", str(template)]) == 1
    assert capsys.readouterr().err
    assert target.exists() is (problem == "existing")
    if target.exists():
        assert target.read_text() == "key: original\n"


@pytest.mark.parametrize("args,parser,content", [
    ([], Yaml, b"key: 1\n"),
    (["--format", "json"], Json, b'{"key": 1}\n'),
])
def test_extensionless_template_init_uses_target_format(tmp_path, monkeypatch, fallback, args, parser, content):
    target = tmp_path / "settings"
    template = tmp_path / "seed.unrecognized"
    template.write_bytes(content)

    def save(self, draft):
        replacement = draft.with_name(draft.name + ".replacement")
        replacement.write_bytes(draft.read_bytes())
        replacement.replace(draft)

    monkeypatch.setattr("confease.cli.TextEditor.open", save)
    assert main(["init", str(target), "--template", str(template), *args]) == 0
    assert target.read_bytes() == content
    assert parser.load(target) == {"key": 1}


def test_template_paths_expand_user_home(tmp_path, monkeypatch, fallback):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "defaults.yaml").write_text("key: template\n")
    calls = []
    monkeypatch.setattr("confease.cli.TextEditor.open", lambda self, path: calls.append(path.read_bytes()))
    assert main(["init", "~/settings.yaml", "--template", "~/defaults.yaml"]) == 0
    assert calls == [b"key: template\n"]
    assert not (tmp_path / "settings.yaml").exists()


def test_template_and_items_are_mutually_exclusive(tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        main(["init", str(tmp_path / "settings.yaml"), "--template", "defaults.yaml", "-i", "key=1"])
    assert caught.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_init_help_describes_template_save_control(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["init", "--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    assert "--template PATH" in help_text
    assert "only on save" in help_text
    assert "best-effort" in help_text
