#!/usr/bin/env bash
#
# Скрипт деплоя Report Service на сервере.
# Запускается на самом сервере после git pull.
#
# Использование:
#   ./deploy.sh
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "=== Report Service Deploy ==="
echo "Directory: $APP_DIR"
echo ""

# 1. Проверяем наличие .env.prod
if [ ! -f .env.prod ]; then
    echo "ERROR: .env.prod not found. Create it from .env.example first."
    exit 1
fi

# 2. Проверяем наличие allure архива
if [ ! -f allure-2.44.0.tgz ]; then
    echo "ERROR: allure-2.44.0.tgz not found in project root."
    exit 1
fi

# 3. Останавливаем старый контейнер (если есть)
echo "Stopping existing container..."
docker compose -f docker-compose.prod.yml down || true

# 4. Пересобираем и запускаем
echo "Building and starting..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

# 5. Ждём и проверяем health
echo "Waiting for service to start..."
sleep 5

MAX_RETRIES=12
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
        echo ""
        echo "=== Deploy successful! ==="
        echo "Service: http://0.0.0.0:8080"
        echo "Health:  http://localhost:8080/health"
        echo ""
        docker compose -f docker-compose.prod.yml ps
        exit 0
    fi
    echo "  Waiting... ($((RETRY + 1))/$MAX_RETRIES)"
    sleep 5
    RETRY=$((RETRY + 1))
done

echo ""
echo "ERROR: Service did not become healthy within 60 seconds."
echo "Logs:"
docker compose -f docker-compose.prod.yml logs --tail=50
exit 1
