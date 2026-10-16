"""Map function: render a Jinja template and JSON variables into jsonnet source."""

from __future__ import annotations

import json
from typing import Any

import jinja2

from docorder.core.entity import Entity
from docorder.core.environment import Environment
from docorder.functions.rendered_map import RenderedMap
from docorder.utils.errors import FatalError


class JinjaToJsonnet(RenderedMap):
    """Fill a home template with one entity's JSON object and write jsonnet.

    The upstream body is a JSON object. Its keys are the Jinja variables.
    ``{{ name }}`` inserts the value as text. ``{{ name | jsonnet }}`` inserts a
    jsonnet literal. ``environment`` is also in scope: ``{{ environment.operator.home }}``
    is this operator's home, and ``{{ environment.entity.output }}`` is the
    directory of the entity being written. ``{{ home }}`` is the same home path.
    The entity JSON cannot replace ``environment``, ``operator``, ``entity``, or
    ``home``. Props stay empty unless a subclass implements ``generate_props``.
    A subclass can override ``template_text`` and bring its own template.

    Config keys:

    - ``template``: path relative to the operator home.
    - ``variables``: default Jinja variables. The entity JSON overrides them.
    """

    def read_source(self, source_entity: Entity, environment: Environment) -> Any:
        return self.variables(source_entity, self.environment.operator_props.get("variables"))

    def apply_render(
        self,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> str:
        if not isinstance(source, dict):
            raise FatalError(f"{source_entity.name} JSON variables must be an object")
        return self.render(self.template_text(), source, environment, source_entity.name)

    def generate_props(
        self,
        rendered: str,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> dict[str, Any]:
        """Props taken from the rendered jsonnet. The default takes none."""
        return {}

    def template_text(self) -> str:
        """Jinja source for this render. The default reads ``config["template"]`` from the home."""
        relative = self.environment.operator_props.get("template")
        if not isinstance(relative, str) or not relative:
            raise FatalError("jinja_to_jsonnet config missing template")
        return self.artifact.read_text(relative)

    def variables(self, entity: Entity, defaults: object) -> dict[str, Any]:
        if defaults is None:
            defaults = {}
        if not isinstance(defaults, dict):
            raise FatalError("jinja_to_jsonnet variables must be a JSON object")
        text = entity.read_text().strip()
        if not text:
            raise FatalError(f"{entity.name} has no JSON variables")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FatalError(f"{entity.name} JSON variables are not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise FatalError(f"{entity.name} JSON variables must be an object")
        merged = dict(defaults)
        merged.update(parsed)
        return merged

    def render(
        self,
        template: str,
        variables: dict[str, Any],
        environment: Environment,
        name: str,
    ) -> str:
        jinja_env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
        jinja_env.filters["jsonnet"] = self.jsonnet_literal
        context = dict(variables)
        context.update(environment.template_env)
        context["home"] = environment.template_env["operator"].get("home", "")
        try:
            body = jinja_env.from_string(template).render(**context)
        except jinja2.TemplateError as exc:
            raise FatalError(f"{name} jinja_to_jsonnet failed: {exc}") from exc
        if not body.strip():
            raise FatalError(f"{name} jinja_to_jsonnet rendered empty")
        return body

    @staticmethod
    def jsonnet_literal(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)
