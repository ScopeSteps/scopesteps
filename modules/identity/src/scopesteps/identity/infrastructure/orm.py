from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from scopesteps.identity.client import Role
from scopesteps.infrastructure.database import Base, UtcDateTime


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class UserRecord(Base):
    __tablename__ = "identity_users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    job_title: Mapped[str] = mapped_column(String(80), server_default="")
    about: Mapped[str] = mapped_column(String(280), server_default="")
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    # An Argon2id encoded hash. Null means the account cannot sign in with a password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # Null until the address is proven by a confirmation link or an accepted invitation; such an
    # account cannot sign in.
    email_verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class MembershipRecord(Base):
    __tablename__ = "identity_memberships"
    __table_args__ = (UniqueConstraint("user_id", "project_id", "role"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), index=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=32, values_callable=_enum_values)
    )
    granted_at: Mapped[datetime] = mapped_column(UtcDateTime)


class SessionRecord(Base):
    __tablename__ = "identity_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    # SHA-256 of the session token as hex; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)


class MemberRevisionRecord(Base):
    """How often a member's roles in a project have changed. A member without a row is at
    revision 1."""

    __tablename__ = "identity_member_revisions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), primary_key=True)
    revision: Mapped[int]


class EmailTokenRecord(Base):
    """A link sent to confirm an email address. Only the token's SHA-256 is stored."""

    __tablename__ = "identity_email_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class InvitationRecord(Base):
    """An invitation to a project for one email address. Only its current link's SHA-256 is
    stored, so a new link or a cancellation stops the old one. Cancelling deletes the row."""

    __tablename__ = "identity_invitations"
    __table_args__ = (UniqueConstraint("project_id", "email"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects_projects.id"), index=True)
    # Normalised; shown only to the project's approvers and the person invited.
    email: Mapped[str] = mapped_column(String(320))
    roles: Mapped[list[str]] = mapped_column(JSON)
    invited_by: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class AttemptRecord(Base):
    """One counted attempt for a rate limit. The key is hashed: no email or IP is stored."""

    __tablename__ = "identity_attempts"
    __table_args__ = (Index("ix_identity_attempts_window", "bucket", "key_hash", "attempted_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    bucket: Mapped[str] = mapped_column(String(32))
    key_hash: Mapped[str] = mapped_column(String(64))
    attempted_at: Mapped[datetime] = mapped_column(UtcDateTime)
