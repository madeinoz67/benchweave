"""The execution 0.2.0 promotion's corpus controls (issue #176).

The train developed against the 0.2.0-dev head (increment 1's controls,
``tests/standards/test_execution_dev_head.py``, retired at the promotion
event); these are the released corpus's arms, reconciled at the promotion:

- **A-R1, promoted** - the released 0.2.0 corpus admits the capture
  family; the retained frozen 0.1.0 corpus still refuses it (the
  differential survives as the retention story, refusal paths naming the
  capture step and the capture rule specifically).
- **A-R2, promoted** - the released tree differs from its 0.1.0
  predecessor by exactly: the capture family (one step branch, one
  allow-rule branch, the examples' capture shapes, the prose sections),
  the F7 contract ceiling, and the version sweep (contract_version
  consts, ``$id``s, titles, the examples' ``contract_version`` fields,
  and the digest cascade the sweep forces). Nothing else moves.
- **Self-retirement** - the ``--corpus`` dev-proof lane and the runtime
  seam both refuse now that no head is declared: the lane cannot validate
  a directory the manifest does not declare, and a stray ``DEV_HEAD``
  composition cannot resolve.

Retired with the head, each with its surviving synthetic coverage named:
the SDK-stillness arm (no head commits can exist; the promotion's SDK
motion is the sanctioned lock sync, pinned by the SDK lock and the
gateway round-trip), the unrepinned-dev-edit arm
(``tests/standards/test_repin.py``'s dev-row arms), and the stripped-block
stray arm (``tests/contract/test_baseline.py``'s derived-corpus-dir guard).
"""

from __future__ import annotations

import copy
import json
import math
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from benchweave.vendoring import declared_dev_family

ROOT = Path(__file__).resolve().parents[2]
STANDARDS = ROOT / "standards"
RELEASED = STANDARDS / "execution" / "0.2.0"
RETAINED = STANDARDS / "execution" / "0.1.0"

BASE_STEP_KINDS = {"invoke", "read", "write", "delay", "sample", "assert", "if", "repeat"}
BASE_ALLOW_KINDS = {"invoke", "write"}
CAPTURE_FORMATS = ("waveform_f64le", "raw_binary")
CAPTURE_STEP_KEYS = {"id", "kind", "role", "format", "sample_count", "max_bytes", "timeout_ms"}
CAPTURE_RULE_KEYS = {"device_id", "kind", "format", "capture_constraints"}
PROSE_SECTIONS_CHANGED = {"header", "1", "3", "5", "7"}


# --- the capture documents -------------------------------------------------------


def _capture_procedure() -> dict[str, Any]:
    """A 0.1.0-shaped procedure with one capture step inserted (the
    predecessor's example, mutated additively — the pre-promotion idiom
    kept so the differential stays exact), with the contract_version
    swept to 0.2.0 so the released schema's const admits it."""
    document: dict[str, Any] = json.loads((RETAINED / "examples" / "procedure.json").read_bytes())
    document["contract_version"] = "0.2.0"
    document["steps"].insert(
        3,
        {
            "id": "capture-trace",
            "kind": "capture",
            "role": "supply",
            "format": "waveform_f64le",
            "sample_count": 1000,
            "max_bytes": 65536,
            "timeout_ms": 400,
        },
    )
    return document


def _capture_policy() -> dict[str, Any]:
    """A 0.1.0-shaped policy with one capture allow rule appended, with
    the contract_version swept to 0.2.0 so the released schema's const
    admits it."""
    document: dict[str, Any] = json.loads(
        (RETAINED / "examples" / "safety-policy.json").read_bytes()
    )
    document["contract_version"] = "0.2.0"
    document["allow_rules"].append(
        {
            "device_id": "psu",
            "kind": "capture",
            "format": "waveform_f64le",
            "capture_constraints": {
                "type": "object",
                "properties": {
                    "sample_count": {"maximum": 1000},
                    "max_bytes": {"maximum": 65536},
                },
            },
        }
    )
    return document


