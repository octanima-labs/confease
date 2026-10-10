import pytest

from confease import CLI, DEF, ENV, ORIGINS, USR, Confease, Confitem


def test_preference_defaults_to_origin_order():
    conf = Confease()

    assert conf.preference == ORIGINS


def test_preference_accepts_subset_and_appends_omitted_origins():
    conf = Confease(preference=[USR, DEF])

    assert conf.preference == [USR, DEF, CLI, ENV, "system"]


def test_preference_rejects_unknown_origin():
    with pytest.raises(ValueError, match="Unknown origin"):
        Confease(preference=["unknown"])


def test_preference_rejects_duplicate_origin():
    with pytest.raises(ValueError, match="Duplicate origin"):
        Confease(preference=[CLI, CLI])


def test_get_returns_default_for_missing_key():
    conf = Confease(items={"EXISTING": "value"})

    assert conf.get("MISSING") is None
    assert conf.get("MISSING", default="fallback") == "fallback"


def test_get_casts_values_and_keeps_string_on_cast_failure():
    conf = Confease(items={"NUMBER": 1312})

    assert conf.get("NUMBER") == 1312
    assert conf.get("NUMBER", cast=int) == 1312
    assert conf.get("NUMBER", cast=float) == 1312.0
    assert conf.get("NUMBER", cast=dict) == 1312


def test_get_item_returns_confitem():
    conf = Confease(items={"KEY": "value"})

    item = conf.get_item("KEY")

    assert item == Confitem("KEY", "value", DEF)


def test_confitem_rejects_unknown_origins():
    with pytest.raises(ValueError, match="Unknown origin"):
        Confitem("KEY", "value", "unknown")


def test_confitem_string_equality_repr_and_str():
    item = Confitem("KEY", 1312, USR)

    assert item == "KEY"
    assert item != "OTHER"
    assert item != object()
    assert repr(item) == "Confitem<KEY, 1312, user>"
    assert str(item) == "1312"


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


def test_nested_defaults_support_dotted_and_section_access():
    conf = Confease(items={"database": {"host": "localhost", "port": 5432}})

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


def test_indexed_access_returns_values_and_none_for_missing_keys():
    conf = Confease(items={"KEY": "value"})

    assert conf["KEY"] == "value"
    assert conf["MISSING"] is None


def test_indexed_assignment_mirrors_set_behavior():
    conf = Confease()

    conf["KEY"] = 1
    assert conf.get_item("KEY") == Confitem("KEY", 1, USR)

    conf["KEY"] = 2
    assert conf.get_item("KEY") == Confitem("KEY", 2, USR)


def test_indexed_assignment_supports_nested_dict_values():
    conf = Confease()

    conf["database"] = {"host": "localhost", "port": 5432}

    assert conf.get_item("database.host") == Confitem("database.host", "localhost", USR)
    assert conf.get_item("database.port") == Confitem("database.port", 5432, USR)


def test_indexed_access_supports_dotted_and_section_reads():
    conf = Confease(items={"database": {"host": "localhost", "port": 5432}})

    assert conf["database.host"] == "localhost"
    assert conf["database"] == {"host": "localhost", "port": 5432}
    assert conf["database"]["host"] == "localhost"


def test_indexed_section_reads_return_plain_dicts_with_key_errors():
    conf = Confease(items={"database": {"host": "localhost"}})

    with pytest.raises(KeyError):
        conf["database"]["missing"]


def test_scalar_and_nested_key_collisions_raise_errors():
    conf = Confease()

    conf.set("database.host", "localhost")
    with pytest.raises(ValueError, match="collides"):
        conf.set("database", "sqlite")

    other = Confease()
    other.set("database", "sqlite")
    with pytest.raises(ValueError, match="collides"):
        other.set("database.host", "localhost")


def test_nested_keys_support_arbitrary_depth():
    conf = Confease()

    conf.set("a.b.c", "value")
    conf.set("a", {"b": {"d": "sibling"}})
    assert conf["a.b"] == {"c": "value", "d": "sibling"}
    assert conf["a"]["b"]["c"] == "value"
