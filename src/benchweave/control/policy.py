"""Safety-policy evaluation over an admitted policy document.

Two pure checks with no store, plugin, clock or I/O of their own.

``check_allowed`` is the deny-by-default gate the executor consults before
every state-changing dispatch: an action is allowed only when at least one
allow rule matches the actual device and the exact action id (invoke) or
parameter (write), and every matching rule's constraints then hold
conjunctively — there are no order-dependent overrides. Invoke inputs are
JSON-Schema-validated against each matching rule's ``input_constraints``
(an empty schema ``{}`` imposes no extra constraint); write values against
``value_constraints``. Rejections carry a machine-matchable prefix:
``no_matching_rule:`` (deny by default), ``input_constraint:`` or
``value_constraint:``.

``evaluate_conditions`` checks the continuous conditions against a signal
snapshot and returns one description per failed condition aspect, each
formatted ``"<condition_id>: <reason>..."``; an empty list means all clear.
Numeric bounds are conservative: the whole error interval ``[v - e, v + e]``
must fit inside ``[minimum, maximum]``. Products bound
``(abs(v1) + e1) * (abs(v2) + e2)`` and additionally cap the sample skew;
a W-valued product requires its two factors' units to be exactly ``V`` and
``A`` in either order, and any other pairing is itself a violation.
Freshness is not checked here: whoever builds the snapshot marks a signal
past its bench ``max_age`` as invalid, and invalid or absent signals make
their condition INVALID and are reported as violations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]


class PolicyDenied(Exception):
    """A state-changing action matched no allow rule or violated one.

    ``reason`` is a machine-matchable description (prefix
    ``no_matching_rule:``, ``input_constraint:`` or ``value_constraint:``);
    ``rule_ids`` names the matching allow rules by ``allow_rules`` index —
    empty for a deny-by-default no-match, the failing rules otherwise.
    """

    def __init__(self, reason: str, rule_ids: tuple[str, ...]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rule_ids = rule_ids


@dataclass(frozen=True)
class SignalValue:
    """One sampled bench signal as evaluated by continuous conditions.

    ``valid`` carries the snapshot builder's freshness verdict (the bench
    ``max_age`` is enforced where the snapshot is built, not here), and
    ``absolute_error`` is the signal's stated error bound, ``None`` when
    unknown.
    """

    signal_id: str
    value: float
    unit: str
    age_ms: int
    valid: bool
    absolute_error: float | None


def check_allowed(
    policy: dict[str, Any],
    device_id: str,
    kind: str,
    target: str,
    payload: dict[str, Any] | Any,
) -> None:
    """Return when the action is allowed; raise :class:`PolicyDenied` otherwise.

    ``target`` is the action id for ``invoke`` rules and the parameter name
    for ``write`` rules; ``payload`` is the invoke input object or the write
    scalar value. A rule matches only on identical ``device_id``, ``kind``
    and target — an empty match denies (the state-changing default), and all
    matching rules must then pass conjunctively.
    """

    matching: list[tuple[str, dict[str, Any]]] = []
    for index, rule in enumerate(policy["allow_rules"]):
        if rule.get("device_id") != device_id or rule.get("kind") != kind:
            continue
        rule_target = rule.get("action_id") if kind == "invoke" else rule.get("parameter")
        if rule_target == target:
            matching.append((f"allow_rules[{index}]", rule))
    if not matching:
        raise PolicyDenied(f"no_matching_rule: {kind} {target} on device {device_id}", ())

    if kind == "invoke":
        if not isinstance(payload, dict):
            # JSON Schema "properties" only applies to objects, so a scalar
            # payload would silently satisfy any constraint schema.
            raise PolicyDenied(
                f"input_constraint: invoke payload for {target} on device {device_id} "
                "is not an object",
                tuple(rule_id for rule_id, _ in matching),
            )
        prefix, constraints_key = "input_constraint", "input_constraints"
    else:
        prefix, constraints_key = "value_constraint", "value_constraints"

    failures: list[str] = []
    failing: list[str] = []
    for rule_id, rule in matching:
        error = next(
            iter(Draft202012Validator(rule[constraints_key]).iter_errors(payload)), None
        )
        if error is not None:
            failures.append(f"{rule_id} {error.json_path}: {error.message}")
            failing.append(rule_id)
    if failures:
        raise PolicyDenied(f"{prefix}: " + "; ".join(failures), tuple(failing))


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _numeric_violation(
    condition: dict[str, Any], snapshot: dict[str, SignalValue]
) -> list[str]:
    condition_id = condition["id"]
    signal = snapshot.get(condition["signal"])
    if signal is None:
        return [f"{condition_id}: signal_missing: {condition['signal']}"]
    if not signal.valid:
        return [f"{condition_id}: signal_invalid: {condition['signal']}"]
    if signal.unit != condition["unit"]:
        return [
            f"{condition_id}: unit_mismatch: expected {condition['unit']}, "
            f"have {signal.unit}"
        ]
    error = signal.absolute_error
    if error is None or not math.isfinite(error) or error < 0:
        return [f"{condition_id}: unknown_error"]
    if not math.isfinite(signal.value):
        return [f"{condition_id}: nonfinite_value: {condition['signal']}"]
    low = signal.value - error
    high = signal.value + error
    if low < condition["minimum"] or high > condition["maximum"]:
        return [
            f"{condition_id}: interval_escape: [{_fmt(low)}, {_fmt(high)}] escapes "
            f"[{_fmt(condition['minimum'])}, {_fmt(condition['maximum'])}]"
        ]
    return []


def _boolean_violation(
    condition: dict[str, Any], snapshot: dict[str, SignalValue]
) -> list[str]:
    condition_id = condition["id"]
    signal = snapshot.get(condition["signal"])
    if signal is None:
        return [f"{condition_id}: signal_missing: {condition['signal']}"]
    if not signal.valid:
        return [f"{condition_id}: signal_invalid: {condition['signal']}"]
    if bool(signal.value) != condition["expected"]:
        return [
            f"{condition_id}: boolean_mismatch: {condition['signal']} is "
            f"{_fmt(signal.value)}, expected {condition['expected']}"
        ]
    return []


def _product_violation(
    condition: dict[str, Any], snapshot: dict[str, SignalValue]
) -> list[str]:
    condition_id = condition["id"]
    values: list[float] = []
    errors: list[float] = []
    ages: list[int] = []
    units: list[str] = []
    for signal_id in condition["signals"]:
        signal = snapshot.get(signal_id)
        if signal is None:
            return [f"{condition_id}: signal_missing: {signal_id}"]
        if not signal.valid:
            return [f"{condition_id}: signal_invalid: {signal_id}"]
        error = signal.absolute_error
        if error is None or not math.isfinite(error) or error < 0:
            return [f"{condition_id}: unknown_error"]
        if not math.isfinite(signal.value):
            return [f"{condition_id}: nonfinite_value: {signal_id}"]
        values.append(signal.value)
        errors.append(error)
        ages.append(signal.age_ms)
        units.append(signal.unit)
    # §7: the product condition is V x A -> W. The condition's unit (W) is
    # the PRODUCT's unit, but the factors must still be exactly one V and
    # one A in either order — anything else (two same-unit signals, a kV-
    # scaled factor) is an INVALID condition, reported so the caller can
    # trigger the protective response rather than let a mis-unitized
    # product silently pass the bound.
    if condition["unit"] == "W" and set(units) != {"V", "A"}:
        return [
            f"{condition_id}: factor_unit_mismatch: expected V and A factors, "
            f"have {units[0]} and {units[1]}"
        ]
    violations: list[str] = []
    bound = (abs(values[0]) + errors[0]) * (abs(values[1]) + errors[1])
    maximum = condition["maximum"]
    if bound > maximum:
        violations.append(
            f"{condition_id}: bound_exceeded: {_fmt(bound)} > maximum {_fmt(maximum)}"
        )
    skew = abs(ages[0] - ages[1])
    max_skew_ms = condition["max_skew_ms"]
    if skew > max_skew_ms:
        violations.append(f"{condition_id}: skew_exceeded: {skew} > max_skew_ms {max_skew_ms}")
    return violations


_CHECKERS = {
    "numeric": _numeric_violation,
    "boolean": _boolean_violation,
    "absolute_product": _product_violation,
}


def evaluate_conditions(
    policy: dict[str, Any], snapshot: dict[str, SignalValue]
) -> list[str]:
    """Return one violation description per failed condition aspect.

    Descriptions are formatted ``"<condition_id>: <reason>..."``; an empty
    list means every continuous condition holds. Missing, invalid (stale),
    wrong-unit or error-unknown signals make their condition INVALID and
    are reported as violations so the caller can trigger the protective
    response.
    """

    violations: list[str] = []
    for condition in policy["continuous_conditions"]:
        violations.extend(_CHECKERS[condition["kind"]](condition, snapshot))
    return violations
