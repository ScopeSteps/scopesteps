from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from scopesteps.api.errors import ErrorResponse, error_response
from scopesteps.api.migrations import schema_is_current

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/live")
def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
)
def ready(request: Request) -> HealthResponse | JSONResponse:
    engine: Engine = request.app.state.engine
    try:
        current = schema_is_current(engine)
    except SQLAlchemyError:
        return _unavailable(request, "DATABASE_UNAVAILABLE", "The database is unreachable")
    if not current:
        return _unavailable(
            request, "SCHEMA_OUTDATED", "The database schema is not migrated. Run `just migrate`."
        )
    return HealthResponse(status="ok")


def _unavailable(request: Request, code: str, message: str) -> JSONResponse:
    return error_response(
        request, status.HTTP_503_SERVICE_UNAVAILABLE, code=code, message=message, retryable=True
    )
