"""The twenty contract cases for one epoch."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.support import (
    EPOCH,
    digest,
    entity_dir,
    entity_text,
    install_homes,
    make_job,
    put_entity,
    read_json,
    snapshot,
)

from docorder.core.artifact import Artifact
from docorder.core.entity import (
    TAG_FILE,
    UPSTREAM_FILE,
    Entity,
    EntityStatus,
    Upstream,
    UpstreamRecord,
)
from docorder.core.environment import Environment
from docorder.core.job import Job
from docorder.core.operator import OperatorNode
from docorder.core.runner import OUTPUT_MARKER, RunContext, execute
from docorder.functions.function import Function
from docorder.utils.errors import FatalError, JobValidationError, OperatorValidationError
from docorder.utils.retry import RetryPolicy, call_with_retry

pytestmark = pytest.mark.usefixtures("homes")


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "homes"
    install_homes(root)
    monkeypatch.setenv("DOCORDER_HOMES", str(root))
    return root


def test_persist_records_upstream_after_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The snapshot lives in tag.json, written after data. leftover upstream.json is removed."""
    order: list[str] = []
    original = Entity._atomic_text

    def record(path: Path, text: str) -> None:
        order.append(path.name)
        original(path, text)

    monkeypatch.setattr(Entity, "_atomic_text", staticmethod(record))
    directory = tmp_path / "orders"
    entity = Entity(directory, "orders")
    entity.staging_data = "body"
    entity.tag = {"ready": True}
    entity.upstream = Upstream.of(UpstreamRecord("tables", "orders", EPOCH, digest("body")))
    entity.persist()

    assert order == ["data", TAG_FILE]
    assert not (directory / UPSTREAM_FILE).exists()
    assert read_json(directory / TAG_FILE)["upstream"]["operator"] == "tables"
    leftover = directory / UPSTREAM_FILE
    leftover.write_text("[]\n", encoding="utf-8")
    loaded = Entity(directory, "orders")
    assert not leftover.exists()
    assert loaded.upstream is not None
    assert loaded.upstream.records[0].operator == "tables"
    order.clear()
    entity.upstream = None
    entity.persist()
    assert order == ["data", TAG_FILE]
    assert "upstream" not in read_json(directory / TAG_FILE)
    leftover.write_text("[]\n", encoding="utf-8")
    entity.persist()
    assert not leftover.exists()
    reloaded = Entity(directory, "orders")
    assert reloaded.check_with_upstream([], "tables", EPOCH) is EntityStatus.INVALID


def test_upstream_snapshot_status(tmp_path: Path) -> None:
    """A stored snapshot is normal only when name, operator, epoch, and hash all match."""
    live_dir = tmp_path / "live"
    put_entity(live_dir, "orders", "body")
    live = Entity(live_dir / "orders", "orders")
    case = 0

    def status(upstream: Upstream | None, entities: list[Entity] | None = None) -> EntityStatus:
        nonlocal case
        case += 1
        directory = tmp_path / f"out-{case}"
        entity = Entity(directory / "orders", "orders")
        entity.staging_data = "out"
        entity.tag = {}
        entity.upstream = upstream
        entity.persist()
        loaded = Entity(directory / "orders", "orders")
        compared = [live] if entities is None else entities
        return loaded.check_with_upstream(compared, "tables", EPOCH)

    matching = snapshot("tables", "orders", "body")
    assert status(None) is EntityStatus.INVALID
    assert status(snapshot("tables", "other", "body")) is EntityStatus.UPSTREAM_ENTITY_MISSING
    duplicated = Upstream.of(matching.records[0], matching.records[0])
    assert status(duplicated) is EntityStatus.UPSTREAM_ENTITY_MISSING
    assert status(snapshot("other", "orders", "body")) is EntityStatus.UPSTREAM_ENTITY_INCONSISTENT
    other_epoch = snapshot("tables", "orders", "body", epoch="other")
    assert status(other_epoch) is EntityStatus.UPSTREAM_ENTITY_INCONSISTENT
    empty_hash = Upstream.of(UpstreamRecord("tables", "orders", EPOCH, ""))
    assert status(empty_hash) is EntityStatus.UPSTREAM_ENTITY_INCONSISTENT
    different = snapshot("tables", "orders", "different")
    assert status(different) is EntityStatus.UPSTREAM_ENTITY_INCONSISTENT
    assert status(matching) is EntityStatus.NORMAL

    tagged_dir = tmp_path / "tagged"
    put_entity(tagged_dir, "orders", "body", {"table": "orders"})
    tagged = Entity(tagged_dir / "orders", "orders")
    assert status(matching, [tagged]) is EntityStatus.UPSTREAM_ENTITY_INCONSISTENT
    assert (
        status(snapshot("tables", "orders", "body", tag={"table": "orders"}), [tagged])
        is EntityStatus.NORMAL
    )


