"""The commissioned FTDI provider runtime and its grant (issue #568, §2).

Derivations (from the design record §1.2/§1.5/§2, not restatements):

- the grant is the seven-fact conjunction: the landed three checks, the
  endpoint resolution (one key → exactly one commissioned USB identity),
  and a runtime whose op table covers every op the admitted grammar's
  request schema discriminates — the table check refuses the GRANT, before
  the device is opened (an un-runnable procedure refuses at build, the
  honest #260 posture);
- the runtime ladder: grammar kinds dispatch through the table (one
  ``asyncio.to_thread`` call, one bounded attempt, never a retry); the
  §8.1 stream trio rides the data pipe with exact_bytes precedence,
  terminator detection, bounded reads and deadline-aware pacing; the
  reserved can/i2c/spi kinds refuse typed ``provider_runtime_kind_
  unsupported:`` (reserved but unserved — they carry gateway-authorisation
  semantics the corpus has not designed);
- intent-first evidence for the two energising ops (``set_bitmode``,
  ``reset_device`` — the classification is a module constant, not a
  per-call judgement): the evidence row lands BEFORE the driver call; a
  row failure refuses ``provider_runtime_audit_refused:`` and the driver
  is never called — EXCEPT the ``protect:`` carve-out, where the safe
  action dispatches and the failed-intent disclosure flushes at close
  (evidence storage is never a dependency of protection);
- driver faults map to ``ConnectionError`` naming the class; a faulted
  runtime stays faulted (reconnect is a new run);
- a missing pyftdi refuses ``provider_runtime_backend_missing:`` naming
  the install extra — at the connections load (admission, loud and early)
  and at the device open.

The double sits at the DRIVER boundary (the injectable ``FtdiDriver``
protocol), driven by #564-format journal provider rows — nothing but the
USB boundary is mocked. The module under test is new: every name resolves
at call time (the new-module RED convention).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.control.provider_settings import (
    load_provider_connections,
    load_transport_settings,
)


def _runtime_module() -> Any:
    return importlib.import_module("benchweave.content.provider_runtime")


def _transport_module() -> Any:
    return importlib.import_module("benchweave.content.provider_transport")


# --- the fixture family: the ftdi-control contract, authored in-tree ----------

#: The seven control ops the banked ftdi-control 1.0.0 grammar declares —
#: the same op vocabulary the runtime's table dispatches. The contract
#: instance below is authored here (operator-supplied bytes at admission;
#: invented approval dates, the banked grammar's shape).
FTDI_OPS = (
    "reset_device",
    "set_timeouts",
    "set_latency",
    "set_baud",
    "purge",
    "set_bitmode",
    "read_pins",
)

_REQUEST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "oneOf": [
        {
            "properties": {"op": {"const": "reset_device"}},
            "required": ["op"],
            "additionalProperties": False,
        },
        {
            "properties": {
                "op": {"const": "set_timeouts"},
                "read_ms": {"type": "integer", "minimum": 0},
                "write_ms": {"type": "integer", "minimum": 0},
            },
            "required": ["op", "read_ms", "write_ms"],
            "additionalProperties": False,
        },
        {
            "properties": {
                "op": {"const": "set_latency"},
                "ms": {"type": "integer", "minimum": 0, "maximum": 255},
            },
            "required": ["op", "ms"],
            "additionalProperties": False,
        },
        {
            "properties": {"op": {"const": "set_baud"}, "baud": {"type": "integer", "minimum": 1}},
            "required": ["op", "baud"],
            "additionalProperties": False,
        },
        {
            "properties": {"op": {"const": "purge"}, "queue": {"enum": ["tx", "rx"]}},
            "required": ["op", "queue"],
            "additionalProperties": False,
        },
        {
            "properties": {
                "op": {"const": "set_bitmode"},
                "mask": {"type": "integer", "minimum": 0, "maximum": 255},
                "mode": {"type": "integer", "minimum": 0, "maximum": 255},
            },
            "required": ["op", "mask", "mode"],
            "additionalProperties": False,
        },
        {
            "properties": {"op": {"const": "read_pins"}},
            "required": ["op"],
            "additionalProperties": False,
        },
    ],
}

_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "oneOf": [
        {"maxProperties": 0},
        {
            "properties": {
                "data": {
                    "type": "string",
                    "contentEncoding": "base64",
                    "minLength": 4,
                    "maxLength": 4,
                    "pattern": "^[A-Za-z0-9+/]{2}==$",
                }
            },
            "required": ["data"],
            "additionalProperties": False,
        },
    ],
}


def _ftdi_contract(
    *, extra_op: dict[str, Any] | None = None, expires: str = "2027-10-26T00:00:00Z"
) -> dict[str, Any]:
    """The ftdi-control contract instance, operator-supplied shape."""
    one_of = list(_REQUEST_SCHEMA["oneOf"])
    if extra_op is not None:
        one_of.append(extra_op)
    request = dict(_REQUEST_SCHEMA)
    request["oneOf"] = one_of
    return {
        "contract_version": "0.1.0",
        "id": "urn:otdp:transport-provider:ftdi-control:1.0.0",
        "feature_id": "otdp.transport.ftdi-control/1.0.0",
        "version": "1.0.0",
        "description": "Test-authored FTDI common control contract (issue #568).",
        "transport_kind": "ftdi_control",
        "transaction_grammar": [
            {
                "kind": "ftdi_control",
                "request_schema": request,
                "result_schema": _RESULT_SCHEMA,
                "limits": {},
            }
        ],
        "security_scope": "commissioned_connection",
        "host_requirements": {
            "summary": "Host-side FTDI-class access to the commissioned device only.",
            "native_libraries": [],
            "privileges": [],
        },
        "approval": {
            "approved_by": "test",
            "approved_at": "2026-10-28T00:00:00Z",
            "expires_at": expires,
            "evidence": [
                {
                    "category": "protocol",
                    "report": {
                        "id": "issue-568-gateway-runtime-tests",
                        "version": "1.0.0",
                        "sha256": "b" * 64,
                    },
                    "tested_at": "2026-10-28T00:00:00Z",
                    "scope": "Test-authored grammar of the FTDI common control surface.",
                    "result": "partial",
                    "limitations": [
                        "A test-authored instance: no hardware session backs it"
                    ],
                }
            ],
        },
    }


class _Context:
    """The bridge's dispatch context, doubled: the operation id, the
    deadline, the services the runtime stamps from."""

    def __init__(self, operation_id: str = "op-1") -> None:
        self.operation_id = operation_id
        self.deadline_monotonic = 1_000_000.0
        self.dispatched = True
        self.cancelled = False
        self.services: Any = _Services()


class _Services:
    def monotonic(self) -> float:
        return 0.0


class ScriptedDriver:
    """The driver-boundary double: records every call, answers from a
    script, and can be made to fault or to open-refuse. Derived from the
    provider rows of a #564-format journal at the test's authoring — the
    same row evidence the SDK's ScriptedFtdiDriver consumes."""

    def __init__(
        self,
        *,
        answers: dict[str, Any] | None = None,
        fault_on: str | None = None,
        inbound: list[bytes] | None = None,
    ) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._answers = answers or {}
        self._fault_on = fault_on
        self._inbound = list(inbound or [])
        self.opened = False

    # the FtdiDriver protocol surface
    def reset_device(self) -> None:
        self._record("reset_device")
        self._maybe_fault("reset_device")

    def set_timeouts(self, read_ms: int, write_ms: int) -> None:
        self._record("set_timeouts", read_ms, write_ms)
        self._maybe_fault("set_timeouts")

    def set_latency(self, ms: int) -> None:
        self._record("set_latency", ms)
        self._maybe_fault("set_latency")

    def set_baud(self, baud: int) -> None:
        self._record("set_baud", baud)
        self._maybe_fault("set_baud")

    def purge(self, queue: str) -> None:
        self._record("purge", queue)
        self._maybe_fault("purge")

    def set_bitmode(self, mask: int, mode: int) -> None:
        self._record("set_bitmode", mask, mode)
        self._maybe_fault("set_bitmode")

    def read_pins(self) -> int:
        self._record("read_pins")
        self._maybe_fault("read_pins")
        return int(self._answers.get("read_pins", 0))

    def write_data(self, data: bytes) -> int:
        self._record("write_data", bytes(data))
        self._maybe_fault("write_data")
        return len(data)

    def read_data(self, size: int) -> bytes:
        self._record("read_data", size)
        self._maybe_fault("read_data")
        if not self._inbound:
            return b""
        chunk = self._inbound.pop(0)
        return chunk[:size]

    def close(self) -> None:
        self._record("close")
        self.opened = False

    def _record(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))

    def _maybe_fault(self, name: str) -> None:
        if self._fault_on == name:
            raise OSError("usb device detached (planted fault)")

    def ops(self) -> list[tuple[str, tuple[Any, ...]]]:
        """The op-call sequence, close excluded (close is lifecycle, not
        conversation)."""
        return [call for call in self.calls if call[0] != "close"]


