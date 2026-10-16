"""A person on a project: named in its sources by the agent, or confirmed as a transcript's
speaker by an editor, or both.

The extraction is never edited. A correction, a confirmed decision right and what an editor
entered when confirming a speaker are stored beside it with who made them and when, so the
agent's original stays visible and a run never overwrites what a person confirmed (ADR 0012).
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from scopesteps.identity.client import UserId
from scopesteps.kernel.errors import ConflictError, InvalidInputError
from scopesteps.projects.domain.extraction import (
    MAX_PERSON_NAME_CHARS,
    MAX_ROLE_CHARS,
    ExtractedPerson,
    name_key,
)
from scopesteps.projects.domain.ids import PersonId, ProjectId

PersonOrigin = Literal["extracted", "confirmed_speaker"]
"""`extracted` when an agent run first named the person, `confirmed_speaker` when an editor
created them as a transcript's speaker. A later extraction or link does not change it."""

ConfirmedRights = Literal["decides", "advises", "unknown"]
"""What a person on the project confirmed. `unknown` records that someone looked and could not
say, which is different from nobody having looked."""


class PersonChangedError(ConflictError):
    code = "PERSON_CHANGED"


class RightsStatedInSourceError(ConflictError):
    code = "RIGHTS_STATED_IN_SOURCE"


@dataclass(frozen=True)
class Correction:
    """The name and role a person on the project entered. None leaves the agent's value."""

    name: str | None
    role: str | None
    corrected_by: UserId
    corrected_at: datetime


@dataclass(frozen=True)
class RightsConfirmation:
    rights: ConfirmedRights
    confirmed_by: UserId
    confirmed_at: datetime


@dataclass(frozen=True)
class MeetingRole:
    """What a person does in the project's meetings, as an editor entered it. Never set by a run."""

    value: str
    set_by: UserId
    set_at: datetime


def participant_name(name: str, field: str = "name") -> str:
    """A name an editor entered, single-spaced; refused when blank or too long."""
    name = " ".join(name.split())
    if not name:
        raise InvalidInputError("A participant needs a name", details={"field": field})
    if len(name) > MAX_PERSON_NAME_CHARS:
        raise InvalidInputError(
            f"A name is at most {MAX_PERSON_NAME_CHARS} characters", details={"field": field}
        )
    return name


def meeting_role_value(role: str, field: str = "meeting_role") -> str | None:
    """A meeting role an editor entered, single-spaced; None when blank."""
    role = " ".join(role.split())
    if len(role) > MAX_ROLE_CHARS:
        raise InvalidInputError(
            f"A meeting role is at most {MAX_ROLE_CHARS} characters", details={"field": field}
        )
    return role or None


@dataclass(frozen=True)
class Person:
    """Has an extraction, an entered name, or both, so it always has a name."""

    id: PersonId
    project_id: ProjectId
    revision: int
    origin: PersonOrigin
    created_at: datetime
    extracted: ExtractedPerson | None = None
    run_id: UUID | None = None
    """The latest agent run that named this person."""
    extracted_at: datetime | None = None
    entered_name: str | None = None
    """The name an editor gave when creating the person as a transcript's speaker."""
    meeting_role: MeetingRole | None = None
    correction: Correction | None = None
    confirmed_rights: RightsConfirmation | None = None

    @classmethod
    def confirmed_speaker(
        cls,
        id: PersonId,  # noqa: A002
        project_id: ProjectId,
        name: str,
        meeting_role: str | None,
        by: UserId,
        at: datetime,
    ) -> Person:
        """A participant an editor created for a transcript's speaker; no run has named them."""
        return cls(
            id=id,
            project_id=project_id,
            revision=1,
            origin="confirmed_speaker",
            created_at=at,
            entered_name=participant_name(name),
            meeting_role=None if meeting_role is None else MeetingRole(meeting_role, by, at),
        )

    @property
    def base_name(self) -> str:
        """The name before any correction: the one entered, else the agent's."""
        if self.entered_name is not None:
            return self.entered_name
        return self.extracted.name if self.extracted else ""

    @property
    def base_role(self) -> str:
        return self.extracted.role if self.extracted else ""

    @property
    def name(self) -> str:
        return (self.correction and self.correction.name) or self.base_name

    @property
    def role(self) -> str:
        if self.correction is not None and self.correction.role is not None:
            return self.correction.role
        return self.base_role

    @property
    def stated_rights(self) -> str:
        return self.extracted.stated_rights if self.extracted else "not_stated"

    def is_named(self, key: str) -> bool:
        """Whether `key` (see `name_key`) is this person's extracted, entered or corrected name."""
        names = (
            self.extracted.name if self.extracted else None,
            self.entered_name,
            self.correction.name if self.correction else None,
        )
        return any(name is not None and key == name_key(name) for name in names)

    def with_meeting_role(self, role: str | None, by: UserId, at: datetime) -> Person:
        """Set or clear the meeting role; unchanged, and the same revision, if it is the same."""
        if role == (self.meeting_role.value if self.meeting_role else None):
            return self
        return replace(
            self,
            meeting_role=None if role is None else MeetingRole(role, by, at),
            revision=self.revision + 1,
        )

    def corrected(self, name: str | None, role: str | None, by: UserId, at: datetime) -> Person:
        """Replace the correction. A value equal to the agent's is no correction of that field,
        so sending the original back removes it."""
        name = None if name is None else " ".join(name.split())
        role = None if role is None else " ".join(role.split())
        if name is not None and not name:
            raise InvalidInputError("A corrected name cannot be empty")
        if name is not None and len(name) > MAX_PERSON_NAME_CHARS:
            raise InvalidInputError(f"A name is at most {MAX_PERSON_NAME_CHARS} characters")
        if role is not None and len(role) > MAX_ROLE_CHARS:
            raise InvalidInputError(f"A role is at most {MAX_ROLE_CHARS} characters")
        correction = Correction(
            name=None if name == self.base_name else name,
            role=None if role == self.base_role else role,
            corrected_by=by,
            corrected_at=at,
        )
        return replace(self, correction=correction, revision=self.revision + 1)

    def with_confirmed_rights(self, rights: ConfirmedRights, by: UserId, at: datetime) -> Person:
        if self.stated_rights != "not_stated":
            raise RightsStatedInSourceError(
                "A source states this person's decision rights, so they cannot be confirmed by hand"
            )
        return replace(
            self,
            confirmed_rights=RightsConfirmation(rights, by, at),
            revision=self.revision + 1,
        )

    def re_extracted(self, extracted: ExtractedPerson, run_id: UUID, at: datetime) -> Person:
        """A run named the person: its reading replaces any earlier one. The correction, confirmed
        rights, entered name and meeting role stay. The revision moves only if the reading changed."""
        changed = extracted != self.extracted
        return replace(
            self,
            extracted=extracted,
            run_id=run_id,
            extracted_at=at,
            revision=self.revision + (1 if changed else 0),
        )
