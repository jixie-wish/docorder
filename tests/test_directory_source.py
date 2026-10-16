"""DirectorySource reads entity directories, not loose files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.support import EPOCH, entity_text, make_job, put_entity, read_json

from docorder.core.entity import TAG_FILE
from docorder.core.runner import execute
from docorder.utils.errors import FatalError

pytestmark = pytest.mark.usefixtures("homes")


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from tests.support import install_homes

    root = tmp_path / "homes"
    install_homes(root)
    monkeypatch.setenv("DOCORDER_HOMES", str(root))
    return root


def _write_home(homes: Path, name: str, class_path: str, extra: dict | None = None) -> None:
    home = homes / name
    home.mkdir(parents=True, exist_ok=True)
    props = {
        "type": "source",
        "class": class_path,
        "retry": {"max_attempts": 1, "backoff_seconds": 0},
    }
    if extra:
        props.update(extra)
    (home / "props.json").write_text(json.dumps(props), encoding="utf-8")


def test_directory_source_reads_entity_directories_and_skips_the_rest(
    tmp_path: Path, homes: Path
) -> None:
    """Each child with data and tag.json becomes an entity; files and incomplete dirs do not."""
    _write_home(
        homes,
        "dirsrc",
        "docorder.functions.impl.directory_source:DirectorySource",
    )
    incoming = tmp_path / "incoming"
    put_entity(incoming, "orders", "create table orders", {"table": "orders"})
    put_entity(incoming, "users", "create table users", {"table": "users"})
    (incoming / "loose.sql").write_text("not an entity", encoding="utf-8")
    incomplete = incoming / "draft"
    incomplete.mkdir()
    (incomplete / "data").write_text("no tag", encoding="utf-8")
    hidden = incoming / "_skip"
    hidden.mkdir()
    (hidden / "data").write_text("hidden", encoding="utf-8")
    (hidden / "tag.json").write_text("{}\n", encoding="utf-8")

    root = tmp_path / "runs"
    execute(
        make_job(
            root,
            [
                {
                    "name": "tables",
                    "home": "dirsrc",
                    "config": {"directory": str(incoming)},
                }
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )

    assert entity_text(root, "tables", "orders") == "create table orders"
    assert entity_text(root, "tables", "users") == "create table users"
    orders_tag = read_json(root / "tables" / EPOCH / "orders" / TAG_FILE)
    assert orders_tag["table"] == "orders"
    assert "current" not in orders_tag
    assert not (root / "tables" / EPOCH / "loose.sql").exists()
    assert not (root / "tables" / EPOCH / "draft").exists()
    assert not (root / "tables" / EPOCH / "_skip").exists()


def test_directory_source_rejects_tag_that_is_not_an_object(
    tmp_path: Path, homes: Path
) -> None:
    """A child directory with data but a non-object tag.json is not a usable entity."""
    _write_home(
        homes,
        "dirsrc",
        "docorder.functions.impl.directory_source:DirectorySource",
    )
    incoming = tmp_path / "incoming"
    put_entity(incoming, "orders", "body", {"table": "orders"})
    (incoming / "orders" / TAG_FILE).write_text("[]\n", encoding="utf-8")

    with pytest.raises(FatalError, match="tag.json"):
        execute(
            make_job(
                tmp_path / "runs",
                [
                    {
                        "name": "tables",
                        "home": "dirsrc",
                        "config": {"directory": str(incoming)},
                    }
                ],
            ),
            EPOCH,
            start_from_scratch=True,
        )
