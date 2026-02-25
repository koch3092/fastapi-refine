"""Query parsing logic for Refine simple-rest conventions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ColumnElement, or_
from starlette.datastructures import QueryParams

__all__ = [
    "parse_filters",
    "parse_sorters",
    "resolve_pagination",
    "ensure_no_legacy_pagination_params",
    "parse_bool",
    "parse_uuid",
]

LEGACY_PAGINATION_QUERY_KEYS = {"skip", "limit"}
IGNORED_QUERY_KEYS = {"_start", "_end", "_sort", "_order", "id", *LEGACY_PAGINATION_QUERY_KEYS}


def parse_bool(value: str) -> bool:
    """Parse boolean from string.

    Supports: 1/0, true/false, t/f, yes/y, no/n (case-insensitive).
    """
    lowered = value.strip().lower()
    if lowered in {"1", "true", "t", "yes", "y"}:
        return True
    if lowered in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def parse_uuid(value: str) -> uuid.UUID:
    """Parse UUID from string."""
    return uuid.UUID(value)


def split_filter_key(key: str) -> tuple[str, str]:
    """Split filter key into field name and operator.

    Examples:
        "name" -> ("name", "eq")
        "age_gte" -> ("age", "gte")
        "title_like" -> ("title", "like")
    """
    for suffix in ("_ne", "_gte", "_lte", "_like"):
        if key.endswith(suffix):
            return key[: -len(suffix)], suffix[1:]
    return key, "eq"


def parse_filters(
    query_params: QueryParams,
    *,
    filter_fields: dict[str, Any],
    search_fields: list[ColumnElement[Any]] | None = None,
) -> list[ColumnElement[Any]]:
    """Parse Refine simple-rest filters from query parameters.

    Supports json-server style operators:
    - eq (default): field=value
    - ne: field_ne=value
    - gte: field_gte=value
    - lte: field_lte=value
    - like: field_like=value (contains match)

    Also supports full-text search via q parameter.

    Args:
        query_params: FastAPI/Starlette query parameters
        filter_fields: Mapping of field names to FilterField configs
        search_fields: Columns to search for q parameter

    Returns:
        List of SQLAlchemy conditions
    """
    conditions: list[ColumnElement[Any]] = []

    for key, value in query_params.multi_items():
        if key in IGNORED_QUERY_KEYS:
            continue

        # Full-text search
        if key == "q":
            if search_fields:
                pattern = f"%{value}%"
                conditions.append(
                    or_(*(field.ilike(pattern) for field in search_fields))
                )
            continue

        # Field filters
        field, op = split_filter_key(key)
        field_spec = filter_fields.get(field)
        if not field_spec:
            continue

        try:
            typed_value = field_spec.cast(value)
        except (TypeError, ValueError):
            continue

        column = field_spec.column
        if op == "eq":
            conditions.append(column == typed_value)
        elif op == "ne":
            conditions.append(column != typed_value)
        elif op == "gte":
            conditions.append(column >= typed_value)
        elif op == "lte":
            conditions.append(column <= typed_value)
        elif op == "like":
            if isinstance(typed_value, str):
                conditions.append(column.ilike(f"%{value}%"))
        else:
            conditions.append(column == typed_value)

    return conditions


def parse_sorters(
    _sort: str | None,
    _order: str | None,
    *,
    sort_fields: dict[str, ColumnElement[Any]],
) -> list[ColumnElement[Any]]:
    """Parse Refine simple-rest sorters from query parameters.

    Supports comma-separated fields and orders:
    _sort=title,createdAt&_order=asc,desc

    Args:
        _sort: Comma-separated field names to sort by
        _order: Comma-separated order directions (asc/desc)
        sort_fields: Mapping of field names to SQLAlchemy columns

    Returns:
        List of SQLAlchemy order by clauses
    """
    if not _sort:
        return []

    sort_fields_list = [field.strip() for field in _sort.split(",") if field.strip()]
    order_list = (
        [order.strip().lower() for order in _order.split(",")] if _order else []
    )

    order_by: list[ColumnElement[Any]] = []
    for index, field in enumerate(sort_fields_list):
        column = sort_fields.get(field)
        if not column:
            continue

        order = order_list[index] if index < len(order_list) else "asc"
        order_by.append(column.desc() if order == "desc" else column.asc())

    return order_by


def ensure_no_legacy_pagination_params(query_params: QueryParams) -> None:
    """Reject legacy skip/limit pagination parameters.

    TODO(0.5.x): stop returning 422 for legacy keys and silently ignore them.
    """
    legacy_keys = sorted(
        {
            key
            for key, _ in query_params.multi_items()
            if key in LEGACY_PAGINATION_QUERY_KEYS
        }
    )

    if legacy_keys:
        supported = "`_start` and `_end`"
        raise ValueError(
            "Legacy pagination parameters are not supported: "
            f"{', '.join(legacy_keys)}. Use {supported} instead."
        )


def resolve_pagination(
    *,
    _start: int | None,
    _end: int | None,
    default_start: int,
    default_page_size: int,
    max_page_size: int,
) -> tuple[int, int]:
    """Resolve pagination from Refine simple-rest range parameters.

    Supports only range-based pagination (`_start`, `_end`). Returned values are
    translated into SQLAlchemy-compatible `(offset, limit)`.

    Args:
        _start: Range start (0-based, inclusive)
        _end: Range end (0-based, exclusive)
        default_start: Default start when `_start` is omitted
        default_page_size: Default page size when `_end` is omitted
        max_page_size: Maximum allowed page size

    Returns:
        Tuple of (offset, limit) for SQLAlchemy queries

    Raises:
        ValueError: If pagination values are invalid
    """
    if default_start < 0:
        raise ValueError("pagination_config.default_start must be >= 0")
    if default_page_size < 0:
        raise ValueError("pagination_config.default_page_size must be >= 0")
    if max_page_size <= 0:
        raise ValueError("pagination_config.max_page_size must be > 0")

    normalized_default_size = min(default_page_size, max_page_size)

    start = _start if _start is not None else default_start
    if _end is None:
        end = start + normalized_default_size
    else:
        end = _end

    if start < 0:
        raise ValueError("`_start` must be greater than or equal to 0.")
    if end < 0:
        raise ValueError("`_end` must be greater than or equal to 0.")
    if end < start:
        raise ValueError("`_end` must be greater than or equal to `_start`.")

    return start, min(max_page_size, end - start)
