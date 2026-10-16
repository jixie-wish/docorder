"""Temporary operator homes and entities for contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docorder.core.entity import DATA_FILE, Entity, Upstream, UpstreamRecord, content_digest
from docorder.core.job import Job

EPOCH = "20261015"

PRIMARY = '''
import json
from pathlib import Path

from docorder.functions.fanout_function import FanoutFunction
from docorder.functions.map_function import MapFunction
from docorder.functions.output_function import OutputFunction
from docorder.functions.reduce_function import ReduceFunction
from docorder.functions.source_function import SourceFunction, SourceRecord


class FixedSource(SourceFunction):
    def emit(self):
        counter = self.environment.operator_props.get("counter")
        if counter:
            path = Path(counter)
            seen = int(path.read_text(encoding="utf-8")) if path.exists() else 0
            path.write_text(str(seen + 1), encoding="utf-8")
        for item in self.environment.operator_props.get("records", []):
            tag = item["tag"] if "tag" in item else {}
            yield SourceRecord(item["name"], item["data"], tag)


class CopyMap(MapFunction):
    def transform_data(self, source_entity, target_entity):
        target_entity.staging_data = source_entity.read_text()

    def transform_props(self, source_entity, target_entity):
        if self.environment.operator_props.get("carry"):
            target_entity.tag = source_entity.carried_tag()
            return
        produced = self.environment.operator_props.get("global_prop")
        target_entity.tag = {} if produced is None else {"global_prop": produced}


class FlakyMap(MapFunction):
    def transform_data(self, source_entity, target_entity):
        if target_entity.name in (self.environment.operator_props.get("fail") or []):
            path = Path(self.environment.operator_props["attempts"])
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            current[target_entity.name] = current.get(target_entity.name, 0) + 1
            path.write_text(json.dumps(current), encoding="utf-8")
            raise RuntimeError(target_entity.name)
        target_entity.staging_data = source_entity.read_text()

    def transform_props(self, source_entity, target_entity):
        target_entity.tag = {}


class ConcatReduce(ReduceFunction):
    def transform_data(self, sources, target_entity):
        target_entity.staging_data = "|".join(entity.read_text() for entity in sources)

    def transform_props(self, sources, target_entity):
        target_entity.tag = {"count": len(sources)}


class SplitFanout(FanoutFunction):
    def output_names(self, source_entity):
        names = self.environment.operator_props.get("names")
        if names is not None:
            return list(names)
        return [f"{source_entity.name}_x", f"{source_entity.name}_y"]

    def transform_data(self, source_entity, target_entity):
        target_entity.staging_data = source_entity.read_text()

    def transform_props(self, source_entity, target_entity):
        target_entity.tag = {}


class PublishOutput(OutputFunction):
    pass
'''


def digest(text: str, tag: dict[str, Any] | None = None) -> str:
    return content_digest(text, tag)


def snapshot(
    operator: str,
    name: str,
    data: str,
    epoch: str = EPOCH,
    tag: dict[str, Any] | None = None,
) -> Upstream:
    return Upstream.of(UpstreamRecord(operator, name, epoch, digest(data, tag)))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def put_entity(
    epoch_dir: Path,
    name: str,
    data: str,
    tag: dict[str, Any] | None = None,
    upstream: Upstream | None = None,
) -> None:
    entity = Entity(epoch_dir / name, name)
    entity.staging_data = data
    entity.tag = {} if tag is None else tag
    entity.upstream = upstream
    entity.persist()


def install_homes(root: Path) -> None:
    specs = {
        "fixed": ("source", "FixedSource", {"max_attempts": 1, "backoff_seconds": 0}),
        "copy": ("map", "CopyMap", {"max_attempts": 1, "backoff_seconds": 0}),
        "flaky": ("map", "FlakyMap", {"max_attempts": 2, "backoff_seconds": 0}),
        "concat": ("reduce", "ConcatReduce", {"max_attempts": 1, "backoff_seconds": 0}),
        "split": ("fanout", "SplitFanout", {"max_attempts": 1, "backoff_seconds": 0}),
        "publish": ("output", "PublishOutput", {"max_attempts": 1, "backoff_seconds": 0}),
    }
    for name, (kind, class_name, retry) in specs.items():
        home = root / name
        home.mkdir(parents=True)
        props = {
            "type": kind,
            "class": f"primary:{class_name}",
            "parallelism": 1,
            "retry": retry,
        }
        (home / "props.json").write_text(json.dumps(props), encoding="utf-8")
        (home / "primary.py").write_text(PRIMARY, encoding="utf-8")


def make_job(root: Path, nodes: list[dict[str, Any]]) -> Job:
    job = Job("demo", root)
    for node in nodes:
        job.add_operator_node(
            node["name"],
            node["home"],
            upstream=node.get("upstream"),
            config=node.get("config"),
            parallelism=node.get("parallelism"),
            retry=node.get("retry"),
        )
    return job


def entity_dir(root: Path, operator: str, name: str, epoch: str = EPOCH) -> Path:
    return root / operator / epoch / name


def entity_text(root: Path, operator: str, name: str, epoch: str = EPOCH) -> str:
    return (entity_dir(root, operator, name, epoch) / DATA_FILE).read_text(encoding="utf-8")
