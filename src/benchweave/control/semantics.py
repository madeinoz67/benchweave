"""Semantic admission of an admitted execution document set.

Document admission proved structure and the digest pin lattice; this stage
enforces the execution contract's semantic rules over the same admitted
dicts: step-ID uniqueness across the whole procedure (nested blocks
included), lexical scoping of result references (a step may reference an
earlier sibling of its own block or the visible prefix inherited from
enclosing blocks — never a later sibling, never itself, never a step inside
a branch body from outside it, and never a repeat iteration's results from
outside the loop or from another iteration), ``$stg_issue`` placement only at
invoke input keys the role's device descriptor marks issued for that exact
action, the worst-case body budget against ``max_body_ms``, the energised-time
qualification against the policy domains, and the commissioning deadline.

Pure functions over the admitted documents: no I/O, and the wall clock is a
parameter. Rejections raise the document-admission
:class:`~benchweave.control.documents.AdmissionRejected` with
machine-matchable prefixes: ``duplicate_step_id:``, ``scope:``,
``issue_placement:``, ``body_budget:``, ``energised_budget:`` and ``expired:``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

from benchweave.control.documents import AdmissionRejected, AdmittedDocuments


def worst_case_body_ms(steps: list[dict[str, Any]]) -> int:
    """Return the worst-case procedure body duration in milliseconds.

    Sums invoke/read/write ``timeout_ms`` and delay ``duration_ms``; an ``if``
    contributes the larger branch and a ``repeat`` multiplies its body by the
    iteration count. Samples and asserts execute in the gateway and cost
    nothing.
    """
    total = 0
    for step in steps:
        kind = step["kind"]
        if kind in ("invoke", "read", "write"):
            total += step["timeout_ms"]
        elif kind == "delay":
            total += step["duration_ms"]
        elif kind == "if":
            total += max(worst_case_body_ms(step["then"]),
                         worst_case_body_ms(step.get("else", [])))
        elif kind == "repeat":
            total += step["count"] * worst_case_body_ms(step["steps"])
    return total


def _walk(steps: list[dict[str, Any]], visible: list[str],
          block_id: str) -> Iterator[tuple[dict[str, Any], frozenset[str], str]]:
    """Yield each step with the IDs visible to it and its block path.

    A step sees the enclosing prefix plus the earlier siblings of its own
    block and never itself: the yield happens before its own ID is appended
    to ``seen``. Branch and repeat bodies are walked with the prefix that
    includes their parent step and everything before it; their internal IDs
    never escape the child walk, and every repeat iteration restarts from the
    same enclosing prefix, so iteration results are invisible to later
    iterations and to anything after the loop.
    """
    seen: list[str] = []
    for step in steps:
        yield step, frozenset(visible + seen), block_id
        sid = step["id"]
        seen.append(sid)
        visible_now = visible + seen
        if step["kind"] == "if":
            yield from _walk(step["then"], visible_now, block_id + f"/{sid}/then")
            yield from _walk(step.get("else", []), visible_now, block_id + f"/{sid}/else")
        elif step["kind"] == "repeat":
            for i in range(step["count"]):
                yield from _walk(step["steps"], visible_now, block_id + f"/{sid}/{i}")


def _collect_ids(steps: list[dict[str, Any]]) -> Iterator[str]:
    """Yield every step ID in the procedure, nested blocks included once."""
    for step in steps:
        yield str(step["id"])
        if step["kind"] == "if":
            yield from _collect_ids(step["then"])
            yield from _collect_ids(step.get("else", []))
        elif step["kind"] == "repeat":
            yield from _collect_ids(step["steps"])


def _check_unique_ids(steps: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for sid in _collect_ids(steps):
        if sid in seen:
            raise AdmissionRejected(f"duplicate_step_id: {sid!r} used by more than one step")
        seen.add(sid)


def _ref_sites(value: Any, path: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(path, directive)`` for every ``$stg_ref`` under ``value``.

    Directive objects carry only ``step`` and ``pointer`` (schema-bound), so
    they are not recursed into.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$stg_ref":
                yield path, child
            else:
                yield from _ref_sites(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _ref_sites(item, f"{path}[{index}]")


def _nested_issue_site(value: Any, path: str) -> str | None:
    """Return the path of the first ``$stg_issue`` nested under ``value``."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$stg_issue":
                return path
            nested = _nested_issue_site(child, f"{path}.{key}")
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for index, item in enumerate(value):
            nested = _nested_issue_site(item, f"{path}[{index}]")
            if nested is not None:
                return nested
    return None


def _reject_scope(sid: str, where: str, origin: str, target: str) -> NoReturn:
    raise AdmissionRejected(
        f"scope: step {sid!r} at {where} references {target!r} via {origin}, "
        "which is not visible here"
    )


