"""REST API роуты для управления отчётами."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_report_manager, require_auth
from app.core.allure import (
    AllureGenerationError,
    AllureTimeoutError,
    InvalidArchiveError,
    ReportManager,
)
from app.core.config import Settings, get_settings
from app.models.report import (
    ErrorResponse,
    ReportDeleteResponse,
    ReportListResponse,
    ReportMeta,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ---------------------------------------------------------------------- #
#  POST /api/reports — загрузка результатов в проект
# ---------------------------------------------------------------------- #

@router.post(
    "",
    response_model=ReportMeta,
    status_code=201,
    summary="Загрузить ZIP и добавить результаты в проект",
    responses={
        400: {"description": "Некорректный архив или нет allure-results/"},
        413: {"description": "Размер файла превышает лимит"},
        500: {"description": "Внутренняя ошибка при генерации"},
    },
)
async def upload_results(
    file: UploadFile = File(..., description="ZIP-архив с allure-results/"),
    project_name: str = Form("default", description="Имя проекта"),
    manager: ReportManager = Depends(get_report_manager),
    settings: Settings = Depends(get_settings),
    _user=Depends(require_auth),
) -> ReportMeta:
    # --- Проверка размера ---
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Размер файла ({len(content)} байт) превышает лимит "
            f"({settings.max_upload_size_mb} МБ).",
        )

    # --- Проверка расширения ---
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Ожидается файл с расширением .zip")

    # --- Генерация ---
    try:
        meta = await manager.upload_results(content, project_name, build_id=None)
    except InvalidArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AllureTimeoutError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AllureGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ReportMeta(**meta)


# ---------------------------------------------------------------------- #
#  GET /api/reports — список проектов с пагинацией
# ---------------------------------------------------------------------- #

@router.get(
    "",
    response_model=ReportListResponse,
    summary="Получить список всех проектов",
    description=(
        "Возвращает список проектов с пагинацией, "
        "отсортированный по дате последнего обновления (новые сверху).\n\n"
        "Параметры пагинации:\n"
        "- `page` — номер страницы (начиная с 1)\n"
        "- `page_size` — размер страницы (1–100, по умолчанию 20)\n"
    ),
    response_description="Список проектов с пагинацией",
    responses={
        401: {"description": "Не авторизован", "model": ErrorResponse},
    },
)
async def list_reports(
    page: int = 1,
    page_size: int = 20,
    manager: ReportManager = Depends(get_report_manager),
    _user=Depends(require_auth),
) -> ReportListResponse:
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    data = await manager.list_reports(page=page, page_size=page_size)
    return ReportListResponse(**data)


# ---------------------------------------------------------------------- #
#  GET /api/reports/{project} — метаданные проекта
# ---------------------------------------------------------------------- #

@router.get(
    "/{project}",
    response_model=ReportMeta,
    summary="Получить метаданные проекта",
    responses={404: {"description": "Проект не найден"}},
)
async def get_report(
    project: str,
    manager: ReportManager = Depends(get_report_manager),
    _user=Depends(require_auth),
) -> ReportMeta:
    meta = await manager.get_report(project)
    if meta is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return ReportMeta(**meta)


# ---------------------------------------------------------------------- #
#  DELETE /api/reports/{project} — удаление проекта
# ---------------------------------------------------------------------- #

@router.delete(
    "/{project}",
    response_model=ReportDeleteResponse,
    summary="Удалить проект и все его результаты",
    responses={404: {"description": "Проект не найден"}},
)
async def delete_report(
    project: str,
    manager: ReportManager = Depends(get_report_manager),
    _user=Depends(require_auth),
) -> ReportDeleteResponse:
    deleted = await manager.delete_report(project)
    if not deleted:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return ReportDeleteResponse(deleted=True, project=project)
