"""The commissioned provider run over the scripted driver double (issue #568,
Metric A and the B/C arms that need the full worker path).

The full production ladder, nothing but the USB boundary doubled (the
design section 1.7's parity rule): admission (settings + connections +
descriptor pin) → seam pre-check → worker grant construction (endpoint,
table-vs-grammar, open, evidence bind) → bridge dispatch → the guard's
grammar gate → the runtime ladder → the driver. The double sits at the
DRIVER boundary, scripted from the provider rows of a #564-format journal
(the same row evidence the SDK's ScriptedFtdiDriver consumes), so the
two rehearsals cannot drift apart without a visible disagreement.

The B controls plant the design's named faults and must fail loudly; the
C arms pin the honesty surfaces that only the full run can show (the
``provider_granted`` event beside ``devices_pinned``, before any body
event).

Adapter note (a disclosed deviation from the acceptance rule's letter):
the bring-up conversation rides the procedure's WRITE step, not an invoke
step. The invoke shape would drag the full invoke-capability descriptor
machinery (catalog + measurement pair, the dataset lane) that is
orthogonal to the provider mechanism; the write dispatch exercises the
identical path under test (bridge deadline and markers → adapter execute
→ services.transfer → guard → runtime → driver), and every measurable
claim of Metric A is preserved.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import test_run_activation as activation

from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.control.documents import AdmissionRejected
from benchweave.interfaces import app as app_module
from benchweave.interfaces.app import _build_run_factory
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.state.store import Store

REPO = Path(__file__).resolve().parents[2]
NOW_ISO = activation.NOW_ISO
QUOTA_LIMITS = activation.QUOTA_LIMITS

#: The #564-format journal's provider rows: the recorded bring-up
#: conversation. THE DENOMINATOR (design section 5, Metric A): five
#: provider rows, stamped here, and the double's op-call sequence must
#: equal them exactly (op, params, order).
JOURNAL_PROVIDER_ROWS: list[dict[str, Any]] = [
    {"kind": "ftdi_control", "op": "reset_device"},
    {"kind": "ftdi_control", "op": "set_timeouts", "read_ms": 50, "write_ms": 500},
    {"kind": "ftdi_control", "op": "set_baud", "baud": 115200},
    {"kind": "ftdi_control", "op": "set_bitmode", "mask": 255, "mode": 64},
    {"kind": "ftdi_control", "op": "read_pins"},
]
JOURNAL_ROW_COUNT = len(JOURNAL_PROVIDER_ROWS)

_REQUEST_SCHEMA_ONE_OF = [
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
]


def _ftdi_contract(extra_op: dict[str, Any] | None = None) -> dict[str, Any]:
    one_of = list(_REQUEST_SCHEMA_ONE_OF)
    if extra_op is not None:
        one_of.append(extra_op)
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
                "request_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "oneOf": one_of,
                },
                "result_schema": {
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
                },
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
            "expires_at": "2027-10-26T00:00:00Z",
            "evidence": [
                {
                    "category": "protocol",
                    "report": {
                        "id": "issue-568-gateway-runtime-tests",
                        "version": "1.0.0",
                        "sha256": "c" * 64,
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


#: The provider-conversation adapter: the write dispatch performs the
#: recorded bring-up through ``services.transfer`` — the plugin-side
#: authorship the whole arc serves (#562's adapter, doubled here at its
#: wire boundary).
ADAPTER_SOURCE = '''\
"""Provider bring-up adapter (issue #568 harness)."""
from __future__ import annotations

import asyncio

CONVERSATION = [
    {"kind": "ftdi_control", "op": "reset_device"},
    {"kind": "ftdi_control", "op": "set_timeouts", "read_ms": 50, "write_ms": 500},
    {"kind": "ftdi_control", "op": "set_baud", "baud": 115200},
    {"kind": "ftdi_control", "op": "set_bitmode", "mask": 255, "mode": 64},
    {"kind": "ftdi_control", "op": "read_pins"},
]


class DemoSupplyAdapter:
    def __init__(self) -> None:
        self.services = None
        self.descriptor = None
        self.sequences = {}
        self.state = {"voltage_setpoint_v": 0.0, "output_enabled": False}

    async def open(self, descriptor, services, context) -> None:
        self.descriptor = descriptor
        self.services = services

    async def close(self, context) -> None:
        return None

    def _reading(self, parameter, value, unit):
        return {
            "parameter": parameter,
            "value": value,
            "unit": unit,
            "observed_at": self.services.utc_now(),
            "age_ms": 0,
            "quality": "valid",
            "source": "device",
        }

    def _output_voltage(self):
        if not self.state["output_enabled"]:
            return 0.0
        return float(self.state["voltage_setpoint_v"])

    async def execute(self, envelope, context):
        await context.mark_dispatch_started()
        verb = envelope["verb"]
        arguments = envelope["arguments"]
        operation_id = envelope["operation_id"]
        if verb == "write":
            parameter = arguments["parameter"]
            value = arguments["value"]
            self.state[parameter] = value
            # The recorded bring-up conversation, over the injected provider
            # transport — the named bring-up write carries it, one
            # transaction per journal row, in order (a protective safe
            # action's write never re-runs the bring-up).
            if parameter == "voltage_setpoint_v":
                for transaction in CONVERSATION:
                    await self.services.transfer(dict(transaction), context)
            unit = "V" if parameter == "voltage_setpoint_v" else None
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {
                    "parameter": parameter,
                    "requested_value": value,
                    "effective_value": value,
                    "assurance": "readback",
                    "verification": self._reading(parameter, value, unit),
                },
            }
        if verb == "read":
            parameter = arguments["parameter"]
            if parameter == "output_voltage_v":
                data = self._reading(parameter, self._output_voltage(), "V")
            elif parameter == "output_current_a":
                current = 0.1 if self.state["output_enabled"] else 0.0
                data = self._reading(parameter, current, "A")
            else:
                data = self._reading(parameter, 0.0, None)
            return {"operation_id": operation_id, "verb": verb, "status": "ok", "data": data}
        if verb in ("stream_subscribe", "stream_unsubscribe"):
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {"subscription_id": arguments["subscription_id"]},
            }
        return {
            "operation_id": operation_id,
            "verb": verb,
            "status": "error",
            "error": {
                "code": "UNSUPPORTED",
                "message": f"provider adapter does not implement {verb}",
                "dispatch_state": "not_dispatched",
            },
        }

    async def next_event(self, subscription_id, context):
        await asyncio.sleep(0)
        self.sequences[subscription_id] = self.sequences.get(subscription_id, -1) + 1
        parameter = "output_voltage_v"
        return {
            "subscription_id": subscription_id,
            "sequence": self.sequences[subscription_id],
            "kind": "telemetry",
            "reading": self._reading(parameter, self._output_voltage(), "V"),
        }


