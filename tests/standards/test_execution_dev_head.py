"""The execution 0.2.0-dev head's controls (issue #176 increment 1).

The design record's pre-committed acceptance arms, replayed here:

- **A-R1** - the dev corpus admits capture; the frozen active 0.1.0
  corpus refuses the same documents; the capture branch is closed.
- **A-R2** - the dev tree differs from its 0.1.0 source by exactly the
  capture family: one step branch, one allow-rule branch, the prose
  sections, the examples' capture shapes; every pre-existing schema
  branch is canonical-equal to 0.1.0, the $stg_issue enum is untouched,
  and no version sweep ran (identity fields stay 0.1.0-shaped until the
  promotion sweep).
- **A-R3-prime** - the dev-stage honesty arms on a real head: SDK
  stillness, an unrepinned dev edit refused by the operator check
  surface by name, and a stripped head block leaving the directory as a
  derived-corpus stray.

The prime suffix marks the dev-stage replay of the record's A-R3; the
roll-up increment carries A-R3 unprimed (admission/policy through the
gateway) by design.
"""

from __future__ import annotations

import copy
import json
import math
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
STANDARDS = ROOT / "standards"
ACTIVE = STANDARDS / "execution" / "0.1.0"
HEAD = STANDARDS / "execution" / "0.2.0-dev"

BASE_STEP_KINDS = {"invoke", "read", "write", "delay", "sample", "assert", "if", "repeat"}
BASE_ALLOW_KINDS = {"invoke", "write"}
CAPTURE_FORMATS = ("waveform_f64le", "raw_binary")
CAPTURE_STEP_KEYS = {"id", "kind", "role", "format", "sample_count", "max_bytes", "timeout_ms"}
CAPTURE_RULE_KEYS = {"device_id", "kind", "format", "capture_constraints"}
PROSE_SECTIONS_CHANGED = {"header", "1", "3", "5", "7"}


# --- the capture documents -------------------------------------------------------


def _capture_procedure() -> dict[str, Any]:
    """A known-valid 0.1.0 procedure with one capture step inserted."""
    document: dict[str, Any] = json.loads((ACTIVE / "examples" / "procedure.json").read_bytes())
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
    """A known-valid 0.1.0 policy with one capture allow rule appended."""
    document: dict[str, Any] = json.loads((ACTIVE / "examples" / "safety-policy.json").read_bytes())
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


# --- A-R1: the differential -------------------------------------------------------


def test_dev_head_admits_the_capture_family() -> None:
    """The capture step and allow rule validate against the dev schemas."""
    procedure_schema = json.loads((HEAD / "procedure.schema.json").read_bytes())
    policy_schema = json.loads((HEAD / "safety-policy.schema.json").read_bytes())
    Draft202012Validator.check_schema(procedure_schema)
    Draft202012Validator.check_schema(policy_schema)
    procedure = Draft202012Validator(procedure_schema)
    policy = Draft202012Validator(policy_schema)

    errors = list(procedure.iter_errors(_capture_procedure()))
    assert not errors, f"capture step refused by the dev schema: {[e.message for e in errors]}"
    errors = list(policy.iter_errors(_capture_policy()))
    assert not errors, f"capture rule refused by the dev schema: {[e.message for e in errors]}"


