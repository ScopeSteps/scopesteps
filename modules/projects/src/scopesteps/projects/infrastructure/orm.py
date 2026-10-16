from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.infrastructure.database import Base, UtcDateTime
from scopesteps.projects.domain.extraction import (
    MAX_PERSON_NAME_CHARS,
    MAX_ROLE_CHARS,
    MAX_SAID_CHARS,
)


class ProjectRecord(Base):
    __tablename__ = "projects_projects"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class CommandReceiptRecord(Base):
    __tablename__ = "projects_command_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class PersonRecord(Base):
    """A person on the project. The `extracted_*`, `stated_rights` and evidence columns hold the
    agent's reading and are null until a run names the person; `entered_name`, `meeting_role_*`,
    `corrected_*` and `confirmed_*` hold what people entered, and are never written by a run."""

    __tablename__ = "projects_people"
    # One row per name in a project, so two runs finishing together cannot both add the same
    # person, and a participant cannot be created twice.
    __table_args__ = (UniqueConstraint("project_id", "name_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), index=True)
    # Unbounded because normalising a name can lengthen it.
    name_key: Mapped[str] = mapped_column(Text)
    revision: Mapped[int]
    origin: Mapped[str] = mapped_column(String(32), server_default="extracted")
    extracted_name: Mapped[str | None] = mapped_column(String(MAX_PERSON_NAME_CHARS))
    extracted_role: Mapped[str | None] = mapped_column(String(MAX_ROLE_CHARS))
    extracted_said: Mapped[str | None] = mapped_column(String(MAX_SAID_CHARS))
    stated_rights: Mapped[str] = mapped_column(String(16))
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    rights_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # Not a foreign key: runs belong to the agent module.
    run_id: Mapped[UUID | None]
    extracted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    entered_name: Mapped[str | None] = mapped_column(String(MAX_PERSON_NAME_CHARS))
    meeting_role: Mapped[str | None] = mapped_column(String(MAX_ROLE_CHARS))
    meeting_role_set_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"))
    meeting_role_set_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    corrected_name: Mapped[str | None] = mapped_column(String(MAX_PERSON_NAME_CHARS))
    corrected_role: Mapped[str | None] = mapped_column(String(MAX_ROLE_CHARS))
    corrected_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"))
    corrected_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    confirmed_rights: Mapped[str | None] = mapped_column(String(16))
    rights_confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"))
    rights_confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class SpeakerMappingRecord(Base):
    """One per source whose speakers an editor answered for; its revision is compared on save."""

    __tablename__ = "projects_speaker_mappings"

    # Not a foreign key: sources belong to the sources module, which builds on this one.
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), index=True)
    revision: Mapped[int]


class SpeakerAssignmentRecord(Base):
    """An editor's answer for one label of a source: a person, or not a person (null)."""

    __tablename__ = "projects_speaker_assignments"
    __table_args__ = (UniqueConstraint("source_id", "label_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects_speaker_mappings.source_id"), index=True
    )
    label_key: Mapped[str] = mapped_column(Text)
    person_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects_people.id"))
    # The mapping revision this answer was given at.
    revision: Mapped[int]
    assigned_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    assigned_at: Mapped[datetime] = mapped_column(UtcDateTime)
