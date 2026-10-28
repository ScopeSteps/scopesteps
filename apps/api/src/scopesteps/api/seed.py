"""Idempotent synthetic seed data for local development: one project, the local reviewer and
one account per role."""

import sys
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from scopesteps.api.settings import get_settings
from scopesteps.identity.application.sessions import PasswordHasher, ensure_password
from scopesteps.identity.client import Role, UserId
from scopesteps.identity.domain.user import Membership, User
from scopesteps.identity.infrastructure.passwords import Argon2PasswordHasher
from scopesteps.identity.infrastructure.repository import SqlUserRepository
from scopesteps.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    utc_now,
)
from scopesteps.kernel.errors import InvalidInputError
from scopesteps.projects.client import ProjectId
from scopesteps.projects.domain.project import Project
from scopesteps.projects.infrastructure.repository import SqlProjectRepository

DEMO_PROJECT_ID = ProjectId(UUID("019a3a5e-0000-7000-8000-000000000001"))
LOCAL_REVIEWER_ID = UserId(UUID("019a3a5e-0000-7000-8000-000000000002"))


@dataclass(frozen=True)
class SeedUser:
    id: UserId
    email: str
    display_name: str
    roles: tuple[Role, ...]


# Acts for every request under AUTH_MODE=local. It never gets a password, so it cannot sign in.
LOCAL_REVIEWER = SeedUser(
    id=LOCAL_REVIEWER_ID,
    email="reviewer@scopesteps.local",
    display_name="Local Reviewer",
    roles=(Role.EDITOR, Role.APPROVER),
)

# One synthetic account per role, for signing in under AUTH_MODE=session.
SEED_ACCOUNTS = (
    SeedUser(
        id=UserId(UUID("019a3a5e-0000-7000-8000-000000000003")),
        email="viewer@scopesteps.local",
        display_name="Sample Viewer",
        roles=(Role.VIEWER,),
    ),
    SeedUser(
        id=UserId(UUID("019a3a5e-0000-7000-8000-000000000004")),
        email="editor@scopesteps.local",
        display_name="Sample Editor",
        roles=(Role.EDITOR,),
    ),
    SeedUser(
        id=UserId(UUID("019a3a5e-0000-7000-8000-000000000005")),
        email="approver@scopesteps.local",
        display_name="Sample Approver",
        roles=(Role.APPROVER,),
    ),
)


def seed(
    session: Session,
    *,
    account_password: str | None = None,
    hasher: PasswordHasher | None = None,
) -> bool:
    """Create the seed records that are missing. Returns whether anything was created or changed.

    The accounts get `account_password` when one is given, and are otherwise left as they are:
    without a password they exist but cannot sign in.
    """
    projects = SqlProjectRepository(session)
    users = SqlUserRepository(session)
    now = utc_now()
    changed = False

    if projects.get(DEMO_PROJECT_ID) is None:
        projects.add(Project(id=DEMO_PROJECT_ID, name="Campus Room Booking", created_at=now))
        changed = True
    for seed_user in (LOCAL_REVIEWER, *SEED_ACCOUNTS):
        if users.get(seed_user.id) is None:
            users.add(
                User(
                    id=seed_user.id,
                    email=seed_user.email,
                    display_name=seed_user.display_name,
                    created_at=now,
                    email_verified_at=now,
                )
            )
            changed = True
    session.flush()

    for seed_user in (LOCAL_REVIEWER, *SEED_ACCOUNTS):
        granted = {
            m.role for m in users.memberships(seed_user.id) if m.project_id == DEMO_PROJECT_ID
        }
        for role in seed_user.roles:
            if role not in granted:
                users.add_membership(
                    Membership(
                        user_id=seed_user.id, project_id=DEMO_PROJECT_ID, role=role, granted_at=now
                    )
                )
                changed = True

    if account_password is not None:
        hasher = hasher or Argon2PasswordHasher()
        for account in SEED_ACCOUNTS:
            changed |= ensure_password(users, hasher, account.id, account_password)

    session.commit()
    return changed


def main() -> None:
    settings = get_settings()
    password = settings.seed_account_password
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            changed = seed(
                session, account_password=None if password is None else password.get_secret_value()
            )
    except InvalidInputError as error:
        sys.exit(f"SEED_ACCOUNT_PASSWORD is not usable: {error.message}. Nothing was seeded.")
    finally:
        engine.dispose()
    sys.stdout.write("Seeded local data.\n" if changed else "Seed data already present.\n")
    if password is None:
        sys.stdout.write(
            "SEED_ACCOUNT_PASSWORD is not set, so the seeded accounts were given no password "
            "and cannot sign in. Run `just setup` to generate one in .env, or set your own, "
            "then run `just seed` again.\n"
        )


if __name__ == "__main__":
    main()
