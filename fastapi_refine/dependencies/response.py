"""Response handling for Refine simple-rest conventions."""

from __future__ import annotations

from fastapi import Response

__all__ = ["RefineResponse", "refine_response"]


class _RefineResponseHelper:
    """Helper for setting Refine-specific response headers.

    Refine's simple-rest data provider expects an x-total-count header
    for list responses to support server-side pagination.
    """

    def __init__(self, response: Response):
        self._response = response

    def set_total_count(self, count: int) -> None:
        """Set the x-total-count header.

        Args:
            count: Total number of records (for pagination)
        """
        self._response.headers["x-total-count"] = str(count)


# Type alias for backwards compatibility
RefineResponse = _RefineResponseHelper


def refine_response() -> _RefineResponseHelper:
    """Dependency that creates a RefineResponse helper.

    Usage:
        ```python
        @router.get("/")
        def read_items(
            response: RefineResponse = Depends(refine_response),
            ...
        ):
            response.set_total_count(100)
            return items
        ```
    """

    def dependency(resp: Response) -> _RefineResponseHelper:
        return _RefineResponseHelper(resp)

    return dependency  # type: ignore[return-value]
