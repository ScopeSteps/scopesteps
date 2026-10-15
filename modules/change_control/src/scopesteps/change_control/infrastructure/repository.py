from collections.abc import Collection, Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, func, or_, select, update
from sqlalchemy.orm import Session

from scopesteps.backlog.client import (
    BacklogVersion,
    BacklogVersionId,
    CheckResult,
    DecisionId,
    ItemId,
    VersionState,
    VersionSummary,
    approval_checks,
    freeze_approved,
    load_version,
    load_version_summary,
    mark_rejected,
)
from scopesteps.change_control.application.decisions import Receipt, ScopeDecision
from scopesteps.change_control.domain.change_request import (
    ChangeRequest,
    ChangeSummary,
    ItemNote,
    ListCursor,
    ScopeReversal,
)
from scopesteps.change_control.domain.ids import ApprovalId, ChangeRequestId, ChangeSetId
from scopesteps.change_control.infrastructure.orm import (
    ApprovalRecord,
    ChangeRequestRecord,
    CommandReceiptRecord,
)
from scopesteps.identity.client import UserId
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId


class SqlDecisionStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, approval_id: ApprovalId) -> ScopeDecision | None:
        record = self._session.get(ApprovalRecord, approval_id)
        return None if record is None else _to_decision(record)

    def current_baseline(self, project_id: ProjectId) -> ScopeDecision | None:
        record = self._session.scalars(
            select(ApprovalRecord)
            .where(
                ApprovalRecord.project_id == project_id,
                ApprovalRecord.baseline_number.is_not(None),
            )
            .order_by(ApprovalRecord.baseline_number.desc())
            .limit(1)
        ).one_or_none()
        return None if record is None else _to_decision(record)

    def of_versions(
        self, version_ids: Collection[BacklogVersionId]
    ) -> dict[BacklogVersionId, ScopeDecision]:
        """The decision on each version that has one, in one query."""
        records = self._session.scalars(
            select(ApprovalRecord).where(ApprovalRecord.version_id.in_(list(version_ids)))
        )
        return {BacklogVersionId(record.version_id): _to_decision(record) for record in records}

    def add(self, decision: ScopeDecision) -> None:
        self._session.add(
            ApprovalRecord(
                id=decision.id,
                project_id=decision.project_id,
                version_id=decision.version_id,
                decision=decision.decision,
                revision=decision.revision,
                content_hash=decision.content_hash,
                baseline_number=decision.baseline_number,
                previous_baseline_id=decision.previous_baseline_id,
                reason=decision.reason,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
            )
        )
        # Fails here, rather than at commit, when a concurrent decision took the version or the
        # baseline number.
        self._session.flush()

    def find_receipt(self, actor_id: UserId, idempotency_key: str) -> Receipt | None:
        record = self._session.scalars(
            select(CommandReceiptRecord).where(
                CommandReceiptRecord.actor_id == actor_id,
                CommandReceiptRecord.idempotency_key == idempotency_key,
            )
        ).one_or_none()
        if record is None:
            return None
        return Receipt(
            actor_id=UserId(record.actor_id),
            idempotency_key=record.idempotency_key,
            approval_id=ApprovalId(record.approval_id),
            fingerprint=record.fingerprint,
            created_at=record.created_at,
        )

    def add_receipt(self, receipt: Receipt) -> None:
        self._session.add(
            CommandReceiptRecord(
                id=new_id(),
                actor_id=receipt.actor_id,
                idempotency_key=receipt.idempotency_key,
                approval_id=receipt.approval_id,
                fingerprint=receipt.fingerprint,
                created_at=receipt.created_at,
            )
        )
        self._session.flush()