def test_prepare_creates_redoes_and_removes_entities(tmp_path: Path) -> None:
    """Missing names are created empty, drifted names are cleared, and extras are deleted."""
    root = tmp_path / "runs"
    source = root / "tables" / EPOCH
    mapped = root / "prompt" / EPOCH
    put_entity(source, "keep", "same")
    put_entity(source, "redo", "live")
    put_entity(source, "fresh", "new")
    put_entity(mapped, "keep", "same", upstream=snapshot("tables", "keep", "same"))
    put_entity(mapped, "redo", "stale-body", upstream=snapshot("tables", "redo", "stale-body"))
    put_entity(mapped, "extra", "drop", upstream=snapshot("tables", "extra", "drop"))
    job = make_job(
        root,
        [
            {"name": "tables", "home": "fixed"},
            {"name": "prompt", "home": "copy", "upstream": "tables"},
        ],
    )
    context = RunContext(job, EPOCH, start_from_scratch=False)
    context.construct()
    pending = context.operators["prompt"].prepare_before_execute()

    assert pending == ["fresh", "redo"]
    assert entity_text(root, "prompt", "keep") == "same"
    fresh = entity_dir(root, "prompt", "fresh")
    redo = entity_dir(root, "prompt", "redo")
    assert read_json(fresh / TAG_FILE) == {}
    assert not (fresh / "data").exists()
    assert read_json(redo / TAG_FILE) == {}
    assert not (redo / "data").exists()
    assert not entity_dir(root, "prompt", "extra").exists()


def test_job_rejects_invalid_graphs_and_keeps_declaration_order(tmp_path: Path) -> None:
    """Cycles, unknown edges, and overlapping outputs fail; ties follow insertion order."""
    missing = Job("demo", tmp_path / "missing")
    missing.add_operator_node("prompt", "copy", upstream="tables")
    with pytest.raises(JobValidationError, match="not in the job"):
        missing.validate()

    loop = Job("demo", tmp_path / "loop")
    loop.add_operator_node("prompt", "copy", upstream="prompt")
    with pytest.raises(JobValidationError, match="cannot depend on itself"):
        loop.validate()

    cycle = Job("demo", tmp_path / "cycle")
    cycle.add_operator_node("left", "copy", upstream="right")
    cycle.add_operator_node("right", "copy", upstream="left")
    with pytest.raises(JobValidationError, match="has a cycle"):
        cycle.validate()

    shared = tmp_path / "shared"
    (shared / "beta").mkdir(parents=True)
    (shared / "alpha").symlink_to(shared / "beta", target_is_directory=True)
    same_path = Job("demo", shared)
    same_path.add_operator_node("alpha", "copy")
    same_path.add_operator_node("beta", "copy")
    with pytest.raises(JobValidationError, match="one output path"):
        same_path.validate()

    nested_root = tmp_path / "nested"
    (nested_root / "outer" / "leaf").mkdir(parents=True)
    (nested_root / "inner").symlink_to(nested_root / "outer" / "leaf", target_is_directory=True)
    nested = Job("demo", nested_root)
    nested.add_operator_node("outer", "copy")
    nested.add_operator_node("inner", "copy")
    with pytest.raises(JobValidationError, match="must not contain each other"):
        nested.validate()

    ordered = Job("demo", tmp_path / "ordered")
    ordered.add_operator_node("a", "copy")
    ordered.add_operator_node("c", "copy")
    ordered.add_operator_node("b", "copy", upstream="a")
    ordered.validate()
    assert [node.name for node in ordered.topological()] == ["a", "c", "b"]


def test_job_config_overrides_props_except_class(tmp_path: Path) -> None:
    """Job config overrides function parameters.

    ``class`` in config is dropped. Node parallelism and retry override the home.
    """
    home = tmp_path / "prompt"
    home.mkdir()
    (home / "props.json").write_text(
        json.dumps(
            {
                "type": "map",
                "class": "docorder.functions.map_function:MapFunction",
                "parallelism": 1,
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "template": "from-home",
            }
        ),
        encoding="utf-8",
    )
    node = OperatorNode(
        job=Job("demo", tmp_path / "runs"),
        name="prompt",
        operator_home=home,
        output_path=tmp_path / "runs" / "prompt",
        config={"template": "from-job", "class": "nope:Nope", "extra": 1},
        parallelism=4,
        retry=RetryPolicy(max_attempts=3, backoff_seconds=1.5),
    )

    assert node.props.others == {"template": "from-job", "extra": 1}
    assert "config" not in vars(node)
    assert node.props.function_class == "docorder.functions.map_function:MapFunction"
    assert node.props.parallelism == 4
    assert node.props.retry == RetryPolicy(max_attempts=3, backoff_seconds=1.5)


