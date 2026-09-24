"""The capture runtime surfaces at admission (issue #176 increment 2, §1b).

The projection (CON-10 capture surface), the semantics mirror (CTL-7's
``capture_undeclared:`` family) and the policy kind (CTL-4's
``capture_constraint:``), exercised against DEV_HEAD-composed admission:
every admission here runs ``admit_documents`` with the manifest-declared
dev head's contracts. Until the promotion event this machinery is
corpus-gated dormant code on main — the default composition resolves
0.1.0, which refuses capture steps at the schema.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.control.documents import AdmissionRejected, admit_documents
from benchweave.control.policy import PolicyDenied, check_allowed
from benchweave.control.semantics import check_semantics, worst_case_body_ms
from benchweave.vendoring import declared_dev_family

HEAD = declared_dev_family("execution")
EXECUTION_FIXTURES = Path(HEAD).resolve().parents[2] / "fixtures" / "execution"
NOW = "2026-09-24T00:00:00Z"


def _capture_descriptor(
    path: Path,
    source: Path,
    *,
    capture: bool = True,
    artifact_writer: bool = True,
    formats: list[str] | None = None,
    max_samples: int = 1024,
    max_bytes: int = 8192,
) -> dict[str, Any]:
    """The committed sim-psu descriptor, additively mutated (the
    ``_mutated_descriptor`` idiom) into a capture-capable harness device."""
    descriptor: dict[str, Any] = json.loads(source.read_text())
    adapter = descriptor["integration"]["adapter"]
    permissions = ["scoped_transport"]
    if capture and artifact_writer:
        permissions.append("artifact_writer")
    adapter["permissions"] = permissions
    adapter["entry_point"] = "benchweave_sim_psu.plugin:create_plugin"
    if capture:
        descriptor["capture_formats"] = (
            ["waveform_f64le", "raw_binary"] if formats is None else formats
        )
        descriptor["capture_limits"] = {
            "max_samples": max_samples,
            "max_bytes": max_bytes,
        }
    path.write_text(json.dumps(descriptor, indent=2) + "\n")
    return descriptor


def _capture_step(
    *,
    step_id: str = "grab",
    fmt: str = "waveform_f64le",
    sample_count: int = 64,
    max_bytes: int = 1024,
    timeout_ms: int = 400,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "kind": "capture",
        "role": "supply",
        "format": fmt,
        "sample_count": sample_count,
        "max_bytes": max_bytes,
        "timeout_ms": timeout_ms,
    }


def _lattice(
    tmp_path: Path,
    *,
    capture_device: bool = True,
    artifact_writer: bool = True,
    descriptor_formats: list[str] | None = None,
    descriptor_max_samples: int = 1024,
    descriptor_max_bytes: int = 8192,
    steps: list[dict[str, Any]] | None = None,
    policy_rules: list[dict[str, Any]] | None = None,
    request_id: str = "req-capture-1",
) -> dict[str, Path]:
    """A minimal execution lattice over one harness supply device."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    descriptor = _capture_descriptor(
        tmp_path / "descriptor-demo-supply.json",
        EXECUTION_FIXTURES / "descriptor-sim-psu.json",
        capture=capture_device,
        artifact_writer=artifact_writer,
        formats=descriptor_formats,
        max_samples=descriptor_max_samples,
        max_bytes=descriptor_max_bytes,
    )
    if steps is None:
        steps = [_capture_step()]
    max_body_ms = 4000
    procedure: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "capture-procedure",
        "version": "0.1.0",
        "description": "Synthetic capture harness procedure.",
        "mode": "gateway_owned",
        "safety_policy": {"id": "capture-policy", "version": "0.1.0"},
        "roles": [
            {
                "id": "supply",
                "required_profiles": ["otdp.dc_psu/1.0.0"],
                "channels": ["output"],
            }
        ],
        "max_body_ms": max_body_ms,
        "max_protection_ms": 2000,
        "steps": steps,
    }
    procedure_path = tmp_path / "procedure-capture.json"
    procedure_path.write_text(json.dumps(procedure, indent=2) + "\n")

    if policy_rules is None:
        policy_rules = [
            {
                "device_id": "demo-supply",
                "kind": "capture",
                "format": "waveform_f64le",
                "capture_constraints": {
                    "type": "object",
                    "properties": {
                        "sample_count": {"maximum": 1024},
                        "max_bytes": {"maximum": 65536},
                    },
                },
            }
        ]
    policy: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "capture-policy",
        "version": "0.1.0",
        "description": "Synthetic capture harness policy.",
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
        "allow_rules": policy_rules,
        "continuous_conditions": [
            {
                "id": "dut-voltage-bounds",
                "kind": "numeric",
                "signal": "dut-voltage",
                "unit": "V",
                "minimum": -0.1,
                "maximum": 5.5,
            }
        ],
        "independent_protection": {
            "required": False,
            "assessment": {
                "id": "capture-protection-assessment",
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
                    "device_id": "demo-supply",
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
    policy_path = tmp_path / "safety-policy.json"
    policy_path.write_text(json.dumps(policy, indent=2) + "\n")

    lock_path = tmp_path / "package-lock.json"
    lock_path.write_bytes((EXECUTION_FIXTURES / "package-lock.json").read_bytes())

    def sha(path: Path) -> str:
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()

    bench: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "capture-bench",
        "version": "0.1.0",
        "description": "Synthetic capture harness bench. Not hardware-qualified.",
        "gateway_id": "capture-gateway",
        "fixture": {
            "id": "capture-fixture",
            "revision": "1",
            "identity_record_id": "ident-capture",
        },
        "dut_class": "low_voltage_embedded",
        "policy": {
            "id": "capture-policy",
            "version": "0.1.0",
            "sha256": sha(policy_path),
        },
        "package_lock": {"id": "sim-lock", "version": "0.1.0", "sha256": sha(lock_path)},
        "commissioning_id": "capture-commissioning",
        "dut_ids": ["demo-supply"],
        "protection_mechanisms": [],
        "devices": [
            {
                "id": "demo-supply",
                "generation": 1,
                "descriptor": {
                    "id": descriptor["id"],
                    "version": descriptor["descriptor_version"],
                    "sha256": sha(tmp_path / "descriptor-demo-supply.json"),
                },
                "identity_record_id": "ident-psu",
                "connection_key": "sim_psu_local",
                "channels": ["ch1"],
            }
        ],
        "resources": [{"id": "dut-net", "device_ids": ["demo-supply"], "depends_on": []}],
        "terminals": [
            {
                "id": "psu-out",
                "owner_kind": "device",
                "owner_id": "demo-supply",
                "channel_id": "ch1",
                "name": "out",
                "domain_id": "dut",
            },
            {
                "id": "psu-in",
                "owner_kind": "device",
                "owner_id": "demo-supply",
                "channel_id": "ch1",
                "name": "in",
                "domain_id": "dut",
            },
        ],
        "nets": [{"id": "n1", "terminal_ids": ["psu-out", "psu-in"]}],
        "signals": [
            {
                "id": "dut-voltage",
                "quantity": "voltage",
                "unit": "V",
                "poll_ms": 50,
                "max_age_ms": 500,
                "absolute_error": 0.05,
                "resource_id": "dut-net",
                "source": {
                    "kind": "parameter",
                    "device_id": "demo-supply",
                    "parameter": "output_voltage_v",
                },
            }
        ],
    }
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps(bench, indent=2) + "\n")

    commissioning: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "capture-commissioning",
        "version": "0.1.0",
        "description": "Synthetic capture harness commissioning. Not hardware-qualified.",
        "bench": {"id": "capture-bench", "version": "0.1.0", "sha256": sha(bench_path)},
        "policy": {
            "id": "capture-policy",
            "version": "0.1.0",
            "sha256": sha(policy_path),
        },
        "package_lock": {
            "id": "sim-lock",
            "version": "0.1.0",
            "sha256": sha(lock_path),
        },
        "procedure_refs": [
            {
                "id": "capture-procedure",
                "version": "0.1.0",
                "sha256": sha(procedure_path),
            }
        ],
        "dut_class": "low_voltage_embedded",
        "modes": ["supervised"],
        "owners": {
            "bench": "capture-harness-owner",
            "test_safety": "capture-harness-owner",
            "system": "capture-harness-owner",
        },
        "approved_by": "capture-harness-owner",
        "approved_at": "2026-09-11T00:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "offline_status_max_age_ms": 86400000,
        "scheduling_overhead_ms": 100,
        "evidence": [
            {
                "category": "envelope",
                "report": {
                    "id": "capture-envelope-report",
                    "version": "0.1.0",
                    "sha256": "0" * 64,
                },
                "tested_at": "2026-09-11T00:00:00Z",
                "scope": "Simulator envelope over the synthetic capture supply.",
                "result": "passed",
                "limitations": ["simulator-only"],
            }
        ],
    }
    commissioning_path = tmp_path / "commissioning.json"
    commissioning_path.write_text(json.dumps(commissioning, indent=2) + "\n")

    binding: dict[str, Any] = {
        "contract_version": "0.1.0",
        "request_id": request_id,
        "procedure": {"id": "capture-procedure", "version": "0.1.0"},
        "bench": {"id": "capture-bench", "version": "0.1.0"},
        "policy": {"id": "capture-policy", "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "commissioning": {"id": "capture-commissioning", "version": "0.1.0"},
        "bindings": [
            {"role": "supply", "device_id": "demo-supply", "channels": {"output": "ch1"}}
        ],
    }
    for name, path in (
        ("procedure", procedure_path),
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lock_path),
        ("commissioning", commissioning_path),
    ):
        binding[name]["sha256"] = sha(path)
    binding_path = tmp_path / "run-binding.json"
    binding_path.write_text(json.dumps(binding, indent=2) + "\n")

    return {
        "procedure": procedure_path,
        "policy": policy_path,
        "bench": bench_path,
        "binding": binding_path,
        "commissioning": commissioning_path,
        "lock": lock_path,
        "descriptor": tmp_path / "descriptor-demo-supply.json",
    }


