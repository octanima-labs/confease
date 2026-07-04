from argparse import Namespace

import pytest

from confease import CLI, DEF, ENV, SYS, USR, Confease, Confitem


def test_reload_files_infers_parser_and_marks_origins(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    user_path = home / "conf.yaml"
    system_path = tmp_path / "system.yaml"
    user_path.write_text("USER_VALUE: user\n")
    system_path.write_text("SYSTEM_VALUE: system\n")
    conf = Confease()

    conf.reload_files(user_path, system_path)

    assert conf.get_item("USER_VALUE") == Confitem("USER_VALUE", "user", USR)
    assert conf.get_item("SYSTEM_VALUE") == Confitem("SYSTEM_VALUE", "system", SYS)


def test_reload_files_respects_default_system_over_user_preference(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    system_path = tmp_path / "system.yaml"
    user_path = home / "conf.yaml"
    system_path.write_text("KEY: system\n")
    user_path.write_text("KEY: user\n")
    conf = Confease()

    conf.reload_files(system_path, user_path)

    assert conf.get_item("KEY") == Confitem("KEY", "system", SYS)


def test_reload_files_raises_for_missing_and_unsupported_files(tmp_path):
    conf = Confease()

    with pytest.raises(FileNotFoundError):
        conf.reload_files(tmp_path / "missing.yaml")

    path = tmp_path / "conf.txt"
    path.write_text("KEY=value\n")
    with pytest.raises(ValueError, match="Unknown parser"):
        conf.reload_files(path)


def test_reload_env_loads_known_keys_only_and_parses_yaml_values(monkeypatch):
    monkeypatch.setenv("PORT", "5432")
    monkeypatch.setenv("ENABLED", "true")
    monkeypatch.setenv("UNKNOWN", "ignored")
    conf = Confease(PORT=1, ENABLED=False)

    conf.reload_env()

    assert conf.get_item("PORT") == Confitem("PORT", 5432, ENV)
    assert conf.get_item("ENABLED") == Confitem("ENABLED", True, ENV)
    assert conf.get("UNKNOWN") is None


def test_reload_cli_skips_none_values_and_flattens_nested_values():
    conf = Confease(OPTION="default")

    conf.reload_cli(Namespace(OPTION=None, OTHER="cli", database={"host": "localhost"}))

    assert conf.get_item("OPTION") == Confitem("OPTION", "default", DEF)
    assert conf.get_item("OTHER") == Confitem("OTHER", "cli", CLI)
    assert conf.get_item("database.host") == Confitem("database.host", "localhost", CLI)


def test_load_sources_accepts_readme_style_paths_and_cli_wins_by_default(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: file\n")
    conf = Confease(KEY="default")

    conf.load_sources(Namespace(KEY="cli"), path)

    assert conf.get_item("KEY") == Confitem("KEY", "cli", CLI)


def test_load_sources_custom_preference_can_make_env_win(monkeypatch):
    monkeypatch.setenv("KEY", "env")
    conf = Confease(KEY="default")

    conf.load_sources(Namespace(KEY="cli"), preference=[ENV, CLI, DEF])

    assert conf.get_item("KEY") == Confitem("KEY", "env", ENV)


def test_load_sources_keeps_existing_preference_when_not_overridden(monkeypatch):
    monkeypatch.setenv("KEY", "env")
    conf = Confease(KEY="default", preference=[DEF, CLI, ENV])

    conf.load_sources(Namespace(KEY="cli"))

    assert conf.preference == [DEF, CLI, ENV, SYS, USR]
    assert conf.get_item("KEY") == Confitem("KEY", "default", DEF)


def test_load_sources_applies_default_precedence_across_all_origins(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("KEY", "env")
    system_path = tmp_path / "system.yaml"
    user_path = home / "conf.yaml"
    system_path.write_text("KEY: system\n")
    user_path.write_text("KEY: user\n")
    conf = Confease(KEY="default")

    conf.load_sources(Namespace(KEY="cli"), system_path, user_path)

    assert conf.get_item("KEY") == Confitem("KEY", "cli", CLI)


def test_reload_files_raises_when_source_keys_collide_with_existing_sections(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("database: sqlite\n")
    conf = Confease(**{"database": {"host": "localhost"}})

    with pytest.raises(ValueError, match="collides"):
        conf.reload_files(path)


def test_indexed_access_uses_reload_enabled_file_reads(tmp_path):
    path = tmp_path / "conf.yaml"
    path.write_text("KEY: initial\n")
    conf = Confease(path, reload=True)

    path.write_text("KEY: updated\n")

    assert conf["KEY"] == "updated"
