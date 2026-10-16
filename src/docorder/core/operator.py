"""Operator homes, job bindings, and one run of an operator."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import InitVar, dataclass, field
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jinja2

from docorder.core.artifact import Artifact
from docorder.core.entity import Entity, EntityStatus, require_entity_name
from docorder.core.storage import EpochStore, EpochStoreFactory
from docorder.functions.fanout_function import FanoutFunction
from docorder.functions.function import Function
from docorder.functions.map_function import MapFunction
from docorder.functions.output_function import OutputFunction
from docorder.functions.reduce_function import ReduceFunction
from docorder.functions.source_function import SourceFunction, SourceRecord
from docorder.utils.errors import FatalError, JobValidationError, OperatorValidationError
from docorder.utils.modules import ModuleLoader
from docorder.utils.progress import progress_bar
from docorder.utils.retry import RetryPolicy, call_with_retry

if TYPE_CHECKING:
    from docorder.core.job import Job
    from docorder.core.runner import RunContext


OPERATOR_TYPES = ("source", "map", "reduce", "fanout", "output")
_PROPS_FIELDS = frozenset({"class", "parallelism", "retry", "type", "home"})

_FUNCTION_BASES: dict[str, type] = {
    "source": SourceFunction,
    "map": MapFunction,
    "reduce": ReduceFunction,
    "fanout": FanoutFunction,
    "output": OutputFunction,
}


@dataclass
class OperatorProps:
    """Static contract stored in an operator home's props.json.

    ``class`` names the function. ``type`` selects the operator. Neither can be
    overridden by the job node. ``parallelism`` and ``retry`` schedule the run
    and can be overridden on the node. ``home`` is that operator's directory.
    Every other key is kept in ``others`` as the default function config.
    The job node applies its ``config`` onto ``others`` at construction.
    """

    function_class: str
    parallelism: int
    retry: RetryPolicy
    type: str
    home: Path
    others: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, home: Path) -> OperatorProps:
        path = home / "props.json"
        if not path.is_file():
            raise JobValidationError(f"operator home missing props.json: {home}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise JobValidationError(f"{home.name}: props.json must be an object")
        function_class = raw.get("class")
        if not isinstance(function_class, str) or ":" not in function_class:
            raise JobValidationError(
                f"{home.name}: class must be 'primary:Class' or 'module:Class'"
            )
        parallelism = int(raw.get("parallelism", 1))
        kind = raw.get("type")
        if kind not in OPERATOR_TYPES:
            joined = ", ".join(OPERATOR_TYPES)
            raise JobValidationError(f"{home.name}: type must be one of {joined}")
        others = {key: value for key, value in raw.items() if key not in _PROPS_FIELDS}
        return cls(
            function_class=function_class,
            parallelism=parallelism,
            retry=RetryPolicy.from_mapping(raw.get("retry")),
            type=kind,
            home=home.resolve(),
            others=others,
        )


class WorkProfile:
    """Immutable picture of one operator after ``refresh``.

    ``lineage`` maps an output entity name to the upstream entity names that
    output depends on. Those entities all come from the operator's single upstream.
    """

    operator: Operator
    exist_entities: dict[str, Entity]
    upstream_entities: dict[str, Entity]
    lineage: dict[str, list[str]]

    def __init__(self, operator: Operator) -> None:
        self.operator = operator
        self.exist_entities = dict(operator.store.entities)
        store = operator.upstream_store
        self.upstream_entities = {} if store is None else dict(store.entities)
        self.lineage = operator.lineage

    def analyze_workload(self) -> tuple[list[str], list[Entity], list[Entity]]:
        """Return names to create, entities to redo, and entities to remove.

        A lineage name missing from disk is created. A name on disk but absent
        from the lineage is removed. A name in both is redone when its upstream
        snapshot does not match the live entities, or when the entity failed to
        load. Call this only after the upstream operator for this epoch has
        finished; otherwise that directory still holds the previous run.
        """
        epoch = self.operator.run_context.epoch
        upstream = self.operator.upstream
        for name, entity in self.exist_entities.items():
            names = self.lineage.get(name)
            # Left on disk but not in the lineage. Removed below, so skip the check.
            if names is None:
                continue
            found, missing = self._lineage_entities(names, self.upstream_entities)
            if missing or upstream is None:
                entity.status = EntityStatus.UPSTREAM_ENTITY_MISSING
            else:
                entity.check_with_upstream(found, upstream, epoch)
        invalid = {
            entity.name: entity
            for entity in self.exist_entities.values()
            if not entity.is_valid()
        }
        todo_names = sorted(set(self.lineage) - set(self.exist_entities))
        redo = [self.exist_entities[name] for name in sorted(set(self.lineage) & set(invalid))]
        removed = [
            self.exist_entities[name]
            for name in sorted(set(self.exist_entities) - set(self.lineage))
        ]
        return todo_names, redo, removed

    @staticmethod
    def _lineage_entities(
        names: list[str],
        upstream_entities: dict[str, Entity],
    ) -> tuple[list[Entity], bool]:
        """Resolve lineage names to live entities of the single upstream.

        The boolean is true when any named entity is no longer in that directory.
        """
        found: list[Entity] = []
        for name in names:
            entity = upstream_entities.get(name)
            if entity is None:
                return [], True
            found.append(entity)
        return found, False


class Operator(ABC):
    """One run of a transform: the job node's public fields plus this epoch."""

    name: str
    props: OperatorProps
    type: str
    operator_home: Path
    output_path: Path
    upstream: str | None
    run_context: RunContext
    store: EpochStore
    upstream_store: EpochStore | None
    lineage: dict[str, list[str]]
    work_profile: WorkProfile
    function_cls: type
    artifact: Artifact

    @classmethod
    def of(
        cls,
        node: OperatorNode,
        *,
        run_context: RunContext,
        factory: EpochStoreFactory,
    ) -> Operator:
        """Lift the node's public fields and bind this epoch's directories."""
        try:
            operator_cls = _OPERATORS[node.type]
        except KeyError:
            joined = ", ".join(OPERATOR_TYPES)
            raise JobValidationError(f"{node.name}: type must be one of {joined}") from None
        operator = operator_cls.__new__(operator_cls)

        operator.name = node.name
        operator.props = node.props
        operator.type = node.type
        operator.operator_home = node.operator_home
        operator.output_path = node.output_path
        operator.upstream = node.upstream
        operator.run_context = run_context
        operator.store = factory.get(operator.output_path)
        if operator.upstream is None:
            operator.upstream_store = None
        else:
            upstream = node.job.get_operator_node(operator.upstream)
            operator.upstream_store = factory.get(upstream.output_path)
        operator.artifact = Artifact(operator)
        operator.function_cls = ModuleLoader.load_function_class(
            operator.operator_home,
            operator.name,
            operator.props.function_class,
            _FUNCTION_BASES[operator.type],
        )
        operator.new_function()
        operator.lineage = operator.build_lineage()
        operator.work_profile = WorkProfile(operator)
        return operator

    def prepare_before_execute(self) -> list[str]:
        """Create empty entities for new and redone names, and delete dropped ones.

        Returns the names ``execute`` should write: new ones, then ones whose
        upstream changed. Names only removed from the lineage are not included.
        """
        if self.upstream_store is not None:
            self.upstream_store.reload()
        self.lineage = self.build_lineage()
        if not self.lineage:
            return []
        self.store.reload()
        self.work_profile = WorkProfile(self)

        todo, redo, removed = self.work_profile.analyze_workload()
        self.store.handle(todo, redo, removed)
        return [*todo, *(entity.name for entity in redo)]

    @abstractmethod
    def execute(self, pending: list[str]) -> None:
        """Write the names returned by ``prepare_before_execute``."""


    @abstractmethod
    def build_lineage(self) -> dict[str, list[str]]:
        """Output entity name to the upstream entity names it depends on."""

    def new_function(self):
        """Construct the configured function for this operator and epoch."""
        return Function.create(
            self.function_cls,
            self.artifact,
            operator=self,
        )

    def epoch_dir(self) -> Path:
        return self.store.epoch_dir

    def census(self) -> dict[str, str]:
        """Names and content hashes this operator contributes to the epoch diff.

        Entity operators report the epoch directory. An output operator reports
        the result files it has published.
        """
        return self.store.census()

    @staticmethod
    def _require_filled(target: Entity, operator_name: str) -> None:
        if target.staging_data is None:
            if not target.data_path.is_file():
                raise FatalError(
                    f"{operator_name}:{target.name}: transform_data must set staging_data to str"
                )
        elif not isinstance(target.staging_data, str):
            raise FatalError(
                f"{operator_name}:{target.name}: transform_data must set staging_data to str"
            )
        if not isinstance(target.tag, dict):
            raise FatalError(
                f"{operator_name}:{target.name}: transform_props must set tag to dict"
            )
        target.tag = dict(target.tag)

    @staticmethod
    def _assign_global_prop(sources: list[Entity], target: Entity) -> None:
        """Copy ``global_prop`` from source entities onto the target.

        The dict lives on the entity. Keys the transform already wrote replace
        the same keys from the sources.
        """
        carried: dict[str, Any] = {}
        found = False
        for source in sources:
            incoming = source.tag.get("global_prop")
            if isinstance(incoming, dict):
                carried.update(incoming)
                found = True
        produced = target.tag.get("global_prop")
        if isinstance(produced, dict):
            carried.update(produced)
            found = True
        if found:
            target.tag["global_prop"] = carried

    @staticmethod
    def _split_shards(
        items: list[tuple[str, str]],
        parallelism: int,
    ) -> list[list[tuple[str, str]]]:
        """Contiguous slices, at most ``parallelism`` of them."""
        count = min(parallelism, len(items))
        size = (len(items) + count - 1) // count
        return [items[start : start + size] for start in range(0, len(items), size)]

    def _execute_pairs(self, pending: list[str]) -> None:
        """Run one function call per pending output that depends on a single entity."""
        pairs: list[tuple[str, str]] = []
        for name in pending:
            sources = self.lineage[name]
            if len(sources) != 1:
                raise OperatorValidationError(
                    f"{self.name}: {name} must depend on one upstream entity"
                )
            pairs.append((name, sources[0]))
        total = len(self.lineage) if self.lineage else len(pairs)
        with progress_bar(self.name, total) as bar:
            skipped = total - len(pairs)
            if skipped:
                bar.update(skipped)
            if not pairs:
                return
            store = self.upstream_store
            upstream = self.upstream
            if store is None or upstream is None:
                raise OperatorValidationError(f"{self.name} needs an upstream")
            parallelism = self.props.parallelism
            if parallelism < 1:
                raise OperatorValidationError(f"{self.name}: parallelism must be >= 1")
            payloads = [
                _EntityShard(
                    names=tuple(shard),
                    upstream_output=store.output_dir,
                    upstream_operator=upstream,
                    output_dir=self.store.output_dir,
                    epoch=self.run_context.epoch,
                    operator=self,
                    retry=self.props.retry,
                    progress=bar,
                )
                for shard in self._split_shards(pairs, parallelism)
            ]
            if len(payloads) == 1:
                self._run_entity_shard(payloads[0])
            else:
                with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
                    futures = [
                        pool.submit(Operator._run_entity_shard, payload) for payload in payloads
                    ]
                    for future in as_completed(futures):
                        future.result()
            self.store.reload()

    @staticmethod
    def _apply_one(
        shard: _EntityShard,
        upstream: EpochStore,
        output: EpochStore,
        output_name: str,
        source_name: str,
        function_cls: type,
    ) -> None:
        source = upstream.get(source_name)
        if source is None or not source.data_path.is_file():
            raise FatalError(f"upstream entity {source_name} has no data")
        target = output.get(output_name)
        if target is None:
            raise FatalError(f"{shard.operator.name}:{output_name} is not in the output store")
        target.tag = {}
        target.staging_data = None
        function = shard.new_function(function_cls)
        function.transform_data(source, target)
        function.transform_props(source, target)
        Operator._require_filled(target, shard.operator.name)
        Operator._assign_global_prop([source], target)
        target.stamp_lineage(
            shard.operator.name,
            shard.epoch,
            [source],
            shard.upstream_operator,
        )
        output.write(target)

    @staticmethod
    def _run_entity_shard(shard: _EntityShard) -> None:
        function_cls = shard.operator.function_cls
        upstream = EpochStore(shard.upstream_output, shard.epoch)
        output = EpochStore(shard.output_dir, shard.epoch)
        for output_name, source_name in shard.names:
            call_with_retry(
                partial(
                    Operator._apply_one,
                    shard,
                    upstream,
                    output,
                    output_name,
                    source_name,
                    function_cls,
                ),
                shard.retry,
                label=f"{shard.operator.name}:{output_name}",
            )
            if shard.progress is not None:
                shard.progress.update(1)


