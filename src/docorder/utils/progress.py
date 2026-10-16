"""Stderr progress bar for one operator stage."""

from __future__ import annotations

import sys

from tqdm import tqdm


def progress_bar(name: str, total: int | None):
    """A bar for one stage. ``total`` is None when the count is not known yet."""
    return tqdm(
        total=total,
        desc=name,
        unit="entity",
        dynamic_ncols=True,
        file=sys.stderr,
        leave=True,
    )
