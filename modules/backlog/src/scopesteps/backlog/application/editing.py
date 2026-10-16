"""Editing a draft and checking whether it can be approved."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.audit.client import AuditActor, AuditRecorder, EventType, Subject, SubjectKind
from scopesteps.backlog.application.candidates import CitationChecker, VersionStore
from scopesteps.backlog.domain.editing import (
    CandidateSuggestionOutcome,
    ItemEdit,
    VersionChangedError,
    VersionNotDraftError,
    VersionNotInReviewError,
    answer_candidate_decision,
    answer_decision,
    apply_edit,
    change_clarification_answer,
    review_candidate_suggestion,
    settle_scope_decision,
)
from scopesteps.backlog.domain.ids import BacklogVersionId, CriterionId, DecisionId, ItemId
from scopesteps.backlog.domain.review import CheckResult, cited_evidence, review_checks
from scopesteps.backlog.domain.version import (
    BacklogVersion,
    Decision,
    Item,
    ScopeOutcome,
    VersionState,
    content_hash,
)
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
        self,
        version: BacklogVersion,
        item: Item,
        *,
        expected_revision: int,
        content_hash: str,
        expected_state: VersionState = VersionState.DRAFT,
    ) -> bool:
        """Store the item and move the version to the next revision, within the caller's
        transaction. False, changing nothing, if the version is no longer in `expected_state`
        at `expected_revision`."""
        ...

    def save_decisions(
        self,
        version: BacklogVersion,
        decisions: tuple[Decision, ...],
        *,
        expected_revision: int,
        content_hash: str,
        expected_state: VersionState = VersionState.DRAFT,
    ) -> bool:
        """Store the version's decisions and move it to the next revision, as `save_item` does,
        if it is still in `expected_state`."""
        ...


@dataclass(frozen=True)
class AnswerDecision:
    idempotency_key: str
    decision_id: DecisionId
    expected_revision: int
    answer: str


@dataclass(frozen=True)
class RecordScopeDecision:
    idempotency_key: str
    decision_id: DecisionId
    expected_revision: int
    outcome: ScopeOutcome


@dataclass(frozen=True)
class AnswerCandidateDecision:
    idempotency_key: str
    decision_id: DecisionId
    expected_revision: int
    answer: str


@dataclass(frozen=True)
class ReviewCandidateSuggestion:
    idempotency_key: str
    criterion_id: CriterionId
    expected_revision: int
    outcome: CandidateSuggestionOutcome


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
        # A change candidate is reviewed in review, not as a draft; its scope decisions are
        # enforced again on approval (ADR 0011).
        return self.version.state in REVIEWABLE and all(c.passed for c in self.checks)


REVIEWABLE = frozenset({VersionState.DRAFT, VersionState.IN_REVIEW})


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


def answer_open_decision(
    store: DraftStore,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    command: AnswerDecision,
    now: datetime,
) -> BacklogVersion:
    """Settle an open or skipped decision on a draft at `expected_revision`. Needs the editor or
    approver role, as answering the agent's questions during a run does.

    A retry with the same Idempotency-Key returns the version as it is now without answering
    again.
    """
    version, access = _load(store, resolve, version_id)
    access.require_any_role(Role.EDITOR, Role.APPROVER)
    actor = access.actor
    fingerprint = _digest(
        [str(version_id), str(command.decision_id), command.expected_revision, command.answer]
    )
    receipt = receipts.find(actor.user_id, command.idempotency_key)
    if receipt is not None:
        if receipt.fingerprint != fingerprint:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for another request"
            )
        return version

    require_draft(version)
    require_revision(version, command.expected_revision)
    decision = next((d for d in version.decisions if d.id == command.decision_id), None)
    if decision is None:
        raise NotFoundError("Decision not found")
    answered = answer_decision(decision, command.answer, decided_by=actor.user_id, now=now)
    decisions = tuple(answered if d.id == decision.id else d for d in version.decisions)
    new_hash = content_hash(version.items, decisions, version.out_of_scope)
    if not store.save_decisions(
        version, decisions, expected_revision=version.revision, content_hash=new_hash
    ):
        raise _changed(None)
    subjects = [Subject(SubjectKind.BACKLOG_VERSION, version.id)]
    if decision.question_id is not None:
        subjects.append(Subject(SubjectKind.QUESTION, decision.question_id))
    audit.record(
        project_id=version.project_id,
        actor=AuditActor.user(actor),
        type=EventType.SCOPE_DECIDED,
        subjects=tuple(subjects),
        # The answer itself stays on the decision; the activity log names counts and kinds only.
        summary=f"Answered a {decision.status} {decision.kind} in draft revision "
        f"{version.revision}",
        occurred_at=now,
    )
    receipts.add(Receipt(actor.user_id, command.idempotency_key, version.id, fingerprint, now))
    return replace(
        version, decisions=decisions, revision=version.revision + 1, content_hash=new_hash
    )


def record_scope_decision(
    store: DraftStore,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    command: RecordScopeDecision,
    now: datetime,
) -> BacklogVersion:
    """Record an approver's reverse or keep on a required scope decision of a change candidate
    in review, at `expected_revision`, moving the candidate to its next revision.

    Only a person with the approver role may: the agent proposes reversals but never settles
    them (ADR 0011). The decision keeps who and when, and its id is what the change's items cite
    as the reason earlier scope was reversed. A retry with the same Idempotency-Key returns the
    version as it is now without recording again.
    """
    return _settle_on_candidate(
        store,
        receipts,
        audit,
        resolve,
        version_id,
        idempotency_key=command.idempotency_key,
        decision_id=command.decision_id,
        expected_revision=command.expected_revision,
        fingerprint=["scope_decision", command.outcome],
        settle=lambda decision, actor: settle_scope_decision(
            decision, command.outcome, decided_by=actor, now=now
        ),
        summary=lambda _decision, revision: (
            f"Chose to {command.outcome} earlier scope in candidate revision {revision}"
        ),
        now=now,
    )


def answer_candidate_open_decision(
    store: DraftStore,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    command: AnswerCandidateDecision,
    now: datetime,
) -> BacklogVersion:
    """Settle an open or skipped decision of a change candidate in review, such as a
    clarification skipped during the change run, with an approver's answer at
    `expected_revision`, moving the candidate to its next revision.

    Approver role only, like every decision on a candidate: the candidate cannot be edited, and
    whoever settles what it leaves open is deciding the change (ADR 0011). Scope decisions take
    `record_scope_decision` instead. A retry with the same Idempotency-Key returns the version
    as it is now without answering again.
    """
    return _settle_on_candidate(
        store,
        receipts,
        audit,
        resolve,
        version_id,
        idempotency_key=command.idempotency_key,
        decision_id=command.decision_id,
        expected_revision=command.expected_revision,
        fingerprint=["candidate_decision", command.answer],
        settle=lambda decision, actor: answer_candidate_decision(
            decision, command.answer, decided_by=actor, now=now
        ),
        # The answer itself stays on the decision; the activity log names kinds only.
        summary=lambda decision, revision: (
            f"Answered a {decision.status} {decision.kind} in candidate revision {revision}"
        ),
        now=now,
    )


def review_suggestion_on_candidate(
    store: DraftStore,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    command: ReviewCandidateSuggestion,
    now: datetime,
) -> BacklogVersion:
    """Accept or reject an agent suggestion of a change candidate in review, at
    `expected_revision`, moving the candidate to its next revision.

    Approver role only, as for a candidate's decisions: the candidate cannot be edited, so
    without this a suggestion the change run proposed would leave only rejection (ADR 0011). A
    rejected suggestion stays visible and is left out on approval, as in a draft. A retry with the
    same Idempotency-Key returns the version as it is now without reviewing again.
    """
    version, access = _load(store, resolve, version_id)
    access.require_role(Role.APPROVER)
    actor = access.actor
    digest = _digest(
        [
            "candidate_suggestion",
            str(version_id),
            str(command.criterion_id),
            command.expected_revision,
            command.outcome,
        ]
    )
    receipt = receipts.find(actor.user_id, command.idempotency_key)
    if receipt is not None:
        if receipt.fingerprint != digest:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for another request"
            )
        return version

    if version.state is not VersionState.IN_REVIEW:
        raise VersionNotInReviewError(
            "Only a change candidate in review takes an approver's review here.",
            details={"state": version.state.value},
        )
    require_revision(version, command.expected_revision)
    item = next(
        (i for i in version.items if any(c.id == command.criterion_id for c in i.criteria)), None
    )
    if item is None:
        raise NotFoundError("Criterion not found")
    reviewed = review_candidate_suggestion(item, command.criterion_id, command.outcome)
    items = tuple(reviewed if i.id == item.id else i for i in version.items)
    new_hash = content_hash(items, version.decisions, version.out_of_scope)
    if not store.save_item(
        version,
        reviewed,
        expected_revision=version.revision,
        content_hash=new_hash,
        expected_state=VersionState.IN_REVIEW,
    ):
        raise _changed(None)
    audit.record(
        project_id=version.project_id,
        actor=AuditActor.user(actor),
        type=EventType.SUGGESTION_ACCEPTED
        if command.outcome == "accepted"
        else EventType.SUGGESTION_REJECTED,
        subjects=(
            Subject(SubjectKind.BACKLOG_VERSION, version.id),
            Subject(SubjectKind.ITEM, item.id),
            Subject(SubjectKind.CRITERION, command.criterion_id),
        ),
        summary=(
            f"{command.outcome.capitalize()} an agent suggestion on a {item.kind} in candidate "
            f"revision {version.revision}"
        ),
        occurred_at=now,
    )
    receipts.add(Receipt(actor.user_id, command.idempotency_key, version.id, digest, now))
    return replace(version, items=items, revision=version.revision + 1, content_hash=new_hash)


def _settle_on_candidate(
    store: DraftStore,
    receipts: ReceiptStore,
    audit: AuditRecorder,
    resolve: ProjectAccessResolver,
    version_id: BacklogVersionId,
    *,
    idempotency_key: str,
    decision_id: DecisionId,
    expected_revision: int,
    fingerprint: list[str],
    settle: Callable[[Decision, UserId], Decision],
    summary: Callable[[Decision, int], str],
    now: datetime,
) -> BacklogVersion:
    version, access = _load(store, resolve, version_id)
    access.require_role(Role.APPROVER)
    actor = access.actor
    digest = _digest(
        [fingerprint[0], str(version_id), str(decision_id), expected_revision, *fingerprint[1:]]
    )
    receipt = receipts.find(actor.user_id, idempotency_key)
    if receipt is not None:
        if receipt.fingerprint != digest:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for another request"
            )
        return version

    if version.state is not VersionState.IN_REVIEW:
        raise VersionNotInReviewError(
            "Only a change candidate in review takes an approver's decision here.",
            details={"state": version.state.value},
        )
    require_revision(version, expected_revision)
    decision = next((d for d in version.decisions if d.id == decision_id), None)
    if decision is None:
        raise NotFoundError("Decision not found")
    settled = settle(decision, actor.user_id)
    decisions = tuple(settled if d.id == decision.id else d for d in version.decisions)
    new_hash = content_hash(version.items, decisions, version.out_of_scope)
    if not store.save_decisions(
        version,
        decisions,
        expected_revision=version.revision,
        content_hash=new_hash,
        expected_state=VersionState.IN_REVIEW,
    ):
        raise _changed(None)
    subjects = [
        Subject(SubjectKind.BACKLOG_VERSION, version.id),
        Subject(SubjectKind.DECISION, decision.id),
    ]
    if decision.question_id is not None:
        subjects.append(Subject(SubjectKind.QUESTION, decision.question_id))
    audit.record(
        project_id=version.project_id,
        actor=AuditActor.user(actor),
        type=EventType.SCOPE_DECIDED,
        subjects=tuple(subjects),
        summary=summary(decision, version.revision),
        occurred_at=now,
    )
    receipts.add(Receipt(actor.user_id, idempotency_key, version.id, digest, now))
    return replace(
        version, decisions=decisions, revision=version.revision + 1, content_hash=new_hash
    )


def change_run_answer(
    store: DraftStore,
    run_id: UUID,
    question_id: UUID,
    answer: str,
    *,
    decided_by: UserId,
    now: datetime,
) -> BacklogVersion | None:
    """Put a reviewer's changed clarification answer into the draft made from `run_id` and move
    the draft to its next revision, so anyone editing the older revision gets a conflict.

    None when no version was made from the run. Raises VersionNotDraftError once the version has
    left the draft state: its answers are then locked. The caller records the action.
    """
    version = store.find_by_run(run_id)
    if version is None:
        return None
    require_draft(version)
    decisions = tuple(
        change_clarification_answer(d, answer, decided_by=decided_by, now=now)
        if d.question_id == question_id
        else d
        for d in version.decisions
    )
    new_hash = content_hash(version.items, decisions, version.out_of_scope)
    if not store.save_decisions(
        version, decisions, expected_revision=version.revision, content_hash=new_hash
    ):
        raise _changed(None)
    return replace(
        version, decisions=decisions, revision=version.revision + 1, content_hash=new_hash
    )


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


def _digest(parts: list[object]) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
