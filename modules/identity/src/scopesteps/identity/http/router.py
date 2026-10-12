from fastapi import APIRouter

from scopesteps.identity.application.users import get_user_profile
from scopesteps.identity.http.auth import CurrentActor
from scopesteps.identity.http.schemas import CurrentUserResponse, MembershipResponse
from scopesteps.identity.infrastructure.repository import SqlUserRepository
from scopesteps.infrastructure.http import SessionDep

router = APIRouter(tags=["identity"])


@router.get("/me")
def get_current_user(actor: CurrentActor, session: SessionDep) -> CurrentUserResponse:
    profile = get_user_profile(SqlUserRepository(session), actor)
    return CurrentUserResponse(
        id=profile.user.id,
        email=profile.user.email,
        display_name=profile.user.display_name,
        memberships=[
            MembershipResponse(project_id=m.project_id, role=m.role) for m in profile.memberships
        ],
    )
