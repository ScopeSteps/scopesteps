"""Binds `projects.client.get_project_work_reader` to the modules that hold the waiting work."""

from collections.abc import Collection, Mapping

from sqlalchemy.orm import Session

from scopesteps.agent.client import open_question_counts
from scopesteps.change_control.client import in_review_counts
from scopesteps.infrastructure.http import SessionDep
from scopesteps.projects.client import ProjectId, ProjectWorkReader


class _ProjectWork:
    def __init__(self, session: Session) -> None:
        self._session = session

    def change_requests_in_review(
        self, project_ids: Collection[ProjectId]
    ) -> Mapping[ProjectId, int]:
        return in_review_counts(self._session, project_ids)

    def open_questions(self, project_ids: Collection[ProjectId]) -> Mapping[ProjectId, int]:
        return open_question_counts(self._session, project_ids)


def resolve_project_work_reader(session: SessionDep) -> ProjectWorkReader:
    return _ProjectWork(session)
