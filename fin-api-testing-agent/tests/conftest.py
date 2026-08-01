import json
import pytest
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage


@pytest.fixture
def make_tool_message():
    def _factory(name, content, tool_call_id="call_abc"):
        return ToolMessage(
            tool_call_id=tool_call_id,
            content=json.dumps(content) if isinstance(content, dict) else str(content),
            name=name,
        )
    return _factory


@pytest.fixture
def sample_portfolio_data():
    return {
        "totalValue": 1500000,
        "totalInvested": 1200000,
        "totalGainLoss": 300000,
        "totalGainLossPercentage": 25.0,
        "dayChange": 12000,
        "dayChangePercentage": 0.81,
        "totalPortfolios": 2,
        "totalHoldings": 15,
        "portfolioBreakdown": [
            {
                "portfolioName": "Growth",
                "currentValue": 900000,
                "gainLossPercent": 30.0,
            },
        ],
        "bestPerformer": {"symbol": "RELIANCE", "changePercent": 3.5},
        "worstPerformer": {"symbol": "INFY", "changePercent": -1.2},
    }


@pytest.fixture
def mixed_message_list(make_tool_message, sample_portfolio_data):
    return [
        HumanMessage(content="Show my portfolio"),
        AIMessage(content="", additional_kwargs={"tool_calls": []}),
        make_tool_message("get_portfolio_summary", sample_portfolio_data),
        AIMessage(content="Here is your portfolio summary."),
    ]