def _issued_fields(
    step: dict[str, Any],
    descriptors: dict[str, dict[str, Any]],
    device_by_role: dict[str, str],
) -> set[str]:
    """Input keys the role's device descriptor marks issued for the action.

    A role that resolves to no device descriptor marks nothing issued, so any
    ``$stg_issue`` under it is rejected here; whether every role must be bound
    at all is binding completeness, a later admission stage.
    """
    device_id = device_by_role.get(str(step["role"]))
    descriptor = descriptors.get(device_id) if device_id is not None else None
    if descriptor is None:
        return set()
    return {
        field
        for action in descriptor["actions"]
        if action["action_id"] == step["action_id"]
        for field in action.get("issued", [])
    }


def _check_step(
    step: dict[str, Any],
    visible: frozenset[str],
    block_id: str,
    descriptors: dict[str, dict[str, Any]],
    device_by_role: dict[str, str],
) -> None:
    sid = str(step["id"])
    kind = step["kind"]
    where = f"{block_id}/{sid}"

    if kind in ("invoke", "write"):
        field = "input" if kind == "invoke" else "value"
        for path, directive in _ref_sites(step[field], field):
            target = str(directive["step"])
            if target not in visible:
                _reject_scope(sid, where, f"$stg_ref at {path}", target)
    if kind == "sample":
        target = str(step["source_step"])
        if target not in visible:
            _reject_scope(sid, where, "sample.source_step", target)
    if kind in ("assert", "if"):
        target = str(step["predicate"]["sample"])
        if target not in visible:
            _reject_scope(sid, where, "predicate.sample", target)

    if kind == "invoke":
        issued = _issued_fields(step, descriptors, device_by_role)
        for key, child in step["input"].items():
            if key == "$stg_issue" or (isinstance(child, dict) and "$stg_issue" in child):
                if key not in issued:
                    raise AdmissionRejected(
                        f"issue_placement: step {sid!r} at {where} places $stg_issue at "
                        f"input key {key!r}, which the role's device descriptor does "
                        f"not mark issued for action {step['action_id']!r}"
                    )
            else:
                nested = _nested_issue_site(child, key)
                if nested is not None:
                    raise AdmissionRejected(
                        f"issue_placement: step {sid!r} at {where} places $stg_issue at "
                        f"{nested}, below the top level of the invoke input"
                    )
    elif kind == "write":
        nested = _nested_issue_site(step["value"], "value")
        if nested is not None:
            raise AdmissionRejected(
                f"issue_placement: step {sid!r} at {where} places $stg_issue at "
                f"{nested}, outside an invoke input"
            )


def _check_body_budget(docs: AdmittedDocuments) -> None:
    bound = worst_case_body_ms(docs.procedure["steps"])
    overhead = int(docs.commissioning["scheduling_overhead_ms"])
    limit = int(docs.procedure["max_body_ms"])
    if bound + overhead > limit:
        raise AdmissionRejected(
            f"body_budget: worst-case body {bound} ms plus scheduling overhead "
            f"{overhead} ms exceeds max_body_ms {limit}"
        )


def _check_energised(docs: AdmittedDocuments) -> None:
    transition = int(docs.policy["safe_transition"]["max_duration_ms"])
    max_body = int(docs.procedure["max_body_ms"])
    energised = min(int(domain["max_energised_ms"]) for domain in docs.policy["domains"])
    if max_body + transition > energised:
        raise AdmissionRejected(
            f"energised_budget: max_body_ms {max_body} plus safe transition "
            f"{transition} ms exceeds the smallest domain max_energised_ms {energised}"
        )


def _parse_utc(text: str, label: str) -> datetime:
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AdmissionRejected(
            f"expired: {label} {text!r} is not an ISO-8601 timestamp"
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


def _check_deadline(docs: AdmittedDocuments, now_wall: str) -> None:
    now = _parse_utc(now_wall, "now_wall")
    expires_at = str(docs.commissioning["expires_at"])
    deadline = _parse_utc(expires_at, "commissioning.expires_at")
    horizon = int(docs.procedure["max_body_ms"]) + int(docs.procedure["max_protection_ms"])
    if now + timedelta(milliseconds=horizon) > deadline:
        raise AdmissionRejected(
            f"expired: now_wall {now_wall} plus body and protection horizon {horizon} ms "
            f"exceeds commissioning expires_at {expires_at}"
        )


def check_semantics(docs: AdmittedDocuments, *, now_wall: str) -> None:
    """Enforce the contract's semantic rules over ``docs`` or reject.

    Raises :class:`AdmissionRejected` (from document admission, so callers
    catch one exception for the whole admission pipeline) before any dispatch:
    duplicate step IDs, out-of-scope references, misplaced ``$stg_issue``
    directives, and the three budget bounds — worst-case body, energised time
    and the commissioning deadline measured from ``now_wall``.
    """
    steps = docs.procedure["steps"]
    _check_unique_ids(steps)
    device_by_role = {
        str(binding["role"]): str(binding["device_id"]) for binding in docs.binding["bindings"]
    }
    for step, visible, block_id in _walk(steps, [], ""):
        _check_step(step, visible, block_id, docs.descriptors, device_by_role)
    _check_body_budget(docs)
    _check_energised(docs)
    _check_deadline(docs, now_wall)