class SourceOperator(Operator):
    """A graph root. It has no upstream.

    ``props.json`` ``class`` names a ``SourceFunction``. ``emit`` yields each output
    entity's name, data, and tag. ``execute`` calls it only when
    ``start_from_scratch`` is set. Otherwise the source is skipped and
    downstream operators read the entities already at its output path.
    """

    def build_lineage(self) -> dict[str, list[str]]:
        """Sources have no upstream lineage. The function is the input."""
        return {}

    def prepare_before_execute(self) -> list[str]:
        pending = super().prepare_before_execute()
        if self.run_context.start_from_scratch:
            # clean source output
            pass
        return pending

    def execute(self, pending: list[str]) -> None:
        """Replace this epoch's entities with what the source function emits.

        Names that are not emitted are deleted.
        """
        if not self.run_context.start_from_scratch:
            # 虽然指定不需要重复source，但还是考虑进行检查，比如检查目录非空，source的entity非空
            with progress_bar(self.name, 0):
                return
        produced: set[str] = set()
        # todo 对于source，还是先写到sandbox中，并进行数据校验比较好
        function = self.new_function()
        with progress_bar(self.name, None) as bar:
            for record in function.emit():
                require_entity_name(record.name, owner=self.name)
                if record.name in produced:
                    raise OperatorValidationError(f"{self.name}: duplicate entity {record.name}")
                call_with_retry(
                    partial(self._write_record, record),
                    self.props.retry,
                    label=f"{self.name}:{record.name}",
                )
                produced.add(record.name)
                bar.update(1)
            self.store.reload()
            for name in list(self.store.entities):
                if name not in produced:
                    self.store.discard(name)

    def _write_record(self, record: SourceRecord) -> None:
        if not isinstance(record.data, str):
            raise FatalError(f"{self.name}:{record.name}: emit data must be str")
        if not isinstance(record.tag, dict):
            raise FatalError(f"{self.name}:{record.name}: emit tag must be dict")
        target = Entity(self.store.epoch_dir / record.name, record.name)
        target.staging_data = record.data
        target.tag = dict(record.tag)
        target.stamp_lineage(self.name, self.run_context.epoch)
        self.store.write(target)