# --- the driver-boundary journal double ---------------------------------------


def _journal_provider_rows() -> list[dict[str, Any]]:
    """The provider rows of a #564-format journal: the recorded bring-up
    conversation (op, params, order) the Metric-A parity runs compare
    against. Rows are in the journal's document form (base64 for byte
    fields; the ftdi control grammar carries none)."""
    return [
        {
            "name": "bring-up-1",
            "transaction": {"kind": "ftdi_control", "op": "reset_device"},
            "response": {},
        },
        {
            "name": "bring-up-2",
            "transaction": {
                "kind": "ftdi_control",
                "op": "set_timeouts",
                "read_ms": 50,
                "write_ms": 500,
            },
            "response": {},
        },
        {
            "name": "bring-up-3",
            "transaction": {"kind": "ftdi_control", "op": "set_baud", "baud": 115200},
            "response": {},
        },
        {
            "name": "bring-up-4",
            "transaction": {
                "kind": "ftdi_control",
                "op": "set_bitmode",
                "mask": 255,
                "mode": 64,
            },
            "response": {},
        },
        {
            "name": "bring-up-5",
            "transaction": {"kind": "ftdi_control", "op": "read_pins"},
            "response": {"data": base64.b64encode(bytes([0x5A])).decode("ascii")},
        },
    ]


