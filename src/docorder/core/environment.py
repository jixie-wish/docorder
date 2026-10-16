"""Values a function can read for one operator run, and optionally one entity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from docorder.core.entity import Entity

if TYPE_CHECKING:
    from docorder.core.operator import Operator


class Environment:
    def __init__(
        self,
        operator: Operator,
        target: Entity | None = None,
        source: Entity | None = None,
    ):
        self._operator = operator
        self._target_entity = target
        self._source_entity = source

    @property
    def operator_props(self) -> dict[str, Any]:
        """Function parameters: home ``others`` plus class, type, and home path."""
        props = dict(self._operator.props.others)
        props["function_class"] = self._operator.props.function_class
        props["type"] = self._operator.props.type
        props["operator_home"] = self._operator.props.home
        return props

    @property
    def template_env(self) -> dict[str, Any]:
        """Nested values a template reads as ``operator``, ``job``, and ``entity``."""
        operator = self.operator_props
        operator["name"] = self._operator.name
        operator["home"] = str(self._operator.props.home)
        entity: dict[str, Any] = {}
        if self._source_entity is not None:
            entity["source_name"] = self._source_entity.name
            entity["source_data"] = self._source_entity.read_text()
            entity["source_tag"] = self._source_entity.tag
            entity["source_data_path"] = self._source_entity.data_path
        if self._target_entity is not None:
            entity["target_name"] = self._target_entity.name
            entity["target_data_path"] = self._target_entity.data_path
            entity["output"] = str(self._target_entity.directory)
        return {
            "operator": operator,
            "job": {
                "name": self._operator.run_context.job.name,
                "epoch": self._operator.run_context.epoch,
            },
            "entity": entity,
        }
