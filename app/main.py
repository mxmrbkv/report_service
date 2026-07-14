"""Точка входа FastAPI-приложения."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from app.api.reports import router as reports_router
from app.core.config import Settings, get_settings

# --- structlog setup ---

_settings_for_logging = get_settings()
_log_level_num = getattr(__import__("logging"), _settings_for_logging.log_level.upper(), 20)

_processors: list = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]
if _settings_for_logging.json_logs:
    _processors.append(structlog.processors.JSONRenderer())
else:
    _processors.append(structlog.dev.ConsoleRenderer())

structlog.configure(
    processors=_processors,
    wrapper_class=structlog.make_filtering_bound_logger(_log_level_num),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("startup", host=settings.host, port=settings.port)
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Allure Report Service",
        description="Загрузка, генерация и хранение Allure-отчётов",
        version="1.0.0",
        lifespan=lifespan,
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Роутеры ---
    app.include_router(reports_router)

    # --- Статика: веб-интерфейс ---
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    # --- Раздача Allure-отчётов ---
    # URL:  /reports/{project}/index.html
    # Диск: data/reports/{project}/html/index.html
    reports_base = settings.reports_path

    @app.get("/reports/{project}/{file_path:path}", include_in_schema=False)
    async def serve_report(project: str, file_path: str):
        # Предотвращаем path traversal
        if ".." in file_path or ".." in project:
            raise HTTPException(status_code=400, detail="Недопустимый путь")

        full_path = reports_base / project / "html" / file_path
        if not full_path.is_file():
            raise HTTPException(status_code=404, detail="Файл отчёта не найден")

        return FileResponse(full_path)

    # --- Главная страница ---
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index():
        index_html = static_dir / "index.html"
        if index_html.exists():
            return FileResponse(index_html)
        return HTMLResponse("<h1>Report Service</h1>", status_code=200)

    # --- Health check ---
    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    return app


app = create_app()