def _journal_document() -> dict[str, Any]:
    return {
        "journal_version": "1",
        "recorded": {"started_at": "2026-10-28T00:00:00Z", "source": "a real bench"},
        "provider": {
            "feature_id": "otdp.transport.ftdi-control/1.0.0",
            "id": "urn:otdp:transport-provider:ftdi-control:1.0.0",
            "sha256": "0" * 64,
        },
        "rows": _journal_provider_rows(),
    }


# --- the registry + endpoints over the authored contract ----------------------


def _admitted_package(tmp_path: Path, contract: dict[str, Any]) -> tuple[Path, Any, Any]:
    """Settings + connections admitting ``contract`` and binding one key —
    the fixtures a commissioned provider lattice carries."""
    raw = (json.dumps(contract, indent=2) + "\n").encode()
    (tmp_path / "ftdi-control.json").write_bytes(raw)
    settings = {
        "config_version": "1",
        "admitted": [
            {
                "id": contract["id"],
                "version": contract["version"],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "feature_id": contract["feature_id"],
                "document": "ftdi-control.json",
            }
        ],
        "connections": [
            {"connection_key": "fpga_prog", "provider_id": contract["id"]}
        ],
    }
    (tmp_path / "transport-settings.json").write_text(json.dumps(settings, indent=2))
    (tmp_path / "provider-connections.json").write_text(
        json.dumps(
            {
                "config_version": "1",
                "connections": [
                    {
                        "connection_key": "fpga_prog",
                        "usb": {
                            "vendor_id": 1027,
                            "product_id": 24593,
                            "serial": "FT-DEMO-0042",
                            "interface": 1,
                        },
                    }
                ],
            },
            indent=2,
        )
    )
    registry = load_transport_settings(tmp_path / "transport-settings.json")
    endpoints = load_provider_connections(
        tmp_path / "provider-connections.json", registry
    )
    return tmp_path, registry, endpoints


