"""Авторизация через Keycloak (OIDC authorization code flow и direct grant)."""

from __future__ import annotations

import secrets
import urllib.parse

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import (
    decode_jwt_payload,
    extract_user_from_token,
    get_authenticated_user,
    http_bearer,
)
from app.core.config import Settings, get_settings
from app.models.auth import RefreshTokenRequest, TokenRequest, TokenResponse, UserProfile

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _decode_jwt_payload(token: str) -> dict:
    """Декодирует payload JWT без проверки подписи (для извлечения claims)."""
    return decode_jwt_payload(token)


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
    # Извлекаем realm-роли из claim realm_access.roles (настроено в Keycloak
    # client scope "roles": mapper "realm roles" с id.token.claim=true).
    realm_access = user_info.get("realm_access") or {}
    roles = [
        r for r in (realm_access.get("roles") or [])
        if r in ("viewer", "reporter", "admin")
    ]
    if not roles:
        roles = ["viewer"]

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
        "roles": roles,
    }

    request.session["user"] = user
    if id_token:
        request.session["id_token"] = id_token
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
    id_token = request.session.get("id_token")
    request.session.clear()

    if settings.auth_enabled:
        # Keycloak end_session_endpoint — завершает сессию и на стороне IdP.
        # id_token_hint помогает Keycloak однозначно определить сессию для завершения.
        params = {
            "client_id": settings.keycloak_client_id,
            "post_logout_redirect_uri": settings.post_logout_redirect_uri,
        }
        if id_token:
            params["id_token_hint"] = id_token
        logout_url = f"{settings.keycloak_logout_url}?{urllib.parse.urlencode(params)}"
        logger.info("keycloak_logout_redirect", user=user.get("name") if user else None)
        return RedirectResponse(url=logout_url)

    return RedirectResponse(url="/")


async def _post_keycloak_token(data: dict, settings: Settings) -> dict:
    """Отправляет запрос к Keycloak Token endpoint с fallback-адресом при необходимости."""
    urls_to_try = [settings.keycloak_token_url]
    if settings.keycloak_internal_url and settings.keycloak_url:
        external_token_url = f"{settings._keycloak_external_base}/protocol/openid-connect/token"
        if external_token_url not in urls_to_try:
            urls_to_try.append(external_token_url)

    last_error: Exception | None = None
    token_resp: httpx.Response | None = None

    for url in urls_to_try:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url,
                    data=data,
                    headers={"Accept": "application/json"},
                )
                token_resp = resp
                break
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.warning("keycloak_token_connect_failed", url=url, error=str(exc))
            last_error = exc
            continue

    if token_resp is None:
        logger.error("keycloak_unavailable", error=str(last_error))
        raise HTTPException(
            status_code=503,
            detail=f"Не удалось подключиться к Keycloak ({settings.keycloak_url}). Убедитесь, что сервис Keycloak запущен.",
        )

    if token_resp.status_code != 200:
        error_detail = "Ошибка авторизации Keycloak"
        try:
            err_data = token_resp.json()
            error_detail = err_data.get("error_description") or err_data.get("error") or error_detail
        except Exception:
            error_detail = token_resp.text or error_detail

        logger.warning(
            "keycloak_token_rejected",
            status=token_resp.status_code,
            detail=error_detail,
        )
        raise HTTPException(
            status_code=token_resp.status_code,
            detail=error_detail,
        )

    return token_resp.json()


async def _create_token_response(
    token_data: dict,
    settings: Settings,
) -> TokenResponse:
    access_token = token_data.get("access_token", "")
    user_info = None
    if access_token:
        try:
            user_dict = extract_user_from_token(access_token, settings)
            user_info = UserProfile(**user_dict)
        except Exception:
            user_info = None

    return TokenResponse(
        access_token=access_token,
        token_type=token_data.get("token_type", "Bearer"),
        expires_in=int(token_data.get("expires_in", 300)),
        refresh_token=token_data.get("refresh_token"),
        refresh_expires_in=token_data.get("refresh_expires_in"),
        scope=token_data.get("scope"),
        user=user_info,
    )


