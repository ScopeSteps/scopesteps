import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.audit.domain.event import AuditEvent, FeedCursor, InvalidCursorError
from scopesteps.audit.domain.ids import AuditEventId
from scopesteps.identity.client import ProjectAccess
from scopesteps.projects.client import ProjectId

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


class EventReader(Protocol):
    def newest_first(
        self, project_id: ProjectId, *, after: FeedCursor | None, limit: int
    ) -> list[AuditEvent]:
        """Up to `limit` events ordered by time then id, both descending, starting after `after`."""
        ...


@dataclass(frozen=True)
class ActivityPage:
    events: tuple[AuditEvent, ...]
    next_cursor: str | None
    """Pass it back to read the next, older page. None on the last page."""


def list_activity(
    store: EventReader, access: ProjectAccess, *, limit: int, cursor: str | None
) -> ActivityPage:
    """One page of the project's log, newest first. Every member sees the same log."""
    access.require_member()
    after = None if cursor is None else decode_cursor(cursor)
    # One extra row tells whether an older page exists without a count query.
    events = store.newest_first(access.project_id, after=after, limit=limit + 1)
    page = events[:limit]
    more = len(events) > limit
    return ActivityPage(
        events=tuple(page),
        next_cursor=encode_cursor(FeedCursor(page[-1].occurred_at, page[-1].id)) if more else None,
    )


def encode_cursor(cursor: FeedCursor) -> str:
    raw = f"{cursor.occurred_at.isoformat()}|{cursor.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(value: str) -> FeedCursor:
    try:
        occurred_at, _, event_id = base64.urlsafe_b64decode(value).decode().partition("|")
        cursor = FeedCursor(datetime.fromisoformat(occurred_at), AuditEventId(UUID(event_id)))
    except (ValueError, binascii.Error) as error:
        raise InvalidCursorError("The cursor is not one this feed returned") from error
    if cursor.occurred_at.tzinfo is None:
        raise InvalidCursorError("The cursor is not one this feed returned")
    return cursor
