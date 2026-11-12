"""Jira publishing as metrics, for the stuck-publish alert (ADR 0029, ADR 0023): how many publishes
finished, how many failed, how many are still sending and how long the oldest has been at it.
Read from the publish table each time the metrics are exported, so they hold however publishes
end and whichever process sent them. Counts and an age only."""

from collections.abc import Callable, Iterable
from datetime import datetime

from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from sqlalchemy.orm import Session, sessionmaker

from scopesteps.infrastructure.database import utc_now
from scopesteps.jira_integration.client import PublishHealth, publish_health

_SCOPE = "scopesteps.jira_integration"


def register_publish_metrics(
    meter_provider: MeterProvider,
    session_factory: sessionmaker[Session],
    now: Callable[[], datetime] = utc_now,
) -> None:
    def read() -> PublishHealth:
        with session_factory() as session:
            return publish_health(session, now())

    def finished(_: CallbackOptions) -> Iterable[Observation]:
        health = read()
        return [
            Observation(health.done, {"scopesteps.publish.status": "done"}),
            Observation(health.failed, {"scopesteps.publish.status": "failed"}),
        ]

    def sending(_: CallbackOptions) -> Iterable[Observation]:
        return [Observation(read().sending)]

    def oldest(_: CallbackOptions) -> Iterable[Observation]:
        return [Observation(read().oldest_sending_seconds)]

    meter = meter_provider.get_meter(_SCOPE)
    meter.create_observable_counter(
        "scopesteps.jira.publishes.finished",
        callbacks=[finished],
        unit="{publish}",
        description="Jira publishes that ended, by status (done or failed)",
    )
    meter.create_observable_gauge(
        "scopesteps.jira.publishes.sending",
        callbacks=[sending],
        unit="{publish}",
        description="Jira publishes still sending",
    )
    meter.create_observable_gauge(
        "scopesteps.jira.publish.oldest_sending.age",
        callbacks=[oldest],
        unit="s",
        description="How long the oldest Jira publish still sending has been at it; 0 when none",
    )
