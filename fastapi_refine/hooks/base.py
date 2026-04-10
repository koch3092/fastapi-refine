"""Hook system for customizing CRUD behavior."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnElement
from sqlmodel import Session, SQLModel

__all__ = ["RefineHooks", "HookContext"]

PrincipalT = TypeVar("PrincipalT")


# Hook type aliases
BeforeQueryHook = Callable[
    ["HookContext[PrincipalT]", list[ColumnElement[Any]]],
    list[ColumnElement[Any]] | Awaitable[list[ColumnElement[Any]]],
]

AfterQueryHook = Callable[
    ["HookContext[PrincipalT]", list[Any]],
    list[Any] | Awaitable[list[Any]],
]

BeforeCreateHook = Callable[
    ["HookContext[PrincipalT]", Any],
    dict[str, Any] | None | Awaitable[dict[str, Any] | None],
]

BeforeUpdateHook = Callable[
    ["HookContext[PrincipalT]", Any, Any],
    dict[str, Any] | None | Awaitable[dict[str, Any] | None],
]

BeforeMutationHook = Callable[
    ["HookContext[PrincipalT]", Any],
    None | Awaitable[None],
]

AfterMutationHook = Callable[
    ["HookContext[PrincipalT]", Any, Any],
    Any | Awaitable[Any],
]

AfterDeleteHook = Callable[
    ["HookContext[PrincipalT]", Any],
    None | Awaitable[None],
]


@dataclass
class HookContext(Generic[PrincipalT]):
    """Context passed to hooks during execution.

    Attributes:
        model: The SQLModel class being operated on
        session: Database session
        current_principal: Currently authenticated principal (if available)
        request: Current FastAPI request (if available)
    """

    model: type[SQLModel]
    session: Session
    current_principal: PrincipalT | None = None
    request: Any | None = None


@dataclass
class RefineHooks(Generic[PrincipalT]):
    """Collection of lifecycle hooks for CRUD operations.

    All hooks are optional. Define only the ones you need.

    Attributes:
        before_query: Called before query execution, can modify conditions
        after_query: Called after query execution, can modify results
        before_create: Called before creating a record, can raise for permission
            check and optionally return extra fields for model validation
        after_create: Called after creating a record, can modify the result
        before_update: Called before updating a record, can raise for permission
            check and optionally return extra fields for the update payload
        after_update: Called after updating a record, can modify the result
        before_delete: Called before deleting a record, can raise for permission check
        after_delete: Called after deleting a record
    """

    before_query: BeforeQueryHook[PrincipalT] | None = None
    after_query: AfterQueryHook[PrincipalT] | None = None
    before_create: BeforeCreateHook[PrincipalT] | None = None
    after_create: AfterMutationHook[PrincipalT] | None = None
    before_update: BeforeUpdateHook[PrincipalT] | None = None
    after_update: AfterMutationHook[PrincipalT] | None = None
    before_delete: BeforeMutationHook[PrincipalT] | None = None
    after_delete: AfterDeleteHook[PrincipalT] | None = None
