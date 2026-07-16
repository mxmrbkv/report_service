"""Конфигурация сервиса через pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, читаемые из переменных окружения / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Сеть ---
    host: str = "0.0.0.0"
    port: int = 8080

    # --- Ограничения ---
    max_upload_size_mb: int = 100
    allure_timeout_seconds: int = 300

    # --- Хранилище ---
    reports_dir: str = "./data/reports"
    data_dir: str = "./data"

    # --- CORS ---
    cors_origins: str = "*"

    # --- Логирование ---
    log_level: str = "INFO"
    json_logs: bool = False

    # --- Авторизация (Keycloak OIDC) ---
    auth_enabled: bool = False
    # Внешний URL Keycloak — для редиректов браузера (виден пользователю)
    keycloak_url: str = "http://localhost:8081"
    # Внутренний URL Keycloak — для server-to-server запросов (token exchange, userinfo).
    # По умолчанию совпадает с keycloak_url, но в Docker можно указать имя сервиса.
    keycloak_internal_url: str = ""
    keycloak_realm: str = "report-service"
    keycloak_client_id: str = ""
    keycloak_client_secret: str = ""
    session_secret: str = "change-me-in-production"

    # Публичный URL сервиса (для OAuth redirect_uri и post-logout redirect).
    # На локалке: http://localhost:8080, на проде: http://185.46.10.125:8080
    public_url: str = "http://localhost:8080"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def reports_path(self) -> Path:
        p = Path(self.reports_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def _keycloak_external_base(self) -> str:
        """Базовый URL Keycloak realm для редиректов браузера."""
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"

    @property
    def _keycloak_internal_base(self) -> str:
        """Базовый URL Keycloak realm для server-to-server запросов."""
        url = self.keycloak_internal_url or self.keycloak_url
        return f"{url}/realms/{self.keycloak_realm}"

    @property
    def keycloak_authorize_url(self) -> str:
        """Авторизация — внешний URL (редирект браузера)."""
        return f"{self._keycloak_external_base}/protocol/openid-connect/auth"

    @property
    def keycloak_token_url(self) -> str:
        """Token endpoint — внутренний URL (server-to-server)."""
        return f"{self._keycloak_internal_base}/protocol/openid-connect/token"

    @property
    def keycloak_userinfo_url(self) -> str:
        """Userinfo — внутренний URL (server-to-server)."""
        return f"{self._keycloak_internal_base}/protocol/openid-connect/userinfo"

    @property
    def keycloak_logout_url(self) -> str:
        """Logout — внешний URL (редирект браузера)."""
        return f"{self._keycloak_external_base}/protocol/openid-connect/logout"

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.public_url}/auth/callback"

    @property
    def post_logout_redirect_uri(self) -> str:
        return f"{self.public_url}/"

    @property
    def oauth_scopes(self) -> str:
        return "openid email profile"


@lru_cache
def get_settings() -> Settings:
    return Settings()
