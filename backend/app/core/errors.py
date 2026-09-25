"""Application errors and the consistent API error envelope (SPEC Â§31)."""

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    EMPTY_UPLOAD = "EMPTY_UPLOAD"
    CORRUPTED_MEDIA = "CORRUPTED_MEDIA"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"
    RECIPE_PROCESSING_FAILED = "RECIPE_PROCESSING_FAILED"
    HTTP_ERROR = "HTTP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for errors that are safe to show to API clients."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        http_status: int | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        self.details = details


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND
    http_status = status.HTTP_404_NOT_FOUND


class ConflictError(AppError):
    code = ErrorCode.CONFLICT
    http_status = status.HTTP_409_CONFLICT


class ConfigurationError(AppError):
    """A required setting or credential is missing for a third-party integration."""

    code = ErrorCode.CONFIGURATION_ERROR
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE


_MEDIA_ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNSUPPORTED_MEDIA: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    ErrorCode.FILE_TOO_LARGE: status.HTTP_413_CONTENT_TOO_LARGE,
    ErrorCode.EMPTY_UPLOAD: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.CORRUPTED_MEDIA: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


class MediaValidationError(AppError):
    """Upload rejected. The HTTP status follows the error code."""

    code = ErrorCode.UNSUPPORTED_MEDIA
    http_status = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode = ErrorCode.UNSUPPORTED_MEDIA,
        details: Any | None = None,
    ) -> None:
        http_status = _MEDIA_ERROR_STATUS.get(code, status.HTTP_422_UNPROCESSABLE_CONTENT)
        super().__init__(message, code=code, http_status=http_status, details=details)


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    """Envelope returned by every failing API call."""

    error: ErrorBody


def error_response(
    http_status: int, code: ErrorCode, message: str, details: Any | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=http_status, content=body.model_dump(exclude_none=True))


_HTTP_STATUS_CODES: dict[int, ErrorCode] = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
}


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    if exc.http_status >= 500:
        logger.error("app_error", extra={"code": exc.code, "path": request.url.path})
    return error_response(exc.http_status, exc.code, exc.message, exc.details)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorCode.VALIDATION_ERROR,
        "The request is invalid.",
        details,
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_CODES.get(exc.status_code, ErrorCode.HTTP_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    response = error_response(exc.status_code, code, message)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Full detail stays in the server log; the client gets a generic message.
    logger.exception("unhandled_error", extra={"path": request.url.path})
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_ERROR,
        "An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected_error)
