from sqlalchemy import select
from sqlalchemy.orm import Session

from scopesteps.backlog.client import (
    BacklogVersionId,
    CheckResult,
    VersionSummary,
    approval_checks,
    freeze_approved,
    load_version_summary,
    mark_rejected,
)
from scopesteps.change_control.application.decisions import Receipt, ScopeDecision
from scopesteps.change_control.domain.ids import ApprovalId
from scopesteps.change_control.infrastructure.orm import ApprovalRecord, CommandReceiptRecord
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
        self, version_id: BacklogVersionId, *, expected_revision: int, content_hash: str
    ) -> bool:
        return freeze_approved(
            self._session,
            version_id,
            expected_revision=expected_revision,
            content_hash=content_hash,
        )

    def reject(self, version_id: BacklogVersionId, *, expected_revision: int) -> bool:
        return mark_rejected(self._session, version_id, expected_revision=expected_revision)


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
