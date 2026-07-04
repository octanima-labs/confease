import pytest
import yaml

from confease import (
    CLI,
    DEF,
    ENV,
    ORIGINS,
    PARSER_CLASSES,
    SYS,
    USR,
    Confease,
    Confitem,
    Json,
    Parser,
    Yaml,
)


def test_preference_defaults_to_origin_order():
    conf = Confease()

    assert conf.preference == ORIGINS


def test_preference_accepts_subset_and_appends_omitted_origins():
    conf = Confease(preference=[USR, DEF])

    assert conf.preference == [USR, DEF, CLI, ENV, SYS]


def test_preference_rejects_unknown_origin():
    with pytest.raises(ValueError, match="Unknown origin"):
        Confease(preference=["unknown"])


def test_preference_rejects_duplicate_origin():
    with pytest.raises(ValueError, match="Duplicate origin"):
        Confease(preference=[CLI, CLI])


def test_get_returns_default_for_missing_key():
    conf = Confease(EXISTING="value")

    assert conf.get("MISSING") is None
    assert conf.get("MISSING", default="fallback") == "fallback"


def test_get_casts_values_and_keeps_string_on_cast_failure():
    conf = Confease(NUMBER=1312)

    assert conf.get("NUMBER") == "1312"
    assert conf.get("NUMBER", cast=int) == 1312
    assert conf.get("NUMBER", cast=dict) == "1312"


def test_get_item_returns_confitem():
    conf = Confease(KEY="value")

    item = conf.get_item("KEY")

    assert item == Confitem("KEY", "value", DEF)


def test_set_adds_and_updates_user_origin_values():
    conf = Confease()

    conf.set("KEY", 1)
    assert conf.get_item("KEY") == Confitem("KEY", "1", USR)

    conf.set("KEY", 2)
    assert conf.get_item("KEY") == Confitem("KEY", "2", USR)


def test_incoming_higher_priority_origin_replaces_existing_item():
    conf = Confease(preference=[CLI, ENV, USR, DEF])

    conf._set_item("KEY", "default", DEF)
    conf._set_item("KEY", "cli", CLI)

    assert conf.get_item("KEY") == Confitem("KEY", "cli", CLI)


def test_incoming_lower_priority_origin_does_not_replace_existing_item():
    conf = Confease(preference=[CLI, ENV, USR, DEF])

    conf._set_item("KEY", "cli", CLI)
    conf._set_item("KEY", "default", DEF)

    assert conf.get_item("KEY") == Confitem("KEY", "cli", CLI)


def test_set_force_updates_even_when_user_origin_is_lower_priority():
    conf = Confease(preference=[CLI, ENV, USR, DEF])

    conf._set_item("KEY", "cli", CLI)
    conf.set("KEY", "user")

    assert conf.get_item("KEY") == Confitem("KEY", "user", USR)


def test_existing_yaml_file_loads_on_init_with_defaults(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("APP_DIR: /tmp/app\nNUMBER: 3\n")

    conf = Confease(path, APP_DIR="~/Apps", OTHER="default")

    assert conf.get_item("APP_DIR") == Confitem("APP_DIR", "/tmp/app", USR)
    assert conf.get_item("NUMBER") == Confitem("NUMBER", "3", USR)
    assert conf.get_item("OTHER") == Confitem("OTHER", "default", DEF)


def test_missing_yaml_file_uses_defaults_without_creating_file(tmp_path):
    path = tmp_path / "missing.yaml"
    conf = Confease(path, KEY="default")

    assert conf.get("KEY") == "default"
    assert not path.exists()


def test_save_writes_only_user_entries(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, DEFAULT="default")

    conf.set("USER", "value")
    conf.save()

    assert yaml.safe_load(path.read_text()) == {"USER": "value"}


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "configs" / "conf.yaml"
    conf = Confease(path)

    conf.set("KEY", "value")
    conf.save()

    assert yaml.safe_load(path.read_text()) == {"KEY": "value"}


def test_empty_yaml_file_loads_defaults(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("")

    conf = Confease(path, KEY="default")

    assert conf.get_item("KEY") == Confitem("KEY", "default", DEF)


def test_non_mapping_yaml_file_raises_value_error(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("- item\n")

    with pytest.raises(ValueError, match="key-value mapping"):
        Confease(path)


def test_yml_file_loads_when_parser_is_inferred(tmp_path):
    path = tmp_path / "conf.yml"
    path.write_text("KEY: value\n")

    conf = Confease(path, parser=None)

    assert conf.get_item("KEY") == Confitem("KEY", "value", USR)


def test_unsupported_parser_raises_for_persistence(tmp_path):
    path = tmp_path / "conf.json"
    path.write_text('{"KEY": "value"}')

    with pytest.raises(NotImplementedError, match="not implemented"):
        Confease(path, parser=Json)

    missing_path = tmp_path / "new.json"
    conf = Confease(missing_path, parser=Json)
    conf.set("KEY", "value")
    with pytest.raises(NotImplementedError, match="not implemented"):
        conf.save()


def test_yaml_parser_loads_and_saves_plain_mapping(tmp_path):
    path = tmp_path / "conf.yaml"

    Yaml.save(path, {"KEY": "value"})

    assert Yaml.load(path) == {"KEY": "value"}
    assert yaml.safe_load(path.read_text()) == {"KEY": "value"}


def test_yaml_parser_rejects_non_mapping_files(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("- item\n")

    with pytest.raises(ValueError, match="key-value mapping"):
        Yaml.load(path)


def test_parser_registry_maps_yaml_extensions_to_yaml_class():
    assert PARSER_CLASSES[".yaml"] is Yaml
    assert PARSER_CLASSES[".yml"] is Yaml


def test_base_parser_methods_raise_not_implemented(tmp_path):
    path = tmp_path / "conf.txt"

    with pytest.raises(NotImplementedError):
        Parser.load(path)
    with pytest.raises(NotImplementedError):
        Parser.save(path, {})
