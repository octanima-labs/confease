"""Compatibility contracts for replacing presentation-losing backends."""

from datetime import date
from io import StringIO

import pytest
from iniparse import INIConfig

from confease import Ini, Yaml


@pytest.fixture
def yaml_types():
    return (
        (
            'legacy: yes\nnumber: 012\nexponent: 1e3\nquoted: "true"\n'
            'nothing: null\nitems: [1, false, "yes"]\nday: 2026-10-07\n'
        ),
        {"legacy": True, "number": 10, "exponent": "1e3", "quoted": "true",
         "nothing": None, "items": [1, False, "yes"], "day": date(2026, 10, 7)},
    )


def test_yaml_existing_type_interpretation(tmp_path, yaml_types):
    text, expected = yaml_types
    path = tmp_path / "settings.yaml"
    path.write_text(text)
    assert Yaml.load(path) == expected
    Yaml.save(path, expected)
    assert Yaml.load(path) == expected


def test_ini_existing_semantics(tmp_path):
    path = tmp_path / "settings.ini"
    path.write_text(
        '[DEFAULT]\nUpper = true\nupper = "true"\npercent = 100%\n'
        'list = [1, 2]\nquoted = "yes"\nempty = null\n'
        '[database]\nHost = localhost\n'
    )
    expected = {
        "Upper": True, "upper": "true", "percent": "100%", "list": [1, 2],
        "quoted": "yes", "empty": None, "database": {"Host": "localhost"},
    }
    assert Ini.load(path) == expected
    Ini.save(path, expected)
    assert Ini.load(path) == expected


def test_ini_configparser_syntax_compatibility(tmp_path):
    path = tmp_path / "settings.ini"
    path.write_text(
        '; header\n[DEFAULT]\ncolon: value\ntext = first\n    second\n'
        'literal = hello # world\n[section]\nvalue = 1\n'
    )
    expected = {
        "colon": "value", "text": "first second", "literal": "hello",
        "section": {"value": 1},
    }
    assert Ini.load(path) == expected


def test_iniparse_retains_configparser_syntax_and_case(tmp_path):
    text = (
        '; header\n[DEFAULT]\ncolon: value\ntext = first\n    second\n'
        'Upper = true\nupper = "true"\npercent = 100%\n'
        '# section comment\n[database] # section inline\nHost = localhost\n'
        '; footer\n'
    )
    document = INIConfig(StringIO(text), optionxformvalue=None)
    assert str(document) == text
    assert document.DEFAULT.Upper == "true"
    assert document.DEFAULT.upper == '"true"'
    document.database.Host = "remote"
    updated = str(document)
    assert updated == text.replace("localhost", "remote")
    path = tmp_path / "settings.ini"
    path.write_text(updated)
    assert Ini.load(path) == {
        "colon": "value", "text": "first second", "Upper": True,
        "upper": "true", "percent": "100%", "database": {"Host": "remote"},
    }
