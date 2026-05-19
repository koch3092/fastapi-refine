from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from fastapi_refine import FilterConfig, FilterField, SortConfig, parse_uuid


class TypedItem(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str
    created_at: datetime


filter_config = FilterConfig(
    fields={
        "id": FilterField(TypedItem.id, parse_uuid),
        "title": FilterField(TypedItem.title, str),
    },
    search_fields=[TypedItem.title],
)
sort_config = SortConfig(
    fields={
        "id": TypedItem.id,
        "title": TypedItem.title,
        "created_at": TypedItem.created_at,
    }
)
