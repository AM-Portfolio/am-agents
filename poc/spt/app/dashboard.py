from __future__ import annotations

from pathlib import Path

from app.config import settings

_TEMPLATE = Path(__file__).resolve().parent / "templates" / "portal.html"
_STATIC = Path(__file__).resolve().parent / "static"
_JS_FILES = (
    "util.js",
    "shell.js",
    "inspector.js",
    "run-detail.js",
    "execute.js",
    # Specs tab (split for maintainability — order matters)
    "specs/state.js",
    "specs/service.js",
    "specs/swagger-loader.js",
    "specs/payloads.js",
    "specs/swagger-try.js",
    "specs/overview.js",
    "specs/page.js",
)


def render_portal() -> str:
    """Serve a self-contained /ui page (CSS/JS embedded) so Traefik/root_path cannot 404 assets."""
    html = _TEMPLATE.read_text(encoding="utf-8")
    root = settings.root_path.rstrip("/") if settings.root_path else ""
    static_base = f"{root}/static"
    css = (_STATIC / "css" / "portal.css").read_text(encoding="utf-8")
    js_parts = [(_STATIC / "js" / name).read_text(encoding="utf-8") for name in _JS_FILES]
    js = "\n".join(js_parts)
    return (
        html.replace("__PORTAL_CSS__", f"<style>\n{css}\n</style>")
        .replace("__PORTAL_JS__", f"<script>\n{js}\n</script>")
        .replace("__ROOT_PATH__", root)
        .replace("__STATIC_BASE__", static_base)
        .replace("__GRAFANA_URL__", settings.grafana_public_url.rstrip("/"))
        .replace("__MINIO_CONSOLE__", settings.minio_public_console_url.rstrip("/"))
    )
