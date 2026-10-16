"""One operator run reports how many entities this epoch added, changed, or removed."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tests.support import EPOCH, install_homes, make_job, put_entity, snapshot

from docorder.core.epoch_diff import EpochEntityDiff, format_diff_table
from docorder.core.runner import execute
from docorder.core.storage import EpochStore

pytestmark = pytest.mark.usefixtures("homes")


def _table(*lines: str) -> str:
    return f"epoch {EPOCH}\n" + "\n".join(lines)


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "homes"
    install_homes(root)
    monkeypatch.setenv("DOCORDER_HOMES", str(root))
    return root


def test_finish_counts_added_modified_and_deleted_entities(tmp_path: Path) -> None:
    """Names new after the run are added, missing names are deleted, and a different body or user tag is modified."""
    store = EpochStore(tmp_path / "prompt", EPOCH)
    put_entity(store.epoch_dir, "keep", "same", {"n": 1})
    put_entity(store.epoch_dir, "edit", "old")
    put_entity(store.epoch_dir, "drop", "gone")
    diff = EpochEntityDiff(store)

    shutil.rmtree(store.epoch_dir / "drop")
    put_entity(store.epoch_dir, "edit", "new", {"n": 2})
    put_entity(store.epoch_dir, "fresh", "born")
    diff.finish()

    assert diff.added == frozenset({"fresh"})
    assert diff.modified == frozenset({"edit"})
    assert diff.deleted == frozenset({"drop"})
    assert format_diff_table(EPOCH, [("documentation", diff)]) == _table(
        "┌───────────────┬───────┬──────────┬─────────┐",
        "│ operator      │ added │ modified │ deleted │",
        "├───────────────┼───────┼──────────┼─────────┤",
        "│ documentation │     1 │        1 │       1 │",
        "└───────────────┴───────┴──────────┴─────────┘",
    )


def test_upstream_snapshot_alone_does_not_count_as_modified(tmp_path: Path) -> None:
    """Rewriting only the upstream snapshot leaves the entity unmodified."""
    store = EpochStore(tmp_path / "prompt", EPOCH)
    put_entity(
        store.epoch_dir,
        "orders",
        "body",
        {"k": 1},
        upstream=snapshot("tables", "orders", "old"),
    )
    diff = EpochEntityDiff(store)

    put_entity(
        store.epoch_dir,
        "orders",
        "body",
        {"k": 1},
        upstream=snapshot("tables", "orders", "new"),
    )
    diff.finish()

    assert diff.added == frozenset()
    assert diff.modified == frozenset()
    assert diff.deleted == frozenset()
    assert format_diff_table(EPOCH, [("prompt", diff)]) == _table(
        "┌──────────┬───────┬──────────┬─────────┐",
        "│ operator │ added │ modified │ deleted │",
        "├──────────┼───────┼──────────┼─────────┤",
        "│ prompt   │     0 │        0 │       0 │",
        "└──────────┴───────┴──────────┴─────────┘",
    )


def test_run_reports_entities_added_changed_and_removed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """After the run, stderr shows one table of added, modified, and deleted counts."""
    root = tmp_path / "runs"
    execute(
        make_job(
            root,
            [
                {
                    "name": "tables",
                    "home": "fixed",
                    "config": {
                        "records": [
                            {"name": "orders", "data": "A", "tag": {}},
                            {"name": "users", "data": "B", "tag": {}},
                        ]
                    },
                },
                {"name": "prompt", "home": "copy", "upstream": "tables"},
                {"name": "result", "home": "publish", "upstream": "prompt"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    err = capsys.readouterr().err
    assert _table(
        "┌──────────┬───────┬──────────┬─────────┐",
        "│ operator │ added │ modified │ deleted │",
        "├──────────┼───────┼──────────┼─────────┤",
        "│ tables   │     2 │        0 │       0 │",
        "│ prompt   │     2 │        0 │       0 │",
        "│ result   │     2 │        0 │       0 │",
        "└──────────┴───────┴──────────┴─────────┘",
    ) in err

    execute(
        make_job(
            root,
            [
                {
                    "name": "tables",
                    "home": "fixed",
                    "config": {
                        "records": [
                            {"name": "orders", "data": "A2", "tag": {}},
                            {"name": "payments", "data": "C", "tag": {}},
                        ]
                    },
                },
                {"name": "prompt", "home": "copy", "upstream": "tables"},
                {"name": "result", "home": "publish", "upstream": "prompt"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    err = capsys.readouterr().err
    assert _table(
        "┌──────────┬───────┬──────────┬─────────┐",
        "│ operator │ added │ modified │ deleted │",
        "├──────────┼───────┼──────────┼─────────┤",
        "│ tables   │     1 │        1 │       1 │",
        "│ prompt   │     1 │        1 │       1 │",
        "│ result   │     1 │        1 │       1 │",
        "└──────────┴───────┴──────────┴─────────┘",
    ) in err


def test_output_counts_files_written_to_its_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Output counts result files, including when directory is not .job_result."""
    root = tmp_path / "runs"
    dest = tmp_path / "custom-out"
    records = [{"name": "orders", "data": "A", "tag": {}}]
    job = make_job(
        root,
        [
            {"name": "tables", "home": "fixed", "config": {"records": records}},
            {
                "name": "output",
                "home": "publish",
                "upstream": "tables",
                "config": {"directory": str(dest)},
            },
        ],
    )
    execute(job, EPOCH, start_from_scratch=True)
    err = capsys.readouterr().err
    assert (dest / "orders").read_text(encoding="utf-8") == "A"
    assert _table(
        "┌──────────┬───────┬──────────┬─────────┐",
        "│ operator │ added │ modified │ deleted │",
        "├──────────┼───────┼──────────┼─────────┤",
        "│ tables   │     1 │        0 │       0 │",
        "│ output   │     1 │        0 │       0 │",
        "└──────────┴───────┴──────────┴─────────┘",
    ) in err
    capsys.readouterr()

    execute(job, EPOCH, start_from_scratch=False)
    err = capsys.readouterr().err
    assert _table(
        "┌──────────┬───────┬──────────┬─────────┐",
        "│ operator │ added │ modified │ deleted │",
        "├──────────┼───────┼──────────┼─────────┤",
        "│ tables   │     0 │        0 │       0 │",
        "│ output   │     0 │        0 │       0 │",
        "└──────────┴───────┴──────────┴─────────┘",
    ) in err