@dataclass(frozen=True)
class _EntityShard:
    """One process's share: output name paired with its single upstream entity."""

    names: tuple[tuple[str, str], ...]
    upstream_output: Path
    upstream_operator: str
    output_dir: Path
    epoch: str
    operator: Operator
    retry: RetryPolicy
    progress: object | None = None

    def new_function(self, function_cls: type) -> Function:
        """Construct the function for this shard's operator and epoch."""
        return Function.create(function_cls, self.operator.artifact, operator=self.operator)


class MapOperator(Operator):
    """One output entity for each entity of the upstream, under the same name.

    ``props.json`` ``class`` names a ``MapFunction`` subclass. For each pending
    entity it receives the upstream entity and the empty target, and fills
    ``staging_data`` and ``props``.
    """

    def build_lineage(self) -> dict[str, list[str]]:
        """One output per upstream entity, depending on that same-named entity."""
        store = self.upstream_store
        if store is None:
            return {}
        return {name: [name] for name in sorted(store.entities)}

    def execute(self, pending: list[str]) -> None:
        """Map each pending upstream entity through the configured function class.

        ``pending`` is the name list from ``prepare_before_execute``. It is split
        into ``parallelism`` slices. A single slice runs here; more than one
        slice runs one thread each.
        """
        self._execute_pairs(pending)


