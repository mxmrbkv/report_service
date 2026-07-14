"""Логика генерации Allure-отчётов через CLI subprocess."""

from __future__ import annotations

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
                self._extract_and_validate(zip_bytes, tmp_results)
            except InvalidArchiveError:
                raise

            # 2. Сливаем результаты в целевую директорию проекта
            project_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)
            added_count = self._merge_results(tmp_results, results_dir)

        logger.info(
            "results_merged",
            project=project_name,
            added_files=added_count,
            is_new_project=is_new_project,
        )

        # 3. Регенерируем HTML из всех накопленных результатов
        try:
            self._run_allure_generate(results_dir, html_dir)
        except (AllureGenerationError, AllureTimeoutError):
            raise

        # 4. Обновляем метаданные
        results_count = sum(1 for f in results_dir.rglob("*") if f.is_file())
        size_bytes = self._dir_size(html_dir)

        if is_new_project:
            meta = {
                "project": project_name,
                "url": f"/reports/{project_name}/index.html",
                "created_at": now_iso,
                "updated_at": now_iso,
                "size_bytes": size_bytes,
                "uploads_count": 1,
                "results_count": results_count,
            }
        else:
            existing_meta = json.loads(meta_file.read_text(encoding="utf-8"))
            existing_meta["updated_at"] = now_iso
            existing_meta["size_bytes"] = size_bytes
            existing_meta["uploads_count"] = existing_meta.get("uploads_count", 0) + 1
            existing_meta["results_count"] = results_count
            meta = existing_meta

        meta_file.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
        all_reports = self._scan_reports()
        all_reports.sort(
            key=lambda r: r.get("updated_at", r.get("created_at", "")),
            reverse=True,
        )

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

    async def get_report(self, project: str) -> dict | None:
        """Возвращает метаданные проекта или None."""
        meta_file = self._base_dir / project / "meta.json"
        if not meta_file.exists():
            return None
        return json.loads(meta_file.read_text(encoding="utf-8"))

    async def delete_report(self, project: str) -> bool:
        """Удаляет проект со всеми результатами. Возвращает True если удалён."""
        project_dir = self._base_dir / project
        if not project_dir.exists():
            return False
        shutil.rmtree(project_dir, ignore_errors=True)
        logger.info("project_deleted", project=project)
        return True

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
        """Сканирует файловую систему и собирает метаданные всех проектов."""
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