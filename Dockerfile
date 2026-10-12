FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CHROMIUM_PATH=/usr/bin/chromium

WORKDIR /app

# Chromium 供 DrissionPage 使用；文泉驿字体保证中文网页和截图正常显示。
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        fonts-wqy-zenhei \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/data/backups /app/data/logs /app/data/snapshots /app/data/.locks \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app

# 非 root 用户运行 Chromium 和 Web 服务，降低容器权限风险。
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
