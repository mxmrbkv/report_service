"""Зависимости FastAPI (dependency injection)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.core.allure import ReportManager
from app.core.config import Settings, get_settings

# Иерархия ролей: больше число = больше прав.
ROLE_LEVELS: dict[str, int] = {"viewer": 0, "reporter": 1, "admin": 2}


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


def _user_role_level(user: dict | None) -> int:
    """Возвращает максимальный уровень роли пользователя (или -1)."""
    if not user:
        return max(ROLE_LEVELS.values())
    roles = user.get("roles") or []
    levels = [ROLE_LEVELS[r] for r in roles if r in ROLE_LEVELS]
    return max(levels) if levels else -1


def require_role(min_role: str):
    """Зависимость: требует роль ``min_role`` или выше.

    Иерархия: viewer < reporter < admin.
    При выключенной авторизации (auth_enabled=False) проверка не выполняется.
    """
    required = ROLE_LEVELS[min_role]

    async def checker(
        request: Request,
        settings: Settings = Depends(get_settings),
    ) -> dict | None:
        if not settings.auth_enabled:
            return None
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        if _user_role_level(user) < required:
            raise HTTPException(
                status_code=403,
                detail=f"Недостаточно прав: требуется роль '{min_role}' или выше.",
            )
        return user

    return checker
