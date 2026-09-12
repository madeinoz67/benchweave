"""The 14-code interface error model (interface-v1.1.0 error_http_status)."""

from __future__ import annotations

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


class OperationFailure(Exception):
    """The seam's only raised error; carries the contract Failure."""

    def __init__(self, fail: Failure) -> None:
        super().__init__(f"{fail.code}: {fail.message}")
        self.failure = fail
