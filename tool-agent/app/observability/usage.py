from __future__ import annotations

from pydantic import BaseModel, Field


class LlmUsageRecord(BaseModel):
    name: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None
    latency_ms: int | None = None


class ToolUsageRecord(BaseModel):
    name: str
    tool_source: str
    duration_ms: int | None = None


class UsageLedger(BaseModel):
    llm_calls: list[LlmUsageRecord] = Field(default_factory=list)
    tool_calls: list[ToolUsageRecord] = Field(default_factory=list)

    def add_llm(self, record: LlmUsageRecord) -> None:
        self.llm_calls.append(record)

    def add_tool(self, record: ToolUsageRecord) -> None:
        self.tool_calls.append(record)

    def totals(self) -> dict[str, float | int]:
        prompt = sum(r.prompt_tokens for r in self.llm_calls)
        completion = sum(r.completion_tokens for r in self.llm_calls)
        total_tokens = sum(r.total_tokens for r in self.llm_calls)
        cost = sum(r.cost_usd or 0.0 for r in self.llm_calls)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total_tokens,
            "cost_usd": round(cost, 8),
            "llm_call_count": len(self.llm_calls),
            "tool_call_count": len(self.tool_calls),
        }

    def breakdown(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for r in self.llm_calls:
            rows.append({"kind": "llm", "name": r.name, "model": r.model, "tokens": r.total_tokens})
        for r in self.tool_calls:
            rows.append({"kind": "tool", "name": r.name, "source": r.tool_source})
        return rows
