import logging
from collections.abc import Callable, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scopesteps.identity.application import accounts, invitations, members
from scopesteps.identity.application.accounts import Links
from scopesteps.identity.application.emails import EmailMessage, EmailSender, EmailSendError
from scopesteps.identity.application.invitations import IssuedLink, WaitingInvitation
from scopesteps.identity.application.sessions import SignedIn, sign_in, sign_out, start_session
from scopesteps.identity.application.users import (
    UpdateProfile,
    UserProfile,
    get_user_profile,
    list_project_members,
    update_profile,
)
from scopesteps.identity.client import (
    Actor,
    MemberActivity,
    ProjectAccess,
    Role,
    UserId,
    get_member_activity,
    get_project_access,
)
from scopesteps.identity.domain.errors import (
    EmailFailedError,
    InvalidCredentialsError,
    MemberChangedError,
    SignInDisabledError,
)
from scopesteps.identity.domain.invitation import Invitation, InvitationId
from scopesteps.identity.http.auth import CurrentActor, SessionAuth, session_cookie
from scopesteps.identity.http.schemas import (
    ChangeRolesRequest,
    CheckYourEmailResponse,
    CurrentUserResponse,
    InvitationCreatedResponse,
    InvitationLinkResponse,
    InvitationPreviewResponse,
    InvitationResponse,
    InvitationsResponse,
    InvitedSignUpRequest,
    InviteRequest,
    JoinedResponse,
    MembershipResponse,
    ProjectMemberResponse,
    ProjectMembersResponse,
    ResendVerificationRequest,
    SignInRequest,
    SignUpRequest,
    UpdateProfileRequest,
    VerifyEmailRequest,
)
from scopesteps.identity.infrastructure.repository import (
    SqlAttemptStore,
    SqlEmailTokenStore,
    SqlInvitationStore,
    SqlMemberStore,
    SqlSessionRepository,
    SqlUserRepository,
)
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import ErrorResponse, SessionDep
from scopesteps.projects.client import ProjectId, ProjectReader, get_project_reader

logger = logging.getLogger(__name__)

router = APIRouter(tags=["identity"])

# Routes a client must reach without a session. The composition root mounts this router
# without the authentication dependency every other route gets.
public_router = APIRouter(tags=["identity"])

SIGN_IN_REJECTIONS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "`INVALID_CREDENTIALS`: the same response for an unknown email and a "
        "wrong password",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "`SIGN_IN_DISABLED`: the server runs with local development authentication",
    },
}


@router.get("/me")
def get_current_user(actor: CurrentActor, session: SessionDep) -> CurrentUserResponse:
    return _current_user(get_user_profile(SqlUserRepository(session), actor))


PROFILE_REJECTIONS: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "`PROFILE_CHANGED`: `expected_revision` is stale. Read `/me` again.",
    },
}


@router.patch("/me", responses=PROFILE_REJECTIONS)
def update_current_user_profile(
    body: UpdateProfileRequest, actor: CurrentActor, session: SessionDep
) -> CurrentUserResponse:
    """Update the signed-in user's name, job title and about text. Email and roles are read-only.

    Sending the profile that is already stored succeeds without a new revision, so a retry is
    safe without an Idempotency-Key.
    """
    profile = update_profile(
        SqlUserRepository(session),
        actor,
        UpdateProfile(
            display_name=body.display_name,
            job_title=body.job_title,
            about=body.about,
            expected_revision=body.expected_revision,
        ),
    )
    session.commit()
    return _current_user(profile)


@router.get("/projects/{project_id}/members")
def list_members(
    project_id: ProjectId,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    session: SessionDep,
) -> ProjectMembersResponse:
    """Everyone with a role in the project, ordered by name. Any member may read it."""
    found = list_project_members(SqlUserRepository(session), access)
    return ProjectMembersResponse(
        members=[
            ProjectMemberResponse(
                user_id=member.user_id,
                display_name=member.display_name,
                job_title=member.job_title,
                roles=sorted(member.roles, key=_ROLE_ORDER),
                revision=member.revision,
            )
            for member in found
        ]
    )


