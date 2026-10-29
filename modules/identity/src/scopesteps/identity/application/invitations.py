"""Inviting people to a project by a personal link, sent by email or copied (ADR 0019).

Every invitation, whether or not its email has an account, has a link that works once, expires
after seven days and is only for that email. Making a new link or cancelling the invitation
stops the old one, since only the newest token's hash is kept. Only an approver manages
invitations; the person invited joins by opening the link.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from scopesteps.identity.application.accounts import AccountStore, Links
from scopesteps.identity.application.emails import EmailMessage, invitation_email, role_names
from scopesteps.identity.application.limits import (
    INVITATION_EMAILS_PER_APPROVER,
    AttemptStore,
    take_attempt,
)
from scopesteps.identity.application.sessions import PasswordHasher, check_password
from scopesteps.identity.client import (
    Actor,
    MemberActivity,
    MemberEvent,
    MemberEventKind,
    ProjectAccess,
    Role,
    UserId,
)
from scopesteps.identity.domain.errors import (
    AccountExistsError,
    AlreadyInvitedError,
    AlreadyMemberError,
    EmailInvalidError,
    InvitationEmailMismatchError,
    InvitationInvalidError,
)
from scopesteps.identity.domain.invitation import Invitation, InvitationId, grantable_roles
from scopesteps.identity.domain.profile import normalize_profile
from scopesteps.identity.domain.tokens import INVITATION_LIFETIME, hash_link_token, new_link_token
from scopesteps.identity.domain.user import User, is_valid_email, normalise_email
from scopesteps.kernel.errors import NotFoundError
from scopesteps.kernel.ids import new_id
from scopesteps.projects.client import ProjectId, ProjectReader


class InvitationStore(Protocol):
    def add(self, invitation: Invitation) -> None: ...

    def get(self, invitation_id: InvitationId) -> Invitation | None: ...

    def by_token_hash(self, token_hash: str) -> Invitation | None: ...

    def for_email(self, project_id: ProjectId, email: str) -> Invitation | None: ...

    def waiting(self, project_id: ProjectId) -> list[Invitation]:
        """The project's invitations nobody has accepted, open or expired, newest first."""
        ...

    def replace_token(
        self, invitation_id: InvitationId, token_hash: str, expires_at: datetime
    ) -> None: ...

    def delete(self, invitation_id: InvitationId) -> None: ...

    def accept(self, invitation: Invitation, at: datetime) -> bool:
        """Compare-and-set on the token the caller opened: False, changing nothing, if it was
        accepted, replaced or cancelled meanwhile."""
        ...


class MemberGrants(Protocol):
    def roles_of(self, project_id: ProjectId, user_id: UserId) -> frozenset[Role]: ...

    def grant(
        self, user_id: UserId, project_id: ProjectId, roles: Collection[Role], now: datetime
    ) -> None:
        """Give the roles the user does not hold yet, in the caller's transaction."""
        ...


@dataclass(frozen=True)
class Invite:
    email: str
    roles: Collection[Role]
    send_email: bool


@dataclass(frozen=True)
class IssuedLink:
    invitation: Invitation
    link: str
    """The only copy of the raw link; it is never stored or logged."""
    email: EmailMessage | None = None
    """The message to send once the transaction commits, when the approver asked for one."""


@dataclass(frozen=True)
class WaitingInvitation:
    invitation: Invitation
    invited_by_name: str


@dataclass(frozen=True)
class InvitationView:
    """What the person who opens a link sees before joining."""

    project_id: ProjectId
    project_name: str
    invited_by_name: str
    email: str
    roles: frozenset[Role]
    expires_at: datetime
    has_account: bool


def invite(
    invitations: InvitationStore,
    members: MemberGrants,
    accounts: AccountStore,
    attempts: AttemptStore,
    projects: ProjectReader,
    activity: MemberActivity,
    links: Links,
    access: ProjectAccess,
    command: Invite,
    now: datetime,
) -> IssuedLink:
    """Invite an email to the project with some roles. Approver only."""
    access.require_role(Role.APPROVER)
    email = normalise_email(command.email)
    if not is_valid_email(email):
        raise EmailInvalidError("Enter a valid email address")
    roles = grantable_roles(command.roles)
    user = accounts.by_email(email)
    if user is not None and members.roles_of(access.project_id, user.id):
        raise AlreadyMemberError("This person is already a member of the project")
    existing = invitations.for_email(access.project_id, email)
    if existing is not None and existing.is_open(now):
        raise AlreadyInvitedError(
            "This email already has an invitation. Copy its link or email it again.",
            details={"invitation_id": str(existing.id)},
        )
    if existing is not None:
        invitations.delete(existing.id)
    raw = new_link_token()
    invitation = Invitation(
        id=InvitationId(new_id()),
        project_id=access.project_id,
        email=email,
        roles=roles,
        invited_by=access.actor.user_id,
        token_hash=hash_link_token(raw),
        expires_at=now + INVITATION_LIFETIME,
        created_at=now,
    )
    invitations.add(invitation)
    _record(
        activity,
        access,
        invitation,
        "member.invited",
        f"Invited someone as {role_names(roles)}",
        now,
    )
    link = links.invitation(raw)
    message = None
    if command.send_email:
        take_attempt(attempts, INVITATION_EMAILS_PER_APPROVER, str(access.actor.user_id), now)
        message = _email(invitation, access.actor, projects, link)
    return IssuedLink(invitation, link, message)