def _provider_descriptor(
    contract: dict[str, Any], raw: bytes, key: str = "fpga_prog"
) -> dict[str, Any]:
    """A provider-declaring raw descriptor shape (the transport/provider
    block the grant gate reads)."""
    return {
        "id": "dev.test.ftdi-bound",
        "integration": {"mode": "adapter", "adapter": {"permissions": ["scoped_transport"]}},
        "transport": {
            "connection_key": key,
            "provider": {
                "id": contract["id"],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "path": "ftdi-control.json",
            },
        },
    }


def _grant_inputs(
    tmp_path: Path, contract: dict[str, Any]
) -> tuple[dict[str, Any], Any, Any]:
    package, registry, endpoints = _admitted_package(tmp_path, contract)
    raw = (package / "ftdi-control.json").read_bytes()
    descriptor = _provider_descriptor(contract, raw)
    return descriptor, registry, endpoints


# --- the op-table-vs-grammar check --------------------------------------------


def test_the_table_covers_the_admitted_grammar_and_opens(
    tmp_path: Path,
) -> None:
    """The healthy grant: the table covers the grammar's every op, the
    driver factory is called ONCE with the commissioned identity (the
    device opens at grant construction), and one transaction dispatches."""
    runtime_mod = _runtime_module()
    transport_mod = _transport_module()
    contract = _ftdi_contract()
    descriptor, registry, endpoints = _grant_inputs(tmp_path, contract)
    driver = ScriptedDriver()
    opens: list[Any] = []

    def open_with(identity: Any) -> Any:
        opens.append(identity)
        return driver

    factory = runtime_mod.make_ftdi_runtime_factory(driver_factory=open_with)
    transport = transport_mod.provider_transport_for(
        descriptor, registry, endpoints=endpoints, runtime_factory=factory
    )
    assert not isinstance(transport, transport_mod._TransportRefusal)
    assert len(opens) == 1
    identity = opens[0]
    assert (identity.vendor_id, identity.product_id, identity.serial) == (
        1027,
        24593,
        "FT-DEMO-0042",
    )
    assert identity.interface == 1
    transport.attach_runtime_evidence(_noop_evidence)
    _drive(
        transport.transfer({"kind": "ftdi_control", "op": "reset_device"}, _Context())
    )
    assert driver.ops() == [("reset_device", ())]


def test_an_eighth_op_refuses_the_grant_before_the_device_opens(
    tmp_path: Path,
) -> None:
    """B4: a contract whose grammar carries an eighth op refuses
    ``provider_runtime_op_unsupported:`` at grant construction — the double
    records ZERO calls (the device never opened)."""
    runtime_mod = _runtime_module()
    transport_mod = _transport_module()
    contract = _ftdi_contract(
        extra_op={
            "properties": {"op": {"const": "op_eight"}},
            "required": ["op"],
            "additionalProperties": False,
        }
    )
    descriptor, registry, endpoints = _grant_inputs(tmp_path, contract)
    driver = ScriptedDriver()
    factory = runtime_mod.make_ftdi_runtime_factory(driver_factory=lambda identity: driver)
    with pytest.raises(ValueError, match="provider_runtime_op_unsupported:") as refused:
        transport_mod.provider_transport_for(
            descriptor, registry, endpoints=endpoints, runtime_factory=factory
        )
    assert "op_eight" in str(refused.value)
    assert driver.calls == []  # the device never opened


