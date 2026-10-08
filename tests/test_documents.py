"""Round-trip behavior of actual emitted configuration documents."""

from pathlib import Path

import pytest
import yaml
from tomlkit.exceptions import ConvertError

from confease import CLI, Confease, Ini, Json, Toml, Xml, Yaml
from confease.documents import render_document


def test_yaml_updates_keep_all_comment_positions(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(
        '# header\n# multiline\nkey: value # inline\n'
        'key2: # section inline\n  # nested leading\n  subkey: value\n'
        'servers:\n  - alpha # primary\n  - beta # fallback\n'
        'message: |\n  # literal content\n  hello\n# footer\n'
    )
    conf = Confease(path)
    conf.set("key", "new")
    conf.set("key2.subkey", "updated")
    conf.save()
    text = path.read_text()
    for comment in ["# header", "# multiline", "# inline", "# section inline",
                    "# nested leading", "# primary", "# fallback", "# footer"]:
        assert text.count(comment) == 1
    assert Yaml.load(path)["message"] == "# literal content\nhello\n"
    assert Yaml.load(path)["key2"] == {"subkey": "updated"}


def test_yaml_new_list_retains_comments_of_surviving_elements(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("items:\n  - alpha # first\n  - beta # second\n")
    Yaml.save(path, {"items": ["beta", "gamma"]})
    assert "# second" in path.read_text()
    assert "# first" not in path.read_text()
    assert Yaml.load(path) == {"items": ["beta", "gamma"]}


def test_yaml_list_footer_and_following_comments_survive_list_changes(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("items:\n  - alpha # first\n  - beta # second\n# footer\n")
    Yaml.save(path, {"items": ["alpha"]})
    assert "# first" in path.read_text()
    assert "# second" not in path.read_text()
    assert path.read_text().endswith("# footer\n")
    Yaml.save(path, {})
    assert path.read_text().endswith("# footer\n")
    path.write_text("items:\n  - alpha # first\n# next key leading\nnext: 2\n")
    Yaml.save(path, {"next": 3})
    assert "# next key leading\nnext: 3" in path.read_text()


def test_toml_new_list_retains_comments_of_surviving_elements(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('items = [\n  "alpha", # first\n  "beta", # second\n]\n')
    Toml.save(path, {"items": ["beta", "gamma"]})
    assert "# second" in path.read_text()
    assert "# first" not in path.read_text()
    assert Toml.load(path) == {"items": ["beta", "gamma"]}


def test_comments_only_yaml_preserves_exact_comment_lines(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("# header\n# continuation\n\n")
    Yaml.save(path, {"key": 1})
    assert path.read_text().startswith("# header\n# continuation\n\n")


def test_toml_footer_remains_after_new_tables(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text('[first]\nvalue=1\n# footer\n')
    Toml.save(path, {"first": {"value": 1}, "second": {"value": 2}})
    assert path.read_text().endswith("# footer\n")


@pytest.mark.parametrize("parser,suffix,text,desired,kept,removed", [
    (Yaml, ".yaml", "# header\nkeep: 1 # keep inline\n# remove leading\nremove: 2 # remove inline\n# footer\n",
     {"keep": 3}, ["# header", "# keep inline", "# footer"], ["# remove leading", "# remove inline"]),
    (Toml, ".toml", "# header\nkeep = 1 # keep inline\n# remove leading\nremove = 2 # remove inline\n# footer\n",
     {"keep": 3}, ["# header", "# keep inline", "# footer"], ["# remove leading", "# remove inline"]),
    (Ini, ".ini", "; header\n[DEFAULT]\nkeep: 1 # keep inline\n# remove leading\nremove = 2 # remove inline\n; footer\n",
     {"keep": 3}, ["; header", "# keep inline", "; footer"], ["# remove leading", "# remove inline"]),
    (Xml, ".xml", "<!-- header --><config>\n<entry key='keep'>1</entry> <!-- keep inline -->\n<!-- remove leading -->\n<entry key='remove'>2</entry> <!-- remove inline -->\n<!-- footer -->\n</config><!-- outside footer -->",
     {"keep": 3}, ["<!-- header -->", "<!-- keep inline -->", "<!-- footer -->", "<!-- outside footer -->"],
     ["<!-- remove leading -->", "<!-- remove inline -->"]),
])
def test_comment_ownership_on_deletion(tmp_path, parser, suffix, text, desired, kept, removed):
    path = tmp_path / f"settings{suffix}"
    path.write_text(text)
    parser.save(path, desired)
    output = path.read_text()
    for comment in kept:
        assert output.count(comment) == 1
    for comment in removed:
        assert comment not in output
    assert parser.load(path) == desired


def test_toml_updates_preserve_tables_and_lists(tmp_path):
    path = tmp_path / "settings.toml"
    path.write_text(
        '# header\nkey = 1 # top inline\nservers = [\n "a", # primary\n "b", # fallback\n]\n'
        '# section leading\n[database] # section inline\n# host leading\nhost = "local" # host inline\n# footer\n'
    )
    values = Toml.load(path)
    values["key"] = 2
    values["database"]["host"] = "remote"
    Toml.save(path, values)
    for comment in ["header", "top inline", "primary", "fallback", "section leading",
                    "section inline", "host leading", "host inline", "footer"]:
        assert f"# {comment}" in path.read_text()
    assert Toml.load(path) == values


@pytest.mark.parametrize("suffix", [".ini", ".cfg", ".conf", ".config"])
def test_ini_syntax_and_inline_hash_comments(tmp_path, suffix):
    path = tmp_path / f"settings{suffix}"
    path.write_text(
        '; header\n[DEFAULT]\nUpper: true # boolean\nupper = "true" # string\n'
        'percent = 100%\nmessage = first\n    second\n'
        '# section leading\n[database] # section inline\n  # host leading\nHost = localhost # host inline\n; footer\n'
    )
    values = Ini.load(path)
    values["Upper"] = False
    values["database"]["Host"] = "remote"
    Ini.save(path, values)
    output = path.read_text()
    for comment in ["; header", "# boolean", "# string", "# section leading",
                    "# section inline", "# host leading", "# host inline", "; footer"]:
        assert output.count(comment) == 1
    assert "Upper:" in output
    assert "message = first\n    second" in output
    assert Ini.load(path) == values


def test_ini_indented_options_are_not_mistaken_for_continuations(tmp_path):
    path = tmp_path / "settings.ini"
    path.write_text(
        "[DEFAULT]\n  first = 1 # inline\n  second: 2\n  text = first\n"
        "      second\n  [section]\n  key = 3\n"
    )
    values = Ini.load(path)
    values["second"] = 4
    values["section"]["key"] = 5
    Ini.save(path, values)
    assert Ini.load(path) == values
    assert "# inline" in path.read_text()


def test_xml_all_boundaries_and_inner_entry_comments(tmp_path):
    path = tmp_path / "settings.xml"
    path.write_text(
        '<?xml version="1.0"?>\n<!-- prolog -->\n<config>\n<!-- root header -->\n'
        '<entry key="key">old<!-- inside entry --></entry>\n'
        '<!-- section leading -->\n<section name="database">\n<!-- host leading -->\n'
        '<entry key="host">local</entry>\n</section>\n<!-- root footer -->\n</config>\n<!-- epilog -->\n'
    )
    Xml.save(path, {"key": "new", "database": {"host": "remote"}})
    output = path.read_text()
    for comment in ["prolog", "root header", "inside entry", "section leading",
                    "host leading", "root footer", "epilog"]:
        assert output.count(f"<!-- {comment} -->") == 1
    assert Xml.load(path) == {"key": "new", "database": {"host": "remote"}}


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "# header\nkey: 1\n# footer\n"),
    (Toml, ".toml", "# header\nkey=1\n# footer\n"),
    (Ini, ".ini", "; header\n[DEFAULT]\nkey=1\n; footer\n"),
    (Xml, ".xml", "<!-- header --><config><entry key='key'>1</entry></config><!-- footer -->"),
])
def test_empty_result_keeps_document_boundaries(tmp_path, parser, suffix, text):
    path = tmp_path / f"settings{suffix}"
    path.write_text(text)
    parser.save(path, {})
    assert "header" in path.read_text()
    assert "footer" in path.read_text()
    assert parser.load(path) == {}


def test_save_preserves_latest_comments_but_memory_values_are_authoritative(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("key: old # original\n")
    conf = Confease(path)
    conf.set("key", "memory")
    path.write_text("key: external # latest\nextra: external\n")
    conf.save()
    assert "# latest" in path.read_text()
    assert Yaml.load(path) == {"key": "memory"}


def test_origin_filter_removes_attached_comments(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("# header\nkeep: user\n# origin comment\noverride: file # inline\n# footer\n")
    conf = Confease(path)
    conf._set_item("override", "cli", CLI)
    conf.save()
    assert "origin comment" not in path.read_text()
    assert "# inline" not in path.read_text()
    assert "# header" in path.read_text() and "# footer" in path.read_text()
    conf.save(user_only=False)
    assert Yaml.load(path) == {"keep": "user", "override": "cli"}


def test_invalid_destination_and_serialization_failures_preserve_state(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("key: old\n")
    conf = Confease(path)
    conf.set("key", "memory")
    previous = list(conf._entries)
    path.write_text("key: [\n")
    with pytest.raises(yaml.YAMLError):
        conf.save()
    assert path.read_text() == "key: [\n"
    assert conf._entries == previous
    toml = tmp_path / "settings.toml"
    toml.write_text("key = 1 # comment\n")
    with pytest.raises(ConvertError):
        Toml.save(toml, {"key": None})
    assert toml.read_text() == "key = 1 # comment\n"
    assert list(tmp_path.glob(".*")) == []


def test_replacement_failure_preserves_original_and_cleans_draft(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"key": "old"}')

    def fail(self, target):
        raise OSError("replacement failed")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="replacement failed"):
        Json.save(path, {"key": "new"})
    assert path.read_text() == '{"key": "old"}'
    assert list(tmp_path.glob(".*")) == []


def test_candidate_semantic_validation_rejects_type_loss(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"key": 1}')
    monkeypatch.setattr("confease.documents.render_document", lambda *args: '{"key": true}')
    with pytest.raises(ValueError, match="faithfully"):
        Json.save(path, {"key": 1})
    assert path.read_text() == '{"key": 1}'
    assert list(tmp_path.glob(".*")) == []


def test_unknown_adapter_rejected():
    from confease import Parser

    with pytest.raises(ValueError, match="adapter"):
        render_document(Parser, "", {}, {})


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "# header\nkeep: 1\n# section leading\nsection: # section inline\n  # leaf leading\n  leaf: 2 # leaf inline\n# footer\n"),
    (Toml, ".toml", "# header\nkeep=1\n# section leading\n[section] # section inline\n# leaf leading\nleaf=2 # leaf inline\n# footer\n"),
    (Ini, ".ini", "; header\n[DEFAULT]\nkeep=1\n; section leading\n[section] # section inline\n# leaf leading\nleaf=2 # leaf inline\n; footer\n"),
    (Xml, ".xml", "<!-- header --><config><entry key='keep'>1</entry>\n<!-- section leading -->\n<section name='section'><!-- leaf leading --><entry key='leaf'>2</entry></section>\n<!-- footer -->\n</config>"),
])
def test_deleted_section_does_not_keep_descendant_comments(tmp_path, parser, suffix, text):
    path = tmp_path / f"settings{suffix}"
    path.write_text(text)
    parser.save(path, {"keep": 1})
    output = path.read_text()
    assert "header" in output and "footer" in output
    assert "section leading" not in output
    assert "section inline" not in output
    assert "leaf leading" not in output
    assert "leaf inline" not in output
    assert parser.load(path) == {"keep": 1}


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "database.host: local # leaf inline\n"),
    (Toml, ".toml", '"database.host" = "local" # leaf inline\n'),
    (Ini, ".ini", '[DEFAULT]\ndatabase.host = local # leaf inline\n'),
    (Xml, ".xml", '<config><entry key="database.host">local</entry> <!-- leaf inline --></config>'),
])
def test_existing_dotted_spelling_keeps_leaf_comments(tmp_path, parser, suffix, text):
    path = tmp_path / f"settings{suffix}"
    path.write_text(text)
    conf = Confease(path, parser=parser)
    conf.set("database.host", "remote")
    conf.save()
    assert "leaf inline" in path.read_text()
    assert Confease(path, parser=parser)["database.host"] == "remote"
