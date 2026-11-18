"""Shared utilities: UTC timestamps, JSON-safe serialisation, id helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    """Naive UTC timestamp (portable across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def walk_iso(value: Any) -> Any:
    """Recursively convert naive datetimes into explicit UTC ISO strings."""
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, list):
        return [walk_iso(item) for item in value]
    if isinstance(value, tuple):
        return tuple(walk_iso(item) for item in value)
    if isinstance(value, dict):
        return {key: walk_iso(item) for key, item in value.items()}
    return value


def new_id() -> str:
    return uuid.uuid4().hex