def test_an_endpointless_key_refuses_the_grant(tmp_path: Path) -> None:
    """B3 leg 2: one key with no commissioned identity refuses
    ``provider_grant_endpoint_absent:`` at the grant."""
    runtime_mod = _runtime_module()
    transport_mod = _transport_module()
    contract = _ftdi_contract()
    package, registry, endpoints = _admitted_package(tmp_path, contract)
    # a second bound key with NO endpoint in the connections document
    settings = json.loads((package / "transport-settings.json").read_text())
    settings["connections"].append(
        {"connection_key": "spare_key", "provider_id": contract["id"]}
    )
    (package / "transport-settings.json").write_text(json.dumps(settings, indent=2))
    registry = load_transport_settings(package / "transport-settings.json")
    raw = (package / "ftdi-control.json").read_bytes()
    descriptor = _provider_descriptor(contract, raw, key="spare_key")
    driver = ScriptedDriver()
    factory = runtime_mod.make_ftdi_runtime_factory(driver_factory=lambda identity: driver)
    with pytest.raises(ValueError, match="provider_grant_endpoint_absent:"):
        transport_mod.provider_transport_for(
            descriptor, registry, endpoints=endpoints, runtime_factory=factory
        )
    assert driver.calls == []


def test_no_runtime_factory_is_todays_posture_notImplementedError(
    tmp_path: Path,
) -> None:
    """B0's unit shape: with the runtime injection reverted, the grant
    constructs the guard with NO runtime and the first transfer raises
    ``NotImplementedError`` naming the implementation lane."""
    transport_mod = _transport_module()
    contract = _ftdi_contract()
    descriptor, registry, endpoints = _grant_inputs(tmp_path, contract)
    transport = transport_mod.provider_transport_for(
        descriptor, registry, endpoints=endpoints, runtime_factory=None
    )
    assert not isinstance(transport, transport_mod._TransportRefusal)

    async def drive() -> None:
        await transport.transfer(
            {"kind": "ftdi_control", "op": "reset_device"}, _Context()
        )

    with pytest.raises(NotImplementedError, match="no provider runtime"):
        asyncio.run(drive())


# --- the runtime ladder over the double ---------------------------------------


async def _noop_evidence(entry: dict[str, Any], context: Any) -> None:
    """The default evidence double: production always binds the bundle's
    writer, so the healthy-path tests bind one too."""


def _granted_runtime(
    tmp_path: Path,
    driver: ScriptedDriver,
    *,
    evidence: Any = None,
    contract: dict[str, Any] | None = None,
) -> Any:
    runtime_mod = _runtime_module()
    transport_mod = _transport_module()
    contract = contract if contract is not None else _ftdi_contract()
    descriptor, registry, endpoints = _grant_inputs(tmp_path, contract)
    factory = runtime_mod.make_ftdi_runtime_factory(driver_factory=lambda identity: driver)
    transport = transport_mod.provider_transport_for(
        descriptor, registry, endpoints=endpoints, runtime_factory=factory
    )
    transport.attach_runtime_evidence(evidence if evidence is not None else _noop_evidence)
    return transport


def _drive(coro: Any) -> Any:
    return asyncio.run(coro)


def test_the_recorded_conversation_replays_over_the_double(
    tmp_path: Path,
) -> None:
    """The journal's provider rows, driven as transactions, produce the
    driver op-call sequence exactly (op, params, order) — the parity the
    Metric-A run measures end to end, pinned here at the runtime boundary."""
    transport = _granted_runtime(tmp_path, ScriptedDriver(answers={"read_pins": 0x5A}))
    for row in _journal_provider_rows():
        _drive(transport.transfer(dict(row["transaction"]), _Context()))
    driver = transport._runtime._driver
    expected = [
        ("reset_device", ()),
        ("set_timeouts", (50, 500)),
        ("set_baud", (115200,)),
        ("set_bitmode", (255, 64)),
        ("read_pins", ()),
    ]
    assert driver.ops() == expected


def test_read_pins_answers_the_document_form(tmp_path: Path) -> None:
    transport = _granted_runtime(tmp_path, ScriptedDriver(answers={"read_pins": 0x5A}))
    result = _drive(
        transport.transfer({"kind": "ftdi_control", "op": "read_pins"}, _Context())
    )
    # the guard validated the document form (base64 text) on the way out
    assert result == {"data": base64.b64encode(bytes([0x5A])).decode("ascii")}


