"""Epoch directories of entities, one store per output root."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from docorder.core.entity import (
    DATA_FILE,
    TAG_FILE,
    Entity,
    UpstreamRecord,
    entity_name_ok,
    require_entity_name,
)


class EpochStore:
    """Entities of one epoch directory, loaded when the store is created."""

    def __init__(self, output_dir: Path, epoch: str) -> None:
        self.output_dir = output_dir
        self.epoch = epoch
        self.epoch_dir = output_dir / epoch
        self.entities: dict[str, Entity] = {}
        self.reload()

    def reload(self) -> None:
        self.entities = {entity.name: entity for entity in self.list_entities()}

    def census(self) -> dict[str, str]:
        """Name to content hash of the entities in this epoch directory."""
        return {entity.name: entity.content_hash() for entity in self.list_entities()}

    def list_entities(self) -> list[Entity]:
        """Direct child directories of this epoch, including ones with no ``data``.

        A name is one directory segment. Nested directories are not entities.
        A directory is an entity when it holds ``data`` or ``tag.json``.
        ``tag.json`` alone is an empty entity created by ``allocate``.
        """
        root = self.epoch_dir
        if not root.is_dir():
            return []
        found: list[Entity] = []
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if not path.is_dir() or not entity_name_ok(path.name):
                continue
            if (path / DATA_FILE).is_file() or (path / TAG_FILE).is_file():
                found.append(Entity(path, path.name))
        return found

    def get(self, name: str) -> Entity | None:
        return self.entities.get(name)

    def record(self, name: str, operator: str) -> UpstreamRecord:
        entity = self.entities.get(name)
        if entity is None:
            return UpstreamRecord(operator, name, self.epoch, "")
        return entity.snapshot(operator, self.epoch)

    def write(self, entity: Entity) -> None:
        """Persist ``entity`` and keep it in this store.

        The caller fills ``staging_data``, ``props``, and ``upstream`` on the
        entity first. This does not build another entity.
        """
        entity.persist()
        self.entities[entity.name] = entity

    def allocate(self, names: Iterable[str]) -> None:
        """Create an empty entity for each name and keep it in this store.

        The directory has ``tag.json`` and no ``data`` file. ``reload`` finds
        it, and ``execute`` fills that same entity.
        """
        for name in names:
            require_entity_name(name, owner=str(self.epoch_dir))
            entity = Entity(self.epoch_dir / name, name)
            entity.tag = {}
            entity.staging_data = None
            entity.persist()
            self.entities[name] = entity

    def handle(
        self,
        todo: Iterable[str],
        redo: Iterable[Entity],
        removed: Iterable[Entity],
    ) -> None:
        """Leave an empty entity for each name ``execute`` will write.

        Redo names are deleted first, then created again empty, so the old body
        is gone and ``get`` still returns the entity. Removed names are deleted
        and not created again. The store is reloaded when this returns.
        """
        redo_entities = list(redo)
        removed_entities = list(removed)
        pending = [*todo, *(entity.name for entity in redo_entities)]
        for entity in [*redo_entities, *removed_entities]:
            self.discard(entity.name)
        self.allocate(pending)
        self.reload()

    def discard(self, name: str) -> None:
        directory = self.epoch_dir / name
        entity = self.entities.pop(name, None)
        if entity is not None:
            entity.discard()
        elif directory.is_dir():
            shutil.rmtree(directory)
        _prune_empty(directory.parent, self.epoch_dir)

    def clear_epoch(self) -> None:
        if self.epoch_dir.is_dir():
            shutil.rmtree(self.epoch_dir)
        self.entities.clear()


class EpochStoreFactory:
    """Returns one store per directory for a single epoch."""

    def __init__(self, epoch: str) -> None:
        self.epoch = epoch
        self._stores: dict[Path, EpochStore] = {}

    def get(self, output_dir: Path) -> EpochStore:
        key = (output_dir / self.epoch).resolve()
        store = self._stores.get(key)
        if store is None:
            store = EpochStore(output_dir, self.epoch)
            self._stores[key] = store
        return store

    def add_operator(self, operator: Any) -> None:
        self.get(operator.output_path)


def _prune_empty(directory: Path, stop: Path) -> None:
    current = directory
    while current != stop and current.is_dir():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