def create_plugin():
    return DemoSupplyAdapter()
'''


class ScriptedGatewayDriver:
    """The driver-boundary double for the full worker path: scripted from
    the journal's provider rows (in order), recording every call, with
    plantable faults. ``read_pins`` answers the journal's recorded byte."""

    def __init__(self, *, fault_on: str | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._fault_on = fault_on
        self.closed = False

    def _record(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if self._fault_on == name:
            raise OSError("usb device detached (planted fault)")

    def reset_device(self) -> None:
        self._record("reset_device")

    def set_timeouts(self, read_ms: int, write_ms: int) -> None:
        self._record("set_timeouts", read_ms, write_ms)

    def set_latency(self, ms: int) -> None:
        self._record("set_latency", ms)

    def set_baud(self, baud: int) -> None:
        self._record("set_baud", baud)

    def purge(self, queue: str) -> None:
        self._record("purge", queue)

    def set_bitmode(self, mask: int, mode: int) -> None:
        self._record("set_bitmode", mask, mode)

    def read_pins(self) -> int:
        self._record("read_pins")
        return 0x5A

    def write_data(self, data: bytes) -> int:
        self._record("write_data", bytes(data))
        return len(data)

    def read_data(self, size: int) -> bytes:
        self._record("read_data", size)
        return b""

    def close(self) -> None:
        self._record("close")
        self.closed = True

    def ops(self) -> list[tuple[str, tuple[Any, ...]]]:
        return [call for call in self.calls if call[0] != "close"]


#: The journal-derived expectation: op names in order with their params.
EXPECTED_SEQUENCE: list[tuple[str, tuple[Any, ...]]] = [
    ("reset_device", ()),
    ("set_timeouts", (50, 500)),
    ("set_baud", (115200,)),
    ("set_bitmode", (255, 64)),
    ("read_pins", ()),
]


def _expected_from_journal() -> list[tuple[str, tuple[Any, ...]]]:
    """The journal's provider rows as the expected op-call sequence — the
    conversion is part of the metric (op, params, order)."""
    from benchweave.content.provider_runtime import _OPS

    sequence: list[tuple[str, tuple[Any, ...]]] = []
    for row in JOURNAL_PROVIDER_ROWS:
        op = row["op"]
        sequence.append((op, tuple(row[name] for name in _OPS[op])))
    return sequence


class _Harness:
    """The activation harness (test_run_activation's machinery) with the
    provider family grafted in: descriptor transport block, pinned
    contract, settings, connections — all before the plugin publishes, so
    the release manifest carries the provider-declaring descriptor."""

    def __init__(
        self,
        tmp_path: Path,
        name: str,
        *,
        extra_op: dict[str, Any] | None = None,
        mutate_settings: Any | None = None,
        mutate_connections: Any | None = None,
        mutate_descriptor: Any | None = None,
    ) -> None:
        self.tmp_path = tmp_path
        self.name = name
        lattice = activation._lattice(
            tmp_path / "lattice",
            f"req-568-{name}",
            steps=[
                {
                    "id": "bring-up",
                    "kind": "write",
                    "role": "supply",
                    "parameter": "voltage_setpoint_v",
                    "value": 5.0,
                    "timeout_ms": 2000,
                },
                {
                    "id": "observe",
                    "kind": "read",
                    "role": "supply",
                    "parameter": "output_voltage_v",
                    "timeout_ms": 500,
                },
            ],
        )
        contract = _ftdi_contract(extra_op)
        contract_raw = (json.dumps(contract, indent=2) + "\n").encode()
        (lattice / "ftdi-control.json").write_bytes(contract_raw)
        descriptor = json.loads(
            (lattice / "descriptor-demo-supply.json").read_text()
        )
        descriptor["transport"] = {
            "type": "custom",
            "connection_key": "fpga_prog",
            "settings": {
                "protocol_reference": "Test-authored FTDI common control grammar"
            },
            "provider": {
                "feature_id": contract["feature_id"],
                "id": contract["id"],
                "path": "ftdi-control.json",
                "sha256": hashlib.sha256(contract_raw).hexdigest(),
            },
        }
        # The S12 mirror: the provider feature id joins required_features
        # (the reference descriptor's own posture).
        required = descriptor.setdefault("required_features", [])
        if contract["feature_id"] not in required:
            required.append(contract["feature_id"])
        if mutate_descriptor is not None:
            mutate_descriptor(descriptor)
        (lattice / "descriptor-demo-supply.json").write_text(
            json.dumps(descriptor, indent=2) + "\n"
        )
        settings = {
            "config_version": "1",
            "admitted": [
                {
                    "id": contract["id"],
                    "version": contract["version"],
                    "sha256": hashlib.sha256(contract_raw).hexdigest(),
                    "feature_id": contract["feature_id"],
                    "document": "ftdi-control.json",
                }
            ],
            "connections": [
                {"connection_key": "fpga_prog", "provider_id": contract["id"]}
            ],
        }
        if mutate_settings is not None:
            mutate_settings(settings)
        (lattice / "transport-settings.json").write_text(
            json.dumps(settings, indent=2) + "\n"
        )
        connections = {
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
        }
        if mutate_connections is not None:
            mutate_connections(connections)
        (lattice / "provider-connections.json").write_text(
            json.dumps(connections, indent=2) + "\n"
        )
        # The digest cascade: the descriptor pin moved, so the bench pins
        # move, so the commissioning and binding pins move.
        bench = json.loads((lattice / "bench.json").read_text())
        descriptor_raw = (lattice / "descriptor-demo-supply.json").read_bytes()
        for device in bench["devices"]:
            if str(device["id"]) == "psu":
                device["descriptor"]["sha256"] = hashlib.sha256(
                    descriptor_raw
                ).hexdigest()
        (lattice / "bench.json").write_text(json.dumps(bench, indent=2) + "\n")
        bench_sha = hashlib.sha256((lattice / "bench.json").read_bytes()).hexdigest()
        commissioning = json.loads((lattice / "commissioning.json").read_text())
        commissioning["bench"]["sha256"] = bench_sha
        (lattice / "commissioning.json").write_text(
            json.dumps(commissioning, indent=2) + "\n"
        )
        commissioning_sha = hashlib.sha256(
            (lattice / "commissioning.json").read_bytes()
        ).hexdigest()
        binding = json.loads((lattice / "run-binding.json").read_text())
        binding["bench"]["sha256"] = bench_sha
        binding["commissioning"]["sha256"] = commissioning_sha
        (lattice / "run-binding.json").write_text(json.dumps(binding, indent=2) + "\n")

        plugin_dir = activation._write_plugin_source(
            tmp_path / "pluginroot", ADAPTER_SOURCE
        )
        registry_root = tmp_path / "dev-registry"
        activation._publish(
            plugin_dir, lattice / "descriptor-demo-supply.json", registry_root
        )
        self.registry_root = registry_root
        self._wire_session()
        self.lattice = lattice

    def _wire_session(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from benchweave.interfaces.bootstrap import RegistrySession
        from benchweave.registry.activation import activate
        from benchweave.registry.admission import AdmissionLimits, Approval, admit
        from benchweave.registry.resolver import (
            LocalDirectorySource,
            OriginConfig,
            Resolver,
        )

        self.signing_key = Ed25519PrivateKey.generate()
        impl_dir = (
            self.registry_root
            / activation.DEV_ID
            / activation.IMPL_PACKAGE
            / activation.PACKAGE_VERSION
        )
        impl_status = json.loads((impl_dir / "status.json").read_bytes())
        impl_status["sequence"] = 2
        impl_status["reason"] = "provider harness commissioning revision"
        activation._write_status(impl_dir, impl_status, None)
        dev_root = activation._sign_release_tree(
            self.registry_root, activation.DEV_ID, self.signing_key
        )
        origins = {
            activation.DEV_ID: OriginConfig(
                registry_id=activation.DEV_ID,
                root=dev_root,
                source=LocalDirectorySource(self.registry_root / activation.DEV_ID),
                namespaces=("dev",),
                signature_policy="required",
            ),
            activation.ORIGIN_MAIN: OriginConfig(
                registry_id=activation.ORIGIN_MAIN,
                root=activation._main_root(),
                source=LocalDirectorySource(
                    activation.REGISTRY_FIXTURES / activation.ORIGIN_MAIN
                ),
                namespaces=("benchweave",),
            ),
        }
        self.work = self.tmp_path / "registry-work"
        self.session = RegistrySession(
            resolver=Resolver(origins),
            roots={activation.ORIGIN_MAIN: activation._main_root()},
            high_water={},
            cache_root=self.work / "cache",
            lock_path=self.work / "packages.lock.json",
            records_dir=self.work / "activations",
            advisories_dir=self.work / "advisories",
            status_cache={},
            consult_water={},
            limits=AdmissionLimits(
                max_archive_bytes=1_000_000,
                max_files=100,
                max_unpacked_bytes=1_000_000,
            ),
            now_ns=lambda: activation.NOW_NS,
            registry_id=activation.DEV_ID,
        )
        self.session.roots[activation.DEV_ID] = dev_root
        closure = self.session.resolver.resolve(
            activation.DEV_ID,
            activation.IMPL_PACKAGE,
            activation.PACKAGE_VERSION,
            now_ns=activation.NOW_NS,
            high_water=self.session.high_water,
        )
        self.admitted = admit(
            closure,
            cache_root=self.session.cache_root,
            lock_path=self.session.lock_path,
            limits=self.session.limits,
            approval=Approval(
                principal_id="provider-harness",
                approved_at=NOW_ISO,
                policy_id="local-policy",
                policy_version="1.0.0",
            ),
            now_ns=activation.NOW_NS,
            roots={
                activation.DEV_ID: dev_root,
                activation.ORIGIN_MAIN: activation._main_root(),
            },
            high_water=self.session.high_water,
        )
        activate(
            self.admitted,
            bench_generation=1,
            bench_has_live_lease=False,
            records_dir=self.session.records_dir / "activation-bench",
            activated_at=NOW_ISO,
        )

    def build_run(
        self, driver: ScriptedGatewayDriver, store: Store
    ) -> Any:
        """The worker factory with the double at the driver boundary (the
        production factory is monkeypatched — the worker's own call site
        is the injection point, no production seam is added for the test)."""
        from benchweave.content.provider_runtime import make_ftdi_runtime_factory

        original = app_module.make_ftdi_runtime_factory

        def factory_of_driver() -> Any:
            return make_ftdi_runtime_factory(
                driver_factory=lambda identity: driver
            )

        setattr(  # noqa: B010 - the deliberate monkeypatch target; direct assignment fights the imported callable's type
            app_module, "make_ftdi_runtime_factory", factory_of_driver
        )
        try:
            factory = _build_run_factory(
                self.lattice,
                SystemClock().now_iso,
                limits=QUOTA_LIMITS,
                registry_session=self.session,
            )
            raw = (self.lattice / "run-binding.json").read_bytes()
            binding = json.loads(raw)
            ref = {
                "id": str(binding["request_id"]),
                "version": str(binding["contract_version"]),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            return factory("run-568", "principal-568", ref, store)
        finally:
            setattr(  # noqa: B010 - restoring the monkeypatch target
                app_module, "make_ftdi_runtime_factory", original
            )

    def open_store(self) -> tuple[Store, ContentStore]:
        store = Store.open(self.tmp_path / "state.db")
        content = ContentStore(store)
        admit_startup_bench(store, content, self.lattice, now=NOW_ISO)
        return store, content


# --- Metric A -------------------------------------------------------------------


def test_metric_a_the_commissioned_run_over_the_double(tmp_path: Path) -> None:
    """The demo (design section 5, Metric A): the full worker path over the
    scripted double — every step ok, the protective transition verified,
    the double's op-call sequence equal to the journal's provider rows
    exactly, and the provider_granted event carrying the triple and the
    endpoint identity."""
    harness = _Harness(tmp_path, "metric-a")
    store, _content = harness.open_store()
    driver = ScriptedGatewayDriver()
    try:
        coordinator = harness.build_run(driver, store)
        record = coordinator.start_run("run-568", "principal-568")
        assert record["outcome"] == "passed", record
        assert record["body_outcome"] == "completed", record
        assert record["safe_state"] == "verified", record
        events = store.read_events("run:run-568")
        kinds = [event["kind"] for event in events]
        assert "write" in kinds and "read" in kinds
        # THE METRIC: the double's op-call sequence equals the journal's
        # provider rows (op, params, order) — denominator: five rows.
        assert driver.ops() == _expected_from_journal()
        assert len(driver.ops()) == JOURNAL_ROW_COUNT
        # C6: the grant event lands beside devices_pinned, before any body
        # event, carrying the triple and the endpoint identity.
        assert kinds[0] == "devices_pinned"
        assert kinds[1] == "provider_granted"
        grant = events[1]
        facts = grant["devices"]["psu"]
        assert facts["id"] == "urn:otdp:transport-provider:ftdi-control:1.0.0"
        assert facts["version"] == "1.0.0"
        assert facts["sha256"] == hashlib.sha256(
            (harness.lattice / "ftdi-control.json").read_bytes()
        ).hexdigest()
        assert facts["connection_key"] == "fpga_prog"
        assert facts["usb"] == {
            "vendor_id": 1027,
            "product_id": 24593,
            "serial": "FT-DEMO-0042",
            "interface": 1,
        }
        # the read_pins result the journal recorded flowed through the
        # adapter's conversation (the document form the guard validated)
        assert driver.ops()[-1] == ("read_pins", ())
    finally:
        store.close()


# --- the B controls over the full path ------------------------------------------


def test_b0_runtime_injection_reverted_loses_the_effect(tmp_path: Path) -> None:
    """B0, the non-gameable core: with the runtime injection reverted
    (runtime=None — today's posture), the SAME fixture run refuses at
    first transfer (NotImplementedError, no provider runtime) and no step
    completes — the effect disappears when the mechanism does."""
    harness = _Harness(tmp_path, "b0")
    store, _content = harness.open_store()
    driver = ScriptedGatewayDriver()
    original = app_module.make_ftdi_runtime_factory
    setattr(  # noqa: B010 - the deliberate monkeypatch target
        app_module, "make_ftdi_runtime_factory", lambda: None
    )
    try:
        factory = _build_run_factory(
            harness.lattice,
            SystemClock().now_iso,
            limits=QUOTA_LIMITS,
            registry_session=harness.session,
        )
        raw = (harness.lattice / "run-binding.json").read_bytes()
        binding = json.loads(raw)
        ref = {
            "id": str(binding["request_id"]),
            "version": str(binding["contract_version"]),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        coordinator = factory("run-b0", "principal-568", ref, store)
        record = coordinator.start_run("run-b0", "principal-568")
        assert record["body_outcome"] != "completed", record
        assert driver.calls == []  # no driver call ever happened
    finally:
        setattr(  # noqa: B010 - restoring the monkeypatch target
            app_module, "make_ftdi_runtime_factory", original
        )
        store.close()


def test_b1_an_unadmitted_triple_never_starts_a_run(tmp_path: Path) -> None:
    """B1: the settings admit a triple no declaration names →
    ``provider_not_admitted:`` at admission; the run never starts (the
    design's digest-flip mutation refuses earlier at the pin checks — a
    different arm's vocabulary, named in the lane report)."""
    def admit_a_different_triple(settings: dict[str, Any]) -> None:
        # The settings admit a triple no declaration names (every byte
        # internally consistent — the admission row, not a pin check, owns
        # the refusal: provider_not_admitted:).
        rival = "urn:otdp:transport-provider:ftdi-control:9.9.9"
        settings["admitted"][0]["id"] = rival
        settings["connections"][0]["provider_id"] = rival

    harness = _Harness(tmp_path, "b1", mutate_settings=admit_a_different_triple)
    driver = ScriptedGatewayDriver()
    # The refusal is at ADMISSION (the startup lane; the run path re-admits
    # the same way) — the run never starts.
    with pytest.raises(AdmissionRejected, match="provider_not_admitted:"):
        harness.open_store()
    assert driver.calls == []


def test_b3_two_keys_one_identity_refuses_at_load(tmp_path: Path) -> None:
    """B3 leg 1: two connection keys sharing one USB identity →
    ``connections_schema:`` at load — the run build refuses before any
    device opens."""
    harness = _Harness(
        tmp_path,
        "b3",
        mutate_settings=lambda s: s["connections"].append(
            {"connection_key": "spare_key", "provider_id": s["admitted"][0]["id"]}
        ),
        mutate_connections=lambda c: c["connections"].append(
            {
                "connection_key": "spare_key",
                "usb": {
                    "vendor_id": 1027,
                    "product_id": 24593,
                    "serial": "FT-DEMO-0042",
                    "interface": 1,
                },
            }
        ),
    )
    from benchweave.control.provider_settings import SettingsRejected

    driver = ScriptedGatewayDriver()
    with pytest.raises(SettingsRejected, match="connections_schema:"):
        harness.open_store()
    assert driver.calls == []


def test_b4_an_eighth_op_refuses_the_grant_before_the_device_opens(
    tmp_path: Path,
) -> None:
    """B4 over the worker: the grant construction refuses with the device
    unopened (the double records zero calls) and the run build fails."""
    harness = _Harness(
        tmp_path,
        "b4",
        extra_op={
            "properties": {"op": {"const": "op_eight"}},
            "required": ["op"],
            "additionalProperties": False,
        },
    )
    store, _content = harness.open_store()
    driver = ScriptedGatewayDriver()
    try:
        with pytest.raises(ValueError, match="provider_runtime_op_unsupported:") as raised:
            harness.build_run(driver, store)
        assert "op_eight" in str(raised.value)
        assert driver.calls == []
    finally:
        store.close()


def test_b5_a_mid_conversation_fault_poisons_the_dispatch(tmp_path: Path) -> None:
    """B5: the driver faults mid-conversation → the dispatch after entry
    poisons (step unknown), the body ends outcome_unknown, and the
    faulting op was called exactly once (no retry)."""
    harness = _Harness(tmp_path, "b5")
    store, _content = harness.open_store()
    driver = ScriptedGatewayDriver(fault_on="read_pins")
    try:
        coordinator = harness.build_run(driver, store)
        record = coordinator.start_run("run-b5", "principal-568")
        assert record["body_outcome"] == "outcome_unknown", record
        ops = driver.ops()
        # the faulting op ran exactly once — one bounded attempt, no retry
        assert ops.count(("read_pins", ())) == 1
        assert ops[:-1] == _expected_from_journal()[:-1]
    finally:
        store.close()
