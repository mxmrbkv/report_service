# Allure Report Service

Внутренний сервис для загрузки, генерации и просмотра Allure-отчётов.
QA-инженеры и CI/CD загружают ZIP-архив с результатами тестов (`allure-results/`),
сервис автоматически генерирует HTML-отчёт через Allure CLI и возвращает
постоянную ссылку для просмотра в браузере.

## Возможности

- 📦 **Загрузка ZIP** с результатами тестов через REST API или веб-интерфейс
- ⚡ **Автоматическая генерация** HTML-отчёта через `allure generate`
- 🔗 **Постоянные ссылки** вида `/reports/{project}/{id}/index.html`
- 📋 **REST API** для списка, метаданных и удаления отчётов
- 🌐 **Веб-интерфейс** с drag-and-drop загрузкой и таблицей отчётов
- 🐳 **Docker + docker-compose** — поднимается одной командой
- 📊 **Пагинация** списка отчётов (по 20 на странице)
- 🔒 **Валидация** архивов и обработка ошибок (400, 404, 413, 500)

## Быстрый старт

### Через docker-compose

```bash
# 1. Клонировать репозиторий и перейти в директорию
cd allure-service

# 2. (Опционально) Настроить переменные окружения
cp .env.example .env
# Отредактировать .env при необходимости

# 3. Запустить
docker-compose up -d --build

# 4. Проверить
curl http://localhost:8080/health
# {"status":"ok"}
```

Сервис будет доступен на http://localhost:8080

### Локально (без Docker)

