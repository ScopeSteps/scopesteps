"""Binds `change_control.client.get_request_origins` to `discussions`, which builds on it."""

from collections.abc import Collection, Mapping
from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.change_control.client import RequestOrigin, RequestOrigins
from scopesteps.discussions.client import thread_origins
from scopesteps.infrastructure.http import SessionDep


class _RequestOrigins:
    def __init__(self, session: Session) -> None:
        self._session = session

    def of(self, request_ids: Collection[UUID]) -> Mapping[UUID, RequestOrigin]:
        return {
            request_id: RequestOrigin(origin.thread_id, origin.item_title)
            for request_id, origin in thread_origins(self._session, request_ids).items()
        }


def resolve_request_origins(session: SessionDep) -> RequestOrigins:
    return _RequestOrigins(session)