def _admit(paths: dict[str, Path]) -> Any:
    return admit_documents(
        procedure_path=paths["procedure"],
        policy_path=paths["policy"],
        bench_path=paths["bench"],
        binding_path=paths["binding"],
        commissioning_path=paths["commissioning"],
        descriptor_paths={"demo-supply": paths["descriptor"]},
        now_wall=NOW,
        contracts=HEAD,
    )


def _admit_lattice(tmp_path: Path, **kwargs: Any) -> Any:
    return _admit(_lattice(tmp_path, **kwargs))


# --- projection (CON-10 capture surface) --------------------------------------


def test_projection_carries_the_capture_surface(tmp_path: Path) -> None:
    """A capture-declaring device's execution view carries the capture
    surface; a non-capturing device's does not (and artifact_writer reads
    False from the transport-only permissions)."""
    docs = _admit_lattice(tmp_path / "capturing")
    view = docs.descriptors["demo-supply"]
    assert view["artifact_writer"] is True
    assert view["capture_formats"] == ["waveform_f64le", "raw_binary"]
    assert view["capture_limits"] == {"max_samples": 1024, "max_bytes": 8192}

    plain = _admit_lattice(tmp_path / "plain", capture_device=False)
    view = plain.descriptors["demo-supply"]
    assert view["artifact_writer"] is False
    assert "capture_formats" not in view
    assert "capture_limits" not in view


