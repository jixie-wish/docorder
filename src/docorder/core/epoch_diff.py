"""How many entities one operator run added, modified, or deleted."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol


class _Census(Protocol):
    def census(self) -> Mapping[str, str]: ...

_HEADERS = ("operator", "added", "modified", "deleted")
_ALIGN_RIGHT = (False, True, True, True)


class EpochEntityDiff:
    """Change across one operator run.

    Construct this before the operator prepares its outputs, and call
    ``finish`` after ``execute`` returns. The source is whatever ``census``
    reports: epoch entities for a transform, or published result files for
    output. Added names are new, deleted names are gone, and modified names
    kept the same name but changed their content hash. An entity hash is the
    body plus the user tag, so a rewrite that only replaces the upstream
    snapshot is not a modification.
    """

    added: frozenset[str]
    modified: frozenset[str]
    deleted: frozenset[str]

    def __init__(self, source: _Census) -> None:
        self._source = source
        self._before = self._snapshot()
        self._finished = False
        self.added = frozenset()
        self.modified = frozenset()
        self.deleted = frozenset()

    def finish(self) -> None:
        """Compare the epoch directory with the snapshot taken at construction."""
        after = self._snapshot()
        before_names = set(self._before)
        after_names = set(after)
        self.added = frozenset(after_names - before_names)
        self.deleted = frozenset(before_names - after_names)
        self.modified = frozenset(
            name
            for name in before_names & after_names
            if self._before[name] != after[name]
        )
        self._finished = True

    def counts(self) -> tuple[int, int, int]:
        """Added, modified, and deleted counts. Requires ``finish``."""
        if not self._finished:
            raise RuntimeError("finish the epoch diff before reporting it")
        return len(self.added), len(self.modified), len(self.deleted)

    def _snapshot(self) -> dict[str, str]:
        return dict(self._source.census())


def format_diff_table(epoch: str, rows: Sequence[tuple[str, EpochEntityDiff]]) -> str:
    """Box table of added, modified, and deleted counts, one operator per row.

    The operator column is left-aligned. Count columns are right-aligned.
    """
    body = [
        (name, *(str(count) for count in diff.counts()))
        for name, diff in rows
    ]
    return f"epoch {epoch}\n{_box_table(body)}"


def _box_table(body: Sequence[tuple[str, ...]]) -> str:
    widths = []
    for index, header in enumerate(_HEADERS):
        width = len(header)
        for row in body:
            width = max(width, len(row[index]))
        widths.append(width)

    def rule(left: str, mid: str, right: str) -> str:
        cells = ["─" * (width + 2) for width in widths]
        return left + mid.join(cells) + right

    def row(values: tuple[str, ...]) -> str:
        cells: list[str] = []
        for value, width, align_right in zip(values, widths, _ALIGN_RIGHT, strict=True):
            text = value.rjust(width) if align_right else value.ljust(width)
            cells.append(f" {text} ")
        return "│" + "│".join(cells) + "│"

    lines = [
        rule("┌", "┬", "┐"),
        row(_HEADERS),
        rule("├", "┼", "┤"),
        *(row(item) for item in body),
        rule("└", "┴", "┘"),
    ]
    return "\n".join(lines)
