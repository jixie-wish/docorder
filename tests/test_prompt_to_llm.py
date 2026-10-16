"""PromptToLLM keeps a data file the tool wrote, and otherwise uses stdout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from tests.support import EPOCH, digest, entity_dir, entity_text, install_homes, make_job, read_json

from docorder.core.runner import execute
from docorder.utils.errors import DocorderError


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "homes"
    install_homes(root)
    monkeypatch.setenv("DOCORDER_HOMES", str(root))
    return root

WRITER = """
import sys
from pathlib import Path

path = Path(sys.argv[1])
marker = Path(sys.argv[2])
path.write_text("written-by-llm\\n", encoding="utf-8")
marker.write_text(str(path.stat().st_ino), encoding="utf-8")
sys.stdout.write("stdout-only\\n")
"""


def test_llm_keeps_data_file_the_tool_wrote(tmp_path: Path, homes: Path) -> None:
    """A data file written by the tool stays on disk. Only tag.json is added."""
    root = tmp_path / "runs"
    data_path = entity_dir(root, "answers", "orders") / "data"
    marker = tmp_path / "inode"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "write_entity.py"
    script.write_text(WRITER, encoding="utf-8")
    home = homes / "ask"
    home.mkdir()
    (home / "props.json").write_text(
        json.dumps(
            {
                "type": "map",
                "class": "docorder.functions.impl.prompt_to_llm:PromptToLLM",
                "workspace": str(workspace),
                "tool": {
                    "name": "writer",
                    "run": [sys.executable, str(script), str(data_path), str(marker)],
                    "prompt": "stdin",
                },
            }
        ),
        encoding="utf-8",
    )
    records = [{"name": "orders", "data": "describe orders", "tag": {"table": "orders"}}]

    execute(
        make_job(
            root,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {"name": "answers", "home": "ask", "upstream": "tables"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )

    assert data_path.read_text(encoding="utf-8") == "written-by-llm\n"
    assert data_path.stat().st_ino == int(marker.read_text(encoding="utf-8"))
    assert entity_text(root, "answers", "orders") == "written-by-llm\n"
    tag = read_json(entity_dir(root, "answers", "orders") / "tag.json")
    assert tag["table"] == "orders"
    assert "current" not in tag
    assert tag["upstream"] == {
        "operator": "tables",
        "name": "orders",
        "epoch": EPOCH,
        "hash": digest("describe orders", {"table": "orders"}),
    }


def test_llm_uses_stdout_when_the_tool_does_not_write_data(tmp_path: Path, homes: Path) -> None:
    """Without a data file, the tool's standard output is the entity body."""
    script = 'import sys\nsys.stdout.write("stdout-only\\n")\n'
    root = _run_llm(tmp_path, homes, script)

    assert entity_text(root, "answers", "orders") == "stdout-only\n"


def test_llm_rejects_an_empty_data_file(tmp_path: Path, homes: Path) -> None:
    """An empty file the tool wrote is not a finished body."""
    script = "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('', encoding='utf-8')\n"
    with pytest.raises(DocorderError, match="llm data is empty"):
        _run_llm(tmp_path, homes, script, pass_data_path=True)


def test_llm_rejects_data_that_is_not_utf8(tmp_path: Path, homes: Path) -> None:
    """The on-disk body has to be text."""
    script = "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_bytes(b'\\xff')\n"
    with pytest.raises(DocorderError, match="llm data is not utf-8"):
        _run_llm(tmp_path, homes, script, pass_data_path=True)


def test_llm_rejects_a_data_directory(tmp_path: Path, homes: Path) -> None:
    """A directory named data is not a body the tool wrote."""
    script = "from pathlib import Path\nimport sys\nPath(sys.argv[1]).mkdir()\n"
    with pytest.raises(DocorderError, match="llm data path is not a file"):
        _run_llm(tmp_path, homes, script, pass_data_path=True)


def test_llm_retry_replaces_a_data_directory_from_the_failed_attempt(
    tmp_path: Path, homes: Path
) -> None:
    """A directory named data left by a failed attempt does not block the next call."""
    script = """
from pathlib import Path
import sys
path = Path(sys.argv[1])
count = Path(sys.argv[2])
seen = int(count.read_text(encoding="utf-8")) if count.exists() else 0
seen += 1
count.write_text(str(seen), encoding="utf-8")
if seen == 1:
    path.mkdir()
else:
    sys.stdout.write("recovered\\n")
"""
    root = _run_llm(tmp_path, homes, script, pass_data_path=True, attempts=2)

    assert entity_text(root, "answers", "orders") == "recovered\n"


def test_llm_retry_drops_a_data_file_from_the_failed_attempt(tmp_path: Path, homes: Path) -> None:
    """A file left by a failed attempt is not treated as the next attempt's output."""
    script = """
from pathlib import Path
import sys
path = Path(sys.argv[1])
count = Path(sys.argv[2])
seen = int(count.read_text(encoding="utf-8")) if count.exists() else 0
seen += 1
count.write_text(str(seen), encoding="utf-8")
if seen == 1:
    path.write_text("", encoding="utf-8")
else:
    sys.stdout.write("recovered\\n")
"""
    root = _run_llm(tmp_path, homes, script, pass_data_path=True, attempts=2)

    assert entity_text(root, "answers", "orders") == "recovered\n"


def _run_llm(
    tmp_path: Path,
    homes: Path,
    script: str,
    *,
    pass_data_path: bool = False,
    attempts: int = 1,
) -> Path:
    root = tmp_path / "runs"
    data_path = entity_dir(root, "answers", "orders") / "data"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    program = tmp_path / "tool.py"
    program.write_text(script, encoding="utf-8")
    run = [sys.executable, str(program)]
    if pass_data_path:
        run.append(str(data_path))
        run.append(str(tmp_path / "attempts"))
    home = homes / "ask"
    home.mkdir()
    (home / "props.json").write_text(
        json.dumps(
            {
                "type": "map",
                "class": "docorder.functions.impl.prompt_to_llm:PromptToLLM",
                "workspace": str(workspace),
                "retry": {"max_attempts": attempts, "backoff_seconds": 0},
                "tool": {"name": "writer", "run": run, "prompt": "stdin"},
            }
        ),
        encoding="utf-8",
    )
    records = [{"name": "orders", "data": "describe orders", "tag": {"table": "orders"}}]
    execute(
        make_job(
            root,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {"name": "answers", "home": "ask", "upstream": "tables"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    return root
