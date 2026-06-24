from tools._shared.grafana_time import grafana_time_to_rfc3339


def test_grafana_time_relative():
    assert grafana_time_to_rfc3339("now").endswith("Z")
    assert grafana_time_to_rfc3339("now-1h").startswith("20")
