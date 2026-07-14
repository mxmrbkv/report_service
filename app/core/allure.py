"""Логика генерации Allure-отчётов через CLI subprocess."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)

# Имя папки с сырыми результатами внутри ZIP
ALLURE_RESULTS_DIR_NAME = "allure-results"


class AllureError(Exception):
    """Базовая ошибка при генерации отчёта."""


class InvalidArchiveError(AllureError):
    """ZIP-архив некорректен или не содержит allure-results/."""


class AllureGenerationError(AllureError):
    """Allure CLI завершился с ненулевым кодом."""


class AllureTimeoutError(AllureError):
    """Превышён таймаут генерации отчёта."""


class ReportManager:
    """Управляет жизненным циклом отчётов: приём, генерация, удаление, листинг."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_dir = settings.reports_path
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  Публичные методы
    # ------------------------------------------------------------------ #

    async def create_report(
        self,
        zip_bytes: bytes,
        project_name: str,
        build_id: str | None,
    ) -> dict:
        """Принимает ZIP, генерирует отчёт, возвращает метаданные.

        Raises:
            InvalidArchiveError: архив битый или без allure-results/.
            AllureGenerationError: allure generate упал.
            AllureTimeoutError: превышён таймаут.
        """
        report_id = build_id or str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        project_dir = self._base_dir / project_name
        report_dir = project_dir / report_id
        report_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "create_report_start",
            report_id=report_id,
            project=project_name,
            zip_size=len(zip_bytes),
        )

        # 1. Распаковываем и валидируем ZIP
        results_dir = report_dir / "allure-results"
        try:
            self._extract_and_validate(zip_bytes, results_dir)
        except InvalidArchiveError:
            shutil.rmtree(report_dir, ignore_errors=True)
            raise

        # 2. Генерируем HTML через Allure CLI
        html_dir = report_dir / "html"
        try:
            self._run_allure_generate(results_dir, html_dir)
        except (AllureGenerationError, AllureTimeoutError):
            shutil.rmtree(report_dir, ignore_errors=True)
            raise

        # 3. Сохраняем метаданные
        size_bytes = self._dir_size(html_dir)
        meta = {
            "id": report_id,
            "project": project_name,
            "url": f"/reports/{project_name}/{report_id}/index.html",
            "created_at": created_at,
            "size_bytes": size_bytes,
        }
        meta_file = report_dir / "meta.json"
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("create_report_done", report_id=report_id, project=project_name, size=size_bytes)
        return meta

    async def list_reports(self, page: int = 1, page_size: int = 20) -> dict:
        """Возвращает список отчётов с пагинацией, отсортированный по дате (новые сверху)."""
        all_reports = self._scan_reports()
        all_reports.sort(key=lambda r: r["created_at"], reverse=True)

        total = len(all_reports)
        start = (page - 1) * page_size
        end = start + page_size
        items = all_reports[start:end]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_report(self, project: str, report_id: str) -> dict | None:
        """Возвращает метаданные конкретного отчёта или None."""
        meta_file = self._base_dir / project / report_id / "meta.json"
        if not meta_file.exists():
            return None
        return json.loads(meta_file.read_text(encoding="utf-8"))

    async def delete_report(self, project: str, report_id: str) -> bool:
        """Удаляет отчёт с диска. Возвращает True если удалён."""
        report_dir = self._base_dir / project / report_id
        if not report_dir.exists():
            return False
        shutil.rmtree(report_dir, ignore_errors=True)
        logger.info("report_deleted", report_id=report_id, project=project)
        return True

    def get_report_html_dir(self, project: str, report_id: str) -> Path | None:
        """Возвращает путь к HTML-директории отчёта или None."""
        html_dir = self._base_dir / project / report_id / "html"
        return html_dir if html_dir.exists() else None

    # ------------------------------------------------------------------ #
    #  Приватные методы
    # ------------------------------------------------------------------ #

    def _extract_and_validate(self, zip_bytes: bytes, dest: Path) -> None:
        """Распаковывает ZIP в *dest* и проверяет наличие allure-results/.

        Поддерживает два варианта структуры ZIP:
          1. allure-results/ прямо в корне архива.
          2. Произвольная вложенность — ищем папку allure-results/.
        """
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as exc:
            raise InvalidArchiveError("Файл не является корректным ZIP-архивом") from exc

        bad = zf.testzip()
        if bad is not None:
            raise InvalidArchiveError(f"Архив содержит повреждённый файл: {bad}")

        # Ищем allure-results внутри архива
        names = zf.namelist()
        allure_prefix = None
        for name in names:
            # Нормализуем путь
            parts = name.split("/")
            for i, part in enumerate(parts):
                if part == ALLURE_RESULTS_DIR_NAME:
                    allure_prefix = "/".join(parts[: i + 1])
                    break
            if allure_prefix:
                break

        if not allure_prefix:
            raise InvalidArchiveError(
                "В архиве не найдена папка 'allure-results'. "
                "Убедитесь, что ZIP содержит директорию allure-results/ с результатами тестов."
            )

        # Распаковываем только содержимое allure-results/
        dest.mkdir(parents=True, exist_ok=True)
        prefix_len = len(allure_prefix)
        for name in names:
            if not name.startswith(allure_prefix):
                continue
            # Относительный путь внутри allure-results/
            rel = name[prefix_len:].lstrip("/")
            if not rel:
                continue
            target = dest / rel
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        logger.debug("zip_extracted", dest=str(dest), file_count=len(names))

    def _run_allure_generate(self, results_dir: Path, html_dir: Path) -> None:
        """Вызывает `allure generate <results> -o <html>` через subprocess."""
        import subprocess

        cmd = [
            "allure",
            "generate",
            str(results_dir),
            "-o",
            str(html_dir),
            "--clean",
        ]
        logger.info("allure_generate_start", cmd=" ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._settings.allure_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AllureTimeoutError(
                f"Генерация отчёта превысила таймаут {self._settings.allure_timeout_seconds} сек."
            ) from exc
        except FileNotFoundError as exc:
            raise AllureGenerationError(
                "Allure CLI не найден. Убедитесь, что 'allure' установлен и доступен в PATH."
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip() or "неизвестная ошибка"
            logger.error("allure_generate_failed", returncode=result.returncode, stderr=stderr)
            raise AllureGenerationError(f"Allure CLI завершился с ошибкой: {stderr}")

        logger.info("allure_generate_done", html_dir=str(html_dir))

    def _scan_reports(self) -> list[dict]:
        """Сканирует файловую систему и собирает метаданные всех отчётов."""
        reports: list[dict] = []
        for meta_file in self._base_dir.rglob("meta.json"):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                reports.append(meta)
            except (json.JSONDecodeError, OSError):
                logger.warning("meta_read_failed", path=str(meta_file))
                continue
        return reports

    @staticmethod
    def _dir_size(path: Path) -> int:
        """Суммарный размер всех файлов в директории."""
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