class ReduceOperator(Operator):
    """One output entity covering every entity of the upstream.

    ``props.json`` ``class`` names a ``ReduceFunction`` subclass. ``config["output"]``
    names that entity and defaults to ``result``. The function receives every
    upstream entity and the target.
    """

    def build_lineage(self) -> dict[str, list[str]]:
        """One output entity depending on every entity of the upstream."""
        store = self.upstream_store
        names = sorted(store.entities) if store is not None else []
        return {self._output_name(): names}

    def execute(self, pending: list[str]) -> None:
        output_name = self._output_name()
        working = output_name in pending
        with progress_bar(self.name, 1) as bar:
            if not working:
                bar.update(1)
                return
            store = self.upstream_store
            upstream = self.upstream
            if store is None or upstream is None:
                raise OperatorValidationError(f"{self.name} needs an upstream")
            sources: list[Entity] = []
            for name in self.lineage.get(output_name, []):
                entity = store.get(name)
                if entity is None or not entity.data_path.is_file():
                    raise FatalError(f"upstream entity {name} has no data")
                sources.append(entity)
            epoch = self.run_context.epoch

            def run() -> None:
                target = self.store.get(output_name)
                if target is None:
                    raise FatalError(f"{self.name}: {output_name} is not in the output store")
                target.tag = {}
                target.staging_data = None
                function = self.new_function()
                function.transform_data(sources, target)
                function.transform_props(sources, target)
                self._require_filled(target, self.name)
                self._assign_global_prop(sources, target)
                target.stamp_lineage(self.name, epoch, sources, upstream)
                self.store.write(target)

            call_with_retry(run, self.props.retry, label=f"{self.name}:{output_name}")
            bar.update(1)

    def _output_name(self) -> str:
        """Name of the single output entity. ``config["output"]`` overrides ``result``."""
        return require_entity_name(
            self.props.others.get("output", "result"), owner=self.name
        )


