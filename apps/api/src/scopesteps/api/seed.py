"""Idempotent synthetic seed data for local development: one project and one reviewer."""

import sys
from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.api.settings import get_settings
from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.user import Membership, User
from scopesteps.identity.infrastructure.repository import SqlUserRepository
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.projects.client import ProjectId
from scopesteps.projects.domain.project import Project
from scopesteps.projects.infrastructure.repository import SqlProjectRepository

DEMO_PROJECT_ID = ProjectId(UUID("019a3a5e-0000-7000-8000-000000000001"))
LOCAL_REVIEWER_ID = UserId(UUID("019a3a5e-0000-7000-8000-000000000002"))
LOCAL_REVIEWER_ROLES = (Role.EDITOR, Role.APPROVER)


def seed(session: Session) -> bool:
    """Create the seed records that are missing. Returns whether anything was created."""
    projects = SqlProjectRepository(session)
    users = SqlUserRepository(session)
    now = utc_now()
    created = False

    if projects.get(DEMO_PROJECT_ID) is None:
        projects.add(Project(id=DEMO_PROJECT_ID, name="Campus Room Booking", created_at=now))
        created = True
    if users.get(LOCAL_REVIEWER_ID) is None:
        users.add(
            User(
                id=LOCAL_REVIEWER_ID,
                email="reviewer@scopesteps.local",
                display_name="Local Reviewer",
                created_at=now,
            )
        )
        created = True
    session.flush()

    granted = {
        m.role for m in users.memberships(LOCAL_REVIEWER_ID) if m.project_id == DEMO_PROJECT_ID
    }
    for role in LOCAL_REVIEWER_ROLES:
        if role not in granted:
            users.add_membership(
                Membership(
                    user_id=LOCAL_REVIEWER_ID, project_id=DEMO_PROJECT_ID, role=role, granted_at=now
                )
            )
            created = True

    session.commit()
    return created


def main() -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    with create_session_factory(engine)() as session:
        created = seed(session)
    engine.dispose()
    sys.stdout.write("Seeded local data.\n" if created else "Seed data already present.\n")


if __name__ == "__main__":
    main()
