"""The retention-policy document (issue #43 slice 3, Decision 8).

The #43 owner call 2 posture, mirrored from
``control/provider_settings.py`` (that module cites the same owner call
as its precedent): retention policies are gateway-local validated
configuration today — corpus promotion is the design record's deferral
row 7, on its named trigger (a policy needing to travel with a package
or bench definition).

The document: an operator-owned, optional ``retention-policy.json``
(default location ``<data-dir>/``), validated against a schema in
gateway source — NOT corpus. ``additionalProperties: false`` throughout;
every free string is pattern-constrained (selectors and bench ids), and
the enum fields are closed sets. Refusals carry the typed
``retention_policy:`` prefix, machine-matchable like every other
admission refusal, and the document decodes through the exact-byte
decoder (duplicate keys, non-finite numbers, size, strict UTF-8).

Standing rule (the record's Decision 8): slice 3 writes nothing back.
This module only VALIDATES policy; the report
(``cli/retention.py``) computes disposal projections at read time and
stores no classification stamp, no cached date, no column.

``retain_after: last_access`` is present in the enum so the refusal is a
named, testable error: policies referencing it refuse while the store
carries no durable access-time tracking (the bounded column backfill is
a deferral row — reopen on the first policy author who needs it).

Class grammar: selectors are ``capture:<format>`` or ``evidence:<kind>``.
The capture lane is CLOSED (the in-tree format vocabulary
``host/otdp_bridge.py::OTDPBridge._CAPTURE_FORMATS`` plus
``capture:unknown``, the report's class for NULL/unknown formats); the
evidence lane is OPEN — a novel kind gets its literal class at report
time and falls to the default, never a refusal here. The selector
pattern admits the in-tree kind shapes (letters, digits, dot, underscore,
hyphen — issue #184 finding 12) and anchors with ``\Z`` (finding 14:
``$`` matched before a trailing newline, admitting dead rules).
``duration_s`` is bounded by the datetime domain ceiling
(:data:`MAX_DURATION_S`, finding 3).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from benchweave.content.json_document import DocumentRejected, load_document

#: The one policy filename the retention report looks for by default.
RETENTION_POLICY_FILENAME = "retention-policy.json"

#: The admission byte cap shared with every other admission document.
_MAX_POLICY_BYTES = 1_048_576

#: The class grammar (issue #184 finding 12): selectors must be able to
#: name every class the report emits — ``evidence:<kind>`` is an OPEN
#: vocabulary (kinds land with dots and uppercase, e.g. ``Event.Log``,
#: ``acme.telemetry``), so the pattern admits the in-tree kind shapes
#: (letters, digits, dot, underscore, hyphen). Residual, disclosed: a
#: kind carrying characters outside this grammar still reports its
#: literal class and falls to the default, but no selector can name it —
#: constraining ``put_evidence``'s kind at landing is out of this slice's
#: scope. ``\Z`` (not ``$``) so a trailing-newline selector can never
#: pass admission into a silently dead rule (finding 14).
_SELECTOR_PATTERN = r"^(capture|evidence):[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z"
_BENCH_ID_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}\Z"

#: The duration ceiling (issue #184 finding 3): the datetime domain's
#: epoch-second ceiling — ``datetime.max`` (year 9999-12-31) is
#: 253402300799.999999 s after the epoch. A whole-second duration above
#: 253402300799 can push ``anchor + duration_s`` out of the datetime
#: domain for every anchor and crashed the report-time math
#: (OverflowError unmapped / ValueError untyped). The bound is that
#: domain ceiling — not an invented threshold.
MAX_DURATION_S = 253_402_300_799

#: The closed capture-class vocabulary (the in-tree format vocabulary
#: plus the report's NULL/unknown class). The evidence lane stays open.
_CAPTURE_CLASSES = frozenset(
    {"capture:waveform_f64le", "capture:raw_binary", "capture:unknown"}
)


def _rule_properties() -> dict[str, Any]:
    return {
        "duration_s": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_DURATION_S,
        },
        "retain_after": {
            "type": "string",
            "enum": ["landing", "run_end", "last_access"],
        },
        "on_disposition": {"type": "string", "enum": ["delete", "archive", "review"]},
        "hold": {"type": "boolean"},
    }


def _rule_schema(with_selector: bool) -> dict[str, Any]:
    properties = _rule_properties()
    required = ["duration_s", "retain_after", "on_disposition"]
    if with_selector:
        properties = {
            "selector": {"type": "string", "pattern": _SELECTOR_PATTERN},
            **properties,
        }
        required = ["selector", *required]
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


#: The retention-policy schema (gateway source, not corpus). Mirrors the
#: transport-settings posture: ``additionalProperties: false`` throughout,
#: every free string pattern-constrained, every enum closed.
RETENTION_POLICY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "config_version": {"const": "1"},
        "default": _rule_schema(False),
        "classes": {"type": "array", "items": _rule_schema(True)},
        "benches": {
            "type": "object",
            "propertyNames": {"pattern": _BENCH_ID_PATTERN},
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "default": _rule_schema(False),
                    "classes": {"type": "array", "items": _rule_schema(True)},
                },
                "required": ["default", "classes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["config_version", "default", "classes", "benches"],
    "additionalProperties": False,
}

_VALIDATOR = Draft202012Validator(RETENTION_POLICY_SCHEMA, format_checker=FormatChecker())


class RetentionPolicyRejected(ValueError):
    """The retention-policy document failed validation or consistency."""


@dataclass(frozen=True)
class RetentionRule:
    """One admitted rule — Decision 8's primitive set exactly.

    ``duration_s`` is integer seconds ≥ 1; ``retain_after`` is ``landing``
    or ``run_end`` (``last_access`` refuses at load); ``on_disposition``
    is a REPORT LABEL ONLY (slice 3 deletes nothing — no automated
    disposition ships until the audit-trail slice); ``hold`` keeps the
    row with no disposal date.
    """

    duration_s: int
    retain_after: str
    on_disposition: str
    hold: bool = False


@dataclass(frozen=True)
class RetentionPolicyScope:
    """One bench's override scope: a default plus class rules."""

    default: RetentionRule
    classes: dict[str, RetentionRule]


