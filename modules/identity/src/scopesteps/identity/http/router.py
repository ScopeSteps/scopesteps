import logging
from typing import Any

from fastapi import APIRouter, Request, Response, status

from scopesteps.identity.application.sessions import sign_in, sign_out
from scopesteps.identity.application.users import UserProfile, get_user_profile
from scopesteps.identity.domain.errors import InvalidCredentialsError, SignInDisabledError
from scopesteps.identity.http.auth import CurrentActor, SessionAuth, session_cookie
from scopesteps.identity.http.schemas import (
    CurrentUserResponse,
    MembershipResponse,
    SignInRequest,
)
from scopesteps.identity.infrastructure.repository import SqlSessionRepository, SqlUserRepository
from scopesteps.infrastructure.database import utc_now
from scopesteps.infrastructure.http import ErrorResponse, SessionDep

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


def _current_user(profile: UserProfile) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=profile.user.id,
        email=profile.user.email,
        display_name=profile.user.display_name,
        memberships=[
            MembershipResponse(project_id=m.project_id, role=m.role) for m in profile.memberships
        ],
    )
