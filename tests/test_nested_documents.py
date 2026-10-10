"""Deep path reconciliation retains presentation and comment ownership."""

import pytest

from confease import Confease, Ini, Toml, Xml, Yaml


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "# header\nkey: # ancestor\n  subkey:\n    two: 2 # sibling\n    # subtree leading\n    subsubkey: # subtree inline\n      # leaf leading\n      three: 3 # leaf inline\n# footer\n"),
    (Toml, ".toml", "# header\n[key] # ancestor\n[key.subkey]\ntwo = 2 # sibling\n# subtree leading\n[key.subkey.subsubkey] # subtree inline\n# leaf leading\nthree = 3 # leaf inline\n# footer\n"),
    (Ini, ".ini", "; header\n[key] # ancestor\n[key.subkey]\ntwo = 2 # sibling\n# subtree leading\n[key.subkey.subsubkey] # subtree inline\n# leaf leading\nthree = 3 # leaf inline\n; footer\n"),
    (Xml, ".xml", "<!-- header --><config>\n<section name='key'> <!-- ancestor -->\n<section name='subkey'>\n<entry key='two'>2</entry> <!-- sibling -->\n<!-- subtree leading -->\n<section name='subsubkey'> <!-- subtree inline -->\n<!-- leaf leading -->\n<entry key='three'>3</entry> <!-- leaf inline -->\n</section>\n</section>\n</section>\n<!-- footer -->\n</config>"),
])
def test_deep_update_and_subtree_deletion_comment_ownership(tmp_path, parser, suffix, text):
    path = tmp_path / f"config{suffix}"
    path.write_text(text)
    conf = Confease(path, parser=parser)
    conf.set("key.subkey.subsubkey.three", 4)
    conf.save()
    for comment in ["header", "ancestor", "sibling", "subtree leading", "subtree inline",
                    "leaf leading", "leaf inline", "footer"]:
        assert path.read_text().count(comment) == 1
    assert parser.load(path) == {"key": {"subkey": {"two": 2, "subsubkey": {"three": 4}}}}
    assert conf.delete("key.subkey.subsubkey") is True
    conf.save()
    for comment in ["header", "ancestor", "sibling", "footer"]:
        assert path.read_text().count(comment) == 1
    for comment in ["subtree leading", "subtree inline", "leaf leading", "leaf inline"]:
        assert comment not in path.read_text()
    assert parser.load(path) == {"key": {"subkey": {"two": 2}}}


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "# header\na.b.c: 1 # dotted root\na:\n  b:\n    other.deep: 2 # dotted child\n    sibling: 3 # sibling\n# footer\n"),
    (Toml, ".toml", '# header\n"a.b.c" = 1 # dotted root\n[a.b]\n"other.deep" = 2 # dotted child\nsibling = 3 # sibling\n# footer\n'),
    (Ini, ".ini", "# header\n[DEFAULT]\na.b.c = 1 # dotted root\n[a.b]\nother.deep = 2 # dotted child\nsibling = 3 # sibling\n# footer\n"),
    (Xml, ".xml", "<!-- header --><config>\n<entry key='a.b.c'>1</entry> <!-- dotted root -->\n<section name='a'><section name='b'>\n<entry key='other.deep'>2</entry> <!-- dotted child -->\n<entry key='sibling'>3</entry> <!-- sibling -->\n</section></section>\n<!-- footer -->\n</config>"),
])
def test_mixed_dotted_and_native_paths_keep_comments(tmp_path, parser, suffix, text):
    path = tmp_path / f"config{suffix}"
    path.write_text(text)
    conf = Confease(path, parser=parser)
    conf.set("a.b.c", 4)
    conf.set("a.b.other.deep", 5)
    conf.save()
    for comment in ["header", "dotted root", "dotted child", "sibling", "footer"]:
        marker = f"<!-- {comment} -->" if parser is Xml else f"# {comment}"
        assert path.read_text().count(marker) == 1
    assert parser.load(path) == {"a": {"b": {"c": 4, "other": {"deep": 5}, "sibling": 3}}}
    conf.delete("a.b.other")
    conf.save()
    assert "dotted child" not in path.read_text()
    assert "dotted root" in path.read_text() and "sibling" in path.read_text()


@pytest.mark.parametrize("parser,suffix,text", [
    (Yaml, ".yaml", "# header\na.b: # empty section\n  c: {} # empty leaf\n# footer\n"),
    (Toml, ".toml", '# header\n["a.b"] # empty section\n["a.b".c] # empty leaf\n# footer\n'),
    (Xml, ".xml", "<!-- header --><config>\n<section name='a.b'> <!-- empty section -->\n<section name='c'/> <!-- empty leaf -->\n</section>\n<!-- footer -->\n</config>"),
])
def test_dotted_mapping_nodes_and_empty_descendants_survive(tmp_path, parser, suffix, text):
    path = tmp_path / f"config{suffix}"
    path.write_text(text)
    conf = Confease(path, parser=parser)
    conf.save()
    assert parser.load(path) == {"a": {"b": {"c": {}}}}
    assert "empty leaf" in path.read_text()
    assert "empty section" in path.read_text()


def test_existing_empty_ini_header_keeps_comments_and_deletes_cleanly(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("# header\n[DEFAULT]\nkeep = 1 # sibling\n# empty leading\n[a.b.c] # empty inline\n# footer\n")
    conf = Confease(path, parser=Ini)
    conf.save()
    assert Ini.load(path) == {"keep": 1, "a": {"b": {"c": {}}}}
    assert "[a.b.c] # empty inline" in path.read_text()
    assert "# empty leading" in path.read_text()
    assert conf.delete("a.b.c") is True
    conf.save()
    assert Ini.load(path) == {"keep": 1}
    assert "empty inline" not in path.read_text() and "empty leading" not in path.read_text()
    assert "header" in path.read_text() and "footer" in path.read_text()


def test_deep_save_uses_latest_comments_without_merging_external_values(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("a:\n  b:\n    c: 1 # original\n")
    conf = Confease(path)
    conf.set("a.b.c", 2)
    path.write_text("a:\n  b:\n    c: 99 # latest\n    external: 3\n")
    conf.save()
    assert "latest" in path.read_text()
    assert Yaml.load(path) == {"a": {"b": {"c": 2}}}
