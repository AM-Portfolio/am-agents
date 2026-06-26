from tools.qdrant.search.parse_rules import parse_rules


def test_parse_rules_list_collections():
    intent = parse_rules("list qdrant collections", tool_name="qdrant")
    assert intent is not None
    assert intent.operation == "list_collections"


def test_parse_rules_collection_info():
    intent = parse_rules("how many points in bug_memory collection", tool_name="qdrant")
    assert intent is not None
    assert intent.operation == "collection_info"
    assert intent.params["collection"] == "bug_memory"


def test_parse_rules_nl_search_maps_to_scroll():
    intent = parse_rules("search bug memory for login timeout", tool_name="qdrant")
    assert intent is not None
    assert intent.operation == "scroll"
    assert intent.params["collection"] == "bug_memory"
