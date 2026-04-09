"""Contract tests for CRUD router success responses."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine

from fastapi_refine import (
    FilterConfig,
    FilterField,
    RefineCRUDRouter,
    RefineHooks,
    SortConfig,
)
from fastapi_refine.hooks import OwnerBasedHooks


class DeleteItem(SQLModel, table=True):
    __tablename__ = "delete_items"

    id: int | None = Field(default=None, primary_key=True)
    title: str


class DeleteItemCreate(SQLModel):
    title: str


class DeleteItemUpdate(SQLModel):
    title: str | None = None


class DeleteItemPublic(SQLModel):
    id: int
    title: str


class OwnedItem(SQLModel, table=True):
    __tablename__ = "owned_items"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    owner_id: int


class OwnedItemCreate(SQLModel):
    title: str
    owner_id: int


class OwnedItemUpdate(SQLModel):
    title: str | None = None


class OwnedItemPublic(SQLModel):
    id: int
    title: str
    owner_id: int


FILTER_CONFIG = FilterConfig(
    fields={
        "id": FilterField(DeleteItem.id, int),
        "title": FilterField(DeleteItem.title, str),
    }
)
SORT_CONFIG = SortConfig(fields={"id": DeleteItem.id, "title": DeleteItem.title})
OWNED_FILTER_CONFIG = FilterConfig(
    fields={
        "id": FilterField(OwnedItem.id, int),
        "title": FilterField(OwnedItem.title, str),
        "owner_id": FilterField(OwnedItem.owner_id, int),
    }
)
OWNED_SORT_CONFIG = SortConfig(
    fields={
        "id": OwnedItem.id,
        "title": OwnedItem.title,
        "owner_id": OwnedItem.owner_id,
    }
)


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def get_authenticated_principal() -> SimpleNamespace:
    return SimpleNamespace(id=7, is_superuser=False)


def get_rejected_principal() -> SimpleNamespace:
    raise HTTPException(status_code=401, detail="Unauthorized")


def make_router() -> RefineCRUDRouter[
    DeleteItem, DeleteItemCreate, DeleteItemUpdate, DeleteItemPublic, Any
]:
    return RefineCRUDRouter(
        model=DeleteItem,
        prefix="/items",
        create_schema=DeleteItemCreate,
        update_schema=DeleteItemUpdate,
        public_schema=DeleteItemPublic,
        session_dep=lambda: None,
        filter_config=FILTER_CONFIG,
        sort_config=SORT_CONFIG,
    )


def make_owned_router(
    current_principal_dep: Any,
) -> RefineCRUDRouter[
    OwnedItem, OwnedItemCreate, OwnedItemUpdate, OwnedItemPublic, SimpleNamespace
]:
    return RefineCRUDRouter(
        model=OwnedItem,
        prefix="/owned-items",
        create_schema=OwnedItemCreate,
        update_schema=OwnedItemUpdate,
        public_schema=OwnedItemPublic,
        session_dep=lambda: None,
        filter_config=OWNED_FILTER_CONFIG,
        sort_config=OWNED_SORT_CONFIG,
        hooks=OwnerBasedHooks(owner_field="owner_id"),
        current_principal_dep=current_principal_dep,
    )


def test_delete_returns_deleted_record_snapshot():
    session = make_session()
    item = DeleteItem(title="alpha")
    session.add(item)
    session.commit()
    session.refresh(item)

    router = make_router()

    deleted = router.delete(id=item.id, session=session)

    assert deleted == DeleteItemPublic(id=item.id, title="alpha")
    assert session.get(DeleteItem, item.id) is None


def test_delete_route_declares_public_schema_response_model():
    app = FastAPI()
    app.include_router(make_router().router)

    schema = app.openapi()
    response_schema = schema["paths"]["/items/{id}"]["delete"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]

    assert response_schema["$ref"].endswith("/DeleteItemPublic")


def test_create_and_update_routes_treat_item_in_as_request_body():
    app = FastAPI()
    app.include_router(make_router().router)

    post_route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/items/"
        and "POST" in route.methods
    )
    patch_route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/items/{id}"
        and "PATCH" in route.methods
    )

    assert [param.name for param in post_route.dependant.body_params] == ["item_in"]
    assert "item_in" not in {param.name for param in post_route.dependant.query_params}
    assert [param.name for param in patch_route.dependant.body_params] == ["item_in"]
    assert "item_in" not in {param.name for param in patch_route.dependant.query_params}


def test_get_one_route_requires_current_principal_dependency():
    app = FastAPI()

    router = RefineCRUDRouter(
        model=DeleteItem,
        prefix="/items",
        create_schema=DeleteItemCreate,
        update_schema=DeleteItemUpdate,
        public_schema=DeleteItemPublic,
        session_dep=lambda: None,
        filter_config=FILTER_CONFIG,
        sort_config=SORT_CONFIG,
        current_principal_dep=get_rejected_principal,
    )
    app.include_router(router.router)

    route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/items/{id}"
        and "GET" in route.methods
    )
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}

    assert get_rejected_principal in dependency_calls


def test_delete_direct_call_resolves_current_principal_dependency():
    session = make_session()
    item = OwnedItem(title="owned", owner_id=7)
    session.add(item)
    session.commit()
    session.refresh(item)

    router = make_owned_router(get_authenticated_principal)

    deleted = router.delete(id=item.id, session=session)

    assert deleted == OwnedItemPublic(id=item.id, title="owned", owner_id=7)
    assert session.get(OwnedItem, item.id) is None


def test_delete_direct_call_keeps_yield_principal_dependency_alive_for_hooks():
    events: list[str] = []

    def principal_dep():
        events.append("enter")
        try:
            yield SimpleNamespace(id=7, is_superuser=False)
        finally:
            events.append("exit")

    def before_delete(context: Any, item: Any) -> None:
        assert context.current_principal is not None
        assert events == ["enter"]
        events.append("before")

    def after_delete(context: Any, item: Any) -> Any:
        assert context.current_principal is not None
        assert events == ["enter", "before"]
        events.append("after")
        return item

    session = make_session()
    item = OwnedItem(title="owned", owner_id=7)
    session.add(item)
    session.commit()
    session.refresh(item)

    router = RefineCRUDRouter(
        model=OwnedItem,
        prefix="/owned-items",
        create_schema=OwnedItemCreate,
        update_schema=OwnedItemUpdate,
        public_schema=OwnedItemPublic,
        session_dep=lambda: None,
        filter_config=OWNED_FILTER_CONFIG,
        sort_config=OWNED_SORT_CONFIG,
        hooks=RefineHooks(
            before_delete=before_delete,
            after_delete=after_delete,
        ),
        current_principal_dep=principal_dep,
    )

    deleted = router.delete(id=item.id, session=session)

    assert deleted == OwnedItemPublic(id=item.id, title="owned", owner_id=7)
    assert events == ["enter", "before", "after", "exit"]


def test_direct_call_does_not_re_resolve_explicit_none_principal():
    calls = 0

    def principal_dep() -> None:
        nonlocal calls
        calls += 1
        return None

    session = make_session()
    item = DeleteItem(title="anonymous")
    session.add(item)
    session.commit()
    session.refresh(item)

    router = RefineCRUDRouter(
        model=DeleteItem,
        prefix="/items",
        create_schema=DeleteItemCreate,
        update_schema=DeleteItemUpdate,
        public_schema=DeleteItemPublic,
        session_dep=lambda: None,
        filter_config=FILTER_CONFIG,
        sort_config=SORT_CONFIG,
        current_principal_dep=principal_dep,
    )

    deleted = router.delete(id=item.id, session=session, current_principal=None)

    assert deleted == DeleteItemPublic(id=item.id, title="anonymous")
    assert calls == 0
