"""Pydantic-схемы для авторизации и токенов."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """Запрос на получение токена по логину и паролю."""

    username: str = Field(
        ...,
        description="Имя пользователя Keycloak",
        examples=["admin"],
    )
    password: str = Field(
        ...,
        description="Пароль пользователя",
        examples=["admin"],
    )
    client_id: str | None = Field(
        default=None,
        description="Client ID (если не передан, берётся из конфигурации сервиса)",
    )
    client_secret: str | None = Field(
        default=None,
        description="Client Secret (если требуется)",
    )
    scope: str | None = Field(
        default=None,
        description="OAuth2 scopes (по умолчанию: openid email profile)",
    )


class RefreshTokenRequest(BaseModel):
    """Запрос на обновление access токена по refresh токену."""

    refresh_token: str = Field(
        ...,
        description="Refresh токен, полученный при первичной авторизации",
    )
    client_id: str | None = Field(
        default=None,
        description="Client ID (если не передан, берётся из конфигурации сервиса)",
    )
    client_secret: str | None = Field(
        default=None,
        description="Client Secret (если требуется)",
    )


class UserProfile(BaseModel):
    """Профиль пользователя."""

    sub: str = Field("", description="Идентификатор пользователя (subject)")
    name: str = Field("", description="Отображаемое имя пользователя")
    email: str = Field("", description="Email пользователя")
    provider: str = Field("keycloak", description="Провайдер авторизации")
    roles: list[str] = Field(
        default_factory=list,
        description="Роли пользователя (viewer, reporter, admin)",
    )


class TokenResponse(BaseModel):
    """Ответ с токенами авторизации."""

    access_token: str = Field(
        ...,
        description="JWT Access Token. Скопируйте его и вставьте в Postman (Bearer Token) или в кнопку Authorize в Swagger UI",
    )
    token_type: str = Field(
        default="Bearer",
        description="Тип токена (Bearer)",
    )
    expires_in: int = Field(
        ...,
        description="Время жизни access токена в секундах",
    )
    refresh_token: str | None = Field(
        default=None,
        description="Refresh токен для продления сессии",
    )
    refresh_expires_in: int | None = Field(
        default=None,
        description="Время жизни refresh токена в секундах",
    )
    scope: str | None = Field(
        default=None,
        description="Выданные OAuth2 scopes",
    )
    user: UserProfile | None = Field(
        default=None,
        description="Данные пользователя, извлеченные из токена",
    )
