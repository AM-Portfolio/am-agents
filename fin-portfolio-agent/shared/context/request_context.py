from contextvars import ContextVar

# Per-request context — set by the logging middleware before any business logic runs.
# Tools read these directly; no need to pass userId as a parameter through the call stack.
user_id_var: ContextVar[str] = ContextVar("user_id", default="anonymous")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")
auth_token_var: ContextVar[str] = ContextVar("auth_token", default="")