@dataclass(frozen=True)
class RetentionPolicy:
    """The validated policy object (owner call 1's granularity: global
    default + global classes + per-bench scopes; per-project is resolved
    out of #43)."""

    default: RetentionRule
    classes: dict[str, RetentionRule]
    benches: dict[str, RetentionPolicyScope]

    def resolve_origin(
        self, *, bench: str | None, data_class: str
    ) -> tuple[RetentionRule, str, str | None]:
        """Resolve and NAME the winning entry (issue #184 finding 7):
        the resolution order is bench class → bench default → global class
        → global default (the global default always terminates the chain).
        Returns ``(rule, scope, selector)`` where ``scope`` is
        ``"bench"``/``"global"`` and ``selector`` is the selector string
        iff a class rule won — a class rule merely PRESENT somewhere while
        a shadowing default governs is never named."""
        if bench is not None:
            scope = self.benches.get(bench)
            if scope is not None:
                rule = scope.classes.get(data_class)
                if rule is not None:
                    return rule, "bench", data_class
                return scope.default, "bench", None
        rule = self.classes.get(data_class)
        if rule is not None:
            return rule, "global", data_class
        return self.default, "global", None

    def resolve(self, *, bench: str | None, data_class: str) -> RetentionRule:
        """The governing rule only — :meth:`resolve_origin` also names
        which entry won."""
        return self.resolve_origin(bench=bench, data_class=data_class)[0]


def _rule(entry: dict[str, Any]) -> RetentionRule:
    return RetentionRule(
        duration_s=int(entry["duration_s"]),
        retain_after=str(entry["retain_after"]),
        on_disposition=str(entry["on_disposition"]),
        hold=bool(entry.get("hold", False)),
    )


def _classes(entries: list[Any], where: str) -> dict[str, RetentionRule]:
    classes: dict[str, RetentionRule] = {}
    for entry in entries:
        selector = str(entry["selector"])
        if selector in classes:
            raise RetentionPolicyRejected(
                f"retention_policy: duplicate selector {selector!r} in {where}; "
                "an ambiguous policy is not one"
            )
        classes[selector] = _rule(entry)
    return classes


def _check_last_access(rule: object) -> None:
    if isinstance(rule, dict) and rule.get("retain_after") == "last_access":
        # The record's exact refusal wording (S3-4 pins it verbatim); the
        # where-context is kept out so the message stays machine-matchable.
        raise RetentionPolicyRejected(
            "retention_policy: last_access requires durable access-time "
            "tracking, which the store does not yet carry"
        )


def _check_capture_vocabulary(selector: str, where: str) -> None:
    if selector.startswith("capture:") and selector not in _CAPTURE_CLASSES:
        raise RetentionPolicyRejected(
            f"retention_policy: {where}: selector {selector!r} is outside the "
            "class grammar; capture classes are capture:waveform_f64le, "
            "capture:raw_binary and capture:unknown"
        )


def load_retention_policy(path: Path) -> RetentionPolicy:
    """Exact-byte decode, validate, and materialize the policy document.

    Schema first (shape), then semantics: ``last_access`` refusals,
    duplicate selectors, and capture selectors outside the closed
    vocabulary. Duplicate bench keys are structurally refused earlier by
    the exact-byte decoder (``duplicate_key``) — the decoder IS that
    check. ``duration_s < 1`` is the schema's ``minimum: 1``.
    """
    path = Path(path)
    raw = path.read_bytes()
    try:
        document = load_document(
            raw, hashlib.sha256(raw).hexdigest(), max_bytes=_MAX_POLICY_BYTES
        )
    except DocumentRejected as exc:
        raise RetentionPolicyRejected(f"retention_policy: {path.name} ({exc})") from exc
    error = next(iter(_VALIDATOR.iter_errors(document.content)), None)
    if error is not None:
        raise RetentionPolicyRejected(
            f"retention_policy: {path.name} {error.json_path}: {error.message}"
        ) from error
    content = document.content

    _check_last_access(content["default"])
    for entry in content["classes"]:
        _check_last_access(entry)
        _check_capture_vocabulary(str(entry["selector"]), "the global classes")
    for bench_id, scope in content["benches"].items():
        _check_last_access(scope["default"])
        for entry in scope["classes"]:
            _check_last_access(entry)
            _check_capture_vocabulary(str(entry["selector"]), f"bench {bench_id!r} classes")

    return RetentionPolicy(
        default=_rule(content["default"]),
        classes=_classes(content["classes"], "the global classes"),
        benches={
            str(bench_id): RetentionPolicyScope(
                default=_rule(scope["default"]),
                classes=_classes(scope["classes"], f"bench {bench_id!r} classes"),
            )
            for bench_id, scope in content["benches"].items()
        },
    )
