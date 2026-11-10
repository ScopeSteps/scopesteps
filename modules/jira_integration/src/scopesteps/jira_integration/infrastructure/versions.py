from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.backlog.client import BacklogVersionId, approved_items, load_version
from scopesteps.jira_integration.application.ports import ApprovedVersion
from scopesteps.jira_integration.domain.plan import ApprovedItem
from scopesteps.projects.client import ProjectId


class BacklogVersions:
    """Approved content through `backlog.client`, as approval froze it."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def version(self, version_id: UUID) -> ApprovedVersion | None:
        version = load_version(self._session, BacklogVersionId(version_id))
        if version is None:
            return None
        return ApprovedVersion(
            id=version.id,
            project_id=ProjectId(version.project_id),
            approved=version.state == "approved",
            items=tuple(
                ApprovedItem(
                    id=item.id,
                    kind=item.kind,
                    parent_id=item.parent_id,
                    title=item.title,
                    description=item.description,
                    criteria=tuple(criterion.text for criterion in item.criteria),
                    assumptions=item.assumptions,
                    open_questions=item.open_questions,
                    tasks=tuple((task.id, task.title) for task in item.tasks),
                )
                for item in approved_items(version)
            ),
        )
