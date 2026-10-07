import pytest
from yaml.representer import RepresenterError

from confease import Confease, Yaml


def test_delete_null_leaf_and_section(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("missing: null\ndatabase:\n  host: local\n  port: 5432\nother: 1\n")
    conf = Confease(path)
    assert conf.delete("missing") is True
    assert conf.delete("missing") is False
    assert conf.delete("database.host") is True
    assert conf["database"] == {"port": 5432}
    assert conf.delete("database") is True
    conf.save()
    assert Yaml.load(path) == {"other": 1}


def test_delete_default_does_not_create_tombstone(tmp_path):
    conf = Confease(tmp_path / "settings.yaml", key="fallback")
    assert conf.delete("key") is True
    assert conf.get_item("key") is None
    conf.reset()
    assert conf["key"] == "fallback"
    assert not (tmp_path / "settings.yaml").exists()


def test_delete_autosaves_current_document_and_comments(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("# header\nkey: null\nother: 1 # original\n")
    conf = Confease(path, reload=True)
    path.write_text("# header\nkey: null\nother: 2 # latest\n")
    assert conf.delete("key") is True
    assert Yaml.load(path) == {"other": 2}
    assert "# latest" in path.read_text()


def test_failed_autodelete_restores_entries(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    path.write_text("key: 1\n")
    conf = Confease(path, reload=True)

    def fail(*args):
        raise OSError("write failed")

    monkeypatch.setattr(conf, "save", fail)
    with pytest.raises(OSError, match="write failed"):
        conf.delete("key")
    assert conf.get_item("key").value == 1
    assert path.read_text() == "key: 1\n"


def test_failed_initial_save_does_not_initialize_live_entries(tmp_path):
    conf = Confease(tmp_path / "settings.yaml", value=object())
    with pytest.raises(RepresenterError):
        conf.save(user_only=False)
    assert conf._entries is None
    assert not (tmp_path / "settings.yaml").exists()