def list_invitations(
    invitations: InvitationStore, accounts: AccountStore, access: ProjectAccess
) -> list[WaitingInvitation]:
    """The invitations nobody has accepted yet, expired ones included. Approver only."""
    access.require_role(Role.APPROVER)
    waiting = invitations.waiting(access.project_id)
    names: dict[UserId, str] = {}
    for invitation in waiting:
        if invitation.invited_by not in names:
            inviter = accounts.get(invitation.invited_by)
            names[invitation.invited_by] = "" if inviter is None else inviter.display_name
    return [WaitingInvitation(i, names[i.invited_by]) for i in waiting]


def new_link(
    invitations: InvitationStore,
    activity: MemberActivity,
    links: Links,
    access: ProjectAccess,
    invitation_id: InvitationId,
    now: datetime,
) -> IssuedLink:
    """A fresh link, valid for seven days from now; the previous one stops working."""
    invitation = _waiting(invitations, access, invitation_id)
    issued = _reissue(invitations, links, invitation, now)
    _record(
        activity, access, invitation, "invitation.link_created", "Made a new invitation link", now
    )
    return issued


def email_invitation(
    invitations: InvitationStore,
    attempts: AttemptStore,
    projects: ProjectReader,
    links: Links,
    access: ProjectAccess,
    invitation_id: InvitationId,
    now: datetime,
) -> IssuedLink:
    """A fresh link to email; the previous one stops working. The caller records
    `invitation_emailed` once the email has gone."""
    invitation = _waiting(invitations, access, invitation_id)
    take_attempt(attempts, INVITATION_EMAILS_PER_APPROVER, str(access.actor.user_id), now)
    issued = _reissue(invitations, links, invitation, now)
    return IssuedLink(
        issued.invitation,
        issued.link,
        _email(issued.invitation, access.actor, projects, issued.link),
    )


def invitation_emailed(
    activity: MemberActivity, access: ProjectAccess, invitation: Invitation, now: datetime
) -> None:
    _record(activity, access, invitation, "invitation.emailed", "Emailed an invitation", now)


def cancel_invitation(
    invitations: InvitationStore,
    activity: MemberActivity,
    access: ProjectAccess,
    invitation_id: InvitationId,
    now: datetime,
) -> None:
    invitation = _waiting(invitations, access, invitation_id)
    invitations.delete(invitation.id)
    _record(
        activity,
        access,
        invitation,
        "invitation.cancelled",
        f"Cancelled an invitation as {role_names(invitation.roles)}",
        now,
    )


def view_invitation(
    invitations: InvitationStore,
    accounts: AccountStore,
    projects: ProjectReader,
    *,
    token: str,
    now: datetime,
) -> InvitationView:
    invitation = _open(invitations, token, now)
    project = projects(invitation.project_id)
    inviter = accounts.get(invitation.invited_by)
    if project is None:
        raise InvitationInvalidError
    return InvitationView(
        project_id=invitation.project_id,
        project_name=project.name,
        invited_by_name="" if inviter is None else inviter.display_name,
        email=invitation.email,
        roles=invitation.roles,
        expires_at=invitation.expires_at,
        has_account=accounts.by_email(invitation.email) is not None,
    )


def accept_invitation(
    invitations: InvitationStore,
    members: MemberGrants,
    accounts: AccountStore,
    activity: MemberActivity,
    actor: Actor,
    *,
    token: str,
    now: datetime,
) -> ProjectId:
    """Join the project as the signed-in person the invitation was sent to."""
    invitation = _open(invitations, token, now)
    user = accounts.get(actor.user_id)
    if user is None or normalise_email(user.email) != invitation.email:
        raise InvitationEmailMismatchError
    if user.email_verified_at is None:
        # The link reached this address, which proves it.
        accounts.mark_verified(user.id, now)
    _join(invitations, members, activity, actor, invitation, now)
    return invitation.project_id


