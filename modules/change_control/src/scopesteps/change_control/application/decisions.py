"""Approving a draft as the project's next baseline, or rejecting it.

Each decision is one transaction: the version is frozen or rejected, the decision and its audit
event are recorded and, for an approval, the baseline moves (ADR 0008). Every step is checked
against what the caller saw, so a stale or concurrent request changes nothing.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.backlog.client import (
    BacklogVersionId,
    CheckResult,
    VersionChangedError,
    VersionNotDraftError,
    VersionState,
    VersionSummary,
)
from scopesteps.change_control.domain.errors import (
    ApprovalBlockedError,
    BaselineChangedError,
    IdempotencyKeyReusedError,
)
from scopesteps.change_control.domain.ids import ApprovalId
from scopesteps.identity.client import ProjectAccess, ProjectAccessResolver, Role, UserId
from scopesteps.kernel.errors import NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId

DecisionKind = Literal["approved", "rejected"]


@dataclass(frozen=True)
class ScopeDecision:
    """An approval or rejection of one exact revision of a draft. Never changed once recorded."""

    id: ApprovalId
    project_id: ProjectId
    version_id: BacklogVersionId
    decision: DecisionKind
    revision: int
    content_hash: str
    baseline_number: int | None
    """1 for the project's first approved baseline, 2 for the next; None for a rejection."""
    previous_baseline_id: BacklogVersionId | None
    """The baseline when the decision was made, which an approval replaced."""
    reason: str | None
    decided_by: UserId
    decided_at: datetime


@dataclass(frozen=True)
class Receipt:
    """An accepted decision, kept so a retry with the same Idempotency-Key does not act twice."""

    actor_id: UserId
    idempotency_key: str
    approval_id: ApprovalId
    fingerprint: str
    created_at: datetime


class Versions(Protocol):
    """The backlog versions decisions are made on, in the caller's transaction."""

    def summary(self, version_id: BacklogVersionId) -> VersionSummary | None: ...

    def checks(self, version_id: BacklogVersionId) -> tuple[CheckResult, ...]: ...

    def freeze(
        self, version_id: BacklogVersionId, *, expected_revision: int, content_hash: str
    ) -> bool:
        """Make the draft approved and unchangeable. False, changing nothing, if it is no longer
        a draft at exactly that revision and hash."""
        ...

    def reject(self, version_id: BacklogVersionId, *, expected_revision: int) -> bool:
        """Mark the draft rejected. False, changing nothing, if it is no longer a draft at that
        revision."""
        ...


class DecisionStore(Protocol):
    def get(self, approval_id: ApprovalId) -> ScopeDecision | None: ...

    def current_baseline(self, project_id: ProjectId) -> ScopeDecision | None:
        """The approval with the highest baseline number, if the project has one."""
        ...

    def add(self, decision: ScopeDecision) -> None:
        """Insert within the caller's transaction. Raises the database's integrity error if the
        version already has a decision or the project already has that baseline number."""
        ...

    def find_receipt(self, actor_id: UserId, idempotency_key: str) -> Receipt | None: ...

    def add_receipt(self, receipt: Receipt) -> None: ...


@dataclass(frozen=True)
class Approve:
    idempotency_key: str
    expected_revision: int
    content_hash: str
    expected_baseline_id: BacklogVersionId | None


@dataclass(frozen=True)
class Reject:
    idempotency_key: str
    expected_revision: int
    reason: str


@dataclass(frozen=True)
class DecisionView:
    decision: ScopeDecision
    current_baseline: ScopeDecision | None


def approve(
    versions: Versions,
    decisions: DecisionStore,
    audit: AuditRecorder,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    command: Approve,
    now: datetime,
) -> DecisionView:
    """Approve the draft at exactly the revision and hash the approver reviewed, as the baseline
    after `expected_baseline_id`. Needs the approver role.

    Every approval check runs again here. A retry with the same Idempotency-Key returns the
    recorded decision without checking anything again.
    """
    version, access = _load(versions, resolve, version_id)
    access.require_role(Role.APPROVER)
    fingerprint = _fingerprint(
        "approve",
        version_id,
        command.expected_revision,
        command.content_hash,
        None if command.expected_baseline_id is None else str(command.expected_baseline_id),
    )
    replayed = _replayed(decisions, access, command.idempotency_key, fingerprint)
    if replayed is not None:
        return replayed

    _require_exact_draft(version, command.expected_revision, command.content_hash)
    baseline = decisions.current_baseline(version.project_id)
    baseline_id = None if baseline is None else baseline.version_id
    if command.expected_baseline_id != baseline_id or version.base_version_id != baseline_id:
        raise BaselineChangedError(
            "The project's baseline is not the one this draft was reviewed against. Reload "
            "and review it again.",
            details={
                "current_baseline_id": None if baseline_id is None else str(baseline_id),
                "base_version_id": None
                if version.base_version_id is None
                else str(version.base_version_id),
            },
        )
    checks = versions.checks(version_id)
    if not all(check.passed for check in checks):
        raise ApprovalBlockedError(
            "This draft cannot be approved until every check passes.",
            details={"checks": [_check_json(check) for check in checks]},
        )
    if not versions.freeze(
        version_id, expected_revision=version.revision, content_hash=version.content_hash
    ):
        raise _changed()

    number = 1 if baseline is None else (baseline.baseline_number or 0) + 1
    decision = ScopeDecision(
        id=ApprovalId(new_id()),
        project_id=version.project_id,
        version_id=version_id,
        decision="approved",
        revision=version.revision,
        content_hash=version.content_hash,
        baseline_number=number,
        previous_baseline_id=baseline_id,
        reason=None,
        decided_by=access.actor.user_id,
        decided_at=now,
    )
    decisions.add(decision)
    audit.record(
        project_id=version.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.BACKLOG_APPROVED,
        subjects=(
            Subject(SubjectKind.BACKLOG_VERSION, version_id),
            Subject(SubjectKind.APPROVAL, decision.id),
        ),
        summary=(
            f"Approved baseline v{number} from draft revision {version.revision}, with "
            f"{_count(version.epics, 'epic', 'epics')} and "
            f"{_count(version.stories, 'story', 'stories')}"
        ),
        occurred_at=now,
    )
    decisions.add_receipt(
        Receipt(access.actor.user_id, command.idempotency_key, decision.id, fingerprint, now)
    )
    return DecisionView(decision, decision)