> Требуется установленный [Allure CLI](https://allurereport.org/docs/install/)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

## Структура проекта

```
allure-service/
├── app/
│   ├── main.py              # FastAPI приложение, раздача статики отчётов
│   ├── api/
│   │   ├── reports.py       # REST API роуты /api/reports
│   │   └── deps.py          # Dependency injection
│   ├── core/
│   │   ├── config.py        # Настройки (pydantic-settings)
│   │   └── allure.py        # Логика генерации отчётов (subprocess)
│   ├── models/
│   │   └── report.py        # Pydantic-схемы
│   └── static/
│       └── index.html       # Веб-интерфейс
├── data/
│   └── reports/             # Хранилище отчётов (project/id/html/...)
├── Dockerfile               # Multi-stage: сборка зависимостей + runtime с Allure CLI
├── docker-compose.yml       # Сервис на порту 8080, volume для data/
├── requirements.txt
├── .env.example             # Пример конфигурации
└── README.md
```

## API

### POST /api/reports — Загрузить и сгенерировать отчёт

**Request:** `multipart/form-data`

| Поле         | Тип   | Обязательно | Описание                          |
|--------------|-------|-------------|-----------------------------------|
| `file`       | File  | ✅          | ZIP-архив с `allure-results/`     |
| `project_name` | str | ❌          | Имя проекта (по умолчанию `default`) |
| `build_id`   | str   | ❌          | Идентификатор сборки (авто-UUID)  |

**Response 201:**
```json
{
  "id": "a1b2c3d4-...",
  "project": "my-project",
  "url": "/reports/my-project/a1b2c3d4-.../index.html",
  "created_at": "2026-07-14T12:00:00+00:00",
  "size_bytes": 1234567
}
```

**Ошибки:**
- `400` — не ZIP, битый архив, нет `allure-results/`
- `413` — превышен лимит размера (100 МБ по умолчанию)
- `500` — ошибка Allure CLI или таймаут

### GET /api/reports — Список отчётов

**Query параметры:**
| Параметр    | По умолчанию | Описание                |
|-------------|-------------|-------------------------|
| `page`      | 1           | Номер страницы          |
| `page_size` | 20          | Размер страницы (1–100) |

**Response 200:**
```json
{
  "items": [
    {
      "id": "a1b2c3d4-...",
      "project": "my-project",
      "url": "/reports/my-project/a1b2c3d4-.../index.html",
      "created_at": "2026-07-14T12:00:00+00:00",
      "size_bytes": 1234567
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

### GET /api/reports/{project}/{id} — Метаданные отчёта

**Response 200:**
```json
{
  "id": "a1b2c3d4-...",
  "project": "my-project",
  "url": "/reports/my-project/a1b2c3d4-.../index.html",
  "created_at": "2026-07-14T12:00:00+00:00",
  "size_bytes": 1234567
}
```
**Ошибки:** `404` — отчёт не найден

### DELETE /api/reports/{project}/{id} — Удалить отчёт

**Response 200:**
```json
{
  "deleted": true,
  "id": "a1b2c3d4-...",
  "project": "my-project"
}
```
**Ошибки:** `404` — отчёт не найден

### GET /reports/{project}/{id}/... — Просмотр отчёта

Отдаёт статические файлы сгенерированного Allure HTML-отчёта.
Главная страница: `/reports/{project}/{id}/index.html`

### GET /health — Health check

```json
{"status": "ok"}
```

## Примеры curl-запросов

### Загрузить отчёт

```bash
# Базовая загрузка
curl -X POST http://localhost:8080/api/reports \
  -F "file=@allure-results.zip" \
  -F "project_name=my-project"

# С указанием build_id
curl -X POST http://localhost:8080/api/reports \
  -F "file=@allure-results.zip" \
  -F "project_name=checkout" \
  -F "build_id=build-42"

# Ответ:
# {
#   "id": "a1b2c3d4-e5f6-...",
#   "project": "my-project",
#   "url": "/reports/my-project/a1b2c3d4-e5f6-.../index.html",
#   "created_at": "2026-07-14T12:00:00+00:00",
#   "size_bytes": 1234567
# }
```

### Получить список отчётов

```bash
# Первая страница
curl http://localhost:8080/api/reports

# Вторая страница, 10 на странице
curl "http://localhost:8080/api/reports?page=2&page_size=10"
```

### Получить метаданные конкретного отчёта

```bash
curl http://localhost:8080/api/reports/my-project/a1b2c3d4-e5f6-...
```

### Удалить отчёт

```bash
curl -X DELETE http://localhost:8080/api/reports/my-project/a1b2c3d4-e5f6-...
```

### Открыть отчёт в браузере

```
http://localhost:8080/reports/my-project/a1b2c3d4-e5f6-.../index.html
```

## Конфигурация

Все настройки задаются через переменные окружения (файл `.env`):

| Переменная               | По умолчанию      | Описание                              |
|--------------------------|-------------------|---------------------------------------|
| `HOST`                   | `0.0.0.0`         | Адрес привязки                        |
| `PORT`                   | `8080`            | Порт                                  |
| `MAX_UPLOAD_SIZE_MB`     | `100`             | Макс. размер ZIP (МБ)                 |
| `ALLURE_TIMEOUT_SECONDS` | `300`             | Таймаут генерации (сек)               |
| `REPORTS_DIR`            | `./data/reports`  | Папка хранения отчётов                |
| `CORS_ORIGINS`           | `*`               | Разрешённые CORS-источники (через `,`)|
| `LOG_LEVEL`              | `INFO`            | Уровень логирования                   |
| `JSON_LOGS`              | `false`           | JSON-формат логов                     |

## Структура хранения

```
data/reports/
├── default/
│   ├── a1b2c3d4-.../
│   │   ├── allure-results/    # Сырые результаты (из ZIP)
│   │   ├── html/              # Сгенерированный Allure HTML
│   │   └── meta.json          # Метаданные отчёта
│   └── e5f6g7h8-.../
│       ├── ...
└── my-project/
    └── ...
```

## CI/CD интеграция

Пример загрузки отчёта из CI-пайплайна:

```bash
# Упаковать allure-results в ZIP
zip -r allure-results.zip allure-results/

# Загрузить в сервис
RESPONSE=$(curl -s -X POST http://allure-service:8080/api/reports \
  -F "file=@allure-results.zip" \
  -F "project_name=$CI_PROJECT_NAME" \
  -F "build_id=$CI_PIPELINE_ID")

# Извлечь URL
REPORT_URL=$(echo "$RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin)['url'])")
echo "Allure report: http://allure-service:8080$REPORT_URL"
```

## Технологии

- **Backend:** Python 3.12 / FastAPI
- **Генерация:** Allure CLI (subprocess)
- **Хранение:** Файловая система
- **Контейнеризация:** Docker (multi-stage) + docker-compose
- **Фронтенд:** Vanilla HTML/CSS/JS
- **Логирование:** structlog