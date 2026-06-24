from tools.mongodb.search.parse_rules import parse_rules


def test_parse_rules_portfolio_find_by_id():
    pid = "163d0143-4fcb-480c-ac20-622f14e0e293"
    intent = parse_rules(
        f"find mongo portfolio {pid}",
        tool_name="mongodb",
        backend_hint="mongodb",
    )
    assert intent is not None
    assert intent.backend == "mongodb"
    assert intent.operation == "find"
    assert intent.params["entity"] == "portfolio"
    assert intent.params["id"] == pid


def test_parse_rules_count_securities_market_data():
    intent = parse_rules(
        "how many securities in market_data mongodb database",
        tool_name="mongodb",
        backend_hint="mongodb",
    )
    assert intent is not None
    assert intent.operation == "count_documents"
    assert intent.params["database"] == "market_data"
    assert intent.params["collection"] == "securities"


def test_parse_rules_list_collections_am_trade():
    intent = parse_rules(
        "list mongo collections in am-trade database",
        tool_name="mongodb",
        backend_hint="mongodb",
    )
    assert intent is not None
    assert intent.operation == "list_collections"
    assert intent.params["database"] == "am-trade"


def test_parse_rules_list_trades_am_trade():
    intent = parse_rules(
        "list trades in am-trade mongo database",
        tool_name="mongodb",
        backend_hint="mongodb",
    )
    assert intent is not None
    assert intent.operation == "find"
    assert intent.params["database"] == "am-trade"
    assert intent.params["collection"] == "trades"


def test_parse_rules_list_databases():
    intent = parse_rules(
        "list mongo databases",
        tool_name="mongodb",
        backend_hint="mongodb",
    )
    assert intent is not None
    assert intent.backend == "mongodb"
    assert intent.operation == "list_databases"
    assert intent.params == {}
