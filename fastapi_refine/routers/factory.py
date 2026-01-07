"""CRUD Router factory for generating standard Refine-compatible endpoints."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlmodel import Session, SQLModel, select

from fastapi_refine.core import FilterConfig, PaginationConfig, SortConfig
from fastapi_refine.dependencies import RefineQuery, RefineResponse
from fastapi_refine.hooks import HookContext, RefineHooks

__all__ = ["RefineCRUDRouter"]

ModelT = TypeVar("ModelT", bound=SQLModel)
CreateSchemaT = TypeVar("CreateSchemaT", bound=SQLModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=SQLModel)
PublicSchemaT = TypeVar("PublicSchemaT", bound=SQLModel)


class RefineCRUDRouter(Generic[ModelT, CreateSchemaT, UpdateSchemaT, PublicSchemaT]):
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
            current_user_dep=CurrentUser,
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
        session_dep: Any,
        filter_config: FilterConfig,
        sort_config: SortConfig,
        pagination_config: PaginationConfig | None = None,
        hooks: RefineHooks | None = None,
        current_user_dep: Any | None = None,
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
            current_user_dep: Optional FastAPI dependency for current user
            tags: OpenAPI tags for documentation
        """
        self.model = model
        self.create_schema = create_schema
        self.update_schema = update_schema
        self.public_schema = public_schema
        self.session_dep = session_dep
        self.filter_config = filter_config
        self.sort_config = sort_config
        self.pagination_config = pagination_config or PaginationConfig()
        self.hooks = hooks or RefineHooks()
        self.current_user_dep = current_user_dep

        self.router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")])  # type: ignore[arg-type]
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup all CRUD routes."""
        self.router.add_api_route(
            "/",
            self.get_list,
            methods=["GET"],
            response_model=list[self.public_schema],  # type: ignore[name-defined]
        )
        self.router.add_api_route(
            "/{id}",
            self.get_one,
            methods=["GET"],
            response_model=self.public_schema,
        )
        self.router.add_api_route(
            "/",
            self.create,
            methods=["POST"],
            response_model=self.public_schema,
        )
        self.router.add_api_route(
            "/{id}",
            self.update,
            methods=["PATCH"],
            response_model=self.public_schema,
        )
        self.router.add_api_route(
            "/{id}",
            self.delete,
            methods=["DELETE"],
        )

    def get_list(
        self,
        request: Any,  # Request
        response: Response,
        session: Session,
        skip: int = 0,
        limit: int = 100,
        _start: int | None = Query(None, alias="_start"),
        _end: int | None = Query(None, alias="_end"),
        _sort: str | None = Query(None, alias="_sort"),
        _order: str | None = Query(None, alias="_order"),
        id: list[Any] | None = Query(None),
    ) -> list[Any]:
        """Get list of items (Refine getList)."""
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
            skip=skip,
            limit=limit,
            request=request,
        )

        conditions = query.conditions
        if id:
            conditions.append(self.model.id.in_(id))  # type: ignore[attr-defined]

        # Execute before_query hook
        if self.hooks.before_query:
            current_user = self.current_user() if self.current_user_dep else None  # type: ignore[attr-defined]
            context = HookContext(
                model=self.model,
                session=session,
                current_user=current_user,
                request=request,
            )
            conditions = self._run_hook(self.hooks.before_query, context, conditions)

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
            current_user = self.current_user() if self.current_user_dep else None  # type: ignore[attr-defined]
            context = HookContext(
                model=self.model,
                session=session,
                current_user=current_user,
                request=request,
            )
            items = self._run_hook(self.hooks.after_query, context, items)

        return items

    def get_one(self, id: Any, session: Session) -> Any:
        """Get single item by ID (Refine getOne)."""
        item = session.get(self.model, id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} not found",
            )
        return item

    def create(
        self,
        item_in: CreateSchemaT,
        session: Session,
    ) -> Any:
        """Create new item (Refine create)."""
        current_user = self.current_user_dep() if self.current_user_dep else None

        # Execute before_create hook
        if self.hooks.before_create:
            context = HookContext(
                model=self.model,
                session=session,
                current_user=current_user,
            )
            self._run_hook(self.hooks.before_create, context, item_in)

        # Create item
        item = self.model.model_validate(item_in)
        session.add(item)
        session.commit()
        session.refresh(item)

        # Execute after_create hook
        if self.hooks.after_create:
            context = HookContext(
                model=self.model,
                session=session,
                current_user=current_user,
            )
            item = self._run_hook(self.hooks.after_create, context, item_in, item)

        return item

    def update(
        self,
        id: Any,
        item_in: UpdateSchemaT,
        session: Session,
    ) -> Any:
        """Update item (Refine update)."""
        item = session.get(self.model, id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} not found",
            )

        current_user = self.current_user_dep() if self.current_user_dep else None

        # Execute before_update hook
        if self.hooks.before_update:
            context = HookContext(
                model=self.model,
                session=session,
                current_user=current_user,
            )
            self._run_hook(self.hooks.before_update, context, item)

        # Update item
        update_data = item_in.model_dump(exclude_unset=True)
        item.sqlmodel_update(update_data)
        session.add(item)
        session.commit()
        session.refresh(item)

        # Execute after_update hook
        if self.hooks.after_update:
            context = HookContext(
                model=self.model,
                session=session,
                current_user=current_user,
            )
            item = self._run_hook(self.hooks.after_update, context, item, item)

        return item

    def delete(self, id: Any, session: Session) -> dict[str, str]:
        """Delete item (Refine delete)."""
        item = session.get(self.model, id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} not found",
            )

        current_user = self.current_user_dep() if self.current_user_dep else None

        # Execute before_delete hook
        if self.hooks.before_delete:
            context = HookContext(
                model=self.model,
                session=session,
                current_user=current_user,
            )
            self._run_hook(self.hooks.before_delete, context, item)

        # Delete item
        session.delete(item)
        session.commit()

        # Execute after_delete hook
        if self.hooks.after_delete:
            context = HookContext(
                model=self.model,
                session=session,
                current_user=current_user,
            )
            self._run_hook(self.hooks.after_delete, context, item)

        return {"message": f"{self.model.__name__} deleted successfully"}

    def _run_hook(self, hook: Any, *args: Any) -> Any:
        """Run a hook, handling both sync and async hooks."""
        import inspect

        result = hook(*args)

        if inspect.isawaitable(result):
            # For now, we'll just return the awaitable as-is
            # In a full async implementation, we'd await it here
            return result
        return result
