"""Зависимости FastAPI (dependency injection)."""

from __future__ import annotations

from app.core.allure import ReportManager
from app.core.config import get_settings


def get_report_manager() -> ReportManager:
    """Возвращает singleton-экземпляр ReportManager."""
    return ReportManager(get_settings())
