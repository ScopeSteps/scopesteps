import logging

import pytest

from scopesteps.agent.application.fallback import CircuitBreaker


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_breaker_opens_after_repeated_failures_and_logs_it_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = Clock()
    breaker = CircuitBreaker(threshold=3, window_seconds=120, cooldown_seconds=300, clock=clock)

    with caplog.at_level(logging.INFO, logger="scopesteps.agent.fallback"):
        for _ in range(4):
            breaker.record_failure()

    assert breaker.is_open()
    assert [r.getMessage() for r in caplog.records] == [
        "primary model circuit opened: new runs start on the backup"
    ]


def test_failures_outside_the_window_do_not_count() -> None:
    clock = Clock()
    breaker = CircuitBreaker(threshold=3, window_seconds=120, clock=clock)

    for at in (0, 100, 250):
        clock.now = at
        breaker.record_failure()

    assert not breaker.is_open()


def test_after_the_cooldown_the_primary_is_tried_again() -> None:
    clock = Clock()
    breaker = CircuitBreaker(threshold=1, cooldown_seconds=300, clock=clock)
    breaker.record_failure()

    clock.now = 301

    assert not breaker.is_open()
    breaker.record_failure()
    assert breaker.is_open(), "one more failure reopens it"