def test_active_corpus_refuses_the_same_capture_documents() -> None:
    """The differential arm: the SAME documents fail against frozen 0.1.0.

    The inline capture documents and the dev example FILES (which carry
    the capture shapes) must all be invalid under the active 0.1.0
    schemas - the frozen corpus is the control the head must differ from.
    """
    active_procedure = Draft202012Validator(
        json.loads((ACTIVE / "procedure.schema.json").read_bytes())
    )
    active_policy = Draft202012Validator(
        json.loads((ACTIVE / "safety-policy.schema.json").read_bytes())
    )

    assert not active_procedure.is_valid(_capture_procedure())
    assert not active_policy.is_valid(_capture_policy())
    dev_procedure_example = json.loads((HEAD / "examples" / "procedure.json").read_bytes())
    dev_policy_example = json.loads((HEAD / "examples" / "safety-policy.json").read_bytes())
    assert not active_procedure.is_valid(dev_procedure_example)
    assert not active_policy.is_valid(dev_policy_example)

    # The refusals must name the capture family specifically (the refute
    # lane's verified probe): error paths at steps/3 (the capture step) and
    # allow_rules/2 (the capture rule), not merely a boolean invalid.
    proc_paths: set[tuple[Any, ...]] = set()
    pol_paths: set[tuple[Any, ...]] = set()

    def _collect(errs: list[Any], sink: set[tuple[Any, ...]]) -> None:
        for err in errs:
            sink.add(tuple(err.absolute_path))
            _collect(list(err.context), sink)

    _collect(list(active_procedure.iter_errors(dev_procedure_example)), proc_paths)
    _collect(list(active_policy.iter_errors(dev_policy_example)), pol_paths)
    assert any(p[:2] == ("steps", 3) for p in proc_paths), sorted(map(str, proc_paths))
    assert any(p[:2] == ("allow_rules", 2) for p in pol_paths), sorted(map(str, pol_paths))


