import pytest
import yaml

from confease import DEF, USR, Confease, Confitem


def test_template_defaults_do_not_create_target(tmp_path):
    template = tmp_path / "template.yaml"
    template.write_text("KEY: default\ndatabase:\n  port: 5432\n")
    path = tmp_path / "missing.yaml"
    conf = Confease(path, template=template)

    assert conf.get_item("KEY") == Confitem("KEY", "default", DEF)
    assert conf.get("database.port") == 5432
    conf.set("USER", "value")
    assert not path.exists()
    conf.save()
    assert yaml.safe_load(path.read_text()) == {"USER": "value"}


def test_existing_target_overrides_template_and_keeps_fallbacks(tmp_path):
    template = tmp_path / "template.yaml"
    template.write_text("KEY: default\nOTHER: fallback\n")
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: user\n")
    conf = Confease(path, template=template)

    assert conf.get_item("KEY") == Confitem("KEY", "user", USR)
    assert conf.get_item("OTHER") == Confitem("OTHER", "fallback", DEF)
    assert path.read_text() == "KEY: user\n"


@pytest.mark.parametrize("existing", [False, True])
def test_reset_restores_exact_template_bytes(tmp_path, existing):
    template = tmp_path / "template.yaml"
    content = b'# Defaults\r\nKEY: "default" # inline\r\ndatabase:\r\n  port: 5432\r\n'
    template.write_bytes(content)
    path = tmp_path / "nested" / "conf.yaml"
    if existing:
        path.parent.mkdir()
        path.write_text("KEY: original\n")
    conf = Confease(path, template=template)
    conf.set("EXTRA", "unsaved")

    conf.reset()

    assert path.read_bytes() == content
    assert conf.get_item("KEY") == Confitem("KEY", "default", USR)
    assert conf.get("EXTRA") is None
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("content", [None, "KEY: [\n", "- invalid\n", "a.b.c: invalid\n"])
def test_failed_template_validation_preserves_file_and_memory(tmp_path, content):
    template = tmp_path / "template.yaml"
    template.write_text("KEY: default\n")
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: original\n")
    conf = Confease(path, template=template)
    previous = list(conf._entries)
    if content is None:
        template.unlink()
    else:
        template.write_text(content)

    with pytest.raises((FileNotFoundError, ValueError, yaml.YAMLError)):
        conf.reset()

    assert path.read_text() == "KEY: original\n"
    assert conf._entries == previous


def test_copy_failure_preserves_file_and_memory(tmp_path, monkeypatch):
    template = tmp_path / "template.yaml"
    template.write_text("KEY: default\n")
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: original\n")
    conf = Confease(path, template=template)
    previous = list(conf._entries)

    def fail_copy(source, destination):
        destination.write_text("partial")
        raise OSError("copy failed")

    monkeypatch.setattr("confease.model.shutil.copyfile", fail_copy)
    with pytest.raises(OSError, match="copy failed"):
        conf.reset()

    assert path.read_text() == "KEY: original\n"
    assert conf._entries == previous
    assert sorted(tmp_path.iterdir()) == sorted([path, template])


def test_runtime_only_template_defaults_and_reset(tmp_path):
    template = tmp_path / "template.yaml"
    template.write_text("KEY: default\n")
    conf = Confease(template=template)
    assert conf.get("KEY") == "default"
    previous = list(conf._entries)
    with pytest.raises(FileNotFoundError, match="path"):
        conf.reset()
    assert conf._entries == previous


def test_items_default_reset_does_not_write_file(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: persisted\n")
    conf = Confease(path, items={"KEY": "default"})
    conf.reset()
    assert conf.get_item("KEY") == Confitem("KEY", "default", DEF)
    assert path.read_text() == "KEY: persisted\n"


def test_reset_reads_updated_template_without_old_default_collisions(tmp_path):
    template = tmp_path / "template.yaml"
    template.write_text("database:\n  host: default\n")
    path = tmp_path / "conf.yaml"
    conf = Confease(path, template=template)
    template.write_text("database: changed\n")
    conf.reset()
    assert conf.get("database") == "changed"
