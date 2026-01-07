"""Built-in hook implementations for common use cases."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement

from fastapi_refine.hooks.base import HookContext, RefineHooks

__all__ = ["OwnerBasedHooks"]


class OwnerBasedHooks(RefineHooks):
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
            before_update=self._before_mutation,
            before_delete=self._before_mutation,
        )

    def _before_query(
        self,
        context: HookContext,
        conditions: list[ColumnElement[Any]],
    ) -> list[ColumnElement[Any]]:
        """Add owner filter to query conditions."""
        if not context.current_user:
            return conditions

        if self.allow_superuser and getattr(
            context.current_user, "is_superuser", False
        ):
            return conditions

        user_id = getattr(context.current_user, "id", None)
        if not user_id:
            return conditions

        # Add owner_id filter
        model_class = context.model
        owner_column = getattr(model_class, self.owner_field)
        conditions.append(owner_column == user_id)

        return conditions

    def _before_mutation(self, context: HookContext, item: Any) -> None:
        """Check if user has permission to modify/delete this item."""
        if not context.current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        if self.allow_superuser and getattr(
            context.current_user, "is_superuser", False
        ):
            return

        user_id = getattr(context.current_user, "id", None)
        owner_id = getattr(item, self.owner_field, None)

        if owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
