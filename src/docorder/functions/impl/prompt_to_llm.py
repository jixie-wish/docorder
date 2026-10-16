"""Map function: send one entity's prompt to the configured LLM tool."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from docorder.core.entity import Entity
from docorder.core.environment import Environment
from docorder.functions.rendered_map import RenderedMap
from docorder.utils.errors import DocorderError, FatalError
from docorder.utils.llm_tool import LLMTool


class PromptToLLM(RenderedMap):
    """Run the configured tool on the entity body.

    A preset name loads ``tools/<name>.json`` from the operator home. The
    entity body is the tool's standard output. When the tool has already
    written ``data`` under the target entity, that file is the body and only
    ``tag.json`` is written.

    Config keys:

    - ``tool``: preset name, JSON file path, or tool object. When omitted, ``DOCORDER_LLM`` is used.
    - ``workspace``: directory passed to the tool. Must already exist.
    """

    def apply_render(
        self,
        source: Any,
        source_entity: Entity,
        environment: Environment,
    ) -> str:
        tool = LLMTool.resolve(self.environment.operator_props, self.artifact)
        return tool.complete(str(source), self.workspace())

    def transform_data(self, source_entity: Entity, target_entity: Entity) -> None:
        path = target_entity.data_path
        self._clear_data(path)
        body, _props = self._outcome(source_entity, target_entity)
        if path.is_file():
            self._check_written_data(path, target_entity.name)
            target_entity.staging_data = None
            return
        if path.exists():
            raise DocorderError(
                f"{self.operator_name}:{target_entity.name}: llm data path is not a file"
            )
        target_entity.staging_data = body

    def _clear_data(self, path: Path) -> None:
        """Drop a body left by an earlier attempt so this call's write is the one we see."""
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    def _check_written_data(self, path: Path, name: str) -> None:
        label = f"{self.operator_name}:{name}"
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise DocorderError(f"{label}: llm data is not utf-8") from exc
        except OSError as exc:
            raise DocorderError(f"{label}: llm data cannot be read: {exc}") from exc
        if text == "":
            raise DocorderError(f"{label}: llm data is empty")

    def workspace(self) -> Path:
        workspace = self.environment.operator_props.get("workspace")
        if not workspace:
            raise FatalError("llm config missing workspace")
        path = Path(str(workspace))
        if not path.is_dir():
            raise FatalError(f"workspace is not a directory: {path}")
        return path
