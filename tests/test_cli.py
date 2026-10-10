"""CLI integration tests use controlled editors instead of a real terminal."""

import pytest
from edital import EditResult

from confease import Csv, Ini, Json, Toml, Xml, Yaml
from confease.cli import main


@pytest.fixture
def editor(monkeypatch):
    calls = []

    def edit(self, text, *, title, validator):
        calls.append(text.encode())
        assert validator(text) is None
        return EditResult("accepted", text)

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    return calls


@pytest.mark.parametrize("parser,suffix", [
    (Yaml, ".yaml"), (Yaml, ".yml"), (Json, ".json"), (Toml, ".toml"),
    (Ini, ".ini"), (Ini, ".cfg"), (Ini, ".conf"), (Ini, ".config"),
    (Xml, ".xml"), (Csv, ".csv"),
])
def test_init_infers_formats_and_accepts_seeded_draft(tmp_path, editor, parser, suffix):
    path = tmp_path / f"settings{suffix}"
    assert main(["init", str(path), "-i", "debug=true", "-i", "database.port=5432"]) == 0
    assert len(editor) == 1
    assert path.read_bytes() == editor[0]
    expected = {"debug": True, "database": {"port": 5432}}
    assert parser.load(path) == expected
    assert list(tmp_path.glob(".*")) == []


def test_init_default_and_explicit_format_keep_path(tmp_path, editor):
    path = tmp_path / "settings"
    assert main(["init", str(path), "-i", "key=1"]) == 0
    assert Yaml.load(path) == {"key": 1}
    other = tmp_path / "other"
    assert main(["init", str(other), "-f", "json", "-i", "key=2"]) == 0
    assert Json.load(other) == {"key": 2}
    assert not other.with_suffix(".json").exists()


@pytest.mark.parametrize("name", ["settings.yaml", "settings.yml", "settings"])
@pytest.mark.parametrize("add_key", [False, True])
def test_empty_yaml_init_preloads_edit_ready_document(tmp_path, monkeypatch, name, add_key):
    path = tmp_path / name
    initial = "%YAML 1.1\n---\n"

    def edit(self, text, *, title, validator):
        assert text == initial
        assert not path.exists()
        candidate = text + "custom: value\n" if add_key else text
        assert validator(candidate) is None
        return EditResult("accepted", candidate)

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main(["init", str(path)]) == 0
    assert path.read_text() == (initial + "custom: value\n" if add_key else initial)
    assert Yaml.load(path) == ({"custom": "value"} if add_key else {})


def test_unknown_format_and_existing_init_do_not_launch_editor(tmp_path, editor, capsys):
    path = tmp_path / "settings.unknown"
    assert main(["init", str(path)]) == 1
    assert "--format" in capsys.readouterr().err
    assert not path.exists()
    path.write_text("original")
    assert main(["init", str(path), "-f", "yaml"]) == 1
    assert path.read_text() == "original"
    assert editor == []


def test_edit_missing_file_errors_without_creation(tmp_path, editor):
    path = tmp_path / "missing.yaml"
    assert main([str(path), "-u", "key=1"]) == 1
    assert main(["edit", str(path)]) == 1
    assert not path.exists()
    assert editor == []


def test_scripted_typed_updates_and_delete_warning(tmp_path, editor, capsys):
    path = tmp_path / "settings.yaml"
    path.write_text("# header\nkey: old # inline\nremove: null\n")
    assert main([str(path), "-u", "key=first", "-u", "key=last", "-u", 'label="true"',
                 "-u", "token=a=b=c", "-u", "items=[alpha, beta]", "-u", "database.port=5432",
                 "-d", "remove", "-d", "absent"]) == 0
    assert Yaml.load(path) == {
        "key": "last", "label": "true", "token": "a=b=c", "items": ["alpha", "beta"],
        "database": {"port": 5432},
    }
    assert "# inline" in path.read_text()
    assert "absent" in capsys.readouterr().err
    assert editor == []


def test_delete_only_sections_is_noninteractive(tmp_path, editor):
    path = tmp_path / "settings.yaml"
    path.write_text("keep: 1\ndatabase:\n  host: local\n  port: 5432\n")
    assert main(["edit", str(path), "-d", "database"]) == 0
    assert Yaml.load(path) == {"keep": 1}
    assert editor == []


