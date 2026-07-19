"""Tiny stdlib HTTP server exposing /metrics (and /healthz) for Temporal workers."""

from __future__ import annotations

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from am_support_agent.observability.metrics import get_shared_metrics

LOG = logging.getLogger("support_agent.metrics_server")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 — silence access logs
        return

    def do_GET(self) -> None:  # noqa: N802
        path = (self.path or "/").split("?", 1)[0]
        if path in {"/healthz", "/readyz", "/health"}:
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/metrics":
            body = get_shared_metrics().render().encode("utf-8")
            self.send_response(200)
            self.send_header(
                "Content-Type", "text/plain; version=0.0.4; charset=utf-8"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def start_metrics_server(*, port: int | None = None, host: str = "0.0.0.0") -> int:
    """Start a daemon metrics HTTP server. Returns the bound port (0 = disabled)."""
    if port is None:
        raw = (
            os.getenv("SUPPORT_AGENT_METRICS_PORT")
            or os.getenv("SUPPORT_AGENT_WORKER_METRICS_PORT")
            or "8091"
        ).strip()
        try:
            port = int(raw)
        except ValueError:
            port = 0
    if port <= 0:
        LOG.info("worker metrics HTTP disabled (port=%s)", port)
        return 0

    server = ThreadingHTTPServer((host, port), _Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="support-agent-metrics",
        daemon=True,
    )
    thread.start()
    LOG.info("worker metrics listening on %s:%s (/metrics)", host, port)
    return port


__all__ = ["start_metrics_server"]
