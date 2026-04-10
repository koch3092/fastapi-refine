"""CRUD Router factory for generating standard Refine-compatible endpoints."""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from typing import Any, Generic, TypeVar, cast

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlmodel import Session, SQLModel, select

from fastapi_refine.core import (
    DependencyCallable,
    FilterConfig,
    PaginationConfig,
    SortConfig,
)
from fastapi_refine.dependencies import RefineQuery, RefineResponse
from fastapi_refine.errors import RefineHTTPException
from fastapi_refine.hooks import HookContext, RefineHooks

__all__ = ["RefineCRUDRouter"]

ModelT = TypeVar("ModelT", bound=SQLModel)
CreateSchemaT = TypeVar("CreateSchemaT", bound=SQLModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=SQLModel)
PublicSchemaT = TypeVar("PublicSchemaT", bound=SQLModel)
PrincipalT = TypeVar("PrincipalT")
_UNSET = object()


class RefineCRUDRouter(
    Generic[ModelT, CreateSchemaT, UpdateSchemaT, PublicSchemaT, PrincipalT]
):
    """Factory for generating Refine-compatible CRUD routers.

    Automatically creates standard CRUD endpoints that follow Refine simple-rest conventions:
    - GET /{resource}/ - List with pagination, sorting, filtering
    - GET /{resource}/{id} - Get single item
    - POST /{resource}/ - Create new item
    - PATCH /{resource}/{id} - Update item
    - DELETE /{resource}/{id} - Delete item

    Example:
        ```python
        router = RefineCRUDRouter(
            model=Item,
            prefix="/items",
            create_schema=ItemCreate,
            update_schema=ItemUpdate,
            public_schema=ItemPublic,
            session_dep=SessionDep,
            filter_config=filter_config,
            sort_config=sort_config,
            current_principal_dep=CurrentPrincipal,
            hooks=OwnerBasedHooks(owner_field="owner_id"),
        ).router
        ```
    """

    def __init__(
        self,
        model: type[ModelT],
        prefix: str,
        create_schema: type[CreateSchemaT],
        update_schema: type[UpdateSchemaT],
        public_schema: type[PublicSchemaT],
        session_dep: DependencyCallable[Session],
        filter_config: FilterConfig,
        sort_config: SortConfig,
        pagination_config: PaginationConfig | None = None,
        hooks: RefineHooks[PrincipalT] | None = None,
        current_principal_dep: DependencyCallable[PrincipalT] | None = None,
        tags: list[str] | None = None,
    ):
        """Initialize the CRUD router.

        Args:
            model: SQLModel database class
            prefix: URL prefix for routes (e.g., "/items")
            create_schema: Pydantic schema for creating items
            update_schema: Pydantic schema for updating items
            public_schema: Pydantic schema for API responses
            session_dep: FastAPI dependency for database session
            filter_config: Filter configuration
            sort_config: Sort configuration
            pagination_config: Optional pagination configuration
            hooks: Optional lifecycle hooks
            current_principal_dep: Optional FastAPI dependency for current principal
            tags: OpenAPI tags for documentation
        """
        if not callable(session_dep):
            raise TypeError("session_dep must be a FastAPI dependency callable")
        if current_principal_dep is not None and not callable(current_principal_dep):
            raise TypeError(
                "current_principal_dep must be a FastAPI dependency callable"
            )

        self.model = model
        self.create_schema = create_schema
        self.update_schema = update_schema
        self.public_schema = public_schema
        self.session_dep = session_dep
        self.filter_config = filter_config
        self.sort_config = sort_config
        self.pagination_config = pagination_config or PaginationConfig()
        self.hooks = hooks or RefineHooks()
        self.current_principal_dep = current_principal_dep

        self.router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")])  # type: ignore[arg-type]
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup all CRUD routes."""
        get_list_endpoint: Any
        create_endpoint: Any
        get_one_endpoint: Any
        update_endpoint: Any
        delete_endpoint: Any

        if self.current_principal_dep:

            def get_list_endpoint_with_principal(
                request: Request,
                response: Response,
                session: Session = Depends(self.session_dep),
                current_principal: PrincipalT = Depends(self.current_principal_dep),
                _start: int | None = Query(None, alias="_start", ge=0),
                _end: int | None = Query(None, alias="_end", ge=0),
                _sort: str | None = Query(None, alias="_sort"),
                _order: str | None = Query(None, alias="_order"),
                id: list[Any] | None = Query(None),
            ) -> list[Any]:
                return self.get_list(
                    request=request,
                    response=response,
                    session=session,
                    current_principal=current_principal,
                    _start=_start,
                    _end=_end,
                    _sort=_sort,
                    _order=_order,
                    id=id,
                )

            def create_endpoint_with_principal(
                item_in: CreateSchemaT,
                session: Session = Depends(self.session_dep),
                current_principal: PrincipalT = Depends(self.current_principal_dep),
            ) -> Any:
                return self.create(
                    item_in=item_in,
                    session=session,
                    current_principal=current_principal,
                )

            create_endpoint_with_principal = self._bind_body_model(
                create_endpoint_with_principal, "item_in", self.create_schema
            )

            def get_one_endpoint_with_principal(
                id: Any,
                session: Session = Depends(self.session_dep),
                current_principal: PrincipalT = Depends(self.current_principal_dep),
            ) -> Any:
                return self.get_one(
                    id=id,
                    session=session,
                    current_principal=current_principal,
                )

            def update_endpoint_with_principal(
                id: Any,
                item_in: UpdateSchemaT,
                session: Session = Depends(self.session_dep),
                current_principal: PrincipalT = Depends(self.current_principal_dep),
            ) -> Any:
                return self.update(
                    id=id,
                    item_in=item_in,
                    session=session,
                    current_principal=current_principal,
                )

            update_endpoint_with_principal = self._bind_body_model(
                update_endpoint_with_principal, "item_in", self.update_schema
            )

            def delete_endpoint_with_principal(
                id: Any,
                session: Session = Depends(self.session_dep),
                current_principal: PrincipalT = Depends(self.current_principal_dep),
            ) -> Any:
                return self.delete(
                    id=id,
                    session=session,
                    current_principal=current_principal,
                )

            get_list_endpoint = get_list_endpoint_with_principal
            create_endpoint = create_endpoint_with_principal
            get_one_endpoint = get_one_endpoint_with_principal
            update_endpoint = update_endpoint_with_principal
            delete_endpoint = delete_endpoint_with_principal
        else:

            def get_list_endpoint_without_principal(
                request: Request,
                response: Response,
                session: Session = Depends(self.session_dep),
                _start: int | None = Query(None, alias="_start", ge=0),
                _end: int | None = Query(None, alias="_end", ge=0),
                _sort: str | None = Query(None, alias="_sort"),
                _order: str | None = Query(None, alias="_order"),
                id: list[Any] | None = Query(None),
            ) -> list[Any]:
                return self.get_list(
                    request=request,
                    response=response,
                    session=session,
                    _start=_start,
                    _end=_end,
                    _sort=_sort,
                    _order=_order,
                    id=id,
                )

            def create_endpoint_without_principal(
                item_in: CreateSchemaT,
                session: Session = Depends(self.session_dep),
            ) -> Any:
                return self.create(item_in=item_in, session=session)

            create_endpoint_without_principal = self._bind_body_model(
                create_endpoint_without_principal, "item_in", self.create_schema
            )

            def get_one_endpoint_without_principal(
                id: Any,
                session: Session = Depends(self.session_dep),
            ) -> Any:
                return self.get_one(id=id, session=session)

            def update_endpoint_without_principal(
                id: Any,
                item_in: UpdateSchemaT,
                session: Session = Depends(self.session_dep),
            ) -> Any:
                return self.update(id=id, item_in=item_in, session=session)

            update_endpoint_without_principal = self._bind_body_model(
                update_endpoint_without_principal, "item_in", self.update_schema
            )

            def delete_endpoint_without_principal(
                id: Any,
                session: Session = Depends(self.session_dep),
            ) -> Any:
                return self.delete(id=id, session=session)

            get_list_endpoint = get_list_endpoint_without_principal
            create_endpoint = create_endpoint_without_principal
            get_one_endpoint = get_one_endpoint_without_principal
            update_endpoint = update_endpoint_without_principal
            delete_endpoint = delete_endpoint_without_principal

        self.router.add_api_route(
            "/",
            get_list_endpoint,
            methods=["GET"],
            response_model=list[self.public_schema],  # type: ignore[name-defined]
        )
        self.router.add_api_route(
            "/{id}",
            get_one_endpoint,
            methods=["GET"],
            response_model=self.public_schema,
        )
        self.router.add_api_route(
            "/",
            create_endpoint,
            methods=["POST"],
            response_model=self.public_schema,
        )
        self.router.add_api_route(
            "/{id}",
            update_endpoint,
            methods=["PATCH"],
            response_model=self.public_schema,
        )
        self.router.add_api_route(
            "/{id}",
            delete_endpoint,
            methods=["DELETE"],
            response_model=self.public_schema,
        )

    def get_list(
        self,
        request: Request,
        response: Response,
        session: Session,
        current_principal: PrincipalT | None | object = _UNSET,
        _start: int | None = Query(None, alias="_start", ge=0),
        _end: int | None = Query(None, alias="_end", ge=0),
        _sort: str | None = Query(None, alias="_sort"),
        _order: str | None = Query(None, alias="_order"),
        id: list[Any] | None = Query(None),
    ) -> list[Any]:
        """Get list of items (Refine getList)."""
        with self._direct_principal_scope(current_principal) as resolved_principal:
            # Parse query
            query = RefineQuery(
                model=self.model,
                filter_config=self.filter_config,
                sort_config=self.sort_config,
                pagination_config=self.pagination_config,
                _start=_start,
                _end=_end,
                _sort=_sort,
                _order=_order,
                request=request,
            )

            conditions = query.conditions
            if id:
                conditions.append(self.model.id.in_(id))  # type: ignore[attr-defined]

            # Execute before_query hook
            if self.hooks.before_query:
                context = HookContext(
                    model=self.model,
                    session=session,
                    current_principal=resolved_principal,
                    request=request,
                )
                conditions = self._run_hook(
                    self.hooks.before_query, context, conditions
                )

            # Get count
            count = query.get_count(session, conditions)
            refine_response = RefineResponse(response)
            refine_response.set_total_count(count)

            # Execute query
            statement = select(self.model)
            if conditions:
                statement = statement.where(*conditions)
            if query.order_by:
                statement = statement.order_by(*query.order_by)

            items = list(
                session.exec(statement.offset(query.offset).limit(query.limit)).all()
            )

            # Execute after_query hook
            if self.hooks.after_query:
                context = HookContext(
                    model=self.model,
                    session=session,
                    current_principal=resolved_principal,
                    request=request,
                )
                items = self._run_hook(self.hooks.after_query, context, items)

            return items

    def get_one(
        self,
        id: Any,
        session: Session,
        current_principal: PrincipalT | None | object = _UNSET,
    ) -> Any:
        """Get single item by ID (Refine getOne)."""
        with self._direct_principal_scope(current_principal):
            item = session.get(self.model, id)
            if not item:
                raise RefineHTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    message=f"{self.model.__name__} not found",
                )
            return item

    def create(
        self,
        item_in: CreateSchemaT,
        session: Session,
        current_principal: PrincipalT | None | object = _UNSET,
    ) -> Any:
        """Create new item (Refine create)."""
        with self._direct_principal_scope(current_principal) as resolved_principal:
            extra_fields: dict[str, Any] = {}
            # Execute before_create hook
            if self.hooks.before_create:
                context = HookContext(
                    model=self.model,
                    session=session,
                    current_principal=resolved_principal,
                )
                hook_result = self._run_hook(self.hooks.before_create, context, item_in)
                if isinstance(hook_result, dict):
                    extra_fields = hook_result

            # Create item
            item = self.model.model_validate(item_in, update=extra_fields)
            session.add(item)
            session.commit()
            session.refresh(item)

            # Execute after_create hook
            if self.hooks.after_create:
                context = HookContext(
                    model=self.model,
                    session=session,
                    current_principal=resolved_principal,
                )
                item = self._run_hook(self.hooks.after_create, context, item_in, item)

            return item

    def update(
        self,
        id: Any,
        item_in: UpdateSchemaT,
        session: Session,
        current_principal: PrincipalT | None | object = _UNSET,
    ) -> Any:
        """Update item (Refine update)."""
        with self._direct_principal_scope(current_principal) as resolved_principal:
            item = session.get(self.model, id)
            if not item:
                raise RefineHTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    message=f"{self.model.__name__} not found",
                )

            # Execute before_update hook
            extra_fields: dict[str, Any] = {}
            if self.hooks.before_update:
                context = HookContext(
                    model=self.model,
                    session=session,
                    current_principal=resolved_principal,
                )
                hook_result = self._run_hook(
                    self.hooks.before_update, context, item, item_in
                )
                if isinstance(hook_result, dict):
                    extra_fields = hook_result

            # Update item
            update_data = item_in.model_dump(exclude_unset=True)
            update_data.update(extra_fields)
            item.sqlmodel_update(update_data)
            session.add(item)
            session.commit()
            session.refresh(item)

            # Execute after_update hook
            if self.hooks.after_update:
                context = HookContext(
                    model=self.model,
                    session=session,
                    current_principal=resolved_principal,
                )
                item = self._run_hook(self.hooks.after_update, context, item, item)

            return item

    def delete(
        self,
        id: Any,
        session: Session,
        current_principal: PrincipalT | None | object = _UNSET,
    ) -> Any:
        """Delete item (Refine delete)."""
        with self._direct_principal_scope(current_principal) as resolved_principal:
            item = session.get(self.model, id)
            if not item:
                raise RefineHTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    message=f"{self.model.__name__} not found",
                )

            # Execute before_delete hook
            if self.hooks.before_delete:
                context = HookContext(
                    model=self.model,
                    session=session,
                    current_principal=resolved_principal,
                )
                self._run_hook(self.hooks.before_delete, context, item)

            deleted_item = self.public_schema.model_validate(item)

            # Delete item
            session.delete(item)
            session.commit()

            # Execute after_delete hook
            if self.hooks.after_delete:
                context = HookContext(
                    model=self.model,
                    session=session,
                    current_principal=resolved_principal,
                )
                self._run_hook(self.hooks.after_delete, context, item)

            return deleted_item

    def _run_hook(self, hook: Any, *args: Any) -> Any:
        """Run a hook, handling both sync and async hooks."""
        result = hook(*args)

        if inspect.isawaitable(result):
            # For now, we'll just return the awaitable as-is
            # In a full async implementation, we'd await it here
            return result
        return result

    @contextmanager
    def _direct_principal_scope(
        self, current_principal: PrincipalT | None | object
    ) -> Any:
        """Resolve and keep the principal alive for direct method calls."""
        if current_principal is not _UNSET or self.current_principal_dep is None:
            yield cast(PrincipalT | None, current_principal)
            return

        result = self.current_principal_dep()

        if inspect.isasyncgen(result) or inspect.isawaitable(result):
            raise TypeError(
                "Direct CRUD method calls require a synchronous "
                "current_principal_dep or an explicit current_principal"
            )

        if inspect.isgenerator(result):
            try:
                yield cast(PrincipalT, next(result))
            finally:
                result.close()
            return

        yield cast(PrincipalT, result)

    def _bind_body_model(
        self, endpoint: Any, parameter_name: str, model: type[SQLModel]
    ) -> Any:
        """Bind a concrete body model to a generic wrapper function."""
        signature = inspect.signature(endpoint)
        parameters = [
            parameter.replace(annotation=model)
            if parameter.name == parameter_name
            else parameter
            for parameter in signature.parameters.values()
        ]
        endpoint.__signature__ = signature.replace(parameters=parameters)
        return endpoint
