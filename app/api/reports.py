"""REST API роуты для управления отчётами."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse

from app.api.deps import get_report_manager
from app.core.allure import (
    AllureGenerationError,
    AllureTimeoutError,
    InvalidArchiveError,
    ReportManager,
)
from app.core.config import Settings, get_settings
from app.models.report import ReportDeleteResponse, ReportListResponse, ReportMeta

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ---------------------------------------------------------------------- #
#  POST /api/reports — загрузка и генерация
# ---------------------------------------------------------------------- #

@router.post(
    "",
    response_model=ReportMeta,
    status_code=201,
    summary="Загрузить ZIP и сгенерировать Allure-отчёт",
    responses={
        400: {"description": "Некорректный архив или нет allure-results/"},
        413: {"description": "Размер файла превышает лимит"},
        500: {"description": "Внутренняя ошибка при генерации"},
    },
)
async def create_report(
    request: Request,
    file: UploadFile = File(..., description="ZIP-архив с allure-results/"),
    project_name: str = Form("default"),
    build_id: str | None = Form(None),
    manager: ReportManager = Depends(get_report_manager),
    settings: Settings = Depends(get_settings),
) -> ReportMeta:
    # --- Проверка размера ---
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Размер файла ({len(content)} байт) превышает лимит "
            f"({settings.max_upload_size_mb} МБ).",
        )

    # --- Проверка content-type / расширения ---
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Ожидается файл с расширением .zip")

    # --- Генерация ---
    try:
        meta = await manager.create_report(content, project_name, build_id)
    except InvalidArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AllureTimeoutError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AllureGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ReportMeta(**meta)


# ---------------------------------------------------------------------- #
#  GET /api/reports — список с пагинацией
# ---------------------------------------------------------------------- #

@router.get(
    "",
    response_model=ReportListResponse,
    summary="Получить список всех отчётов",
)
async def list_reports(
    page: int = 1,
    page_size: int = 20,
    manager: ReportManager = Depends(get_report_manager),
) -> ReportListResponse:
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    data = await manager.list_reports(page=page, page_size=page_size)
    return ReportListResponse(**data)


# ---------------------------------------------------------------------- #
#  GET /api/reports/{project}/{id} — метаданные одного отчёта
# ---------------------------------------------------------------------- #

@router.get(
    "/{project}/{report_id}",
    response_model=ReportMeta,
    summary="Получить метаданные конкретного отчёта",
    responses={404: {"description": "Отчёт не найден"}},
)
async def get_report(
    project: str,
    report_id: str,
    manager: ReportManager = Depends(get_report_manager),
) -> ReportMeta:
    meta = await manager.get_report(project, report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return ReportMeta(**meta)


# ---------------------------------------------------------------------- #
#  DELETE /api/reports/{project}/{id} — удаление
# ---------------------------------------------------------------------- #

@router.delete(
    "/{project}/{report_id}",
    response_model=ReportDeleteResponse,
    summary="Удалить отчёт",
    responses={404: {"description": "Отчёт не найден"}},
)
async def delete_report(
    project: str,
    report_id: str,
    manager: ReportManager = Depends(get_report_manager),
) -> ReportDeleteResponse:
    deleted = await manager.delete_report(project, report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return ReportDeleteResponse(deleted=True, id=report_id, project=project)
