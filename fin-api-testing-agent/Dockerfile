FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/shared \
    APP_PORT=8102 \
    TZ=Asia/Kolkata

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY am_fin_api_testing/ am_fin_api_testing/
COPY shared/ shared/

EXPOSE 8102

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD curl -f "http://localhost:${APP_PORT}/health" || exit 1

CMD ["uvicorn", "am_fin_api_testing.api:app", "--host", "0.0.0.0", "--port", "8102"]