@public_router.post("/auth/sign-in", responses=SIGN_IN_REJECTIONS)
def sign_in_with_password(
    body: SignInRequest, request: Request, response: Response, session: SessionDep
) -> CurrentUserResponse:
    """Start a session and set it as an HttpOnly cookie. The token appears nowhere else.

    Any session the client already holds is ended first.
    """
    auth = request.app.state.auth
    if not isinstance(auth, SessionAuth):
        raise SignInDisabledError
    users = SqlUserRepository(session)
    try:
        signed_in = sign_in(
            users,
            users,
            SqlSessionRepository(session),
            auth.hasher,
            auth.policy,
            email=body.email,
            password=body.password.get_secret_value(),
            presented_token=request.cookies.get(auth.cookie.name),
            now=utc_now(),
        )
    except InvalidCredentialsError:
        logger.info("Sign-in refused", extra={"request_id": request.state.request_id})
        raise
    profile = get_user_profile(users, signed_in.actor)
    session.commit()
    logger.info(
        "Signed in",
        extra={"request_id": request.state.request_id, "user_id": str(signed_in.actor.user_id)},
    )
    _set_session_cookie(response, auth, signed_in)
    return _current_user(profile)


@public_router.post("/auth/sign-out", status_code=status.HTTP_204_NO_CONTENT)
def sign_out_of_session(request: Request, response: Response, session: SessionDep) -> None:
    """End the session on the server and clear the cookie. Succeeds without a session too."""
    auth = request.app.state.auth
    # Under local development authentication there is no session, but a cookie left over from
    # session mode is still cleared.
    cookie = auth.cookie if isinstance(auth, SessionAuth) else session_cookie(secure=False)
    sign_out(SqlSessionRepository(session), token=request.cookies.get(cookie.name))
    session.commit()

    response.delete_cookie(
        cookie.name, path="/", secure=cookie.secure, httponly=True, samesite="lax"
    )


CHECK_YOUR_EMAIL = CheckYourEmailResponse(
    message="Check your email. If the address can be used, we sent it a link to continue."
)
RATE_LIMITED: dict[int | str, dict[str, Any]] = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": ErrorResponse,
        "description": "`RATE_LIMITED`: too many attempts in the last hour. Retryable later.",
    }
}
EMAIL_REJECTIONS: dict[int | str, dict[str, Any]] = {
    **RATE_LIMITED,
    status.HTTP_502_BAD_GATEWAY: {
        "model": ErrorResponse,
        "description": "`EMAIL_FAILED`: the email service did not take the message. Retry, or "
        "copy the link instead.",
    },
}
ActivityDep = Annotated[MemberActivity, Depends(get_member_activity)]
ProjectsDep = Annotated[ProjectReader, Depends(get_project_reader)]
AccessDep = Annotated[ProjectAccess, Depends(get_project_access)]


@public_router.post("/auth/sign-up", status_code=status.HTTP_202_ACCEPTED, responses=RATE_LIMITED)
def sign_up(body: SignUpRequest, request: Request, session: SessionDep) -> CheckYourEmailResponse:
    """Create an account that can sign in once its email is confirmed by the link sent to it.

    The answer is the same whether or not the address has an account; an existing owner is told
    by email instead. A weak password is `422`, too many attempts `429 RATE_LIMITED`.
    """
    auth = _session_auth(request)
    users = SqlUserRepository(session)
    messages = accounts.sign_up(
        users,
        SqlEmailTokenStore(session),
        SqlAttemptStore(session),
        auth.hasher,
        _links(request),
        accounts.SignUp(
            display_name=body.display_name,
            email=body.email,
            password=body.password.get_secret_value(),
            client_address=_client_address(request),
        ),
        utc_now(),
    )
    session.commit()
    logger.info("Sign-up requested", extra={"request_id": request.state.request_id})
    # Its failure stays private: the answer must not differ, and the person can ask again.
    _send_quietly(request, messages)
    return CHECK_YOUR_EMAIL


