"""Snapshots must retain bytes and allocate names without destructive races."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from confease.backups import create_backup, latest_backup


@pytest.fixture
def frozen_time(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 7, 14, 30, 52)

    monkeypatch.setattr("confease.backups.datetime", Clock)


@pytest.mark.parametrize("name,expected", [
    ("settings.yaml", "settings-20261007-143052.yaml.bkp"),
    ("settings", "settings-20261007-143052.bkp"),
    ("app.settings.toml", "app.settings-20261007-143052.toml.bkp"),
])
def test_names_exact_bytes_and_permissions(tmp_path, frozen_time, name, expected):
    target = tmp_path / name
    content = b"# header\r\nkey: old # inline\r\n\xff"
    target.write_bytes(content)
    target.chmod(0o600)
    first = create_backup(target)
    assert first.name == expected
    assert first.read_bytes() == content
    assert first.stat().st_mode & 0o777 == 0o600
    target.write_bytes(b"new")
    second = create_backup(target)
    assert second.name == expected.replace("143052", "143052-001")
    assert first.read_bytes() == content
    assert second.read_bytes() == b"new"


def test_concurrent_allocations_do_not_overwrite(tmp_path, frozen_time):
    target = tmp_path / "settings.yaml"
    target.write_bytes(b"key: original\r\n")
    occupied = tmp_path / "settings-20261007-143052.yaml.bkp"
    occupied.write_bytes(b"older")
    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(executor.map(lambda _: create_backup(target), range(12)))
    assert len(set(paths)) == 12
    assert occupied.read_bytes() == b"older"
    assert all(path.read_bytes() == target.read_bytes() for path in paths)
    assert latest_backup(target).name == "settings-20261007-143052-012.yaml.bkp"


def test_failed_copy_removes_partial_backup(tmp_path, monkeypatch, frozen_time):
    target = tmp_path / "settings.yaml"
    target.write_bytes(b"original")

    def fail(source, output):
        output.write(b"partial")
        raise OSError("copy failed")

    monkeypatch.setattr("confease.backups.shutil.copyfileobj", fail)
    with pytest.raises(OSError, match="copy failed"):
        create_backup(target)
    assert list(tmp_path.iterdir()) == [target]
    assert target.read_bytes() == b"original"


def test_discovery_filters_and_orders_names(tmp_path):
    target = tmp_path / "app.settings.yaml"
    names = [
        "app.settings-20261006-143052.yaml.bkp",
        "app.settings-20261007-143052.yaml.bkp",
        "app.settings-20261007-143052-009.yaml.bkp",
        "app.settings-20261007-143052-010.yaml.bkp",
        "appXsettings-20271007-143052.yaml.bkp",
        "other-20271007-143052.yaml.bkp",
        "app.settings-20261307-143052.yaml.bkp",
        "app.settings-20261007-253052.yaml.bkp",
        "app.settings-20271007-143052-000.yaml.bkp",
        "app.settings-20271007-143052-0001.yaml.bkp",
        "app.settings-20271007-143052.json.bkp",
        "app.settings-20271007-143052.yaml.bkp.extra",
    ]
    for name in names:
        (tmp_path / name).write_bytes(b"key: 1")
    (tmp_path / "app.settings-20281007-143052.yaml.bkp").mkdir()
    os.utime(tmp_path / names[0], (2000000000, 2000000000))
    os.utime(tmp_path / names[3], (1, 1))
    assert latest_backup(target).name == names[3]


def test_missing_target_and_backups(tmp_path):
    target = tmp_path / "absent" / "settings.yaml"
    assert create_backup(target) is None
    with pytest.raises(FileNotFoundError, match="No matching backup"):
        latest_backup(target)
