"""Pydantic-схемы для API-ответов."""

from __future__ import annotations

from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


from pydantic import BaseModel, Field


class ReportMeta(BaseModel):
    """Метаданные проекта-отчёта."""

    project: str = "default"
    url: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    size_bytes: int = 0
    uploads_count: int = 0
    results_count: int = 0


class ReportListResponse(BaseModel):
    """Ответ GET /api/reports с пагинацией."""

    items: list[ReportMeta]
    total: int
    page: int
    page_size: int


class ReportDeleteResponse(BaseModel):
    """Ответ DELETE /api/reports/{project}."""

    deleted: bool
    project: str


class ErrorResponse(BaseModel):
    """Стандартное тело ошибки."""

    detail: str