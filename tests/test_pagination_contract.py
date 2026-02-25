"""Contract tests for Refine simple-rest pagination behavior."""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select
from starlette.requests import Request

from fastapi_refine import (
    FilterConfig,
    FilterField,
    RefineQuery,
    SortConfig,
    refine_query,
)


class Item(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str


FILTER_CONFIG = FilterConfig(
    fields={"id": FilterField(Item.id, int), "title": FilterField(Item.title, str)}
)
SORT_CONFIG = SortConfig(fields={"id": Item.id, "title": Item.title})


def make_request(query_string: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/items",
        "query_string": query_string.encode(),
        "headers": [],
    }
    return Request(scope)


def seed_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add_all([Item(title="alpha"), Item(title="beta"), Item(title="gamma")])
    session.commit()
    return session


def test_skip_limit_is_rejected_with_422():
    request = make_request("skip=0&limit=10")

    with pytest.raises(HTTPException) as exc_info:
        RefineQuery(
            model=Item,
            filter_config=FILTER_CONFIG,
            sort_config=SORT_CONFIG,
            request=request,
        )

    assert exc_info.value.status_code == 422
    assert "Legacy pagination parameters are not supported" in str(exc_info.value.detail)


def test_invalid_range_is_rejected_with_422():
    request = make_request("_start=2&_end=1")

    with pytest.raises(HTTPException) as exc_info:
        RefineQuery(
            model=Item,
            filter_config=FILTER_CONFIG,
            sort_config=SORT_CONFIG,
            _start=2,
            _end=1,
            request=request,
        )

    assert exc_info.value.status_code == 422
    assert "`_end` must be greater than or equal to `_start`" in str(exc_info.value.detail)


def test_start_end_range_pagination_still_works():
    session = seed_session()

    query = RefineQuery(
        model=Item,
        filter_config=FILTER_CONFIG,
        sort_config=SORT_CONFIG,
        _start=0,
        _end=2,
        _sort="id",
        _order="asc",
        request=make_request("_start=0&_end=2&_sort=id&_order=asc"),
    )

    statement = (
        select(Item)
        .where(*query.conditions)
        .order_by(*query.order_by)
        .offset(query.offset)
        .limit(query.limit)
    )

    items = list(session.exec(statement).all())

    assert len(items) == 2
    assert query.get_count(session, query.conditions) == 3


def test_openapi_does_not_expose_skip_limit_query_params():
    app = FastAPI()

    @app.get("/items")
    def read_items(
        query: Annotated[
            RefineQuery,
            Depends(refine_query(Item, FILTER_CONFIG, SORT_CONFIG)),
        ],
    ) -> dict[str, int]:
        return {"offset": query.offset}

    schema = app.openapi()
    params = {param["name"] for param in schema["paths"]["/items"]["get"]["parameters"]}

    assert "_start" in params
    assert "_end" in params
    assert "skip" not in params
    assert "limit" not in params
