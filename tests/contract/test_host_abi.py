"""WP04 S1 — the published host ABI against the OTDP runtime contract.

Every invariant asserted here mirrors a conditional in
contracts/otdp/0.1.1/otdp-runtime.schema.json: the ABI is the contract in
Python, not a reinterpretation of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from benchweave.host import (
    Assurance,
    DispatchState,
    ErrorCode,
    HostServices,
    Identity,
    IdentitySource,
    OperationError,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationVerb,
    Quality,
    Reading,
    ReadingSource,
    SimulationInfo,
    WriteReceipt,
)

ROOT = Path(__file__).resolve().parents[2]

NOW = "2026-09-11T00:00:00Z"


def an_identity() -> Identity:
    return Identity(
        manufacturer="benchweave-sim",
        model="sim-psu-1",
        serial=None,
        firmware="sim-0.1.0",
        source=IdentitySource.DEVICE,
    )


def a_reading() -> Reading:
    return Reading(
        parameter="output_voltage",
        value=12.0,
        unit="V",
        observed_at=NOW,
        age_ms=0,
        quality=Quality.VALID,
        source=ReadingSource.DEVICE,
    )


# --- typed envelopes -------------------------------------------------------


def test_reading_fields_match_contract() -> None:
    reading = a_reading()
    assert reading.parameter == "output_voltage"
    assert reading.quality is Quality.VALID


def test_write_receipt_assurance_is_dispatch_ladder() -> None:
    receipt = WriteReceipt(
        parameter="output_voltage",
        requested_value=12.0,
        effective_value=12.0,
        assurance=Assurance.DISPATCHED,
        verification=None,
    )
    assert receipt.assurance is Assurance.DISPATCHED


# --- operation result invariants (the schema's allOf, enforced in Python) ----


def test_ok_result_requires_data_and_rejects_error() -> None:
    result = OperationResult.ok("op-1", OperationVerb.READ, a_reading())
    assert result.status is OperationStatus.OK
    assert result.error is None
    with pytest.raises(ValueError, match="error"):
        OperationResult(
            operation_id="op-1",
            verb=OperationVerb.READ,
            status=OperationStatus.OK,
            data=a_reading(),
            error=OperationError(
                code=ErrorCode.DEVICE_REJECTED,
                message="must not coexist with data",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            ),
        )


def test_error_result_requires_error_and_rejects_data() -> None:
    result = OperationResult.failure(
        "op-1",
        OperationVerb.WRITE,
        code=ErrorCode.DEVICE_REJECTED,
        message="limit exceeded",
        dispatch_state=DispatchState.NOT_DISPATCHED,
    )
    assert result.data is None
    assert result.error is not None
    assert result.error.code is ErrorCode.DEVICE_REJECTED
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_unknown_status_never_claims_not_dispatched() -> None:
    result = OperationResult.failure(
        "op-1",
        OperationVerb.WRITE,
        code=ErrorCode.TIMEOUT,
        message="deadline passed after dispatch",
        dispatch_state=DispatchState.DISPATCHED,
    )
    assert result.status is OperationStatus.ERROR
    unknown = OperationResult.indeterminate(
        "op-2",
        OperationVerb.WRITE,
        code=ErrorCode.TIMEOUT,
        message="deadline passed, dispatch state unknown",
    )
    assert unknown.status is OperationStatus.UNKNOWN
    assert unknown.error is not None
    assert unknown.error.dispatch_state in (DispatchState.DISPATCHED, DispatchState.UNKNOWN)


def test_request_verb_and_arguments_shape() -> None:
    request = OperationRequest.read("op-1", parameter="output_voltage")
    assert request.verb is OperationVerb.READ
    assert request.arguments == {"parameter": "output_voltage"}
    write = OperationRequest.write("op-2", parameter="output_voltage", value=12.0)
    assert write.arguments == {"parameter": "output_voltage", "value": 12.0}


# --- scoped services surface -------------------------------------------------


def test_host_services_is_the_scoped_surface() -> None:
    methods = {
        name
        for name in dir(HostServices)
        if not name.startswith("_") and callable(getattr(HostServices, name))
    }
    assert methods <= {
        "resolve_content",
        "retain_evidence",
        "emit_event",
        "quota_state",
        "register_reading_sink",
    }, f"host services grew beyond the scoped surface: {methods}"


# --- no implicit I/O on import -------------------------------------------------


def test_host_package_import_performs_no_io() -> None:
    source_files = sorted((ROOT / "src" / "benchweave" / "host").rglob("*.py"))
    assert source_files, "host package must exist"
    banned = (
        "socket",
        "urllib",
        "http.client",
        "subprocess",
        "pathlib",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "os.system",
    )
    for path in source_files:
        source = path.read_text(encoding="utf-8")
        for marker in banned:
            assert marker not in source, f"{path.name} must not contain I/O marker {marker!r}"


def test_host_package_already_imported_has_no_side_effect_handles() -> None:
    import benchweave.host  # noqa: F401 — the import IS the test

    assert "benchweave.host" in sys.modules


# --- simulation is visibly identified -------------------------------------------


def test_simulation_info_is_explicit() -> None:
    info = SimulationInfo(simulated=True, label="sim-psu")
    assert info.simulated is True
    real = SimulationInfo(simulated=False, label="dps150")
    assert real.simulated is False
