from sqlalchemy import select
from sqlalchemy.orm import Session

from scopesteps.identity.client import UserId
from scopesteps.identity.domain.user import Membership, User
from scopesteps.identity.infrastructure.orm import MembershipRecord, UserRecord
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId


class SqlUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UserId) -> User | None:
        record = self._session.get(UserRecord, user_id)
        if record is None:
            return None
        return User(
            id=UserId(record.id),
            email=record.email,
            display_name=record.display_name,
            created_at=record.created_at,
        )

    def add(self, user: User) -> None:
        self._session.add(
            UserRecord(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                created_at=user.created_at,
            )
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
