from contextvars import ContextVar

# Per-request context — set by middleware / chat entry before business logic.
# Tools read these directly; no need to pass userId as a parameter through the call stack.
user_id_var: ContextVar[str] = ContextVar("user_id", default="anonymous")
auth_token_var: ContextVar[str] = ContextVar("auth_token", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
