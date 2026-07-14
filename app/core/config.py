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

    # --- CORS ---
    cors_origins: str = "*"

    # --- Логирование ---
    log_level: str = "INFO"
    json_logs: bool = False

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
