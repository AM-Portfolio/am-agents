from app.observability.usage import LlmUsageRecord, ToolUsageRecord, UsageLedger


def test_usage_ledger_totals():
    ledger = UsageLedger()
    ledger.add_llm(
        LlmUsageRecord(
            name="db-agent-intent",
            model="test-model",
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            cost_usd=0.0001,
        )
    )
    ledger.add_llm(
        LlmUsageRecord(
            name="db-agent-summary",
            model="test-model",
            prompt_tokens=50,
            completion_tokens=10,
            total_tokens=60,
            cost_usd=0.00005,
        )
    )
    ledger.add_tool(ToolUsageRecord(name="collection_info", tool_source="adapter", duration_ms=42))

    totals = ledger.totals()
    assert totals["prompt_tokens"] == 150
    assert totals["completion_tokens"] == 30
    assert totals["total_tokens"] == 180
    assert totals["llm_call_count"] == 2
    assert totals["tool_call_count"] == 1

    breakdown = ledger.breakdown()
    assert len(breakdown) == 3
    assert breakdown[0]["type"] == "llm"
    assert breakdown[2]["type"] == "tool"
    assert breakdown[2]["total_tokens"] == 0
