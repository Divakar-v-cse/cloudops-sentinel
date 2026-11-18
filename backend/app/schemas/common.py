from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_serializer

from app.core.utils import walk_iso

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base schema that emits explicit UTC (``Z``) timestamps."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    @model_serializer(mode="wrap")
    def _serialize_utc(self, handler):  # pragma: no cover - trivial
        return walk_iso(handler(self))


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class Message(BaseModel):
    message: str
    detail: Any | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    mode: str
    database: str
    scheduler: bool
    aws_configured: bool
    ai_enabled: bool
    server_time: str
