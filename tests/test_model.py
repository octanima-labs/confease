import csv as csv_module
import json
import xml.etree.ElementTree as ET

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
    Csv,
    Ini,
    Json,
    Parser,
    Toml,
    Xml,
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


def test_save_can_write_default_entries_when_user_only_is_false(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, DEFAULT="default")

    conf.save(user_only=False)

    assert yaml.safe_load(path.read_text()) == {"DEFAULT": "default"}


def test_save_can_write_entries_from_all_origins(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, DEFAULT="default")

    conf.set("USER", "value")
    conf._set_item("CLI_VALUE", "cli", CLI)
    conf.save(user_only=False)

    assert yaml.safe_load(path.read_text()) == {
        "CLI_VALUE": "cli",
        "DEFAULT": "default",
        "USER": "value",
    }


def test_save_can_write_nested_entries_from_all_origins(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, **{"database": {"host": "default"}})

    conf.set("database.port", 5432)
    conf.save(user_only=False)

    assert yaml.safe_load(path.read_text()) == {"database": {"host": "default", "port": 5432}}


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


def test_csv_parser_loads_and_saves_flat_dotted_mapping(tmp_path):
    path = tmp_path / "conf.csv"

    Csv.save(path, {"KEY": "value", "database": {"host": "localhost", "port": 5432}})

    assert Csv.load(path) == {"KEY": "value", "database.host": "localhost", "database.port": 5432}
    with path.open(newline="") as file:
        rows = list(csv_module.DictReader(file))
    assert rows == [
        {"key": "KEY", "value": "value"},
        {"key": "database.host", "value": "localhost"},
        {"key": "database.port", "value": "5432"},
    ]


