"""Format conversion and transactional entry points share recursive semantics."""

from itertools import product

import pytest
import yaml
from edital import EditResult
from tomlkit.exceptions import ConvertError

from confease import DEF, USR, Confease, Csv, Ini, Json, Toml, Xml, Yaml
from confease.backups import create_backup
from confease.cli import main
from confease.documents import equivalent

FORMATS = [(Yaml, ".yaml"), (Json, ".json"), (Toml, ".toml"),
           (Ini, ".ini"), (Xml, ".xml"), (Csv, ".csv")]
DATA = {
    "key": {"one": 1, "subkey": {"two": 2, "subsubkey": {
        "three": 3, "subsubsubkey": "hello"}}},
    "units": {},
    "types": {"nested": {"empty": {}, "number": 1, "text": "1", "flag": True,
                         "list": [{"name": "example", "settings": {"enabled": False}}]}},
}


@pytest.mark.parametrize("source_format,target_format", list(product(FORMATS, repeat=2)))
def test_cross_format_conversion_preserves_structure_and_types(tmp_path, source_format, target_format):
    source_parser, source_suffix = source_format
    target_parser, target_suffix = target_format
    source = tmp_path / f"source{source_suffix}"
    target = tmp_path / f"target{target_suffix}"
    source_parser.save(source, DATA)
    loaded = source_parser.load(source)
    assert equivalent(loaded, DATA)
    conf = Confease(target, parser=target_parser, items=loaded)
    conf.save(user_only=False)
    assert equivalent(target_parser.load(target), DATA)
    reloaded = Confease(target, parser=target_parser)
    for key, value in DATA.items():
        assert equivalent(reloaded[key], value)
    assert reloaded["key.subkey.subsubkey.three"] == 3


@pytest.mark.parametrize("parser,suffix", FORMATS)
def test_unrepresentable_deep_value_preserves_file_and_live_entries(tmp_path, parser, suffix):
    path = tmp_path / f"config{suffix}"
    parser.save(path, DATA)
    original = path.read_bytes()
    conf = Confease(path, parser=parser, backup=True)
    conf.set("types.nested.unsupported", object())
    previous = list(conf._entries)
    with pytest.raises((TypeError, ValueError, yaml.YAMLError, ConvertError)):
        conf.save()
    assert path.read_bytes() == original
    assert conf._entries == previous
    assert not list(tmp_path.glob("*.bkp"))
    assert not list(tmp_path.glob(".*"))


def test_deep_toml_null_is_explicit_safe_failure(tmp_path):
    path = tmp_path / "config.toml"
    Toml.save(path, DATA)
    original = path.read_bytes()
    conf = Confease(path, parser=Toml)
    conf.set("types.nested.null", None)
    previous = conf._entries
    with pytest.raises(ConvertError):
        conf.save()
    assert path.read_bytes() == original
    assert conf._entries is previous
    assert conf.get_item("types.nested.null").value is None


@pytest.mark.parametrize("parser,suffix", FORMATS)
def test_deep_origin_filtering_and_deferred_first_save(tmp_path, parser, suffix):
    path = tmp_path / f"config{suffix}"
    parser.save(path, DATA)
    conf = Confease(path, parser=parser, autoload=False,
                    items={"fallback": {"deep": {"value": 9, "empty": {}}}})
    assert conf._entries is None
    conf.save()
    assert equivalent(parser.load(path), DATA)
    assert conf.get_item("fallback.deep.empty").origin == DEF
    conf.set("user.deep.empty", {})
    conf.set("key.subkey.two", 8)
    conf.save()
    assert "fallback" not in parser.load(path)
    assert parser.load(path)["user"] == {"deep": {"empty": {}}}
    conf.save(user_only=False)
    assert parser.load(path)["fallback"] == {"deep": {"value": 9, "empty": {}}}


@pytest.mark.parametrize("parser,suffix", FORMATS)
def test_deep_deletion_autosaves_and_can_restore_backup(tmp_path, parser, suffix):
    path = tmp_path / f"config{suffix}"
    parser.save(path, DATA)
    original = path.read_bytes()
    conf = Confease(path, parser=parser, reload=True, backup=True)
    assert conf.delete("key.subkey.subsubkey") is True
    assert parser.load(path)["key"] == {"one": 1, "subkey": {"two": 2}}
    snapshots = list(tmp_path.glob("*.bkp"))
    assert len(snapshots) == 1
    assert snapshots[0].read_bytes() == original
    conf.restore(snapshots[0], backup=False)
    assert path.read_bytes() == original
    assert conf["key.subkey.subsubkey.three"] == 3
    assert conf.get_item("key.subkey.subsubkey.three").origin == USR


@pytest.mark.parametrize("parser,suffix", FORMATS)
def test_deep_template_reset_preserves_exact_bytes(tmp_path, parser, suffix):
    template = tmp_path / f"template{suffix}"
    parser.save(template, DATA)
    exact = template.read_bytes()
    path = tmp_path / f"config{suffix}"
    conf = Confease(path, parser=parser, template=template, autoload=False)
    assert conf.get_item("key.subkey.subsubkey.three").origin == DEF
    assert not path.exists()
    conf.reset()
    assert path.read_bytes() == exact
    assert conf.get_item("key.subkey.subsubkey.three").origin == USR
    conf.set("key.subkey.two", 99)
    conf.save()
    conf.reset()
    assert path.read_bytes() == exact


@pytest.mark.parametrize("parser,suffix", FORMATS)
def test_transactional_editor_accepts_deep_configuration_exactly(tmp_path, monkeypatch, parser, suffix):
    path = tmp_path / f"config{suffix}"
    parser.save(path, {"original": 1})
    original = path.read_bytes()
    candidate = tmp_path / f"candidate{suffix}"
    parser.save(candidate, DATA)
    accepted = candidate.read_text()
    conf = Confease(path, parser=parser, backup=True, autoload=False)

    def edit(text, *, title, validator):
        assert validator("definitely invalid document") is not None
        assert validator(accepted) is None
        assert path.read_bytes() == original
        assert conf._entries is None
        return EditResult("accepted", accepted)

    monkeypatch.setattr(conf.editor, "edit", edit)
    conf.edit_file()
    assert path.read_bytes() == accepted.encode()
    assert conf["key.subkey.subsubkey"] == {"three": 3, "subsubsubkey": "hello"}
    assert conf["units"] == {}
    assert len(list(tmp_path.glob("*.bkp"))) == 1


def test_deep_backup_recovery_bypasses_malformed_destination(tmp_path):
    path = tmp_path / "config.yaml"
    Yaml.save(path, DATA)
    source = create_backup(path)
    exact = source.read_bytes()
    path.write_text("key: [\n")
    conf = Confease(path, autoload=False, items={"fallback.deep.value": 9})
    conf.restore(source)
    assert path.read_bytes() == exact
    assert conf["key.subkey.subsubkey.three"] == 3
    assert conf["fallback.deep.value"] == 9


@pytest.mark.parametrize("parser,suffix", FORMATS)
def test_scripted_cli_updates_and_deletes_deep_paths(tmp_path, parser, suffix):
    path = tmp_path / f"config{suffix}"
    parser.save(path, DATA)
    assert main([str(path), "-u", "key.subkey.two=8",
                 "-d", "key.subkey.subsubkey"]) == 0
    assert parser.load(path)["key"] == {"one": 1, "subkey": {"two": 8}}
    original = path.read_bytes()
    assert main([str(path), "-u", "key.subkey.two.child=3"]) == 1
    assert path.read_bytes() == original
