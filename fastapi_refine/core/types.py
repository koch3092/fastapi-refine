"""Core type definitions for fastapi-refine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement

__all__ = ["FilterField", "FilterConfig", "SortConfig", "PaginationConfig"]


@dataclass(frozen=True)
class FilterField:
    """Field filter configuration.

    Args:
        column: SQLAlchemy column reference
        cast: Type converter function (str -> target type)
    """

    column: ColumnElement[Any]
    cast: Callable[[str], Any]


@dataclass
class FilterConfig:
    """Filter configuration.

    Args:
        fields: Mapping of field names to FilterField configs
        search_fields: List of columns for full-text search (q parameter)
    """

    fields: dict[str, FilterField]
    search_fields: list[ColumnElement[Any]] | None = None


@dataclass
class SortConfig:
    """Sort configuration.

    Args:
        fields: Mapping of field names to SQLAlchemy columns
    """

    fields: dict[str, ColumnElement[Any]]


@dataclass
class PaginationConfig:
    """Pagination configuration.

    Args:
        default_skip: Default offset for skip pagination
        default_limit: Default limit for skip/limit pagination
        max_limit: Maximum allowed limit (prevents excessive queries)
    """

    default_skip: int = 0
    default_limit: int = 100
    max_limit: int = 1000
