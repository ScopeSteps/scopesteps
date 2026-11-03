import logging
from typing import Any

import pytest

from scopesteps.agent.application.fallback import CIRCUIT_OPENED_EVENT, CircuitBreaker


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


def test_each_opening_is_sent_to_the_sink_once_with_counts_only() -> None:
    clock = Clock()
    events: list[dict[str, Any]] = []
    breaker = CircuitBreaker(threshold=2, cooldown_seconds=300, clock=clock, sink=events.append)

    for _ in range(3):
        breaker.record_failure()
    clock.now = 301
    breaker.is_open()
    breaker.record_failure()
    breaker.record_failure()

    assert (
        events
        == [
            {
                "name": CIRCUIT_OPENED_EVENT,
                "scopesteps.circuit.failures": 2,
                "scopesteps.circuit.cooldown_seconds": 300,
            }
        ]
        * 2
    )


def test_a_failing_sink_never_stops_the_breaker_opening(caplog: pytest.LogCaptureFixture) -> None:
    def broken(event: dict[str, Any]) -> None:
        raise RuntimeError("collector down")

    breaker = CircuitBreaker(threshold=1, sink=broken)

    with caplog.at_level(logging.WARNING, logger="scopesteps.agent.fallback"):
        breaker.record_failure()

    assert breaker.is_open()
    assert "Could not send a circuit event (RuntimeError)" in caplog.messages
