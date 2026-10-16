"""Map function: run one command per entity."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from docorder.core.entity import Entity
from docorder.core.environment import Environment
from docorder.functions.rendered_map import RenderedMap
from docorder.utils.errors import DocorderError, FatalError

_NAMED = re.compile(r"\{([\w.]+)\}")


class Command(RenderedMap):
    """Format an argv with ``{prop}`` and run it once per entity.

    Names come from the environment: entity props, plus ``{operator.home}``
    and ``{entity.output}``.

    Config keys:

    - ``argv``: command and arguments. Each item is formatted with ``{prop}``.
    - ``cwd``: working directory.
    - ``capture``: ``file``, ``stdout``, or ``none``. Default ``file`` when
      ``output_file`` is set, otherwise ``stdout``.
    - ``output_file``: path read when ``capture`` is ``file``. Also formatted with ``{prop}``.
    """

    def apply_render(
        self,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> str:
        argv, output_path = self.prepared(environment)
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        cwd = self.environment.operator_props.get("cwd")
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd) if cwd else None,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise FatalError(f"command not found: {argv[0]}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise DocorderError(f"command exited {completed.returncode}: {detail[-4000:]}")
        capture = str(
            self.environment.operator_props.get(
                "capture", "file" if output_path is not None else "stdout"
            )
        )
        if capture == "file":
            if output_path is None:
                raise FatalError("capture=file needs output_file")
            if not output_path.is_file():
                raise DocorderError(f"command did not write {output_path}")
            return output_path.read_text(encoding="utf-8")
        if capture == "stdout":
            return completed.stdout
        if capture == "none":
            return ""
        raise FatalError(f"unknown capture mode {capture}")

    def generate_props(
        self,
        rendered: str,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> dict[str, Any]:
        argv, output_path = self.prepared(environment)
        props = source_entity.carried_tag()
        props["command"] = " ".join(argv)
        if output_path is not None:
            props["output_file"] = str(output_path)
        return props

    def prepared(self, environment: Environment) -> tuple[list[str], Path | None]:
        argv = [
            _format_named(str(item), environment.template_env)
            for item in self.environment.operator_props.get("argv") or []
        ]
        if not argv:
            raise FatalError("command config missing argv")
        output_file = self.environment.operator_props.get("output_file")
        if not output_file:
            return argv, None
        return argv, Path(_format_named(str(output_file), environment.template_env))


def _format_named(template: str, values: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        current: Any = values
        for part in match.group(1).split("."):
            if not isinstance(current, dict) or part not in current:
                raise FatalError(f"format placeholder {{{match.group(1)}}} has no value")
            current = current[part]
        return str(current)

    return _NAMED.sub(replace, template)
