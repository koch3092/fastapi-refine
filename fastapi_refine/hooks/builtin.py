"""Built-in hook implementations for common use cases."""

from __future__ import annotations

from typing import Any

from fastapi import status
from sqlalchemy import ColumnElement

from fastapi_refine.errors import RefineHTTPException
from fastapi_refine.hooks.base import HookContext, RefineHooks

__all__ = ["OwnerBasedHooks"]


class OwnerBasedHooks(RefineHooks[Any]):
    """Hooks for owner-based permission control.

    Ensures users can only access records they own, unless they are superusers.

    Example:
        ```python
        hooks = OwnerBasedHooks(
            owner_field="owner_id",
            allow_superuser=True,
        )
        ```
    """

    def __init__(
        self,
        owner_field: str = "owner_id",
        allow_superuser: bool = True,
    ):
        """Initialize owner-based hooks.

        Args:
            owner_field: Name of the field containing the owner's user ID
            allow_superuser: Whether to allow superusers to access all records
        """
        self.owner_field = owner_field
        self.allow_superuser = allow_superuser
        super().__init__(
            before_query=self._before_query,
            before_create=self._before_create,
            before_update=self._before_update,
            before_delete=self._before_mutation,
        )

    def _before_query(
        self,
        context: HookContext[Any],
        conditions: list[ColumnElement[Any]],
    ) -> list[ColumnElement[Any]]:
        """Add owner filter to query conditions."""
        if not context.current_principal:
            return conditions

        if self.allow_superuser and getattr(
            context.current_principal, "is_superuser", False
        ):
            return conditions

        user_id = getattr(context.current_principal, "id", None)
        if not user_id:
            return conditions

        # Add owner_id filter
        model_class = context.model
        owner_column = getattr(model_class, self.owner_field)
        conditions.append(owner_column == user_id)

        return conditions

    def _resolve_owner_fields(
        self, context: HookContext[Any]
    ) -> dict[str, Any] | None:
        """Return extra fields that bind the record to the current principal."""
        if not context.current_principal:
            return None

        user_id = getattr(context.current_principal, "id", None)
        if user_id is None:
            return None

        return {self.owner_field: user_id}

    def _before_create(
        self, context: HookContext[Any], item_in: Any
    ) -> dict[str, Any] | None:
        """Inject the current principal as the record owner on create."""
        return self._resolve_owner_fields(context)

    def _before_update(
        self, context: HookContext[Any], item: Any, item_in: Any
    ) -> dict[str, Any] | None:
        """Check ownership and keep the record bound to the current principal."""
        self._before_mutation(context, item)
        return self._resolve_owner_fields(context)

    def _before_mutation(self, context: HookContext[Any], item: Any) -> None:
        """Check if user has permission to modify/delete this item."""
        if not context.current_principal:
            raise RefineHTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Authentication required",
            )

        if self.allow_superuser and getattr(
            context.current_principal, "is_superuser", False
        ):
            return

        user_id = getattr(context.current_principal, "id", None)
        owner_id = getattr(item, self.owner_field, None)

        if owner_id != user_id:
            raise RefineHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                message="Not enough permissions",
            )
