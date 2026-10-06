import base64
import json
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import app
from app.models.db import init_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Инициализирует базу данных перед тестами."""
    await init_db()


def create_jwt_token(
    sub: str = "user-123",
    name: str = "Test User",
    email: str = "test@example.com",
    roles: list[str] = None,
    expires_in: int = 3600,
) -> str:
    """Создает валидный JWT токен без подписи для тестов."""
    if roles is None:
        roles = ["viewer"]
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "name": name,
        "email": email,
        "realm_access": {"roles": roles},
        "exp": int(time.time()) + expires_in,
    }
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("ascii").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{h_b64}.{p_b64}.mocksignature"


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_unauthenticated_request_fails():
    """Без токена защищенный эндпоинт возвращает 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/reports")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_bearer_token_authenticated_request():
    """С валидным Bearer токеном GET /api/reports возвращает 200."""
    token = create_jwt_token(roles=["viewer"])
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/reports", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_me_with_bearer_token():
    """GET /auth/me возвращает профиль пользователя из Bearer-токена."""
    token = create_jwt_token(
        sub="admin-id",
        name="Admin User",
        email="admin@example.com",
        roles=["admin"],
    )
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["user"]["sub"] == "admin-id"
    assert data["user"]["name"] == "Admin User"
    assert data["user"]["email"] == "admin@example.com"
    assert "admin" in data["user"]["roles"]


@pytest.mark.asyncio
async def test_expired_bearer_token():
    """Истекший токен возвращает 401."""
    expired_token = create_jwt_token(expires_in=-3600)
    headers = {"Authorization": f"Bearer {expired_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/reports", headers=headers)
    assert response.status_code == 401
    assert "истек" in response.json()["detail"].lower() or "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_role_authorization_permissions():
    """Проверка уровней ролей: viewer < reporter < admin."""
    viewer_token = create_jwt_token(roles=["viewer"])
    reporter_token = create_jwt_token(roles=["reporter"])

    # Viewer не может удалить проект (нужен admin) -> 403
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(
            "/api/reports/nonexistent",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
    assert resp.status_code == 403

    # Reporter не может удалить проект -> 403
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(
            "/api/reports/nonexistent",
            headers={"Authorization": f"Bearer {reporter_token}"},
        )
    assert resp.status_code == 403

    # Admin может вызвать delete (получит 404 так как проект не существует, но пройдет авторизацию)
    admin_token = create_jwt_token(roles=["admin"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete(
            "/api/reports/nonexistent",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_auth_token_success():
    """POST /auth/token возвращает access_token при успешном ответе Keycloak."""
    mock_token = create_jwt_token(
        sub="user-42",
        name="Keycloak Admin",
        roles=["admin"],
    )
    mock_data = {
        "access_token": mock_token,
        "token_type": "Bearer",
        "expires_in": 300,
        "refresh_token": "mock-refresh-token",
        "refresh_expires_in": 1800,
        "scope": "openid email profile",
    }

    with patch("app.api.auth._post_keycloak_token", new_callable=AsyncMock, return_value=mock_data):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/auth/token",
                json={"username": "admin", "password": "correct-password"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == mock_token
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 300
    assert data["user"]["name"] == "Keycloak Admin"
    assert "admin" in data["user"]["roles"]


@pytest.mark.asyncio
async def test_post_auth_login_alias_success():
    """POST /auth/login работает аналогично /auth/token."""
    mock_token = create_jwt_token(
        sub="user-42",
        name="Keycloak Reporter",
        roles=["reporter"],
    )
    mock_data = {
        "access_token": mock_token,
        "token_type": "Bearer",
        "expires_in": 300,
        "refresh_token": "mock-refresh-token",
        "scope": "openid email profile",
    }

    with patch("app.api.auth._post_keycloak_token", new_callable=AsyncMock, return_value=mock_data):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/auth/login",
                json={"username": "reporter", "password": "password123"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == mock_token
    assert "reporter" in data["user"]["roles"]


@pytest.mark.asyncio
async def test_post_auth_refresh_success():
    """POST /auth/refresh обновляет access токен."""
    new_mock_token = create_jwt_token(sub="user-42", roles=["reporter"])
    mock_data = {
        "access_token": new_mock_token,
        "token_type": "Bearer",
        "expires_in": 300,
        "refresh_token": "new-refresh-token",
        "scope": "openid email profile",
    }

    with patch("app.api.auth._post_keycloak_token", new_callable=AsyncMock, return_value=mock_data):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/auth/refresh",
                json={"refresh_token": "old-refresh-token"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == new_mock_token


@pytest.mark.asyncio
async def test_post_auth_token_invalid_credentials():
    """POST /auth/token возвращает ошибку 400 при неверном логине/пароле."""
    from fastapi import HTTPException
    with patch("app.api.auth._post_keycloak_token", new_callable=AsyncMock, side_effect=HTTPException(status_code=400, detail="Invalid user credentials")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/auth/token",
                json={"username": "wrong-user", "password": "wrong-password"},
            )

    assert response.status_code == 400
    assert "Invalid user credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_openapi_schema_contains_bearer_auth_and_routes():
    """Проверка генерации OpenAPI схемы: наличие BearerAuth, /auth/token, /auth/login, /auth/refresh."""
    schema = app.openapi()
    assert "components" in schema
    assert "securitySchemes" in schema["components"]
    assert "BearerAuth" in schema["components"]["securitySchemes"]
    assert schema["components"]["securitySchemes"]["BearerAuth"]["type"] == "http"
    assert schema["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"

    paths = schema["paths"]
    assert "/auth/token" in paths
    assert "post" in paths["/auth/token"]
    assert "/auth/login" in paths
    assert "post" in paths["/auth/login"]
    assert "/auth/refresh" in paths
    assert "post" in paths["/auth/refresh"]
    assert "/auth/me" in paths
    assert "get" in paths["/auth/me"]

    # Проверяем, что эндпоинты отчетов требуют BearerAuth
    assert "security" in paths["/api/reports"]["get"]
    assert any("BearerAuth" in s for s in paths["/api/reports"]["get"]["security"])


@pytest.mark.asyncio
async def test_auth_disabled_mode():
    """При выключенной авторизации (auth_enabled=False) эндпоинты доступны без токена."""
    mock_settings = Settings(auth_enabled=False)
    app.dependency_overrides[get_settings] = lambda: mock_settings
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # GET /api/reports без токена возвращает 200
            resp_reports = await ac.get("/api/reports")
            assert resp_reports.status_code == 200

            # GET /auth/me возвращает auth_enabled: False
            resp_me = await ac.get("/auth/me")
            assert resp_me.status_code == 200
            assert resp_me.json()["auth_enabled"] is False

            # POST /auth/token возвращает dev-токен
            resp_token = await ac.post("/auth/token", json={"username": "dev", "password": "dev"})
            assert resp_token.status_code == 200
            assert "access_token" in resp_token.json()
    finally:
        app.dependency_overrides.clear()

