# ============================================================
# Stage 1: Сборка зависимостей Python
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.12-slim AS runtime

# Устанавливаем JDK (Allure требует Java) и скачиваем Allure CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        default-jdk-headless \
        ca-certificates && \
    curl -fsSL https://github.com/allure-framework/allure2/releases/download/2.44.0/allure-2.44.0.tgz \
        -o /tmp/allure.tgz && \
    tar -xzf /tmp/allure.tgz -C /opt/ && \
    ln -s /opt/allure-2.44.0/bin/allure /usr/local/bin/allure && \
    rm /tmp/allure.tgz && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Проверяем установку
RUN allure --version

WORKDIR /app

# Копируем зависимости из builder
COPY --from=builder /install /usr/local

# Копируем код приложения
COPY . .

# Создаём директорию для отчётов
RUN mkdir -p /app/data/reports

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]