"""Basic usage example of fastapi-refine."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Field, Session, SQLModel, create_engine, select

from fastapi_refine import (
    FilterConfig,
    FilterField,
    RefineQuery,
    RefineResponse,
    SortConfig,
    refine_query,
    refine_response,
)
from fastapi_refine.core import parse_bool

# Database setup
sqlite_url = "sqlite:///./example.db"
engine = create_engine(sqlite_url, echo=True)


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


# Models
class Item(SQLModel, table=True):
    """Item model."""

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    description: str | None = None
    is_active: bool = Field(default=True)
    price: float = Field(default=0.0)


class ItemPublic(SQLModel):
    """Public item schema."""

    id: int
    title: str
    description: str | None
    is_active: bool
    price: float


# FastAPI app
app = FastAPI(title="fastapi-refine Example")


# Configure filters and sorting
filter_config = FilterConfig(
    fields={
        "id": FilterField(Item.id, int),
        "title": FilterField(Item.title, str),
        "is_active": FilterField(Item.is_active, parse_bool),
        "price": FilterField(Item.price, float),
    },
    search_fields=[Item.title, Item.description],
)

sort_config = SortConfig(
    fields={
        "id": Item.id,
        "title": Item.title,
        "price": Item.price,
    }
)


@app.on_event("startup")
def on_startup():
    """Create tables on startup."""
    SQLModel.metadata.create_all(engine)


@app.get("/items", response_model=list[ItemPublic])
def read_items(
    session: SessionDep,
    refine_resp: Annotated[RefineResponse, Depends(refine_response())],
    query: Annotated[RefineQuery, Depends(refine_query(Item, filter_config, sort_config))],
) -> list[Item]:
    """Get list of items with filtering, sorting, and pagination."""
    # Build query
    items = session.exec(
        select(Item)
        .where(*query.conditions)
        .order_by(*query.order_by)
        .offset(query.offset)
        .limit(query.limit)
    ).all()

    # Set total count header for pagination
    total = query.get_count(session, query.conditions)
    refine_resp.set_total_count(total)

    return list(items)


@app.get("/items/{item_id}", response_model=ItemPublic)
def read_item(item_id: int, session: SessionDep) -> Item:
    """Get single item by ID."""
    item = session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
