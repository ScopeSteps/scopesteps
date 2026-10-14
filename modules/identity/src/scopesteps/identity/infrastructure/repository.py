from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.orm import Session as DatabaseSession

from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.profile import Profile
from scopesteps.identity.domain.session import Session, SessionId
from scopesteps.identity.domain.user import (
    Credentials,
    Membership,
    ProjectMember,
    User,
    normalise_email,
)
from scopesteps.identity.infrastructure.orm import MembershipRecord, SessionRecord, UserRecord
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId


class SqlUserRepository:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    def get(self, user_id: UserId) -> User | None:
        record = self._session.get(UserRecord, user_id)
        return None if record is None else _user(record)

    def add(self, user: User) -> None:
        self._session.add(
            UserRecord(
                id=user.id,
                email=normalise_email(user.email),
                display_name=user.display_name,
                job_title=user.job_title,
                about=user.about,
                revision=user.revision,
                created_at=user.created_at,
            )
        )

    def update_profile(self, user_id: UserId, profile: Profile, *, expected_revision: int) -> bool:
        # The revision is compared in the UPDATE itself, so of two writers holding the same
        # revision exactly one succeeds.
        result = self._session.execute(
            update(UserRecord)
            .where(UserRecord.id == user_id, UserRecord.revision == expected_revision)
            .values(
                display_name=profile.display_name,
                job_title=profile.job_title,
                about=profile.about,
                revision=expected_revision + 1,
            )
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def project_members(self, project_id: ProjectId) -> list[ProjectMember]:
        rows = self._session.execute(
            select(UserRecord, MembershipRecord.role)
            .join(MembershipRecord, MembershipRecord.user_id == UserRecord.id)
            .where(MembershipRecord.project_id == project_id)
            .order_by(UserRecord.display_name, UserRecord.id)
        )
        roles: dict[UserId, set[Role]] = {}
        users: dict[UserId, UserRecord] = {}
        for record, role in rows:
            users.setdefault(UserId(record.id), record)
            roles.setdefault(UserId(record.id), set()).add(role)
        return [
            ProjectMember(
                user_id=user_id,
                display_name=record.display_name,
                job_title=record.job_title,
                roles=frozenset(roles[user_id]),
            )
            for user_id, record in users.items()
        ]

    def credentials_for_email(self, email: str) -> Credentials | None:
        record = self._session.scalars(
            select(UserRecord).where(func.lower(UserRecord.email) == email)
        ).one_or_none()
        return None if record is None else _credentials(record)

    def credentials(self, user_id: UserId) -> Credentials | None:
        record = self._session.get(UserRecord, user_id)
        return None if record is None else _credentials(record)

    def set_password_hash(self, user_id: UserId, password_hash: str) -> None:
        self._session.execute(
            update(UserRecord).where(UserRecord.id == user_id).values(password_hash=password_hash)
        )

    def memberships(self, user_id: UserId) -> list[Membership]:
        records = self._session.scalars(
            select(MembershipRecord)
            .where(MembershipRecord.user_id == user_id)
            .order_by(MembershipRecord.project_id, MembershipRecord.role)
        )
        return [
            Membership(
                user_id=UserId(record.user_id),
                project_id=ProjectId(record.project_id),
                role=record.role,
                granted_at=record.granted_at,
            )
            for record in records
        ]

    def add_membership(self, membership: Membership) -> None:
        self._session.add(
            MembershipRecord(
                id=new_id(),
                user_id=membership.user_id,
                project_id=membership.project_id,
                role=membership.role,
                granted_at=membership.granted_at,
            )
        )


def _user(record: UserRecord) -> User:
    return User(
        id=UserId(record.id),
        email=record.email,
        display_name=record.display_name,
        created_at=record.created_at,
        job_title=record.job_title,
        about=record.about,
        revision=record.revision,
    )


def _credentials(record: UserRecord) -> Credentials:
    return Credentials(user_id=UserId(record.id), password_hash=record.password_hash)


class SqlSessionRepository:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    def add(self, session: Session) -> None:
        self._session.add(
            SessionRecord(
                id=session.id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
            )
        )

    def get_by_token_hash(self, token_hash: str) -> Session | None:
        record = self._session.scalars(
            select(SessionRecord).where(SessionRecord.token_hash == token_hash)
        ).one_or_none()
        if record is None:
            return None
        return Session(
            id=SessionId(record.id),
            user_id=UserId(record.user_id),
            token_hash=record.token_hash,
            created_at=record.created_at,
            last_seen_at=record.last_seen_at,
            expires_at=record.expires_at,
        )

    def record_activity(self, session_id: SessionId, seen_at: datetime) -> None:
        self._session.execute(
            update(SessionRecord).where(SessionRecord.id == session_id).values(last_seen_at=seen_at)
        )

    def delete_by_token_hash(self, token_hash: str) -> None:
        self._session.execute(delete(SessionRecord).where(SessionRecord.token_hash == token_hash))

    def delete_expired(self, now: datetime) -> None:
        self._session.execute(delete(SessionRecord).where(SessionRecord.expires_at <= now))
