"""Reads for a project's dashboard: its approved versions and how its change requests went."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from scopesteps.change_control.domain.change_request import ChangeRequestStatus
from scopesteps.change_control.infrastructure.orm import ApprovalRecord, ChangeRequestRecord
from scopesteps.projects.client import ProjectId


@dataclass(frozen=True)
class ApprovedVersionRow:
    version_id: UUID
    number: int
    approved_by: UUID
    approved_at: datetime
    change_request_number: int | None


@dataclass(frozen=True)
class ChangeRequestRow:
    number: int
    status: ChangeRequestStatus
    requested_at: datetime
    decided_at: datetime | None


def approved_versions(session: Session, project_id: ProjectId) -> list[ApprovedVersionRow]:
    """Oldest first, in one query: each approval with the change request it decided, if any."""
    rows = session.execute(
        select(
            ApprovalRecord.version_id,
            ApprovalRecord.baseline_number,
            ApprovalRecord.decided_by,
            ApprovalRecord.decided_at,
            ChangeRequestRecord.number,
        )
        .outerjoin(
            ChangeRequestRecord,
            ChangeRequestRecord.candidate_version_id == ApprovalRecord.version_id,
        )
        .where(
            ApprovalRecord.project_id == project_id,
            ApprovalRecord.decision == "approved",
            ApprovalRecord.baseline_number.is_not(None),
        )
        .order_by(ApprovalRecord.baseline_number)
    )
    return [
        ApprovedVersionRow(version_id, number, decided_by, decided_at, request_number)
        for version_id, number, decided_by, decided_at, request_number in rows
        if number is not None
    ]


def change_request_rows(session: Session, project_id: ProjectId) -> list[ChangeRequestRow]:
    """Every change request with when an approver decided its proposed version, in one query.
    A request no approver decided (still in review, no change needed, failed) has none."""
    rows = session.execute(
        select(
            ChangeRequestRecord.number,
            ChangeRequestRecord.status,
            ChangeRequestRecord.requested_at,
            ApprovalRecord.decided_at,
        )
        .outerjoin(
            ApprovalRecord, ApprovalRecord.version_id == ChangeRequestRecord.candidate_version_id
        )
        .where(ChangeRequestRecord.project_id == project_id)
        .order_by(ChangeRequestRecord.number)
    )
    return [
        ChangeRequestRow(number, status, requested_at, decided_at)
        for number, status, requested_at, decided_at in rows
    ]
