# WP05 — Procedure Admission, Execution and Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The controlling spec is the planning pack (00–04) plus `docs/execution-v1.0.0/execution-contract.md` and the vendored `contracts/execution-v1.0.0/` schemas; `ISA.md` at the repo root holds the verifiable bar (ISC-1…ISC-22).

**Goal:** Ship `src/benchweave/control/` — procedure admission, binding/ownership, the eight-kind execution engine, policy enforcement and the protection/terminal pipeline — over the WP03 store and WP04 host ABI, verified by `tests/integration/test_procedures.py` and `tests/faults/test_protection.py`.

**Architecture:** Documents are admitted strictly (exact bytes → vendored Draft 2020-12 schemas → semantic admission incl. lexical scope and budgets). A coordinator owns the run lifecycle `accepted → running → protecting → terminal`, takes the bench lease from the WP03 store, drives the sim plugins only through `DevicePlugin.dispatch` under monotonic deadlines, evaluates the safety policy at dispatch and continuously, executes the fixed-deadline safe transition on every body end, and finalises a run record that validates against `run-record.schema.json`. Time is injected everywhere (monotonic + wall clocks as ports); the store receives caller-supplied timestamps and never sits inside device I/O.

**Tech Stack:** Python 3.13 (CPython, uv-managed), stdlib `sqlite3` via existing `benchweave.state.store`, `jsonschema` 4.26 + `referencing` (already dev deps), pytest 9.1. Gates: `uv run pytest`, `uv run ruff check .`, `uv run mypy` (strict, files = src+tests+plugins per pyproject).

## Global Constraints

- Schemas in `contracts/execution-v1.0.0/` are structure-only; the semantic rules in `docs/execution-v1.0.0/execution-contract.md` (§2–§9, checks P01–P10) are mandatory. JSON validity grants no authority.
- Parsers reject duplicate keys, nonfinite numbers and unknown ordinary fields — every control-layer document load goes through `benchweave.content.json_document` (exact-byte decode).
- No arbitrary code in procedures, no raw-device bypass, no hidden plugin I/O, no automatic retry of uncertain physical actions, no automatic resume after restart, no user-authored cleanup.
- Commit acceptance before dispatch; no DB transaction open during device I/O; store timestamps are caller-supplied.
- Device work only via `DevicePlugin.dispatch(request, deadline_ns=...)`; dispatch-state honesty preserved end-to-end.
- One RED→GREEN slice per commit. Gates run under `set -o pipefail` and MUST pass BEFORE every commit: `uv run pytest && uv run ruff check . && uv run mypy`.
- Gortex-first repo access for reads AND writes (`mcp__gortex__read`/`edit`); Bash only for gates and git.
- Non-dot venv (`UV_PROJECT_ENVIRONMENT=venv`, already in `~/.zshrc`); if the editable install rots, heal with `uv sync --reinstall-package benchweave`, else `rm -rf .venv && uv sync`.
- Line length 100 (ruff), mypy strict — no `Any` leaks, no untyped defs.
- Third-party AI-tool droppings in the worktree root (`.agents/`, `.continue/`, `.gemini/`, `.opencode/`, `.pi/`, `GEMINI.md`, `opencode.json`, `.github/copilot-instructions.md`, `.github/skills/`) stay untracked; never `git add` them.

## File Structure

| File | Responsibility |
|---|---|
| `plugins/sim_psu/plugin.py` (modify) | Add the three dc_psu class actions (configure/output/measure) as INVOKE verbs returning typed results incl. an admitted `scalar_set` |
| `fixtures/protocols/sim_psu_vectors.json` (modify) | Invoke + invoke-fault vectors |
| `fixtures/execution/*.json` (create) | Executable procedure, safety-policy, bench, run-binding, commissioning + two device descriptors — genuinely runnable, real sha256 pins |
| `src/benchweave/control/__init__.py` (create) | Package surface re-exports |
| `src/benchweave/control/clocking.py` | `MonotonicClock`/`WallClock` ports + `TestClock` (virtual, deterministic) |
| `src/benchweave/control/documents.py` | Strict loaders: exact-byte decode → vendored schema validation → digest pinning across the five documents |
| `src/benchweave/control/semantics.py` | Semantic admission: unique IDs, lexical scope, `$stg_issue` placement, worst-case body bound, qualification budget |
| `src/benchweave/control/binding.py` | Role→device resolution, profile/action/parameter declared-ness, resource transitive closure, reservation + lease |
| `src/benchweave/control/policy.py` | Allow-rule intersection at dispatch; continuous-condition evaluation with conservative intervals and V×A product |
| `src/benchweave/control/executor.py` | Eight-kind interpreter: occurrence ledger, reference resolution, three-valued predicates, trustworthy samples, body deadline |
| `src/benchweave/control/protection.py` | Safe-transition engine: fixed deadline on first entry, ordered safe actions, conjunction verification held `stable_for_ms` |
| `src/benchweave/control/coordinator.py` | Run lifecycle, terminal truth mapping, run-record finalisation, restart recovery |
| `tests/integration/test_procedures.py` (create) | ISC-3…ISC-15, ISC-18: admission, execution, policy-denial probes |
| `tests/faults/test_protection.py` (create) | ISC-16…ISC-17, ISC-19…ISC-22: trip/deadline/restart probes |

Decomposition rationale: each control module maps to one contract seam (documents→§2/§9, semantics→§3/§5, binding→§2/§6, policy→§7, executor→§3/§4, protection→§5/§7); the coordinator is the only writer of run state. Tests split by purpose (integration = behavioural contract, faults = protection truthfulness), matching the delivery plan's named files.

---

### Task 1: sim_psu class actions (configure / output / measure)

**Files:**
- Modify: `plugins/sim_psu/plugin.py`
- Modify: `fixtures/protocols/sim_psu_vectors.json`
- Test: `tests/contract/test_sim_plugins.py`

**Interfaces:**
- Consumes: `OperationVerb.INVOKE`, existing `dispatch`/write/trip machinery, injected `now_fn`/`monotonic_ns_fn`.
- Produces: INVOKE dispatch with `arguments={"action_id": str, "input": dict}`; ok results carry `data={"result": <payload>}` where measure's payload is the `scalar_set` dataset envelope below; `ACTION_*` constants; `CHANNELS = ("ch1",)`.

