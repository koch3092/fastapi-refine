"""Hook system for customizing CRUD behavior."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement
from sqlmodel import SQLModel

__all__ = ["RefineHooks", "HookContext"]


# Hook type aliases
BeforeQueryHook = Callable[
    ["HookContext", list[ColumnElement[Any]]],
    list[ColumnElement[Any]] | Awaitable[list[ColumnElement[Any]]],
]

AfterQueryHook = Callable[
    ["HookContext", list[Any]],
    list[Any] | Awaitable[list[Any]],
]

BeforeMutationHook = Callable[
    ["HookContext", Any],
    None | Awaitable[None],
]

AfterMutationHook = Callable[
    ["HookContext", Any, Any],
    Any | Awaitable[Any],
]


@dataclass
class HookContext:
    """Context passed to hooks during execution.

    Attributes:
        model: The SQLModel class being operated on
        session: Database session
        current_user: Currently authenticated user (if available)
        request: Current FastAPI request (if available)
    """

    model: type[SQLModel]
    session: Any
    current_user: Any | None = None
    request: Any | None = None


@dataclass
class RefineHooks:
    """Collection of lifecycle hooks for CRUD operations.

    All hooks are optional. Define only the ones you need.

    Attributes:
        before_query: Called before query execution, can modify conditions
        after_query: Called after query execution, can modify results
        before_create: Called before creating a record, can raise for permission check
        after_create: Called after creating a record, can modify the result
        before_update: Called before updating a record, can raise for permission check
        after_update: Called after updating a record, can modify the result
        before_delete: Called before deleting a record, can raise for permission check
        after_delete: Called after deleting a record
    """

    before_query: BeforeQueryHook | None = None
    after_query: AfterQueryHook | None = None
    before_create: BeforeMutationHook | None = None
    after_create: AfterMutationHook | None = None
    before_update: BeforeMutationHook | None = None
    after_update: AfterMutationHook | None = None
    before_delete: BeforeMutationHook | None = None
    after_delete: AfterMutationHook | None = None
