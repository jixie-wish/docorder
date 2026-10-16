"""Status of a job output directory: epochs, consistency, and entity counts."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.support import install_homes, make_job, put_entity, snapshot

from docorder.cli import main
from docorder.cli.status import format_status, inspect_output
from docorder.core.entity import Upstream
from docorder.core.runner import OUTPUT_MARKER, execute


def _mark(stage: Path) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    (stage / OUTPUT_MARKER).write_text("docorder\n", encoding="utf-8")


def test_status_marks_epoch_inconsistent_when_upstream_hash_differs(tmp_path: Path) -> None:
    """A snapshot whose hash does not match the live upstream body makes the epoch inconsistent."""
    root = tmp_path / "runs"
    tables = root / "tables"
    prompt = root / "prompt"
    _mark(tables)
    _mark(prompt)
    put_entity(tables / "demo", "orders", "body")
    put_entity(tables / "demo", "users", "other")
    put_entity(
        prompt / "demo",
        "orders",
        "Note: body",
        upstream=snapshot("tables", "orders", "stale", epoch="demo"),
    )

    text = format_status(inspect_output(root))

    assert text == (
        "demo: inconsistent\n"
        "  prompt: 1\n"
        "  tables: 2\n"
    )


def test_status_marks_epoch_consistent_when_snapshot_matches_named_upstream(
    tmp_path: Path,
) -> None:
    """A map entity stays consistent when its one upstream matches, even if that stage has more entities."""
    root = tmp_path / "runs"
    tables = root / "tables"
    prompt = root / "prompt"
    _mark(tables)
    _mark(prompt)
    put_entity(tables / "demo", "orders", "body")
    put_entity(tables / "demo", "users", "other")
    put_entity(
        prompt / "demo",
        "orders",
        "Note: body",
        upstream=snapshot("tables", "orders", "body", epoch="demo"),
    )

    text = format_status(inspect_output(root))

    assert text == (
        "demo: consistent\n"
        "  prompt: 1\n"
        "  tables: 2\n"
    )


def test_status_counts_every_stage_for_every_epoch(tmp_path: Path) -> None:
    """Each epoch lists every stage, and a stage with no directory for that epoch counts as zero."""
    root = tmp_path / "runs"
    tables = root / "tables"
    prompt = root / "prompt"
    _mark(tables)
    _mark(prompt)
    put_entity(tables / "v1", "orders", "one")
    put_entity(
        prompt / "v1",
        "orders",
        "Note: one",
        upstream=snapshot("tables", "orders", "one", epoch="v1"),
    )
    put_entity(tables / "v2", "orders", "two")
    put_entity(tables / "v2", "users", "else")

    text = format_status(inspect_output(root))

    assert text == (
        "v1: consistent\n"
        "  prompt: 1\n"
        "  tables: 1\n"
        "v2: consistent\n"
        "  prompt: 0\n"
        "  tables: 2\n"
    )


def test_status_treats_source_entities_as_consistent(tmp_path: Path) -> None:
    """A source epoch has no upstream snapshot. Finished entities with a body are consistent."""
    root = tmp_path / "runs"
    tables = root / "tables"
    _mark(tables)
    put_entity(tables / "demo", "orders", "body")
    put_entity(tables / "demo", "users", "other")

    text = format_status(inspect_output(root))

    assert text == (
        "demo: consistent\n"
        "  tables: 2\n"
    )


def test_status_marks_epoch_inconsistent_when_entity_has_no_body(tmp_path: Path) -> None:
    """An allocated entity with only tag.json has not finished, so the epoch is inconsistent."""
    root = tmp_path / "runs"
    tables = root / "tables"
    _mark(tables)
    put_entity(tables / "demo", "orders", "body")
    empty = tables / "demo" / "users"
    empty.mkdir(parents=True)
    (empty / "tag.json").write_text("{}\n", encoding="utf-8")

    text = format_status(inspect_output(root))

    assert text == (
        "demo: inconsistent\n"
        "  tables: 2\n"
    )


def test_status_marks_reduce_inconsistent_when_one_upstream_is_missing(tmp_path: Path) -> None:
    """A snapshot that names two upstream entities is inconsistent when one of them is gone."""
    root = tmp_path / "runs"
    tables = root / "tables"
    index = root / "index"
    _mark(tables)
    _mark(index)
    put_entity(tables / "demo", "orders", "body")
    upstream = snapshot("tables", "orders", "body", epoch="demo")
    missing = snapshot("tables", "users", "other", epoch="demo")
    put_entity(
        index / "demo",
        "index",
        "orders",
        upstream=Upstream.of(*upstream.records, *missing.records),
    )

    text = format_status(inspect_output(root))

    assert text == (
        "demo: inconsistent\n"
        "  index: 1\n"
        "  tables: 1\n"
    )


def test_status_reads_epochs_written_by_a_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status uses the epoch directories a finished run left on disk."""
    homes = tmp_path / "homes"
    install_homes(homes)
    monkeypatch.setenv("DOCORDER_HOMES", str(homes))
    output = tmp_path / "runs"
    job = make_job(
        output,
        [
            {
                "name": "tables",
                "home": "fixed",
                "config": {
                    "records": [
                        {"name": "orders", "data": "body"},
                        {"name": "users", "data": "other"},
                    ]
                },
            },
            {"name": "prompt", "home": "copy", "upstream": "tables"},
        ],
    )
    execute(job, "demo", start_from_scratch=True)

    text = format_status(inspect_output(output))

    assert text == (
        "demo: consistent\n"
        "  prompt: 2\n"
        "  tables: 2\n"
    )


def test_status_reports_when_no_epoch_was_written(tmp_path: Path) -> None:
    """A job output with stages but no epoch directories says so."""
    root = tmp_path / "runs"
    _mark(root / "tables")

    assert format_status(inspect_output(root)) == "epochs: none\n"


def test_cli_status_prints_epochs_consistency_and_counts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`docorder status` prints the report for the job output directory."""
    root = tmp_path / "runs"
    tables = root / "tables"
    _mark(tables)
    put_entity(tables / "demo", "orders", "body")

    main(["status", str(root)])

    assert capsys.readouterr().out == (
        "demo: consistent\n"
        "  tables: 1\n"
    )


def test_cli_status_rejects_a_missing_output_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A path that is not a job output directory stops the command."""
    missing = tmp_path / "missing"
    with pytest.raises(SystemExit) as caught:
        main(["status", str(missing)])

    assert caught.value.code == 1
    assert capsys.readouterr().err == f"job output directory does not exist: {missing}\n"
