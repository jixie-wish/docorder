"""A function's read-only view of one operator home."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docorder.utils.errors import FatalError, OperatorValidationError


class Artifact:
    """Files in the operator home a function is running for.

    Construct it with the operator. Paths passed to ``read_text`` are relative
    to the operator home. Scheduling and function config stay on the operator.
    """

    def __init__(self, operator: Any) -> None:
        self._home = operator.operator_home

    @property
    def home(self) -> Path:
        return self._home

    def path(self, relative: str) -> Path:
        """Resolve ``relative`` inside the operator home."""
        if not isinstance(relative, str) or not relative or relative.startswith(("/", "\\")):
            raise OperatorValidationError(f"artifact path must be relative: {relative!r}")
        parts = Path(relative).parts
        if not parts or any(part in {".", ".."} for part in parts):
            raise OperatorValidationError(
                f"artifact path must stay in the operator home: {relative}"
            )
        home = self._home.resolve()
        full = (self._home / relative).resolve()
        if full != home and home not in full.parents:
            raise OperatorValidationError(
                f"artifact path must stay in the operator home: {relative}"
            )
        return full

    def exists(self, relative: str) -> bool:
        return self.path(relative).is_file()

    def read_text(self, relative: str) -> str:
        path = self.path(relative)
        if not path.is_file():
            raise FatalError(f"artifact {relative} is not in {self._home}")
        return path.read_text(encoding="utf-8")
