from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from scopesteps.projects.domain.extraction import (
    MAX_EVIDENCE,
    MAX_PEOPLE_PER_RUN,
    MAX_PERSON_NAME_CHARS,
    MAX_QUOTE_CHARS,
    MAX_ROLE_CHARS,
    MAX_SAID_CHARS,
    ExtractedPerson,
    PersonEvidence,
    StatedRights,
    extraction_problems,
    name_key,
)
from scopesteps.projects.domain.ids import PersonId, ProjectId
from scopesteps.projects.domain.speakers import SpeakerIdentity


@dataclass(frozen=True)
class ProjectRef:
    id: ProjectId
    name: str


ProjectReader = Callable[[ProjectId], ProjectRef | None]
"""A project's current name, for labelling versions and exports; None if there is no such
project. Performs no access check: callers check the actor's access to the project first."""


def get_project_reader() -> ProjectReader:
    """FastAPI dependency for modules that show a project's name.

    Projects owns the implementation; the composition root binds it with
    `app.dependency_overrides`, which keeps this module free of SQLAlchemy for the domain code
    that imports `ProjectId` from it.
    """
    raise RuntimeError("get_project_reader is not bound to the projects module's reader")


PeopleRecorder = Callable[[ProjectId, UUID, Sequence[ExtractedPerson], datetime], None]
"""Stores the people a run (the UUID) read from its sources, in the request's transaction.

A person the project already has (same name, or the name someone corrected it to) gets the new
reading; their correction and confirmed decision rights are kept, and nobody is removed. Raises
InvalidInputError, storing nothing, if a person fails `extraction_problems`.
"""


SpeakerIdentityReader = Callable[[ProjectId, UUID, Sequence[str]], dict[str, SpeakerIdentity]]
"""Who each of a source's speaker labels (by key) is, as editors confirmed it (ADR 0012): linked
to a participant, linked automatically, not a person, or unconfirmed. Performs no access check."""


def get_speaker_identity_reader() -> SpeakerIdentityReader:
    """FastAPI dependency for the agent's routes. Bound by the composition root like
    `get_project_reader`, for the same reason."""
    raise RuntimeError("get_speaker_identity_reader is not bound to the projects module's reader")


class ProjectWorkReader(Protocol):
    """What waits in many projects, from the modules that build on this one, for the home page.

    Each read covers every project given in one query; a project with nothing waiting may be
    absent. Performs no access check: callers pass only the actor's projects.
    """

    def change_requests_in_review(
        self, project_ids: Collection[ProjectId]
    ) -> Mapping[ProjectId, int]: ...

    def open_questions(self, project_ids: Collection[ProjectId]) -> Mapping[ProjectId, int]:
        """Clarification questions waiting for an answer in runs that wait for input."""
        ...


def get_project_work_reader() -> ProjectWorkReader:
    """FastAPI dependency for the home page's summary. `agent` and `change_control` build on
    this module, so it cannot import them; the composition root binds a reader that asks them."""
    raise RuntimeError("get_project_work_reader is not bound to the modules that hold the work")


@dataclass(frozen=True)
class DashboardQuestion:
    id: UUID
    subject: str


@dataclass(frozen=True)
class DashboardApproval:
    version_id: UUID
    number: int
    approved_by: UUID
    approved_at: datetime
    change_request_number: int | None
    """The change request whose proposed version this approval decided; None for v1."""


@dataclass(frozen=True)
class DashboardChangeRequest:
    number: int
    status: str
    requested_at: datetime
    decided_at: datetime | None
    """When an approver approved or rejected its proposed version; None until then."""


@dataclass(frozen=True)
class DashboardCoverage:
    confirmed: int
    covered: int


class DashboardReader(Protocol):
    """A project's figures held by the modules that build on this one, for its dashboard.
    Performs no access check: the caller checks the actor's access first."""

    def open_questions(self, project_id: ProjectId) -> Sequence[DashboardQuestion]:
        """Clarification questions waiting for an answer, the ones `ProjectWorkReader` counts."""
        ...

    def approvals(self, project_id: ProjectId) -> Sequence[DashboardApproval]:
        """Approved versions, oldest first."""
        ...

    def change_requests(self, project_id: ProjectId) -> Sequence[DashboardChangeRequest]: ...

    def coverage(self, run_id: UUID) -> DashboardCoverage | None:
        """What an initial run's draft covers of what the sources confirm; None for other runs."""
        ...


def get_dashboard_reader() -> DashboardReader:
    """FastAPI dependency for the dashboard. Bound by the composition root like
    `get_project_work_reader`, for the same reason."""
    raise RuntimeError("get_dashboard_reader is not bound to the modules that hold the figures")


def get_people_recorder() -> PeopleRecorder:
    """FastAPI dependency for routes in other modules that hand over extracted people.

    Bound by the composition root like `get_project_reader`, for the same reason.
    """
    raise RuntimeError("get_people_recorder is not bound to the projects module's recorder")


__all__ = [
    "MAX_EVIDENCE",
    "MAX_PEOPLE_PER_RUN",
    "MAX_PERSON_NAME_CHARS",
    "MAX_QUOTE_CHARS",
    "MAX_ROLE_CHARS",
    "MAX_SAID_CHARS",
    "DashboardApproval",
    "DashboardChangeRequest",
    "DashboardCoverage",
    "DashboardQuestion",
    "DashboardReader",
    "ExtractedPerson",
    "PeopleRecorder",
    "PersonEvidence",
    "PersonId",
    "ProjectId",
    "ProjectReader",
    "ProjectRef",
    "ProjectWorkReader",
    "SpeakerIdentity",
    "SpeakerIdentityReader",
    "StatedRights",
    "extraction_problems",
    "get_dashboard_reader",
    "get_people_recorder",
    "get_project_reader",
    "get_project_work_reader",
    "get_speaker_identity_reader",
    "name_key",
]
