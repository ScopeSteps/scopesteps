import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from scopesteps.infrastructure.http import ErrorResponse
from scopesteps.kernel.errors import (
    ConflictError,
    DomainError,
    FeatureNotImplementedError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
    UnauthenticatedError,
    UnavailableError,
    UnsupportedMediaTypeError,
)

logger = logging.getLogger(__name__)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    UnauthenticatedError: status.HTTP_401_UNAUTHORIZED,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    PayloadTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    UnsupportedMediaTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    InvalidInputError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    FeatureNotImplementedError: status.HTTP_501_NOT_IMPLEMENTED,
    UnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500, 501, 503)
}


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle_domain_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(HTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected_error)


def error_response(
    request: Request,
    status_code: int,
    *,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        code=code,
        message=message,
        request_id=request.state.request_id,
        retryable=retryable,
        details=details or {},
    )
    return JSONResponse(jsonable_encoder(body), status_code=status_code)


def _status_for(error: DomainError) -> int:
    for error_type in type(error).__mro__:
        if error_type in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[error_type]
    return status.HTTP_400_BAD_REQUEST


async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise exc
    return error_response(
        request,
        _status_for(exc),
        code=exc.code,
        message=exc.message,
        retryable=exc.retryable,
        details=exc.details,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="VALIDATION_ERROR",
        message="The request is invalid",
        details={"errors": exc.errors()},
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise exc
    return error_response(
        request,
        exc.status_code,
        code="HTTP_ERROR",
        message=str(exc.detail),
        retryable=exc.status_code >= 500,
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", extra={"request_id": request.state.request_id})
    return error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        retryable=True,
    )
