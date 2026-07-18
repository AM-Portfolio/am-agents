# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY registry ./registry
COPY src ./src

RUN pip install --no-cache-dir ".[temporal,postgres]" \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin support-agent

ENV SUPPORT_AGENT_GATEWAY_HOST=0.0.0.0
ENV SUPPORT_AGENT_GATEWAY_PORT=8091
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8091
USER 10001
CMD ["am-support-agent-gateway"]
