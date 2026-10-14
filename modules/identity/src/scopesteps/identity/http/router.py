import logging
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from scopesteps.identity.application.sessions import sign_in, sign_out
from scopesteps.identity.application.users import (
    UpdateProfile,
    UserProfile,
    get_user_profile,
    list_project_members,
    update_profile,
)
from scopesteps.identity.client import ProjectAccess, Role, get_project_access
from scopesteps.identity.domain.errors import InvalidCredentialsError, SignInDisabledError
from scopesteps.identity.http.auth import CurrentActor, SessionAuth, session_cookie
from scopesteps.identity.http.schemas import (
    CurrentUserResponse,
    MembershipResponse,
    ProjectMemberResponse,
    ProjectMembersResponse,
    SignInRequest,
    UpdateProfileRequest,
)
from scopesteps.identity.infrastructure.repository import SqlSessionRepository, SqlUserRepository
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import ErrorResponse, SessionDep
from scopesteps.projects.client import ProjectId

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
    members = list_project_members(SqlUserRepository(session), access)
    return ProjectMembersResponse(
        members=[
            ProjectMemberResponse(
                user_id=member.user_id,
                display_name=member.display_name,
                job_title=member.job_title,
                roles=sorted(member.roles, key=_ROLE_ORDER),
            )
            for member in members
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
