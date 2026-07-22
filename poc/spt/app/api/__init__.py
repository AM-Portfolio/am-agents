"""API routers — routes still live in main.py for now; this package is the target split."""

from __future__ import annotations

# Future layout (incremental):
#   app/api/runs.py
#   app/api/configs.py
#   app/api/payloads.py
#   app/api/catalog.py
#   app/api/platform.py
# Wired via include_router from app.main once extracted.
