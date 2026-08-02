FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/shared \
    APP_PORT=8080 \
    TZ=Asia/Kolkata

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY fin-portfolio-agent/requirements.docker.txt .
RUN pip install --no-cache-dir -r requirements.docker.txt

COPY fin-portfolio-agent/am_fin_portfolio_analysis/ am_fin_portfolio_analysis/
COPY fin-portfolio-agent/shared/ shared/
COPY fin-portfolio-agent/prompts/ prompts/

# Non-root (matches universal-chart runAsUser 1000)
RUN useradd -u 1000 -m appuser && chown -R appuser:appuser /app
USER 1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD curl -f "http://localhost:${APP_PORT}/health" || exit 1

CMD ["uvicorn", "am_fin_portfolio_analysis.api:app", "--host", "0.0.0.0", "--port", "8080"]
