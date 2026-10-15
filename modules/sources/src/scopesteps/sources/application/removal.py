from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.identity.client import ProjectAccess, Role, UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.projects.client import ProjectId
from scopesteps.sources.application.upload import short_filename
from scopesteps.sources.domain.errors import SourceChangedError, SourceInUseError
from scopesteps.sources.domain.ids import SourceId, SourceVersionId
from scopesteps.sources.domain.source import Source, SourceKind, SourceVersion

SourceUserKind = Literal["run", "backlog_version", "person"]


@dataclass(frozen=True)
class SourceUse:
    """Something stored elsewhere that refers to one of a source's versions."""

    kind: SourceUserKind
    id: UUID


@dataclass(frozen=True)
class RemovedSource:
    id: SourceId
    project_id: ProjectId
    kind: SourceKind
    number: int
    removed_at: datetime
    removed_by: UserId

    @classmethod
    def of(cls, source: Source, removed_at: datetime, removed_by: UserId) -> RemovedSource:
        return cls(source.id, source.project_id, source.kind, source.number, removed_at, removed_by)


SourceUsageReader = Callable[[ProjectId, Collection[SourceVersionId]], list[SourceUse]]
"""Everything in the project that refers to any of the given versions: runs that pinned them,
backlog versions made from or citing them, people whose evidence quotes them. Performs no access
check."""


class SourceRemover(Protocol):
    def get_source(self, project_id: ProjectId, source_id: SourceId) -> Source | None: ...

    def latest_version_of(self, source_id: SourceId) -> SourceVersion: ...

    def version_ids(self, source_id: SourceId) -> list[SourceVersionId]: ...

    def mark_removed(self, source_id: SourceId, removed_by: UserId, removed_at: datetime) -> bool:
        """Compare-and-set: False, changing nothing, if the source was already removed."""
        ...


_USER_NAMES: dict[SourceUserKind, tuple[str, str]] = {
    "run": ("run", "runs"),
    "backlog_version": ("backlog version", "backlog versions"),
    "person": ("person", "people"),
}


def remove_source(
    store: SourceRemover,
    audit: AuditRecorder,
    usage: SourceUsageReader,
    access: ProjectAccess,
    source_id: SourceId,
    now: datetime,
) -> RemovedSource:
    """Take an unused source out of the project's current set (ADR 0009). Nothing is deleted.

    Removing a removed source returns it unchanged and records nothing.
    """
    access.require_role(Role.EDITOR)
    source = store.get_source(access.project_id, source_id)
    # A change request's text is not one of the project's sources to manage.
    if source is None or source.kind is SourceKind.CHANGE_REQUEST:
        raise NotFoundError("Source not found")
    if source.removed_at is not None and source.removed_by is not None:
        return RemovedSource.of(source, source.removed_at, source.removed_by)

    uses = usage(access.project_id, store.version_ids(source.id))
    if uses:
        used_by: dict[SourceUserKind, int] = {}
        for use in uses:
            used_by[use.kind] = used_by.get(use.kind, 0) + 1
        raise SourceInUseError(
            f"This source is used by {_describe(used_by)}, so it cannot be removed. "
            "Its paragraphs stay available as evidence.",
            details={"source_id": str(source.id), "used_by": used_by},
        )

    if not store.mark_removed(source.id, access.actor.user_id, now):
        # A concurrent request removed it first and recorded the event; a retry returns it.
        raise SourceChangedError("The source changed while it was being removed. Try again.")
    latest = store.latest_version_of(source.id)
    audit.record(
        project_id=access.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.SOURCE_REMOVED,
        subjects=(Subject(SubjectKind.SOURCE, source.id),),
        summary=f"Removed the {source.kind.label} {short_filename(latest.filename)}",
        occurred_at=now,
    )
    return RemovedSource.of(source, now, access.actor.user_id)


def _describe(used_by: dict[SourceUserKind, int]) -> str:
    parts = [
        f"{count} {_USER_NAMES[kind][0 if count == 1 else 1]}" for kind, count in used_by.items()
    ]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
