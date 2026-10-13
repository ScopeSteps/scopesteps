from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.infrastructure.database import Base, UtcDateTime
from scopesteps.sources.domain.source import MediaType, SourceKind
from scopesteps.sources.domain.upload import MAX_FILENAME_LENGTH


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class SourceRecord(Base):
    __tablename__ = "sources_sources"
    __table_args__ = (UniqueConstraint("project_id", "kind"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    kind: Mapped[SourceKind] = mapped_column(
        Enum(SourceKind, native_enum=False, length=32, values_callable=_enum_values)
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class SourceVersionRecord(Base):
    __tablename__ = "sources_versions"
    __table_args__ = (UniqueConstraint("source_id", "version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources_sources.id"))
    version: Mapped[int]
    filename: Mapped[str] = mapped_column(String(MAX_FILENAME_LENGTH))
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False, length=32, values_callable=_enum_values)
    )
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int]
    word_count: Mapped[int]
    block_count: Mapped[int]
    # Deferred so listing versions does not load whole documents.
    text: Mapped[str] = mapped_column(Text, deferred=True)
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class SourceBlockRecord(Base):
    __tablename__ = "sources_blocks"
    __table_args__ = (UniqueConstraint("source_version_id", "ordinal"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_version_id: Mapped[UUID] = mapped_column(ForeignKey("sources_versions.id"))
    ordinal: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int]
    end_offset: Mapped[int]


class UploadReceiptRecord(Base):
    __tablename__ = "sources_upload_receipts"
    __table_args__ = (UniqueConstraint("project_id", "actor_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    source_version_ids: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