async def _handle_token_request(
    request: Request,
    body: TokenRequest | None,
    settings: Settings,
) -> TokenResponse:
    if not settings.auth_enabled:
        return TokenResponse(
            access_token="dev-token-auth-disabled",
            token_type="Bearer",
            expires_in=86400,
            scope="openid email profile",
            user=UserProfile(
                sub="dev-user",
                name="Developer (auth disabled)",
                email="dev@example.com",
                roles=["admin"],
            ),
        )

    username = None
    password = None
    client_id = None
    client_secret = None
    scope = None

    if body is not None:
        username = body.username
        password = body.password
        client_id = body.client_id
        client_secret = body.client_secret
        scope = body.scope
    else:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        client_id = form.get("client_id")
        client_secret = form.get("client_secret")
        scope = form.get("scope")

    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="Необходимо указать username и password",
        )

    data = {
        "grant_type": "password",
        "client_id": client_id or settings.keycloak_client_id,
        "username": str(username),
        "password": str(password),
        "scope": scope or settings.oauth_scopes,
    }
    secret = client_secret or settings.keycloak_client_secret
    if secret:
        data["client_secret"] = secret

    token_data = await _post_keycloak_token(data, settings)
    return await _create_token_response(token_data, settings)


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Получить токен авторизации (JWT Bearer Token)",
    description=(
        "Авторизация по логину и паролю через Keycloak (Resource Owner Password Credentials flow).\n\n"
        "Возвращает `access_token`, который можно использовать:\n"
        "- В **Postman**: вкладка **Authorization** -> **Bearer Token**\n"
        "- В **Swagger UI**: кнопка **Authorize** в правом верхнем углу (вставьте токен)\n"
        "- В заголовке запроса: `Authorization: Bearer <access_token>`"
    ),
    responses={
        200: {"description": "Успешная авторизация, выдан access_token"},
        400: {"description": "Неверные учетные данные или параметры запроса"},
        503: {"description": "Keycloak недоступен"},
    },
)
async def token(
    request: Request,
    body: TokenRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    return await _handle_token_request(request, body, settings)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Авторизация и получение токена (алиас /auth/token)",
    description="Алиас для `/auth/token`. Позволяет авторизоваться по логину и паролю и получить Bearer токен для Postman.",
    responses={
        200: {"description": "Успешная авторизация, выдан access_token"},
        400: {"description": "Неверные учетные данные или параметры запроса"},
        503: {"description": "Keycloak недоступен"},
    },
)
async def login_api(
    request: Request,
    body: TokenRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    return await _handle_token_request(request, body, settings)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Обновить access-токен по refresh-токену",
    description="Обновляет истекший access_token, используя выданный ранее refresh_token.",
    responses={
        200: {"description": "Токен успешно обновлен"},
        400: {"description": "Некорректный или истекший refresh_token"},
        503: {"description": "Keycloak недоступен"},
    },
)
async def refresh_token(
    request: Request,
    body: RefreshTokenRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    if not settings.auth_enabled:
        return TokenResponse(
            access_token="dev-token-refreshed",
            token_type="Bearer",
            expires_in=86400,
            scope="openid email profile",
            user=UserProfile(
                sub="dev-user",
                name="Developer (auth disabled)",
                email="dev@example.com",
                roles=["admin"],
            ),
        )

    raw_refresh = None
    client_id = None
    client_secret = None

    if body is not None:
        raw_refresh = body.refresh_token
        client_id = body.client_id
        client_secret = body.client_secret
    else:
        form = await request.form()
        raw_refresh = form.get("refresh_token")
        client_id = form.get("client_id")
        client_secret = form.get("client_secret")

    if not raw_refresh:
        raise HTTPException(status_code=400, detail="Необходимо указать refresh_token")

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id or settings.keycloak_client_id,
        "refresh_token": str(raw_refresh),
    }
    secret = client_secret or settings.keycloak_client_secret
    if secret:
        data["client_secret"] = secret

    token_data = await _post_keycloak_token(data, settings)
    return await _create_token_response(token_data, settings)


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
                                    "roles": ["admin"],
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
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Возвращает статус авторизации и профиль текущего пользователя.

    Поддерживает:
    - Авторизацию через Bearer-токен (в Postman / curl / Swagger UI)
    - Сессионную cookie (в веб-интерфейсе)
    """
    if not settings.auth_enabled:
        return {"authenticated": True, "user": None, "auth_enabled": False}

    user = await get_authenticated_user(request, credentials, settings)
    if user:
        return {"authenticated": True, "user": user, "auth_enabled": True}
    return {"authenticated": False, "user": None, "auth_enabled": True}
