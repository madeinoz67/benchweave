"""The 14-code interface error model (interface-v1.1.0 error_http_status)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

FAILURE_HTTP: dict[str, int] = {
    "invalid_request": 400,
    "unauthenticated": 401,
    "forbidden": 403,
    "not_found": 404,
    "conflict": 409,
    "policy_denied": 403,
    "not_ready": 409,
    "gone": 410,
    "cursor_expired": 410,
    "event_gap": 410,
    "payload_too_large": 413,
    "rate_limited": 429,
    "unavailable": 503,
    "internal_error": 500,
}


@dataclass(frozen=True)
class Failure:
    code: str
    message: str
    correlation_id: str = ""
    retry: str = "never"  # never | read | same_request
    details: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "correlation_id": self.correlation_id,
                "retry": self.retry,
                "details": self.details,
            },
        }


def failure(
    code: str, message: str, *, retry: str = "never", details: dict[str, Any] | None = None
) -> Failure:
    if code not in FAILURE_HTTP:
        raise ValueError(f"unknown interface error code {code!r}")
    return Failure(code=code, message=message, retry=retry, details=details or {})


def internal_failure(crash: BaseException | None = None) -> Failure:
    """The ONE ``internal_error`` construction site for both adapters (D13).

    The message text is transport-invariant — per-instance detail is
    parameterised into ``details`` (the exception CLASS name only: a
    crashed exception string can carry anything, and the contract §10
    excludes stack traces from the wire), never the message. Every
    envelope mints its own ``correlation_id`` (``uuid4().hex[:16]``): the
    §10 "a correlation ID links internal diagnostics" link between the
    wire response and the operator's logs. Both adapters render exactly
    this factory's output, so text parity is by construction and is
    pinned end to end in the parity suite.
    """
    details: dict[str, Any] = {}
    if crash is not None:
        details["exception"] = type(crash).__name__
    return Failure(
        code="internal_error",
        message="unexpected gateway failure",
        correlation_id=uuid.uuid4().hex[:16],
        retry="never",
        details=details,
    )


class OperationFailure(Exception):
    """The seam's only raised error; carries the contract Failure."""

    def __init__(self, fail: Failure) -> None:
        super().__init__(f"{fail.code}: {fail.message}")
        self.failure = fail
