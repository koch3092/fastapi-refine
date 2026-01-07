"""Dependency injection for Refine query parsing."""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from sqlalchemy import ColumnElement
from sqlmodel import SQLModel

from fastapi_refine.core import FilterConfig, PaginationConfig, SortConfig
from fastapi_refine.core.query import (
    parse_filters,
    parse_sorters,
    resolve_pagination,
)

__all__ = ["RefineQuery", "refine_query"]


class RefineQuery:
    """Refine query parameters parsed from request.

    This class provides convenient access to parsed query parameters
    following Refine simple-rest conventions.

    Attributes:
        model: The SQLModel class for this resource
        conditions: List of SQLAlchemy filter conditions
        order_by: List of SQLAlchemy order by clauses
        offset: Query offset for pagination
        limit: Query limit for pagination
    """

    def __init__(
        self,
        model: type[SQLModel],
        filter_config: FilterConfig,
        sort_config: SortConfig,
        pagination_config: PaginationConfig | None = None,
        *,
        _start: int | None = None,
        _end: int | None = None,
        _sort: str | None = None,
        _order: str | None = None,
        skip: int = 0,
        limit: int = 100,
        request: Request | None = None,
    ):
        self.model = model
        self.filter_config = filter_config
        self.sort_config = sort_config
        self.pagination_config = pagination_config or PaginationConfig()

        # Parse filters
        if request:
            self.conditions = parse_filters(
                request.query_params,
                filter_fields=filter_config.fields,
                search_fields=filter_config.search_fields,
            )
        else:
            self.conditions = []

        # Parse sorters
        self.order_by = parse_sorters(_sort, _order, sort_fields=sort_config.fields)

        # Parse pagination
        self.offset, self.limit = resolve_pagination(
            _start=_start,
            _end=_end,
            skip=skip,
            limit=min(limit, self.pagination_config.max_limit),
        )

    def get_count(
        self, session: Any, conditions: list[ColumnElement[Any]] | None = None
    ) -> int:
        """Get total count of records matching conditions.

        Args:
            session: SQLAlchemy/SQLModel session
            conditions: Optional list of conditions (uses self.conditions if None)

        Returns:
            Total count of matching records
        """
        from sqlalchemy import func, select

        conditions = conditions if conditions is not None else self.conditions

        count_statement = select(func.count()).select_from(self.model)
        if conditions:
            count_statement = count_statement.where(*conditions)

        return session.scalar(count_statement) or 0


def refine_query(
    model: type[SQLModel],
    filter_config: FilterConfig,
    sort_config: SortConfig,
    pagination_config: PaginationConfig | None = None,
) -> type[RefineQuery]:
    """Create a RefineQuery dependency.

    Use this function with FastAPI's Depends:

    ```python
    query_dep = refine_query(Item, filter_config, sort_config)

    @router.get("/")
    def read_items(
        query: RefineQuery = Depends(query_dep),
        ...
    ):
        conditions = query.conditions
        order_by = query.order_by
        offset, limit = query.offset, query.limit
        ...
    ```

    Args:
        model: SQLModel class
        filter_config: Filter configuration
        sort_config: Sort configuration
        pagination_config: Optional pagination configuration

    Returns:
        A callable that can be used with FastAPI's Depends
    """

    def dependency(
        request: Request,
        _start: int | None = Query(None, alias="_start"),
        _end: int | None = Query(None, alias="_end"),
        _sort: str | None = Query(None, alias="_sort"),
        _order: str | None = Query(None, alias="_order"),
        skip: int = 0,
        limit: int = 100,
    ) -> RefineQuery:
        return RefineQuery(
            model=model,
            filter_config=filter_config,
            sort_config=sort_config,
            pagination_config=pagination_config,
            _start=_start,
            _end=_end,
            _sort=_sort,
            _order=_order,
            skip=skip,
            limit=limit,
            request=request,
        )

    return dependency  # type: ignore[return-value]
