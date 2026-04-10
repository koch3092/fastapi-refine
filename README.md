# fastapi-refine

[![PyPI version](https://badge.fury.io/py/fastapi-refine.svg)](https://badge.fury.io/py/fastapi-refine)
[![Python Versions](https://img.shields.io/pypi/pyversions/fastapi-refine.svg)](https://pypi.org/project/fastapi-refine/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

FastAPI integration for [Refine](https://refine.dev/) simple-rest data provider. Build type-safe, production-ready REST APIs that work seamlessly with Refine's data provider conventions.

## Features

- **Automatic Query Parsing**: Parse Refine's filter, sort, and pagination parameters out-of-the-box
- **Type-Safe**: Full type hints and mypy strict mode compliance
- **SQLModel Integration**: First-class support for SQLModel/SQLAlchemy ORM
- **CRUD Router Factory**: Generate complete CRUD endpoints with one class
- **Flexible Filtering**: Support for `eq`, `ne`, `gte`, `lte`, `like` operators and full-text search
- **Hook System**: Inject custom logic before/after operations (permissions, validation, etc.)
- **Refine Error Integration**: Optional app-level error normalization via `configure_refine(app)`
- **Production Ready**: Built with FastAPI best practices

## Installation

```bash
pip install fastapi-refine
```

## Upgrade Notes for 0.3.0

If you are upgrading from `0.2.x`, these are the user-visible changes to account for:

- `RefineCRUDRouter(..., current_user_dep=...)` is now
  `RefineCRUDRouter(..., current_principal_dep=...)`.
- `HookContext.current_user` is now `HookContext.current_principal`.
- `DELETE` success returns the deleted public record snapshot, matching Refine's
  expected mutation response contract.
- Unified Refine error envelopes are opt-in via `configure_refine(app)`.
- Legacy `skip`/`limit` query parameters still return `422` in `0.3.x`.

## Quick Start

### Basic Usage with Manual Endpoints

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from fastapi_refine import (
    FilterConfig,
    FilterField,
    SortConfig,
    RefineQuery,
    RefineResponse,
    refine_query,
    refine_response,
)
from fastapi_refine.core import parse_bool

from .models import Item, ItemPublic
from .database import get_session

router = APIRouter(prefix="/items", tags=["items"])

SessionDep = Annotated[Session, Depends(get_session)]

# Configure which fields can be filtered and sorted
filter_config = FilterConfig(
    fields={
        "id": FilterField(Item.id, str),
        "title": FilterField(Item.title, str),
        "is_active": FilterField(Item.is_active, parse_bool),
    },
    search_fields=[Item.title, Item.description],  # Full-text search fields
)

sort_config = SortConfig(
    fields={
        "id": Item.id,
        "title": Item.title,
        "created_at": Item.created_at,
    }
)

@router.get("/", response_model=list[ItemPublic])
def read_items(
    session: SessionDep,
    refine_resp: Annotated[RefineResponse, Depends(refine_response())],
    query: Annotated[RefineQuery, Depends(refine_query(Item, filter_config, sort_config))],
) -> list[ItemPublic]:
    # query.conditions contains parsed WHERE clauses
    # query.order_by contains ORDER BY clauses
    # query.offset and query.limit are ready for pagination

    items = session.exec(
        select(Item)
        .where(*query.conditions)
        .order_by(*query.order_by)
        .offset(query.offset)
        .limit(query.limit)
    ).all()

    # Set x-total-count header for Refine pagination
    total = query.get_count(session, query.conditions)
    refine_resp.set_total_count(total)

    return items
```

### Automatic CRUD Router (Recommended)

Generate all CRUD endpoints automatically:

```python
from fastapi import FastAPI
from fastapi_refine import (
    RefineCRUDRouter,
    FilterConfig,
    FilterField,
    SortConfig,
    configure_refine,
)
from fastapi_refine.core import parse_bool
from .models import Item, ItemCreate, ItemUpdate, ItemPublic
from .database import get_session

app = FastAPI()
# Register any numeric status handlers before calling configure_refine(app).
configure_refine(app)

# Create router with full CRUD operations
crud_router = RefineCRUDRouter(
    model=Item,
    prefix="/items",
    create_schema=ItemCreate,
    update_schema=ItemUpdate,
    public_schema=ItemPublic,
    session_dep=get_session,
    filter_config=FilterConfig(
        fields={
            "title": FilterField(Item.title, str),
            "is_active": FilterField(Item.is_active, parse_bool),
        },
        search_fields=[Item.title],
    ),
    sort_config=SortConfig(
        fields={"title": Item.title, "created_at": Item.created_at}
    ),
    tags=["items"],
)

app.include_router(crud_router.router)
```

This automatically creates:
- `GET /items/` - List with filtering, sorting, pagination
- `GET /items/{id}` - Get single item
- `POST /items/` - Create item
- `PATCH /items/{id}` - Update item
- `DELETE /items/{id}` - Delete item

## Advanced Usage

### Custom Hooks for Permissions

```python
from fastapi import Depends, HTTPException
from fastapi_refine import (
    RefineHooks,
    HookContext,
    RefineCRUDRouter,
)

def before_query(context: HookContext, conditions: list) -> list:
    """Filter items to only show user's own items"""
    if context.current_principal:
        conditions.append(context.model.owner_id == context.current_principal.id)
    return conditions

def before_delete(context: HookContext, item) -> None:
    """Only allow deleting own items"""
    if item.owner_id != context.current_principal.id:
        raise HTTPException(status_code=403, detail="Not authorized")

def before_create(context: HookContext, item_in) -> dict | None:
    """Inject server-side fields during create"""
    if context.current_principal:
        return {"owner_id": context.current_principal.id}
    return None

def before_update(context: HookContext, item, item_in) -> dict | None:
    """Override server-controlled fields during update"""
    if context.current_principal:
        return {"owner_id": context.current_principal.id}
    return None

hooks = RefineHooks(
    before_query=before_query,
    before_create=before_create,
    before_update=before_update,
    before_delete=before_delete,
)

crud_router = RefineCRUDRouter(
    model=Item,
    hooks=hooks,
    current_principal_dep=get_current_user,
    # ... other config
)
```

### Error Formatting

Install the app-level Refine integration to normalize FastAPI and package errors into
Refine-friendly JSON responses:

```python
from fastapi import FastAPI
from fastapi_refine import configure_refine

app = FastAPI()
# Register numeric status handlers such as 404/409/422 before configure_refine(app).
configure_refine(app)
```

`configure_refine(app)` is a convenience helper with installation-time snapshot
semantics:

- It ensures `RefineHTTPException` has a dedicated handler, preserving any existing
  app-registered `RefineHTTPException` handler.
- It wraps numeric status handlers that already exist when called, so
  `RefineHTTPException(status_code=...)` still uses the active
  `RefineHTTPException` handler for those statuses.
- It installs `StarletteHTTPException` and `RequestValidationError` handlers only when
  those slots are still using FastAPI's defaults.
- If the middleware stack was already built, it rebuilds the current stack so the new
  handlers take effect immediately.
- It does not track numeric status handlers added later.

Package-generated router/query/hook errors are raised as `RefineHTTPException` and are
handled by fastapi-refine before generic `HTTPException` or
`StarletteHTTPException` handlers. This keeps the Refine wire shape stable, but it also
means your existing generic HTTP exception handlers will not see those package-generated
errors.

When installed, the normalized response envelope uses:

- `message`
- `statusCode`
- `code`
- optional `errors`
- optional top-level `detail` when the original `HTTPException.detail` was any
  non-string structured value

For `RefineHTTPException`, `message` stays the primary Refine-facing summary. If you
pass a more specific `detail_message`, it is preserved as top-level `detail` when the
handler formats the response.

Top-level `errors` are produced only for package-generated `RefineHTTPException`
values and `RequestValidationError`. Custom structured `HTTPException.detail`
payloads are preserved under `detail` rather than being auto-promoted to `errors`.

If your app needs logging, trace IDs, or extra headers on package-generated Refine
errors, register a `RefineHTTPException` handler explicitly and delegate to the public
handler. `configure_refine(app)` preserves that handler and numeric status wrappers
continue to dispatch through it:

```python
from fastapi_refine import RefineHTTPException, refine_http_exception_handler
from starlette.requests import Request

@app.exception_handler(RefineHTTPException)
async def app_refine_exception_handler(request: Request, exc: RefineHTTPException):
    response = await refine_http_exception_handler(request, exc)
    response.headers["x-trace-id"] = request.headers.get("x-trace-id", "missing")
    return response
```

If you want full explicit control instead of `configure_refine(app)`, register the
public handlers yourself:

```python
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi_refine import (
    RefineHTTPException,
    refine_http_exception_handler,
    refine_validation_exception_handler,
)

app.add_exception_handler(RefineHTTPException, refine_http_exception_handler)
app.add_exception_handler(StarletteHTTPException, refine_http_exception_handler)
app.add_exception_handler(RequestValidationError, refine_validation_exception_handler)
```

### Pagination Configuration

```python
from fastapi_refine import PaginationConfig, RefineCRUDRouter

pagination_config = PaginationConfig(
    default_start=0,
    default_page_size=50,
    max_page_size=500,  # Prevent excessive queries
)

crud_router = RefineCRUDRouter(
    pagination_config=pagination_config,
    # ... other config
)
```

## Supported Query Parameters

The library parses Refine simple-rest query parameters:

### Filtering
- `field=value` - Exact match (eq)
- `field_ne=value` - Not equal
- `field_gte=value` - Greater than or equal
- `field_lte=value` - Less than or equal
- `field_like=value` - Contains (case-insensitive)
- `q=search` - Full-text search across configured fields

### Sorting
- `_sort=field1,field2` - Sort by multiple fields
- `_order=asc,desc` - Sort order for each field

### Pagination
- Range-based: `_start=0&_end=20`
- Legacy `skip`/`limit` is currently rejected with `422` (planned to be silently ignored after `0.5.x`).

### Example Query
```
GET /items?title_like=hello&is_active=true&_sort=created_at&_order=desc&_start=0&_end=10
```

## Type Converters

Built-in converters for common types:

```python
from fastapi_refine import FilterConfig, FilterField
from fastapi_refine.core import parse_bool, parse_uuid

filter_config = FilterConfig(
    fields={
        "id": FilterField(Item.id, parse_uuid),
        "is_active": FilterField(Item.is_active, parse_bool),
        "price": FilterField(Item.price, float),
        "quantity": FilterField(Item.quantity, int),
    }
)
```

## Requirements

- Python 3.10+
- FastAPI 0.114.2+
- SQLModel 0.0.21+

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details.

## Links

- [Refine Documentation](https://refine.dev/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLModel Documentation](https://sqlmodel.tiangolo.com/)
