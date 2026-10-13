from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from scopesteps.backlog.domain.ids import BacklogVersionId
from scopesteps.backlog.domain.status import ScopeState, ScopeStatus, VersionHeader, scope_status
from scopesteps.backlog.domain.version import VersionState

START = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def _id(number: int) -> BacklogVersionId:
    return BacklogVersionId(UUID(int=number))


def _history(*states: str) -> list[VersionHeader]:
    """Versions numbered from 1 in the order they were created."""
    return [
        VersionHeader(_id(number), VersionState(state), START + timedelta(minutes=number))
        for number, state in enumerate(states, start=1)
    ]


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ((), ScopeStatus(ScopeState.NO_BASELINE)),
        (("rejected",), ScopeStatus(ScopeState.NO_BASELINE)),
        (("draft",), ScopeStatus(ScopeState.DRAFT_IN_PROGRESS, open_version_id=_id(1))),
        (("draft", "draft"), ScopeStatus(ScopeState.DRAFT_IN_PROGRESS, open_version_id=_id(2))),
        (
            ("in_review", "draft"),
            ScopeStatus(ScopeState.CANDIDATE_IN_REVIEW, open_version_id=_id(1)),
        ),
        (("draft", "approved"), ScopeStatus(ScopeState.BASELINE, 1, _id(2))),
        (("approved", "rejected"), ScopeStatus(ScopeState.BASELINE, 1, _id(1))),
        (("approved", "draft"), ScopeStatus(ScopeState.DRAFT_IN_PROGRESS, 1, _id(1), _id(2))),
        (
            ("approved", "in_review"),
            ScopeStatus(ScopeState.CANDIDATE_IN_REVIEW, 1, _id(1), _id(2)),
        ),
        (("approved", "draft", "approved"), ScopeStatus(ScopeState.BASELINE, 2, _id(3))),
    ],
)
def test_status_follows_the_versions(states: tuple[str, ...], expected: ScopeStatus) -> None:
    assert scope_status(_history(*states)) == expected


def test_the_order_versions_are_given_in_does_not_matter() -> None:
    history = _history("approved", "draft", "approved", "in_review")

    assert scope_status(list(reversed(history))) == scope_status(history)
