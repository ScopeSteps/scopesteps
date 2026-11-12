"""Binds `projects.client.get_dashboard_reader` to the modules that hold the dashboard's figures."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.agent.client import draft_coverage, open_questions
from scopesteps.change_control.client import approved_versions, change_request_rows
from scopesteps.infrastructure.http import SessionDep
from scopesteps.projects.client import (
    DashboardApproval,
    DashboardChangeRequest,
    DashboardCoverage,
    DashboardQuestion,
    DashboardReader,
    ProjectId,
)


class _Dashboard:
    def __init__(self, session: Session) -> None:
        self._session = session

    def open_questions(self, project_id: ProjectId) -> Sequence[DashboardQuestion]:
        return [
            DashboardQuestion(question.id, question.subject)
            for question in open_questions(self._session, project_id)
        ]

    def approvals(self, project_id: ProjectId) -> Sequence[DashboardApproval]:
        return [
            DashboardApproval(
                version_id=row.version_id,
                number=row.number,
                approved_by=row.approved_by,
                approved_at=row.approved_at,
                change_request_number=row.change_request_number,
            )
            for row in approved_versions(self._session, project_id)
        ]

    def change_requests(self, project_id: ProjectId) -> Sequence[DashboardChangeRequest]:
        return [
            DashboardChangeRequest(row.number, row.status.value, row.requested_at, row.decided_at)
            for row in change_request_rows(self._session, project_id)
        ]

    def coverage(self, run_id: UUID) -> DashboardCoverage | None:
        found = draft_coverage(self._session, run_id)
        return None if found is None else DashboardCoverage(found.confirmed, found.covered)


def resolve_dashboard_reader(session: SessionDep) -> DashboardReader:
    return _Dashboard(session)
