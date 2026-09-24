"""Row D lattice control (issue #176, design Decision 3): the demo lattice
streams.

D-R1: post-rebuild, the demo bench admits at bootstrap and a run on it
constructs a ``StreamController`` for the psu through the unmutated
fixture lattice; during a delay step telemetry lands as ``event_log``
evidence under ``run:{run_id}``.

Composition notes (disclosed, not hidden):

* The run reuses the COMMITTED device surfaces verbatim -- the edited
  descriptor (event_sink, stream_limits, the adapter entry point) and
  the committed bench signals -- while authoring the run-authoring
  documents (policy, procedure, commissioning, binding) around them.
  The committed policy authorizes only INVOKE-kind psu actions, which
  the bridge's corpus-pinned verb set does not carry (invoke over the
  bridge is a deferred train), so the harness authors a write-kind
  policy whose safe transition is bridge-dispatchable, re-pinning the
  bench copy's policy digest, and moving the CONTROLLER's declared
  generation to an unactivated one (the activation record is bench-scoped;
  the generation separation is what links the record to the psu alone).
  The device descriptor digests and signals stay the committed bytes.
* The psu's package closure is admitted and activated from the
  COMMITTED catalogue (origin-main signed fixtures -- verification
  needs only the committed public key), at the demo bench's declared
  generation 1, so the bridge leg loads the COMMITTED plugin bytes
  through ``load_otdp_plugin``.

RED arm (absence-presence): revert the descriptor's ``event_sink``
permission (and its ``stream_limits``), REBUILD the registry lattice
(``scripts/registry/build_fixtures.py``), and this control fails -- the
run constructs no stream services and lands zero ``event_log`` evidence.
The rebuild step is load-bearing: a descriptor revert without it fails
earlier and elsewhere -- ``closure_descriptor_absent``, the reverted
descriptor digest no longer served by the pinned closure -- so the run
never reaches the arm that discriminates ``event_sink``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.interfaces.app import _build_run_factory
from benchweave.interfaces.bootstrap import (
    RegistrySession,
    admit_startup_bench,
    build_registry_session,
)
from benchweave.registry.activation import activate
from benchweave.registry.admission import Approval, admit
from benchweave.state.store import Store

REPO = Path(__file__).resolve().parents[2]
EXECUTION_FIXTURES = REPO / "fixtures" / "execution"
REGISTRY_FIXTURES = REPO / "fixtures" / "registry"

# The registry clock, frozen inside every fixture status's validity window
# (the established harness posture -- never a hand-typed nanosecond literal).
NOW_NS = int(datetime(2026, 9, 14, tzinfo=UTC).timestamp() * 1_000_000_000)
NOW_ISO = "2026-09-14T00:00:00Z"

#: The quota seam's required operator ceilings (the #167 harness shape).
QUOTA_LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
    "max_dataset_bytes": 8 * 1024 * 1024,
    "max_event_batch": 64,
}

BENCH_ID = "sim-bench"
DEVICE_ID = "psu"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, document: dict[str, Any]) -> Path:
    path.write_text(json.dumps(document, indent=2))
    return path


def _demo_session(work: Path) -> RegistrySession:
    """The resolver session over the COMMITTED fixture catalogue, with the
    committed benchweave/sim-psu closure admitted and activated at the demo
    bench's declared generation 1."""
    session = build_registry_session(REGISTRY_FIXTURES, work, now_ns=lambda: NOW_NS)
    closure = session.resolver.resolve(
        "origin-main",
        "benchweave/sim-psu",
        "1.0.0",
        now_ns=NOW_NS,
        high_water=session.high_water,
    )
    admitted = admit(
        closure,
        cache_root=session.cache_root,
        lock_path=session.lock_path,
        limits=session.limits,
        approval=Approval(
            principal_id="demo-lattice-harness",
            approved_at=NOW_ISO,
            policy_id="local-policy",
            policy_version="1.0.0",
        ),
        now_ns=NOW_NS,
        roots=dict(session.roots),
        high_water=session.high_water,
    )
    activate(
        admitted,
        # activate() writes the record at bench_generation + 1: the demo
        # bench declares generation 1, so the pre-generation is 0.
        bench_generation=0,
        bench_has_live_lease=False,
        records_dir=session.records_dir / BENCH_ID,
        activated_at=NOW_ISO,
    )
    return session


