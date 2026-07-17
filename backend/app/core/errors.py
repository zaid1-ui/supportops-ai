"""Application errors and FastAPI exception handlers."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base application error."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class AuthError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class PermissionError_(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class AgentError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "agent_failure"


class ToolError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "tool_failure"


def _envelope(code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


# HTTP status -> stable machine-readable code. The frontend switches on `code`,
# never on the prose in `message`, which is free to change.
_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    502: "upstream_failure",
    503: "unavailable",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        logger.warning("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        """Render HTTPException in the same envelope as AppError.

        Without this, FastAPI emits {"detail": ...} for HTTPException while
        AppError emits {"error": {...}}, so the API returns two different error
        shapes and every client has to parse both. One shape, one parser.
        """
        code = _STATUS_CODES.get(exc.status_code, "error")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail), {}),
            # 401 must keep WWW-Authenticate or the challenge is lost.
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("validation_error", "Request validation failed",
                              {"errors": exc.errors()}),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Log the detail, return none of it: an internal traceback in an HTTP
        # response is an information leak.
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "An unexpected error occurred", {}),
        )
