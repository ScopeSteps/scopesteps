from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker


def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        description="Client-generated key. Reusing it with a different request body returns 409.",
    ),
]


class ErrorResponse(BaseModel):
    """The envelope every API error uses. Routes reference it to document extra statuses."""

    code: str
    message: str
    request_id: str
    retryable: bool
    details: dict[str, Any]
