# tests/integration/test_registry_activation.py
"""Activation: idle-boundary generation records and the cache plugin loader.

The PRD-02 "and runs" leg at ABI level: a plugin imported from the admitted,
content-addressed cache — never from ``plugins/`` — opens on scoped services
and dispatches the same configure vector the contract suite pins. The
admission clock is fixed (fixtures expire 2027-09-11); loader clock defaults
are real time observed only through deadlines generous by construction.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
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
    # Atomic write (fix 7a M3): a successful activate leaves exactly the
    # record on disk — no staging sibling survives.
    assert list(records.iterdir()) == [path]


def test_activation_refuses_generation_overwrite(tmp_path: Path) -> None:
    """Fix 7a M2: a regressed generation must not overwrite its record."""
    records = tmp_path / "records"
    first = activate(
        _synthetic_admitted(tmp_path),
        bench_generation=3,
        bench_has_live_lease=False,
        records_dir=records,
        activated_at=ACTIVATED_AT,
    )
    assert first.new_generation == 4

    later = Admitted(
        lock_path=tmp_path / "packages-other.lock.json",
        lock_sha256="ef" * 32,
        manifest_sha256s=("cd" * 32,),
    )
    with pytest.raises(ActivationRejected) as exc:
        activate(
            later,
            bench_generation=3,  # regressed — activation-4.json already exists
            bench_has_live_lease=False,
            records_dir=records,
            activated_at="2026-09-12T01:00:00Z",
        )
    assert exc.value.reason == "generation_conflict"
    # The first record survived the refused overwrite byte-for-byte.
    raw = (records / "activation-4.json").read_bytes()
    assert json.loads(raw) == {
        "lock_sha256": LOCK_SHA,
        "previous_generation": 3,
        "new_generation": 4,
        "activated_at": ACTIVATED_AT,
    }
    # Forward activations are unaffected: the next generation still lands.
    third = activate(
        later,
        bench_generation=4,
        bench_has_live_lease=False,
        records_dir=records,
        activated_at="2026-09-12T01:00:00Z",
    )
    assert third.new_generation == 5
    assert (records / "activation-5.json").is_file()


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


@pytest.mark.parametrize(
    "offender",
    ["../../plugins/sim_psu/plugin.py", "/abs/plugin.py"],
)
def test_load_refuses_traversing_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offender: str
) -> None:
    """Fix 7a I1: containment is structural — a forged manifest cannot un-gate it.

    The forged manifest lists the offending path with role ``implementation``
    (what admission would never produce). The guard must reject before the
    manifest is trusted and before any importlib call — the sentinel asserts
    the load never reached the import machinery, so the resolve join can
    never escape ``<cache_root>/<manifest_sha256>/``.
    """
    forged = {"payload": {"files": [{"path": offender, "role": "implementation"}]}}
    imports: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        importlib.util, "spec_from_file_location", lambda *args: imports.append(args)
    )
    with pytest.raises(ActivationRejected) as exc:
        load_plugin(tmp_path / "cache", forged, "aa" * 32, entry_relpath=offender)
    assert exc.value.reason == "entry_not_implementation"
    assert imports == []


def test_load_refuses_module_without_factory(tmp_path: Path) -> None:
    """Fix 7a M1: a cache module that parses but exposes no factory is refused."""
    sha = "ff" * 32
    payload = b"x = 1\n"
    entry = tmp_path / "cache" / sha / "payload.py"
    entry.parent.mkdir(parents=True)
    entry.write_bytes(payload)
    manifest = {
        "payload": {
            "files": [
                {
                    "path": "payload.py",
                    "role": "implementation",
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            ]
        }
    }
    with pytest.raises(ActivationRejected) as exc:
        load_plugin(tmp_path / "cache", manifest, sha, entry_relpath="payload.py")
    assert exc.value.reason == "unsupported_plugin_module"


def test_load_rejects_tampered_cache_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final-fix wave 2: exec-time integrity — the entry file's on-disk bytes
    are re-hashed against the manifest inventory's pinned digest BEFORE
    importlib executes anything; a cache tampered after admission is refused
    and nothing is imported."""
    closure = _resolve()
    _admit(closure, tmp_path)
    release = _sim_psu_release(closure)
    entry = tmp_path / "cache" / release.manifest_sha256 / "plugin" / "plugin.py"
    honest = entry.read_bytes()
    entry.write_bytes(honest + b"# tampered after admission\n")

    imports: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        importlib.util, "spec_from_file_location", lambda *args: imports.append(args)
    )
    with pytest.raises(ActivationRejected) as exc:
        load_plugin(
            tmp_path / "cache",
            release.manifest,
            release.manifest_sha256,
            entry_relpath="plugin/plugin.py",
        )
    assert exc.value.reason == "file_hash_mismatch"
    assert imports == []  # the import machinery was never reached


def test_load_pops_sys_modules_on_exec_failure(tmp_path: Path) -> None:
    """Wave-1 item 3: an import-time failure leaves no half-initialized
    module in ``sys.modules``. The plugin's own error is the honest surface —
    ``ActivationRejected`` is not invented for a module body that raises —
    but the loader's namespace hygiene must hold regardless."""
    sha = "ee" * 32
    payload = b"raise RuntimeError('boom at import')\n"
    entry = tmp_path / "cache" / sha / "plugin.py"
    entry.parent.mkdir(parents=True)
    entry.write_bytes(payload)
    manifest = {
        "payload": {
            "files": [
                {
                    "path": "plugin.py",
                    "role": "implementation",
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            ]
        }
    }
    module_name = f"plugin_py_{sha}"
    with pytest.raises(RuntimeError, match="boom at import"):
        load_plugin(tmp_path / "cache", manifest, sha, entry_relpath="plugin.py")
    assert module_name not in sys.modules
