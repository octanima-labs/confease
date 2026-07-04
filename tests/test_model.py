import pytest
import json
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
    Csv,
    Json,
    Parser,
    Toml,
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

    assert conf.get("NUMBER") == 1312
    assert conf.get("NUMBER", cast=int) == 1312
    assert conf.get("NUMBER", cast=dict) == 1312


def test_get_item_returns_confitem():
    conf = Confease(KEY="value")

    item = conf.get_item("KEY")

    assert item == Confitem("KEY", "value", DEF)


def test_set_adds_and_updates_user_origin_values():
    conf = Confease()

    conf.set("KEY", 1)
    assert conf.get_item("KEY") == Confitem("KEY", 1, USR)

    conf.set("KEY", 2)
    assert conf.get_item("KEY") == Confitem("KEY", 2, USR)


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
    assert conf.get_item("NUMBER") == Confitem("NUMBER", 3, USR)
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


def test_nested_defaults_support_dotted_and_section_access():
    conf = Confease(**{"database": {"host": "localhost", "port": 5432}})

    assert conf.get("database.host") == "localhost"
    assert conf.get("database.port") == 5432
    assert conf.get("database") == {"host": "localhost", "port": 5432}


def test_set_supports_nested_dict_values():
    conf = Confease()

    conf.set("database", {"host": "localhost", "port": 5432})

    assert conf.get_item("database.host") == Confitem("database.host", "localhost", USR)
    assert conf.get_item("database.port") == Confitem("database.port", 5432, USR)
    assert conf.get("database") == {"host": "localhost", "port": 5432}


def test_set_supports_dotted_nested_keys():
    conf = Confease()

    conf.set("database.host", "localhost")

    assert conf.get("database.host") == "localhost"
    assert conf.get("database") == {"host": "localhost"}


def test_yaml_load_flattens_nested_mapping_into_leaf_items(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("database:\n  host: localhost\n  port: 5432\n")

    conf = Confease(path)

    assert conf.get_item("database.host") == Confitem("database.host", "localhost", USR)
    assert conf.get_item("database.port") == Confitem("database.port", 5432, USR)
    assert conf.get("database") == {"host": "localhost", "port": 5432}


def test_yaml_save_nests_dotted_leaf_items(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path)

    conf.set("database.host", "localhost")
    conf.set("database.port", 5432)
    conf.save()

    assert yaml.safe_load(path.read_text()) == {"database": {"host": "localhost", "port": 5432}}


def test_scalar_and_nested_key_collisions_raise_errors():
    conf = Confease()

    conf.set("database.host", "localhost")
    with pytest.raises(ValueError, match="collides"):
        conf.set("database", "sqlite")

    other = Confease()
    other.set("database", "sqlite")
    with pytest.raises(ValueError, match="collides"):
        other.set("database.host", "localhost")


def test_nested_keys_support_one_level_only():
    conf = Confease()

    with pytest.raises(ValueError, match="one level"):
        conf.set("a.b.c", "value")
    with pytest.raises(ValueError, match="one level"):
        conf.set("a", {"b": {"c": "value"}})


def test_unsupported_parser_raises_for_persistence(tmp_path):
    path = tmp_path / "conf.csv"
    path.write_text("KEY,value\n")

    with pytest.raises(NotImplementedError, match="not implemented"):
        Confease(path, parser=Csv)

    missing_path = tmp_path / "new.csv"
    conf = Confease(missing_path, parser=Csv)
    conf.set("KEY", "value")
    with pytest.raises(NotImplementedError, match="not implemented"):
        conf.save()


def test_yaml_parser_loads_and_saves_plain_mapping(tmp_path):
    path = tmp_path / "conf.yaml"

    Yaml.save(path, {"KEY": "value", "database": {"host": "localhost"}})

    assert Yaml.load(path) == {"KEY": "value", "database": {"host": "localhost"}}
    assert yaml.safe_load(path.read_text()) == {"KEY": "value", "database": {"host": "localhost"}}


def test_yaml_parser_rejects_non_mapping_files(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("- item\n")

    with pytest.raises(ValueError, match="key-value mapping"):
        Yaml.load(path)


def test_toml_parser_loads_and_saves_nested_mapping(tmp_path):
    path = tmp_path / "conf.toml"

    Toml.save(path, {"KEY": "value", "database": {"host": "localhost", "port": 5432}})

    assert Toml.load(path) == {"KEY": "value", "database": {"host": "localhost", "port": 5432}}


def test_json_parser_loads_and_saves_nested_mapping(tmp_path):
    path = tmp_path / "conf.json"

    Json.save(path, {"KEY": "value", "database": {"host": "localhost", "port": 5432}})

    assert Json.load(path) == {"KEY": "value", "database": {"host": "localhost", "port": 5432}}
    assert json.loads(path.read_text()) == {"KEY": "value", "database": {"host": "localhost", "port": 5432}}
    assert path.read_text().startswith("{\n")


def test_json_parser_rejects_non_mapping_files(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('["item"]')

    with pytest.raises(ValueError, match="key-value mapping"):
        Json.load(path)


def test_json_file_loads_when_parser_is_inferred(tmp_path):
    path = tmp_path / "conf.json"
    path.write_text('{"KEY": "value", "database": {"host": "localhost", "port": 5432}}')

    conf = Confease(path, parser=None)

    assert conf.get_item("KEY") == Confitem("KEY", "value", USR)
    assert conf.get_item("database.host") == Confitem("database.host", "localhost", USR)
    assert conf.get_item("database.port") == Confitem("database.port", 5432, USR)


def test_confease_saves_nested_values_as_json(tmp_path):
    path = tmp_path / "conf.json"
    conf = Confease(path, parser=Json)

    conf.set("database.host", "localhost")
    conf.set("database.port", 5432)
    conf.save()

    assert Json.load(path) == {"database": {"host": "localhost", "port": 5432}}


def test_empty_toml_file_loads_empty_mapping(tmp_path):
    path = tmp_path / "empty.toml"
    path.write_text("")

    assert Toml.load(path) == {}


def test_toml_file_loads_when_parser_is_inferred(tmp_path):
    path = tmp_path / "conf.toml"
    path.write_text('KEY = "value"\n\n[database]\nhost = "localhost"\nport = 5432\n')

    conf = Confease(path, parser=None)

    assert conf.get_item("KEY") == Confitem("KEY", "value", USR)
    assert conf.get_item("database.host") == Confitem("database.host", "localhost", USR)
    assert conf.get_item("database.port") == Confitem("database.port", 5432, USR)


def test_confease_saves_nested_values_as_toml(tmp_path):
    path = tmp_path / "conf.toml"
    conf = Confease(path, parser=Toml)

    conf.set("database.host", "localhost")
    conf.set("database.port", 5432)
    conf.save()

    assert Toml.load(path) == {"database": {"host": "localhost", "port": 5432}}


def test_parser_registry_maps_yaml_extensions_to_yaml_class():
    assert PARSER_CLASSES[".yaml"] is Yaml
    assert PARSER_CLASSES[".yml"] is Yaml
    assert PARSER_CLASSES[".json"] is Json
    assert PARSER_CLASSES[".toml"] is Toml


def test_base_parser_methods_raise_not_implemented(tmp_path):
    path = tmp_path / "conf.txt"

    with pytest.raises(NotImplementedError):
        Parser.load(path)
    with pytest.raises(NotImplementedError):
        Parser.save(path, {})
