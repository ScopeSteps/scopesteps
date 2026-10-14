"""A person named in a project's sources: what the agent extracted, and what people changed.

The extraction is never edited. A correction and a confirmed decision right are stored beside
it with who made them and when, so the agent's original stays visible.
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
class Person:
    id: PersonId
    project_id: ProjectId
    revision: int
    extracted: ExtractedPerson
    run_id: UUID
    """The latest agent run that named this person."""
    extracted_at: datetime
    created_at: datetime
    correction: Correction | None = None
    confirmed_rights: RightsConfirmation | None = None

    @property
    def name(self) -> str:
        return (self.correction and self.correction.name) or self.extracted.name

    @property
    def role(self) -> str:
        if self.correction is not None and self.correction.role is not None:
            return self.correction.role
        return self.extracted.role

    def is_named(self, key: str) -> bool:
        """Whether `key` (see `name_key`) is this person's extracted or corrected name."""
        corrected = self.correction.name if self.correction else None
        return key == name_key(self.extracted.name) or (
            corrected is not None and key == name_key(corrected)
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
            name=None if name == self.extracted.name else name,
            role=None if role == self.extracted.role else role,
            corrected_by=by,
            corrected_at=at,
        )
        return replace(self, correction=correction, revision=self.revision + 1)

    def with_confirmed_rights(self, rights: ConfirmedRights, by: UserId, at: datetime) -> Person:
        if self.extracted.stated_rights != "not_stated":
            raise RightsStatedInSourceError(
                "A source states this person's decision rights, so they cannot be confirmed by hand"
            )
        return replace(
            self,
            confirmed_rights=RightsConfirmation(rights, by, at),
            revision=self.revision + 1,
        )

    def re_extracted(self, extracted: ExtractedPerson, run_id: UUID, at: datetime) -> Person:
        """A later run named the same person: its reading replaces the earlier one, and the
        correction and confirmed rights stay. The revision moves only if the reading changed."""
        changed = extracted != self.extracted
        return replace(
            self,
            extracted=extracted,
            run_id=run_id,
            extracted_at=at,
            revision=self.revision + (1 if changed else 0),
        )