def test_projection_view_stays_total_for_the_preexisting_members(
    tmp_path: Path,
) -> None:
    """The capture surface JOINS the total execution view; the preexisting
    projection members are untouched (the descriptor view stays what
    binding and semantics already read)."""
    docs = _admit_lattice(tmp_path / "total")
    view = docs.descriptors["demo-supply"]
    assert view["id"] == "dev.benchweave.sim-psu"
    assert view["profiles"] == ["otdp.dc_psu/1.0.0"]
    assert {str(action["action_id"]) for action in view["actions"]} >= {
        "otdp.dc_psu.configure/1.0.0"
    }
    assert "voltage_setpoint_v" in view["parameters"]


# --- semantics (CTL-7 capture mirror + budget) ---------------------------------


def test_a_r3_capture_step_admits_on_a_capture_declaring_device(
    tmp_path: Path,
) -> None:
    """A capture step on a capture-declaring device passes the real
    admission path — schema, semantics mirror, binding — under the
    dev-resolved contracts."""
    docs = _admit_lattice(tmp_path / "admits")
    check_semantics(docs, now_wall=NOW)  # no raise
    from benchweave.control.binding import resolve_binding

    resolve_binding(docs)  # no raise


@pytest.mark.parametrize(
    ("kwargs", "detail"),
    [
        ({"capture_device": False}, "declares no capture surface"),
        ({"artifact_writer": False}, "artifact_writer"),
        ({"descriptor_formats": ["raw_binary"]}, "waveform_f64le"),
        ({"descriptor_max_samples": 32}, "sample_count"),
        ({"descriptor_max_bytes": 256}, "max_bytes"),
    ],
)
def test_a_r3_undeclared_capture_refuses_capture_undeclared(
    tmp_path: Path, kwargs: dict[str, Any], detail: str
) -> None:
    """Every undeclared-capture shape refuses with the
    ``capture_undeclared:`` mirror prefix at semantics."""
    docs = _admit_lattice(tmp_path / "refuses", **kwargs)
    with pytest.raises(AdmissionRejected, match="capture_undeclared:") as refused:
        check_semantics(docs, now_wall=NOW)
    assert detail in str(refused.value)


