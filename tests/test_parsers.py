import csv as csv_module
import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from confease import PARSER_CLASSES, Csv, Ini, Json, Parser, Toml, Xml, Yaml


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


def test_empty_toml_file_loads_empty_mapping(tmp_path):
    path = tmp_path / "empty.toml"
    path.write_text("")

    assert Toml.load(path) == {}


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


def test_csv_parser_rejects_malformed_rows(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text("key,value\n,missing-key\n")

    with pytest.raises(ValueError, match="Malformed"):
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


def test_xml_parser_rejects_duplicate_entries(tmp_path):
    path = tmp_path / "invalid.xml"

    path.write_text("<config><entry key='KEY'>one</entry><entry key='KEY'>two</entry></config>")
    with pytest.raises(ValueError, match="Duplicate"):
        Xml.load(path)

    path.write_text("<config><section name='section'><entry key='KEY'>one</entry><entry key='KEY'>two</entry></section></config>")
    with pytest.raises(ValueError, match="Duplicate"):
        Xml.load(path)


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