@public_router.post(
    "/auth/resend-verification", status_code=status.HTTP_202_ACCEPTED, responses=RATE_LIMITED
)
def resend_verification(
    body: ResendVerificationRequest, request: Request, session: SessionDep
) -> CheckYourEmailResponse:
    """Send a new confirmation link to an account that has not confirmed its email. The answer
    is the same for every address."""
    messages = accounts.resend_confirmation(
        SqlUserRepository(session),
        SqlEmailTokenStore(session),
        SqlAttemptStore(session),
        _links(request),
        email=body.email,
        client_address=_client_address(request),
        now=utc_now(),
    )
    session.commit()
    _send_quietly(request, messages)
    return CHECK_YOUR_EMAIL


@public_router.post("/auth/verify-email")
def verify_email(
    body: VerifyEmailRequest, request: Request, response: Response, session: SessionDep
) -> CurrentUserResponse:
    """Confirm the email address the link was sent to and sign in. The link works once and for
    24 hours; otherwise `404 TOKEN_INVALID`."""
    auth = _session_auth(request)
    users = SqlUserRepository(session)
    now = utc_now()
    actor = accounts.confirm_email(users, SqlEmailTokenStore(session), token=body.token, now=now)
    signed_in = _start_session(request, session, auth, actor)
    profile = get_user_profile(users, actor)
    session.commit()
    _set_session_cookie(response, auth, signed_in)
    return _current_user(profile)


@public_router.get("/invitations/{token}")
def preview_invitation(
    token: str, projects: ProjectsDep, session: SessionDep
) -> InvitationPreviewResponse:
    """Who invited the person to which project, as which roles, until when, and whether the
    invited email has an account. An unknown, expired, used, replaced or cancelled link is
    `404 INVITATION_INVALID`."""
    view = invitations.view_invitation(
        SqlInvitationStore(session),
        SqlUserRepository(session),
        projects,
        token=token,
        now=utc_now(),
    )
    return InvitationPreviewResponse(
        project_id=view.project_id,
        project_name=view.project_name,
        invited_by_name=view.invited_by_name,
        email=view.email,
        roles=sorted(view.roles, key=_ROLE_ORDER),
        expires_at=view.expires_at,
        has_account=view.has_account,
    )


@public_router.post("/invitations/{token}/sign-up")
def sign_up_with_invitation(
    token: str,
    body: InvitedSignUpRequest,
    request: Request,
    response: Response,
    activity: ActivityDep,
    session: SessionDep,
) -> JoinedResponse:
    """Create the invited email's account, join the project and sign in, in one step. The link
    proves the address. `409 ACCOUNT_EXISTS` when it already has an account: sign in and join."""
    auth = _session_auth(request)
    users = SqlUserRepository(session)
    now = utc_now()
    actor, project_id = invitations.sign_up_with_invitation(
        SqlInvitationStore(session),
        SqlMemberStore(session),
        users,
        auth.hasher,
        activity,
        invitations.InvitedSignUp(
            token=token,
            display_name=body.display_name,
            password=body.password.get_secret_value(),
        ),
        now,
    )
    signed_in = _start_session(request, session, auth, actor)
    profile = get_user_profile(users, actor)
    session.commit()
    _set_session_cookie(response, auth, signed_in)
    return JoinedResponse(project_id=project_id, user=_current_user(profile))


@router.post("/invitations/{token}/accept")
def accept_invitation(
    token: str, actor: CurrentActor, activity: ActivityDep, session: SessionDep
) -> JoinedResponse:
    """Join the project as the signed-in person the invitation is for. Another account gets
    `403 INVITATION_EMAIL_MISMATCH`; a link that no longer works `404 INVITATION_INVALID`."""
    users = SqlUserRepository(session)
    project_id = invitations.accept_invitation(
        SqlInvitationStore(session),
        SqlMemberStore(session),
        users,
        activity,
        actor,
        token=token,
        now=utc_now(),
    )
    profile = get_user_profile(users, actor)
    session.commit()
    return JoinedResponse(project_id=project_id, user=_current_user(profile))


