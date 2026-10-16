"""Map function: render a prompt template stored in the operator home."""

from __future__ import annotations

from typing import Any

import jinja2

from docorder.core.entity import Entity
from docorder.core.environment import Environment
from docorder.functions.rendered_map import RenderedMap
from docorder.utils.errors import FatalError


class TemplateToPrompt(RenderedMap):
    """Render a Jinja prompt template stored in the operator home.

    The template sees ``template_env``: ``operator``, ``job``, and ``entity``.
    Write ``{{ operator.home }}``, ``{{ job.epoch }}``, ``{{ entity.source_data }}``.

    Config keys:

    - ``template``: path relative to the operator home.
    """

    def apply_render(
        self,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> str:
        relative = self.environment.operator_props.get("template")
        if not isinstance(relative, str) or not relative:
            raise FatalError("template_to_prompt config missing template")
        return self.render(
            self.artifact.read_text(relative),
            environment.template_env,
            source_entity.name,
        )

    def render(self, template: str, values: dict[str, Any], name: str) -> str:
        jinja_env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
        try:
            return jinja_env.from_string(template).render(**values)
        except jinja2.TemplateError as exc:
            raise FatalError(f"{name} template_to_prompt failed: {exc}") from exc