def test_capture_branch_shapes_are_closed() -> None:
    """Negative shapes refuse in the dev lane (the record's A-R1 list)."""
    procedure = Draft202012Validator(
        json.loads((HEAD / "procedure.schema.json").read_bytes())
    )
    policy = Draft202012Validator(
        json.loads((HEAD / "safety-policy.schema.json").read_bytes())
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
    mutant["steps"][3]["sample_count"] = 1000
    mutant["steps"][3]["max_bytes"] = 0
    assert not procedure.is_valid(mutant)
    # The rule branch is closed the same way: a device-wide capture rule
    # (invoke's action_id vocabulary) is unrepresentable.
    wide_rule = _capture_policy()
    wide_rule["allow_rules"][-1]["action_id"] = "otdp.dc_psu.measure/1.0.0"
    assert not policy.is_valid(wide_rule)


# --- A-R2: the diff is exactly the capture family ---------------------------------

#: F7's contract ceiling: the ONE sanctioned non-capture schema diff the
#: head carries over 0.1.0 — a finite authoring bound (one day) on every
#: ``timeout_ms`` and the two top-level budgets, stated in contract §5.
PROCEDURE_CEILING_MS = 86_400_000


def test_contract_ceiling_bounds_timeouts_and_budgets() -> None:
    """F7: the head's finite contract ceiling — every ``timeout_ms`` (the
    four step kinds that carry one) and ``max_body_ms``/``max_protection_ms``
    carry ``maximum``; the active corpus carries none. A schema-valid
    ``timeout_ms`` at the ceiling converts through the bridge's
    ``deadline_ns / 1_000_000_000`` without overflow; one step above the
    ceiling is refused by the schema."""
    head = json.loads((HEAD / "procedure.schema.json").read_bytes())
    active = json.loads((ACTIVE / "procedure.schema.json").read_bytes())
    head_timeouts = [
        branch["properties"]["timeout_ms"]
        for branch in head["$defs"]["step"]["oneOf"]
        if "timeout_ms" in branch.get("properties", {})
    ]
    assert len(head_timeouts) == 4  # invoke, read, write, capture
    for prop in head_timeouts:
        assert prop["maximum"] == PROCEDURE_CEILING_MS
    for key in ("max_body_ms", "max_protection_ms"):
        assert head["properties"][key]["maximum"] == PROCEDURE_CEILING_MS
        assert "maximum" not in active["properties"][key]  # head-only
    for branch in active["$defs"]["step"]["oneOf"]:
        if "timeout_ms" in branch.get("properties", {}):
            assert "maximum" not in branch["properties"]["timeout_ms"]

    # Schema-valid AT the ceiling; refused ABOVE it.
    validator = Draft202012Validator(head)
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


def test_dev_head_diff_is_exactly_the_capture_family() -> None:
    """The shape argument, mechanical: one branch each, nothing else moves.

    Every pre-existing schema branch is byte-identical (canonical deep
    equality preserves oneOf order) ONCE F7's contract ceiling is cleared
    from both sides — the ceiling is the one sanctioned non-capture
    schema diff, asserted present and head-only by
    ``test_contract_ceiling_bounds_timeouts_and_budgets`` — the
    ``$stg_issue`` enum is untouched, the version consts and ``$id``s stay
    0.1.0-shaped (no sweep), the examples gain exactly one capture step
    and one capture rule, and the prose moved only in the sections the
    record names.
    """
    old_procedure = json.loads((ACTIVE / "procedure.schema.json").read_bytes())
    new_procedure = json.loads((HEAD / "procedure.schema.json").read_bytes())
    old_policy = json.loads((ACTIVE / "safety-policy.schema.json").read_bytes())
    new_policy = json.loads((HEAD / "safety-policy.schema.json").read_bytes())
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

    # No version sweep: identity fields are the 0.1.0 bytes.
    for new_doc, old_doc in ((new_procedure, old_procedure), (new_policy, old_policy)):
        assert (
            new_doc["properties"]["contract_version"]["const"]
            == old_doc["properties"]["contract_version"]["const"]
        )
        assert new_doc["$id"] == old_doc["$id"]
        assert new_doc["title"] == old_doc["title"]

    # $defs/value untouched: the whole subtree byte-identical, and the
    # $stg_issue enum still names exactly the two issued-id kinds.
    assert new_procedure["$defs"]["value"] == old_procedure["$defs"]["value"]
    issue_variants = _by_kind(  # kind key does not exist here; use $stg_issue
        new_procedure["$defs"]["value"]["oneOf"], "capture"
    )
    assert issue_variants == []
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

    # The dev document minus its new branch IS the 0.1.0 document.
    swept_procedure = copy.deepcopy(new_procedure)
    swept_procedure["$defs"]["step"]["oneOf"] = old_steps
    assert swept_procedure == old_procedure
    swept_policy = copy.deepcopy(new_policy)
    swept_policy["properties"]["allow_rules"]["items"]["oneOf"] = old_rules
    assert swept_policy == old_policy

    # The examples gain exactly the capture shapes.
    old_example = json.loads((ACTIVE / "examples" / "procedure.json").read_bytes())
    new_example = json.loads((HEAD / "examples" / "procedure.json").read_bytes())
    old_rules_example = json.loads((ACTIVE / "examples" / "safety-policy.json").read_bytes())
    new_rules_example = json.loads((HEAD / "examples" / "safety-policy.json").read_bytes())
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
    assert len(capture_example_rules) == 1
    assert [r for r in new_rules_example["allow_rules"] if r.get("kind") != "capture"] == (
        old_rules_example["allow_rules"]
    )
    assert set(capture_example_rules[0]) == CAPTURE_RULE_KEYS

    # The digest cascade: the dependent examples differ from 0.1.0 ONLY in
    # embedded sha256 pins. Editing the two capture-bearing examples forces
    # every cross-document pin naming them to move in-arc; the package-lock
    # pins (the zero digests) do not move and are covered by the lane's
    # consistency check.
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
        old_doc = json.loads((ACTIVE / "examples" / (name + ".json")).read_bytes())
        new_doc = json.loads((HEAD / "examples" / (name + ".json")).read_bytes())
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
        assert new_doc == old_doc, f"{name}.json moved non-pin bytes"

    # The prose companions: exactly the named sections moved.
    old_prose = _sections(ACTIVE / "execution-contract.md")
    new_prose = _sections(HEAD / "execution-contract.md")
    assert set(new_prose) == set(old_prose)
    changed = {name for name in old_prose if old_prose[name] != new_prose[name]}
    assert changed <= PROSE_SECTIONS_CHANGED, changed


# --- A-R1: the dev-proof lane ------------------------------------------------------


def test_dev_proof_lane_runs_the_head_green(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_execution.py --corpus <declared head>: every check passes
    and the run writes nothing (a dev run is a check, not a report)."""
    report = HEAD / "validation-report.md"
    # The stale founding copy was folded away: a dev head carries no
    # validation report (reports are a released-version property), and the
    # lane must not write one either.
    assert not report.exists(), "the dev head carries no validation report"
    monkeypatch.setattr(
        sys, "argv", ["check_execution.py", "--corpus", str(HEAD.resolve())]
    )
    namespace = runpy.run_path(
        str(ROOT / "scripts" / "architecture" / "check_execution.py"),
        init_globals={"DOCS": ROOT / "docs", "STANDARDS": STANDARDS},
    )
    assert namespace["CONTRACT_DIR"] == HEAD.resolve()
    checks = [(str(name), bool(ok)) for name, ok in namespace["CHECKS"]]
    assert checks, "no checks executed"
    failures = [name for name, ok in checks if not ok]
    assert not failures, f"{len(failures)}/{len(checks)} failed:\n" + "\n".join(failures)
    assert not report.exists(), "a dev run must not write a report"


# --- A-R3-prime: the dev-stage honesty arms on a real head -------------------------


def test_sdk_tree_is_still_across_the_head() -> None:
    """SDK stillness: no head commit moves packages/sdk bytes, and the
    operator round-trip (bundle, lock, vendored tree, compatibility
    mirror) is clean - the invisibility tripwire."""
    # Scope is head commits, not the branch diff: a legitimate pointer
    # advance (fork (a)'s #187 mirror+pointer pairing) moves packages/sdk
    # without touching the head and must not trip this. The branch-wide
    # diff was the wrong scope - it only ever discriminated on branches
    # that never moved the pointer.
    head_commits = subprocess.run(
        [
            "git",
            "log",
            "--format=%H",
            "origin/main..HEAD",
            "--",
            "standards/execution/0.2.0-dev",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert head_commits.returncode == 0, head_commits.stderr
    for commit in head_commits.stdout.split():
        files = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert files.returncode == 0, files.stderr
        assert "packages/sdk" not in files.stdout.splitlines(), (
            f"head commit {commit[:10]} moves SDK bytes:\n{files.stdout}"
        )
    round_trip = subprocess.run(
        [sys.executable, "-m", "benchweave.standards", "check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = round_trip.stdout + round_trip.stderr
    assert round_trip.returncode == 0, combined
    assert "standards check clean" in combined


def test_unrepinned_dev_edit_fails_check_naming_the_dev_path() -> None:
    """An unrepinned dev byte is refused by the operator surface by name.

    The sabotage lives only inside the test and is restored in a finally
    block; the pinned state is untouched across the probe.
    """
    target = HEAD / "procedure.schema.json"
    original = target.read_bytes()
    assert original == target.read_bytes()
    try:
        target.write_bytes(original + b" ")
        probe = subprocess.run(
            [sys.executable, "-m", "benchweave.standards", "check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = probe.stdout + probe.stderr
        assert probe.returncode == 1, combined
        assert "normative_hash_mismatch: standards/execution/0.2.0-dev/" in combined
    finally:
        target.write_bytes(original)


def test_head_block_removal_leaves_the_dev_dir_stray() -> None:
    """The forgetfulness arm: stripping the dev block while the directory
    and its rows remain fires the derived corpus-dir guard, naming the
    head - an undeclared staging directory cannot launder admission."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "test_baseline_under_test",
        ROOT / "tests" / "contract" / "test_baseline.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _corpus_dir_justification = module._corpus_dir_justification

    manifest = json.loads((STANDARDS / "standards-manifest.json").read_bytes())
    for entry in manifest["standards"]:
        if entry["id"] == "execution":
            entry.pop("dev")
    corpus = json.loads((STANDARDS / "corpus-manifest.json").read_bytes())
    stray, missing = _corpus_dir_justification(manifest, corpus["files"])
    assert stray == ["execution/0.2.0-dev"], stray
    assert missing == []
