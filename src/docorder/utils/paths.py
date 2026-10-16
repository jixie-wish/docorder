"""Locate bundled and user-supplied operator homes."""

from __future__ import annotations

import os
from pathlib import Path


def bundled_homes_dir() -> Path:
    """Homes shipped inside the installed package, at ``docorder/homes``."""
    return Path(__file__).resolve().parents[1] / "homes"


def home_search_path() -> list[Path]:
    """Directories from ``DOCORDER_HOMES``, then ``src/docorder/homes`` when that directory exists.

    ``DOCORDER_HOMES`` is a path-separator list. A home found earlier wins.
    Homes may sit directly in a directory or under a category subdirectory.
    """
    directories: list[Path] = []
    raw = os.environ.get("DOCORDER_HOMES", "")
    for part in raw.split(os.pathsep):
        if part.strip():
            directories.append(Path(part).expanduser())
    directories.append(bundled_homes_dir())
    return directories


def home_path(name: str) -> Path:
    """Find ``name`` directly under a search root, or one category directory down."""
    searched = home_search_path()
    for directory in searched:
        found = _find_home(directory, name)
        if found is not None:
            return found
    listed = ", ".join(str(directory) for directory in searched)
    raise FileNotFoundError(f"operator home {name!r} not found in: {listed}")


def _find_home(directory: Path, name: str) -> Path | None:
    direct = directory / name
    if (direct / "props.json").is_file():
        return direct
    if not directory.is_dir():
        return None
    for category in sorted(directory.iterdir()):
        if not category.is_dir() or category.name.startswith((".", "_")):
            continue
        nested = category / name
        if (nested / "props.json").is_file():
            return nested
    return None
