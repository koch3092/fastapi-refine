"""Core type definitions for fastapi-refine."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from sqlalchemy import ColumnElement

__all__ = [
    "DependencyCallable",
    "FilterField",
    "FilterConfig",
    "SortConfig",
    "PaginationConfig",
]

T_co = TypeVar("T_co", covariant=True)


class DependencyCallable(Protocol[T_co]):
    """A FastAPI-compatible dependency callable.

    Supports standard return-value dependencies as well as sync/async yield-based
    dependencies used by FastAPI.
    """

    def __call__(
        self, *args: Any, **kwargs: Any
    ) -> (
        T_co
        | Awaitable[T_co]
        | Generator[T_co, None, None]
        | AsyncGenerator[T_co, None]
    ): ...


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
    """Pagination configuration for Refine simple-rest range pagination.

    Args:
        default_start: Default `_start` value when `_start` is omitted.
        default_page_size: Default page size used when `_end` is omitted.
        max_page_size: Maximum allowed page size (prevents excessive queries).
    """

    default_start: int = 0
    default_page_size: int = 100
    max_page_size: int = 1000
