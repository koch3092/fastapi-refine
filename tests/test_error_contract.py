"""Contract tests for Refine error formatting."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlmodel import Field, Session, SQLModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from fastapi_refine import (
    FilterConfig,
    FilterField,
    HookContext,
    RefineCRUDRouter,
    RefineHTTPException,
    SortConfig,
    configure_refine,
    format_refine_http_exception,
    format_refine_validation_error,
    refine_http_exception_handler,
    refine_validation_exception_handler,
)
from fastapi_refine.dependencies.query import RefineQuery
from fastapi_refine.hooks import OwnerBasedHooks


class Item(SQLModel, table=True):
    __tablename__ = "error_contract_items"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    owner_id: int = 1


class ItemCreate(SQLModel):
    title: str
    owner_id: int


class ItemUpdate(SQLModel):
    title: str | None = None


class ItemPublic(SQLModel):
    id: int
    title: str
    owner_id: int


FILTER_CONFIG = FilterConfig(
    fields={
        "id": FilterField(Item.id, int),
        "title": FilterField(Item.title, str),
        "owner_id": FilterField(Item.owner_id, int),
    }
)
SORT_CONFIG = SortConfig(fields={"id": Item.id, "title": Item.title})


class FakeSession:
    def __init__(self, item: Item | None = None):
        self.item = item

    def get(self, model: Any, id: Any) -> Item | None:
        return self.item


def make_request(path: str = "/items", query_string: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query_string.encode(),
        "headers": [],
    }
    return Request(scope)


def render_json_response(response: Any) -> dict[str, Any]:
    return json.loads(response.body.decode())


def run_handler(handler: Any, request: Request, exc: Exception) -> dict[str, Any]:
    response = asyncio.run(handler(request, exc))
    return render_json_response(response)


def run_app(
    app: FastAPI,
    *,
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers or [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    asyncio.run(app(scope, receive, send))

    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    response_headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in start.get("headers", [])
    }
    return start["status"], response_headers, body


def make_router() -> RefineCRUDRouter[Item, ItemCreate, ItemUpdate, ItemPublic, Any]:
    return RefineCRUDRouter(
        model=Item,
        prefix="/items",
        create_schema=ItemCreate,
        update_schema=ItemUpdate,
        public_schema=ItemPublic,
        session_dep=lambda: None,
        filter_config=FILTER_CONFIG,
        sort_config=SORT_CONFIG,
    )


def test_configure_refine_returns_app():
    app = FastAPI()
    assert configure_refine(app) is app


def test_configure_refine_rebuilds_existing_middleware_stack():
    app = FastAPI()

    @app.get("/items/123")
    def read_item() -> dict[str, str]:
        raise HTTPException(status_code=404, detail="Item not found")

    before_status, _, before_body = run_app(app, method="GET", path="/items/123")
    assert before_status == 404
    assert json.loads(before_body.decode()) == {"detail": "Item not found"}
    assert app.middleware_stack is not None

    configure_refine(app)

    after_status, _, after_body = run_app(app, method="GET", path="/items/123")
    assert after_status == 404
    assert json.loads(after_body.decode()) == {
        "message": "Item not found",
        "statusCode": 404,
        "code": "not_found",
    }


def test_package_errors_keep_string_detail_without_configure_refine():
    with pytest.raises(HTTPException) as exc_info:
        make_router().get_one(id=123, session=FakeSession())

    assert exc_info.value.detail == "Item not found"


def test_crud_not_found_is_formatted_as_refine_error():
    app = configure_refine(FastAPI())
    handler = app.exception_handlers[RefineHTTPException]

    with pytest.raises(HTTPException) as exc_info:
        make_router().get_one(id=123, session=FakeSession())

    body = run_handler(handler, make_request("/items/123"), exc_info.value)

    assert body == {
        "message": "Item not found",
        "statusCode": 404,
        "code": "not_found",
    }


def test_owner_hooks_errors_are_formatted_as_refine_errors():
    app = configure_refine(FastAPI())
    handler = app.exception_handlers[RefineHTTPException]
    hooks = OwnerBasedHooks(owner_field="owner_id")
    item = Item(id=1, title="alpha", owner_id=7)

    with pytest.raises(HTTPException) as unauth_exc:
        hooks._before_mutation(HookContext(model=Item, session=Session()), item)
    unauthorized = run_handler(handler, make_request("/items/1"), unauth_exc.value)
    assert unauthorized == {
        "message": "Authentication required",
        "statusCode": 401,
        "code": "unauthorized",
    }

    with pytest.raises(HTTPException) as forbidden_exc:
        hooks._before_mutation(
            HookContext(
                model=Item,
                session=Session(),
                current_principal=type(
                    "Principal", (), {"id": 9, "is_superuser": False}
                )(),
            ),
            item,
        )
    forbidden = run_handler(handler, make_request("/items/1"), forbidden_exc.value)
    assert forbidden == {
        "message": "Not enough permissions",
        "statusCode": 403,
        "code": "forbidden",
    }


def test_query_validation_is_formatted_with_root_errors():
    app = configure_refine(FastAPI())
    handler = app.exception_handlers[RefineHTTPException]

    with pytest.raises(HTTPException) as exc_info:
        RefineQuery(
            model=Item,
            filter_config=FILTER_CONFIG,
            sort_config=SORT_CONFIG,
            _start=2,
            _end=1,
            request=make_request("/items", "_start=2&_end=1"),
        )

    body = run_handler(
        handler, make_request("/items", "_start=2&_end=1"), exc_info.value
    )

    assert body["message"] == "Validation failed"
    assert body["statusCode"] == 422
    assert body["code"] == "validation_error"
    assert body["errors"] == {
        "_root": ["`_end` must be greater than or equal to `_start`."]
    }


def test_request_validation_errors_are_mapped_to_dot_paths():
    app = configure_refine(FastAPI())
    handler = app.exception_handlers[RequestValidationError]
    exc = RequestValidationError(
        [
            {"loc": ("body", "title"), "msg": "Field required", "type": "missing"},
            {
                "loc": ("body", "items", 0, "count"),
                "msg": "Input should be a valid integer",
                "type": "int_parsing",
            },
            {
                "loc": ("query", "_start"),
                "msg": "Input should be greater than or equal to 0",
                "type": "greater_than_equal",
            },
        ]
    )

    body = run_handler(handler, make_request("/items", "_start=-1"), exc)

    assert body == {
        "message": "Validation failed",
        "statusCode": 422,
        "code": "validation_error",
        "errors": {
            "title": ["Field required"],
            "items.0.count": ["Input should be a valid integer"],
            "_start": ["Input should be greater than or equal to 0"],
        },
    }


def test_format_refine_validation_error_returns_standard_envelope():
    exc = RequestValidationError(
        [{"loc": ("body", "title"), "msg": "Field required", "type": "missing"}]
    )

    body = format_refine_validation_error(exc)

    assert body == {
        "message": "Validation failed",
        "statusCode": 422,
        "code": "validation_error",
        "errors": {"title": ["Field required"]},
    }


def test_http_exception_string_detail_is_wrapped():
    body = run_handler(
        refine_http_exception_handler,
        make_request("/login"),
        HTTPException(status_code=401, detail="Unauthorized"),
    )

    assert body == {
        "message": "Unauthorized",
        "statusCode": 401,
        "code": "unauthorized",
    }


def test_http_exception_structured_detail_is_preserved_and_completed():
    body = run_handler(
        refine_http_exception_handler,
        make_request("/items/1"),
        HTTPException(
            status_code=403,
            detail={
                "message": "Custom forbidden",
                "code": "custom_forbidden",
                "errors": {"owner_id": ["Mismatch"]},
            },
        ),
    )

    assert body == {
        "message": "Custom forbidden",
        "statusCode": 403,
        "code": "custom_forbidden",
        "detail": {
            "message": "Custom forbidden",
            "code": "custom_forbidden",
            "errors": {"owner_id": ["Mismatch"]},
        },
    }


def test_http_exception_partial_structured_detail_uses_default_message():
    body = run_handler(
        refine_http_exception_handler,
        make_request("/items"),
        HTTPException(
            status_code=422,
            detail={"errors": {"name": ["Required"]}},
        ),
    )

    assert body == {
        "message": "Validation failed",
        "statusCode": 422,
        "code": "validation_error",
        "detail": {"errors": {"name": ["Required"]}},
    }


def test_http_exception_arbitrary_structured_detail_is_preserved():
    body = run_handler(
        refine_http_exception_handler,
        make_request("/items"),
        HTTPException(
            status_code=409,
            detail={"foo": "bar", "statusCode": 999},
        ),
    )

    assert body == {
        "message": "Conflict",
        "statusCode": 409,
        "code": "http_409",
        "detail": {"foo": "bar", "statusCode": 999},
    }


def test_http_exception_list_detail_is_preserved_without_stringifying():
    body = run_handler(
        refine_http_exception_handler,
        make_request("/items"),
        HTTPException(
            status_code=400,
            detail=[{"field": "name", "msg": "Required"}],
        ),
    )

    assert body == {
        "message": "Bad Request",
        "statusCode": 400,
        "code": "http_400",
        "detail": [{"field": "name", "msg": "Required"}],
    }


def test_http_exception_structured_detail_is_json_encoded():
    event_id = uuid4()
    body = run_handler(
        refine_http_exception_handler,
        make_request("/items"),
        HTTPException(
            status_code=400,
            detail={
                "when": datetime(2024, 1, 1, 12, 0, 0),
                "id": event_id,
            },
        ),
    )

    assert body == {
        "message": "Bad Request",
        "statusCode": 400,
        "code": "http_400",
        "detail": {
            "when": "2024-01-01T12:00:00",
            "id": str(event_id),
        },
    }


def test_format_refine_http_exception_preserves_structured_detail():
    body = format_refine_http_exception(
        HTTPException(
            status_code=422,
            detail={"errors": {"name": ["Required"]}},
        )
    )

    assert body == {
        "message": "Validation failed",
        "statusCode": 422,
        "code": "validation_error",
        "detail": {"errors": {"name": ["Required"]}},
    }


def test_format_refine_http_exception_preserves_list_detail():
    body = format_refine_http_exception(
        HTTPException(
            status_code=400,
            detail=[{"field": "name", "msg": "Required"}],
        )
    )

    assert body == {
        "message": "Bad Request",
        "statusCode": 400,
        "code": "http_400",
        "detail": [{"field": "name", "msg": "Required"}],
    }


def test_format_refine_http_exception_preserves_refine_detail_message():
    body = format_refine_http_exception(
        RefineHTTPException(
            status_code=409,
            message="Conflict",
            detail_message="Item with slug `alpha` already exists",
            code="conflict",
        )
    )

    assert body == {
        "message": "Conflict",
        "statusCode": 409,
        "code": "conflict",
        "detail": "Item with slug `alpha` already exists",
    }


def test_refine_validation_exception_handler_matches_public_formatter():
    exc = RequestValidationError(
        [{"loc": ("body", "title"), "msg": "Field required", "type": "missing"}]
    )

    body = run_handler(
        refine_validation_exception_handler,
        make_request("/items"),
        exc,
    )

    assert body == format_refine_validation_error(exc)


def test_configure_refine_preserves_http_exception_headers():
    response = asyncio.run(
        refine_http_exception_handler(
            make_request("/login"),
            HTTPException(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            ),
        )
    )

    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_configure_refine_does_not_override_custom_starlette_http_handler():
    app = FastAPI()

    async def custom_handler(_request: Request, exc: Exception) -> JSONResponse:
        http_exc = exc
        status_code = getattr(http_exc, "status_code", 500)
        return JSONResponse({"detail": "custom-http"}, status_code=status_code)

    app.add_exception_handler(StarletteHTTPException, custom_handler)
    configure_refine(app)

    assert app.exception_handlers[StarletteHTTPException] is custom_handler

    body = run_handler(
        app.exception_handlers[RefineHTTPException],
        make_request("/items/123"),
        RefineHTTPException(status_code=404, message="Item not found"),
    )

    assert body == {
        "message": "Item not found",
        "statusCode": 404,
        "code": "not_found",
    }


def test_configure_refine_does_not_override_custom_fastapi_http_handler():
    app = FastAPI()

    async def custom_handler(_request: Request, exc: Exception) -> JSONResponse:
        http_exc = exc
        status_code = getattr(http_exc, "status_code", 500)
        return JSONResponse({"detail": "custom-fastapi-http"}, status_code=status_code)

    app.add_exception_handler(HTTPException, custom_handler)
    configure_refine(app)

    assert app.exception_handlers[HTTPException] is custom_handler
    assert (
        app.exception_handlers[StarletteHTTPException] is refine_http_exception_handler
    )


def test_configure_refine_does_not_override_custom_validation_handler():
    app = FastAPI()

    async def custom_validation_handler(
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        return JSONResponse({"detail": "custom-validation"}, status_code=422)

    app.add_exception_handler(RequestValidationError, custom_validation_handler)
    configure_refine(app)

    assert app.exception_handlers[RequestValidationError] is custom_validation_handler


def test_configure_refine_preserves_existing_refine_http_exception_handler(
    caplog: pytest.LogCaptureFixture,
):
    app = FastAPI()

    async def custom_refine_handler(_request: Request, exc: Exception) -> JSONResponse:
        http_exc = exc
        status_code = getattr(http_exc, "status_code", 500)
        return JSONResponse(
            {"detail": "custom-refine"},
            status_code=status_code,
            headers={"X-Refine-Handler": "custom"},
        )

    app.add_exception_handler(RefineHTTPException, custom_refine_handler)

    with caplog.at_level(logging.WARNING, logger="fastapi_refine"):
        configure_refine(app)

    assert app.exception_handlers[RefineHTTPException] is custom_refine_handler
    assert "preserving existing RefineHTTPException handler" in caplog.text


def test_configure_refine_warns_when_generic_http_handler_is_bypassed(
    caplog: pytest.LogCaptureFixture,
):
    app = FastAPI()

    async def custom_handler(_request: Request, exc: Exception) -> JSONResponse:
        http_exc = exc
        status_code = getattr(http_exc, "status_code", 500)
        return JSONResponse({"detail": "custom-http"}, status_code=status_code)

    app.add_exception_handler(StarletteHTTPException, custom_handler)

    with caplog.at_level(logging.WARNING, logger="fastapi_refine"):
        configure_refine(app)

    assert "detected custom generic HTTP exception handler" in caplog.text
    assert "Register RefineHTTPException explicitly" in caplog.text


def test_configure_refine_wraps_custom_status_handler_for_refine_http_exception():
    app = FastAPI()

    async def custom_404_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": "custom-404"}, status_code=404)

    app.add_exception_handler(404, custom_404_handler)
    configure_refine(app)

    wrapped_handler = app.exception_handlers[404]

    refine_body = run_handler(
        wrapped_handler,
        make_request("/items/123"),
        RefineHTTPException(status_code=404, message="Item not found"),
    )
    assert refine_body == {
        "message": "Item not found",
        "statusCode": 404,
        "code": "not_found",
    }

    regular_body = run_handler(
        wrapped_handler,
        make_request("/items/123"),
        HTTPException(status_code=404, detail="custom"),
    )
    assert regular_body == {"detail": "custom-404"}


def test_status_handler_wrapper_uses_registered_refine_http_exception_handler():
    app = FastAPI()

    async def custom_refine_handler(_request: Request, exc: Exception) -> JSONResponse:
        http_exc = exc
        status_code = getattr(http_exc, "status_code", 500)
        return JSONResponse(
            {"detail": "custom-refine"},
            status_code=status_code,
            headers={"X-Refine-Handler": "custom"},
        )

    async def custom_404_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": "custom-404"}, status_code=404)

    app.add_exception_handler(RefineHTTPException, custom_refine_handler)
    app.add_exception_handler(404, custom_404_handler)
    configure_refine(app)

    wrapped_handler = app.exception_handlers[404]
    response = asyncio.run(
        wrapped_handler(
            make_request("/items/123"),
            RefineHTTPException(status_code=404, message="Item not found"),
        )
    )

    assert render_json_response(response) == {"detail": "custom-refine"}
    assert response.headers["X-Refine-Handler"] == "custom"


def test_wrapped_sync_handlers_run_in_threadpool():
    app = FastAPI()
    threads: dict[str, int] = {}

    def sync_refine_handler(_request: Request, exc: Exception) -> JSONResponse:
        http_exc = exc
        threads["refine"] = threading.get_ident()
        return JSONResponse(
            {"detail": "sync-refine"},
            status_code=getattr(http_exc, "status_code", 500),
        )

    def sync_404_handler(_request: Request, exc: Exception) -> JSONResponse:
        http_exc = exc
        threads["status"] = threading.get_ident()
        return JSONResponse(
            {"detail": "sync-404"},
            status_code=getattr(http_exc, "status_code", 500),
        )

    app.add_exception_handler(RefineHTTPException, sync_refine_handler)
    app.add_exception_handler(404, sync_404_handler)
    configure_refine(app)
    wrapped_handler = app.exception_handlers[404]

    async def exercise_wrapped_handler() -> tuple[int, int]:
        event_loop_thread_id = threading.get_ident()
        await wrapped_handler(
            make_request("/items/123"),
            RefineHTTPException(status_code=404, message="Item not found"),
        )
        await wrapped_handler(
            make_request("/items/123"),
            HTTPException(status_code=404, detail="custom"),
        )
        return event_loop_thread_id, threads["refine"]

    event_loop_thread_id, refine_thread_id = asyncio.run(exercise_wrapped_handler())

    assert refine_thread_id != event_loop_thread_id
    assert threads["status"] != event_loop_thread_id


def test_configure_refine_wraps_custom_status_handler_for_refine_422_errors():
    app = FastAPI()

    async def custom_422_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": "custom-422"}, status_code=422)

    app.add_exception_handler(422, custom_422_handler)
    configure_refine(app)

    wrapped_handler = app.exception_handlers[422]

    refine_body = run_handler(
        wrapped_handler,
        make_request("/items"),
        RefineHTTPException(
            status_code=422,
            message="Validation failed",
            errors={"_root": ["Bad input"]},
        ),
    )
    assert refine_body == {
        "message": "Validation failed",
        "statusCode": 422,
        "code": "validation_error",
        "errors": {"_root": ["Bad input"]},
    }

    regular_body = run_handler(
        wrapped_handler,
        make_request("/items"),
        HTTPException(status_code=422, detail={"errors": {"name": ["Required"]}}),
    )
    assert regular_body == {"detail": "custom-422"}


def test_configure_refine_wraps_custom_status_handler_for_public_refine_http_exception():
    app = FastAPI()

    async def custom_409_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": "custom-409"}, status_code=409)

    app.add_exception_handler(409, custom_409_handler)
    configure_refine(app)

    wrapped_handler = app.exception_handlers[409]

    refine_body = run_handler(
        wrapped_handler,
        make_request("/items"),
        RefineHTTPException(
            status_code=409,
            message="Conflict",
            code="conflict",
        ),
    )
    assert refine_body == {
        "message": "Conflict",
        "statusCode": 409,
        "code": "conflict",
    }

    regular_body = run_handler(
        wrapped_handler,
        make_request("/items"),
        HTTPException(status_code=409, detail="custom"),
    )
    assert regular_body == {"detail": "custom-409"}


@pytest.mark.parametrize("status_code", [204, 205, 304])
def test_refine_http_exception_handler_uses_empty_body_for_no_content_statuses(
    status_code: int,
):
    app = FastAPI()
    configure_refine(app)

    @app.get(f"/status-{status_code}")
    def read_status() -> dict[str, str]:
        raise HTTPException(
            status_code=status_code,
            headers={"X-Status": str(status_code)},
        )

    response_status, response_headers, response_body = run_app(
        app,
        method="GET",
        path=f"/status-{status_code}",
    )

    assert response_status == status_code
    assert response_headers["x-status"] == str(status_code)
    assert response_body == b""


def test_custom_fastapi_http_handler_coexists_with_starlette_refine_handler():
    app = FastAPI()

    async def custom_fastapi_handler(_request: Request, exc: Exception) -> JSONResponse:
        http_exc = exc
        status_code = getattr(http_exc, "status_code", 500)
        return JSONResponse(
            {"detail": "custom-fastapi-http"},
            status_code=status_code,
        )

    app.add_exception_handler(HTTPException, custom_fastapi_handler)
    configure_refine(app)

    @app.get("/manual")
    def read_manual() -> dict[str, str]:
        raise HTTPException(status_code=418, detail="teapot")

    @app.get("/items")
    def read_items() -> dict[str, str]:
        return {"ok": "true"}

    manual_status, _, manual_body = run_app(app, method="GET", path="/manual")
    not_found_status, _, not_found_body = run_app(app, method="GET", path="/missing")
    method_status, method_headers, method_body = run_app(
        app,
        method="POST",
        path="/items",
    )

    assert manual_status == 418
    assert json.loads(manual_body.decode()) == {"detail": "custom-fastapi-http"}

    assert not_found_status == 404
    assert json.loads(not_found_body.decode()) == {
        "message": "Not Found",
        "statusCode": 404,
        "code": "not_found",
    }

    assert method_status == 405
    assert json.loads(method_body.decode()) == {
        "message": "Method Not Allowed",
        "statusCode": 405,
        "code": "http_405",
    }
    assert method_headers["allow"] == "GET"
