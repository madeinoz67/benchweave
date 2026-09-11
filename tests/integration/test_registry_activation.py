# tests/integration/test_registry_activation.py
"""Activation: idle-boundary generation records and the cache plugin loader.

The PRD-02 "and runs" leg at ABI level: a plugin imported from the admitted,
content-addressed cache — never from ``plugins/`` — opens on scoped services
and dispatches the same configure vector the contract suite pins. The
admission clock is fixed (fixtures expire 2027-09-11); loader clock defaults
are real time observed only through deadlines generous by construction.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from benchweave.host import OperationRequest, OperationVerb, QuotaState
from benchweave.registry.activation import (
    ActivationRecord,
    ActivationRejected,
    activate,
    load_plugin,
)
from benchweave.registry.admission import (
    AdmissionLimits,
    Admitted,
    Approval,
    admit,
)
from benchweave.registry.authenticity import load_trust_root
from benchweave.registry.resolver import (
    LocalDirectorySource,
    OriginConfig,
    ResolvedClosure,
    Resolver,
)

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures/registry"
NOW = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)
ACTIVATED_AT = "2026-09-12T00:00:00Z"
LOCK_SHA = "ab" * 32

MAIN_ROOT = load_trust_root("origin-main", REG / "keys" / "main.pub.pem")

# The configure invoke vector, verbatim from tests/contract/test_sim_plugins.py
# (that file is the authority for ABI request construction).
CONFIGURE_ACTION = "otdp.dc_psu.configure/1.0.0"
CONFIGURE_INPUT: dict[str, Any] = {
    "configuration_id": "cfg-1",
    "channel": "ch1",
    "voltage_v": 5.0,
    "current_limit_a": 0.5,
    "ovp_v": 5.5,
    "ocp_a": 0.5,
}


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _resolve() -> ResolvedClosure:
    origins: dict[str, OriginConfig] = {
        "origin-main": OriginConfig(
            registry_id="origin-main",
            root=MAIN_ROOT,
            source=LocalDirectorySource(REG / "origin-main"),
            namespaces=("benchweave",),
        )
    }
    return Resolver(origins).resolve(
        "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
    )


def _admit(closure: ResolvedClosure, work: Path) -> Admitted:
    return admit(
        closure,
        cache_root=work / "cache",
        lock_path=work / "packages.lock.json",
        limits=AdmissionLimits(
            max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1_000_000
        ),
        approval=Approval(
            principal_id="benchweave-test",
            approved_at="2026-09-12T00:00:00Z",
            policy_id="local-policy",
            policy_version="1.0.0",
        ),
        now_ns=NOW,
        roots={"origin-main": MAIN_ROOT},
    )


def _synthetic_admitted(work: Path) -> Admitted:
    """Activation only reads the lock digest; no pipeline needed for its gates."""
    return Admitted(
        lock_path=work / "packages.lock.json",
        lock_sha256=LOCK_SHA,
        manifest_sha256s=("cd" * 32,),
    )


class _NullServices:
    """Minimal scoped-services double, mirroring test_sim_plugins.NullServices.

    One typing repair: ``quota_state`` returns the typed ``QuotaState`` (the
    contract double's plain dict is behaviourally identical for these vectors
    — nothing here reads quotas — but would not satisfy HostServices).
    """

    def __init__(self) -> None:
        self.touches: list[str] = []

    def resolve_content(self, content_id: str) -> bytes:
        self.touches.append(f"resolve:{content_id}")
        return b"{}"

    def retain_evidence(self, key: str, payload: bytes) -> str:
        self.touches.append(f"retain:{key}")
        return f"evidence-{key}"

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        self.touches.append(f"event:{kind}")

    def quota_state(self) -> QuotaState:
        return QuotaState(dataset_bytes_used=0, evidence_entries_used=0, events_emitted=0)

    def register_reading_sink(self, sink: Any) -> None:
        self.touches.append("reading-sink")


def _invoke(action_id: str, input_: dict[str, Any]) -> OperationRequest:
    """Verbatim construction from test_sim_plugins._invoke."""
    return OperationRequest(
        operation_id="op-1",
        verb=OperationVerb.INVOKE,
        arguments={"action_id": action_id, "input": input_},
    )


def _sim_psu_release(closure: ResolvedClosure) -> Any:
    return next(r for r in closure.releases if r.package_id == "benchweave/sim-psu")


# --- activate: the idle boundary ----------------------------------------------


def test_activation_refuses_live_lease(tmp_path: Path) -> None:
    records = tmp_path / "records"
    with pytest.raises(ActivationRejected) as exc:
        activate(
            _synthetic_admitted(tmp_path),
            bench_generation=3,
            bench_has_live_lease=True,
            records_dir=records,
            activated_at=ACTIVATED_AT,
        )
    assert exc.value.reason == "not_idle"
    assert not records.exists()


def test_activation_writes_generation_record(tmp_path: Path) -> None:
    records = tmp_path / "records"
    record: ActivationRecord = activate(
        _synthetic_admitted(tmp_path),
        bench_generation=3,
        bench_has_live_lease=False,
        records_dir=records,
        activated_at=ACTIVATED_AT,
    )
    assert record.lock_sha256 == LOCK_SHA
    assert record.previous_generation == 3
    assert record.new_generation == 4
    assert record.activated_at == ACTIVATED_AT

    path = records / "activation-4.json"
    assert path.is_file()
    raw = path.read_bytes()
    assert raw == _canonical(json.loads(raw))
    assert json.loads(raw) == {
        "lock_sha256": LOCK_SHA,
        "previous_generation": 3,
        "new_generation": 4,
        "activated_at": ACTIVATED_AT,
    }


# --- load_plugin: the "runs" leg at ABI level ---------------------------------


def test_load_plugin_from_cache(tmp_path: Path) -> None:
    closure = _resolve()
    admitted = _admit(closure, tmp_path)
    record = activate(
        admitted,
        bench_generation=0,
        bench_has_live_lease=False,
        records_dir=tmp_path / "records",
        activated_at=ACTIVATED_AT,
    )
    assert record.new_generation == 1

    release = _sim_psu_release(closure)
    plugin = load_plugin(
        tmp_path / "cache",
        release.manifest,
        release.manifest_sha256,
        entry_relpath="plugin/plugin.py",
    )
    assert plugin.simulation.simulated is True

    plugin.plugin_open(_NullServices())
    try:
        configured = plugin.dispatch(
            _invoke(CONFIGURE_ACTION, CONFIGURE_INPUT), deadline_ns=10**12
        )
        assert configured.status.value == "ok"
        assert configured.data["result"]["configuration_id"] == "cfg-1"
        reading = plugin.dispatch(
            OperationRequest.read("op-2", parameter="voltage_setpoint_v"),
            deadline_ns=10**12,
        )
        assert reading.data.value == 5.0
    finally:
        plugin.plugin_close()


def test_load_refuses_non_implementation_entry(tmp_path: Path) -> None:
    closure = _resolve()
    _admit(closure, tmp_path)
    release = _sim_psu_release(closure)
    with pytest.raises(ActivationRejected) as exc:
        load_plugin(
            tmp_path / "cache",
            release.manifest,
            release.manifest_sha256,
            entry_relpath="LICENSE",
        )
    assert exc.value.reason == "entry_not_implementation"
