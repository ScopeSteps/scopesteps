"""How publishing is going across every project, for the stuck-publish alert (ADR 0029). Counts
and an age only: no project, version, item or person."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scopesteps.jira_integration.infrastructure.orm import PublishRecord


@dataclass(frozen=True)
class PublishHealth:
    done: int
    failed: int
    sending: int
    oldest_sending_seconds: float
    """How long the oldest publish still sending has been at it; 0 when none is."""


def publish_health(session: Session, now: datetime) -> PublishHealth:
    """Two small queries over the publish table: counts by status, and the oldest still sending.
    A publish's `created_at` is when it was asked for, so the age includes any waiting."""
    rows = session.execute(
        select(PublishRecord.status, func.count()).group_by(PublishRecord.status)
    ).tuples()
    # Not dict(rows): the result has `keys()`, so dict() reads it as a mapping and fails.
    counts = {status: count for status, count in rows}  # noqa: C416
    oldest = session.scalar(
        select(func.min(PublishRecord.created_at)).where(PublishRecord.status == "sending")
    )
    return PublishHealth(
        done=counts.get("done", 0),
        failed=counts.get("failed", 0),
        sending=counts.get("sending", 0),
        oldest_sending_seconds=0.0 if oldest is None else max(0.0, (now - oldest).total_seconds()),
    )
