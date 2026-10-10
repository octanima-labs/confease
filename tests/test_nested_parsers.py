"""Direct semantic parser contracts for recursive configurations."""

import configparser
import itertools
import xml.etree.ElementTree as ET

import pytest

from confease import PARSER_CLASSES, Csv, Ini, Json, Toml, Xml, Yaml

EXAMPLE = {"key": {"one": 1, "subkey": {"two": 2, "subsubkey": {
    "three": 3, "subsubsubkey": "hello"}}}}
FORMATS = list(PARSER_CLASSES.items())


@pytest.mark.parametrize("suffix,parser", FORMATS)
@pytest.mark.parametrize("data", [
    EXAMPLE, {"empty": {}}, {"a": {"b": {"empty": {}, "leaf": 1}}, "units": {}},
    {"a": {"b": {"list": [{"name": "example", "settings": {"enabled": True}}]}}},
    {"root": 1, "a": {"b": {"number": 1, "text": "1", "boolean": True}}},
])
def test_direct_parsers_round_trip_deep_and_empty_data(tmp_path, suffix, parser, data):
    path = tmp_path / f"config{suffix}"
    parser.save(path, data)
    assert parser.load(path) == data
    # Updating an existing presentation tree follows the same semantic contract.
    parser.save(path, data)
    assert parser.load(path) == data


@pytest.mark.parametrize("sections", list(itertools.permutations([
    "[key]\none = 1\n", "[key.subkey]\ntwo = 2\n",
    "[key.subkey.subsubkey]\nthree = 3\nsubsubsubkey = hello\n",
])))
def test_ini_sections_merge_in_any_order(tmp_path, sections):
    path = tmp_path / "config.ini"
    path.write_text("\n".join(sections))
    assert Ini.load(path) == EXAMPLE


@pytest.mark.parametrize("text,expected", [
    ("[a]\n[a.b]\n[a.b.c]\n", {"a": {"b": {"c": {}}}}),
    ("[a]\n[a.b]\nvalue = 1\n", {"a": {"b": {"value": 1}}}),
    ("[DEFAULT]\nunits = {}\n[key]\nempty = {}\none = 1\n",
     {"units": {}, "key": {"empty": {}, "one": 1}}),
    ("[DEFAULT]\nUpper = true\npercent = 100%\n[a.b]\nHost = localhost\n",
     {"Upper": True, "percent": "100%", "a": {"b": {"Host": "localhost"}}}),
])
def test_ini_empty_headers_and_explicit_option_semantics(tmp_path, text, expected):
    path = tmp_path / "config.ini"
    path.write_text(text)
    assert Ini.load(path) == expected
    Ini.save(path, expected)
    assert Ini.load(path) == expected


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "a.b.c: 1\na:\n  b:\n    c: 2\n"),
    (Yaml, ".yaml", "a:\n  b:\n    c: 1\n    c: 2\n"),
    (Json, ".json", '{"a.b.c": 1, "a": {"b": {"c": 2}}}'),
    (Json, ".json", '{"a": {"b": {"c": 1, "c": 2}}}'),
    (Toml, ".toml", '"a.b.c" = 1\n[a.b]\nc = 2\n'),
    (Ini, ".ini", "[a]\nb.c = 1\n[a.b]\nc = 2\n"),
    (Csv, ".csv", "key,value\na.b.c,1\na.b.c,2\n"),
    (Csv, ".csv", 'key,value\na,"{b: 1, b: 2}"\n'),
    (Ini, ".ini", "[DEFAULT]\na = {b: 1, b: 2}\n"),
    (Xml, ".xml", '<config><entry key="a">{b: 1, b: 2}</entry></config>'),
    (Xml, ".xml", '<config><entry key="a.b.c">1</entry><section name="a"><section name="b"><entry key="c">2</entry></section></section></config>'),
])
def test_loaders_reject_duplicate_logical_paths(tmp_path, parser, suffix, text):
    path = tmp_path / f"config{suffix}"
    path.write_text(text)
    with pytest.raises(ValueError, match="Duplicate"):
        parser.load(path)


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "a.b: 1\na.b.c: 2\n"),
    (Json, ".json", '{"a.b": 1, "a.b.c": 2}'),
    (Toml, ".toml", '"a.b" = 1\n"a.b.c" = 2\n'),
    (Ini, ".ini", "[a]\nb = 1\n[a.b]\nc = 2\n"),
    (Ini, ".ini", "[DEFAULT]\na.b = 1\n[a.b]\n"),
    (Csv, ".csv", "key,value\na.b,1\na.b.c,2\n"),
    (Xml, ".xml", '<config><section name="a"><entry key="b">1</entry><section name="b.c"><entry key="d">2</entry></section></section></config>'),
])
def test_loaders_reject_intermediate_scalar_conflicts(tmp_path, parser, suffix, text):
    path = tmp_path / f"config{suffix}"
    path.write_text(text)
    with pytest.raises(ValueError, match="collides|Duplicate"):
        parser.load(path)


def test_format_layouts_use_native_hierarchy_or_full_paths(tmp_path):
    toml = tmp_path / "config.toml"
    Toml.save(toml, EXAMPLE)
    assert "[key.subkey.subsubkey]" in toml.read_text()
    assert "one = 1" in toml.read_text()
    ini = tmp_path / "config.ini"
    Ini.save(ini, EXAMPLE)
    config = configparser.ConfigParser()
    config.read(ini)
    assert config.sections() == ["key", "key.subkey", "key.subkey.subsubkey"]
    xml = tmp_path / "config.xml"
    Xml.save(xml, EXAMPLE)
    assert ET.parse(xml).find("./section/section/section/entry[@key='three']").text == "3"
    csv = tmp_path / "config.csv"
    Csv.save(csv, EXAMPLE)
    assert "key.subkey.subsubkey.three,3" in csv.read_text()


def test_yaml_merge_semantics_remain_supported(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("base: &base\n  leaf: 1\nchild:\n  <<: *base\n  leaf: 2\n")
    assert Yaml.load(path) == {"base": {"leaf": 1}, "child": {"leaf": 2}}