def test_csv_parser_rejects_missing_required_header(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text("name,value\nKEY,value\n")

    with pytest.raises(ValueError, match="key,value"):
        Csv.load(path)


def test_csv_parser_loads_yaml_typed_values(tmp_path):
    path = tmp_path / "conf.csv"
    path.write_text("key,value\nenabled,true\nmissing,null\nnumbers,\"[1, 2, 3]\"\n")

    assert Csv.load(path) == {"enabled": True, "missing": None, "numbers": [1, 2, 3]}


def test_ini_parser_loads_and_saves_sectioned_mapping(tmp_path):
    path = tmp_path / "conf.ini"

    Ini.save(path, {"APP_DIR": "~/Apps", "database": {"HOST": "localhost", "port": 5432}})

    assert Ini.load(path) == {"APP_DIR": "~/Apps", "database": {"HOST": "localhost", "port": 5432}}


def test_ini_parser_loads_yaml_typed_values(tmp_path):
    path = tmp_path / "conf.ini"
    path.write_text("[DEFAULT]\nenabled = true\nmissing = null\nnumbers = [1, 2, 3]\n")

    assert Ini.load(path) == {"enabled": True, "missing": None, "numbers": [1, 2, 3]}


def test_ini_parser_preserves_key_case(tmp_path):
    path = tmp_path / "conf.ini"
    path.write_text("[DEFAULT]\nAPP_DIR = ~/Apps\n\n[database]\nHOST = localhost\n")

    assert Ini.load(path) == {"APP_DIR": "~/Apps", "database": {"HOST": "localhost"}}


def test_xml_parser_loads_and_saves_entry_section_mapping(tmp_path):
    path = tmp_path / "conf.xml"

    Xml.save(path, {"APP_DIR": "~/Apps", "debug": True, "database": {"host": "localhost", "port": 5432}})

    assert Xml.load(path) == {
        "APP_DIR": "~/Apps",
        "debug": True,
        "database": {"host": "localhost", "port": 5432},
    }
    assert ET.parse(path).getroot().tag == "config"


def test_xml_parser_loads_yaml_typed_values(tmp_path):
    path = tmp_path / "conf.xml"
    path.write_text(
        """<?xml version='1.0'?>
<config>
  <entry key="enabled">true</entry>
  <entry key="missing">null</entry>
  <entry key="numbers">[1, 2, 3]</entry>
  <section name="database">
    <entry key="port">5432</entry>
  </section>
</config>
"""
    )

    assert Xml.load(path) == {
        "enabled": True,
        "missing": None,
        "numbers": [1, 2, 3],
        "database": {"port": 5432},
    }


def test_xml_parser_rejects_invalid_shapes(tmp_path):
    path = tmp_path / "invalid.xml"

    path.write_text("<settings></settings>")
    with pytest.raises(ValueError, match="root"):
        Xml.load(path)

    path.write_text("<config><item key='KEY'>value</item></config>")
    with pytest.raises(ValueError, match="Unsupported"):
        Xml.load(path)

    path.write_text("<config><entry>value</entry></config>")
    with pytest.raises(ValueError, match="key attribute"):
        Xml.load(path)

    path.write_text("<config><section><entry key='KEY'>value</entry></section></config>")
    with pytest.raises(ValueError, match="name attribute"):
        Xml.load(path)

    path.write_text("<config><section name='section'><section name='nested'></section></section></config>")
    with pytest.raises(ValueError, match="only contain entry"):
        Xml.load(path)


def test_ini_file_loads_when_parser_is_inferred(tmp_path):
    path = tmp_path / "conf.ini"
    path.write_text("[DEFAULT]\nAPP_DIR = ~/Apps\n\n[database]\nhost = localhost\nport = 5432\n")

    conf = Confease(path, parser=None)

    assert conf.get_item("APP_DIR") == Confitem("APP_DIR", "~/Apps", USR)
    assert conf.get_item("database.host") == Confitem("database.host", "localhost", USR)
    assert conf.get_item("database.port") == Confitem("database.port", 5432, USR)


def test_xml_file_loads_when_parser_is_inferred(tmp_path):
    path = tmp_path / "conf.xml"
    path.write_text(
        """<config>
  <entry key="KEY">value</entry>
  <section name="database">
    <entry key="host">localhost</entry>
    <entry key="port">5432</entry>
  </section>
</config>
"""
    )

    conf = Confease(path, parser=None)

    assert conf.get_item("KEY") == Confitem("KEY", "value", USR)
    assert conf.get_item("database.host") == Confitem("database.host", "localhost", USR)
    assert conf.get_item("database.port") == Confitem("database.port", 5432, USR)


def test_cfg_conf_and_config_files_infer_ini_parser(tmp_path):
    for suffix in [".cfg", ".conf", ".config"]:
        path = tmp_path / f"conf{suffix}"
        path.write_text("[section]\nkey = value\n")

        conf = Confease(path, parser=None)

        assert conf.get_item("section.key") == Confitem("section.key", "value", USR)


def test_confease_saves_nested_values_as_ini(tmp_path):
    path = tmp_path / "conf.ini"
    conf = Confease(path, parser=Ini)

    conf.set("APP_DIR", "~/Apps")
    conf.set("database.host", "localhost")
    conf.set("database.port", 5432)
    conf.save()

    assert Ini.load(path) == {"APP_DIR": "~/Apps", "database": {"host": "localhost", "port": 5432}}


def test_confease_saves_nested_values_as_xml(tmp_path):
    path = tmp_path / "conf.xml"
    conf = Confease(path, parser=Xml)

    conf.set("APP_DIR", "~/Apps")
    conf.set("database.host", "localhost")
    conf.set("database.port", 5432)
    conf.save()

    assert Xml.load(path) == {"APP_DIR": "~/Apps", "database": {"host": "localhost", "port": 5432}}


def test_csv_file_loads_when_parser_is_inferred(tmp_path):
    path = tmp_path / "conf.csv"
    path.write_text("key,value\nKEY,value\ndatabase.host,localhost\ndatabase.port,5432\n")

    conf = Confease(path, parser=None)

    assert conf.get_item("KEY") == Confitem("KEY", "value", USR)
    assert conf.get_item("database.host") == Confitem("database.host", "localhost", USR)
    assert conf.get_item("database.port") == Confitem("database.port", 5432, USR)


def test_confease_saves_nested_values_as_csv(tmp_path):
    path = tmp_path / "conf.csv"
    conf = Confease(path, parser=Csv)

    conf.set("database.host", "localhost")
    conf.set("database.port", 5432)
    conf.save()

    assert Csv.load(path) == {"database.host": "localhost", "database.port": 5432}


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
    assert PARSER_CLASSES[".csv"] is Csv
    assert PARSER_CLASSES[".ini"] is Ini
    assert PARSER_CLASSES[".cfg"] is Ini
    assert PARSER_CLASSES[".conf"] is Ini
    assert PARSER_CLASSES[".config"] is Ini
    assert PARSER_CLASSES[".xml"] is Xml


def test_base_parser_methods_raise_not_implemented(tmp_path):
    path = tmp_path / "conf.txt"

    with pytest.raises(NotImplementedError):
        Parser.load(path)
    with pytest.raises(NotImplementedError):
        Parser.save(path, {})
