"""Pydantic-схемы для API-ответов."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


class ReportCreateResponse:
    """Ответ на POST /api/reports — возвращается вручную (dict)."""
    pass


# --- Pydantic v2 модели ---

from pydantic import BaseModel, Field


class ReportMeta(BaseModel):
    """Метаданные одного отчёта."""

    id: str = Field(default_factory=_uuid)
    project: str = "default"
    url: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    size_bytes: int = 0


class ReportListResponse(BaseModel):
    """Ответ GET /api/reports с пагинацией."""

    items: list[ReportMeta]
    total: int
    page: int
    page_size: int


class ReportDeleteResponse(BaseModel):
    """Ответ DELETE /api/reports/{project}/{id}."""

    deleted: bool
    id: str
    project: str


class ErrorResponse(BaseModel):
    """Стандартное тело ошибки."""

    detail: str
