"""D8: seam input validation against the vendored corpus (spec Decision 2)."""
import json
from pathlib import Path

import pytest

from benchweave.interfaces import errors
from benchweave.interfaces.validation import SeamValidator

CORPUS = Path(__file__).resolve().parents[2] / "standards" / "interface/1.1.1"


@pytest.fixture(scope="module")
def validator() -> SeamValidator:
    return SeamValidator(CORPUS)


def test_registry_builds_from_vendored_corpus(validator: SeamValidator) -> None:
    names = validator.operation_names()
    # every mutating + paginating operation we validate; observe ops with no
    # body (bench_get etc.) validate path/query params via their handlers
    for op in ("run_start", "run_cancel", "lease_create", "lease_renew",
               "lease_release", "change_submit", "change_apply", "events_get",
               "artifact_read", "run_check", "run_find"):
        assert op in names


def test_type_confusion_is_invalid_request(validator: SeamValidator) -> None:
    # binding_ref must be an object with id/version/sha256 strings
    with pytest.raises(errors.OperationFailure) as ei:
        validator.validate("run_start", {
            "bench_id": "bench-sim-1",
            "request_id": "req-1",
            "binding_ref": "not-an-object",
            "expected_generation": 1,
            "lease_id": None,
        })
    assert ei.value.failure.code == "invalid_request"


def test_expected_generation_string_is_invalid_request(
    validator: SeamValidator,
) -> None:
    # the corpus declares expected_generation as integer (minimum 1): a
    # string where an int belongs must be rejected, never compared/coerced
    with pytest.raises(errors.OperationFailure) as ei:
        validator.validate("run_start", {
            "bench_id": "bench-sim-1",
            "request_id": "req-1",
            "binding_ref": {"id": "b", "version": "1", "sha256": "0" * 64},
            "expected_generation": "1",
            "lease_id": None,
        })
    assert ei.value.failure.code == "invalid_request"


def test_missing_required_is_invalid_request(validator: SeamValidator) -> None:
    with pytest.raises(errors.OperationFailure) as ei:
        validator.validate("run_start", {"bench_id": "bench-sim-1"})
    assert ei.value.failure.code == "invalid_request"


def test_extra_property_is_invalid_request(validator: SeamValidator) -> None:
    with pytest.raises(errors.OperationFailure) as ei:
        validator.validate("run_cancel", {"run_id": "run-x", "junk": 1})
    assert ei.value.failure.code == "invalid_request"


def test_valid_payload_passes(validator: SeamValidator) -> None:
    # run_cancel's corpus schema requires run_id/request_id/reason together
    # (the brief's {"run_id": "run-x"} alone violates that required set).
    validator.validate("run_cancel", {
        "run_id": "run-x",
        "request_id": "req-x",
        "reason": "stop",
    })


def test_registry_inventory_is_the_corpus_surface(validator: SeamValidator) -> None:
    # 17 MCP tools (complete payload schemas: body + routing params) plus the
    # two REST-only admin bodies (change_submit, change_apply); change_get is
    # the one op with neither a tool nor a requestBody — no schema, no-op.
    docs = json.loads((CORPUS / "mcp-tools.json").read_text(encoding="utf-8"))
    tool_ops = {t["name"].removeprefix("stg_v1_") for t in docs["tools"]}
    assert validator.operation_names() == tool_ops | {"change_submit", "change_apply"}
    # an op with no corpus schema validates as a no-op (handler owns it)
    validator.validate("change_get", {"change_id": "chg-1"})
