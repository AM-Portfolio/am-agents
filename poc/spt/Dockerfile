FROM python:3.12-slim

WORKDIR /app

# Offline install — no PyPI or apt during build (cluster/VPS egress is unreliable)
COPY requirements.txt .
COPY vendor/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

COPY vendor/bin/k6 /usr/local/bin/k6
RUN chmod +x /usr/local/bin/k6

COPY app/ app/
COPY catalog/ catalog/
COPY k6/ k6/
COPY playwright/ playwright/

ENV APP_PORT=8150
ENV K6_BIN=/usr/local/bin/k6
ENV DATA_DIR=/data
ENV ROOT_PATH=/spt-poc
ENV PYTHONUNBUFFERED=1

EXPOSE 8150

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8150/health')" || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}"]
