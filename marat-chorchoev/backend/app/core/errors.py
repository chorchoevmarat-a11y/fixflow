"""Uniform, machine-readable API errors.

Every error response has the shape::

    {"error": {"code": "SCHEDULE_CONFLICT", "message": "...", "details": {...}},
     "request_id": "..."}
"""

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Any = None,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        self.headers = headers


class BadRequest(AppError):
    status_code = 400
    code = "BAD_REQUEST"


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class Unprocessable(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class PayloadTooLarge(AppError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"


class TooManyRequests(AppError):
    status_code = 429
    code = "RATE_LIMITED"


def error_body(code: str, message: str, request_id: str | None, details: Any = None) -> dict:
    body: dict[str, Any] = {"error": {"code": code, "message": message}, "request_id": request_id}
    if details is not None:
        body["error"]["details"] = details
    return body