def test_energising_ops_land_intent_rows_before_the_driver_call(
    tmp_path: Path,
) -> None:
    """C4's healthy half + the ordering pin: ``set_bitmode``/``reset_device``
    land the evidence row BEFORE the driver call — the row carries the
    transaction, the operation id and a monotonic stamp."""
    rows: list[dict[str, Any]] = []
    order: list[str] = []

    async def evidence(entry: dict[str, Any], context: Any) -> None:
        rows.append(entry)
        order.append("evidence")

    class _OrderingDriver(ScriptedDriver):
        def set_bitmode(self, mask: int, mode: int) -> None:
            order.append("driver")
            super().set_bitmode(mask, mode)

    driver = _OrderingDriver()
    transport = _granted_runtime(tmp_path, driver, evidence=evidence)
    _drive(
        transport.transfer(
            {"kind": "ftdi_control", "op": "set_bitmode", "mask": 255, "mode": 64},
            _Context(operation_id="step-7"),
        )
    )
    assert order == ["evidence", "driver"]
    assert len(rows) == 1
    assert rows[0]["operation_id"] == "step-7"
    assert rows[0]["transaction"]["op"] == "set_bitmode"
    assert rows[0]["transaction"]["mask"] == 255
    assert rows[0]["transaction"]["mode"] == 64
    assert "monotonic" in rows[0]


def test_non_energising_ops_land_no_intent_rows(tmp_path: Path) -> None:
    """The classification is a constant: ``set_baud`` (interface
    configuration) records nothing — the dispatch is the audited intent."""

    async def evidence(entry: dict[str, Any], context: Any) -> None:
        raise AssertionError("no energising op ran; no row may land")

    transport = _granted_runtime(tmp_path, ScriptedDriver(), evidence=evidence)
    _drive(
        transport.transfer({"kind": "ftdi_control", "op": "set_baud", "baud": 9600}, _Context())
    )


def test_an_evidence_failure_refuses_the_energising_op(
    tmp_path: Path,
) -> None:
    """C4: a store-failure double → ZERO driver calls and the typed
    ``provider_runtime_audit_refused:`` refusal (intent that cannot be
    recorded is not actuated)."""

    async def failing_evidence(entry: dict[str, Any], context: Any) -> None:
        raise RuntimeError("quota exhausted (planted store failure)")

    driver = ScriptedDriver()
    transport = _granted_runtime(tmp_path, driver, evidence=failing_evidence)
    with pytest.raises(ValueError, match="provider_runtime_audit_refused:"):
        _drive(
            transport.transfer(
                {"kind": "ftdi_control", "op": "set_bitmode", "mask": 255, "mode": 64},
                _Context(),
            )
        )
    assert driver.ops() == []


def test_the_protective_carveout_dispatches_anyway(
    tmp_path: Path,
) -> None:
    """C5: the SAME store failure under a ``protect:`` operation dispatches
    the safe action (the driver call happens) and the disclosure lands at
    close — evidence storage is never a dependency of protection."""

    async def failing_evidence(entry: dict[str, Any], context: Any) -> None:
        raise RuntimeError("quota exhausted (planted store failure)")

    driver = ScriptedDriver()
    transport = _granted_runtime(tmp_path, driver, evidence=failing_evidence)
    _drive(
        transport.transfer(
            {"kind": "ftdi_control", "op": "reset_device"},
            _Context(operation_id="protect:safe-reset"),
        )
    )
    assert driver.ops() == [("reset_device", ())]  # the safe action dispatched

    disclosures: list[dict[str, Any]] = []

    async def close_evidence(entry: dict[str, Any], context: Any) -> None:
        disclosures.append(entry)

    transport.attach_runtime_evidence(close_evidence)
    _drive(transport.close_transport(_Context()))
    assert len(disclosures) == 1
    assert disclosures[0]["kind"] == "provider_intent_disclosure"


