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
- **Production Ready**: Built with FastAPI best practices

## Installation

```bash
pip install fastapi-refine
```

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
from fastapi_refine import RefineCRUDRouter, FilterConfig, FilterField, SortConfig
from fastapi_refine.core import parse_bool
from .models import Item, ItemCreate, ItemUpdate, ItemPublic
from .database import get_session

app = FastAPI()

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
from fastapi_refine import RefineHooks, HookContext, RefineCRUDRouter

def before_query(context: HookContext, conditions: list) -> list:
    """Filter items to only show user's own items"""
    if context.current_user:
        conditions.append(context.model.owner_id == context.current_user.id)
    return conditions

def before_delete(context: HookContext, item) -> None:
    """Only allow deleting own items"""
    if item.owner_id != context.current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

hooks = RefineHooks(
    before_query=before_query,
    before_delete=before_delete,
)

crud_router = RefineCRUDRouter(
    model=Item,
    hooks=hooks,
    current_user_dep=get_current_user,
    # ... other config
)
```

### Pagination Configuration

```python
from fastapi_refine import PaginationConfig, RefineCRUDRouter

pagination_config = PaginationConfig(
    default_skip=0,
    default_limit=50,
    max_limit=500,  # Prevent excessive queries
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
- Offset-based: `skip=0&limit=20`

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
