"""Change requests: recording one, recording its analysis, and reading them back.

The agent's change run creates the request and reports its analysis through this module's
client, in the transactions that store the run's own state; this module owns the record and how
it reads (ADR 0011). Deciding on the candidate belongs to approval and rejection.
"""

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.backlog.client import (
    BacklogVersion,
    BacklogVersionId,
    DecisionId,
    Item,
    ItemChange,
    ScopeNote,
    approved_items,
    compare_versions,
)
from scopesteps.change_control.domain.change_request import (
    ChangeAnalysis,
    ChangeImpact,
    ChangeRequest,
    ChangeRequestStatus,
    ChangeSummary,
    ListCursor,
    ScopeCount,
    decode_cursor,
    encode_cursor,
)
from scopesteps.change_control.domain.ids import ChangeRequestId, ChangeSetId
from scopesteps.identity.client import ProjectAccess, ProjectAccessResolver, UserId
from scopesteps.kernel.errors import ConflictError, NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class ChangeRequestStore(Protocol):
    def get(self, request_id: ChangeRequestId) -> ChangeRequest | None: ...

    def by_run(self, run_id: UUID) -> ChangeRequest | None: ...

    def by_candidate(self, version_id: BacklogVersionId) -> ChangeRequest | None: ...

    def next_number(self, project_id: ProjectId) -> int:
        """One more than the project's highest request number."""
        ...

    def add(self, request: ChangeRequest) -> None:
        """Insert within the caller's transaction. Raises the database's integrity error if a
        concurrent request took the same number or run."""
        ...

    def save(self, request: ChangeRequest, *, expected_revision: int) -> bool:
        """Compare-and-set: False, and nothing written, if the stored revision has moved on."""
        ...

    def newest_first(
        self, project_id: ProjectId, *, after: ListCursor | None, limit: int
    ) -> list[ChangeRequest]:
        """Up to `limit` requests ordered by time then id, both descending, after `after`."""
        ...


class VersionReader(Protocol):
    def load(self, version_id: UUID) -> BacklogVersion | None: ...

    def baseline_numbers(self, version_ids: Sequence[UUID]) -> dict[UUID, int]:
        """The baseline number of each approved version among `version_ids` (1 for v1)."""
        ...


@dataclass(frozen=True)
class OpenChangeRequest:
    project_id: ProjectId
    text: str
    requested_by: UserId
    requested_by_name: str
    base_version_id: BacklogVersionId
    base_content_hash: str
    source_version_id: UUID
    run_id: UUID


def open_change_request(
    store: ChangeRequestStore, command: OpenChangeRequest, now: datetime
) -> ChangeRequest:
    """Record a request that is about to be analysed. The caller has checked access, the text and
    the baseline, stored the text as a source version, and records the action."""
    request = ChangeRequest(
        id=ChangeRequestId(new_id()),
        project_id=command.project_id,
        number=store.next_number(command.project_id),
        text=command.text,
        requested_by=command.requested_by,
        requested_by_name=command.requested_by_name,
        requested_at=now,
        base_version_id=command.base_version_id,
        base_content_hash=command.base_content_hash,
        source_version_id=command.source_version_id,
        run_id=command.run_id,
        status=ChangeRequestStatus.ANALYZING,
        revision=1,
    )
    store.add(request)
    return request


def record_analysis(
    store: ChangeRequestStore,
    versions: VersionReader,
    run_id: UUID,
    analysis: ChangeAnalysis,
    now: datetime,
) -> ChangeRequest:
    """Record what the run's analysis proposed, in the caller's transaction. The summary is
    counted from a stable-id comparison of the saved candidate with the baseline, never taken
    from the model."""
    request = _of_run(store, run_id)
    summary = None
    if analysis.candidate_version_id is not None:
        base, candidate = _versions(
            versions, request.base_version_id, analysis.candidate_version_id
        )
        summary = summarize(compare_versions(base, candidate))
    updated = request.analyzed(analysis, summary, ChangeSetId(new_id()), now)
    _save(store, request, updated)
    return updated


def record_failure(
    store: ChangeRequestStore, run_id: UUID, code: str, now: datetime
) -> ChangeRequest | None:
    """Mark the run's request failed, in the caller's transaction. None if the run analysed no
    request or its request was already decided."""
    request = store.by_run(run_id)
    if request is None or request.status is not ChangeRequestStatus.ANALYZING:
        return None
    updated = request.failed(code, now)
    _save(store, request, updated)
    return updated


