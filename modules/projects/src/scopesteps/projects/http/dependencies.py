from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from scopesteps.infrastructure.http import SessionDep
from scopesteps.projects.application.people import record_extracted_people
from scopesteps.projects.client import ExtractedPerson, PeopleRecorder, ProjectId
from scopesteps.projects.infrastructure.repository import SqlPeopleRepository


def resolve_people_recorder(session: SessionDep) -> PeopleRecorder:
    """Bound to `client.get_people_recorder` by the composition root. It writes through the
    request's session, so the people commit or roll back with the run that extracted them."""

    def record(
        project_id: ProjectId, run_id: UUID, people: Sequence[ExtractedPerson], now: datetime
    ) -> None:
        record_extracted_people(SqlPeopleRepository(session), project_id, run_id, people, now)

    return record