@dataclass(frozen=True)
class InvitedSignUp:
    token: str
    display_name: str
    password: str


def sign_up_with_invitation(
    invitations: InvitationStore,
    members: MemberGrants,
    accounts: AccountStore,
    hasher: PasswordHasher,
    activity: MemberActivity,
    command: InvitedSignUp,
    now: datetime,
) -> tuple[Actor, ProjectId]:
    """Create the account the invitation was sent to and join, in one step. The link proves the
    address, so the account needs no confirmation. Refused when that address already has a
    confirmed account: its owner signs in and joins instead."""
    invitation = _open(invitations, command.token, now)
    name = normalize_profile(command.display_name, "", "").display_name
    check_password(command.password)
    existing = accounts.by_email(invitation.email)
    if existing is not None and existing.email_verified_at is not None:
        raise AccountExistsError
    password_hash = hasher.hash(command.password)
    if existing is None:
        user = User(
            id=UserId(new_id()),
            email=invitation.email,
            display_name=name,
            created_at=now,
            email_verified_at=now,
        )
        accounts.add_account(user, password_hash)
    else:
        # An account nobody confirmed: the invited person takes it over, as a sign-up would.
        accounts.reset_unverified(existing.id, name, password_hash)
        accounts.mark_verified(existing.id, now)
        user = existing
    actor = Actor(user_id=user.id, display_name=name)
    _join(invitations, members, activity, actor, invitation, now)
    return actor, invitation.project_id


def _join(
    invitations: InvitationStore,
    members: MemberGrants,
    activity: MemberActivity,
    actor: Actor,
    invitation: Invitation,
    now: datetime,
) -> None:
    if not invitations.accept(invitation, now):
        raise InvitationInvalidError
    members.grant(actor.user_id, invitation.project_id, invitation.roles, now)
    activity.record(
        MemberEvent(
            project_id=invitation.project_id,
            actor=actor,
            kind="invitation.accepted",
            summary=f"Joined the project as {role_names(invitation.roles)}",
            occurred_at=now,
            member_id=actor.user_id,
            invitation_id=invitation.id,
        )
    )


def _open(invitations: InvitationStore, token: str, now: datetime) -> Invitation:
    """The invitation a link names, if it still works. Unknown, used, replaced, cancelled and
    expired links all get the same answer."""
    invitation = invitations.by_token_hash(hash_link_token(token))
    if invitation is None or not invitation.is_open(now):
        raise InvitationInvalidError
    return invitation


def _waiting(
    invitations: InvitationStore, access: ProjectAccess, invitation_id: InvitationId
) -> Invitation:
    access.require_role(Role.APPROVER)
    invitation = invitations.get(invitation_id)
    if (
        invitation is None
        or invitation.project_id != access.project_id
        or invitation.accepted_at is not None
    ):
        raise NotFoundError("Invitation not found")
    return invitation


def _reissue(
    invitations: InvitationStore, links: Links, invitation: Invitation, now: datetime
) -> IssuedLink:
    raw = new_link_token()
    token_hash = hash_link_token(raw)
    expires_at = now + INVITATION_LIFETIME
    invitations.replace_token(invitation.id, token_hash, expires_at)
    reissued = Invitation(
        id=invitation.id,
        project_id=invitation.project_id,
        email=invitation.email,
        roles=invitation.roles,
        invited_by=invitation.invited_by,
        token_hash=token_hash,
        expires_at=expires_at,
        created_at=invitation.created_at,
    )
    return IssuedLink(reissued, links.invitation(raw))


def _email(
    invitation: Invitation, inviter: Actor, projects: ProjectReader, link: str
) -> EmailMessage:
    project = projects(invitation.project_id)
    if project is None:
        raise NotFoundError("Project not found")
    return invitation_email(
        to=invitation.email,
        inviter=inviter.display_name,
        project=project.name,
        roles=invitation.roles,
        link=link,
        expires_at=invitation.expires_at,
    )


def _record(
    activity: MemberActivity,
    access: ProjectAccess,
    invitation: Invitation,
    kind: MemberEventKind,
    summary: str,
    now: datetime,
) -> None:
    activity.record(
        MemberEvent(
            project_id=access.project_id,
            actor=access.actor,
            kind=kind,
            summary=summary,
            occurred_at=now,
            invitation_id=invitation.id,
        )
    )
