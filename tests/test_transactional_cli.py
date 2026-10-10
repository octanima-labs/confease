"""CLI cancellation, diagnostics, and default session integration."""

import asyncio

import pytest
from edital import EditResult
from edital.app import EditorApp
from textual.widgets import TextArea

from confease.cli import main


@pytest.mark.parametrize("initializing", [False, True])
def test_explicit_cancel_preserves_destination(tmp_path, monkeypatch, capsys, initializing):
    path = tmp_path / "settings.yaml"
    if not initializing:
        path.write_text("key: original\n")
    monkeypatch.setattr("confease.cli.TuiEditor.edit", lambda *args, **kwargs: EditResult("cancelled"))
    args = ["init", str(path), "-i", "key=1"] if initializing else [str(path), "-b"]
    assert main(args) == 130
    assert "Cancelled" in capsys.readouterr().err
    assert path.exists() is (not initializing)
    if not initializing:
        assert path.read_text() == "key: original\n"
    assert not list(tmp_path.glob("*.bkp"))
    assert not list(tmp_path.glob(".*"))


def test_noninteractive_invocation_reports_actionable_error(tmp_path, capsys):
    path = tmp_path / "settings.yaml"
    assert main(["init", str(path)]) == 1
    assert "interactive terminal" in capsys.readouterr().err
    assert not path.exists()


def test_actual_ui_repairs_cli_document_without_reopening(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    path.write_text("key: [\n")
    calls = []

    def edit(self, initial_text, *, title, validator):
        async def exercise():
            app = EditorApp(initial_text, title=title, validator=validator)
            calls.append(app)
            async with app.run_test() as pilot:
                await pilot.press("f2")
                assert app.query_one(TextArea).text == initial_text
                assert path.read_text() == initial_text
                await pilot.press("f7", "k", "e", "y", ":", "space", "2", "f2")
            return app.return_value
        return asyncio.run(exercise())

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main([str(path), "-b"]) == 0
    assert len(calls) == 1
    assert path.read_text() == "key: 2"
    assert next(tmp_path.glob("*.bkp")).read_text() == "key: [\n"