@pytest.mark.parametrize("flags", [
    ["-u", "key=2", "-d", "key"],
    ["-u", "database.host=remote", "-d", "database"],
    ["-u", "key=2", "-u", "database.host.deep=bad"],
    ["-u", "key=2", "-u", "=value"],
    ["-u", "key=2", "-u", "no-equals"],
    ["-u", "key=2", "-u", "key.child=collision"],
])
def test_invalid_batch_preserves_original(tmp_path, editor, flags):
    path = tmp_path / "settings.yaml"
    original = "key: 1 # inline\ndatabase:\n  host: local\n"
    path.write_text(original)
    assert main([str(path), *flags]) == 1
    assert path.read_text() == original
    assert list(tmp_path.glob(".*")) == []
    assert editor == []


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "database: scalar # obsolete\n"),
    (Toml, ".toml", 'database = "scalar" # obsolete\n'),
    (Ini, ".ini", '[DEFAULT]\ndatabase = scalar # obsolete\n'),
    (Xml, ".xml", '<config><entry key="database">scalar</entry> <!-- obsolete --></config>'),
])
def test_convert_scalar_to_section(tmp_path, editor, parser, suffix, text):
    path = tmp_path / f"settings{suffix}"
    path.write_text(text)
    assert main([str(path), "-d", "database", "-u", "database.host=local"]) == 0
    assert parser.load(path) == {"database": {"host": "local"}}
    assert "obsolete" not in path.read_text()


def test_scripted_invalid_source_offers_repair(tmp_path, editor, capsys):
    path = tmp_path / "settings.yaml"
    path.write_text("key: [\n")
    assert main([str(path), "-u", "key=1"]) == 1
    assert "Repair it" in capsys.readouterr().err
    assert path.read_text() == "key: [\n"
    assert editor == []


def test_toml_null_rejected_before_editor_and_without_truncation(tmp_path, editor):
    path = tmp_path / "settings.toml"
    assert main(["init", str(path), "-i", "key=null"]) == 1
    assert not path.exists()
    path.write_text("key=1 # inline\n")
    assert main([str(path), "-u", "key=null"]) == 1
    assert path.read_text() == "key=1 # inline\n"
    assert editor == []


def test_extensionless_edit_requires_override(tmp_path, editor):
    path = tmp_path / "settings"
    path.write_text('{"key": 1}')
    assert main([str(path), "-u", "key=2"]) == 1
    assert main([str(path), "-f", "json", "-u", "key=2"]) == 0
    assert Json.load(path) == {"key": 2}


def test_command_name_path_is_disambiguated(tmp_path, monkeypatch, editor):
    path = tmp_path / "init"
    path.write_text("key: 1\n")
    monkeypatch.chdir(tmp_path)
    assert main(["./init", "-f", "yaml", "-u", "key=2"]) == 0
    assert Yaml.load(path) == {"key": 2}


def test_interactive_invalid_source_and_draft_are_repaired(tmp_path, monkeypatch, capsys):
    path = tmp_path / "settings.yaml"
    original = b"key: [\r\n"
    path.write_bytes(original)
    calls = []
    valid = b"# header\r\nkey: 2 # inline\r\n"

    def edit(self, text, *, title, validator):
        calls.append(text.encode())
        assert path.read_bytes() == original
        assert validator("key: [1\n") is not None
        assert path.read_bytes() == original
        assert validator(valid.decode()) is None
        return EditResult("accepted", valid.decode())

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main(["edit", str(path)]) == 0
    assert calls == [original]
    assert "Reopening" not in capsys.readouterr().err
    assert path.read_bytes() == valid
    assert list(tmp_path.glob(".*")) == []


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_editor_failure_preserves_existing_or_missing_destination(tmp_path, monkeypatch, failure):
    path = tmp_path / "settings.yaml"

    def edit(self, text, **kwargs):
        raise failure()

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main(["init", str(path)]) != 0
    assert not path.exists()
    path.write_text("key: original\n")
    assert main([str(path)]) != 0
    assert path.read_text() == "key: original\n"
    assert list(tmp_path.glob(".*")) == []


def test_init_does_not_overwrite_destination_created_during_editor(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"

    def edit(self, text, **kwargs):
        path.write_text("key: concurrent\n")
        return EditResult("accepted", text)

    monkeypatch.setattr("confease.cli.TuiEditor.edit", edit)
    assert main(["init", str(path), "-i", "key=initial"]) == 1
    assert path.read_text() == "key: concurrent\n"
    drafts = list(tmp_path.glob(".*"))
    assert len(drafts) == 1
    assert Yaml.load(drafts[0]) == {"key": "initial"}


def test_generic_validation_does_not_claim_application_schema(tmp_path, editor):
    path = tmp_path / "settings.yaml"
    path.write_text("port: banana # app decides validity\n")
    assert main([str(path)]) == 0
    assert Yaml.load(path) == {"port": "banana"}


def test_help_describes_shorthand_and_repeatable_options(capsys):
    with pytest.raises(SystemExit) as error:
        main(["--help"])
    assert error.value.code == 0
    assert "confease PATH" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["edit", "--help"])
    help_text = capsys.readouterr().out
    assert "--update" in help_text and "--delete" in help_text and "--format" in help_text
