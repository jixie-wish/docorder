"""Each stage prints a progress bar for the work it does this run."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.support import EPOCH, install_homes, make_job

from docorder.core.runner import execute

pytestmark = pytest.mark.usefixtures("homes")


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "homes"
    install_homes(root)
    monkeypatch.setenv("DOCORDER_HOMES", str(root))
    return root


def test_source_map_and_output_stages_print_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Source, map, and output each print a bar named after the operator."""
    records = [
        {"name": "orders", "data": "A", "tag": {}},
        {"name": "users", "data": "B", "tag": {}},
    ]
    execute(
        make_job(
            tmp_path / "runs",
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {"name": "prompt", "home": "copy", "upstream": "tables"},
                {"name": "result", "home": "publish", "upstream": "prompt"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    err = capsys.readouterr().err
    assert "tables:" in err
    assert "prompt:" in err
    assert "result:" in err
    assert err.count("2/2") >= 2


def test_map_progress_counts_kept_entities_on_rerun(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A later run still shows the stage size, including entities that are kept."""
    records = [
        {"name": "orders", "data": "A", "tag": {}},
        {"name": "users", "data": "B", "tag": {}},
    ]
    job = make_job(
        tmp_path / "runs",
        [
            {"name": "tables", "home": "fixed", "config": {"records": records}},
            {"name": "prompt", "home": "copy", "upstream": "tables"},
        ],
    )
    execute(job, EPOCH, start_from_scratch=True)
    capsys.readouterr()
    execute(job, EPOCH, start_from_scratch=False)
    err = capsys.readouterr().err
    assert "prompt:" in err
    assert "2/2" in err


def test_reduce_stage_prints_progress_for_its_single_entity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reduce prints a one-item bar for the single output entity."""
    records = [
        {"name": "a", "data": "A", "tag": {}},
        {"name": "b", "data": "B", "tag": {}},
    ]
    execute(
        make_job(
            tmp_path / "runs",
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {"name": "joined", "home": "concat", "upstream": "tables"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    err = capsys.readouterr().err
    assert "joined:" in err
    assert "1/1" in err