def test_environment_reads_operator_not_a_prebuilt_dict(tmp_path: Path) -> None:
    """Environment is built from the operator and the current source and target."""
    home = tmp_path / "prompt"
    home.mkdir()
    (home / "props.json").write_text(
        json.dumps(
            {
                "type": "map",
                "class": "docorder.functions.map_function:MapFunction",
                "template": "from-home",
                "audience": "from-home",
            }
        ),
        encoding="utf-8",
    )
    node = OperatorNode(
        job=Job("demo", tmp_path / "runs"),
        name="prompt",
        operator_home=home,
        output_path=tmp_path / "runs" / "prompt",
        config={"audience": "from-job", "extra": "only-job", "name": "spoofed"},
    )
    source_dir = tmp_path / "source" / "orders"
    put_entity(source_dir.parent, "orders", "hello", tag={"table": "orders"})
    source = Entity(source_dir, "orders")
    target = Entity(tmp_path / "runs" / "prompt" / EPOCH / "orders", "orders")
    operator = SimpleNamespace(
        name=node.name,
        props=node.props,
        output_path=node.output_path,
        operator_home=node.operator_home,
        run_context=SimpleNamespace(epoch=EPOCH, job=SimpleNamespace(name="demo")),
    )

    environment = Environment(operator, target, source)
    assert not hasattr(operator, "node")
    assert not hasattr(environment, "namespace")
    assert not hasattr(environment, "config") or "config" not in vars(type(environment))

    assert environment.operator_props["audience"] == "from-job"
    assert environment.template_env["operator"]["audience"] == "from-job"
    assert environment.template_env["operator"]["name"] == "prompt"
    assert environment.template_env["job"]["epoch"] == EPOCH
    assert environment.template_env["entity"]["source_data"] == "hello"
    assert environment.template_env["entity"]["source_tag"]["table"] == "orders"