def _sections(path: Path) -> dict[str, str]:
    """Split the contract prose into its ``## `` sections (header, then ids)."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("\n## ")
    sections = {"header": parts[0]}
    for part in parts[1:]:
        title = part.split("\n", 1)[0].strip()
        sections[title.split(".")[0].split(" ")[0]] = part
    return sections


# --- A-R1, promoted: the differential ----------------------------------------------


def test_released_corpus_admits_the_capture_family() -> None:
    """The capture step and allow rule validate against the released
    0.2.0 schemas — the corpus-level activation proof."""
    procedure_schema = json.loads((RELEASED / "procedure.schema.json").read_bytes())
    policy_schema = json.loads((RELEASED / "safety-policy.schema.json").read_bytes())
    Draft202012Validator.check_schema(procedure_schema)
    Draft202012Validator.check_schema(policy_schema)
    procedure = Draft202012Validator(procedure_schema)
    policy = Draft202012Validator(policy_schema)

    errors = list(procedure.iter_errors(_capture_procedure()))
    assert not errors, f"capture step refused by the 0.2.0 schema: {[e.message for e in errors]}"
    errors = list(policy.iter_errors(_capture_policy()))
    assert not errors, f"capture rule refused by the 0.2.0 schema: {[e.message for e in errors]}"


def test_retained_corpus_refuses_the_same_capture_documents() -> None:
    """The differential arm, promoted: frozen 0.1.0 still refuses the
    SAME documents 0.2.0 admits.

    The inline capture documents and the released example FILES (which
    carry the capture shapes) must all be invalid under the retained
    0.1.0 schemas - retention is what keeps the differential checkable.
    """
    retained_procedure = Draft202012Validator(
        json.loads((RETAINED / "procedure.schema.json").read_bytes())
    )
    retained_policy = Draft202012Validator(
        json.loads((RETAINED / "safety-policy.schema.json").read_bytes())
    )

    assert not retained_procedure.is_valid(_capture_procedure())
    assert not retained_policy.is_valid(_capture_policy())
    released_procedure_example = json.loads((RELEASED / "examples" / "procedure.json").read_bytes())
    released_policy_example = json.loads(
        (RELEASED / "examples" / "safety-policy.json").read_bytes()
    )
    assert not retained_procedure.is_valid(released_procedure_example)
    assert not retained_policy.is_valid(released_policy_example)

    # The refusals must name the capture family specifically (the refute
    # lane's verified probe): error paths at steps/3 (the capture step) and
    # allow_rules/2 (the capture rule), not merely a boolean invalid.
    proc_paths: set[tuple[Any, ...]] = set()
    pol_paths: set[tuple[Any, ...]] = set()

    def _collect(errs: list[Any], sink: set[tuple[Any, ...]]) -> None:
        for err in errs:
            sink.add(tuple(err.absolute_path))
            _collect(list(err.context), sink)

    _collect(list(retained_procedure.iter_errors(released_procedure_example)), proc_paths)
    _collect(list(retained_policy.iter_errors(released_policy_example)), pol_paths)
    assert any(p[:2] == ("steps", 3) for p in proc_paths), sorted(map(str, proc_paths))
    assert any(p[:2] == ("allow_rules", 2) for p in pol_paths), sorted(map(str, pol_paths))


def test_capture_branch_shapes_are_closed() -> None:
    """Negative shapes refuse against the released schemas (the record's
    A-R1 list, now a property of the active corpus)."""
    procedure = Draft202012Validator(
        json.loads((RELEASED / "procedure.schema.json").read_bytes())
    )
    policy = Draft202012Validator(
        json.loads((RELEASED / "safety-policy.schema.json").read_bytes())
    )

    valid = _capture_procedure()
    assert procedure.is_valid(valid)

    # Unknown field on the capture branch: additionalProperties false.
    unknown_field = copy.deepcopy(valid)
    unknown_field["steps"][3]["capture_id"] = "host-minted-must-not-be-authored"
    assert not procedure.is_valid(unknown_field)
    # Missing timeout_ms: the capture budget is required (Amendment 3).
    no_budget = copy.deepcopy(valid)
    del no_budget["steps"][3]["timeout_ms"]
    assert not procedure.is_valid(no_budget)
    # Format outside the core-lane enum; non-positive bounds.
    mutant = copy.deepcopy(valid)
    mutant["steps"][3]["format"] = "waveform_f32le"
    assert not procedure.is_valid(mutant)
    mutant["steps"][3]["format"] = "waveform_f64le"
    mutant["steps"][3]["sample_count"] = 0
    assert not procedure.is_valid(mutant)
    mutant["steps"][3]["max_bytes"] = 0
    assert not procedure.is_valid(mutant)
    # The rule branch is closed the same way: a device-wide capture rule
    # (invoke's action_id vocabulary) is unrepresentable.
    wide_rule = _capture_policy()
    wide_rule["allow_rules"][-1]["action_id"] = "otdp.dc_psu.measure/1.0.0"
    assert not policy.is_valid(wide_rule)


# --- A-R2, promoted: the diff is the family plus the sweep -------------------------


#: F7's contract ceiling: the ONE sanctioned non-capture schema diff — a
#: finite authoring bound (one day) on every ``timeout_ms`` and the two
#: top-level budgets, stated in contract §5.
PROCEDURE_CEILING_MS = 86_400_000


def test_contract_ceiling_bounds_timeouts_and_budgets() -> None:
    """F7: the released corpus's finite contract ceiling — every
    ``timeout_ms`` (the four step kinds that carry one) and
    ``max_body_ms``/``max_protection_ms`` carry ``maximum``; the retained
    0.1.0 corpus carries none. A schema-valid ``timeout_ms`` at the
    ceiling converts through the bridge's ``deadline_ns / 1_000_000_000``
    without overflow; one step above the ceiling is refused by the
    schema."""
    released = json.loads((RELEASED / "procedure.schema.json").read_bytes())
    retained = json.loads((RETAINED / "procedure.schema.json").read_bytes())
    released_timeouts = [
        branch["properties"]["timeout_ms"]
        for branch in released["$defs"]["step"]["oneOf"]
        if "timeout_ms" in branch.get("properties", {})
    ]
    assert len(released_timeouts) == 4  # invoke, read, write, capture
    for prop in released_timeouts:
        assert prop["maximum"] == PROCEDURE_CEILING_MS
    for key in ("max_body_ms", "max_protection_ms"):
        assert released["properties"][key]["maximum"] == PROCEDURE_CEILING_MS
        assert "maximum" not in retained["properties"][key]  # 0.2.0-only
    for branch in retained["$defs"]["step"]["oneOf"]:
        if "timeout_ms" in branch.get("properties", {}):
            assert "maximum" not in branch["properties"]["timeout_ms"]

    # Schema-valid AT the ceiling; refused ABOVE it.
    validator = Draft202012Validator(released)
    at = _capture_procedure()
    at["max_body_ms"] = PROCEDURE_CEILING_MS
    at["max_protection_ms"] = PROCEDURE_CEILING_MS
    for step in at["steps"]:
        if "timeout_ms" in step:
            step["timeout_ms"] = PROCEDURE_CEILING_MS
    assert validator.is_valid(at)
    over = copy.deepcopy(at)
    over["steps"][3]["timeout_ms"] = PROCEDURE_CEILING_MS + 1
    assert not validator.is_valid(over)

    # The conversion the bridge performs (otdp_bridge.dispatch's
    # ``deadline_ns / 1_000_000_000``) never raises for a schema-valid
    # value: the ceiling keeps it orders of magnitude inside float64.
    deadline_ns = 1_000_000_000 + PROCEDURE_CEILING_MS * 1_000_000
    deadline = deadline_ns / 1_000_000_000
    assert math.isfinite(deadline)


def _clear_ceiling(doc: dict[str, Any]) -> None:
    """Remove F7's sanctioned ceiling diff so the byte-identity claims
    below compare everything EXCEPT it."""
    for branch in doc["$defs"]["step"]["oneOf"]:
        prop = branch.get("properties", {}).get("timeout_ms")
        if isinstance(prop, dict):
            prop.pop("maximum", None)
    for key in ("max_body_ms", "max_protection_ms"):
        prop = doc["properties"].get(key)
        if isinstance(prop, dict):
            prop.pop("maximum", None)


def test_promoted_diff_is_the_capture_family_plus_the_sweep() -> None:
    """The shape argument, mechanical: the family, the ceiling, the sweep.

    Every pre-existing schema branch is byte-identical (canonical deep
    equality preserves oneOf order) ONCE F7's contract ceiling is cleared
    from both sides. The version sweep is the other sanctioned diff: the
    contract_version consts, the ``$id``s and the titles carry 0.2.0, the
    examples gain exactly one capture step and one capture rule plus the
    cascade pins their sweep forces, and the prose moved only in the
    sections the record names (header included — the title swept).
    """
    old_procedure = json.loads((RETAINED / "procedure.schema.json").read_bytes())
    new_procedure = json.loads((RELEASED / "procedure.schema.json").read_bytes())
    old_policy = json.loads((RETAINED / "safety-policy.schema.json").read_bytes())
    new_policy = json.loads((RELEASED / "safety-policy.schema.json").read_bytes())
    # F7's ceiling is the one sanctioned non-capture schema diff: clear it
    # on both sides, then every byte-identity claim below holds exactly as
    # the design record's A-R2 states it (amended to name the ceiling).
    _clear_ceiling(old_procedure)
    _clear_ceiling(new_procedure)

    old_steps = old_procedure["$defs"]["step"]["oneOf"]
    new_steps = new_procedure["$defs"]["step"]["oneOf"]

    def _by_kind(branches: list[Any], kind: str) -> list[dict[str, Any]]:
        return [
            b
            for b in branches
            if isinstance(b, dict) and b.get("properties", {}).get("kind", {}).get("const") == kind
        ]

    capture_branches = _by_kind(new_steps, "capture")
    assert len(new_steps) == len(old_steps) + 1
    assert len(capture_branches) == 1
    capture_branch = capture_branches[0]
    # Pre-existing branches, in their original order, byte-identical.
    assert [b for b in new_steps if b is not capture_branch] == old_steps
    assert {b["properties"]["kind"]["const"] for b in new_steps} == BASE_STEP_KINDS | {"capture"}

    old_rules = old_policy["properties"]["allow_rules"]["items"]["oneOf"]
    new_rules = new_policy["properties"]["allow_rules"]["items"]["oneOf"]
    capture_rules = _by_kind(new_rules, "capture")
    assert len(new_rules) == len(old_rules) + 1
    assert len(capture_rules) == 1
    capture_rule = capture_rules[0]
    assert [b for b in new_rules if b is not capture_rule] == old_rules
    assert {b["properties"]["kind"]["const"] for b in new_rules} == BASE_ALLOW_KINDS | {"capture"}

    # The capture branches themselves: closed, exact key sets, required.
    assert set(capture_branch["properties"]) == CAPTURE_STEP_KEYS
    assert set(capture_branch["required"]) == CAPTURE_STEP_KEYS
    assert capture_branch["additionalProperties"] is False
    assert set(capture_rule["properties"]) == CAPTURE_RULE_KEYS
    assert set(capture_rule["required"]) == CAPTURE_RULE_KEYS
    assert capture_rule["additionalProperties"] is False

    # The version sweep: identity fields moved exactly to 0.2.0 — the
    # consts and the $ids (fork-3: track the standard version). Schema
    # titles are version-free constants; the PROSE companion carries the
    # swept title (asserted in the prose section below).
    for new_doc in (new_procedure, new_policy):
        assert new_doc["properties"]["contract_version"]["const"] == "0.2.0"
        assert new_doc["$id"].endswith(":0.2.0")
    # ... and ONLY the sweep moved there: with identity fields cleared to
    # the retained shapes, the remaining diff is the capture family alone.
    for new_doc, old_doc in ((new_procedure, old_procedure), (new_policy, old_policy)):
        cleared = copy.deepcopy(new_doc)
        cleared["properties"]["contract_version"]["const"] = (
            old_doc["properties"]["contract_version"]["const"]
        )
        cleared["$id"] = old_doc["$id"]
        cleared["title"] = old_doc["title"]
        assert cleared != old_doc  # the capture branch (procedure) / rule (policy)
        assert set(cleared["properties"]) == set(old_doc["properties"])
    # $defs/value untouched: the whole subtree byte-identical, and the
    # $stg_issue enum still names exactly the two issued-id kinds.
    assert new_procedure["$defs"]["value"] == old_procedure["$defs"]["value"]
    stg_issue_variants = [
        v
        for v in new_procedure["$defs"]["value"]["oneOf"]
        if isinstance(v, dict) and "$stg_issue" in v.get("properties", {})
    ]
    assert len(stg_issue_variants) == 1
    assert stg_issue_variants[0]["properties"]["$stg_issue"]["enum"] == [
        "configuration_id",
        "acquisition_id",
    ]

    # The released document minus its new branch, with identity cleared,
    # IS the retained document (the family + sweep is the whole diff).
    swept_procedure = copy.deepcopy(new_procedure)
    swept_procedure["$defs"]["step"]["oneOf"] = old_steps
    _clear_sweep(swept_procedure, old_procedure)
    assert swept_procedure == old_procedure
    swept_policy = copy.deepcopy(new_policy)
    swept_policy["properties"]["allow_rules"]["items"]["oneOf"] = old_rules
    _clear_sweep(swept_policy, old_policy)
    assert swept_policy == old_policy

    # The examples gain exactly the capture shapes + the sweep + cascade.
    old_example = json.loads((RETAINED / "examples" / "procedure.json").read_bytes())
    new_example = json.loads((RELEASED / "examples" / "procedure.json").read_bytes())
    old_rules_example = json.loads((RETAINED / "examples" / "safety-policy.json").read_bytes())
    new_rules_example = json.loads((RELEASED / "examples" / "safety-policy.json").read_bytes())
    assert new_example["contract_version"] == "0.2.0"
    assert new_rules_example["contract_version"] == "0.2.0"
    capture_example_steps = [s for s in new_example["steps"] if s.get("kind") == "capture"]
    assert len(new_example["steps"]) == len(old_example["steps"]) + 1
    assert len(capture_example_steps) == 1
    assert [s for s in new_example["steps"] if s.get("kind") != "capture"] == old_example["steps"]
    assert set(capture_example_steps[0]) == CAPTURE_STEP_KEYS
    assert capture_example_steps[0]["format"] in CAPTURE_FORMATS
    capture_example_rules = [
        r for r in new_rules_example["allow_rules"] if r.get("kind") == "capture"
    ]
    assert len(new_rules_example["allow_rules"]) == len(old_rules_example["allow_rules"]) + 1
    assert len(capture_rules) == 1
    assert [r for r in new_rules_example["allow_rules"] if r.get("kind") != "capture"] == (
        old_rules_example["allow_rules"]
    )
    assert set(capture_example_rules[0]) == CAPTURE_RULE_KEYS

    # The digest cascade: the dependent examples differ from 0.1.0 ONLY in
    # embedded sha256 pins (plus the swept contract_version, cleared with
    # the pins before the byte-identity compare). Editing the two
    # capture-bearing examples forces every cross-document pin naming
    # them to move in-arc; the package-lock pins (the zero digests) do
    # not move and are covered by the lane's consistency check.
    cascade_pins: dict[str, list[tuple[Any, ...]]] = {
        "bench": [("policy", "sha256")],
        "commissioning": [
            ("bench", "sha256"),
            ("policy", "sha256"),
            ("procedure_refs", 0, "sha256"),
        ],
        "run-binding": [
            ("procedure", "sha256"),
            ("bench", "sha256"),
            ("policy", "sha256"),
            ("commissioning", "sha256"),
        ],
        "run-record": [("binding", "sha256")],
    }

    def _pin_value(doc: dict[str, Any], path: tuple[Any, ...]) -> Any:
        target = doc
        for key in path[:-1]:
            target = target[key]
        return target[path[-1]]

    def _clear_pin(doc: dict[str, Any], path: tuple[Any, ...]) -> None:
        target = doc
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = None

    for name, pins in cascade_pins.items():
        old_doc = json.loads((RETAINED / "examples" / (name + ".json")).read_bytes())
        new_doc = json.loads((RELEASED / "examples" / (name + ".json")).read_bytes())
        assert new_doc["contract_version"] == "0.2.0"
        moved = False
        for path in pins:
            old_value = _pin_value(old_doc, path)
            new_value = _pin_value(new_doc, path)
            assert isinstance(old_value, str) and isinstance(new_value, str)
            if old_value != new_value:
                moved = True
            _clear_pin(old_doc, path)
            _clear_pin(new_doc, path)
        assert moved, f"{name}.json carries no moved pin"
        old_doc["contract_version"] = None
        new_doc["contract_version"] = None
        assert new_doc == old_doc, f"{name}.json moved non-pin bytes"

    # The prose companions: exactly the named sections moved (the header
    # carries the swept title).
    old_prose = _sections(RETAINED / "execution-contract.md")
    new_prose = _sections(RELEASED / "execution-contract.md")
    assert set(new_prose) == set(old_prose)
    changed = {name for name in old_prose if old_prose[name] != new_prose[name]}
    assert changed <= PROSE_SECTIONS_CHANGED, changed


def _clear_sweep(doc: dict[str, Any], reference: dict[str, Any]) -> None:
    """Rewrite the swept identity fields back to the retained shapes so
    the final equality isolates exactly the capture family."""
    doc["properties"]["contract_version"]["const"] = (
        reference["properties"]["contract_version"]["const"]
    )
    doc["$id"] = reference["$id"]
    doc["title"] = reference["title"]


# --- self-retirement: the lane and the seam refuse together ------------------------


def test_dev_proof_lane_self_retires_with_the_head() -> None:
    """check_execution.py --corpus <the retired head path>: the lane
    refuses — reports are a released-version property, and the override
    accepts exactly the manifest-declared head, which no longer exists.
    The refusal names the override, not a stale-pin drift."""
    retired_head = STANDARDS / "execution" / "0.2.0-dev"
    assert not retired_head.exists(), "the promotion tore the head down"
    sys.argv = ["check_execution.py", "--corpus", str(retired_head.resolve())]
    try:
        with pytest.raises(SystemExit) as stopped:
            runpy.run_path(
                str(ROOT / "scripts" / "architecture" / "check_execution.py"),
                init_globals={"DOCS": ROOT / "docs", "STANDARDS": STANDARDS},
            )
    finally:
        sys.argv = ["check_execution.py"]
    message = str(stopped.value)
    assert "execution_dev_head_absent:" in message, message
    # Never-a-fallback, stated in the refusal itself: the active corpus is
    # not offered as a substitute for the deleted head.
    assert "execution/0.2.0" not in message


def test_stray_dev_head_composition_refuses() -> None:
    """The seam's self-retirement is live truth: on the post-promotion
    manifest (no dev block), a stray ``DEV_HEAD`` resolution refuses —
    it never falls back to the active corpus."""
    with pytest.raises(ValueError, match="execution_dev_head_absent:"):
        declared_dev_family("execution")
