"""WP08 Task 5: the 14-code error model — rendered envelope shape and the
one ``internal_error`` construction site (D13 batch B).

Unit level: the ``Failure`` envelope is the wire contract both adapters
render, so these pins hold the rendered shape itself, the verbatim catalog
``error_http_status`` map, and the single ``internal_failure`` factory both
transports share — identical message text across transports, a freshly
minted 16-hex ``correlation_id`` per envelope (DISTINCT per envelope,
controller-ratified), and crash diagnostics OFF the wire: the closed
``details`` def admits no ``exception`` key, so the class is logged
server-side keyed by the correlation_id (§10). The end-to-end
both-transport comparison lives in ``test_interface_parity.py``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest

from benchweave.interfaces.errors import (
    FAILURE_HTTP,
    failure,
    internal_failure,
)

CORPUS = Path(__file__).resolve().parents[2] / "standards" / "interface/1.1.1"
CATALOG = json.loads((CORPUS / "operation-catalog.json").read_text(encoding="utf-8"))
_HEX16 = re.compile(r"^[0-9a-f]{16}$")


def test_failure_http_is_the_catalog_map_verbatim() -> None:
    """The 14-code error→HTTP map is the vendored catalog, byte for byte."""
    assert CATALOG["error_http_status"] == FAILURE_HTTP


def test_failure_body_is_the_rendered_error_envelope() -> None:
    """D14 cheap half (WP09): every failure mints a real correlation_id
    (vendored $defs/error minLength 1). The ``details`` half of D14 stays
    deferred — rendered ``details`` remains open/free-form, pinned here as
    the rendered shape, registered in compatibility.md."""
    fail = failure("conflict", "bench busy", retry="never", details={"x": 1})
    body = fail.body()
    assert body == {
        "ok": False,
        "error": {
            "code": "conflict",
            "message": "bench busy",
            "correlation_id": fail.correlation_id,
            "retry": "never",
            "details": {"x": 1},
        },
    }
    assert _HEX16.match(fail.correlation_id), "non-internal failures mint too"


def test_failure_honours_explicit_correlation_id_and_uniqueness() -> None:
    explicit = failure("conflict", "x", correlation_id="deadbeefdeadbeef")
    assert explicit.correlation_id == "deadbeefdeadbeef"
    assert failure("conflict", "a").correlation_id != failure("conflict", "b").correlation_id


def test_unknown_code_is_a_programming_error_never_a_wire_code() -> None:
    with pytest.raises(ValueError):
        failure("nope", "never a wire code")


def test_internal_failure_message_is_transport_invariant() -> None:
    """One construction site, one message: whatever crashed and wherever it
    surfaced, the message text cannot diverge between transports."""
    one = internal_failure(RuntimeError("boom one"))
    two = internal_failure()
    assert one.code == two.code == "internal_error"
    assert one.message == two.message == "unexpected gateway failure"
    assert one.retry == two.retry == "never"


def test_internal_failure_mints_a_unique_16hex_correlation_id() -> None:
    one = internal_failure()
    two = internal_failure()
    assert _HEX16.match(one.correlation_id)
    assert _HEX16.match(two.correlation_id)
    assert one.correlation_id != two.correlation_id
    assert one.body()["error"]["correlation_id"] == one.correlation_id


def test_internal_failure_keeps_diagnostics_off_the_wire_and_logs_them(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The vendored ``details`` def is CLOSED (six keys, no ``exception``):
    internal diagnostics never ride the wire. The exception is logged
    server-side by the module logger, keyed by the envelope's
    correlation_id — the §10 "a correlation ID links internal
    diagnostics" join between a wire response and its log line."""
    with caplog.at_level(logging.ERROR, logger="benchweave.interfaces.errors"):
        crash = internal_failure(ValueError("secret connection string"))
    assert crash.details == {}  # nothing about the crash is on the wire
    assert "secret" not in json.dumps(crash.body())
    assert _HEX16.match(crash.correlation_id)
    joined = [
        record
        for record in caplog.records
        if crash.correlation_id in record.getMessage()
    ]
    assert joined, "the log line must carry the envelope's correlation_id"
    assert "ValueError" in joined[0].getMessage()
