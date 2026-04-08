"""Error handling and app-level integration for fastapi-refine."""

from __future__ import annotations

from collections import defaultdict
from http import HTTPStatus
import logging
from typing import Any, cast

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import (
    http_exception_handler as fastapi_http_exception_handler,
)
from fastapi.exception_handlers import (
    request_validation_exception_handler as fastapi_request_validation_exception_handler,
)
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.utils import is_body_allowed_for_status_code
from starlette._utils import is_async_callable
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

__all__ = [
    "RefineHTTPException",
    "configure_refine",
    "format_refine_http_exception",
    "format_refine_validation_error",
    "refine_http_exception_handler",
    "refine_validation_exception_handler",
]

ERROR_CODE_BY_STATUS = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    422: "validation_error",
}
REQUEST_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}
logger = logging.getLogger("fastapi_refine")


def error_code_for_status(status_code: int) -> str:
    """Map an HTTP status code to a stable error code."""
    return ERROR_CODE_BY_STATUS.get(status_code, f"http_{status_code}")


class RefineHTTPException(FastAPIHTTPException):
    """HTTP exception carrying Refine-specific error metadata.

    The base `detail` remains a plain string so apps that do not install
    `configure_refine(app)` keep FastAPI's default `{"detail": "..."}` behavior.
    When `configure_refine(app)` is installed, fastapi-refine handles this exception
    directly to preserve the Refine error envelope.
    """

    def __init__(
        self,
        *,
        status_code: int,
        message: str,
        detail_message: str | None = None,
        code: str | None = None,
        errors: dict[str, list[str]] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(
            status_code=status_code,
            detail=detail_message or message,
            headers=headers,
        )
        self.message = message
        self.detail_message = detail_message
        self.code = code or error_code_for_status(status_code)
        self.errors = errors


def _default_message_for_status(status_code: int) -> str:
    if status_code == 422:
        return "Validation failed"
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return f"HTTP {status_code}"


def _jsonable_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], jsonable_encoder(payload))


def format_refine_http_exception(http_exc: StarletteHTTPException) -> dict[str, Any]:
    if isinstance(http_exc, RefineHTTPException):
        normalized = {
            "message": http_exc.message,
            "statusCode": http_exc.status_code,
            "code": http_exc.code,
        }
        if http_exc.detail_message and http_exc.detail_message != http_exc.message:
            normalized["detail"] = http_exc.detail_message
        if http_exc.errors is not None:
            normalized["errors"] = http_exc.errors
        return _jsonable_payload(normalized)

    detail = http_exc.detail
    if isinstance(detail, str) and detail:
        return _jsonable_payload(
            {
                "message": detail,
                "statusCode": http_exc.status_code,
                "code": error_code_for_status(http_exc.status_code),
            }
        )

    if detail is None:
        return _jsonable_payload(
            {
                "message": _default_message_for_status(http_exc.status_code),
                "statusCode": http_exc.status_code,
                "code": error_code_for_status(http_exc.status_code),
            }
        )

    if isinstance(detail, dict):
        normalized = {
            "message": detail.get("message")
            or _default_message_for_status(http_exc.status_code),
            "statusCode": http_exc.status_code,
            "code": detail.get("code") or error_code_for_status(http_exc.status_code),
            "detail": detail,
        }
        return _jsonable_payload(normalized)

    return _jsonable_payload(
        {
            "message": _default_message_for_status(http_exc.status_code),
            "statusCode": http_exc.status_code,
            "code": error_code_for_status(http_exc.status_code),
            "detail": detail,
        }
    )


def _loc_to_key(loc: tuple[Any, ...] | list[Any]) -> str:
    parts = list(loc)
    if parts and parts[0] in REQUEST_LOC_PREFIXES:
        parts = parts[1:]
    if not parts:
        return "_root"
    return ".".join(str(part) for part in parts)


def _validation_errors_map(exc: RequestValidationError) -> dict[str, list[str]]:
    errors_by_key: defaultdict[str, list[str]] = defaultdict(list)
    for error in exc.errors():
        key = _loc_to_key(error.get("loc", ()))
        message = error.get("msg", "Invalid value")
        errors_by_key[key].append(message)
    return dict(errors_by_key)


def format_refine_validation_error(exc: RequestValidationError) -> dict[str, Any]:
    return _jsonable_payload(
        {
            "message": "Validation failed",
            "statusCode": 422,
            "code": error_code_for_status(422),
            "errors": _validation_errors_map(exc),
        }
    )


async def refine_http_exception_handler(
    _request: Request, exc: Exception
) -> Response:
    http_exc = cast(StarletteHTTPException, exc)
    if not is_body_allowed_for_status_code(http_exc.status_code):
        return Response(
            status_code=http_exc.status_code,
            headers=http_exc.headers,
        )
    return JSONResponse(
        status_code=http_exc.status_code,
        content=format_refine_http_exception(http_exc),
        headers=http_exc.headers,
    )