class BacklogVersions:
    """The backlog module's versions, through its client, in this session's transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def summary(self, version_id: BacklogVersionId) -> VersionSummary | None:
        return load_version_summary(self._session, version_id)

    def checks(self, version_id: BacklogVersionId) -> tuple[CheckResult, ...]:
        return approval_checks(self._session, version_id)

    def freeze(
        self,
        version_id: BacklogVersionId,
        *,
        expected_revision: int,
        content_hash: str,
        expected_state: VersionState,
    ) -> bool:
        return freeze_approved(
            self._session,
            version_id,
            expected_revision=expected_revision,
            content_hash=content_hash,
            expected_state=expected_state,
        )

    def reject(
        self, version_id: BacklogVersionId, *, expected_revision: int, expected_state: VersionState
    ) -> bool:
        return mark_rejected(
            self._session,
            version_id,
            expected_revision=expected_revision,
            expected_state=expected_state,
        )


def _to_decision(record: ApprovalRecord) -> ScopeDecision:
    return ScopeDecision(
        id=ApprovalId(record.id),
        project_id=ProjectId(record.project_id),
        version_id=BacklogVersionId(record.version_id),
        decision="approved" if record.decision == "approved" else "rejected",
        revision=record.revision,
        content_hash=record.content_hash,
        baseline_number=record.baseline_number,
        previous_baseline_id=None
        if record.previous_baseline_id is None
        else BacklogVersionId(record.previous_baseline_id),
        reason=record.reason,
        decided_by=UserId(record.decided_by),
        decided_at=record.decided_at,
    )


class SqlChangeRequestStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, request_id: ChangeRequestId) -> ChangeRequest | None:
        record = self._session.get(ChangeRequestRecord, request_id, populate_existing=True)
        return None if record is None else _to_request(record)

    def by_run(self, run_id: UUID) -> ChangeRequest | None:
        return self._one(ChangeRequestRecord.run_id == run_id)

    def by_candidate(self, version_id: BacklogVersionId) -> ChangeRequest | None:
        return self._one(ChangeRequestRecord.candidate_version_id == version_id)

    def next_number(self, project_id: ProjectId) -> int:
        highest = self._session.scalar(
            select(func.max(ChangeRequestRecord.number)).where(
                ChangeRequestRecord.project_id == project_id
            )
        )
        return (highest or 0) + 1

    def add(self, request: ChangeRequest) -> None:
        self._session.add(ChangeRequestRecord(id=request.id, **_request_fields(request)))
        # Fails here, rather than at commit, when a concurrent request took the number.
        self._session.flush()

    def save(self, request: ChangeRequest, *, expected_revision: int) -> bool:
        result = self._session.execute(
            update(ChangeRequestRecord)
            .where(
                ChangeRequestRecord.id == request.id,
                ChangeRequestRecord.revision == expected_revision,
            )
            .values(**_request_fields(request))
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def newest_first(
        self, project_id: ProjectId, *, after: ListCursor | None, limit: int
    ) -> list[ChangeRequest]:
        query = select(ChangeRequestRecord).where(ChangeRequestRecord.project_id == project_id)
        if after is not None:
            query = query.where(
                or_(
                    ChangeRequestRecord.requested_at < after.requested_at,
                    and_(
                        ChangeRequestRecord.requested_at == after.requested_at,
                        ChangeRequestRecord.id < after.id,
                    ),
                )
            )
        records = self._session.scalars(
            query.order_by(
                ChangeRequestRecord.requested_at.desc(), ChangeRequestRecord.id.desc()
            ).limit(limit)
        )
        return [_to_request(record) for record in records]

    def _one(self, condition: Any) -> ChangeRequest | None:
        record = self._session.scalars(select(ChangeRequestRecord).where(condition)).one_or_none()
        return None if record is None else _to_request(record)


class BacklogVersionReader:
    """Versions through the backlog module's client, and baseline numbers from approvals."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load(self, version_id: UUID) -> BacklogVersion | None:
        return load_version(self._session, BacklogVersionId(version_id))

    def baseline_numbers(self, version_ids: Sequence[UUID]) -> dict[UUID, int]:
        decisions = SqlDecisionStore(self._session).of_versions(
            [BacklogVersionId(version_id) for version_id in version_ids]
        )
        return {
            version_id: decision.baseline_number
            for version_id, decision in decisions.items()
            if decision.baseline_number is not None
        }


def _request_fields(request: ChangeRequest) -> dict[str, Any]:
    summary = request.summary
    return {
        "project_id": request.project_id,
        "number": request.number,
        "text": request.text,
        "requested_by": request.requested_by,
        "requested_by_name": request.requested_by_name,
        "requested_at": request.requested_at,
        "base_version_id": request.base_version_id,
        "base_content_hash": request.base_content_hash,
        "source_version_id": request.source_version_id,
        "run_id": request.run_id,
        "status": request.status,
        "revision": request.revision,
        "candidate_version_id": request.candidate_version_id,
        "change_set_id": request.change_set_id,
        "added_count": None if summary is None else summary.added,
        "changed_count": None if summary is None else summary.changed,
        "removed_count": None if summary is None else summary.removed,
        "analysis": request.analysis,
        "change_set": {
            "rationales": [_note_json(note) for note in request.rationales],
            "impacts": [_note_json(note) for note in request.impacts],
            "scope_reversals": [
                {
                    "decision_id": str(r.decision_id),
                    "reverses": r.reverses,
                    "summary": r.summary,
                    "reversed_decision_id": None
                    if r.reversed_decision_id is None
                    else str(r.reversed_decision_id),
                }
                for r in request.scope_reversals
            ],
        },
        "failure": request.failure,
        "analyzed_at": request.analyzed_at,
    }


def _note_json(note: ItemNote) -> dict[str, str]:
    return {"item_id": str(note.item_id), "note": note.note}


def _to_note(data: Mapping[str, str]) -> ItemNote:
    return ItemNote(ItemId(UUID(data["item_id"])), data["note"])


def _to_request(record: ChangeRequestRecord) -> ChangeRequest:
    change_set = record.change_set
    counts = (record.added_count, record.changed_count, record.removed_count)
    return ChangeRequest(
        id=ChangeRequestId(record.id),
        project_id=ProjectId(record.project_id),
        number=record.number,
        text=record.text,
        requested_by=UserId(record.requested_by),
        requested_by_name=record.requested_by_name,
        requested_at=record.requested_at,
        base_version_id=BacklogVersionId(record.base_version_id),
        base_content_hash=record.base_content_hash,
        source_version_id=record.source_version_id,
        run_id=record.run_id,
        status=record.status,
        revision=record.revision,
        candidate_version_id=None
        if record.candidate_version_id is None
        else BacklogVersionId(record.candidate_version_id),
        change_set_id=None if record.change_set_id is None else ChangeSetId(record.change_set_id),
        summary=None
        if counts[0] is None or counts[1] is None or counts[2] is None
        else ChangeSummary(counts[0], counts[1], counts[2]),
        analysis=record.analysis,
        rationales=tuple(_to_note(note) for note in change_set.get("rationales", [])),
        impacts=tuple(_to_note(note) for note in change_set.get("impacts", [])),
        scope_reversals=tuple(
            ScopeReversal(
                decision_id=DecisionId(UUID(r["decision_id"])),
                reverses="exclusion" if r["reverses"] == "exclusion" else "decision",
                summary=r["summary"],
                reversed_decision_id=None
                if r["reversed_decision_id"] is None
                else DecisionId(UUID(r["reversed_decision_id"])),
            )
            for r in change_set.get("scope_reversals", [])
        ),
        failure=record.failure,
        analyzed_at=record.analyzed_at,
    )
