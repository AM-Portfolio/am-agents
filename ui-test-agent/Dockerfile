# App layer — fast rebuild when only app/ or scripts/ change.
# Base (Playwright + tzdata + pip deps): ghcr.io/am-portfolio/am-ui-test-agent-base
ARG BASE_IMAGE=ghcr.io/am-portfolio/am-ui-test-agent-base:latest
FROM ${BASE_IMAGE}

COPY app/ app/
COPY scripts/ scripts/

EXPOSE 8130

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -f "http://localhost:${APP_PORT}/health" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8130"]
