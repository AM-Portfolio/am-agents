"""A2A enums."""

from __future__ import annotations

from enum import Enum


class A2AOp(str, Enum):
    DISCOVER = "discover"
    PLAN = "plan"
    EXECUTE = "execute"
    STREAM = "stream"
    STATUS = "status"
    CANCEL = "cancel"
    FEEDBACK = "feedback"


class TaskStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class FeedbackRating(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    UNSAFE = "unsafe"


class SupportDomain(str, Enum):
    """Allowlisted business classification used by observability."""

    TECHNICAL = "technical"
    BILLING = "billing"
    PRODUCT = "product"
    INTERNAL = "internal"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class IncidentValidationStatus(str, Enum):
    """Post-assignment acceptance gate outcome."""

    CONFIRMED = "confirmed"
    INCONCLUSIVE = "inconclusive"
    NOT_CONFIRMED = "not_confirmed"


class ApprovalRisk(str, Enum):
    """Generic tool approval / risk class (provider-agnostic)."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    SEND = "send"
    DELETE = "delete"
    EXECUTE = "execute"


class CapabilityId(str, Enum):
    """Neutral capability IDs used by support-agent and tool-agent plugins."""

    WORK_ITEM_SEARCH = "work-item.search"
    WORK_ITEM_GET = "work-item.get"
    WORK_ITEM_CREATE = "work-item.create"
    WORK_ITEM_ASSIGN = "work-item.assign"
    WORK_ITEM_COMMENT = "work-item.comment"
    WORK_ITEM_TRANSITION = "work-item.transition"
    DIRECTORY_OWNER_RESOLVE = "directory.owner.resolve"
    CHAT_MESSAGE_SEND = "chat.message.send"
    CHAT_CARD_SEND = "chat.card.send"
    MAIL_MESSAGE_SEND = "mail.message.send"
    CALENDAR_EVENT_CREATE = "calendar.event.create"
    DOCUMENT_PUT = "document.put"
    DOCUMENT_GET = "document.get"
    DOCUMENT_EXISTS = "document.exists"
    DOCUMENT_SIGNED_URL_CREATE = "document.signed-url.create"
    OBSERVE_METRICS_QUERY = "observe.metrics.query"
    OBSERVE_LOGS_QUERY = "observe.logs.query"
    OBSERVE_TIMESERIES_QUERY = "observe.timeseries.query"
    ALERT_SILENCE_CREATE = "alert.silence.create"
    ALERT_SILENCE_GET = "alert.silence.get"
    ALERT_SILENCE_EXPIRE = "alert.silence.expire"
    SPT_TEST_DATA_PREPARE = "spt.test-data.prepare"
    SPT_EXECUTE = "spt.execute"
    SPT_STATUS = "spt.status"
    SPT_CANCEL = "spt.cancel"
    SECRET_INJECT = "secret.inject"


class CapabilityEffect(str, Enum):
    """Classifies whether a capability is a real remediation vs admin/notify."""

    REMEDIATION = "remediation"
    ADMIN = "admin"
    NOTIFY = "notify"
    OBSERVE = "observe"