def test_template_operator_view_follows_job_config(tmp_path: Path, homes: Path) -> None:
    """A template's ``operator`` shows job config overrides. Run fields such as ``name`` still win."""
    home = homes / "render"
    (home / "lib").mkdir(parents=True)
    (home / "props.json").write_text(
        json.dumps(
            {
                "type": "map",
                "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
                "template": "lib/view.jinja",
                "audience": "from-home",
            }
        ),
        encoding="utf-8",
    )
    (home / "lib" / "view.jinja").write_text(
        "{{ operator.audience }} {{ operator.extra }} {{ operator.name }}", encoding="utf-8"
    )
    root = tmp_path / "runs"
    records = [{"name": "orders", "data": "hello"}]
    execute(
        make_job(
            root,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {
                    "name": "prompt",
                    "home": "render",
                    "upstream": "tables",
                    "config": {"audience": "from-job", "extra": "only-job", "name": "spoofed"},
                },
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )

    assert entity_text(root, "prompt", "orders") == "from-job only-job prompt"


def test_function_environment_provides_config_and_operator(tmp_path: Path) -> None:
    """Function.environment is built from the operator and is the source of config."""
    home = tmp_path / "prompt"
    home.mkdir()
    (home / "props.json").write_text(
        json.dumps(
            {
                "type": "map",
                "class": "docorder.functions.map_function:MapFunction",
                "template": "from-home",
                "audience": "from-home",
            }
        ),
        encoding="utf-8",
    )
    node = OperatorNode(
        job=Job("demo", tmp_path / "runs"),
        name="prompt",
        operator_home=home,
        output_path=tmp_path / "runs" / "prompt",
        config={"audience": "from-job", "extra": "only-job", "name": "spoofed"},
    )
    operator = SimpleNamespace(
        name=node.name,
        props=node.props,
        output_path=node.output_path,
        operator_home=node.operator_home,
        run_context=SimpleNamespace(epoch=EPOCH, job=SimpleNamespace(name="demo")),
    )
    function = Function.create(Function, Artifact(operator), operator=operator)
    assert not hasattr(operator, "node")

    assert not hasattr(function, "config") or "config" not in vars(function)
    assert function.environment.operator_props["audience"] == "from-job"
    assert function.environment.operator_props["extra"] == "only-job"
    assert function.environment.operator_props["template"] == "from-home"
    assert function.environment.template_env["operator"]["name"] == "prompt"
    assert function.environment.template_env["job"]["epoch"] == EPOCH


def test_operator_exposes_node_fields_after_construction(tmp_path: Path) -> None:
    """Operator.of lifts the node's public fields; later code uses the operator."""
    root = tmp_path / "runs"
    job = make_job(
        root,
        [
            {"name": "tables", "home": "fixed"},
            {"name": "prompt", "home": "copy", "upstream": "tables"},
        ],
    )
    context = RunContext(job, EPOCH, start_from_scratch=False)
    context.construct()
    operator = context.operators["prompt"]

    assert "node" not in vars(operator)
    assert operator.name == "prompt"
    assert operator.upstream == "tables"
    assert operator.output_path == root / "prompt"
    assert operator.props is job.get_operator_node("prompt").props
    assert operator.operator_home == job.get_operator_node("prompt").operator_home


def test_execute_refuses_unmarked_nonempty_output(tmp_path: Path) -> None:
    """A non-empty output without the marker is refused; an empty one is marked and used."""
    blocked = tmp_path / "blocked"
    occupied = blocked / "tables"
    occupied.mkdir(parents=True)
    (occupied / "local.txt").write_text("keep\n", encoding="utf-8")
    with pytest.raises(FatalError, match="no docorder marker"):
        execute(make_job(blocked, [{"name": "tables", "home": "fixed"}]), EPOCH)
    assert (occupied / "local.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (occupied / OUTPUT_MARKER).exists()

    empty = tmp_path / "empty"
    execute(make_job(empty, [{"name": "tables", "home": "fixed"}]), EPOCH)
    assert (empty / "tables" / OUTPUT_MARKER).read_text(encoding="utf-8") == "docorder\n"


def test_source_scratch_writes_entities_without_upstream(tmp_path: Path) -> None:
    """Scratch emit writes data and tag.json, rejects duplicate names, and rejects bad types."""
    root = tmp_path / "runs"
    records = [{"name": "orders", "data": "create table orders", "tag": {"filename": "orders.sql"}}]
    execute(
        make_job(root, [{"name": "tables", "home": "fixed", "config": {"records": records}}]),
        EPOCH,
        start_from_scratch=True,
    )
    written = entity_dir(root, "tables", "orders")
    assert entity_text(root, "tables", "orders") == "create table orders"
    assert read_json(written / TAG_FILE) == {"filename": "orders.sql"}
    assert not (written / UPSTREAM_FILE).exists()

    duplicated = [
        {"name": "orders", "data": "one", "tag": {}},
        {"name": "orders", "data": "two", "tag": {}},
    ]
    with pytest.raises(OperatorValidationError, match="duplicate entity"):
        execute(
            make_job(
                tmp_path / "duplicate",
                [{"name": "tables", "home": "fixed", "config": {"records": duplicated}}],
            ),
            EPOCH,
            start_from_scratch=True,
        )

    bad_data = [{"name": "orders", "data": 1, "tag": {}}]
    with pytest.raises(FatalError, match="emit data must be str"):
        execute(
            make_job(
                tmp_path / "bad-data",
                [{"name": "tables", "home": "fixed", "config": {"records": bad_data}}],
            ),
            EPOCH,
            start_from_scratch=True,
        )

    bad_tag = [{"name": "orders", "data": "text", "tag": "nope"}]
    with pytest.raises(FatalError, match="emit tag must be dict"):
        execute(
            make_job(
                tmp_path / "bad-tag",
                [{"name": "tables", "home": "fixed", "config": {"records": bad_tag}}],
            ),
            EPOCH,
            start_from_scratch=True,
        )


def test_source_skips_emit_when_not_starting_from_scratch(tmp_path: Path) -> None:
    """Without scratch, emit is not called and downstream reads the entities already stored."""
    root = tmp_path / "runs"
    counter = tmp_path / "emit-count"
    output = root / "tables"
    output.mkdir(parents=True)
    (output / OUTPUT_MARKER).write_text("docorder\n", encoding="utf-8")
    put_entity(output / EPOCH, "orders", "already")
    job = make_job(
        root,
        [
            {
                "name": "tables",
                "home": "fixed",
                "config": {
                    "counter": str(counter),
                    "records": [{"name": "orders", "data": "from-emit", "tag": {}}],
                },
            },
            {"name": "prompt", "home": "copy", "upstream": "tables"},
        ],
    )
    execute(job, EPOCH)

    assert not counter.exists()
    assert entity_text(root, "tables", "orders") == "already"
    assert entity_text(root, "prompt", "orders") == "already"


def test_source_scratch_replaces_epoch_entities(tmp_path: Path) -> None:
    """A later scratch run deletes entity directories that were not emitted."""
    root = tmp_path / "runs"
    job = make_job(
        root,
        [
            {
                "name": "tables",
                "home": "fixed",
                "config": {
                    "records": [
                        {"name": "orders", "data": "v1", "tag": {}},
                        {"name": "items", "data": "keep-me", "tag": {}},
                    ]
                },
            }
        ],
    )
    execute(job, EPOCH, start_from_scratch=True)
    job.get_operator_node("tables").props.others["records"] = [
        {"name": "orders", "data": "v2", "tag": {}},
    ]
    execute(job, EPOCH, start_from_scratch=True)

    assert entity_text(root, "tables", "orders") == "v2"
    assert not entity_dir(root, "tables", "items").exists()


def test_written_entity_has_no_current_and_downstream_snapshots_live_upstream(
    tmp_path: Path,
) -> None:
    """A written entity does not record current. Downstream snapshots the live upstream.

    The upstream tag is copied onto the next entity. That copy may still hold the
    upstream entity's upstream and a leftover current. Each downstream write drops
    current and replaces upstream with a live snapshot of the immediate sources.
    """
    root = tmp_path / "runs"
    body = "hello"
    user_tag = {"filename": "orders.sql"}
    records = [
        {
            "name": "orders",
            "data": body,
            "tag": {
                **user_tag,
                "current": {"operator": "stale", "name": "stale", "epoch": "old", "hash": "stale"},
            },
        }
    ]
    execute(
        make_job(
            root,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {"name": "once", "home": "copy", "upstream": "tables", "config": {"carry": True}},
                {"name": "twice", "home": "copy", "upstream": "once", "config": {"carry": True}},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )

    def record(operator: str, name: str) -> dict[str, str]:
        return {
            "operator": operator,
            "name": name,
            "epoch": EPOCH,
            "hash": digest(body, user_tag),
        }

    source_tag = read_json(entity_dir(root, "tables", "orders") / TAG_FILE)
    assert source_tag == user_tag

    source_snapshot = record("tables", "orders")
    once_tag = read_json(entity_dir(root, "once", "orders") / TAG_FILE)
    assert once_tag["filename"] == "orders.sql"
    assert "current" not in once_tag
    assert once_tag["upstream"] == source_snapshot

    twice_tag = read_json(entity_dir(root, "twice", "orders") / TAG_FILE)
    assert twice_tag["filename"] == "orders.sql"
    assert "current" not in twice_tag
    assert twice_tag["upstream"] == record("once", "orders")
    assert twice_tag["upstream"] != source_snapshot


def test_map_writes_same_name_entity_and_merges_global_prop(tmp_path: Path) -> None:
    """Each upstream entity is copied under the same name, and global_prop keys merge."""
    root = tmp_path / "runs"
    records = [
        {
            "name": "orders",
            "data": "hello",
            "tag": {"global_prop": {"from_up": 1, "shared": "up"}, "table": "orders"},
        }
    ]
    execute(
        make_job(
            root,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {
                    "name": "prompt",
                    "home": "copy",
                    "upstream": "tables",
                    "config": {"global_prop": {"shared": "down", "from_down": 2}},
                },
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )

    assert entity_text(root, "prompt", "orders") == "hello"
    tag = read_json(entity_dir(root, "prompt", "orders") / TAG_FILE)
    assert tag["global_prop"] == {"from_up": 1, "shared": "down", "from_down": 2}
    assert "current" not in tag
    assert tag["upstream"] == {
        "operator": "tables",
        "name": "orders",
        "epoch": EPOCH,
        "hash": digest(
            "hello",
            {"global_prop": {"from_up": 1, "shared": "up"}, "table": "orders"},
        ),
    }


def test_map_parallelism_shares_unpicklable_operator_state(tmp_path: Path) -> None:
    """A map with parallelism > 1 runs in threads, so operator state need not be picklable."""
    root = tmp_path / "runs"
    records = [
        {"name": "a", "data": "A", "tag": {}},
        {"name": "b", "data": "B", "tag": {}},
    ]
    job = make_job(
        root,
        [
            {"name": "tables", "home": "fixed", "config": {"records": records}},
            {"name": "prompt", "home": "copy", "upstream": "tables", "parallelism": 2},
        ],
    )
    job.get_operator_node("prompt").props.others["token"] = threading.Lock()
    execute(job, EPOCH, start_from_scratch=True)

    assert entity_text(root, "prompt", "a") == "A"
    assert entity_text(root, "prompt", "b") == "B"


def test_map_rerun_skips_matches_and_repairs_drift(tmp_path: Path) -> None:
    """A second pass keeps matches, rewrites drift, adds new names, and deletes orphans."""
    root = tmp_path / "runs"
    names = ["keep", "changed", "bare", "stale", "extra"]
    records = [{"name": name, "data": f"{name}-body", "tag": {}} for name in names]
    job = make_job(
        root,
        [
            {"name": "tables", "home": "fixed", "config": {"records": records}},
            {"name": "prompt", "home": "copy", "upstream": "tables"},
        ],
    )
    execute(job, EPOCH, start_from_scratch=True)

    for name in ("keep", "changed", "bare", "stale"):
        (entity_dir(root, "prompt", name) / "data").write_text("SENTINEL", encoding="utf-8")
    (entity_dir(root, "tables", "changed") / "data").write_text("new-body", encoding="utf-8")
    bare_tag_path = entity_dir(root, "prompt", "bare") / TAG_FILE
    bare_tag = read_json(bare_tag_path)
    del bare_tag["upstream"]
    bare_tag_path.write_text(json.dumps(bare_tag), encoding="utf-8")
    stale_tag_path = entity_dir(root, "prompt", "stale") / TAG_FILE
    stale_tag = read_json(stale_tag_path)
    stale_tag["upstream"]["epoch"] = "other"
    stale_tag_path.write_text(json.dumps(stale_tag), encoding="utf-8")
    shutil.rmtree(entity_dir(root, "tables", "extra"))
    put_entity(root / "tables" / EPOCH, "fresh", "fresh-body")

    execute(job, EPOCH)

    assert entity_text(root, "prompt", "keep") == "SENTINEL"
    assert entity_text(root, "prompt", "changed") == "new-body"
    assert entity_text(root, "prompt", "bare") == "bare-body"
    assert entity_text(root, "prompt", "stale") == "stale-body"
    assert not entity_dir(root, "prompt", "extra").exists()
    assert entity_text(root, "prompt", "fresh") == "fresh-body"
    assert read_json(entity_dir(root, "prompt", "fresh") / TAG_FILE)["upstream"]["name"] == "fresh"


def test_manual_entity_edit_redoes_downstream(tmp_path: Path) -> None:
    """Editing an upstream entity's data or tag.json redos the downstream entity."""
    root = tmp_path / "runs"
    records = [{"name": "orders", "data": "body", "tag": {"table": "orders"}}]
    job = make_job(
        root,
        [
            {"name": "tables", "home": "fixed", "config": {"records": records}},
            {"name": "prompt", "home": "copy", "upstream": "tables", "config": {"carry": True}},
        ],
    )
    execute(job, EPOCH, start_from_scratch=True)
    prompt = entity_dir(root, "prompt", "orders")
    (prompt / "data").write_text("SENTINEL", encoding="utf-8")

    execute(job, EPOCH)
    assert entity_text(root, "prompt", "orders") == "SENTINEL"

    (entity_dir(root, "tables", "orders") / "data").write_text("new-body", encoding="utf-8")
    execute(job, EPOCH)
    assert entity_text(root, "prompt", "orders") == "new-body"

    (prompt / "data").write_text("SENTINEL", encoding="utf-8")
    tag_path = entity_dir(root, "tables", "orders") / TAG_FILE
    tag = read_json(tag_path)
    tag["table"] = "orders_v2"
    tag_path.write_text(json.dumps(tag), encoding="utf-8")
    execute(job, EPOCH)
    assert entity_text(root, "prompt", "orders") == "new-body"
    assert read_json(prompt / TAG_FILE)["table"] == "orders_v2"
    assert "current" not in read_json(prompt / TAG_FILE)


def test_stage_failure_keeps_finished_entities_for_resume(tmp_path: Path) -> None:
    """Retry exhaustion stops the stage; a later epoch run continues with the rest."""
    root = tmp_path / "runs"
    attempts = tmp_path / "attempts.json"
    job = make_job(
        root,
        [
            {
                "name": "tables",
                "home": "fixed",
                "config": {
                    "records": [
                        {"name": "a", "data": "a-body", "tag": {}},
                        {"name": "b", "data": "b-body", "tag": {}},
                    ]
                },
            },
            {
                "name": "once",
                "home": "flaky",
                "upstream": "tables",
                "config": {"fail": ["b"], "attempts": str(attempts)},
            },
            {"name": "twice", "home": "copy", "upstream": "once"},
        ],
    )
    with pytest.raises(RuntimeError, match="b"):
        execute(job, EPOCH, start_from_scratch=True)

    assert read_json(attempts) == {"b": 2}
    assert "upstream" in read_json(entity_dir(root, "once", "a") / TAG_FILE)
    assert "upstream" not in read_json(entity_dir(root, "once", "b") / TAG_FILE)
    assert not (root / "twice").exists()

    (entity_dir(root, "once", "a") / "data").write_text("SENTINEL", encoding="utf-8")
    job.get_operator_node("once").props.others["fail"] = []
    execute(job, EPOCH)

    assert entity_text(root, "once", "a") == "SENTINEL"
    assert entity_text(root, "once", "b") == "b-body"
    assert "upstream" in read_json(entity_dir(root, "once", "b") / TAG_FILE)
    assert entity_text(root, "twice", "a") == "SENTINEL"
    assert entity_text(root, "twice", "b") == "b-body"
    assert read_json(attempts) == {"b": 2}


def test_reduce_writes_one_entity_for_the_whole_upstream(tmp_path: Path) -> None:
    """Reduce writes one entity, can rename it, and still writes when the upstream is empty."""
    root = tmp_path / "runs"
    records = [
        {"name": "a", "data": "A", "tag": {}},
        {"name": "b", "data": "B", "tag": {}},
    ]
    execute(
        make_job(
            root,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {"name": "joined", "home": "concat", "upstream": "tables"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    assert entity_text(root, "joined", "result") == "A|B"
    joined_tag = read_json(entity_dir(root, "joined", "result") / TAG_FILE)
    assert joined_tag["count"] == 2
    assert "current" not in joined_tag
    assert joined_tag["upstream"] == [
        {"operator": "tables", "name": "a", "epoch": EPOCH, "hash": digest("A")},
        {"operator": "tables", "name": "b", "epoch": EPOCH, "hash": digest("B")},
    ]
    assert not (entity_dir(root, "joined", "result") / UPSTREAM_FILE).exists()

    empty = tmp_path / "empty"
    execute(
        make_job(
            empty,
            [
                {"name": "tables", "home": "fixed", "config": {"records": []}},
                {"name": "joined", "home": "concat", "upstream": "tables"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    assert entity_text(empty, "joined", "result") == ""
    empty_tag = read_json(entity_dir(empty, "joined", "result") / TAG_FILE)
    assert empty_tag["count"] == 0
    assert empty_tag["upstream"] == []
    assert "current" not in empty_tag
    assert not (entity_dir(empty, "joined", "result") / UPSTREAM_FILE).exists()

    renamed = tmp_path / "renamed"
    execute(
        make_job(
            renamed,
            [
                {
                    "name": "tables",
                    "home": "fixed",
                    "config": {"records": [{"name": "a", "data": "A", "tag": {}}]},
                },
                {
                    "name": "joined",
                    "home": "concat",
                    "upstream": "tables",
                    "config": {"output": "summary"},
                },
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    assert entity_text(renamed, "joined", "summary") == "A"
    assert not entity_dir(renamed, "joined", "result").exists()


def test_fanout_expands_one_entity_and_rejects_duplicate_names(tmp_path: Path) -> None:
    """One upstream entity expands into the listed outputs; repeated names fail."""
    root = tmp_path / "runs"
    records = [{"name": "orders", "data": "body", "tag": {}}]
    execute(
        make_job(
            root,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {"name": "parts", "home": "split", "upstream": "tables"},
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    source_snapshot = {
        "operator": "tables",
        "name": "orders",
        "epoch": EPOCH,
        "hash": digest("body"),
    }
    for name in ("orders_x", "orders_y"):
        assert entity_text(root, "parts", name) == "body"
        tag = read_json(entity_dir(root, "parts", name) / TAG_FILE)
        assert tag["upstream"] == source_snapshot
        assert not (entity_dir(root, "parts", name) / UPSTREAM_FILE).exists()
        assert "current" not in tag

    with pytest.raises(OperatorValidationError, match="duplicate output"):
        execute(
            make_job(
                tmp_path / "duplicate",
                [
                    {"name": "tables", "home": "fixed", "config": {"records": records}},
                    {
                        "name": "parts",
                        "home": "split",
                        "upstream": "tables",
                        "config": {"names": ["same", "same"]},
                    },
                ],
            ),
            EPOCH,
            start_from_scratch=True,
        )


def test_output_writes_upstream_data_to_job_result(tmp_path: Path) -> None:
    """Output writes each upstream entity's data under the job's .job_result directory.

    The file name is the entity name, unless name_template is set; then the
    entity tag is rendered to produce the name. A later run drops files for
    entities that are no longer in the upstream epoch.
    """
    root = tmp_path / "runs"
    records = [
        {"name": "orders", "data": "create orders", "tag": {"table": "orders", "kind": "sql"}},
        {"name": "users", "data": "create users", "tag": {"table": "users", "kind": "sql"}},
    ]
    job = make_job(
        root,
        [
            {"name": "tables", "home": "fixed", "config": {"records": records}},
            {"name": "result", "home": "publish", "upstream": "tables"},
        ],
    )
    execute(job, EPOCH, start_from_scratch=True)

    published = root / ".job_result"
    assert (published / "orders").read_text(encoding="utf-8") == "create orders"
    assert (published / "users").read_text(encoding="utf-8") == "create users"

    named = tmp_path / "named"
    execute(
        make_job(
            named,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {
                    "name": "result",
                    "home": "publish",
                    "upstream": "tables",
                    "config": {"name_template": "{{ table }}.{{ kind }}"},
                },
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    rendered = named / ".job_result"
    assert (rendered / "orders.sql").read_text(encoding="utf-8") == "create orders"
    assert (rendered / "users.sql").read_text(encoding="utf-8") == "create users"
    assert not (rendered / "orders").exists()

    job.get_operator_node("tables").props.others["records"] = [records[0]]
    execute(job, EPOCH, start_from_scratch=True)
    assert (published / "orders").read_text(encoding="utf-8") == "create orders"
    assert not (published / "users").exists()


def test_output_writes_to_configured_directory(tmp_path: Path) -> None:
    """When directory is set, output writes there instead of the job's .job_result."""
    root = tmp_path / "runs"
    dest = tmp_path / "custom-out"
    records = [
        {"name": "orders", "data": "create orders", "tag": {"table": "orders"}},
    ]
    execute(
        make_job(
            root,
            [
                {"name": "tables", "home": "fixed", "config": {"records": records}},
                {
                    "name": "result",
                    "home": "publish",
                    "upstream": "tables",
                    "config": {"directory": str(dest)},
                },
            ],
        ),
        EPOCH,
        start_from_scratch=True,
    )
    assert (dest / "orders").read_text(encoding="utf-8") == "create orders"
    assert not (root / ".job_result").exists()


def test_output_rejects_blank_or_duplicate_result_names(tmp_path: Path) -> None:
    """A rendered name must be one file name, and two entities cannot share it."""
    records = [
        {"name": "orders", "data": "A", "tag": {"file": "same.sql"}},
        {"name": "users", "data": "B", "tag": {"file": "same.sql"}},
    ]
    with pytest.raises(FatalError, match="duplicate"):
        execute(
            make_job(
                tmp_path / "duplicate",
                [
                    {"name": "tables", "home": "fixed", "config": {"records": records}},
                    {
                        "name": "result",
                        "home": "publish",
                        "upstream": "tables",
                        "config": {"name_template": "{{ file }}"},
                    },
                ],
            ),
            EPOCH,
            start_from_scratch=True,
        )

    with pytest.raises(FatalError, match="job result name"):
        execute(
            make_job(
                tmp_path / "blank",
                [
                    {
                        "name": "tables",
                        "home": "fixed",
                        "config": {
                            "records": [{"name": "orders", "data": "A", "tag": {"file": ""}}]
                        },
                    },
                    {
                        "name": "result",
                        "home": "publish",
                        "upstream": "tables",
                        "config": {"name_template": "{{ file }}"},
                    },
                ],
            ),
            EPOCH,
            start_from_scratch=True,
        )


def test_retry_repeats_failures_and_stops_on_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ordinary failures wait backoff times the attempt count; FatalError is not retried."""
    slept: list[float] = []
    monkeypatch.setattr("docorder.utils.retry.time.sleep", slept.append)
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("nope")
        return "ok"

    policy = RetryPolicy(max_attempts=3, backoff_seconds=0.5)
    assert call_with_retry(flaky, policy, label="orders") == "ok"
    assert calls["n"] == 3
    assert slept == [0.5, 1.0]

    slept.clear()

    def fatal() -> None:
        calls["n"] += 1
        raise FatalError("bad")

    with pytest.raises(FatalError, match="bad"):
        call_with_retry(fatal, policy, label="orders")
    assert calls["n"] == 4
    assert slept == []
