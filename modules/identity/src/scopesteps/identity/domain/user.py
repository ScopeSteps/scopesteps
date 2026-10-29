import re
from dataclasses import dataclass
from datetime import datetime

from scopesteps.identity.client import Role, UserId
from scopesteps.projects.client import ProjectId

# Long enough to resist guessing without a complexity rule (NIST SP 800-63B). The upper bound
# only stops a huge input from tying up the password hasher.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024


MAX_EMAIL_LENGTH = 320
# Enough to catch a typo; whether an address really exists is proven by the link sent to it.
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def normalise_email(email: str) -> str:
    """Emails identify accounts case-insensitively; stored and compared in this form."""
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    """`email` is normalised."""
    return len(email) <= MAX_EMAIL_LENGTH and _EMAIL.fullmatch(email) is not None


@dataclass(frozen=True)
class User:
    id: UserId
    email: str
    display_name: str
    created_at: datetime
    job_title: str = ""
    about: str = ""
    revision: int = 1
    """Goes up by one with every saved profile change, so a writer can tell its copy is stale."""
    email_verified_at: datetime | None = None
    """When the address was proven: by a confirmation link, or by accepting an invitation sent
    to it. Until then the account cannot sign in."""


@dataclass(frozen=True)
class ProjectMember:
    """A member of one project as other members see them: no email."""

    user_id: UserId
    display_name: str
    job_title: str
    roles: frozenset[Role]
    revision: int = 1
    """Goes up by one whenever the member's roles change, so an approver's change can be refused
    when they read a stale copy."""


@dataclass(frozen=True)
class Membership:
    """A project-scoped role. Roles combine; none implies another."""

    user_id: UserId
    project_id: ProjectId
    role: Role
    granted_at: datetime


@dataclass(frozen=True)
class Credentials:
    """A user's password hash, kept apart from `User` so it cannot ride along into a response."""

    user_id: UserId
    password_hash: str | None
    email_verified: bool