The dataset envelope mirrors `contracts/otdp-v0.3.0/examples/measurement-vectors.json` exactly (fields: `dataset_id, kind, configuration_id, acquisition_id, started_at, clock{domain_id,timestamp_source,synchronisation,uncertainty_s}, axes, variables[{id,quantity,unit,channel_ids,dtype,dimensions,values,uncertainty{status[,absolute]},calibration{status},status}]`). The sim reports KNOWN uncertainty (`{"status": "known", "absolute": …}`) so the conservative-interval path is real: voltage ±0.05 V, current ±0.01 A, power ±0.1 W.

- [ ] **Step 1: Write the failing tests** (append; reuse the file's existing plugin-construction helper — shown standalone):

```python
from benchweave.host import DispatchState, OperationRequest, OperationVerb


def _invoke(action_id: str, input_: dict) -> OperationRequest:
    return OperationRequest(
        operation_id="op-1", verb=OperationVerb.INVOKE,
        arguments={"action_id": action_id, "input": input_},
    )


def test_invoke_configure_applies_and_echoes(psu) -> None:
    result = psu.dispatch(
        _invoke("otdp.dc_psu.configure/1.0.0", {
            "configuration_id": "cfg-1", "channel": "ch1",
            "voltage_v": 5.0, "current_limit_a": 0.5,
            "ovp_v": 5.5, "ocp_a": 0.5,
        }),
        deadline_ns=10**12,
    )
    assert result.status.value == "ok"
    assert result.data["result"]["configuration_id"] == "cfg-1"
    reading = psu.dispatch(
        OperationRequest.read("op-2", parameter="voltage_setpoint_v"),
        deadline_ns=10**12,
    )
    assert reading.data.value == 5.0


def test_invoke_measure_returns_admitted_scalar_set(psu) -> None:
    psu.dispatch(_invoke("otdp.dc_psu.configure/1.0.0", {
        "configuration_id": "cfg-1", "channel": "ch1", "voltage_v": 5.0,
        "current_limit_a": 0.5, "ovp_v": 5.5, "ocp_a": 0.5,
    }), deadline_ns=10**12)
    psu.dispatch(_invoke("otdp.dc_psu.output/1.0.0", {
        "channel": "ch1", "enabled": True, "configuration_id": "cfg-1",
    }), deadline_ns=10**12)
    result = psu.dispatch(
        _invoke("otdp.dc_psu.measure/1.0.0", {
            "configuration_id": "cfg-1", "channels": ["ch1"],
        }),
        deadline_ns=10**12,
    )
    dataset = result.data["result"]
    assert dataset["kind"] == "scalar_set"
    ids = [v["id"] for v in dataset["variables"]]
    assert ids == ["voltage", "current", "power"]
    voltage = dataset["variables"][0]
    assert voltage["unit"] == "V" and voltage["values"] == [5.0]
    assert voltage["dimensions"] == [] and voltage["status"] == "valid"
    assert voltage["uncertainty"] == {"status": "known", "absolute": 0.05}


def test_invoke_unknown_action_rejected_not_dispatched(psu) -> None:
    result = psu.dispatch(_invoke("otdp.dc_psu.nope/1.0.0", {}), deadline_ns=10**12)
    assert result.status.value == "error"
    assert result.error.code.value == "UNSUPPORTED"
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_invoke_measure_requires_current_configuration(psu) -> None:
    result = psu.dispatch(
        _invoke("otdp.dc_psu.measure/1.0.0", {
            "configuration_id": "cfg-wrong", "channels": ["ch1"],
        }),
        deadline_ns=10**12,
    )
    assert result.status.value == "error"
    assert result.error.code.value == "DEVICE_REJECTED"
```

Also validate the crafted dataset against the vendored OTDP measurement schema in one test (load `contracts/otdp-v0.3.0/otdp-measurement.schema.json`, `Draft202012Validator(...).validate(dataset)`); if field names drift, this is the probe that fails.

- [ ] **Step 2: Run to verify RED**

Run: `set -o pipefail; uv run pytest tests/contract/test_sim_plugins.py -k invoke -v`
Expected: FAIL — INVOKE currently rejected `UNSUPPORTED`.

- [ ] **Step 3: Implement** — add to `SimPsuPlugin`:

```python
ACTION_CONFIGURE = "otdp.dc_psu.configure/1.0.0"
ACTION_OUTPUT = "otdp.dc_psu.output/1.0.0"
ACTION_MEASURE = "otdp.dc_psu.measure/1.0.0"
CHANNELS = ("ch1",)
```

Route `OperationVerb.INVOKE` in the handler map to `_invoke(request)`. `_invoke` extracts `action_id`/`input` (reject `INVALID_ARGUMENT` if missing/malformed), then:

- `configure`: require `configuration_id` (non-empty str), `channel` ∈ `CHANNELS`, numeric `voltage_v/current_limit_a/ovp_v/ocp_a`. Apply via the existing write semantics (bounds, trip checks) to `voltage_setpoint_v`, `current_limit_a`, `ovp_threshold_v`, `ocp_threshold_a`; on trip return the existing `DEVICE_REJECTED` trip error. Store `self._configuration_id = configuration_id`. Ok payload `{"result": {"configuration_id": configuration_id, "applied": True}}`.
- `output`: require `channel` ∈ `CHANNELS`, bool `enabled`, `configuration_id` equal to the stored one (else `DEVICE_REJECTED`). Write `output_enabled` through the write path (a trip on enable surfaces as the trip error). Ok payload `{"result": {"channel": channel, "enabled": <observed output_enabled>}}`.
- `measure`: require `configuration_id` matching the stored one and `channels` ⊆ `CHANNELS`. Build the dataset with `voltage=self._output_voltage()`, `current=self._output_current()`, `power=round(v*i, 6)`, `started_at=self._now()`, `dataset_id=f"dataset-psu-{self._monotonic_ns()}"`, `clock={"domain_id": "sim-psu", "timestamp_source": "device", "synchronisation": "unknown", "uncertainty_s": None}`. Ok payload `{"result": dataset}`.

Extend `fixtures/protocols/sim_psu_vectors.json` with the four tests above as replay vectors (the fault-matrix suite picks them up; post-dispatch timeout vector: set `deadline_ns` already passed → existing TIMEOUT-not-dispatched path stays honest).

- [ ] **Step 4: Run to verify GREEN** — `set -o pipefail; uv run pytest tests/contract/test_sim_plugins.py tests/contract/test_fault_matrix.py -v`
- [ ] **Step 5: Gates + commit** — `set -o pipefail; uv run pytest && uv run ruff check . && uv run mypy` then
  `git add plugins/sim_psu/plugin.py fixtures/protocols/sim_psu_vectors.json tests/contract/test_sim_plugins.py && git commit -m "feat: sim_psu dc_psu class actions over the host ABI"`

---

### Task 2: executable fixtures + strict document admission

**Files:**
- Create: `fixtures/execution/procedure-voltage-check.json`, `safety-policy.json`, `bench.json`, `run-binding.json`, `commissioning.json`, `descriptor-sim-psu.json`, `descriptor-sim-controller.json`
- Create: `src/benchweave/control/__init__.py`, `src/benchweave/control/documents.py`
- Test: `tests/integration/test_procedures.py`

**Interfaces:**
- Consumes: `benchweave.content.json_document` (exact-byte decode), `contracts/execution-v1.0.0/*.schema.json`.
- Produces:

```python
@dataclass(frozen=True)
class AdmittedDocuments:
    procedure: dict[str, Any]
    policy: dict[str, Any]
    bench: dict[str, Any]
    binding: dict[str, Any]
    commissioning: dict[str, Any]
    descriptors: dict[str, dict[str, Any]]  # device_id -> descriptor doc
    digests: dict[str, str]                 # logical name -> sha256 hex

def admit_documents(
    procedure_path: Path, policy_path: Path, bench_path: Path,
    binding_path: Path, commissioning_path: Path,
    descriptor_paths: dict[str, Path],   # device_id -> descriptor file
) -> AdmittedDocuments
```

Failures raise `AdmissionRejected(message)` — one exception type, machine-matchable reason prefix (`schema:`, `digest_mismatch:`, `pin_absent:`).

- [ ] **Step 1: Author the fixtures.** Procedure `procedure-voltage-check.json` (all eight kinds, sim-true values):

```json
{
  "contract_version": "1.0.0",
  "id": "voltage-check",
  "version": "1.0.0",
  "description": "Executable simulator procedure: configure, enable, measure, assert, repeat.",
  "mode": "gateway_owned",
  "safety_policy": {"id": "sim-policy", "version": "1.0.0"},
  "roles": [
    {"id": "supply", "required_profiles": ["otdp.dc_psu/1.0.0"], "channels": ["output"]},
    {"id": "dut", "required_profiles": [], "channels": []}
  ],
  "max_body_ms": 8000,
  "max_protection_ms": 2000,
  "steps": [
    {"id": "configure", "kind": "invoke", "role": "supply",
     "action_id": "otdp.dc_psu.configure/1.0.0",
     "input": {"configuration_id": {"$stg_issue": "configuration_id"},
               "channel": {"$stg_channel": "output"},
               "voltage_v": 5.0, "current_limit_a": 0.5, "ovp_v": 5.5, "ocp_a": 0.5},
     "timeout_ms": 500},
    {"id": "enable", "kind": "invoke", "role": "supply",
     "action_id": "otdp.dc_psu.output/1.0.0",
     "input": {"channel": {"$stg_channel": "output"}, "enabled": true,
               "configuration_id": {"$stg_ref": {"step": "configure", "pointer": "/configuration_id"}}},
     "timeout_ms": 500},
    {"id": "settle", "kind": "delay", "duration_ms": 100},
    {"id": "note", "kind": "write", "role": "dut", "parameter": "operator_note",
     "value": "wp05 run", "timeout_ms": 200},
    {"id": "model", "kind": "read", "role": "dut", "parameter": "identity_model",
     "timeout_ms": 200},
    {"id": "measure", "kind": "invoke", "role": "supply",
     "action_id": "otdp.dc_psu.measure/1.0.0",
     "input": {"configuration_id": {"$stg_ref": {"step": "configure", "pointer": "/configuration_id"}},
               "channels": [{"$stg_channel": "output"}]},
     "timeout_ms": 500},
    {"id": "voltage", "kind": "sample", "source_step": "measure", "variable_id": "voltage",
     "unit": "V", "max_age_ms": 500, "require_known_uncertainty": true},
    {"id": "check", "kind": "assert",
     "predicate": {"sample": "voltage", "minimum": 4.9, "maximum": 5.1}},
    {"id": "branch", "kind": "if",
     "predicate": {"sample": "voltage", "minimum": 0.1, "maximum": 5.5},
     "then": [{"id": "recheck", "kind": "sample", "source_step": "measure",
               "variable_id": "current", "unit": "A", "max_age_ms": 500,
               "require_known_uncertainty": true},
              {"id": "check-current", "kind": "assert",
               "predicate": {"sample": "recheck", "minimum": 0.0, "maximum": 0.5}}],
     "else": []},
    {"id": "loop", "kind": "repeat", "count": 3, "steps": [
      {"id": "remeasure", "kind": "invoke", "role": "supply",
       "action_id": "otdp.dc_psu.measure/1.0.0",
       "input": {"configuration_id": {"$stg_ref": {"step": "configure", "pointer": "/configuration_id"}},
                 "channels": [{"$stg_channel": "output"}]},
       "timeout_ms": 500},
      {"id": "voltage-again", "kind": "sample", "source_step": "remeasure",
       "variable_id": "voltage", "unit": "V", "max_age_ms": 500,
       "require_known_uncertainty": true},
      {"id": "check-again", "kind": "assert",
       "predicate": {"sample": "voltage-again", "minimum": 4.9, "maximum": 5.1}}]}
  ]
}
```

`safety-policy.json` (numeric + product conditions; no boolean/host-input this slice):

```json
{
  "contract_version": "1.0.0",
  "id": "sim-policy",
  "version": "1.0.0",
  "description": "Executable simulator envelope. Not hardware-qualified.",
  "domains": [{"id": "dut", "max_abs_voltage_v": 6, "max_abs_current_a": 1,
               "max_power_w": 3, "max_stored_energy_j": 0.01, "max_energised_ms": 10000}],
  "allow_rules": [
    {"device_id": "psu", "kind": "invoke", "action_id": "otdp.dc_psu.configure/1.0.0",
     "input_constraints": {"type": "object", "properties": {
       "channel": {"const": "ch1"}, "voltage_v": {"minimum": 0, "maximum": 5.5},
       "current_limit_a": {"maximum": 0.5}, "ovp_v": {"maximum": 6}, "ocp_a": {"maximum": 0.5}}}},
    {"device_id": "psu", "kind": "invoke", "action_id": "otdp.dc_psu.output/1.0.0",
     "input_constraints": {"properties": {"channel": {"const": "ch1"}}}},
    {"device_id": "psu", "kind": "invoke", "action_id": "otdp.dc_psu.measure/1.0.0",
     "input_constraints": {"properties": {"channel": {"const": "ch1"}}}},
    {"device_id": "controller", "kind": "write", "parameter": "operator_note",
     "value_constraints": {"type": "string", "maxLength": 200}}
  ],
  "continuous_conditions": [
    {"id": "dut-voltage-bounds", "kind": "numeric", "signal": "dut-voltage",
     "unit": "V", "minimum": -0.1, "maximum": 5.5},
    {"id": "dut-power", "kind": "absolute_product", "signals": ["dut-voltage", "dut-current"],
     "unit": "W", "maximum": 3.0, "max_skew_ms": 100}
  ],
  "independent_protection": {"required": false,
    "assessment": {"id": "sim-protection-assessment", "version": "1.0.0",
                   "sha256": "0000000000000000000000000000000000000000000000000000000000000000"},
    "mechanism_ids": []},
  "safe_transition": {"max_duration_ms": 2000, "actions": [
      {"id": "disable", "device_id": "psu", "kind": "invoke",
       "action_id": "otdp.dc_psu.output/1.0.0",
       "input": {"channel": "ch1", "enabled": false, "configuration_id": "issued-at-admission"},
       "timeout_ms": 500}],
    "verify": [{"id": "voltage-safe", "kind": "numeric", "signal": "dut-voltage",
                "unit": "V", "minimum": -0.1, "maximum": 0.1}],
    "stable_for_ms": 100}
}
```

NOTE: the disable action's `configuration_id` — safe actions use literal arguments and "do not depend on … valid configuration tokens" (execution-contract §7). Change the literal to `null`? The schema types `input` as plain object, so use `"configuration_id": null` and make sim_psu's `output` action accept `configuration_id: null` as "no token check" ONLY when disabling (`enabled: false`)? No — simpler and contract-true: make `output` not require a configuration token at all (only validate it when present). Then the disable literal is `{"channel": "ch1", "enabled": false}`. Amend Task 1's `output` spec accordingly: `configuration_id` optional; validated only if present. Fixture uses the two-key literal.

`bench.json`: `gateway_id: "sim-gateway"`, `fixture {id, revision, identity_record_id}`, `dut_class: "low_voltage_embedded"`, `policy` pin (id/version/sha256 of safety-policy.json), `package_lock` pin (synthetic `sim-lock/1.0.0` with its own fixture file `package-lock.json` — a trivial `{"id": "sim-lock", "version": "1.0.0"}` document; not schema-gated this WP, digest-pinned only), `commissioning_id: "sim-commissioning"`, `dut_ids: ["controller"]`, `protection_mechanisms: []`, devices:

```json
{"id": "psu", "generation": 1,
 "descriptor": {"id": "descriptor-sim-psu", "version": "1.0.0", "sha256": "<computed>"},
 "identity_record_id": "ident-psu", "connection_key": "sim_psu_local", "channels": ["ch1"]},
{"id": "controller", "generation": 1,
 "descriptor": {"id": "descriptor-sim-controller", "version": "1.0.0", "sha256": "<computed>"},
 "identity_record_id": "ident-controller", "connection_key": "sim_controller_local",
 "channels": ["ch1"]}
```

`resources`: `[{"id": "dut-net", "device_ids": ["psu", "controller"], "depends_on": []}]`.
`terminals`: psu terminal `psu-out` (device/ch1/domain dut) + controller terminal `ctl-vin` (device/ch1/domain dut). `nets`: `[{"id": "n1", "terminal_ids": ["psu-out", "ctl-vin"]}]`.
`signals`:

```json
[
  {"id": "dut-voltage", "quantity": "voltage", "unit": "V", "poll_ms": 50, "max_age_ms": 500,
   "absolute_error": 0.05, "resource_id": "dut-net",
   "source": {"kind": "parameter", "device_id": "psu", "parameter": "output_voltage_v"}},
  {"id": "dut-current", "quantity": "current", "unit": "A", "poll_ms": 50, "max_age_ms": 500,
   "absolute_error": 0.01, "resource_id": "dut-net",
   "source": {"kind": "parameter", "device_id": "psu", "parameter": "output_current_a"}}
]
```

Descriptors (`descriptor-sim-psu.json`): `{"id": "descriptor-sim-psu", "version": "1.0.0", "profiles": ["otdp.dc_psu/1.0.0"], "actions": [{"action_id": "otdp.dc_psu.configure/1.0.0", "issued": ["configuration_id"]}, {"action_id": "otdp.dc_psu.output/1.0.0"}, {"action_id": "otdp.dc_psu.measure/1.0.0"}], "parameters": ["voltage_setpoint_v", "current_limit_a", "ovp_threshold_v", "ocp_threshold_a", "load_a", "output_enabled", "operator_note", "output_voltage_v", "output_current_a", "output_power_w", "identity_model"]}`; controller descriptor analogous (`profiles: []`, `actions: []`, `parameters: ["uptime_s", "identity_model", "operator_note"]`).

`run-binding.json`: `request_id: "req-voltage-check-1"`, procedure/bench/policy/package_lock/commissioning pins (`<computed>` sha256s), `bindings: [{"role": "supply", "device_id": "psu", "channels": {"output": "ch1"}}, {"role": "dut", "device_id": "controller", "channels": {}}]`.

`commissioning.json`: pins bench/policy/package_lock/procedure digests, `dut_class: "low_voltage_embedded"`, `modes: ["supervised"]`, `owners {bench, test_safety, system}` (role labels, e.g. `"stephen-eaton"`), `approved_by/approved_at`, `expires_at: "2030-01-01T00:00:00Z"`, `offline_status_max_age_ms: 86400000`, `scheduling_overhead_ms: 100`, one evidence entry (`category: "envelope"`, report pin, `tested_at`, `scope`, `result: "passed"`, `limitations: ["simulator-only"]`).

Compute and insert every `<computed>` digest: `shasum -a 256 fixtures/execution/<file>.json` (do descriptors first, then bench/binding/commissioning which pin them; the binding and commissioning pin the procedure/bench/policy/lock).

- [ ] **Step 2: Write the failing tests:**

```python
from pathlib import Path

import pytest

from benchweave.control.documents import AdmissionRejected, admit_documents

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"


def admit() -> "admit_documents(...)":
    return admit_documents(
        procedure_path=FIXTURES / "procedure-voltage-check.json",
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=FIXTURES / "run-binding.json",
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths={"psu": FIXTURES / "descriptor-sim-psu.json",
                          "controller": FIXTURES / "descriptor-sim-controller.json"},
    )


def test_fixtures_admit() -> None:
    docs = admit()
    assert docs.procedure["id"] == "voltage-check"
    assert docs.binding["request_id"] == "req-voltage-check-1"


def test_digest_mismatch_rejected(tmp_path: Path) -> None:
    tampered = tmp_path / "procedure.json"
    tampered.write_text((FIXTURES / "procedure-voltage-check.json").read_text()
                        .replace('"voltage_v": 5.0', '"voltage_v": 5.1'))
    with pytest.raises(AdmissionRejected, match="digest_mismatch"):
        admit_documents(procedure_path=tampered, policy_path=FIXTURES / "safety-policy.json",
                        bench_path=FIXTURES / "bench.json",
                        binding_path=FIXTURES / "run-binding.json",
                        commissioning_path=FIXTURES / "commissioning.json",
                        descriptor_paths={"psu": FIXTURES / "descriptor-sim-psu.json",
                                          "controller": FIXTURES / "descriptor-sim-controller.json"})
```

Plus a schema-rejection case: append `,'"unexpected": 1'` before the final `}` of a copy of the procedure → `AdmissionRejected` with `schema:` prefix.

- [ ] **Step 3: RED** — `set -o pipefail; uv run pytest tests/integration/test_procedures.py -v` → import error (module missing).
- [ ] **Step 4: Implement `documents.py`** — decode each file via the exact-byte decoder; `Draft202012Validator` per vendored schema (loaded once, module-level cache keyed by schema filename); verify the pin lattice: binding→{procedure, bench, policy, package_lock, commissioning}, bench→policy, commissioning→{bench, policy, package_lock, procedure_refs ∋ procedure}, bench device descriptors→descriptor docs, bench.commissioning_id == commissioning.id, procedure.safety_policy == policy {id, version}. Digests are sha256 over the ORIGINAL bytes. Package-lock and descriptor docs are decoded exactly but schema-gated only by their own minimal structural check (documented Decisions row in ISA).
- [ ] **Step 5: GREEN + gates + commit** — `git add fixtures/execution src/benchweave/control tests/integration/test_procedures.py && git commit -m "feat: strict admission of execution documents with executable fixtures"`

---

### Task 3: semantic admission — IDs, lexical scope, issue placement, budgets

**Files:**
- Create: `src/benchweave/control/semantics.py`
- Test: `tests/integration/test_procedures.py` (extend)

**Interfaces:**
- Consumes: `AdmittedDocuments` (Task 2).
- Produces:

```python
def check_semantics(docs: AdmittedDocuments, *, now_wall: str) -> None  # raises AdmissionRejected
def worst_case_body_ms(steps: list[dict[str, Any]]) -> int
```

- [ ] **Step 1: Failing tests** — build each malformed variant by `json.loads`-mutating the admitted procedure, re-serialising, and re-admitting with a corrected binding pin (helper `readmit_with_procedure(mutate_fn)` that recomputes the procedure digest into binding + commissioning):

```python
def test_duplicate_step_id_rejected(): ...          # duplicate "settle" inside repeat
def test_future_reference_rejected(): ...           # configure input refs step "enable"
def test_branch_scope_leak_rejected(): ...          # outer step refs "recheck" (inside then)
def test_previous_iteration_rejected(): ...         # remeasure input refs "remeasure"
def test_issue_misplacement_rejected(): ...         # $stg_issue inside "voltage_v" value
def test_body_budget_rejected(): ...                # raise loop count until bound > max_body_ms
def test_energised_budget_rejected(): ...           # max_body_ms 15000 > 10000 - 2000
def test_expired_commissioning_rejected(): ...      # now_wall "2031-01-01T00:00:00Z"
def test_worst_case_bound_exact():                  # hand-computed for the fixture
    from benchweave.control.semantics import worst_case_body_ms
    steps = json.loads((FIXTURES / "procedure-voltage-check.json").read_text())["steps"]
    # 500+500+100+200+200+500 + max(500+0,0)... assert exact integer
    assert worst_case_body_ms(steps) == EXPECTED  # compute by hand, assert equality
```

- [ ] **Step 2: RED** → module missing.
- [ ] **Step 3: Implement.** Walker + scope (kernel code):

```python
def _walk(steps: list[dict[str, Any]], visible: list[str],
          block_id: str) -> Iterator[tuple[dict[str, Any], frozenset[str], str]]:
    seen: list[str] = []
    for step in steps:
        yield step, frozenset(visible), block_id
        sid = step["id"]
        seen.append(sid)
        visible_now = visible + seen
        if step["kind"] == "if":
            yield from _walk(step["then"], visible_now, block_id + f"/{sid}/then")
            yield from _walk(step.get("else", []), visible_now, block_id + f"/{sid}/else")
        elif step["kind"] == "repeat":
            for i in range(step["count"]):
                yield from _walk(step["steps"], visible_now, block_id + f"/{sid}/{i}")
```

(Visibility semantics: each later sibling sees earlier siblings of its own block plus the enclosing prefix — the `visible` list passed down. Inside repeat, iteration i sees the same enclosing prefix; iteration results never become visible to anything.)

For each yielded step, validate every `$stg_ref.step`, `sample.source_step`, and `predicate.sample` against the step's visible frozenset; collect IDs globally for uniqueness (including across nested bodies). `$stg_issue` placement: recursively scan invoke `input` — allowed only at top-level key `configuration_id` when the role's descriptor marks the action `issued: ["configuration_id"]`, or at `acquisition_id` similarly. Budget kernel:

```python
def worst_case_body_ms(steps: list[dict[str, Any]]) -> int:
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
```

`check_semantics` rejects when `worst_case_body_ms + commissioning["scheduling_overhead_ms"] > procedure["max_body_ms"]`, when `max_body_ms + policy["safe_transition"]["max_duration_ms"] > min(d["max_energised_ms"] for d in policy["domains"])`, and when `now_wall + (max_body_ms + max_protection_ms)` exceeds `commissioning["expires_at"]` (ISO-8601 parse, UTC).

- [ ] **Step 4: GREEN + gates + commit** — `git commit -m "feat: semantic admission with lexical scope and budget bounds"`

---

### Task 4: binding, resource closure, own lease

**Files:**
- Create: `src/benchweave/control/binding.py`
- Test: `tests/integration/test_procedures.py` (extend)

**Interfaces:**
- Consumes: `AdmittedDocuments`, `benchweave.state.store.Store`.
- Produces:

```python
@dataclass(frozen=True)
class Reservation:
    resources: frozenset[str]
    lease: Lease

class BindingError(Exception): ...

def resolve_binding(docs: AdmittedDocuments) -> ResolvedBinding
    # roles→device ids+channels; profile/action/parameter/channel declared-ness
def reserve(store: Store, docs: AdmittedDocuments, bench_id: str, holder: str,
            expires_at: str, now_wall: str) -> Reservation  # raises BindingError
def release(store: Store, reservation: Reservation, now_wall: str) -> None
```

- [ ] **Step 1: Failing tests** (store on a tmp SQLite file, `Store.open(tmp_path/"state.db")`):
  - unbound role (delete the `dut` binding) → `BindingError("unbound_role: dut")`
  - missing profile (drop `otdp.dc_psu/1.0.0` from the descriptor) → rejected
  - undeclared action (`action_id` mutated to `…/9.9.9`, pins recomputed) → rejected
  - undeclared parameter (read `nope`) → rejected
  - channel alias to an undeclared channel (`"output": "ch9"`) → rejected
  - resource cycle in a mutated bench (`dut-net` depends on `aux`, `aux` depends on `dut-net`) → rejected
  - `reserve` twice on the same bench → second raises `BindingError("bench_busy")`; after `release`, reserve succeeds
  - failed reserve leaves no active lease (`store.get_active_lease(bench) is None`)
- [ ] **Step 2: RED** → module missing.
- [ ] **Step 3: Implement** — closure via iterative expansion over `bench["resources"]` (start from resources whose `device_ids` intersect bound devices; add `depends_on` transitively; detect cycles with a visiting-set). One-active check: `store.get_active_lease(bench_id)` with `expires_at` still in the future (wall now) → busy; else `store.next_lease(bench_id, lease_id=f"lease-{request_id}", holder, expires_at)`. Wrap admission failures so the lease and any partially-reserved state unwind (`release` is idempotent, checks state='active' rowcount as the store already does).
- [ ] **Step 4: GREEN + gates + commit** — `git commit -m "feat: role binding resource closure and bench lease"`

---

### Task 5: policy evaluation

**Files:**
- Create: `src/benchweave/control/policy.py`
- Test: `tests/integration/test_procedures.py` (extend)

**Interfaces:**
- Consumes: policy dict from `AdmittedDocuments`.
- Produces:

```python
class PolicyDenied(Exception): ...   # carries reason + matching rule ids

def check_allowed(policy: dict[str, Any], device_id: str, kind: str,
                  target: str, payload: dict[str, Any] | Any) -> None
@dataclass(frozen=True)
class SignalValue:
    signal_id: str; value: float; unit: str; age_ms: int; valid: bool
    absolute_error: float | None
def evaluate_conditions(policy: dict[str, Any],
                        snapshot: dict[str, SignalValue]) -> list[str]  # violation ids+reasons
```

- [ ] **Step 1: Failing tests:**
  - invoke with no matching rule (device `controller`, action configure) → `PolicyDenied`
  - configure input `voltage_v: 5.6` violates `input_constraints` maximum 5.5 → denied
  - matched configure at 5.0 → allowed (returns None)
  - write `operator_note` 201 chars violates `value_constraints` → denied
  - numeric condition: value 5.4 error 0.2 against max 5.5 → violation (interval escapes)
  - stale/missing signal (age 600 > max_age 500; absent key) → violation
  - product: (5.0+0.05)×(0.5+0.01)=2.5755 ≤ 3 passes; (5.0,0.7) → (5.05)(0.71)=3.5855 > 3 → violation; skew 150 > 100 → violation
- [ ] **Step 2: RED** → module missing.
- [ ] **Step 3: Implement** — `check_allowed` selects rules where `device_id`+`kind`+(action_id|parameter) equal; empty match → deny (state-changing default). Invoke: each matching rule's `input_constraints` validated with `Draft202012Validator` (empty schema `{}` = no extra constraint); write: `value_constraints` over the scalar value. All matching rules apply conjunctively. `evaluate_conditions`: numeric → interval `[v−e, v+e] ⊆ [min, max]` with e required finite (None → violation "unknown_error"); boolean → equality; product → `(abs(v1)+e1) * (abs(v2)+e2) <= maximum` AND `abs(age1−age2) <= max_skew_ms`; freshness `age_ms <= bench signal max_age` enforced by the caller building `SignalValue` (violation if invalid/absent).
- [ ] **Step 4: GREEN + gates + commit** — `git commit -m "feat: safety policy allow rules and continuous conditions"`

---

### Task 6: clocking + execution engine core (happy path, deadline, occurrence ledger)

**Files:**
- Create: `src/benchweave/control/clocking.py`, `src/benchweave/control/executor.py`
- Test: `tests/integration/test_procedures.py` (extend)

**Interfaces:**
- Produces:

```python
class MonotonicClock(Protocol):
    def now_ns(self) -> int: ...
    def wait_ns(self, duration_ns: int) -> None: ...
class WallClock(Protocol):
    def now_iso(self) -> str: ...
@dataclass(frozen=True)
class TestClock:  # implements both protocols; virtual advance; records waits
class SystemClock:  # time.monotonic_ns / time.time
@dataclass(frozen=True)
class BodyResult:
    body_outcome: str          # completed|assertion_failed|cancelled|timed_out|tripped|execution_error|outcome_unknown
    reasons: list[str]
    step_events: list[dict[str, Any]]
@dataclass
class Executor:
    def __init__(self, plugins: dict[str, DevicePlugin], binding: ResolvedBinding,
                 policy: dict[str, Any], clock: MonotonicClock, wall: WallClock) -> None: ...
    def run_body(self, procedure: dict[str, Any], run_id: str,
                 body_deadline_ns: int) -> BodyResult
```

- [ ] **Step 1: Failing tests:**
  - happy path: coordinator-less direct `Executor.run_body` over the fixture procedure with both sim plugins on a `TestClock` → `body_outcome == "completed"`, all eight kinds observed in `step_events` (assert `{"step": "configure", "occurrence": [run_id, "configure", []]}`-style entries; occurrence tuple = `(run_id, step_id, loop_index_path)`), issued `configuration_id` present in configure's resolved input and echoed in its result, `$stg_ref` resolution fed the enable input.
  - deadline shortening: set `max_body_ms` tiny via mutated procedure (pins recomputed) so remaining budget < step timeout → the dispatched `deadline_ns` is clamped (assert via a recording plugin wrapper that captures deadlines) and never exceeds `body_deadline_ns`.
  - no-retry: wrap the psu plugin so `measure` returns a `TRANSPORT_ERROR` with `dispatch_state=DISPATCHED` once → body ends `outcome_unknown` with the operation counted exactly once in `step_events`.
  - post-dispatch timeout honesty: wrapper returns TIMEOUT/`dispatch_state=UNKNOWN` → body `outcome_unknown`, reason names the step.
  - body expiry: TestClock pre-advanced past deadline before a step → `timed_out`.
- [ ] **Step 2: RED** → modules missing.
- [ ] **Step 3: Implement** — `TestClock` holds `_now_ns`, `wait_ns` advances it (no sleeping). Executor: recursive `execute_block(steps, visible_results, index_path)`; occurrence ledger `dict[tuple[str, str, tuple[int, ...]], dict]` consulted before dispatch (re-entry returns the recorded result — tested by calling `run_body` twice sharing an injected ledger via constructor param `occurrence_ledger: dict | None`); per-step `deadline_ns = min(clock.now_ns() + timeout_ms*1_000_000, body_deadline_ns)`; delay → `clock.wait_ns`; before every dispatch call `check_allowed` (policy) with the RESOLVED input; `read`/`write` via `OperationRequest.read/write` to the role's device plugin; `invoke` via `arguments={"action_id": …, "input": resolved}`. Error mapping: `NOT_DISPATCHED` failures → `execution_error`; `dispatch_state in (DISPATCHED, UNKNOWN)` → `outcome_unknown`; body deadline passed → `timed_out`. Every step appends an event `{occurrence, kind, resolved_input_sha256, operation_id, status, data_digest}` to `step_events` (full payloads retained by the coordinator, not the executor).
- [ ] **Step 4: GREEN + gates + commit** — `git commit -m "feat: eight-kind execution engine with occurrence ledger and body deadline"`

---

### Task 7: reference resolution, issued IDs, three-valued predicates, trustworthy samples

**Files:**
- Modify: `src/benchweave/control/executor.py`
- Test: `tests/integration/test_procedures.py` (extend)

**Interfaces:**
- Consumes: dataset envelope (Task 1), `resolved` step results (invoke `data["result"]`; read/write typed `Reading`/`WriteReceipt` in `data`).
- Produces (module-level, unit-testable):

```python
def resolve_value(value: object, scope: Scope, role: str) -> object
    # Scope = mapping step_id -> result payload for the visible chain
def select_sample(step: dict[str, Any], invoke_result: object, *,
                  evaluated_at_wall: str) -> SampleOutcome
    # SampleOutcome: TRUE_VALUE payload or INVALID reason (stale|wrong_unit|not_scalar|unknown_uncertainty|missing)
def evaluate_predicate(predicate: dict[str, Any], samples: dict[str, SampleOutcome]
                       ) -> bool | None   # None = INVALID; an INVALID sample outcome propagates
```

- [ ] **Step 1: Failing tests:**
  - `$stg_ref` pointer `/configuration_id` selects exact type from configure result; pointer to missing key → body `execution_error` BEFORE dispatch (no dispatch recorded for the consuming step).
  - `$stg_channel` resolves via binding (`output`→`ch1`).
  - repeat iteration isolation: inside iteration i, a ref to iteration i−1's `remeasure` → admission already rejects (Task 3); runtime counterpart: scope frames per iteration.
  - `$stg_issue` at the configure field produces a fresh id per occurrence (two `run_body` calls → different ids); failed configure (wrapper rejects once) → re-running the same occurrence does NOT mint a new id (invalidation recorded, body ends execution_error).
  - sample: wrong unit (`"mV"`) → INVALID → `execution_error`; `max_age_ms` violated (TestClock wall advanced 600ms between measure and assert) → INVALID; dataset with two values / dimensions non-empty → INVALID; `require_known_uncertainty` true against unknown-uncertainty dataset (crafted stub) → INVALID.
  - conservative interval: value 5.08 ± 0.05 against bounds [4.9, 5.1] → interval [5.03, 5.13] escapes → assert FALSE → `assertion_failed` (even though nominal value is inside!). This is the headline truthfulness test.
  - `if` false → else branch steps appear in events, then-branch steps do not.
- [ ] **Step 2: RED**.
- [ ] **Step 3: Implement** — `resolve_value` recursive: dict with `$stg_ref` (RFC 6901 walk, exact types, missing → `ScopeError`), `$stg_channel` (binding lookup), `$stg_issue` (ledger-issued `f"{kind}-{run_id}-{step_id}-{occurrence_suffix}"`); dicts containing any other `$stg_` key → reject; lists recurse. `select_sample`: dataset must be dict with `kind == "scalar_set"`, variable by id present, `dimensions == []`, `values` exactly one finite number, `status == "valid"`, dataset `configuration_id` provenance retained, unit exact-equal, age = wall-now minus `started_at`, uncertainty known iff required. `evaluate_predicate` returns `None` on any INVALID; with known uncertainty uses the conservative interval for BOTH assert and if.
- [ ] **Step 4: GREEN + gates + commit** — `git commit -m "feat: lexical references issued ids and three-valued trustworthy predicates"`

---

### Task 8: protection engine + coordinator + truthful terminal + recovery

**Files:**
- Create: `src/benchweave/control/protection.py`, `src/benchweave/control/coordinator.py`
- Test: `tests/faults/test_protection.py` (create), `tests/integration/test_procedures.py` (final full-run)

**Interfaces:**
- Consumes: Tasks 2–7.
- Produces:

```python
class ProtectionEngine:
    def __init__(self, plugins, policy, bench, clock, wall) -> None: ...
    def enter(self, reasons: list[str], entered_at_ns: int) -> ProtectionResult
    # ProtectionResult: safe_state "verified"|"unknown", reasons, actions attempted
class RunCoordinator:
    def __init__(self, store: Store, plugins: dict[str, DevicePlugin],
                 clock: MonotonicClock, wall: WallClock, docs: AdmittedDocuments) -> None: ...
    def start_run(self, run_id: str, principal_id: str) -> dict[str, Any]  # terminal record
    def cancel(self, run_id: str, principal_id: str) -> None
    def recover_interrupted(self) -> list[str]  # run_ids finalised as interrupted
def build_terminal_record(...) -> dict[str, Any]  # validates against run-record schema
```

- [ ] **Step 1: Failing tests (`tests/faults/test_protection.py`):**
  - **trip**: monitoring wrapper makes `output_voltage_v` read 5.9 after enable (condition max 5.5) → terminal `outcome == "tripped"`, `body_outcome == "tripped"`, safe actions ran (disable dispatched), `safe_state == "verified"` only if the verification conjunction holds post-disable (voltage reads 0.0 after output off — wrapper must reflect the disable).
  - **fixed deadline**: inject a second fault while protecting (verification signal goes bad mid-verify) → `reasons` grows, the protection deadline (captured at first entry via TestClock) is NEVER extended, and if the budget lapses → `safe_state == "unknown"` → terminal `outcome == "outcome_unknown"`.
  - **stale signal trips**: signal age beyond `max_age_ms` (TestClock advance, no fresh reads) → protective response.
  - **cancel**: `cancel` before dispatch window closes → `outcome == "cancelled"`, safe transition still runs, record validates.
  - **timeout**: body deadline expiry → `timed_out`; protection still runs and verifies.
  - **truthful passed**: normal full `start_run` → record validates against `contracts/execution-v1.0.0/run-record.schema.json` with `outcome == "passed"`, `body_outcome == "completed"`, `safe_state == "verified"`; store `get_run(run_id)["terminal"]` equals it; events stream non-empty with monotonic sequences.
  - **no false passed**: wrapper forces verification to fail → `outcome == "outcome_unknown"` even though body completed.
  - **restart recovery**: open a second coordinator on the same store file with a run left un-terminalised (first coordinator crashed between `create_run` and `finalize_run` — simulate by calling internal steps or killing a child like `tests/faults/_kill_child.py` does) → `recover_interrupted()` finalises `interrupted`/`outcome_unknown`/`safe_state: "unknown"`; a subsequent `start_run` with the same run_id is refused; occurrence identities from the crashed run suppress replay (ledger rebuild from events).
  - **lease lifecycle**: after terminal, `store.get_active_lease(bench)` is None (released); a second `start_run` on the same bench now admits.
  - **monitor from acceptance**: condition violated before first dispatch (pre-energised bad signal via wrapper initial state) → trip before any body dispatch.
- [ ] **Step 2: RED** → modules missing.
- [ ] **Step 3: Implement** — ProtectionEngine: on first `enter`, `deadline_ns = entered_at_ns + max_duration_ms*1_000_000` (stored; later enters only append reasons); safe actions dispatched in order, each `deadline_ns = min(action deadline, protection deadline)`, failures recorded and remaining non-conflicting actions attempted; verification loop polls the verify signals until the conjunction holds continuously `stable_for_ms` (TestClock waits) or budget ends → `unknown`. RunCoordinator: `admit_documents` + `check_semantics` + `resolve_binding`/`reserve` (own lease, holder `run:{run_id}`, expiry = acceptance + body + protection) + `store.create_run` + monitor/execute interleaved loop (monitor ticks: before each dispatch, after each dispatch, and across `wait_ns` in `delay`/verify — single-threaded, deterministic on TestClock) + on ANY body end or condition violation → `ProtectionEngine.enter` → `build_terminal_record` → `store.finalize_run` → `release`. Terminal mapping per execution-contract §5: body completed + safe verified → `passed`; assertion false → `assertion_failed`; cancel/lease expiry → `cancelled`; deadline → `timed_out`; trip → `tripped`; pre-dispatch errors → `execution_error`; uncertain dispatch or unverified safety → `outcome_unknown`; `body_outcome` recorded independently; restart → `interrupted`. `build_terminal_record` emits the run-record fields (`run_id`, binding pin = request_id/version/sha256 of the binding document, principal, started/ended, outcomes, safe_state, reasons, evidence_refs incl. the event-stream digest) and the test validates it with the vendored schema.
- [ ] **Step 4: GREEN + gates + commit** — `git commit -m "feat: protection engine coordinator and truthful terminal records"`

---

## Verification commands (every task, before commit)

```bash
set -o pipefail
uv run pytest
uv run ruff check .
uv run mypy
```

Full WP05 acceptance (Task 8 close): the above plus
`uv run pytest tests/integration/test_procedures.py tests/faults/test_protection.py -v` green, ISA claims ISC-1…ISC-22 checked with stubs, and `Skill("ISA", "check completeness of ISA.md")` passing.

## Review boundary

- Per task: diff review against this plan + the semantic clause it implements; gates green before commit (enforced above).
- Task 8 close: full-suite rerun, ISA CheckCompleteness, and an independent second look per Algorithm claim 11 (fresh-context skeptic or Forge audit) over the protection truth table — protection semantics are the core-surface risk of this WP; electing zero review requires a Log row naming the skip.
- Out of boundary: anything REST/MCP (WP07), registry (WP06), CLI (WP08), hardware (WP10+).
