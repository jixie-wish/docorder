"""Source functions emit entities. The source operator only writes them."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from docorder.functions.function import Function


@dataclass(frozen=True)
class SourceRecord:
    """One entity emitted by a source function."""

    name: str
    data: str
    tag: dict[str, Any] = field(default_factory=dict)


class SourceFunction(Function, ABC):
    """Produces the entities of a source operator.

    Implement ``emit`` as a generator. Each record is one output entity:
    ``name``, ``data``, and ``tag``.
    """

    @abstractmethod
    def emit(self) -> Iterable[SourceRecord]:
        """Yield the entities this source writes."""