async def refine_validation_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    validation_exc = cast(RequestValidationError, exc)
    return JSONResponse(
        status_code=422,
        content=format_refine_validation_error(validation_exc),
    )


def _has_custom_starlette_http_exception_handler(app: FastAPI) -> bool:
    starlette_handler = app.exception_handlers.get(StarletteHTTPException)
    return (
        starlette_handler is not None
        and starlette_handler is not fastapi_http_exception_handler
    )


def _has_custom_validation_exception_handler(app: FastAPI) -> bool:
    validation_handler = app.exception_handlers.get(RequestValidationError)
    return (
        validation_handler is not None
        and validation_handler is not fastapi_request_validation_exception_handler
    )


def _handler_name(handler: Any) -> str:
    module = getattr(handler, "__module__", None)
    qualname = getattr(handler, "__qualname__", None)
    if module and qualname:
        return f"{module}.{qualname}"
    name = getattr(handler, "__name__", None)
    if module and name:
        return f"{module}.{name}"
    return repr(handler)


def _resolve_refine_exception_handler(app: FastAPI) -> Any:
    return app.exception_handlers.get(RefineHTTPException, refine_http_exception_handler)


async def _call_exception_handler(
    handler: Any, request: Request, exc: Exception
) -> Response:
    if is_async_callable(handler):
        return cast(Response, await handler(request, exc))
    return cast(Response, await run_in_threadpool(handler, request, exc))


def _warn_about_bypassed_generic_http_handlers(app: FastAPI) -> None:
    if app.exception_handlers.get(RefineHTTPException) is not None:
        return

    handlers_to_warn: list[Any] = []
    fastapi_http_handler = app.exception_handlers.get(FastAPIHTTPException)
    if (
        fastapi_http_handler is not None
        and fastapi_http_handler is not fastapi_http_exception_handler
    ):
        handlers_to_warn.append(fastapi_http_handler)

    starlette_http_handler = app.exception_handlers.get(StarletteHTTPException)
    if (
        starlette_http_handler is not None
        and starlette_http_handler is not fastapi_http_exception_handler
        and starlette_http_handler not in handlers_to_warn
    ):
        handlers_to_warn.append(starlette_http_handler)

    for handler in handlers_to_warn:
        logger.warning(
            "configure_refine(app) detected custom generic HTTP exception handler %s, "
            "but package-generated RefineHTTPException values will bypass it and use %s. "
            "Register RefineHTTPException explicitly if you need the same logging, "
            "headers, or trace IDs.",
            _handler_name(handler),
            _handler_name(refine_http_exception_handler),
        )


def _wrap_status_handler_for_refine_errors(
    app: FastAPI,
    handler: Any,
) -> Any:
    if getattr(handler, "__fastapi_refine_status_wrapper__", False):
        return handler

    async def wrapped_handler(request: Request, exc: Exception) -> Response:
        if isinstance(exc, RefineHTTPException):
            refine_handler = _resolve_refine_exception_handler(app)
            return await _call_exception_handler(refine_handler, request, exc)

        return await _call_exception_handler(handler, request, exc)

    setattr(wrapped_handler, "__fastapi_refine_status_wrapper__", True)
    return wrapped_handler


def _rebuild_middleware_stack_if_needed(app: FastAPI) -> None:
    if app.middleware_stack is not None:
        app.middleware_stack = app.build_middleware_stack()


def configure_refine(app: FastAPI) -> FastAPI:
    """Configure app-level Refine integration for error formatting.

    This helper preserves any existing `RefineHTTPException` handler (or installs the
    default one), wraps the numeric status handlers visible at call time, and installs default
    `StarletteHTTPException` / `RequestValidationError` handlers only when those slots
    are still using FastAPI's defaults.
    """

    for status_code, status_handler in list(app.exception_handlers.items()):
        if isinstance(status_code, int):
            app.add_exception_handler(
                status_code,
                _wrap_status_handler_for_refine_errors(app, status_handler),
            )

    existing_refine_handler = app.exception_handlers.get(RefineHTTPException)
    if existing_refine_handler is None:
        _warn_about_bypassed_generic_http_handlers(app)
        app.add_exception_handler(RefineHTTPException, refine_http_exception_handler)
    elif existing_refine_handler is not refine_http_exception_handler:
        logger.warning(
            "configure_refine(app) preserving existing RefineHTTPException handler %s; "
            "package-generated RefineHTTPException values will use it.",
            _handler_name(existing_refine_handler),
        )

    if not _has_custom_starlette_http_exception_handler(app):
        app.add_exception_handler(
            StarletteHTTPException, refine_http_exception_handler
        )

    if not _has_custom_validation_exception_handler(app):
        app.add_exception_handler(
            RequestValidationError, refine_validation_exception_handler
        )

    _rebuild_middleware_stack_if_needed(app)

    return app
