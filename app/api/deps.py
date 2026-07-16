"""Зависимости FastAPI (dependency injection)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.core.allure import ReportManager
from app.core.config import Settings, get_settings


def get_report_manager() -> ReportManager:
    """Возвращает singleton-экземпляр ReportManager."""
    return ReportManager(get_settings())


async def require_auth(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict | None:
    """Проверяет авторизацию пользователя.

    Если ``auth_enabled = False`` — авторизация не требуется, возвращает ``None``.
    Если включена — проверяет наличие пользователя в сессии, иначе 401.
    """
    if not settings.auth_enabled:
        return None

    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
