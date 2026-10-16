"""Retry policy declared by an operator home and applied by the runner."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from docorder.utils.errors import FatalError

log = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> RetryPolicy:
        raw = raw or {}
        attempts = int(raw.get("max_attempts", 1))
        if attempts < 1:
            raise ValueError("retry.max_attempts must be >= 1")
        return cls(
            max_attempts=attempts,
            backoff_seconds=float(raw.get("backoff_seconds", 0)),
        )


def call_with_retry(action: Callable[[], T], policy: RetryPolicy, *, label: str) -> T:
    last: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return action()
        except FatalError:
            raise
        except Exception as exc:
            last = exc
            if attempt >= policy.max_attempts:
                raise
            delay = policy.backoff_seconds * attempt
            log.warning("%s attempt %s/%s failed: %s", label, attempt, policy.max_attempts, exc)
            if delay > 0:
                time.sleep(delay)
    assert last is not None
    raise last