def reject(
    versions: Versions,
    decisions: DecisionStore,
    audit: AuditRecorder,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    command: Reject,
    now: datetime,
) -> DecisionView:
    """Reject the draft at `expected_revision`. The baseline stays as it is. Needs the approver
    role."""
    version, access = _load(versions, resolve, version_id)
    access.require_role(Role.APPROVER)
    reason = command.reason.strip()
    fingerprint = _fingerprint("reject", version_id, command.expected_revision, reason)
    replayed = _replayed(decisions, access, command.idempotency_key, fingerprint)
    if replayed is not None:
        return replayed

    _require_exact_draft(version, command.expected_revision, None)
    if not versions.reject(version_id, expected_revision=version.revision):
        raise _changed()
    baseline = decisions.current_baseline(version.project_id)
    decision = ScopeDecision(
        id=ApprovalId(new_id()),
        project_id=version.project_id,
        version_id=version_id,
        decision="rejected",
        revision=version.revision,
        content_hash=version.content_hash,
        baseline_number=None,
        previous_baseline_id=None if baseline is None else baseline.version_id,
        reason=reason,
        decided_by=access.actor.user_id,
        decided_at=now,
    )
    decisions.add(decision)
    audit.record(
        project_id=version.project_id,
        actor=AuditActor.user(access.actor),
        type=EventType.BACKLOG_REJECTED,
        subjects=(
            Subject(SubjectKind.BACKLOG_VERSION, version_id),
            Subject(SubjectKind.APPROVAL, decision.id),
        ),
        # The reason is the approver's own text and stays out of the shared log.
        summary=f"Rejected draft revision {version.revision}; the baseline is unchanged",
        occurred_at=now,
    )
    decisions.add_receipt(
        Receipt(access.actor.user_id, command.idempotency_key, decision.id, fingerprint, now)
    )
    return DecisionView(decision, baseline)


def _load(
    versions: Versions, resolve: ProjectAccessResolver, version_id: BacklogVersionId
) -> tuple[VersionSummary, ProjectAccess]:
    version = versions.summary(version_id)
    if version is None:
        raise NotFoundError("Backlog version not found")
    access = resolve(version.project_id)
    # A version in a project the actor has no role in is reported exactly like a missing one.
    if not access.roles:
        raise NotFoundError("Backlog version not found")
    return version, access


def _require_exact_draft(
    version: VersionSummary, expected_revision: int, content_hash: str | None
) -> None:
    if version.state is not VersionState.DRAFT:
        raise VersionNotDraftError(
            f"This backlog version is already {version.state.value.replace('_', ' ')}.",
            details={"state": version.state.value},
        )
    if version.revision != expected_revision or (
        content_hash is not None and version.content_hash != content_hash
    ):
        raise VersionChangedError(
            "The backlog changed since you reviewed it. Reload it and review it again.",
            details={"current_revision": version.revision, "content_hash": version.content_hash},
        )


def _changed() -> VersionChangedError:
    return VersionChangedError(
        "The backlog changed since you reviewed it. Reload it and review it again."
    )


def _replayed(
    decisions: DecisionStore, access: ProjectAccess, idempotency_key: str, fingerprint: str
) -> DecisionView | None:
    receipt = decisions.find_receipt(access.actor.user_id, idempotency_key)
    if receipt is None:
        return None
    if receipt.fingerprint != fingerprint:
        raise IdempotencyKeyReusedError("This Idempotency-Key was already used for another request")
    decision = decisions.get(receipt.approval_id)
    if decision is None:
        raise NotFoundError("Decision not found")
    return DecisionView(decision, decisions.current_baseline(decision.project_id))


def _check_json(check: CheckResult) -> dict[str, object]:
    return {
        "code": check.code.value,
        "title": check.title,
        "passed": check.passed,
        "problems": list(check.problems),
        "problem_count": check.problem_count,
    }


def _count(number: int, one: str, many: str) -> str:
    return f"{number} {one if number == 1 else many}"


def _fingerprint(operation: str, version_id: BacklogVersionId, *values: str | int | None) -> str:
    canonical = json.dumps([operation, str(version_id), *values])
    return hashlib.sha256(canonical.encode()).hexdigest()
