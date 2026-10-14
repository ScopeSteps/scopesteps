from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
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
