import pytest
import yaml

from confease import CLI, DEF, USR, Confease, Confitem, Csv, Ini, Json, Toml, Xml


@pytest.mark.parametrize("content", [
    "- invalid\n",
    "KEY: [\n",
    "database:\n  host:\n    nested: invalid\n",
    "database: scalar\ndatabase.host: collision\n",
])
def test_failed_load_preserves_previous_entries(tmp_path, content):
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: original\n")
    conf = Confease(path, items={"DEFAULT": "fallback"})
    conf.set("UNSAVED", 42)
    previous = list(conf._entries)
    path.write_text(content)

    with pytest.raises((ValueError, yaml.YAMLError)):
        conf.load()

    assert conf._entries == previous
    assert conf.get("KEY") == "original"
    assert conf.get("UNSAVED") == 42


def test_failed_load_with_default_collision_preserves_entries(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, items={"database": {"host": "default"}})
    conf.set("KEY", "original")
    previous = list(conf._entries)
    path.write_text("database: scalar\n")

    with pytest.raises(ValueError, match="collides"):
        conf.load()

    assert conf._entries == previous


def test_existing_yaml_file_loads_on_init_with_defaults(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("APP_DIR: /tmp/app\nNUMBER: 3\n")

    conf = Confease(path, items={"APP_DIR": "~/Apps", "OTHER": "default"})

    assert conf.get_item("APP_DIR") == Confitem("APP_DIR", "/tmp/app", USR)
    assert conf.get_item("NUMBER") == Confitem("NUMBER", 3, USR)
    assert conf.get_item("OTHER") == Confitem("OTHER", "default", DEF)


def test_missing_yaml_file_uses_defaults_without_creating_file(tmp_path):
    path = tmp_path / "missing.yaml"
    conf = Confease(path, items={"KEY": "default"})

    assert conf.get("KEY") == "default"
    assert not path.exists()


def test_save_writes_only_user_entries(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, items={"DEFAULT": "default"})

    conf.set("USER", "value")
    conf.save()

    assert yaml.safe_load(path.read_text()) == {"USER": "value"}


def test_save_can_write_default_entries_when_user_only_is_false(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, items={"DEFAULT": "default"})

    conf.save(user_only=False)

    assert yaml.safe_load(path.read_text()) == {"DEFAULT": "default"}


def test_save_can_write_entries_from_all_origins(tmp_path):
    path = tmp_path / "conf.yaml"
    conf = Confease(path, items={"DEFAULT": "default"})

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
    conf = Confease(path, items={"database": {"host": "default"}})

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

    conf = Confease(path, items={"KEY": "default"})

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