def _build_run_lattice(root: Path) -> Path:
    """Assemble the run lattice: committed device bytes, authored run docs.

    The descriptor files, the bench's device descriptor digests and the
    bench's declared signals are the COMMITTED fixture bytes verbatim; the
    run-authoring documents are authored around them (see the module
    docstring's disclosure). Re-pins travel in dependency order:
    policy -> bench copy -> commissioning -> binding.
    """
    lattice = root / "lattice"
    lattice.mkdir(parents=True)
    # Committed device surfaces, verbatim.
    for name in (
        "descriptor-sim-psu.json",
        "descriptor-sim-controller.json",
    ):
        shutil.copyfile(EXECUTION_FIXTURES / name, lattice / name)
    bench = json.loads((EXECUTION_FIXTURES / "bench.json").read_bytes())
    lock_bytes = (EXECUTION_FIXTURES / "package-lock.json").read_bytes()
    (lattice / "package-lock.json").write_bytes(lock_bytes)

    # Authored policy: psu write rules (the bridge's verb set) with the
    # same domain envelope and the same signal conditions the committed
    # policy declares; the safe transition is a bridge-dispatchable write.
    policy: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "sim-policy",
        "version": "0.1.0",
        "description": "Demo-lattice streaming harness policy (synthetic).",
        "domains": [
            {
                "id": "dut",
                "max_abs_voltage_v": 6,
                "max_abs_current_a": 1,
                "max_power_w": 3,
                "max_stored_energy_j": 0.01,
                "max_energised_ms": 10000,
            }
        ],
        "allow_rules": [
            {
                "device_id": DEVICE_ID,
                "kind": "write",
                "parameter": "voltage_setpoint_v",
                "value_constraints": {"type": "number", "minimum": 0, "maximum": 5.5},
            },
            {
                "device_id": DEVICE_ID,
                "kind": "write",
                "parameter": "output_enabled",
                "value_constraints": {"type": "boolean"},
            },
            {
                "device_id": "controller",
                "kind": "write",
                "parameter": "operator_note",
                "value_constraints": {"type": "string", "maxLength": 200},
            },
        ],
        "continuous_conditions": [
            {
                "id": "dut-voltage-bounds",
                "kind": "numeric",
                "signal": "dut-voltage",
                "unit": "V",
                "minimum": -0.1,
                "maximum": 5.5,
            },
            {
                "id": "dut-power",
                "kind": "absolute_product",
                "signals": ["dut-voltage", "dut-current"],
                "unit": "W",
                "maximum": 3.0,
                "max_skew_ms": 100,
            },
        ],
        "independent_protection": {
            "required": False,
            "assessment": {
                "id": "sim-protection-assessment",
                "version": "0.1.0",
                "sha256": "0" * 64,
            },
            "mechanism_ids": [],
        },
        "safe_transition": {
            "max_duration_ms": 2000,
            "actions": [
                {
                    "id": "disable",
                    "device_id": DEVICE_ID,
                    "kind": "write",
                    "parameter": "output_enabled",
                    "value": False,
                    "timeout_ms": 500,
                }
            ],
            "verify": [
                {
                    "id": "voltage-safe",
                    "kind": "numeric",
                    "signal": "dut-voltage",
                    "unit": "V",
                    "minimum": -0.1,
                    "maximum": 0.1,
                }
            ],
            "stable_for_ms": 100,
        },
    }
    policy_path = _write(lattice / "safety-policy.json", policy)

    # Authored procedure: writes -> settle (the poll window) -> read, all
    # bridge verbs.
    procedure: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "voltage-check",
        "version": "0.1.0",
        "description": "Demo-lattice streaming harness procedure (synthetic).",
        "mode": "gateway_owned",
        "safety_policy": {"id": "sim-policy", "version": "0.1.0"},
        "roles": [
            {"id": "supply", "required_profiles": [], "channels": ["output"]}
        ],
        "max_body_ms": 8000,
        "max_protection_ms": 2000,
        "steps": [
            {
                "id": "set-voltage",
                "kind": "write",
                "role": "supply",
                "parameter": "voltage_setpoint_v",
                "value": 5.0,
                "timeout_ms": 500,
            },
            {
                "id": "enable",
                "kind": "write",
                "role": "supply",
                "parameter": "output_enabled",
                "value": True,
                "timeout_ms": 500,
            },
            {"id": "settle", "kind": "delay", "duration_ms": 400},
            {
                "id": "observe",
                "kind": "read",
                "role": "supply",
                "parameter": "output_voltage_v",
                "timeout_ms": 500,
            },
        ],
    }
    procedure_path = _write(lattice / "procedure-voltage-check.json", procedure)

    # The bench copy: the policy digest moves, and the CONTROLLER's declared
    # generation moves to 2 (an unactivated generation) so the bench-scoped
    # activation record at generation 1 links ONLY the psu -- the same
    # generation-separation the #167 harness bench uses. Device descriptor
    # digests and the declared signals stay the committed bytes.
    bench["policy"]["sha256"] = _sha(policy_path.read_bytes())
    assert bench["devices"][1]["id"] == "controller"
    bench["devices"][1]["generation"] = 2
    bench_path = _write(lattice / "bench.json", bench)

    # Authored commissioning: the committed simulation mark so the
    # controller keeps its declarative sim leg.
    commissioning: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "sim-commissioning",
        "version": "0.1.0",
        "description": "Demo-lattice streaming harness commissioning (synthetic).",
        "bench": {"id": BENCH_ID, "version": "0.1.0"},
        "policy": {"id": "sim-policy", "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "procedure_refs": [{"id": "voltage-check", "version": "0.1.0"}],
        "dut_class": "low_voltage_embedded",
        "modes": ["supervised"],
        "owners": {
            "bench": "demo-lattice-harness",
            "test_safety": "demo-lattice-harness",
            "system": "demo-lattice-harness",
        },
        "approved_by": "demo-lattice-harness",
        "approved_at": "2026-09-11T00:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "offline_status_max_age_ms": 86400000,
        "scheduling_overhead_ms": 100,
        "evidence": [
            {
                "category": "envelope",
                "report": {
                    "id": "sim-envelope-report",
                    "version": "0.1.0",
                    "sha256": "0" * 64,
                },
                "tested_at": "2026-09-11T00:00:00Z",
                "scope": "Simulator envelope over the synthetic demo devices.",
                "result": "passed",
                "limitations": ["simulator-only"],
            }
        ],
    }
    for name, path in (
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lattice / "package-lock.json"),
    ):
        commissioning[name]["sha256"] = _sha(path.read_bytes())
    for reference in commissioning["procedure_refs"]:
        reference["sha256"] = _sha(procedure_path.read_bytes())
    commissioning_path = _write(lattice / "commissioning.json", commissioning)

    binding: dict[str, Any] = {
        "contract_version": "0.1.0",
        "request_id": "req-demo-stream-1",
        "procedure": {"id": "voltage-check", "version": "0.1.0"},
        "bench": {"id": BENCH_ID, "version": "0.1.0"},
        "policy": {"id": "sim-policy", "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "commissioning": {"id": "sim-commissioning", "version": "0.1.0"},
        "bindings": [
            {"role": "supply", "device_id": DEVICE_ID, "channels": {"output": "ch1"}},
        ],
    }
    for name, path in (
        ("procedure", procedure_path),
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lattice / "package-lock.json"),
        ("commissioning", commissioning_path),
    ):
        binding[name]["sha256"] = _sha(path.read_bytes())
    _write(lattice / "run-binding.json", binding)
    return lattice


