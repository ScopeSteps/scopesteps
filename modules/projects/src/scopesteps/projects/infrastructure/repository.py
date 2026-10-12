from sqlalchemy.orm import Session

from scopesteps.projects.client import ProjectId
from scopesteps.projects.domain.project import Project
from scopesteps.projects.infrastructure.orm import ProjectRecord


class SqlProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, project_id: ProjectId) -> Project | None:
        record = self._session.get(ProjectRecord, project_id)
        if record is None:
            return None
        return Project(id=ProjectId(record.id), name=record.name, created_at=record.created_at)

    def add(self, project: Project) -> None:
        self._session.add(
            ProjectRecord(id=project.id, name=project.name, created_at=project.created_at)
        )