def test_unchanged_rerun_reports_no_entity_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A second run that keeps every body and user tag reports zeros."""
    root = tmp_path / "runs"
    records = [
        {"name": "orders", "data": "A", "tag": {}},
        {"name": "users", "data": "B", "tag": {}},
    ]
    job = make_job(
        root,
        [
            {"name": "tables", "home": "fixed", "config": {"records": records}},
            {"name": "prompt", "home": "copy", "upstream": "tables"},
        ],
    )
    execute(job, EPOCH, start_from_scratch=True)
    capsys.readouterr()

    execute(job, EPOCH, start_from_scratch=False)
    err = capsys.readouterr().err
    assert _table(
        "┌──────────┬───────┬──────────┬─────────┐",
        "│ operator │ added │ modified │ deleted │",
        "├──────────┼───────┼──────────┼─────────┤",
        "│ tables   │     0 │        0 │       0 │",
        "│ prompt   │     0 │        0 │       0 │",
        "└──────────┴───────┴──────────┴─────────┘",
    ) in err


def test_downstream_keeps_a_zero_when_only_its_upstream_snapshot_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A copy that rewrites the same body and user tag is not a modification."""
    root = tmp_path / "runs"
    execute(
        make_job(
            root,
            [
                {
                    "name": "tables",
                    "home": "fixed",
                    "config": {"records": [{"name": "orders", "data": "A", "tag": {}}]},
                },
                {"name": "prompt", "home": "copy", "upstream": "tables"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    capsys.readouterr()

    execute(
        make_job(
            root,
            [
                {
                    "name": "tables",
                    "home": "fixed",
                    "config": {
                        "records": [{"name": "orders", "data": "A", "tag": {"owner": "ada"}}]
                    },
                },
                {"name": "prompt", "home": "copy", "upstream": "tables"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    err = capsys.readouterr().err
    assert _table(
        "┌──────────┬───────┬──────────┬─────────┐",
        "│ operator │ added │ modified │ deleted │",
        "├──────────┼───────┼──────────┼─────────┤",
        "│ tables   │     0 │        1 │       0 │",
        "│ prompt   │     0 │        0 │       0 │",
        "└──────────┴───────┴──────────┴─────────┘",
    ) in err
