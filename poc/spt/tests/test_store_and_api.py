"""API / store smoke tests (no k6 required)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class StoreFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._td.name
        os.environ["SPT_STORE"] = "db"
        os.environ.pop("SPT_DATABASE_URL", None)
        # Reload settings / engine
        from app.config import settings

        settings.data_dir = self._td.name
        settings.spt_store = "db"
        settings.spt_database_url = None
        from app.db import engine as eng

        eng._engine = None
        eng._SessionLocal = None
        from app.db.engine import init_db

        init_db()

    def tearDown(self) -> None:
        from app.db.engine import dispose_engine

        dispose_engine()
        try:
            self._td.cleanup()
        except PermissionError:
            pass

    def test_save_list_get_run(self) -> None:
        from app.run_store import get_run, list_runs, save_run, slim_run_for_list

        saved = save_run(
            {
                "status": "passed",
                "passed": True,
                "config_name": "t",
                "service": "am-analysis",
                "environment": "dev",
                "api_summary": [{"api_id": "a", "checks_passed": True}],
                "payloads_used": {"bench_run": {"vus": 1, "iterations": 1}},
            }
        )
        self.assertTrue(saved.get("id"))
        rows, total = list_runs(limit=10)
        self.assertEqual(total, 1)
        self.assertEqual(slim_run_for_list(rows[0])["config_name"], "t")
        got = get_run(saved["id"])
        self.assertEqual(got["status"], "passed")

    def test_profile_crud(self) -> None:
        from app.run_store import delete_config, get_config, list_configs, save_config

        c = save_config(
            {
                "name": "p1",
                "service": "am-analysis",
                "audience": "agent",
                "payloads": {"bench_run": {"vus": 1, "iterations": 1}},
            }
        )
        self.assertTrue(get_config(c["id"]))
        self.assertEqual(len(list_configs(audience="agent")), 1)
        self.assertTrue(delete_config(c["id"]))

    def test_compare(self) -> None:
        from app.run_store import save_run
        from app.services import compare_runs

        a = save_run({"status": "passed", "p90_ms": 100, "fail_pct": 0.0, "config_name": "a"})
        b = save_run({"status": "passed", "p90_ms": 120, "fail_pct": 0.1, "config_name": "b"})
        cmp = compare_runs(a["id"], b["id"])
        self.assertTrue(cmp["ok"])
        self.assertAlmostEqual(cmp["deltas_b_minus_a"]["p90_ms"], 20)

    def test_migrate_json(self) -> None:
        from app.db.migrate_json import migrate_all, parity_check
        from app.stores import json_backend as jb

        jb.save_run({"id": "json-run-1", "status": "passed", "config_name": "from-json", "service": "am-analysis"})
        jb.save_config({"id": "json-cfg-1", "name": "from-json", "service": "am-analysis", "audience": "developer"})
        stats = migrate_all()
        self.assertGreaterEqual(stats["runs"], 1)
        self.assertGreaterEqual(stats["profiles"], 1)
        parity = parity_check(10)
        self.assertTrue(parity["ok"], parity)


class FastApiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._td.name
        os.environ["SPT_STORE"] = "db"
        os.environ["CATALOG_EXTERNAL_DIR"] = str(Path(__file__).resolve().parents[1] / "catalog")
        from app.config import settings

        settings.data_dir = self._td.name
        settings.spt_store = "db"
        settings.spt_database_url = None
        settings.spt_acl_required = False
        from app.db import engine as eng

        eng._engine = None
        eng._SessionLocal = None

    def tearDown(self) -> None:
        from app.db.engine import dispose_engine

        dispose_engine()
        try:
            self._td.cleanup()
        except PermissionError:
            pass

    def test_health_and_profiles(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            h = client.get("/health")
            self.assertEqual(h.status_code, 200)
            body = h.json()
            self.assertEqual(body.get("store"), "db")
            p = client.get("/api/profiles")
            self.assertEqual(p.status_code, 200)
            self.assertGreaterEqual(p.json().get("count", 0), 1)
            c = client.get("/api/configs")
            self.assertEqual(c.status_code, 200)


if __name__ == "__main__":
    unittest.main()
