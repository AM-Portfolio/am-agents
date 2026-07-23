"""Unit tests for schema-first payload builder (no network)."""
from __future__ import annotations

from app.payload_builder import build_request_from_operation, example_from_param, example_from_schema
from app.openapi_overlay import apply_overlay_to_document


SAMPLE_DOC = {
    "openapi": "3.0.1",
    "paths": {
        "/v1/demo/{type}/items": {
            "get": {
                "operationId": "listItems",
                "parameters": [
                    {
                        "name": "type",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "enum": ["PORTFOLIO", "BASKET"]},
                    },
                    {
                        "name": "timeFrame",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["1D", "1M"], "default": "1D"},
                    },
                    {
                        "name": "id",
                        "in": "query",
                        "schema": {"type": "string", "example": "pf-demo-001"},
                    },
                ],
            }
        },
        "/v1/demo/create": {
            "post": {
                "operationId": "createItem",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "example": "alpha"},
                                    "when": {"type": "string", "format": "date-time"},
                                },
                            }
                        }
                    }
                },
            }
        },
    },
}


def test_enum_and_example_from_schema():
    assert example_from_schema({"enum": ["1D", "1M"]}) == "1D"
    assert example_from_schema({"type": "string", "format": "uuid"}).startswith("0000")
    assert example_from_schema({"type": "string", "format": "date-time"}).endswith("Z")


def test_build_uses_enum_not_service_hardcodes():
    built = build_request_from_operation(SAMPLE_DOC, operation_id="listItems")
    assert built["ok"] is True
    assert built["source"] in ("example", "schema")
    req = built["request"]
    assert req["path_params"]["type"] == "PORTFOLIO"
    assert req["query"]["timeFrame"] == "1D"
    assert req["query"]["id"] == "pf-demo-001"


def test_build_body_from_schema():
    built = build_request_from_operation(SAMPLE_DOC, operation_id="createItem")
    assert built["ok"] is True
    body = built["request"]["body"]
    assert body["name"] == "alpha"
    assert "T" in body["when"]


def test_overlay_wins():
    overlay = {
        "operations": {
            "listItems": {
                "path_params": {"type": "BASKET"},
                "query": {"timeFrame": "1M", "id": "custom"},
                "source": "set",
            }
        }
    }
    doc = apply_overlay_to_document(SAMPLE_DOC, overlay)
    built = build_request_from_operation(
        doc,
        operation_id="listItems",
        overlay_entry=overlay["operations"]["listItems"],
    )
    assert built["source"] == "set"
    assert built["request"]["path_params"]["type"] == "BASKET"
    assert built["request"]["query"]["timeFrame"] == "1M"


def test_param_pagination_only_heuristic():
    assert example_from_param({"name": "page", "in": "query", "schema": {"type": "integer"}}) == 0
    assert example_from_param({"name": "size", "in": "query", "schema": {"type": "integer"}}) == 10
    # no hard-coded timeframe without enum
    assert example_from_param({"name": "timeFrame", "in": "query", "schema": {"type": "string"}}) in (
        "example",
        None,
        "",
    )
