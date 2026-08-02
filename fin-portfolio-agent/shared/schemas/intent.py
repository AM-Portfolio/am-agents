from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class WidgetId:
    """Deprecated Flutter widget ids. Chat path uses artifactType; kept for legacy formatters/tests."""

    TEXT_RESPONSE = "TEXT_RESPONSE"
    PORTFOLIO_SUMMARY = "PORTFOLIO_SUMMARY"
    HOLDINGS_TABLE = "HOLDINGS_TABLE"
    ALLOCATION_PIE = "ALLOCATION_PIE_CHART"
    TOP_MOVERS = "TOP_MOVERS"
    RECENT_ACTIVITY = "RECENT_ACTIVITY"
    BENCHMARK = "BENCHMARK_COMPARISON"
    ETF_ANALYSIS = "ETF_ANALYSIS"
    API_TEST_WIDGET = "API_TEST_WIDGET"
    ERROR = "ERROR"


class ChatRequest(BaseModel):
    message: str
    userId: str = ""
    sessionId: Optional[str] = None


class AiIntentResponse(BaseModel):
    """Chat response. UI maps artifactType → widget; agent does not own Flutter widget ids."""

    message: str
    artifactType: str = "text.v1"
    data: Optional[Any] = None
    sessionId: str
    toolsUsed: List[str] = Field(default_factory=list)
    traceId: str
    # Deprecated: kept optional for older clients until Flutter migrates.
    widgetId: Optional[str] = None
    widgetParams: Dict[str, Any] = Field(default_factory=dict)