@router.post(
    "/projects/{project_id}/members",
    status_code=status.HTTP_201_CREATED,
    responses=RATE_LIMITED,
)
def invite_member(
    project_id: ProjectId,
    body: InviteRequest,
    request: Request,
    access: AccessDep,
    activity: ActivityDep,
    projects: ProjectsDep,
    session: SessionDep,
) -> InvitationCreatedResponse:
    """Invite an email with one or more roles. Approver only. Every invitation gets a personal
    link that works once and expires after 7 days. Already a member: `409 ALREADY_MEMBER`;
    already invited: `409 ALREADY_INVITED`. When the email cannot be sent the invitation still
    stands and its link is returned to copy."""
    users = SqlUserRepository(session)
    issued = invitations.invite(
        SqlInvitationStore(session),
        SqlMemberStore(session),
        users,
        SqlAttemptStore(session),
        projects,
        activity,
        _links(request),
        access,
        invitations.Invite(
            email=body.email, roles=[Role(role) for role in body.roles], send_email=body.send_email
        ),
        utc_now(),
    )
    session.commit()
    sent = issued.email is not None and _emailed(request, session, access, activity, issued)
    return InvitationCreatedResponse(
        invitation=_invitation(issued.invitation, access.actor.display_name),
        link=None if sent else issued.link,
        email_sent=sent,
    )


@router.get("/projects/{project_id}/invitations")
def list_invitations(
    project_id: ProjectId, access: AccessDep, session: SessionDep
) -> InvitationsResponse:
    """The invitations nobody has accepted yet, expired ones included. Approver only."""
    waiting = invitations.list_invitations(
        SqlInvitationStore(session), SqlUserRepository(session), access
    )
    return InvitationsResponse(invitations=[_waiting(w) for w in waiting])


@router.post("/projects/{project_id}/invitations/{invitation_id}/link")
def new_invitation_link(
    project_id: ProjectId,
    invitation_id: InvitationId,
    request: Request,
    access: AccessDep,
    activity: ActivityDep,
    session: SessionDep,
) -> InvitationLinkResponse:
    """A new link for the invitation, valid for 7 days. The previous link stops working.
    Approver only."""
    issued = invitations.new_link(
        SqlInvitationStore(session), activity, _links(request), access, invitation_id, utc_now()
    )
    session.commit()
    return InvitationLinkResponse(
        invitation=_invitation(issued.invitation, _inviter(session, issued.invitation)),
        link=issued.link,
    )


@router.post(
    "/projects/{project_id}/invitations/{invitation_id}/email",
    status_code=status.HTTP_202_ACCEPTED,
    responses=EMAIL_REJECTIONS,
)
def email_invitation(
    project_id: ProjectId,
    invitation_id: InvitationId,
    request: Request,
    access: AccessDep,
    activity: ActivityDep,
    projects: ProjectsDep,
    session: SessionDep,
) -> InvitationResponse:
    """Email a new link for the invitation; the previous one stops working. Approver only, at
    most 20 invitation emails an hour (`429 RATE_LIMITED`); `502 EMAIL_FAILED` when the email
    service refuses it."""
    issued = invitations.email_invitation(
        SqlInvitationStore(session),
        SqlAttemptStore(session),
        projects,
        _links(request),
        access,
        invitation_id,
        utc_now(),
    )
    session.commit()
    if not _emailed(request, session, access, activity, issued):
        raise EmailFailedError
    return _invitation(issued.invitation, _inviter(session, issued.invitation))


@router.delete(
    "/projects/{project_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_invitation(
    project_id: ProjectId,
    invitation_id: InvitationId,
    access: AccessDep,
    activity: ActivityDep,
    session: SessionDep,
) -> None:
    """Cancel an invitation; its link stops working. Approver only."""
    invitations.cancel_invitation(
        SqlInvitationStore(session), activity, access, invitation_id, utc_now()
    )
    session.commit()


@router.put("/projects/{project_id}/members/{user_id}/roles")
def change_member_roles(
    project_id: ProjectId,
    user_id: UserId,
    body: ChangeRolesRequest,
    access: AccessDep,
    activity: ActivityDep,
    session: SessionDep,
) -> ProjectMemberResponse:
    """Give a member exactly these roles. Approver only. A stale `expected_revision` is
    `409 MEMBER_CHANGED`; taking Approver from the last approver `409 LAST_APPROVER`."""
    users = SqlUserRepository(session)
    _committing(
        session,
        lambda: members.change_roles(
            SqlMemberStore(session),
            users,
            activity,
            access,
            user_id,
            [Role(role) for role in body.roles],
            expected_revision=body.expected_revision,
            now=utc_now(),
        ),
    )
    member = next(m for m in list_project_members(users, access) if m.user_id == user_id)
    return ProjectMemberResponse(
        user_id=member.user_id,
        display_name=member.display_name,
        job_title=member.job_title,
        roles=sorted(member.roles, key=_ROLE_ORDER),
        revision=member.revision,
    )