def summarize(changes: Sequence[ItemChange]) -> ChangeSummary:
    return ChangeSummary(
        added=sum(1 for c in changes if c.kind == "add_item"),
        changed=sum(1 for c in changes if c.kind == "modify_item"),
        removed=sum(1 for c in changes if c.kind == "remove_item"),
    )


def measure_impact(
    base: BacklogVersion,
    candidate: BacklogVersion,
    changes: Sequence[ItemChange],
    scope_decisions: int,
) -> ChangeImpact:
    """The scope before and after, counted from `changes`, the stable-id comparison of the two
    versions as approval freezes them. Nothing here comes from the model (ADR 0011).

    An item that changes between epic and story leaves one kind and joins the other, so each
    kind's before and after still add up; it counts as changed in `summarize`."""
    before = approved_items(base)
    after = approved_items(candidate)
    tally: Counter[tuple[str, str]] = Counter()
    for item in before:
        tally[item.kind, "before"] += 1
        tally["criterion", "before"] += len(item.criteria)
    for item in after:
        tally[item.kind, "after"] += 1
        tally["criterion", "after"] += len(item.criteria)
    for change in changes:
        old, new = change.before, change.after
        if old is None and new is not None:
            _add(tally, new, "added")
        elif new is None and old is not None:
            _add(tally, old, "removed")
        elif old is not None and new is not None:
            if old.kind == new.kind:
                tally[new.kind, "changed"] += 1
            else:
                tally[old.kind, "removed"] += 1
                tally[new.kind, "added"] += 1
            for criterion in change.criteria:
                tally[
                    "criterion", "changed" if criterion.kind == "modified" else criterion.kind
                ] += 1

    def count(kind: str) -> ScopeCount:
        changed, removed = tally[kind, "changed"], tally[kind, "removed"]
        return ScopeCount(
            before=tally[kind, "before"],
            after=tally[kind, "after"],
            added=tally[kind, "added"],
            changed=changed,
            removed=removed,
            unchanged=tally[kind, "before"] - changed - removed,
        )

    return ChangeImpact(
        epics=count("epic"),
        stories=count("story"),
        criteria=count("criterion"),
        scope_decisions=scope_decisions,
    )


def _add(tally: Counter[tuple[str, str]], item: Item, side: str) -> None:
    """An item added or removed as a whole, with all of its criteria."""
    tally[item.kind, side] += 1
    tally["criterion", side] += len(item.criteria)


@dataclass(frozen=True)
class ListedRequest:
    request: ChangeRequest
    base_version_number: int | None
    approved_version_number: int | None = None
    """The baseline number the request's approved candidate became; None unless approved."""
    summary: ChangeSummary | None = None
    """Counted when the request is read, like `impact`; None without a candidate."""
    impact: ChangeImpact | None = None
    """What the candidate does to the baseline's scope; None without a candidate."""


@dataclass(frozen=True)
class ChangeRequestPage:
    requests: tuple[ListedRequest, ...]
    next_cursor: str | None
    """Pass it back to read the next, older page. None on the last page."""


def list_change_requests(
    store: ChangeRequestStore,
    versions: VersionReader,
    access: ProjectAccess,
    *,
    limit: int,
    cursor: str | None,
) -> ChangeRequestPage:
    """One page of the project's change requests, newest first. Any member may read them."""
    access.require_member()
    after = None if cursor is None else decode_cursor(cursor)
    # One extra row tells whether an older page exists without a count query.
    rows = store.newest_first(access.project_id, after=after, limit=limit + 1)
    page = rows[:limit]
    numbers = versions.baseline_numbers(list(_numbered_versions(page)))
    loaded = _VersionCache(versions)
    last = page[-1] if page else None
    return ChangeRequestPage(
        requests=tuple(_listed(r, numbers, loaded) for r in page),
        next_cursor=encode_cursor(ListCursor(last.requested_at, last.id))
        if last is not None and len(rows) > limit
        else None,
    )


def get_change_request(
    store: ChangeRequestStore,
    versions: VersionReader,
    resolve: ProjectAccessResolver,
    request_id: ChangeRequestId,
) -> ListedRequest:
    request = store.get(request_id)
    if request is None or not resolve(request.project_id).roles:
        # A request in a project the actor cannot see is reported exactly like a missing one.
        raise NotFoundError("Change request not found")
    numbers = versions.baseline_numbers(list(_numbered_versions([request])))
    return _listed(request, numbers, _VersionCache(versions))