def test_a_driver_fault_maps_to_ConnectionError_and_poisons(
    tmp_path: Path,
) -> None:
    """B5's unit shape: the faulting call maps to ``ConnectionError`` naming
    the exception class, the runtime stays faulted, and exactly ONE call
    was made (no retry)."""
    driver = ScriptedDriver(fault_on="read_pins")
    transport = _granted_runtime(tmp_path, driver)
    with pytest.raises(ConnectionError, match="OSError"):
        _drive(transport.transfer({"kind": "ftdi_control", "op": "read_pins"}, _Context()))
    assert driver.ops() == [("read_pins", ())]  # one bounded attempt
    with pytest.raises(ConnectionError):
        _drive(transport.transfer({"kind": "ftdi_control", "op": "read_pins"}, _Context()))
    assert len(driver.ops()) == 1  # a faulted runtime stays faulted


def test_the_reserved_unserved_kinds_refuse_typed(tmp_path: Path) -> None:
    """can/i2c/spi are reserved but unserved: ``provider_runtime_kind_
    unsupported:`` — they carry gateway-authorisation semantics the corpus
    has not designed and this runtime does not serve."""
    transport = _granted_runtime(tmp_path, ScriptedDriver())
    for kind in ("can_receive", "can_send", "i2c_transfer", "spi_transfer"):
        with pytest.raises(ValueError, match="provider_runtime_kind_unsupported:"):
            _drive(transport.transfer({"kind": kind}, _Context()))


# --- the section 8.1 stream trio ----------------------------------------------


def test_stream_send_rides_the_data_pipe(tmp_path: Path) -> None:
    driver = ScriptedDriver()
    transport = _granted_runtime(tmp_path, driver)
    result = _drive(
        transport.transfer(
            {"kind": "stream_send", "data": bytes.fromhex("2a420a")}, _Context()
        )
    )
    assert result == {}
    assert driver.ops() == [("write_data", (bytes.fromhex("2a420a"),))]


def test_stream_receive_exact_bytes_and_terminator(tmp_path: Path) -> None:
    driver = ScriptedDriver(inbound=[b"OK=42\n", b"TAIL"])
    transport = _granted_runtime(tmp_path, driver)
    result = _drive(
        transport.transfer(
            {
                "kind": "stream_receive",
                "max_bytes": 64,
                "termination": "lf",
                "exact_bytes": None,
            },
            _Context(),
        )
    )
    assert result == {"data": b"OK=42\n"}  # terminator included


def test_stream_receive_exact_bytes_takes_precedence(tmp_path: Path) -> None:
    driver = ScriptedDriver(inbound=[b"ABCDEFGH\n"])
    transport = _granted_runtime(tmp_path, driver)
    result = _drive(
        transport.transfer(
            {
                "kind": "stream_receive",
                "max_bytes": 64,
                "termination": "lf",
                "exact_bytes": 4,
            },
            _Context(),
        )
    )
    assert result == {"data": b"ABCD"}  # exact_bytes wins over the terminator


def test_stream_exchange_writes_then_receives(tmp_path: Path) -> None:
    driver = ScriptedDriver(inbound=[b"42\n"])
    transport = _granted_runtime(tmp_path, driver)
    result = _drive(
        transport.transfer(
            {
                "kind": "stream_exchange",
                "data": b"READ?\n",
                "max_bytes": 16,
                "termination": "lf",
                "exact_bytes": None,
            },
            _Context(),
        )
    )
    assert result == {"data": b"42\n"}
    assert driver.ops() == [
        ("write_data", (b"READ?\n",)),
        ("read_data", (16,)),
    ]


def test_an_incomplete_frame_never_returns_as_complete(tmp_path: Path) -> None:
    import time

    driver = ScriptedDriver(inbound=[b"PAR"])  # no terminator, pipe empty after
    transport = _granted_runtime(tmp_path, driver)

    class _ExpiringServices:
        def monotonic(self) -> float:
            return time.monotonic()

    context = _Context()
    context.services = _ExpiringServices()
    context.deadline_monotonic = time.monotonic() + 0.2  # the paced loop expires
    with pytest.raises(TimeoutError):
        _drive(
            transport.transfer(
                {
                    "kind": "stream_receive",
                    "max_bytes": 64,
                    "termination": "lf",
                    "exact_bytes": None,
                },
                context,
            )
        )


