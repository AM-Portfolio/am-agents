from tools.kafka.search.convention import extract_topic, normalize_topic, resolve_topic_param


def test_normalize_legacy_alias():
    assert normalize_topic("am-trade-executions") == "am-trade-update"


def test_extract_from_nl_hint():
    assert extract_topic("kafka consumer lag on am-user-watching") == "am-user-watching"


def test_resolve_topic_param_from_query():
    params, topic, method = resolve_topic_param({}, "describe kafka topic am-stock-price-update")
    assert topic == "am-stock-price-update"
    assert method == "convention"


def test_extract_topic_ignores_read_only_modifier():
    assert extract_topic("List kafka topics read-only. backend kafka") is None
