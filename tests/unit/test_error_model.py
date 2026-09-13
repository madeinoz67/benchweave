"""WP08 Task 5: the 14-code error model — envelope shape and the one
``internal_error`` construction site (D13 batch B).

Unit level: the ``Failure`` envelope is the wire contract both adapters
render, so these pins hold the shape itself, the verbatim catalog
``error_http_status`` map, and the single ``internal_failure`` factory both
transports share — identical message text across transports (per-instance
detail is parameterised into ``details``, never the message) and a freshly
minted 16-hex ``correlation_id`` per envelope, the contract §10 "a
correlation ID links internal diagnostics" link. The end-to-end
both-transport comparison lives in ``test_interface_parity.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from benchweave.interfaces.errors import (
    FAILURE_HTTP,
    failure,
    internal_failure,
)

CORPUS = Path(__file__).resolve().parents[2] / "contracts" / "interface-v1.1.0"
CATALOG = json.loads((CORPUS / "operation-catalog.json").read_text(encoding="utf-8"))
_HEX16 = re.compile(r"^[0-9a-f]{16}$")


def test_failure_http_is_the_catalog_map_verbatim() -> None:
    """The 14-code error→HTTP map is the vendored catalog, byte for byte."""
    assert CATALOG["error_http_status"] == FAILURE_HTTP


def test_failure_body_is_the_contract_error_envelope() -> None:
    fail = failure("conflict", "bench busy", retry="never", details={"x": 1})
    assert fail.body() == {
        "ok": False,
        "error": {
            "code": "conflict",
            "message": "bench busy",
            "correlation_id": "",
            "retry": "never",
            "details": {"x": 1},
        },
    }


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


def test_internal_failure_details_carry_only_the_exception_class() -> None:
    """Per-instance detail is the exception CLASS, never the payload — a
    crashed exception string can carry anything, and the contract §10
    excludes stack traces from the wire."""
    crash = internal_failure(ValueError("secret connection string"))
    assert crash.details == {"exception": "ValueError"}
    assert "secret" not in json.dumps(crash.body())
