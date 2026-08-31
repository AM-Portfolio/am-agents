"""Wave C: keyword router forces tools for data questions."""
from shared.agents.data_question_router import is_greeting, match_data_question


def test_greeting_not_routed():
    assert is_greeting("hey")
    assert is_greeting("Hello there")
    assert match_data_question("hey") is None


def test_portfolio_summary_routed():
    m = match_data_question("Show my portfolio summary")
    assert m is not None
    assert m[0] == "get_portfolio_summary"


def test_holdings_routed():
    m = match_data_question("List all my holdings")
    assert m == ("get_holdings_list", {})


def test_recent_activity_routed():
    m = match_data_question("Show my recent activity")
    assert m is not None
    assert m[0] == "get_recent_activity"
    assert m[1].get("limit") == 20


def test_sector_allocation_routed():
    m = match_data_question("What is my sector allocation?")
    assert m == ("get_sector_allocation", {})


def test_market_movers_not_portfolio_movers():
    m = match_data_question("What are today's Nifty gainers?")
    assert m is not None
    assert m[0] == "get_market_movers"
    assert m[1]["indexSymbol"] == "NIFTY 50"
    assert m[1]["type"] == "GAINERS"


def test_market_movers_losers():
    m = match_data_question("Show Nifty losers today")
    assert m is not None
    assert m[0] == "get_market_movers"
    assert m[1]["type"] == "LOSERS"


def test_portfolio_movers_routed():
    m = match_data_question("What are my best performers?")
    assert m is not None
    assert m[0] == "get_top_movers"


def test_indices_routed():
    m = match_data_question("Where is Nifty?")
    assert m is not None
    assert m[0] == "get_indices_data"


def test_stock_quote_extracts_symbol():
    m = match_data_question("What is RELIANCE trading at?")
    assert m is not None
    assert m[0] == "get_stock_quote"
    assert m[1]["symbol"] == "RELIANCE"


def test_stock_quote_reliance_stock_price_phrasing():
    """Regression: 'reliance stock price?' must not capture symbol=STOCK."""
    m = match_data_question("reliance stock price?")
    assert m is not None
    assert m[0] == "get_stock_quote"
    assert m[1]["symbol"] == "RELIANCE"


def test_stock_quote_does_not_capture_stopword_stock():
    assert match_data_question("stock price?") is None


def test_search_instruments_routed():
    m = match_data_question("Find Tata stocks")
    assert m is not None
    assert m[0] == "search_instruments"
    assert m[1]["query"].lower() == "tata"


def test_basket_static_reply():
    from shared.agents.data_question_router import match_static_reply, BASKET_UNAVAILABLE_REPLY

    assert match_static_reply("List my investment baskets") == BASKET_UNAVAILABLE_REPLY
    assert match_static_reply("Show portfolio summary") is None
