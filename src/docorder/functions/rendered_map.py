"""Run a map body once, then expose it as data and props."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from docorder.core.entity import Entity
from docorder.core.environment import Environment
from docorder.functions.map_function import MapFunction


class RenderedMap(MapFunction):
    """Read one upstream entity, render its body, then build its props.

    ``build`` runs those three steps in order. Override ``read_source``,
    ``apply_render``, or ``generate_props`` instead of ``build``. Each step
    receives the ``Environment`` for this entity: ``operator`` holds the
    operator props, including ``home``, and ``entity`` holds the upstream
    props, including ``output`` for the entity being written.
    """

    def build(
        self,
        source_entity: Entity,
        environment: Environment,
    ) -> tuple[str, dict[str, Any]]:
        """Return the output body and props for one upstream entity."""
        source = self.read_source(source_entity, environment)
        rendered = self.apply_render(source, source_entity, environment)
        props = self.generate_props(rendered, source, source_entity, environment)
        return rendered, props

    def read_source(self, source_entity: Entity, environment: Environment) -> Any:
        """Read the upstream entity. The default is its text."""
        return source_entity.read_text()

    @abstractmethod
    def apply_render(
        self,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> str:
        """Turn the value from ``read_source`` into the output body."""

    def generate_props(
        self,
        rendered: str,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> dict[str, Any]:
        """Tag for the output entity. The default carries the upstream tag."""
        return source_entity.carried_tag()

    def transform_data(self, source_entity: Entity, target_entity: Entity) -> None:
        body, _props = self._outcome(source_entity, target_entity)
        target_entity.staging_data = body

    def transform_props(self, source_entity: Entity, target_entity: Entity) -> None:
        _body, props = self._outcome(source_entity, target_entity)
        target_entity.tag = props

    def _outcome(
        self,
        source_entity: Entity,
        target_entity: Entity,
    ) -> tuple[str, dict[str, Any]]:
        cached = getattr(self, "_cache", None)
        key = (source_entity, target_entity)
        if cached is None or cached[0] != key:
            environment = Environment(self.operator, target_entity, source_entity)
            self.environment = environment
            cached = (key, self.build(source_entity, environment))
            self._cache = cached
        return cached[1]
