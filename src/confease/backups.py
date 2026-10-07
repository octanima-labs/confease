"""Exact-byte sibling snapshots and filename-based backup discovery."""

import re
import shutil
import stat
from datetime import datetime
from pathlib import Path


def create_backup(target: Path) -> Path | None:
    """Copy an existing target exclusively; never overwrite a prior snapshot."""
    if not target.exists():
        return None
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    sequence = 0
    while True:
        extra = f"-{sequence:03d}" if sequence else ""
        backup = target.with_name(f"{target.stem}-{timestamp}{extra}{target.suffix}.bkp")
        try:
            output = backup.open("xb")
        except FileExistsError:
            sequence += 1
            continue
        try:
            with output, target.open("rb") as source:
                shutil.copyfileobj(source, output)
            backup.chmod(stat.S_IMODE(target.stat().st_mode))
        except BaseException:
            backup.unlink(missing_ok=True)
            raise
        return backup


def latest_backup(target: Path) -> Path:
    """Select the newest valid matching filename, independent of metadata."""
    pattern = re.compile(
        rf"{re.escape(target.stem)}-(\d{{8}}-\d{{6}})(?:-(\d{{3,}}))?"
        rf"{re.escape(target.suffix)}\.bkp"
    )
    candidates: list[tuple[datetime, int, Path]] = []
    if target.parent.exists():
        for path in target.parent.iterdir():
            match = pattern.fullmatch(path.name)
            if match is None or not path.is_file():
                continue
            try:
                # Names encode local wall time, not an offset-bearing instant.
                timestamp = datetime.strptime(match[1], "%Y%m%d-%H%M%S")  # noqa: DTZ007
            except ValueError:
                continue
            sequence = int(match[2]) if match[2] else 0
            if match[2] is not None and match[2] != f"{sequence:03d}":
                continue
            if match[2] is not None and sequence == 0:
                continue
            candidates.append((timestamp, sequence, path))
    if not candidates:
        raise FileNotFoundError(f"No matching backup for {target}")
    return max(candidates, key=lambda item: item[:2])[2]
