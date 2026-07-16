"""Авторизация через Keycloak (OIDC authorization code flow)."""

from __future__ import annotations

import base64
import json
import secrets
import urllib.parse

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _decode_jwt_payload(token: str) -> dict:
    """Декодирует payload JWT без проверки подписи (для извлечения claims)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    payload_b64 = parts[1]
    # Добавляем padding если нужно
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    return json.loads(payload_bytes)


@router.get("/login", include_in_schema=False)
async def login(
    request: Request,
    next: str = "/",
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Перенаправляет на страницу авторизации Keycloak."""
    if not settings.auth_enabled:
        return RedirectResponse(url=next)

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = next

    params = {
        "client_id": settings.keycloak_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "scope": settings.oauth_scopes,
        "state": state,
    }
    authorize_url = f"{settings.keycloak_authorize_url}?{urllib.parse.urlencode(params)}"
    logger.info("keycloak_login_redirect", authorize_url=authorize_url)
    return RedirectResponse(url=authorize_url)


@router.get("/callback", include_in_schema=False)
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Обрабатывает callback: обмен кода на токен, получение профиля, запись в сессию."""
    if error:
        logger.warning("keycloak_callback_error", error=error)
        raise HTTPException(status_code=400, detail=f"Keycloak error: {error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    stored_state = request.session.get("oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    # --- Обмен кода на access_token ---
    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            settings.keycloak_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oauth_redirect_uri,
                "client_id": settings.keycloak_client_id,
                "client_secret": settings.keycloak_client_secret,
            },
            headers={"Accept": "application/json"},
        )

        if token_resp.status_code != 200:
            logger.error(
                "keycloak_token_exchange_failed",
                status=token_resp.status_code,
                body=token_resp.text,
            )
            raise HTTPException(
                status_code=400,
                detail="Failed to exchange authorization code for token",
            )

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="No access_token in Keycloak response",
            )

        # --- Декодируем id_token для получения профиля ---
        # Используем id_token вместо userinfo endpoint, чтобы избежать
        # проблем с несовпадением issuer при разделении external/internal URL.
        id_token = token_data.get("id_token")
        if id_token:
            user_info = _decode_jwt_payload(id_token)
        else:
            # Fallback: userinfo endpoint
            user_resp = await client.get(
                settings.keycloak_userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                logger.error(
                    "keycloak_userinfo_failed",
                    status=user_resp.status_code,
                    body=user_resp.text,
                )
                raise HTTPException(status_code=400, detail="Failed to fetch user info")
            user_info = user_resp.json()

    # --- Нормализуем профиль под единый формат ---
    user = {
        "sub": str(user_info.get("sub") or ""),
        "name": (
            user_info.get("name")
            or user_info.get("preferred_username")
            or user_info.get("email")
            or "Unknown"
        ),
        "email": user_info.get("email") or "",
        "provider": "keycloak",
    }

    request.session["user"] = user
    request.session.pop("oauth_state", None)

    next_url = request.session.pop("oauth_next", "/")
    logger.info("keycloak_login_success", user=user["name"], next=next_url)
    return RedirectResponse(url=next_url)


@router.get("/logout", include_in_schema=False)
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Очищает локальную сессию и перенаправляет на Keycloak end_session."""
    user = request.session.get("user")
    request.session.clear()

    if settings.auth_enabled:
        # Keycloak end_session_endpoint — завершает сессию и на стороне IdP
        params = {
            "client_id": settings.keycloak_client_id,
            "post_logout_redirect_uri": settings.post_logout_redirect_uri,
        }
        logout_url = f"{settings.keycloak_logout_url}?{urllib.parse.urlencode(params)}"
        logger.info("keycloak_logout_redirect", user=user.get("name") if user else None)
        return RedirectResponse(url=logout_url)

    return RedirectResponse(url="/")


@router.get(
    "/me",
    summary="Информация о текущем пользователе",
    response_description="Статус авторизации и профиль пользователя",
    responses={
        200: {
            "description": "Статус авторизации",
            "content": {
                "application/json": {
                    "examples": {
                        "authenticated": {
                            "summary": "Авторизован",
                            "value": {
                                "authenticated": True,
                                "auth_enabled": True,
                                "user": {
                                    "sub": "12345-678-90",
                                    "name": "Иван Иванов",
                                    "email": "ivan@example.com",
                                    "provider": "keycloak",
                                },
                            },
                        },
                        "not_authenticated": {
                            "summary": "Не авторизован",
                            "value": {
                                "authenticated": False,
                                "auth_enabled": True,
                                "user": None,
                            },
                        },
                        "auth_disabled": {
                            "summary": "Авторизация отключена",
                            "value": {
                                "authenticated": True,
                                "auth_enabled": False,
                                "user": None,
                            },
                        },
                    }
                }
            },
        }
    },
)
async def me(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Возвращает статус авторизации и профиль текущего пользователя.

    Используйте этот метод, чтобы проверить:
    - включена ли авторизация (`auth_enabled`)
    - авторизован ли текущий пользователь (`authenticated`)
    - профиль пользователя (`user`: `sub`, `name`, `email`, `provider`)
    """
    if not settings.auth_enabled:
        return {"authenticated": True, "user": None, "auth_enabled": False}

    user = request.session.get("user")
    if user:
        return {"authenticated": True, "user": user, "auth_enabled": True}
    return {"authenticated": False, "user": None, "auth_enabled": True}
