from pathlib import Path

import pytest

from app.target_loader import get_target_config, load_env_file, resolve_env_refs


def test_resolve_env_refs():
    env = {"AM_API_BASE_URL": "https://am.asrax.in"}
    assert resolve_env_refs("${AM_API_BASE_URL}/path", env) == "https://am.asrax.in/path"


def test_get_target_config_preprod(tmp_path: Path):
    env_file = tmp_path / ".env.preprod"
    env_file.write_text("AM_API_BASE_URL=https://am.asrax.in\n", encoding="utf-8")
    targets = tmp_path / "targets.preprod.json"
    targets.write_text(
        """
        {
          "module": "modern-ui",
          "environment": "preprod",
          "default_target": "main",
          "targets": {
            "main": {
              "base_url": "${AM_API_BASE_URL}",
              "ui_mode": "main",
              "profile": "AUTH_FLOW_MAIN"
            }
          }
        }
        """,
        encoding="utf-8",
    )
    cfg = get_target_config(targets, env_file=env_file)
    assert cfg.base_url == "https://am.asrax.in"
    assert cfg.ui_mode == "main"
    assert cfg.profile == "AUTH_FLOW_MAIN"


def test_load_env_file_skips_comments(tmp_path: Path):
    f = tmp_path / ".env"
    f.write_text("# comment\nFOO=bar\n", encoding="utf-8")
    assert load_env_file(f)["FOO"] == "bar"


def test_get_target_config_missing_key(tmp_path: Path):
    targets = tmp_path / "t.json"
    targets.write_text('{"targets": {"main": {"base_url": "${MISSING}"}}}', encoding="utf-8")
    with pytest.raises(KeyError):
        get_target_config(targets, target_name="main")
