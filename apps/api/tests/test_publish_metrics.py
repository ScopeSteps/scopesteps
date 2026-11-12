"""The Jira publishing metrics the stuck-publish alert reads: counts and an age, read from the
publish table at export time."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint

from scopesteps.api.publish_metrics import register_publish_metrics
from scopesteps.api.seed import DEMO_PROJECT_ID, LOCAL_REVIEWER_ID
from scopesteps.infrastructure.database import create_database_engine, create_session_factory
from scopesteps.jira_integration.infrastructure.orm import PublishRecord
from scopesteps.kernel.ids import new_id

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)

Metrics = dict[str, list[tuple[dict[str, str], float]]]


def _collect(database_url: str, statuses: list[tuple[str, timedelta]]) -> Metrics:
    """Publishes with these statuses, each asked for that long before NOW, then one export."""
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    with sessions() as session:
        for number, (status, age) in enumerate(statuses):
            session.add(
                PublishRecord(
                    id=new_id(),
                    project_id=DEMO_PROJECT_ID,
                    version_id=new_id(),
                    idempotency_key=f"metrics-{number}",
                    status=status,
                    created_by=LOCAL_REVIEWER_ID,
                    created_by_name="Local Reviewer",
                    created_at=NOW - age,
                    finished_at=None if status == "sending" else NOW,
                    last_error=None,
                    revision=1,
                    next_attempt_at=None,
                    failed_attempts=0,
                    leased_until=None,
                )
            )
        session.commit()
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    register_publish_metrics(provider, sessions, lambda: NOW)
    data = reader.get_metrics_data()
    engine.dispose()
    found: Metrics = {}
    assert data is not None
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                points = found.setdefault(metric.name, [])
                for point in metric.data.data_points:
                    assert isinstance(point, NumberDataPoint)
                    labels = {key: str(value) for key, value in (point.attributes or {}).items()}
                    points.append((labels, float(point.value)))
    return found


@pytest.fixture
def collect(seeded_database_url: str) -> Callable[[list[tuple[str, timedelta]]], Metrics]:
    return lambda statuses: _collect(seeded_database_url, statuses)


def test_the_oldest_publish_still_sending_gives_the_age_the_alert_reads(
    collect: Callable[[list[tuple[str, timedelta]]], Metrics],
) -> None:
    metrics = collect(
        [
            ("done", timedelta(hours=2)),
            ("failed", timedelta(hours=3)),
            ("sending", timedelta(minutes=45)),
            ("sending", timedelta(minutes=2)),
        ]
    )

    assert metrics["scopesteps.jira.publish.oldest_sending.age"] == [({}, 45 * 60.0)]
    assert metrics["scopesteps.jira.publishes.sending"] == [({}, 2.0)]
    assert sorted(metrics["scopesteps.jira.publishes.finished"], key=lambda p: p[1]) == [
        ({"scopesteps.publish.status": "done"}, 1.0),
        ({"scopesteps.publish.status": "failed"}, 1.0),
    ]


def test_with_nothing_sending_the_age_is_zero(
    collect: Callable[[list[tuple[str, timedelta]]], Metrics],
) -> None:
    metrics = collect([("done", timedelta(days=1))])

    assert metrics["scopesteps.jira.publish.oldest_sending.age"] == [({}, 0.0)]
    assert metrics["scopesteps.jira.publishes.sending"] == [({}, 0.0)]


def test_the_metrics_name_no_project_version_or_person(
    collect: Callable[[list[tuple[str, timedelta]]], Metrics],
) -> None:
    metrics = collect([("sending", timedelta(minutes=5)), ("failed", timedelta(minutes=9))])

    labels = {key for points in metrics.values() for attributes, _ in points for key in attributes}
    assert labels == {"scopesteps.publish.status"}
