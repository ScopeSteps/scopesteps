from collections.abc import Collection
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.orm import Session as DatabaseSession

from scopesteps.identity.application.accounts import EmailToken
from scopesteps.identity.application.limits import Bucket
from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.invitation import GRANTABLE_ROLES, Invitation, InvitationId
from scopesteps.identity.domain.profile import Profile
from scopesteps.identity.domain.session import Session, SessionId
from scopesteps.identity.domain.user import (
    Credentials,
    Membership,
    ProjectMember,
    User,
    normalise_email,
)
from scopesteps.identity.infrastructure.orm import (
    AttemptRecord,
    EmailTokenRecord,
    InvitationRecord,
    MemberRevisionRecord,
    MembershipRecord,
    SessionRecord,
    UserRecord,
)
from scopesteps.infrastructure.database import utc_now
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
                email_verified_at=user.email_verified_at,
            )
        )

    def add_account(self, user: User, password_hash: str) -> None:
        self.add(user)
        self._session.flush()
        self.set_password_hash(user.id, password_hash)

    def by_email(self, email: str) -> User | None:
        record = self._session.scalars(
            select(UserRecord).where(func.lower(UserRecord.email) == email)
        ).one_or_none()
        return None if record is None else _user(record)

    def reset_unverified(self, user_id: UserId, display_name: str, password_hash: str) -> None:
        self._session.execute(
            update(UserRecord)
            .where(UserRecord.id == user_id, UserRecord.email_verified_at.is_(None))
            .values(display_name=display_name, password_hash=password_hash)
        )

    def mark_verified(self, user_id: UserId, at: datetime) -> None:
        self._session.execute(
            update(UserRecord)
            .where(UserRecord.id == user_id, UserRecord.email_verified_at.is_(None))
            .values(email_verified_at=at)
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
            select(UserRecord, MembershipRecord.role, MemberRevisionRecord.revision)
            .join(MembershipRecord, MembershipRecord.user_id == UserRecord.id)
            .outerjoin(
                MemberRevisionRecord,
                (MemberRevisionRecord.user_id == UserRecord.id)
                & (MemberRevisionRecord.project_id == project_id),
            )
            .where(MembershipRecord.project_id == project_id)
            .order_by(UserRecord.display_name, UserRecord.id)
        )
        roles: dict[UserId, set[Role]] = {}
        users: dict[UserId, tuple[UserRecord, int]] = {}
        for record, role, revision in rows:
            users.setdefault(UserId(record.id), (record, revision or 1))
            roles.setdefault(UserId(record.id), set()).add(role)
        return [
            ProjectMember(
                user_id=user_id,
                display_name=record.display_name,
                job_title=record.job_title,
                roles=frozenset(roles[user_id]),
                revision=revision,
            )
            for user_id, (record, revision) in users.items()
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
        email_verified_at=record.email_verified_at,
    )


def _credentials(record: UserRecord) -> Credentials:
    return Credentials(
        user_id=UserId(record.id),
        password_hash=record.password_hash,
        email_verified=record.email_verified_at is not None,
    )


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


