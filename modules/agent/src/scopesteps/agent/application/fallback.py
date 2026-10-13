"""Opt-in fallback to a backup provider when the primary is unavailable (ADR 0006).

A run uses one model from start to finish. It may move to the backup only before its first
successful call, when nothing in it depends on the primary yet, and only for availability errors
(overload, timeout, rate limit), never for bad output. A circuit breaker sends new runs straight
to the backup while the primary keeps failing, so each run does not wait out its timeouts first.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from scopesteps.agent.application.ports import ModelProvider

AVAILABILITY_ERRORS = frozenset({"MODEL_UNAVAILABLE", "MODEL_TIMEOUT", "MODEL_QUOTA"})


@dataclass(frozen=True)
class ServedModel:
    provider: ModelProvider
    provider_name: str
    model_id: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.provider_name, self.model_id)


@dataclass
class CircuitBreaker:
    """Opens after `threshold` primary availability failures within `window_seconds` and stays
    open for `cooldown_seconds`. In memory, per process: enough for one API instance; several
    instances would share it through the database or a cache."""

    threshold: int = 3
    window_seconds: float = 120.0
    cooldown_seconds: float = 300.0
    clock: Callable[[], float] = time.monotonic
    _failures: deque[float] = field(default_factory=deque[float])
    _opened_at: float | None = None

    def record_failure(self) -> None:
        now = self.clock()
        self._failures.append(now)
        while self._failures and self._failures[0] < now - self.window_seconds:
            self._failures.popleft()
        if len(self._failures) >= self.threshold:
            self._opened_at = now

    def record_success(self) -> None:
        self._failures.clear()
        self._opened_at = None

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if self.clock() - self._opened_at >= self.cooldown_seconds:
            # Half-open: the next run tries the primary again; another failure reopens it.
            self._opened_at = None
            self._failures.clear()
            return False
        return True
