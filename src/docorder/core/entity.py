"""Directory-backed entities.

An entity is one directory directly under an epoch directory. It holds ``data``
and ``tag.json``. That directory's name is the entity name. The upstream
snapshot lives in ``tag.json`` as ``upstream``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from docorder.utils.errors import OperatorValidationError

log = logging.getLogger(__name__)

DATA_FILE = "data"
TAG_FILE = "tag.json"
UPSTREAM_FILE = "upstream.json"
LINEAGE_TAG_KEYS = frozenset({"upstream", "current"})


def content_digest(data: str, tag: Mapping[str, Any] | None = None) -> str:
    """Sha256 of one entity's body and user tag.

    An empty body is an empty digest, so an empty upstream never matches.
    ``upstream`` and leftover ``current`` are omitted: a snapshot must not
    hash itself, and a manual edit of the user tag must still be visible.
    """
    if not data:
        return ""
    payload = (
        {} if not tag else {key: value for key, value in tag.items() if key not in LINEAGE_TAG_KEYS}
    )
    material = json.dumps(
        {"data": data, "tag": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def entity_name_ok(name: object) -> bool:
    """True when ``name`` is one visible directory segment.

    A name has no slash, is not ``.`` or ``..``, and does not start with ``.``
    or ``_``.
    """
    return (
        isinstance(name, str)
        and bool(name)
        and name == name.strip()
        and "/" not in name
        and "\\" not in name
        and name not in {".", ".."}
        and not name.startswith((".", "_"))
    )


def require_entity_name(name: object, *, owner: str) -> str:
    """Return ``name`` when it is one visible directory segment."""
    if entity_name_ok(name):
        return name
    raise OperatorValidationError(
        f"{owner}: entity name must be one visible directory segment, got {name!r}"
    )


class EntityStatus(Enum):
    NORMAL = "normal"
    INVALID = "invalid"
    UPSTREAM_ENTITY_MISSING = "upstream_entity_missing"
    UPSTREAM_ENTITY_INCONSISTENT = "upstream_entity_inconsistent"


@dataclass(frozen=True)
class UpstreamRecord:
    operator: str
    name: str
    epoch: str
    hash: str

    def as_dict(self) -> dict[str, str]:
        return {
            "operator": self.operator,
            "name": self.name,
            "epoch": self.epoch,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> UpstreamRecord | None:
        if not isinstance(raw, dict):
            return None
        operator, name, epoch, digest = (
            raw.get("operator"),
            raw.get("name"),
            raw.get("epoch"),
            raw.get("hash"),
        )
        if not all(isinstance(item, str) for item in (operator, name, epoch, digest)):
            return None
        return cls(operator, name, epoch, digest)


@dataclass(frozen=True)
class Upstream:
    """Entity snapshots taken from one upstream operator."""

    records: tuple[UpstreamRecord, ...]

    @classmethod
    def of(cls, *records: UpstreamRecord) -> Upstream:
        return cls(records)

    def as_list(self) -> list[dict[str, str]]:
        return [record.as_dict() for record in self.records]

    @classmethod
    def from_list(cls, raw: Any) -> Upstream | None:
        if not isinstance(raw, list):
            return None
        records: list[UpstreamRecord] = []
        for item in raw:
            record = UpstreamRecord.from_dict(item)
            if record is None:
                return None
            records.append(record)
        return cls(tuple(records))


class Entity:
    """In-memory view of an entity directory.

    ``tag`` and ``upstream`` load from disk. ``staging_data`` records a data
    edit and stays unset until assigned. Load does not read the data file.
    ``persist`` writes that edit when it is set, then writes ``tag.json``.
    The snapshot is ``tag["upstream"]``, not a separate file.
    """

    directory: Path
    name: str
    staging_data: str | None
    tag: dict[str, Any]
    status: EntityStatus
    _upstream: Upstream | None

    def __init__(self, directory: Path, name: str) -> None:
        self.directory = directory
        self.name = name
        self.status = EntityStatus.NORMAL
        self.staging_data = None
        self._upstream = None
        self.tag = self._load_tag()
        self._upstream = self._load_upstream()
        self._drop_legacy_upstream_file()


    @property
    def data_path(self) -> Path:
        return self.directory / DATA_FILE

    @property
    def tag_path(self) -> Path:
        return self.directory / TAG_FILE

    @property
    def upstream_path(self) -> Path:
        return self.directory / UPSTREAM_FILE

    @property
    def upstream(self) -> Upstream | None:
        return self._upstream

    @upstream.setter
    def upstream(self, upstream: Upstream | None) -> None:
        self._upstream = upstream
        self.tag = dict(self.tag)
        if upstream is None:
            self.tag.pop("upstream", None)
        else:
            records = upstream.as_list()
            self.tag["upstream"] = records[0] if len(records) == 1 else records

    def carried_tag(self) -> dict[str, Any]:
        """Tag to hand to a downstream entity."""
        return dict(self.tag)

    def read_text(self) -> str:
        if self.staging_data is not None:
            return self.staging_data
        if not self.data_path.is_file():
            return ""
        try:
            return self.data_path.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            self.status = EntityStatus.INVALID
            log.warning("entity %s data: %s", self.name, exc)
            return ""

    def content_hash(self) -> str:
        return content_digest(self.read_text(), self.tag)

    def snapshot(self, operator: str, epoch: str) -> UpstreamRecord:
        return UpstreamRecord(operator, self.name, epoch, self.content_hash())

    def stamp_lineage(
        self,
        operator: str,
        epoch: str,
        sources: list[Entity] | None = None,
        upstream_operator: str | None = None,
    ) -> None:
        """Record a live upstream snapshot after this entity's data is set.

        ``sources`` is None for a source entity, which has no ``upstream``.
        A downstream entity is given the upstream entity, and a function often
        copies that tag wholesale. The copy still holds the upstream
        ``upstream`` and may hold a leftover ``current``, so both keys are
        replaced here. ``upstream`` becomes a live snapshot of the immediate
        sources: the record itself when there is one source, and a list when
        there are none or several. ``current`` is dropped. Values a function
        wrote on those two keys are discarded.
        """
        self.tag = dict(self.tag)
        self.tag.pop("current", None)
        if sources is None:
            self.tag.pop("upstream", None)
        else:
            if not isinstance(upstream_operator, str) or not upstream_operator:
                raise OperatorValidationError(
                    f"{operator}: downstream lineage needs an upstream operator"
                )
            records = [source.snapshot(upstream_operator, epoch).as_dict() for source in sources]
            self.tag["upstream"] = records[0] if len(records) == 1 else records
        self._upstream = self._load_upstream()

    def _load_tag(self) -> dict[str, Any]:
        if not self.tag_path.is_file():
            return {}
        try:
            payload = json.loads(self.tag_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return self._invalid_tag(exc)
        if not isinstance(payload, dict):
            return self._invalid_tag("tag.json is not an object")
        return payload

    def _load_upstream(self) -> Upstream | None:
        if self.status != EntityStatus.NORMAL:
            return None
        raw = self.tag.get("upstream")
        if raw is None:
            return None
        payload = [raw] if isinstance(raw, dict) else raw
        return self._upstream_from_payload(payload)

    def _upstream_from_payload(self, payload: Any) -> Upstream | None:
        info = Upstream.from_list(payload)
        if info is None:
            return self._invalid_upstream("upstream is not a list of records")
        operators = {record.operator for record in info.records}
        if len(operators) > 1:
            return self._invalid_upstream("upstream records name more than one operator")
        return info

    def _invalid_tag(self, reason: object) -> dict[str, Any]:
        self.status = EntityStatus.INVALID
        log.warning("entity %s tag.json: %s", self.name, reason)
        return {}

    def _invalid_upstream(self, reason: object) -> None:
        self.status = EntityStatus.INVALID
        log.warning("entity %s upstream: %s", self.name, reason)
        return None

    @classmethod
    def load(cls, output_dir: Path, name: str) -> Entity:
        directory = output_dir / name
        entity = cls(directory, name)
        if not entity.data_path.is_file():
            raise FileNotFoundError(f"entity {name} has no data under {output_dir}")
        return entity

    def persist(self) -> None:
        require_entity_name(self.name, owner=self.name)
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.staging_data is not None:
            self._atomic_text(self.data_path, self.staging_data)
        self._atomic_text(
            self.tag_path,
            json.dumps(self.tag, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        self._drop_legacy_upstream_file()

    def _drop_legacy_upstream_file(self) -> None:
        if self.upstream_path.is_file():
            self.upstream_path.unlink()

    @staticmethod
    def _atomic_text(path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)

    def discard(self) -> None:
        if self.directory.is_dir():
            shutil.rmtree(self.directory)

    def is_valid(self) -> bool:
        return self.status == EntityStatus.NORMAL

    def check_with_upstream(
        self,
        entities: list[Entity],
        operator: str,
        epoch: str,
    ) -> EntityStatus:
        """Compare the stored upstream snapshot with the entities named by lineage.

        The snapshot is ``tag["upstream"]``, one record or a list of records
        from one operator. ``entities`` is the live set for that operator,
        limited to the names in the lineage. Each record's hash is compared
        with the live entity's body and user tag. The result is stored on
        ``status``. A failure is redone.
        """
        recorded = self.upstream
        # No snapshot: the body may exist, but the previous run never recorded its upstream.
        if recorded is None:
            self.status = EntityStatus.INVALID
            return self.status
        live = {entity.name: entity for entity in entities}
        recorded_names = [record.name for record in recorded.records]
        # Names differ, or the same name was recorded more than once.
        if set(recorded_names) != set(live) or len(recorded_names) != len(live):
            self.status = EntityStatus.UPSTREAM_ENTITY_MISSING
            return self.status
        for record in recorded.records:
            # Every record belongs to this entity's single upstream operator.
            if record.operator != operator:
                self.status = EntityStatus.UPSTREAM_ENTITY_INCONSISTENT
                return self.status
            entity = live[record.name]
            digest = entity.content_hash()
            # An empty hash means the body was missing. A different epoch or
            # hash means the body or the user tag changed.
            if record.epoch != epoch or not record.hash or record.hash != digest:
                self.status = EntityStatus.UPSTREAM_ENTITY_INCONSISTENT
                return self.status
        self.status = EntityStatus.NORMAL
        return self.status