class SqlMemberStore:
    """Members of a project and their roles, for approvers' changes."""

    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    def roles_of(self, project_id: ProjectId, user_id: UserId) -> frozenset[Role]:
        return frozenset(
            self._session.scalars(
                select(MembershipRecord.role).where(
                    MembershipRecord.project_id == project_id, MembershipRecord.user_id == user_id
                )
            )
        )

    def grant(
        self, user_id: UserId, project_id: ProjectId, roles: Collection[Role], now: datetime
    ) -> None:
        held = self.roles_of(project_id, user_id)
        for role in sorted(set(roles) - held):
            self._session.add(
                MembershipRecord(
                    id=new_id(), user_id=user_id, project_id=project_id, role=role, granted_at=now
                )
            )
        if held:
            self._bump(project_id, user_id)

    def roles_by_member(self, project_id: ProjectId) -> dict[UserId, frozenset[Role]]:
        # Locks the approver rows on databases that support it, so a concurrent change that
        # could leave no approver waits for this transaction (ADR 0019).
        self._session.execute(
            select(MembershipRecord.id)
            .where(
                MembershipRecord.project_id == project_id,
                MembershipRecord.role == Role.APPROVER,
            )
            .with_for_update()
        ).all()
        roles: dict[UserId, set[Role]] = {}
        for user_id, role in self._session.execute(
            select(MembershipRecord.user_id, MembershipRecord.role).where(
                MembershipRecord.project_id == project_id
            )
        ):
            roles.setdefault(UserId(user_id), set()).add(role)
        return {user_id: frozenset(held) for user_id, held in roles.items()}

    def revision(self, project_id: ProjectId, user_id: UserId) -> int | None:
        if not self.roles_of(project_id, user_id):
            return None
        stored = self._session.scalar(
            select(MemberRevisionRecord.revision).where(
                MemberRevisionRecord.project_id == project_id,
                MemberRevisionRecord.user_id == user_id,
            )
        )
        return stored or 1

    def set_roles(
        self,
        project_id: ProjectId,
        user_id: UserId,
        roles: Collection[Role],
        now: datetime,
        *,
        expected_revision: int,
    ) -> bool:
        if not self._advance(project_id, user_id, expected_revision):
            return False
        chosen = set(roles)
        self._session.execute(
            delete(MembershipRecord).where(
                MembershipRecord.project_id == project_id,
                MembershipRecord.user_id == user_id,
                MembershipRecord.role.in_(GRANTABLE_ROLES - chosen),
            )
        )
        held = self.roles_of(project_id, user_id)
        for role in sorted(chosen - held):
            self._session.add(
                MembershipRecord(
                    id=new_id(), user_id=user_id, project_id=project_id, role=role, granted_at=now
                )
            )
        self._session.flush()
        return True

    def remove(self, project_id: ProjectId, user_id: UserId) -> None:
        self._session.execute(
            delete(MembershipRecord).where(
                MembershipRecord.project_id == project_id, MembershipRecord.user_id == user_id
            )
        )
        self._session.execute(
            delete(MemberRevisionRecord).where(
                MemberRevisionRecord.project_id == project_id,
                MemberRevisionRecord.user_id == user_id,
            )
        )

    def approver_count(self, project_id: ProjectId) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(MembershipRecord)
                .where(
                    MembershipRecord.project_id == project_id,
                    MembershipRecord.role == Role.APPROVER,
                )
            )
            or 0
        )

    def _advance(self, project_id: ProjectId, user_id: UserId, expected_revision: int) -> bool:
        """Compare-and-set the member's revision. A member without a row is at revision 1; two
        writers inserting its first row collide on the primary key, and one fails."""
        result = self._session.execute(
            update(MemberRevisionRecord)
            .where(
                MemberRevisionRecord.project_id == project_id,
                MemberRevisionRecord.user_id == user_id,
                MemberRevisionRecord.revision == expected_revision,
            )
            .values(revision=expected_revision + 1)
            .execution_options(synchronize_session=False)
        )
        if cast(CursorResult[Any], result).rowcount == 1:
            return True
        if expected_revision != 1 or self._session.get(MemberRevisionRecord, (user_id, project_id)):
            return False
        self._session.add(MemberRevisionRecord(user_id=user_id, project_id=project_id, revision=2))
        self._session.flush()
        return True

    def _bump(self, project_id: ProjectId, user_id: UserId) -> None:
        revision = self.revision(project_id, user_id) or 1
        self._advance(project_id, user_id, revision)


