from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
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
    "ExtractedPerson",
    "PeopleRecorder",
    "PersonEvidence",
    "PersonId",
    "ProjectId",
    "ProjectReader",
    "ProjectRef",
    "StatedRights",
    "extraction_problems",
    "get_people_recorder",
    "get_project_reader",
    "name_key",
]
