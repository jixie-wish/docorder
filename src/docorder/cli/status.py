"""Read a job output directory and report each epoch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docorder.core.entity import Entity, EntityStatus
from docorder.core.runner import OUTPUT_MARKER
from docorder.core.storage import EpochStore


@dataclass(frozen=True)
class StageCount:
    stage: str
    count: int


@dataclass(frozen=True)
class EpochStatus:
    epoch: str
    consistent: bool
    stages: tuple[StageCount, ...]


def inspect_output(output_dir: Path) -> tuple[EpochStatus, ...]:
    """Epochs under a job output directory, with consistency and entity counts.

    A stage is a direct child directory that holds the output marker. Entity
    counts come from ``EpochStore``. An epoch is consistent when every entity
    with an upstream snapshot matches that snapshot's live upstream entities,
    and every source entity has a body.
    """
    stages = _stage_dirs(output_dir)
    epochs = sorted({name for stage in stages for name in _epoch_names(stage)})
    return tuple(_epoch_status(epoch, stages) for epoch in epochs)


def format_status(reports: tuple[EpochStatus, ...]) -> str:
    if not reports:
        return "epochs: none\n"
    lines: list[str] = []
    for report in reports:
        state = "consistent" if report.consistent else "inconsistent"
        lines.append(f"{report.epoch}: {state}")
        for stage in report.stages:
            lines.append(f"  {stage.stage}: {stage.count}")
    return "\n".join(lines) + "\n"


def _stage_dirs(output_dir: Path) -> list[Path]:
    if not output_dir.is_dir():
        raise FileNotFoundError(f"job output directory does not exist: {output_dir}")
    return sorted(
        (
            path
            for path in output_dir.iterdir()
            if path.is_dir() and (path / OUTPUT_MARKER).is_file()
        ),
        key=lambda path: path.name,
    )


def _epoch_names(stage: Path) -> list[str]:
    return [path.name for path in stage.iterdir() if path.is_dir()]


def _epoch_status(epoch: str, stages: list[Path]) -> EpochStatus:
    stores = {stage.name: EpochStore(stage, epoch) for stage in stages}
    counts = tuple(StageCount(stage.name, len(stores[stage.name].entities)) for stage in stages)
    consistent = all(_stage_consistent(stores[stage.name], stores) for stage in stages)
    return EpochStatus(epoch, consistent, counts)


def _stage_consistent(store: EpochStore, stores: dict[str, EpochStore]) -> bool:
    entities = list(store.entities.values())
    # A stage that already recorded snapshots is downstream. An entity there
    # with no snapshot did not finish. A stage with no snapshots is a source.
    downstream = any(entity.upstream is not None for entity in entities)
    for entity in entities:
        if not entity.is_valid():
            return False
        if entity.upstream is None:
            if downstream or not entity.data_path.is_file():
                return False
            continue
        if _snapshot_status(entity, store.epoch, stores) is not EntityStatus.NORMAL:
            return False
    return True


def _snapshot_status(
    entity: Entity,
    epoch: str,
    stores: dict[str, EpochStore],
) -> EntityStatus:
    recorded = entity.upstream
    assert recorded is not None
    if not recorded.records:
        return entity.check_with_upstream([], "", epoch)
    operator = recorded.records[0].operator
    upstream = stores.get(operator)
    found: list[Entity] = []
    if upstream is not None:
        for record in recorded.records:
            live = upstream.get(record.name)
            if live is not None:
                found.append(live)
    return entity.check_with_upstream(found, operator, epoch)