class OutputOperator(Operator):
    """Write the upstream epoch's entity data into the job result directory.

    Each upstream entity becomes one file under ``directory`` when that config
    is set, otherwise under ``job.result_path``. The file name is the entity
    name, or ``name_template`` rendered with the entity tag. The file body is
    the entity data. Files this operator wrote in an earlier run and no longer
    produced are removed.
    """

    _PUBLISHED_FILE = ".job_result-files"

    def build_lineage(self) -> dict[str, list[str]]:
        """Output publishes files, not entities. Lineage stays empty."""
        return {}

    def census(self) -> dict[str, str]:
        """Hashes of the result files this operator last published."""
        directory = self._result_dir()
        if not directory.is_dir():
            return {}
        found: dict[str, str] = {}
        for name in self._load_published():
            path = directory / name
            if path.is_file():
                found[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return found

    def execute(self, pending: list[str]) -> None:
        del pending
        store = self.upstream_store
        if store is None or self.upstream is None:
            raise OperatorValidationError(f"{self.name} needs an upstream")
        store.reload()
        template = self.props.others.get("name_template")
        planned: dict[str, Entity] = {}
        for entity in store.entities.values():
            name = self._result_name(entity, template)
            if name in planned:
                raise FatalError(f"{self.name}: duplicate job result name {name!r}")
            planned[name] = entity
        result_dir = self._result_dir()
        previous = self._load_published()
        result_dir.mkdir(parents=True, exist_ok=True)
        with progress_bar(self.name, len(planned)) as bar:
            for name, entity in planned.items():
                call_with_retry(
                    partial(self._write_result, result_dir / name, entity.read_text()),
                    self.props.retry,
                    label=f"{self.name}:{name}",
                )
                bar.update(1)
            for name in previous - planned.keys():
                path = result_dir / name
                if path.is_file():
                    path.unlink()
            self._save_published(set(planned))

    def _result_dir(self) -> Path:
        raw = self.props.others.get("directory")
        if raw is None:
            return self.run_context.job.result_path
        if not isinstance(raw, str) or not raw:
            raise FatalError(f"{self.name}: directory must be a non-empty string")
        path = Path(raw)
        if not path.is_absolute():
            path = self.operator_home / path
        return path.resolve()

    def _result_name(self, entity: Entity, template: object) -> str:
        if template is None or template == "":
            name = entity.name
        else:
            if not isinstance(template, str):
                raise FatalError(f"{self.name}: name_template must be a string")
            name = self._render_name(entity, template)
        if not _job_result_name_ok(name):
            raise FatalError(
                f"{self.name}:{entity.name}: job result name must be one file name, got {name!r}"
            )
        return name

    def _render_name(self, entity: Entity, template: str) -> str:
        jinja_env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
        try:
            rendered = jinja_env.from_string(template).render(entity.tag)
        except jinja2.TemplateError as exc:
            raise FatalError(
                f"{self.name}:{entity.name}: name_template failed: {exc}"
            ) from exc
        return rendered.strip()

    def _published_path(self) -> Path:
        return self.output_path / self._PUBLISHED_FILE

    def _load_published(self) -> set[str]:
        path = self._published_path()
        if not path.is_file():
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            return set()
        return set(payload)

    def _save_published(self, names: set[str]) -> None:
        path = self._published_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(names), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _write_result(path: Path, text: str) -> None:
        Entity._atomic_text(path, text)


def _job_result_name_ok(name: object) -> bool:
    """True when ``name`` is one file name under the job result directory."""
    return (
        isinstance(name, str)
        and bool(name)
        and name == name.strip()
        and "/" not in name
        and "\\" not in name
        and name not in {".", ".."}
    )


class FanoutOperator(Operator):
    """One upstream entity expands into many outputs.

    ``props.json`` ``class`` names a ``FanoutFunction`` subclass. ``output_names``
    on that function lists the targets for each upstream entity. Each target is
    filled by ``transform_data`` and ``transform_props``.
    """

    def build_lineage(self) -> dict[str, list[str]]:
        store = self.upstream_store
        if store is None:
            return {}
        function = self.new_function()
        lineage: dict[str, list[str]] = {}
        for source_name in sorted(store.entities):
            entity = store.entities[source_name]
            names = function.output_names(entity)
            if not isinstance(names, list):
                raise OperatorValidationError(
                    f"{self.name}: output_names must return a list of entity names"
                )
            for name in names:
                require_entity_name(name, owner=self.name)
                if name in lineage:
                    raise OperatorValidationError(f"{self.name}: duplicate output {name}")
                lineage[name] = [source_name]
        return lineage

    def execute(self, pending: list[str]) -> None:
        self._execute_pairs(pending)


_OPERATORS: dict[str, type[Operator]] = {
    "source": SourceOperator,
    "map": MapOperator,
    "reduce": ReduceOperator,
    "fanout": FanoutOperator,
    "output": OutputOperator,
}





@dataclass
class OperatorNode:
    """One vertex in a job: a reusable home plus this run's output path.

    ``config`` is applied onto ``props`` at construction and is not kept.
    After that, function parameters and the template operator view both
    come from ``props``. ``Operator.of`` lifts these public fields onto
    the operator; later code uses the operator, not the node.
    """

    job: Job
    name: str
    operator_home: Path
    output_path: Path
    upstream: str | None = None
    config: InitVar[dict[str, Any] | None] = None
    parallelism: int | None = None
    retry: RetryPolicy | None = None

    def __post_init__(self, config: dict[str, Any] | None) -> None:
        props = OperatorProps.load(self.operator_home)
        props.parallelism = self.parallelism if self.parallelism is not None else props.parallelism
        props.retry = self.retry if self.retry is not None else props.retry
        merged = dict(props.others)
        merged.update(config or {})
        merged.pop("class", None)
        props.others = merged
        self.props = props
        self.type = props.type
