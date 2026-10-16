"""Stage execution: one operator finishes before any downstream operator starts."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from docorder.core.epoch_diff import EpochEntityDiff, format_diff_table
from docorder.core.job import Job
from docorder.core.operator import Operator
from docorder.core.storage import EpochStoreFactory
from docorder.utils.errors import FatalError

log = logging.getLogger(__name__)

OUTPUT_MARKER = ".docorder-output"


class RunContext:
    """One epoch of a job: the shared factory and every operator."""

    def __init__(self, job: Job, epoch: str, start_from_scratch: bool) -> None:
        self.job = job
        self.epoch = epoch
        self.epoch_store_factory = EpochStoreFactory(epoch)
        self.operators: dict[str, Operator] = {}
        self.start_from_scratch = start_from_scratch

    def construct(self) -> None:
        operator_nodes = self.job.topological()
        operators = [
            Operator.of(node, run_context=self, factory=self.epoch_store_factory)
            for node in operator_nodes
        ]
        self.operators = {operator.name: operator for operator in operators}
        for operator in operators:
            self.epoch_store_factory.add_operator(operator)


def execute(job: Job, epoch: str, *, start_from_scratch: bool = False) -> None:
    """Run one epoch.

    Source operators run their function only when ``start_from_scratch`` is true.
    Otherwise they are skipped and downstream operators read the entities
    already stored at the source output path.
    """
    job.validate()
    context = RunContext(job, epoch, start_from_scratch=start_from_scratch)
    context.construct()
    log.info(
        "job %s epoch %s: %s",
        job.name,
        epoch,
        " -> ".join(context.operators),
    )
    # Topological order, one stage at a time. Do not start the next operator
    # from inside the one that just finished.
    rows: list[tuple[str, EpochEntityDiff]] = []
    for operator in context.operators.values():
        rows.append(_run_operator(operator))
    print("\n" + format_diff_table(epoch, rows), file=sys.stderr)


def _run_operator(operator: Operator) -> tuple[str, EpochEntityDiff]:
    _prepare_output(operator.output_path)
    diff = EpochEntityDiff(operator)
    pending = operator.prepare_before_execute()
    operator.execute(pending)
    diff.finish()
    return operator.name, diff


def _prepare_output(path: Path) -> None:
    marker = path / OUTPUT_MARKER
    if path.exists() and not marker.is_file() and any(path.iterdir()):
        raise FatalError(
            f"refuse to use {path} as an operator output: "
            "the directory is not empty and has no docorder marker"
        )
    path.mkdir(parents=True, exist_ok=True)
    marker.write_text("docorder\n", encoding="utf-8")
