from pydantic import BaseModel
from typing import Dict, Any, List, Optional


class WidgetId:
    PORTFOLIO_SUMMARY  = "PORTFOLIO_SUMMARY"
    HOLDINGS_TABLE     = "HOLDINGS_TABLE"
    ALLOCATION_PIE     = "ALLOCATION_PIE_CHART"
    TOP_MOVERS         = "TOP_MOVERS"
    RECENT_ACTIVITY    = "RECENT_ACTIVITY"
    ETF_ANALYSIS       = "ETF_ANALYSIS"
    BENCHMARK          = "BENCHMARK_COMPARISON"
    API_TEST_WIDGET    = "API_TEST_WIDGET"
    TEXT_RESPONSE      = "TEXT_RESPONSE"
    ERROR              = "ERROR"


class ChatRequest(BaseModel):
    message: str
    userId: str
    sessionId: Optional[str] = None  # None = new session, server generates UUID


class AiIntentResponse(BaseModel):
    message: str
    widgetId: str
    widgetParams: Dict[str, Any] = {}
    sessionId: str
    toolsUsed: List[str] = []
    traceId: str
