"""Зависимости FastAPI (dependency injection)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.allure import ReportManager
from app.core.config import Settings, get_settings

# Иерархия ролей: больше число = больше прав.
ROLE_LEVELS: dict[str, int] = {"viewer": 0, "reporter": 1, "admin": 2}

# Security-схема для Swagger UI (кнопка Authorize) и извлечения Bearer-токена
http_bearer = HTTPBearer(
    scheme_name="BearerAuth",
    auto_error=False,
    description="JWT Access Token. Введите токен без префикса 'Bearer '",
)


def get_report_manager() -> ReportManager:
    """Возвращает singleton-экземпляр ReportManager."""
    return ReportManager(get_settings())


def decode_jwt_payload(token: str) -> dict:
    """Декодирует payload JWT без проверки подписи (для извлечения claims)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format: expected 3 parts")
    payload_b64 = parts[1]
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    return json.loads(payload_bytes)


def extract_user_from_token(token: str, settings: Settings) -> dict:
    """Извлекает данные пользователя и роли из JWT токена, проверяя exp."""
    try:
        payload = decode_jwt_payload(token)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Некорректный формат токена: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Проверка срока действия
    exp = payload.get("exp")
    if exp is not None:
        if datetime.now(timezone.utc).timestamp() > exp:
            raise HTTPException(
                status_code=401,
                detail="Срок действия токена истек",
                headers={
                    "WWW-Authenticate": 'Bearer error="invalid_token", error_description="Token has expired"'
                },
            )

    realm_access = payload.get("realm_access") or {}
    realm_roles = realm_access.get("roles") or []

    client_roles = []
    if settings.keycloak_client_id:
        res_access = payload.get("resource_access") or {}
        client_roles = (
            res_access.get(settings.keycloak_client_id) or {}
        ).get("roles") or []

    all_roles = set(realm_roles + client_roles)
    roles = [r for r in all_roles if r in ROLE_LEVELS]
    if not roles:
        roles = ["viewer"]

    return {
        "sub": str(payload.get("sub") or ""),
        "name": (
            payload.get("name")
            or payload.get("preferred_username")
            or payload.get("email")
            or "Unknown"
        ),
        "email": payload.get("email") or "",
        "provider": "keycloak",
        "roles": roles,
    }


async def get_authenticated_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
    settings: Settings | None = None,
) -> dict | None:
    """Извлекает пользователя из Bearer-токена или cookie-сессии."""
    if settings is None:
        settings = get_settings()

    if not settings.auth_enabled:
        return None

    # 1. Проверяем Bearer токен (credentials из HTTPBearer или из заголовка Authorization)
    raw_token = None
    if credentials and credentials.credentials:
        raw_token = credentials.credentials
    else:
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                raw_token = parts[1]

    if raw_token:
        return extract_user_from_token(raw_token, settings)

    # 2. Проверяем cookie сессии
    session_user = request.session.get("user")
    if session_user:
        return session_user

    return None


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    settings: Settings = Depends(get_settings),
) -> dict | None:
    """Проверяет авторизацию пользователя.

    Поддерживает:
    - Bearer токен в заголовке Authorization (для Postman, curl, Swagger UI)
    - Сессионную cookie (для веб-интерфейса)

    Если auth_enabled = False — возвращает None.
    Иначе возвращает словарь с данными пользователя или 401.
    """
    if not settings.auth_enabled:
        return None

    user = await get_authenticated_user(request, credentials, settings)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
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
        credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
        settings: Settings = Depends(get_settings),
    ) -> dict | None:
        if not settings.auth_enabled:
            return None
        user = await get_authenticated_user(request, credentials, settings)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if _user_role_level(user) < required:
            raise HTTPException(
                status_code=403,
                detail=f"Недостаточно прав: требуется роль '{min_role}' или выше.",
            )
        return user

    return checker
