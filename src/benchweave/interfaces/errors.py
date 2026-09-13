"""The 14-code interface error model (interface-v1.1.0 error_http_status)."""

from __future__ import annotations

import logging
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


# The app's first operational module logger (Task-5 fix wave): the one
# place unexpected-exception diagnostics land. The vendored ``$defs/error``
# ``details`` is a CLOSED six-key object, so crash detail cannot ride the
# wire — per §10 ("a correlation ID links internal diagnostics") it is
# logged here, keyed by the envelope's correlation_id.
_LOG = logging.getLogger(__name__)


def internal_failure(crash: BaseException | None = None) -> Failure:
    """The ONE ``internal_error`` construction site for both adapters (D13).

    The message text is transport-invariant and the wire envelope carries
    NO crash detail — the vendored ``$defs/error`` ``details`` is closed
    (findings/revision/watermarks/retry_after_ms only), so an ``exception``
    key there is a schema violation. Per the §10 design, the freshly
    minted ``correlation_id`` (``uuid4().hex[:16]``) rides the wire while
    the exception is LOGGED server-side keyed by that same id, so an
    operator can join a wire response to its log line. Both adapters
    render exactly this factory's output, so text parity is by
    construction and is pinned end to end in the parity suite.
    """
    correlation_id = uuid.uuid4().hex[:16]
    if crash is not None:
        _LOG.error(
            "internal_error correlation_id=%s: %s: %s",
            correlation_id,
            type(crash).__name__,
            crash,
        )
    return Failure(
        code="internal_error",
        message="unexpected gateway failure",
        correlation_id=correlation_id,
        retry="never",
    )


class OperationFailure(Exception):
    """The seam's only raised error; carries the contract Failure."""

    def __init__(self, fail: Failure) -> None:
        super().__init__(f"{fail.code}: {fail.message}")
        self.failure = fail
