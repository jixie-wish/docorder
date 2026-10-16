"""A job is a DAG of operator bindings."""

from __future__ import annotations

from pathlib import Path

from docorder.core.operator import OperatorNode
from docorder.utils.errors import JobValidationError
from docorder.utils.paths import home_path
from docorder.utils.retry import RetryPolicy

JOB_RESULT_DIR = ".job_result"


class Job:
    def __init__(self, name, root_path: Path):
        self.name = name
        self.root_path = root_path
        self.nodes = {}

    @property
    def result_path(self) -> Path:
        """Job-level output directory under the root: ``.job_result``."""
        return self.root_path / JOB_RESULT_DIR

    def add_operator_node(
        self,
        name: str,
        operator_home: str,
        *,
        upstream: str | None = None,
        config: dict | None = None,
        parallelism: int | None = None,
        retry: RetryPolicy | None = None,
    ):
        if isinstance(upstream, (list, tuple)):
            raise JobValidationError(f"{name} must depend on one upstream")
        node = OperatorNode(
            job=self,
            name=name,
            operator_home=home_path(operator_home),
            output_path=self.root_path / name,
            upstream=upstream,
            config=config or {},
            parallelism=parallelism,
            retry=retry,
        )
        self.nodes[name] = node

    def get_operator_node(self, name: str) -> OperatorNode:
        if name in self.nodes:
            return self.nodes[name]
        raise JobValidationError(f"job {self.name} has no operator {name}")

    def validate(self) -> None:
        nodes = list(self.nodes.values())
        names = [node.name for node in nodes]
        if len(names) != len(set(names)):
            raise JobValidationError(f"job {self.name} has duplicate operator names")
        by_name = {node.name: node for node in nodes}
        outputs = [node.output_path.resolve() for node in nodes]
        if len(outputs) != len(set(outputs)):
            raise JobValidationError(f"job {self.name} binds two operators to one output path")
        for left in outputs:
            for right in outputs:
                if left == right:
                    continue
                if left in right.parents or right in left.parents:
                    raise JobValidationError(
                        f"job {self.name}: output paths must not contain each other ({left}, {right})"
                    )
        for node in nodes:
            upstream = node.upstream
            if upstream is None:
                continue
            if upstream not in by_name:
                raise JobValidationError(f"{node.name}: upstream {upstream} is not in the job")
            if upstream == node.name:
                raise JobValidationError(f"{node.name}: cannot depend on itself")
        self.topological()

    def topological(self) -> list[OperatorNode]:
        """Declaration order breaks ties, so the graph runs in the order it was built."""
        nodes = list(self.nodes.values())
        by_name = {node.name: node for node in nodes}
        index = {node.name: position for position, node in enumerate(nodes)}
        indegree = {node.name: 0 for node in nodes}
        children: dict[str, list[str]] = {node.name: [] for node in nodes}
        for node in nodes:
            upstream = node.upstream
            if upstream is None:
                continue
            if upstream not in by_name:
                raise JobValidationError(f"{node.name}: unknown upstream {upstream}")
            children[upstream].append(node.name)
            indegree[node.name] += 1
        ready = sorted((name for name, degree in indegree.items() if degree == 0), key=index.get)
        ordered: list[OperatorNode] = []
        while ready:
            name = ready.pop(0)
            ordered.append(by_name[name])
            for child in children[name]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
            ready.sort(key=index.get)
        if len(ordered) != len(self.nodes):
            raise JobValidationError(f"job {self.name} has a cycle")
        return ordered

