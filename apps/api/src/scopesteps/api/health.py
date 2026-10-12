from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Engine, text

from scopesteps.api.database import get_engine

router = APIRouter(prefix="/health", tags=["health"])


class HealthStatus(BaseModel):
    status: str


class ErrorDetail(BaseModel):
    detail: str


@router.get("/live")
def live() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/ready",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorDetail,
            "description": "Database unavailable",
        }
    },
)
def ready(engine: Annotated[Engine, Depends(get_engine)]) -> HealthStatus:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable") from exc
    return HealthStatus(status="ok")