def test_stream_field_sets_are_strict(tmp_path: Path) -> None:
    """§8.1's own rule: transaction objects reject unspecified fields."""
    transport = _granted_runtime(tmp_path, ScriptedDriver())
    bad_transactions = [
        {"kind": "stream_send"},  # missing data
        {"kind": "stream_send", "data": b"x", "max_bytes": 4},  # send carries no receive fields
        {"kind": "stream_receive", "max_bytes": 4, "termination": "lf"},  # exact_bytes missing
        {"kind": "stream_receive", "max_bytes": 4, "termination": "eom", "exact_bytes": None},
        {"kind": "stream_receive", "max_bytes": 0, "termination": "lf", "exact_bytes": None},
        {"kind": "stream_receive", "max_bytes": 4, "termination": "lf", "exact_bytes": 5},
    ]
    for transaction in bad_transactions:
        with pytest.raises(ValueError):
            _drive(transport.transfer(transaction, _Context()))


# --- the backend probe ---------------------------------------------------------


def test_a_missing_backend_refuses_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_mod = _runtime_module()
    monkeypatch.setattr(
        runtime_mod, "_require_backend", lambda: (_ for _ in ()).throw(
            ValueError(
                "provider_runtime_backend_missing: install 'benchweave[provider]' "
                "for FTDI provider transport support (pyftdi rides the provider extra)"
            )
        )
    )
    with pytest.raises(ValueError, match="provider_runtime_backend_missing:"):
        runtime_mod.require_backend()


def test_the_connections_load_probes_the_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Maintainer ruling 1: a provider-descriptor lattice on an extra-less
    install refuses at the connections load — loud and early, never at
    first transfer. The probe seam is patched (the arm proves the refusal
    mapping, never the install state)."""
    contract = _ftdi_contract()
    package, _registry, _endpoints = _admitted_package(tmp_path, contract)
    import benchweave.control.provider_settings as settings_module

    def refuse() -> Any:
        raise ValueError(
            "provider_runtime_backend_missing: install 'benchweave[provider]' "
            "for FTDI provider transport support (pyftdi rides the provider extra)"
        )

    monkeypatch.setattr(settings_module, "_provider_backend_probe", refuse)
    registry = settings_module.load_transport_settings(
        package / "transport-settings.json"
    )
    with pytest.raises(ValueError, match="provider_runtime_backend_missing:"):
        settings_module.load_provider_connections(
            package / "provider-connections.json", registry
        )


# --- the spelling pins (C2's family, runtime side) ----------------------------


def test_the_refusal_prefixes_are_the_designed_family() -> None:
    """C2: the refusal-prefix family is machine-matchable — the module
    names its prefixes as constants and the emitters use them."""
    runtime_mod = _runtime_module()
    expected_prefixes = frozenset(
        {
            "provider_runtime_backend_missing:",
            "provider_runtime_device_unavailable:",
            "provider_runtime_op_unsupported:",
            "provider_runtime_kind_unsupported:",
            "provider_runtime_audit_refused:",
        }
    )
    assert expected_prefixes == runtime_mod.REFUSAL_PREFIXES


def test_the_energising_classification_is_the_constant_pair() -> None:
    runtime_mod = _runtime_module()
    assert frozenset({"set_bitmode", "reset_device"}) == runtime_mod.ENERGISING_OPS


def test_the_stream_trio_field_sets_match_the_corpus_table() -> None:
    """Obligation 17's family: the §8.1 stream-trio field sets are
    hand-carried (the vendored runtime schema does not enumerate kinds) —
    pinned here against the corpus §8.1 table's own rows."""
    runtime_mod = _runtime_module()
    receive = {"max_bytes", "termination", "exact_bytes"}
    assert {
        "stream_send": frozenset({"kind", "data"}),
        "stream_receive": frozenset({"kind", *receive}),
        "stream_exchange": frozenset({"kind", "data", *receive}),
    } == runtime_mod.STREAM_FIELDS
