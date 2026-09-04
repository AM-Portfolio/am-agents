"""Tests for MCP URL resolution (in-cluster vs ingress-style bases)."""
import os

import pytest

from shared.mcp_ext.urls import (
    normalize_mcp_base_url,
    resolve_mcp_health_url,
    resolve_mcp_sse_url,
)


def test_in_cluster_sse_url():
  base = "http://am-mcp-server.am-apps-prod.svc.cluster.local:8080"
  assert resolve_mcp_sse_url(base) == f"{base}/sse"


def test_ingress_style_sse_url():
  base = "https://am.asrax.in/mcp"
  assert resolve_mcp_sse_url(base) == "https://am.asrax.in/mcp/sse"


def test_normalize_strips_sse_suffix():
  assert normalize_mcp_base_url("http://host:8080/sse") == "http://host:8080"


def test_health_url_in_cluster():
  base = "http://am-mcp-server.am-apps-prod.svc.cluster.local:8080"
  assert resolve_mcp_health_url(base) == f"{base}/actuator/health"


def test_health_url_ingress_style_strips_mcp():
  base = "https://am.asrax.in/mcp"
  assert resolve_mcp_health_url(base) == "https://am.asrax.in/actuator/health"
