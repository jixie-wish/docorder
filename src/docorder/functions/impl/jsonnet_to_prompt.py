"""Map function: compile one entity's jsonnet source."""

from __future__ import annotations

import subprocess
from typing import Any

from docorder.core.entity import Entity
from docorder.core.environment import Environment
from docorder.functions.rendered_map import RenderedMap
from docorder.utils.errors import DocorderError, FatalError


class JsonnetToPrompt(RenderedMap):
    """Compile the upstream entity body with ``jsonnet``.

    The body is the program and is passed on stdin. The output body is the
    compiler's stdout. Props are the upstream props. Imports are
    paths already written in the program, such as an absolute path under the
    operator home. This operator has no config.
    """

    def apply_render(
        self,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> str:
        return self.compile(str(source), source_entity.name)

    def compile(self, source: str, name: str) -> str:
        try:
            completed = subprocess.run(
                ["jsonnet", "-"],
                input=source,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise FatalError("jsonnet is not on PATH") from exc
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip()
            raise DocorderError(f"jsonnet failed for {name}: {tail}")
        return completed.stdout