@router.delete("/projects/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id: ProjectId,
    user_id: UserId,
    access: AccessDep,
    activity: ActivityDep,
    session: SessionDep,
) -> None:
    """Remove a member (approver only), or leave the project when `user_id` is your own. Access
    ends at once; what they wrote keeps their name. The last approver cannot leave or be removed:
    `409 LAST_APPROVER`."""
    _committing(
        session,
        lambda: members.remove_member(
            SqlMemberStore(session),
            SqlUserRepository(session),
            activity,
            access,
            user_id,
            utc_now(),
        ),
    )


def _committing(session: Session, change: Callable[[], None]) -> None:
    try:
        change()
        session.commit()
    except IntegrityError as error:
        # Another approver changed the same member first; nothing of this request was saved.
        session.rollback()
        raise MemberChangedError(
            "This member was changed meanwhile. Reload the members and try again."
        ) from error


def _session_auth(request: Request) -> SessionAuth:
    auth = request.app.state.auth
    if not isinstance(auth, SessionAuth):
        raise SignInDisabledError
    return auth


def _links(request: Request) -> Links:
    links: Links = request.app.state.links
    return links


def _client_address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _start_session(request: Request, session: Session, auth: SessionAuth, actor: Actor) -> SignedIn:
    return start_session(
        SqlSessionRepository(session),
        auth.policy,
        actor,
        presented_token=request.cookies.get(auth.cookie.name),
        now=utc_now(),
    )


def _set_session_cookie(response: Response, auth: SessionAuth, signed_in: SignedIn) -> None:
    response.set_cookie(
        auth.cookie.name,
        signed_in.token,
        max_age=int(auth.policy.absolute_lifetime.total_seconds()),
        path="/",
        secure=auth.cookie.secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def _send(request: Request, message: EmailMessage) -> bool:
    """Send after the transaction committed. A failure is logged by kind only: the message
    holds a link."""
    sender: EmailSender = request.app.state.email_sender
    try:
        sender.send(message)
    except EmailSendError as error:
        logger.warning(
            "Email not sent",
            extra={"request_id": request.state.request_id, "error": str(error)},
        )
        return False
    return True


def _send_quietly(request: Request, messages: Sequence[EmailMessage]) -> None:
    for message in messages:
        _send(request, message)


def _emailed(
    request: Request,
    session: Session,
    access: ProjectAccess,
    activity: MemberActivity,
    issued: IssuedLink,
) -> bool:
    """Send the invitation's email and, once it has gone, record that it was."""
    if issued.email is None or not _send(request, issued.email):
        return False
    invitations.invitation_emailed(activity, access, issued.invitation, utc_now())
    session.commit()
    return True


def _inviter(session: Session, invitation: Invitation) -> str:
    inviter = SqlUserRepository(session).get(invitation.invited_by)
    return "" if inviter is None else inviter.display_name


def _invitation(invitation: Invitation, invited_by_name: str) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        roles=sorted(invitation.roles, key=_ROLE_ORDER),
        invited_by=invitation.invited_by,
        invited_by_name=invited_by_name,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        expired=not invitation.is_open(utc_now()),
    )


def _waiting(waiting: WaitingInvitation) -> InvitationResponse:
    return _invitation(waiting.invitation, waiting.invited_by_name)


_ROLE_ORDER: Callable[[Role], int] = list(Role).index


def _current_user(profile: UserProfile) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=profile.user.id,
        email=profile.user.email,
        display_name=profile.user.display_name,
        job_title=profile.user.job_title,
        about=profile.user.about,
        revision=profile.user.revision,
        memberships=[
            MembershipResponse(project_id=m.project_id, role=m.role) for m in profile.memberships
        ],
    )
