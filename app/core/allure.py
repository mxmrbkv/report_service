"""Логика генерации Allure-отчётов через CLI subprocess."""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)

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
    """Управляет жизненным циклом отчётов: приём, накопление, генерация, удаление.

    Один проект = один отчёт. При повторной загрузке в тот же проект
    новые результаты добавляются к существующим, HTML регенерируется.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_dir = settings.reports_path
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  Публичные методы
    # ------------------------------------------------------------------ #

    async def upload_results(
        self,
        zip_bytes: bytes,
        project_name: str,
        build_id: str | None,
    ) -> dict:
        """Принимает ZIP, добавляет результаты к проекту, регенерирует отчёт.

        Если проект существует — новые файлы allure-results сливаются
        с уже имеющимися. Если нет — создаётся новый проект.

        Raises:
            InvalidArchiveError: архив битый или без allure-results/.
            AllureGenerationError: allure generate упал.
            AllureTimeoutError: превышён таймаут.
        """
        project_dir = self._base_dir / project_name
        results_dir = project_dir / "allure-results"
        html_dir = project_dir / "html"
        meta_file = project_dir / "meta.json"

        is_new_project = not meta_file.exists()
        now_iso = datetime.now(timezone.utc).isoformat()

        logger.info(
            "upload_results_start",
            project=project_name,
            zip_size=len(zip_bytes),
            is_new_project=is_new_project,
        )

        # 1. Распаковываем и валидируем ZIP во временную директорию
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_results = Path(tmp_dir) / "allure-results"
            try:
                await asyncio.to_thread(self._extract_and_validate, zip_bytes, tmp_results)
            except InvalidArchiveError:
                raise

            # 2. Сливаем результаты в целевую директорию проекта
            project_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)
            added_count = await asyncio.to_thread(self._merge_results, tmp_results, results_dir)

        logger.info(
            "results_merged",
            project=project_name,
            added_files=added_count,
            is_new_project=is_new_project,
        )

        # 3. Регенерируем HTML из всех накопленных результатов
        try:
            await self._run_allure_generate(results_dir, html_dir)
        except (AllureGenerationError, AllureTimeoutError):
            raise

        # 4. Обновляем метаданные
        results_count = sum(1 for f in results_dir.rglob("*") if f.is_file())
        size_bytes = self._dir_size(html_dir)

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        from app.models.db import Project, AsyncSessionLocal
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            stmt = select(Project).where(Project.name == project_name)
            result = await session.execute(stmt)
            project_obj = result.scalar_one_or_none()

            if project_obj is None:
                project_obj = Project(
                    name=project_name,
                    created_at=now,
                    updated_at=now,
                    size_bytes=size_bytes,
                    uploads_count=1,
                    results_count=results_count
                )
                session.add(project_obj)
            else:
                project_obj.updated_at = now
                project_obj.size_bytes = size_bytes
                project_obj.uploads_count += 1
                project_obj.results_count = results_count

            await session.commit()
            
            meta = {
                "project": project_name,
                "url": f"/reports/{project_name}/index.html",
                "created_at": project_obj.created_at.isoformat(),
                "updated_at": project_obj.updated_at.isoformat(),
                "size_bytes": size_bytes,
                "uploads_count": project_obj.uploads_count,
                "results_count": results_count,
            }

        logger.info(
            "upload_results_done",
            project=project_name,
            results_count=results_count,
            uploads_count=meta["uploads_count"],
            size=size_bytes,
        )
        return meta

    async def list_reports(self, page: int = 1, page_size: int = 20) -> dict:
        """Возвращает список проектов с пагинацией, отсортированный по дате обновления (новые сверху)."""
        from app.models.db import Project, AsyncSessionLocal
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as session:
            count_stmt = select(func.count(Project.name))
            total = await session.scalar(count_stmt) or 0

            stmt = select(Project).order_by(Project.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
            result = await session.execute(stmt)
            projects = result.scalars().all()

        items = []
        for p in projects:
            items.append({
                "project": p.name,
                "url": f"/reports/{p.name}/index.html",
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
                "size_bytes": p.size_bytes,
                "uploads_count": p.uploads_count,
                "results_count": p.results_count,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_report(self, project: str) -> dict | None:
        """Возвращает метаданные проекта или None."""
        from app.models.db import Project, AsyncSessionLocal
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            stmt = select(Project).where(Project.name == project)
            result = await session.execute(stmt)
            p = result.scalar_one_or_none()

        if not p:
            return None

        return {
            "project": p.name,
            "url": f"/reports/{p.name}/index.html",
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
            "size_bytes": p.size_bytes,
            "uploads_count": p.uploads_count,
            "results_count": p.results_count,
        }

    async def delete_report(self, project: str) -> bool:
        """Удаляет проект со всеми результатами. Возвращает True если удалён."""
        from app.models.db import Project, AsyncSessionLocal
        from sqlalchemy import delete

        async with AsyncSessionLocal() as session:
            stmt = delete(Project).where(Project.name == project)
            result = await session.execute(stmt)
            await session.commit()
            deleted = result.rowcount > 0

        project_dir = self._base_dir / project
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
            
        if deleted:
            logger.info("project_deleted", project=project)
        return deleted

    def get_report_html_dir(self, project: str) -> Path | None:
        """Возвращает путь к HTML-директории проекта или None."""
        html_dir = self._base_dir / project / "html"
        return html_dir if html_dir.exists() else None

    # ------------------------------------------------------------------ #
    #  Приватные методы
    # ------------------------------------------------------------------ #

    def _merge_results(self, src: Path, dest: Path) -> int:
        """Копирует файлы результатов из *src* в *dest*, накапливая.

        Файлы в allure-results имеют UUID-имена, поэтому коллизий нет.
        Возвращает количество скопированных файлов.
        """
        count = 0
        for item in src.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(src)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1
        return count

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

        names = zf.namelist()
        allure_prefix = None
        for name in names:
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

        dest.mkdir(parents=True, exist_ok=True)
        prefix_len = len(allure_prefix)
        for name in names:
            if not name.startswith(allure_prefix):
                continue
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

    async def _run_allure_generate(self, results_dir: Path, html_dir: Path) -> None:
        """Вызывает `allure generate <results> -o <html>` через asyncio subprocess."""
        import asyncio

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
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=self._settings.allure_timeout_seconds
                )
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise AllureTimeoutError(
                    f"Генерация отчёта превысила таймаут {self._settings.allure_timeout_seconds} сек."
                ) from exc
                
        except FileNotFoundError as exc:
            raise AllureGenerationError(
                "Allure CLI не найден. Убедитесь, что 'allure' установлен и доступен в PATH."
            ) from exc

        if process.returncode != 0:
            err_text = stderr.decode(errors='ignore').strip() if stderr else "неизвестная ошибка"
            logger.error("allure_generate_failed", returncode=process.returncode, stderr=err_text)
            raise AllureGenerationError(f"Allure CLI завершился с ошибкой: {err_text}")

        logger.info("allure_generate_done", html_dir=str(html_dir))



    @staticmethod
    def _dir_size(path: Path) -> int:
        """Суммарный размер всех файлов в директории."""
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())