def test_worst_case_body_ms_counts_capture_timeout() -> None:
    """The budget walk counts a capture's timeout_ms like an invoke's."""
    steps: list[dict[str, Any]] = [
        _capture_step(timeout_ms=400),
        {"id": "settle", "kind": "delay", "duration_ms": 100},
        {
            "id": "set-voltage",
            "kind": "write",
            "role": "supply",
            "parameter": "voltage_setpoint_v",
            "value": 5.0,
            "timeout_ms": 500,
        },
    ]
    assert worst_case_body_ms(steps) == 1000
    nested: list[dict[str, Any]] = [
        {
            "id": "twice",
            "kind": "repeat",
            "count": 3,
            "steps": [_capture_step(timeout_ms=10)],
        }
    ]
    assert worst_case_body_ms(nested) == 30


def test_a_r5_capture_budget_overrun_refuses_admission(tmp_path: Path) -> None:
    """A procedure whose static bound overruns max_body_ms on capture
    timeouts alone refuses admission (body_budget:)."""
    steps = [_capture_step(step_id="grab", timeout_ms=6000)]
    docs = _admit_lattice(tmp_path / "overrun", steps=steps)
    with pytest.raises(AdmissionRejected, match="body_budget:"):
        check_semantics(docs, now_wall=NOW)


# --- policy (CTL-4 capture kind) ------------------------------------------------


CAPTURE_POLICY: dict[str, Any] = {
    "allow_rules": [
        {
            "device_id": "dev-1",
            "kind": "capture",
            "format": "waveform_f64le",
            "capture_constraints": {
                "type": "object",
                "properties": {
                    "sample_count": {"maximum": 1024},
                    "max_bytes": {"maximum": 65536},
                },
            },
        }
    ],
    "continuous_conditions": [],
}


def _capture_payload(fmt: str = "waveform_f64le") -> dict[str, Any]:
    return {"format": fmt, "sample_count": 64, "max_bytes": 1024}


def test_policy_capture_allowed_when_a_rule_matches() -> None:
    check_allowed(CAPTURE_POLICY, "dev-1", "capture", "waveform_f64le", _capture_payload())


def test_policy_capture_deny_by_default_without_a_rule() -> None:
    with pytest.raises(PolicyDenied, match="no_matching_rule:"):
        check_allowed(
            CAPTURE_POLICY, "dev-1", "capture", "raw_binary", _capture_payload("raw_binary")
        )


def test_policy_capture_constraint_violation_refuses() -> None:
    with pytest.raises(PolicyDenied, match="capture_constraint:") as denied:
        check_allowed(
            CAPTURE_POLICY,
            "dev-1",
            "capture",
            "waveform_f64le",
            {"format": "waveform_f64le", "sample_count": 9999, "max_bytes": 1024},
        )
    assert denied.value.rule_ids == ("allow_rules[0]",)


def test_policy_capture_vacuous_constraint_warns() -> None:
    policy: dict[str, Any] = copy.deepcopy(CAPTURE_POLICY)
    policy["allow_rules"][0]["capture_constraints"] = {}
    with pytest.warns(UserWarning, match="vacuous_constraint:"):
        check_allowed(policy, "dev-1", "capture", "waveform_f64le", _capture_payload())


def test_policy_capture_non_object_payload_refuses() -> None:
    with pytest.raises(PolicyDenied) as denied:
        check_allowed(CAPTURE_POLICY, "dev-1", "capture", "waveform_f64le", 64)
    assert "capture_constraint:" in str(denied.value)