def load_impacts(
    store: ChangeRequestStore, versions: VersionReader, request_ids: Collection[UUID]
) -> dict[ChangeRequestId, ChangeImpact]:
    """The current impact of each request that has a candidate, for showing beside the
    conversation event that reported its analysis. The caller has checked access."""
    loaded = _VersionCache(versions)
    impacts: dict[ChangeRequestId, ChangeImpact] = {}
    for request_id in request_ids:
        request = store.get(ChangeRequestId(request_id))
        if request is None:
            continue
        impact = _listed(request, {}, loaded).impact
        if impact is not None:
            impacts[request.id] = impact
    return impacts


def _numbered_versions(requests: Sequence[ChangeRequest]) -> set[UUID]:
    """The versions whose baseline numbers a page shows: each base, and each candidate."""
    ids = {r.base_version_id for r in requests}
    ids.update(r.candidate_version_id for r in requests if r.candidate_version_id is not None)
    return ids


class _VersionCache:
    """Loads each version once per read: the requests of a page often share a baseline."""

    def __init__(self, versions: VersionReader) -> None:
        self._versions = versions
        self._loaded: dict[UUID, BacklogVersion | None] = {}

    def load(self, version_id: UUID) -> BacklogVersion | None:
        if version_id not in self._loaded:
            self._loaded[version_id] = self._versions.load(version_id)
        return self._loaded[version_id]


def _listed(
    request: ChangeRequest, numbers: Mapping[UUID, int], versions: _VersionCache
) -> ListedRequest:
    approved = (
        numbers.get(request.candidate_version_id)
        if request.status is ChangeRequestStatus.APPROVED
        and request.candidate_version_id is not None
        else None
    )
    listed = ListedRequest(request, numbers.get(request.base_version_id), approved)
    if request.candidate_version_id is None:
        return listed
    # Counted on every read, not taken from the analysis: an approver may still reject an agent
    # suggestion on the candidate, which changes what approval would freeze.
    base, candidate = _versions(versions, request.base_version_id, request.candidate_version_id)
    changes = compare_versions(base, candidate)
    return replace(
        listed,
        summary=summarize(changes),
        impact=measure_impact(base, candidate, changes, len(request.scope_reversals)),
    )


@dataclass(frozen=True)
class ChangeSet:
    """A candidate compared with the baseline it changes, with the analysis that proposed it."""

    id: ChangeSetId
    request: ChangeRequest
    base: BacklogVersion
    candidate: BacklogVersion
    changes: tuple[ItemChange, ...]
    removed_exclusions: tuple[ScopeNote, ...]
    open_decision_ids: tuple[DecisionId, ...]
    """Decisions the candidate adds that nobody has settled yet, scope decisions included."""


def get_change_set(
    store: ChangeRequestStore,
    versions: VersionReader,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
) -> ChangeSet:
    """The change set of a candidate a change request proposed. Any member may read it."""
    request = store.by_candidate(version_id)
    if request is None or request.change_set_id is None or not resolve(request.project_id).roles:
        raise NotFoundError("No change set proposes this backlog version")
    base, candidate = _versions(versions, request.base_version_id, version_id)
    known = {decision.id for decision in base.decisions}
    return ChangeSet(
        id=request.change_set_id,
        request=request,
        base=base,
        candidate=candidate,
        changes=compare_versions(base, candidate),
        removed_exclusions=tuple(n for n in base.out_of_scope if n not in candidate.out_of_scope),
        open_decision_ids=tuple(
            d.id for d in candidate.decisions if d.id not in known and not d.is_resolved
        ),
    )


def _of_run(store: ChangeRequestStore, run_id: UUID) -> ChangeRequest:
    request = store.by_run(run_id)
    if request is None:
        raise NotFoundError("No change request belongs to this run")
    return request


def _versions(
    versions: VersionReader | _VersionCache, base_id: UUID, candidate_id: UUID
) -> tuple[BacklogVersion, BacklogVersion]:
    base = versions.load(base_id)
    candidate = versions.load(candidate_id)
    if base is None or candidate is None:
        raise NotFoundError("Backlog version not found")
    return base, candidate


def _save(store: ChangeRequestStore, before: ChangeRequest, after: ChangeRequest) -> None:
    if not store.save(after, expected_revision=before.revision):
        raise ConflictError("The change request changed while saving. Try again.")
