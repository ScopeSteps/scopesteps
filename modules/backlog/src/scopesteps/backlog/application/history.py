"""Listing a project's versions and comparing two of them. Both are reads for any member."""

from dataclasses import dataclass
from typing import Protocol

from scopesteps.backlog.application.candidates import VersionStore, get_version
from scopesteps.backlog.domain.history import (
    ItemChange,
    ListCursor,
    VersionListing,
    compare_items,
    decode_cursor,
    encode_cursor,
)
from scopesteps.backlog.domain.ids import BacklogVersionId
from scopesteps.backlog.domain.version import BacklogVersion
from scopesteps.backlog.domain.version_decision import DecisionReader, VersionDecision
from scopesteps.identity.client import ProjectAccess
from scopesteps.projects.client import ProjectId

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class VersionLister(Protocol):
    def newest_first(
        self, project_id: ProjectId, *, after: ListCursor | None, limit: int
    ) -> list[VersionListing]:
        """Up to `limit` versions ordered by creation time then id, both descending, starting
        after `after`."""
        ...


@dataclass(frozen=True)
class ListedVersion:
    version: VersionListing
    decision: VersionDecision | None
    """The approval or rejection, if the version was decided."""


@dataclass(frozen=True)
class VersionPage:
    versions: tuple[ListedVersion, ...]
    next_cursor: str | None
    """Pass it back to read the next, older page. None on the last page."""


def list_versions(
    store: VersionLister,
    decisions: DecisionReader,
    access: ProjectAccess,
    *,
    limit: int,
    cursor: str | None,
) -> VersionPage:
    """One page of the project's versions, newest first, each with how it was decided."""
    access.require_member()
    after = None if cursor is None else decode_cursor(cursor)
    # One extra row tells whether an older page exists without a count query.
    listings = store.newest_first(access.project_id, after=after, limit=limit + 1)
    page = listings[:limit]
    decided = decisions([listing.id for listing in page])
    last = page[-1] if page else None
    return VersionPage(
        versions=tuple(ListedVersion(listing, decided.get(listing.id)) for listing in page),
        next_cursor=encode_cursor(ListCursor(last.created_at, last.id))
        if last is not None and len(listings) > limit
        else None,
    )


@dataclass(frozen=True)
class Comparison:
    base: BacklogVersion
    candidate: BacklogVersion
    changes: tuple[ItemChange, ...]


def compare_versions(
    store: VersionStore,
    access: ProjectAccess,
    base_id: BacklogVersionId,
    candidate_id: BacklogVersionId,
) -> Comparison:
    """What changes from `base` to `candidate`, both versions of the project `access` names. A
    version of another project is reported exactly like a missing one."""
    base = get_version(store, access, base_id)
    candidate = get_version(store, access, candidate_id)
    return Comparison(base, candidate, compare_items(base.items, candidate.items))