def test_demo_lattice_admits_and_streams(tmp_path: Path) -> None:
    """D-R1: the committed lattice admits at bootstrap; a run constructs the
    psu's bridge with its stream controller, and during the settle delay the
    sim's telemetry lands as ``event_log`` evidence under ``run:{run_id}``.

    Wall-clock sensitivity (disclosed): this control is timing-sensitive
    under CPU load -- 1 of 27 load runs landed ``outcome_unknown``
    honestly (no ``signal_invalid``, no subscribe refusal; the §5
    mapping minted in ``terminal_outcome`` at coordinator.py:107-108 and
    documented at executor.py:49). Disposition: accepted flake,
    disclosed; the N×-under-load CI lane is deferred (design record
    deferral table, trigger: a second under-load D-R1 flake).
    """
    session = _demo_session(tmp_path / "registry-work")
    lattice = _build_run_lattice(tmp_path)

    # Arm 1: the COMMITTED execution lattice admits at bootstrap --
    # the edited descriptor chain (event_sink, stream_limits, entry point)
    # validates and pin-verifies end to end.
    bootstrap_store = Store.open(tmp_path / "bootstrap.db")
    try:
        admit_startup_bench(
            bootstrap_store,
            ContentStore(bootstrap_store),
            EXECUTION_FIXTURES,
            now=NOW_ISO,
        )
    finally:
        bootstrap_store.close()

    # Arm 2: the run through the bridge leg.
    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    try:
        admit_startup_bench(store, content, lattice, now=NOW_ISO)
        factory = _build_run_factory(
            lattice,
            # Real wall time: the monitor's freshness verdict compares each
            # reading's observed_at against the coordinator's clock, so the
            # run's services must stamp readings with live wall time (the
            # frozen NOW_ISO is the registry/bootstrap clock only).
            SystemClock().now_iso,
            limits=QUOTA_LIMITS,
            registry_session=session,
        )
        run_id = "run-demo-stream"
        coordinator = factory(run_id, "demo-lattice-principal", _binding_ref(lattice), store)
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        bridge = coordinator.plugins[DEVICE_ID]
        assert isinstance(bridge, OTDPBridge)
        # The stream controller constructed for the psu: the descriptor's
        # event_sink permission admits stream services.
        assert bridge._stream is not None
        record = coordinator.start_run(run_id, "demo-lattice-principal")
        assert record["outcome"] == "passed", record
        assert record["safe_state"] == "verified", record

        rows = store.connection.execute(
            "SELECT content_ref_json, artifact_id FROM evidence "
            "WHERE kind = 'event_log' AND context_key = ?",
            (f"run:{run_id}",),
        ).fetchall()
        landed = [json.loads(row[0]) for row in rows]
        # Two bench signals -> two subscriptions; each carries the sim's
        # strictly-increasing telemetry sequence and its terminal marker.
        by_subscription: dict[str, list[dict[str, Any]]] = {}
        for reference in landed:
            by_subscription.setdefault(str(reference["subscription_id"]), []).append(reference)
        assert len(by_subscription) == 2, sorted(by_subscription)
        for subscription_id, references in by_subscription.items():
            sequences = sorted(int(row["sequence"]) for row in references)
            kinds = {row["kind"] for row in references}
            assert len(sequences) == len(set(sequences)), subscription_id
            assert "ended" in kinds, subscription_id
            assert "telemetry" in kinds, subscription_id
        # Telemetry values are the device's actual readings: the run set
        # the setpoint to 5.0 V and enabled the output during the settle,
        # so the voltage stream's telemetry carries 5.0 while enabled and
        # returns to 0.0 once the protective transition disables it.
        payloads: list[dict[str, Any]] = []
        for (artifact_id,) in store.connection.execute(
            "SELECT artifact_id FROM evidence "
            "WHERE kind = 'event_log' AND context_key = ?",
            (f"run:{run_id}",),
        ).fetchall():
            blob = store.connection.execute(
                "SELECT data FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()[0]
            payloads.append(json.loads(bytes(blob)))
        voltage_values = [
            float(event["reading"]["value"])
            for event in payloads
            if event["kind"] == "telemetry"
            and event["reading"]["parameter"] == "output_voltage_v"
        ]
        assert voltage_values and all(value == 5.0 for value in voltage_values), voltage_values
    finally:
        store.close()


def _binding_ref(lattice: Path) -> dict[str, str]:
    raw = (lattice / "run-binding.json").read_bytes()
    return {
        "id": json.loads(raw)["request_id"],
        "version": "0.1.0",
        "sha256": _sha(raw),
    }
