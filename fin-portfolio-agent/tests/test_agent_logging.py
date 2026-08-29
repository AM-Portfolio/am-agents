import json
import logging

from shared.context.request_context import session_id_var, trace_id_var, user_id_var
from shared.observability.agent_log import log_agent_event
from shared.observability.log_events import AgentLogEvent
from shared.observability.logging_setup import JsonLogFormatter, RequestContextFilter, configure_logging


def test_json_formatter_includes_context():
    configure_logging(force=True)
    formatter = JsonLogFormatter()
    trace_id_var.set("trace-abc")
    user_id_var.set("user-1")
    session_id_var.set("sess-9")

    record = logging.LogRecord(
        name="am.fin.agent.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.event = AgentLogEvent.CHAT_START
    RequestContextFilter().filter(record)
    payload = json.loads(formatter.format(record))
    assert payload["trace_id"] == "trace-abc"
    assert payload["userId"] == "user-1"
    assert payload["sessionId"] == "sess-9"
    assert payload["event"] == AgentLogEvent.CHAT_START


def test_log_agent_event_allows_reserved_module_field():
    configure_logging(force=True)
    from shared.observability.logging_setup import get_logger

    test_logger = get_logger("test.reserved")
    # `module` is reserved on LogRecord; must not raise KeyError.
    log_agent_event(test_logger, AgentLogEvent.MODULE_LOAD, module="portfolio_analysis")
