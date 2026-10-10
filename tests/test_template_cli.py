"""Template initialization uses explicit transactional text outcomes."""

import pytest
from edital import EditResult

from confease import Json, Yaml
from confease.cli import main


@pytest.mark.parametrize("save", ["abandon", "unchanged", "edited"])
def test_template_init_only_installs_accepted_text(tmp_path, monkeypatch, save):
    target = tmp_path / "nested" / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    initial = b'# Header\r\nkey: "original" # inline\r\n'
    edited = b"# Edited\r\nkey: saved # keep\r\n"
    template.write_bytes(initial)
    calls = []

    def edit(self, text, *, title, validator):
        calls.append(text)
        assert not target.exists()
        assert text.encode() == initial
        if save == "abandon":
            return EditResult("cancelled")
        accepted = text if save == "unchanged" else edited.decode()
        assert validator(accepted) is None
        return EditResult("accepted", accepted)

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main(["init", str(target), "--template", str(template)]) == (130 if save == "abandon" else 0)
    assert len(calls) == 1
    assert template.read_bytes() == initial
    assert target.exists() is (save != "abandon")
    if target.exists():
        assert target.read_bytes() == (initial if save == "unchanged" else edited)
    assert not list(tmp_path.rglob(".*"))


def test_template_invalid_candidate_is_corrected_in_one_session(tmp_path, monkeypatch):
    target = tmp_path / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    template.write_text("key: template\n")
    calls = []

    def edit(self, text, *, title, validator):
        calls.append(text)
        assert validator("key: [\n") is not None
        assert not target.exists()
        assert validator("key: corrected\n") is None
        return EditResult("accepted", "key: corrected\n")

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main(["init", str(target), "--template", str(template)]) == 0
    assert len(calls) == 1
    assert target.read_text() == "key: corrected\n"


@pytest.mark.parametrize("failure", ["collision", "launch", "interrupt", "install"])
def test_template_init_reports_only_post_acceptance_recovery(tmp_path, monkeypatch, capsys, failure):
    target = tmp_path / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    template.write_text("key: template\n")

    def edit(self, text, **kwargs):
        if failure == "launch":
            raise RuntimeError("launch failed")
        if failure == "interrupt":
            raise KeyboardInterrupt
        if failure == "collision":
            target.write_text("key: concurrent\n")
        return EditResult("accepted", "key: saved\n")

    if failure == "install":
        def fail_install(*args, **kwargs):
            raise OSError("install failed")
        monkeypatch.setattr("confease.editing.install_draft", fail_install)
    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main(["init", str(target), "--template", str(template)]) == (130 if failure == "interrupt" else 1)
    error = capsys.readouterr().err
    assert target.exists() is (failure == "collision")
    if failure == "collision":
        assert target.read_text() == "key: concurrent\n"
    drafts = list(tmp_path.glob(".*"))
    if failure in ("collision", "install"):
        assert len(drafts) == 1
        assert drafts[0].read_text() == "key: saved\n"
        assert "Accepted editor text retained at:" in error
        assert str(drafts[0]) in error
    else:
        assert not drafts
        assert "retained" not in error


@pytest.mark.parametrize("problem", ["missing", "invalid", "existing"])
def test_template_init_rejects_bad_inputs_before_launch(tmp_path, monkeypatch, capsys, problem):
    target = tmp_path / "settings.yaml"
    template = tmp_path / "defaults.yaml"
    if problem != "missing":
        template.write_text("key: [\n" if problem == "invalid" else "key: template\n")
    if problem == "existing":
        target.write_text("key: original\n")

    def unexpected_launch(*args, **kwargs):
        pytest.fail("Invalid inputs must fail before launch")

    monkeypatch.setattr("confease.cli.TuiEditor.edit", unexpected_launch)
    assert main(["init", str(target), "--template", str(template)]) == 1
    assert capsys.readouterr().err
    assert target.exists() is (problem == "existing")
    if target.exists():
        assert target.read_text() == "key: original\n"


@pytest.mark.parametrize("args,parser,content", [
    ([], Yaml, b"key: 1\n"),
    (["--format", "json"], Json, b'{"key": 1}\n'),
])
def test_extensionless_template_init_uses_target_format(tmp_path, monkeypatch, args, parser, content):
    target = tmp_path / "settings"
    template = tmp_path / "seed.unrecognized"
    template.write_bytes(content)
    monkeypatch.setattr("confease.cli.TuiEditor.edit", lambda self, text, **kwargs: EditResult("accepted", text))
    assert main(["init", str(target), "--template", str(template), *args]) == 0
    assert target.read_bytes() == content
    assert parser.load(target) == {"key": 1}


def test_template_paths_expand_user_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "defaults.yaml").write_text("key: template\n")
    calls = []

    def cancel(self, text, **kwargs):
        calls.append(text)
        return EditResult("cancelled")

    monkeypatch.setattr("confease.cli.TuiEditor.edit", cancel)
    assert main(["init", "~/settings.yaml", "--template", "~/defaults.yaml"]) == 130
    assert calls == ["key: template\n"]
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
    assert "only on accept" in help_text
    assert "F2/F3" in help_text
    assert "best-effort" not in help_text
