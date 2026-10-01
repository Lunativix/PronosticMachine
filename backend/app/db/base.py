"""SQLAlchemy declarative base and shared columns."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class SourceMixin:
    source: Mapped[str] = mapped_column(String(64), default="import")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    quality: Mapped[str] = mapped_column(String(32), default="unknown")
    source_priority: Mapped[float] = mapped_column(Float, default=0.0)
