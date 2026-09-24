"""Issue #43 slice 3: the retention-policy document (Decision 8).

Gateway-local validated configuration — the #43 owner call 2 posture,
mirroring ``control/provider_settings.py``: exact-byte decode, a
gateway-source schema (NOT corpus; promotion is the design record's
deferral row 7), then semantic checks whose refusals carry the
machine-matchable ``retention_policy:`` prefix.

Covered:

- A full document (global default + classes + a per-bench scope) loads
  and round-trips into the dataclasses; resolution follows the owner
  call 1 order (bench class → bench default → global class → global
  default).
- S3-4: ``retain_after: last_access`` refuses with the named
  durable-tracking error — the enum member exists so the refusal is a
  named, testable error, not a silent schema gap.
- Duplicate selectors, selectors outside the class grammar (shape, and
  the closed capture vocabulary), ``duration_s < 1``, unknown rule
  fields, and duplicate bench keys in the raw bytes all refuse with the
  ``retention_policy:`` prefix.
- The evidence lane is an OPEN vocabulary: a novel kind resolves to the
  default, never a refusal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.control.retention_policy import (
    RetentionPolicy,
    RetentionPolicyRejected,
    load_retention_policy,
)

A_RULE = {"duration_s": 86400, "retain_after": "landing", "on_disposition": "review"}


def _document() -> dict[str, Any]:
    return {
        "config_version": "1",
        "default": dict(A_RULE),
        "classes": [
            {
                "selector": "capture:waveform_f64le",
                "duration_s": 3600,
                "retain_after": "landing",
                "on_disposition": "delete",
            },
            {
                "selector": "evidence:event_log",
                "duration_s": 604800,
                "retain_after": "run_end",
                "on_disposition": "archive",
                "hold": True,
            },
        ],
        "benches": {
            "bench-ov": {
                "default": {
                    "duration_s": 60,
                    "retain_after": "landing",
                    "on_disposition": "review",
                },
                "classes": [
                    {
                        "selector": "capture:waveform_f64le",
                        "duration_s": 120,
                        "retain_after": "landing",
                        "on_disposition": "delete",
                    }
                ],
            }
        },
    }


def _load(tmp_path: Path, document: object) -> RetentionPolicy:
    path = tmp_path / "retention-policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_retention_policy(path)


# --- a valid document ------------------------------------------------------------


def test_a_full_document_loads_and_round_trips(tmp_path: Path) -> None:
    policy = _load(tmp_path, _document())
    assert policy.default.duration_s == 86400
    assert policy.default.retain_after == "landing"
    assert policy.default.on_disposition == "review"
    assert policy.default.hold is False
    held = policy.classes["evidence:event_log"]
    assert held.hold is True and held.retain_after == "run_end"
    scope = policy.benches["bench-ov"]
    assert scope.default.duration_s == 60
    assert scope.classes["capture:waveform_f64le"].duration_s == 120


def test_resolution_is_bench_class_bench_default_global_class_global_default(
    tmp_path: Path,
) -> None:
    policy = _load(tmp_path, _document())
    # bench class wins over everything
    assert (
        policy.resolve(bench="bench-ov", data_class="capture:waveform_f64le").duration_s
        == 120
    )
    # bench default wins over the global class
    assert policy.resolve(bench="bench-ov", data_class="evidence:event_log").duration_s == 60
    # global class when the bench has no scope at all
    assert (
        policy.resolve(bench="other-bench", data_class="evidence:event_log").duration_s
        == 604800
    )
    # global default when nothing matches
    assert policy.resolve(bench=None, data_class="capture:raw_binary").duration_s == 86400
    assert policy.resolve(bench="bench-ov", data_class="capture:raw_binary").duration_s == 60


def test_novel_evidence_kind_falls_to_the_default(tmp_path: Path) -> None:
    """The evidence lane is an open vocabulary: a kind the policy never
    names gets its literal class at report time and resolves to the
    default — never a refusal here."""
    policy = _load(tmp_path, _document())
    assert policy.resolve(bench=None, data_class="evidence:spectrum").duration_s == 86400


# --- refusals ----------------------------------------------------------------------


def test_last_access_refuses_naming_the_missing_tracking(tmp_path: Path) -> None:
    """S3-4: the enum carries ``last_access`` so the refusal is a named
    error, not a schema gap."""
    document = _document()
    document["default"]["retain_after"] = "last_access"
    with pytest.raises(
        RetentionPolicyRejected,
        match=(
            r"retention_policy: last_access requires durable access-time "
            r"tracking, which the store does not yet carry"
        ),
    ):
        _load(tmp_path, document)


def test_last_access_refuses_in_class_and_bench_rules_too(tmp_path: Path) -> None:
    document = _document()
    document["classes"][0]["retain_after"] = "last_access"
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:"):
        _load(tmp_path, document)
    document = _document()
    document["benches"]["bench-ov"]["default"]["retain_after"] = "last_access"
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:"):
        _load(tmp_path, document)


def test_duplicate_selector_refuses(tmp_path: Path) -> None:
    document = _document()
    document["classes"].append(dict(document["classes"][0]))
    with pytest.raises(
        RetentionPolicyRejected, match=r"retention_policy: duplicate selector"
    ):
        _load(tmp_path, document)


def test_duplicate_bench_scope_selector_refuses(tmp_path: Path) -> None:
    document = _document()
    document["benches"]["bench-ov"]["classes"].append(
        dict(document["benches"]["bench-ov"]["classes"][0])
    )
    with pytest.raises(
        RetentionPolicyRejected, match=r"retention_policy: duplicate selector"
    ):
        _load(tmp_path, document)


def test_duplicate_bench_keys_refuse_at_decode(tmp_path: Path) -> None:
    """Duplicate bench keys are structurally refused by the exact-byte
    decoder (``duplicate_key``) — the refusal still carries the prefix."""
    one_scope = json.dumps(
        {"default": A_RULE, "classes": []}, sort_keys=True
    )
    raw = (
        '{"config_version": "1", "default": ' + json.dumps(A_RULE) + ","
        ' "classes": [], "benches": {"bench-ov": ' + one_scope + ","
        ' "bench-ov": ' + one_scope + "}}"
    )
    path = tmp_path / "retention-policy.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:.*duplicate_key"):
        load_retention_policy(path)


def test_capture_selector_outside_the_closed_vocabulary_refuses(tmp_path: Path) -> None:
    """The capture lane's classes are closed (the in-tree format
    vocabulary plus ``capture:unknown``); the evidence lane stays open."""
    document = _document()
    document["classes"][0]["selector"] = "capture:csv"
    with pytest.raises(
        RetentionPolicyRejected, match=r"retention_policy:.*outside the class grammar"
    ):
        _load(tmp_path, document)


def test_selector_outside_the_class_grammar_refuses(tmp_path: Path) -> None:
    document = _document()
    document["classes"][0]["selector"] = "waveform_f64le"  # no lane prefix
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:"):
        _load(tmp_path, document)
    document = _document()
    document["classes"][0]["selector"] = "capture:Waveform"
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:"):
        _load(tmp_path, document)


def test_duration_below_one_refuses(tmp_path: Path) -> None:
    document = _document()
    document["default"]["duration_s"] = 0
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:.*duration_s"):
        _load(tmp_path, document)


def test_unknown_rule_field_refuses(tmp_path: Path) -> None:
    document = _document()
    document["default"]["archive_tier"] = "cold"
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:"):
        _load(tmp_path, document)


def test_missing_top_level_keys_refuse(tmp_path: Path) -> None:
    document = _document()
    del document["benches"]
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:"):
        _load(tmp_path, document)


# --- fix wave (issue #184): schema hardening ------------------------------------

#: The duration ceiling (issue #184 finding 3): the datetime domain's
#: epoch-second ceiling — ``datetime.max`` (year 9999-12-31) is
#: 253402300799.999999 s after the epoch, so a whole-second duration
#: above 253402300799 can push ``anchor + duration_s`` out of the
#: datetime domain for every anchor. The bound is that ceiling, not an
#: invented threshold.
MAX_DURATION_S = 253_402_300_799


def test_fw3_duration_s_boundary_table(tmp_path: Path) -> None:
    """Finding 3 (HIGH): ``duration_s`` admitted any int >= 1, so 1e20
    raised OverflowError at report time (an unmapped traceback) and 1e12
    an untyped ValueError. The schema carries a documented maximum now
    and the load refuses typed — boundary over {1, max, max+1, 1e12,
    1e20}."""
    for good in (1, MAX_DURATION_S):
        document = _document()
        document["default"]["duration_s"] = good
        policy = _load(tmp_path, document)
        assert policy.default.duration_s == good
    for bad in (MAX_DURATION_S + 1, 10**12, 10**20):
        document = _document()
        document["default"]["duration_s"] = bad
        with pytest.raises(
            RetentionPolicyRejected, match=r"retention_policy:.*duration_s"
        ):
            _load(tmp_path, document)
        # the class and bench rule shapes carry the same bound
        document = _document()
        document["classes"][0]["duration_s"] = bad
        with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:"):
            _load(tmp_path, document)


def test_fw12_dotted_and_uppercase_kinds_are_selectable(tmp_path: Path) -> None:
    """Finding 12 (LOW): the report emits ``evidence:<kind>`` verbatim but
    selectors were pattern-locked to lowercase [a-z0-9_-] — dots and
    uppercase kinds were ungovernable at class level. The selector grammar
    now admits what the report can name (dots, uppercase, the in-tree
    kind shapes); the capture lane stays closed via the vocabulary."""
    document = _document()
    document["classes"].append(
        {
            "selector": "evidence:Event.Log",
            "duration_s": 60,
            "retain_after": "landing",
            "on_disposition": "delete",
        }
    )
    policy = _load(tmp_path, document)
    assert (
        policy.resolve(bench=None, data_class="evidence:Event.Log").duration_s == 60
    )
    document = _document()
    document["classes"].append(
        {
            "selector": "evidence:acme.telemetry",
            "duration_s": 90,
            "retain_after": "landing",
            "on_disposition": "review",
        }
    )
    policy = _load(tmp_path, document)
    assert (
        policy.resolve(bench=None, data_class="evidence:acme.telemetry").duration_s
        == 90
    )


def test_fw14_trailing_newline_selector_refused(tmp_path: Path) -> None:
    """Finding 14 (NIT): the pattern's ``$`` matches before a trailing
    newline, so ``"evidence:dataset\\n"`` passed admission and became a
    silently dead rule. ``\\Z`` closes the escape — the selector must
    match the whole string."""
    document = _document()
    document["classes"].append(
        {
            "selector": "evidence:dataset\n",
            "duration_s": 60,
            "retain_after": "landing",
            "on_disposition": "delete",
        }
    )
    with pytest.raises(RetentionPolicyRejected, match=r"retention_policy:"):
        _load(tmp_path, document)