class SqlEmailTokenStore:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    def add(self, token: EmailToken) -> None:
        self._session.add(
            EmailTokenRecord(
                id=token.id,
                user_id=token.user_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                used_at=token.used_at,
                created_at=utc_now(),
            )
        )

    def by_hash(self, token_hash: str) -> EmailToken | None:
        record = self._session.scalars(
            select(EmailTokenRecord).where(EmailTokenRecord.token_hash == token_hash)
        ).one_or_none()
        if record is None:
            return None
        return EmailToken(
            id=record.id,
            user_id=UserId(record.user_id),
            token_hash=record.token_hash,
            expires_at=record.expires_at,
            used_at=record.used_at,
        )

    def use(self, token: EmailToken, at: datetime) -> bool:
        result = self._session.execute(
            update(EmailTokenRecord)
            .where(EmailTokenRecord.id == token.id, EmailTokenRecord.used_at.is_(None))
            .values(used_at=at)
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1

    def discard_unused(self, user_id: UserId) -> None:
        self._session.execute(
            delete(EmailTokenRecord).where(
                EmailTokenRecord.user_id == user_id, EmailTokenRecord.used_at.is_(None)
            )
        )


class SqlInvitationStore:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    def add(self, invitation: Invitation) -> None:
        self._session.add(
            InvitationRecord(
                id=invitation.id,
                project_id=invitation.project_id,
                email=invitation.email,
                roles=sorted(role.value for role in invitation.roles),
                invited_by=invitation.invited_by,
                token_hash=invitation.token_hash,
                expires_at=invitation.expires_at,
                accepted_at=invitation.accepted_at,
                created_at=invitation.created_at,
            )
        )
        self._session.flush()

    def get(self, invitation_id: InvitationId) -> Invitation | None:
        record = self._session.get(InvitationRecord, invitation_id, populate_existing=True)
        return None if record is None else _invitation(record)

    def by_token_hash(self, token_hash: str) -> Invitation | None:
        record = self._session.scalars(
            select(InvitationRecord).where(InvitationRecord.token_hash == token_hash)
        ).one_or_none()
        return None if record is None else _invitation(record)

    def for_email(self, project_id: ProjectId, email: str) -> Invitation | None:
        record = self._session.scalars(
            select(InvitationRecord).where(
                InvitationRecord.project_id == project_id, InvitationRecord.email == email
            )
        ).one_or_none()
        return None if record is None else _invitation(record)

    def waiting(self, project_id: ProjectId) -> list[Invitation]:
        records = self._session.scalars(
            select(InvitationRecord)
            .where(
                InvitationRecord.project_id == project_id, InvitationRecord.accepted_at.is_(None)
            )
            .order_by(InvitationRecord.created_at.desc(), InvitationRecord.id.desc())
        )
        return [_invitation(record) for record in records]

    def replace_token(
        self, invitation_id: InvitationId, token_hash: str, expires_at: datetime
    ) -> None:
        self._session.execute(
            update(InvitationRecord)
            .where(InvitationRecord.id == invitation_id)
            .values(token_hash=token_hash, expires_at=expires_at)
        )

    def delete(self, invitation_id: InvitationId) -> None:
        self._session.execute(delete(InvitationRecord).where(InvitationRecord.id == invitation_id))
        self._session.flush()

    def accept(self, invitation: Invitation, at: datetime) -> bool:
        result = self._session.execute(
            update(InvitationRecord)
            .where(
                InvitationRecord.id == invitation.id,
                InvitationRecord.token_hash == invitation.token_hash,
                InvitationRecord.accepted_at.is_(None),
            )
            .values(accepted_at=at)
            .execution_options(synchronize_session=False)
        )
        return cast(CursorResult[Any], result).rowcount == 1


def _invitation(record: InvitationRecord) -> Invitation:
    return Invitation(
        id=InvitationId(record.id),
        project_id=ProjectId(record.project_id),
        email=record.email,
        roles=frozenset(Role(role) for role in record.roles),
        invited_by=UserId(record.invited_by),
        token_hash=record.token_hash,
        expires_at=record.expires_at,
        created_at=record.created_at,
        accepted_at=record.accepted_at,
    )


# Attempts are only counted within an hour; a day's margin keeps the table small.
_ATTEMPTS_KEPT = timedelta(days=1)


class SqlAttemptStore:
    def __init__(self, session: DatabaseSession) -> None:
        self._session = session

    def count(self, bucket: Bucket, key_hash: str, since: datetime) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(AttemptRecord)
                .where(
                    AttemptRecord.bucket == bucket,
                    AttemptRecord.key_hash == key_hash,
                    AttemptRecord.attempted_at > since,
                )
            )
            or 0
        )

    def add(self, bucket: Bucket, key_hash: str, at: datetime) -> None:
        self._session.execute(
            delete(AttemptRecord).where(AttemptRecord.attempted_at < at - _ATTEMPTS_KEPT)
        )
        self._session.add(
            AttemptRecord(id=new_id(), bucket=bucket, key_hash=key_hash, attempted_at=at)
        )
