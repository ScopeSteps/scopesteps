"""Editing a draft and checking whether it can be approved."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Protocol

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.backlog.application.candidates import CitationChecker, VersionStore
from scopesteps.backlog.domain.editing import (
    ItemEdit,
    VersionChangedError,
    VersionNotDraftError,
    apply_edit,
)
from scopesteps.backlog.domain.ids import BacklogVersionId, ItemId
from scopesteps.backlog.domain.review import CheckResult, cited_evidence, review_checks
from scopesteps.backlog.domain.version import BacklogVersion, Item, VersionState, content_hash
from scopesteps.evidence.client import Citation
from scopesteps.identity.client import ProjectAccess, ProjectAccessResolver, Role, UserId
from scopesteps.kernel.errors import ConflictError, NotFoundError
from scopesteps.kernel.ids import new_id


class IdempotencyKeyReusedError(ConflictError):
    code = "IDEMPOTENCY_KEY_REUSED"


@dataclass(frozen=True)
class Receipt:
    """An accepted edit, kept so a retry with the same Idempotency-Key does not apply it twice."""

    actor_id: UserId
    idempotency_key: str
    version_id: BacklogVersionId
    fingerprint: str
    created_at: datetime


class ReceiptStore(Protocol):
    def find(self, actor_id: UserId, idempotency_key: str) -> Receipt | None: ...

    def add(self, receipt: Receipt) -> None: ...


class DraftStore(VersionStore, Protocol):
    def save_item(
        self, version: BacklogVersion, item: Item, *, expected_revision: int, content_hash: str
    ) -> bool:
        """Store the item and move the version to the next revision, within the caller's
        transaction. False, changing nothing, if the version is no longer a draft at
        `expected_revision`."""
        ...


@dataclass(frozen=True)
class EditItem:
    idempotency_key: str
    item_id: ItemId
    expected_revision: int
    edit: ItemEdit


@dataclass(frozen=True)
class Review:
    """A version with the result of every approval check, as of its current revision."""

    version: BacklogVersion
    checks: tuple[CheckResult, ...]

    @property
    def ready(self) -> bool:
        return self.version.state is VersionState.DRAFT and all(c.passed for c in self.checks)


def edit_item(
    store: DraftStore,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    command: EditItem,
    now: datetime,
) -> BacklogVersion:
    """Apply an editor's change to one item of a draft at `expected_revision`.

    A retry with the same Idempotency-Key returns the version as it is now without applying the
    edit again. An edit that changes nothing saves nothing and keeps the revision.
    """
    version, access = _load(store, resolve, version_id)
    access.require_role(Role.EDITOR)
    actor = access.actor
    fingerprint = _fingerprint(version_id, command)
    receipt = receipts.find(actor.user_id, command.idempotency_key)
    if receipt is not None:
        if receipt.fingerprint != fingerprint:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for another request"
            )
        return version

    require_draft(version)
    require_revision(version, command.expected_revision)
    item = next((item for item in version.items if item.id == command.item_id), None)
    if item is None:
        raise NotFoundError("Backlog item not found")
    edited, summary = apply_edit(item, command.edit, editor=actor.user_id, now=now, new_id=new_id)
    if summary.changes_anything:
        items = tuple(edited if i.id == item.id else i for i in version.items)
        new_hash = content_hash(items, version.decisions, version.out_of_scope)
        if not store.save_item(
            version, edited, expected_revision=version.revision, content_hash=new_hash
        ):
            raise _changed(None)
        audit.record(
            project_id=version.project_id,
            actor=AuditActor.user(actor),
            type=EventType.BACKLOG_ITEM_EDITED,
            subjects=(
                Subject(SubjectKind.BACKLOG_VERSION, version.id),
                Subject(SubjectKind.ITEM, item.id),
            ),
            summary=f"Edited a {item.kind} in draft revision {version.revision}: "
            + summary.describe(),
            occurred_at=now,
        )
        version = replace(
            version, items=items, revision=version.revision + 1, content_hash=new_hash
        )
    receipts.add(Receipt(actor.user_id, command.idempotency_key, version.id, fingerprint, now))
    return version


def review_version(
    store: VersionStore,
    check_citations: CitationChecker,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    expected_revision: int,
) -> Review:
    """Run every approval check on the version at `expected_revision`. Changes nothing, so any
    member may ask."""
    version, _access = _load(store, resolve, version_id)
    require_revision(version, expected_revision)
    return Review(version, run_checks(check_citations, version))


def run_checks(
    check_citations: CitationChecker, version: BacklogVersion
) -> tuple[CheckResult, ...]:
    citations = [
        Citation(e.source_version_id, e.block_id, e.quote) for e in cited_evidence(version)
    ]
    invalid = check_citations(version.project_id, citations) if citations else []
    return review_checks(version, [problem.message for problem in invalid])


def require_draft(version: BacklogVersion) -> None:
    if version.state is not VersionState.DRAFT:
        raise VersionNotDraftError(
            f"This backlog version is {version.state.value.replace('_', ' ')}, so it cannot "
            "change. Later work starts a new draft.",
            details={"state": version.state.value},
        )


def require_revision(version: BacklogVersion, expected_revision: int) -> None:
    if version.revision != expected_revision:
        raise _changed(version)


def _changed(version: BacklogVersion | None) -> VersionChangedError:
    details: dict[str, object] = (
        {}
        if version is None
        else {"current_revision": version.revision, "content_hash": version.content_hash}
    )
    return VersionChangedError(
        "The backlog changed since you opened it. Reload it and review it again.",
        details=details,
    )


def _load(
    store: VersionStore, resolve: ProjectAccessResolver, version_id: BacklogVersionId
) -> tuple[BacklogVersion, ProjectAccess]:
    version = store.get(version_id)
    if version is None:
        raise NotFoundError("Backlog version not found")
    access = resolve(version.project_id)
    # A version in a project the actor has no role in is reported exactly like a missing one.
    if not access.roles:
        raise NotFoundError("Backlog version not found")
    return version, access


def _fingerprint(version_id: BacklogVersionId, command: EditItem) -> str:
    canonical = json.dumps(
        [
            "edit_item",
            str(version_id),
            str(command.item_id),
            command.expected_revision,
            asdict(command.edit),
        ],
        default=str,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
