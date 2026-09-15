"""Mock-only OTDP 0.3.0 / adapter 1.1 conformance."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from benchweave_fnirsi_dps150.adapter import create_plugin
from benchweave_fnirsi_dps150.codec import GET
from benchweave_fnirsi_dps150.descriptor import build_descriptor
from benchweave_fnirsi_dps150.session import BAUD_NEGOTIATE, SESSION_OPEN

# The two fire-and-forget frames the adapter sends at session establishment;
# conformance assertions index or filter past them wherever commanded wire is pinned.
SESSION_FRAMES = (SESSION_OPEN, BAUD_NEGOTIATE)


def commanded_sends(calls: list[tuple[dict[str, Any], Any]]) -> list[bytes]:
    """stream_send transactions excluding the establishment handshake."""
    return [
        t["data"]
        for t, _ in calls
        if t["kind"] == "stream_send" and t["data"] not in SESSION_FRAMES
    ]


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src/benchweave_fnirsi_dps150"
SCHEMAS = ROOT / "contracts/otdp-v0.3.0"
IDENTITY = bytes.fromhex("f0a1de074450532d3135308f f0a1e003312e3072")


class Context:
    def __init__(self, operation_id: str = "host-op", deadline: float = 101.0) -> None:
        self.operation_id = operation_id
        self.dataset_id: str | None = None
        self.deadline_monotonic = deadline
        self.cancelled = False
        self.markers = 0
        self.marker_error: BaseException | None = None

    def is_cancelled(self) -> bool:
        return self.cancelled

    async def mark_dispatch_started(self) -> None:
        self.markers += 1
        if self.marker_error:
            raise self.marker_error


class Host:
    """Wire-scripted host whose GET replies materialise only at send time.

    A commanded GET pops the next scripted reply into the receive buffer, so
    the telemetry drain the adapter runs BEFORE each command finds an empty,
    EOF-terminated stream (no unsolicited telemetry on this mock) and can
    never consume a reply that has not been asked for yet.
    """

    def __init__(self, wire: bytes = b"") -> None:
        self.replies: list[bytes] = []
        self.wire = wire
        self.buffer = bytearray()
        self.now = 100.0
        self.calls: list[tuple[dict[str, Any], Any]] = []
        self.closes = 0
        self.failure: BaseException | None = None
        self.fail_at = 0
        self.advance_at = 0
        self.cancel_at = 0
        self.block_at = 0
        self.timestamp = "2026-09-12T03:00:00Z"
        self.entered = asyncio.Event()

    @property
    def wire(self) -> bytes:
        return self.replies[0] if self.replies else b""

    @wire.setter
    def wire(self, value: bytes) -> None:
        self.replies[:] = [value] if value else []

    def queue_replies(self, *frames: bytes) -> None:
        self.replies.extend(frames)

    def monotonic(self) -> float:
        return self.now

    def utc_now(self) -> str:
        return self.timestamp

    async def transfer(self, transaction: dict[str, Any], context: Any) -> dict[str, Any]:
        # Pure receives need no dispatch marker (spec §8); sends must be marked.
        assert context.operation_id == "host-op" and context.dataset_id is None
        assert context.deadline_monotonic <= 101.0
        self.calls.append((transaction, context))
        count = len(self.calls)
        if count == self.block_at:
            self.entered.set()
            await asyncio.Event().wait()
        if count == self.advance_at:
            self.now = 102.0
        if count == self.cancel_at:
            context.cancelled = True
        if count == self.fail_at and self.failure:
            raise self.failure
        if transaction["kind"] == "stream_send":
            assert context.markers == 1
            assert set(transaction) == {"kind", "data"}
            data = transaction["data"]
            assert type(data) is bytes
            if data[:2] == bytes((0xF1, GET)) and self.replies:
                self.buffer.extend(self.replies.pop(0))
            return {}
        assert transaction["kind"] == "stream_receive"
        assert set(transaction) == {"kind", "max_bytes", "exact_bytes", "termination"}
        assert transaction["termination"] == "lf"
        size = transaction["exact_bytes"]
        assert 1 <= size == transaction["max_bytes"] <= 256
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return {"data": data}

    async def close_transport(self, context: Any) -> None:
        self.closes += 1


def request(verb: str = "identify", **arguments: Any) -> dict[str, Any]:
    return {"operation_id": "host-op", "verb": verb, "arguments": arguments}


def validate_result(result: dict[str, Any]) -> None:
    schema = json.loads((SCHEMAS / "otdp-runtime.schema.json").read_text())
    schema["$ref"] = "#/$defs/operationResult"
    schema.pop("oneOf")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
    assert result["operation_id"] == "host-op"


async def opened(host: Host) -> Any:
    plugin = create_plugin()
    await plugin.open(build_descriptor(), host, Context())
    assert host.calls == []
    return plugin


async def identified(host: Host) -> Any:
    pending = host.replies[:]
    host.replies[:] = [IDENTITY[:12], IDENTITY[12:]]
    plugin = await opened(host)
    result = await plugin.execute(request(), Context())
    validate_result(result)
    assert result["status"] == "ok"
    assert result["data"] == {
        "manufacturer": "FNIRSI",
        "model": "DPS-150",
        "serial": None,
        "firmware": "1.0",
        "source": "device",
    }
    assert [data.hex() for data in commanded_sends(host.calls)] == [
        "f1a1de00de",
        "f1a1e000e0",
    ]
    host.replies[:] = pending
    host.calls.clear()
    return plugin


def test_descriptor_schema_and_package_evidence() -> None:
    descriptor = json.loads((PACKAGE / "descriptor.json").read_text())
    assert descriptor == build_descriptor()
    schema = json.loads((SCHEMAS / "otdp-device-descriptor.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(descriptor)
    assert descriptor["capabilities"] == ["identify", "read"]
    assert set(descriptor["operations"]) == {"identify", "read"}
    assert descriptor["required_features"] == ["otdp.core/0.3.0", "otdp.adapter/1.1"]
    assert not {"profiles", "actions", "contracts", "channels"} & descriptor.keys()
    assert descriptor["integration"]["adapter"]["permissions"] == ["scoped_transport"]
    assert descriptor["integration"]["adapter"]["dependencies"] == []
    names = [p["name"] for p in descriptor["parameters"]]
    assert len(names) == len(set(names)) == 8
    for p in descriptor["parameters"]:
        assert p["access"] == "ro" and "write_policy" not in p
        assert p["read_policy"] == {"max_age_ms": 0, "destructive": False}
        assert p["binding"] == {"kind": "adapter", "key": p["name"]}
    for vector in descriptor["provenance"]["test_vectors"]:
        path = (PACKAGE / vector["path"]).resolve()
        assert path.is_relative_to(PACKAGE) and path.is_file()
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "pyproject.toml").is_file()


def test_identity_and_factory_isolation() -> None:
    async def scenario() -> None:
        first = await identified(Host())
        second = await opened(Host())
        assert first is not second
        denied = await second.execute(request("read", parameter="voltage"), Context())
        assert denied["error"]["code"] == "IDENTITY_MISMATCH"

    asyncio.run(scenario())


def test_scalar_vectors() -> None:
    async def scenario(vector: dict[str, Any]) -> None:
        host = Host(bytes.fromhex(vector["response_hex"]))
        plugin = await identified(host)
        result = await plugin.execute(request("read", parameter=vector["parameter"]), Context())
        validate_result(result)
        assert result == vector["result"]
        # one EOF-ended drain precedes the GET on every commanded call
        assert host.calls[1][0] == {
            "kind": "stream_send",
            "data": bytes.fromhex(vector["request_hex"]),
        }
        assert len(host.calls) == 4
        host.wire = bytes.fromhex(vector["response_hex"])
        result2 = await plugin.execute(request("read", parameter=vector["parameter"]), Context())
        assert result2 == result and len(host.calls) == 8

    for vector in json.loads((PACKAGE / "adapter-vectors.json").read_text()):
        asyncio.run(scenario(vector))


@pytest.mark.parametrize(
    "verb",
    [
        "write",
        "reset",
        "self_test",
        "get_errors",
        "capture",
        "stream_subscribe",
        "stream_unsubscribe",
        "invoke",
    ],
)
def test_unsupported_operations_never_dispatch(verb: str) -> None:
    async def scenario() -> None:
        host = Host()
        plugin = await opened(host)
        result = await plugin.execute(request(verb), Context())
        validate_result(result)
        assert result["verb"] == verb
        assert result["error"]["code"] == "UNSUPPORTED"
        assert result["error"]["dispatch_state"] == "not_dispatched"
        assert host.calls == []
        assert await plugin.next_event("anything", Context()) is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"parameter": 1},
        {"parameter": True},
        {"parameter": []},
        {"parameter": "missing"},
        {"parameter": "voltage", "value": 1},
        {"parameter": "voltage", "max_age_ms": 1000},
    ],
)
def test_invalid_read_arguments(arguments: dict[str, Any]) -> None:
    async def scenario() -> None:
        host = Host()
        plugin = await identified(host)
        result = await plugin.execute(request("read", **arguments), Context())
        validate_result(result)
        assert result["error"]["code"] == "INVALID_ARGUMENT"
        assert result["error"]["dispatch_state"] == "not_dispatched"
        assert host.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field,value",
    [
        ("otdp_version", "0.4.0"),
        ("profiles", ["otdp.dc_psu/1.0.0"]),
        ("required_features", ["unknown/1.0"]),
        ("capabilities", ["identify", "read", "write"]),
        ("x-device-handshake", True),
    ],
)
def test_descriptor_semantic_drift_rejected(field: str, value: Any) -> None:
    async def scenario() -> None:
        host = Host()
        plugin = create_plugin()
        descriptor = build_descriptor()
        descriptor[field] = value
        with pytest.raises(ValueError):
            await plugin.open(descriptor, host, Context())
        await plugin.close(Context())
        await plugin.close(Context())
        assert host.closes == 1 and host.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "wire",
    [
        "",
        "f0a1c3",
        "f0a1c30c0000803f000000400000004081",
        "f0a1c0040000807fc3",
        "f0a1db0102de",
        "f0a1dd0102e0",
        "f0a1dc0107e4",
        "f1a1c300c3",
        "f0a1c3010000",
    ],
)
def test_malformed_response_poisons_session(wire: str) -> None:
    async def scenario() -> None:
        host = Host(bytes.fromhex(wire))
        plugin = await identified(host)
        result = await plugin.execute(request("read", parameter="voltage"), Context())
        validate_result(result)
        assert result["status"] != "ok"
        assert result["error"]["code"] == "PROTOCOL_ERROR"
        count = len(host.calls)
        host.wire = IDENTITY
        repeated = await plugin.execute(request(), Context())
        assert repeated["error"]["code"] == "TRANSPORT_ERROR"
        assert len(host.calls) == count

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError("secret"), "TIMEOUT"),
        (ConnectionError("secret"), "TRANSPORT_ERROR"),
        (ValueError("secret"), "INVALID_ARGUMENT"),
        (RuntimeError("secret"), "INTERNAL_ERROR"),
    ],
)
@pytest.mark.parametrize("at", [1, 2, 3, 4])
def test_host_failures_preserve_dispatch_uncertainty(
    failure: Exception, code: str, at: int
) -> None:
    """T5-9: every fault position is pinned, including at=1 — the drain's
    first receive (pre-send, not dispatched; only pinnable since the drain's
    window stopped conflating host TimeoutError with its own deadline)."""

    async def scenario() -> None:
        host = Host(bytes.fromhex("f0a1c30c0000803f00000040000000400e"))
        plugin = await identified(host)
        host.failure, host.fail_at = failure, at
        result = await plugin.execute(request("read", parameter="voltage"), Context())
        validate_result(result)
        assert result["error"]["code"] == code
        assert result["error"]["dispatch_state"] == (
            "not_dispatched" if at == 1 else "unknown" if at == 2 else "dispatched"
        )
        assert result["status"] == ("error" if at == 1 else "unknown")
        assert "secret" not in json.dumps(result)
        assert len(host.calls) == at

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("after", [0, 1, 2, 3])
def test_deadline_and_cancellation_boundaries(cancel: bool, after: int) -> None:
    """T5-9: after=1 pins the boundary between the drain's EOF receive and
    the send — a clock advance or cancellation landing there fails the call
    pre-dispatch, unlike after>=2 which lands inside the dispatched window."""

    async def scenario() -> None:
        host = Host(bytes.fromhex("f0a1c30c0000803f00000040000000400e"))
        plugin = await identified(host)
        context = Context()
        if after == 0:
            if cancel:
                context.cancelled = True
            else:
                context.deadline_monotonic = 100.0
        elif cancel:
            host.cancel_at = after
        else:
            host.advance_at = after
        result = await plugin.execute(request("read", parameter="voltage"), context)
        validate_result(result)
        assert result["error"]["code"] == ("CANCELLED" if cancel else "TIMEOUT")
        assert result["error"]["dispatch_state"] == (
            "not_dispatched" if after <= 1 else "dispatched"
        )
        assert result["status"] == (
            ("cancelled" if cancel else "error") if after <= 1 else "unknown"
        )
        assert len(host.calls) == after

    asyncio.run(scenario())


def test_envelope_mismatch_and_marker_failure() -> None:
    async def scenario() -> None:
        host = Host()
        plugin = await opened(host)
        result = await plugin.execute(request(), Context("different"))
        assert result["operation_id"] == "host-op"
        assert result["error"]["code"] == "INVALID_ARGUMENT"
        context = Context()
        context.marker_error = RuntimeError("secret")
        result = await plugin.execute(request(), context)
        assert result["error"]["dispatch_state"] == "not_dispatched"
        assert host.calls == []

    asyncio.run(scenario())


def test_close_no_reopen_and_no_retained_context() -> None:
    async def scenario() -> None:
        host = Host()
        plugin = await identified(host)
        await plugin.close(Context())
        await plugin.close(Context())
        assert host.closes == 1
        assert await plugin.next_event("none", Context()) is None
        result = await plugin.execute(request(), Context())
        assert result["error"]["code"] == "TRANSPORT_ERROR"
        assert host.calls == []
        with pytest.raises(RuntimeError):
            await plugin.open(build_descriptor(), host, Context())
        assert all(not isinstance(v, Context) for v in vars(plugin).values())

    asyncio.run(scenario())


def test_blocked_transfer_timeout_task_cancel_and_busy() -> None:
    async def scenario(cancel: bool) -> None:
        host = Host()
        plugin = await opened(host)
        host.block_at = 1
        task = asyncio.create_task(plugin.execute(request(), Context(deadline=100.03)))
        await host.entered.wait()
        busy = await plugin.execute(request(), Context())
        assert busy["error"]["code"] == "RESOURCE_LIMIT"
        if cancel:
            task.cancel()
        result = await task
        validate_result(result)
        assert result["status"] == "unknown"
        assert result["error"]["code"] == ("CANCELLED" if cancel else "TIMEOUT")
        assert len(host.calls) == 1

    asyncio.run(scenario(False))
    asyncio.run(scenario(True))


def test_model_mismatch_and_invalid_firmware() -> None:
    async def scenario(replies: list[bytes], code: str) -> None:
        host = Host()
        host.queue_replies(*replies)
        plugin = await opened(host)
        result = await plugin.execute(request(), Context())
        validate_result(result)
        assert result["error"]["code"] == code
        assert len(commanded_sends(host.calls)) <= 2
        before = len(host.calls)
        denied = await plugin.execute(request("read", parameter="voltage"), Context())
        assert denied["status"] != "ok" and len(host.calls) == before

    # Valid checksum, different model; malformed UTF-8 firmware; empty firmware.
    asyncio.run(scenario([bytes.fromhex("f0a1de014120")], "IDENTITY_MISMATCH"))
    for firmware in ["f0a1e001ffe0", "f0a1e000e0"]:
        asyncio.run(scenario([IDENTITY[:12], bytes.fromhex(firmware)], "PROTOCOL_ERROR"))


@pytest.mark.parametrize(
    "timestamp",
    [
        "yesterday",
        "2026-09-12",
        "2026-09-12 00:00:00Z",
        "2026-09-12T00:00:00+08:00",
        "2026-09-12T00:00:00+00:00:00",
        "2026-13-12T00:00:00Z",
    ],
)
def test_invalid_utc_never_becomes_a_valid_reading(timestamp: str) -> None:
    async def scenario() -> None:
        host = Host(bytes.fromhex("f0a1c0040000404145"))
        plugin = await identified(host)
        host.timestamp = timestamp
        result = await plugin.execute(request("read", parameter="input_voltage"), Context())
        validate_result(result)
        assert result["status"] != "ok" and "data" not in result

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "parameter,field,values",
    [
        ("output_enabled", 219, [False, True]),
        ("protection", 220, ["normal", "OVP", "OCP", "OPP", "OTP", "LVP", "REP"]),
        ("mode", 221, ["CC", "CV"]),
    ],
)
def test_complete_boolean_and_enum_maps(parameter: str, field: int, values: list[Any]) -> None:
    async def scenario() -> None:
        host = Host()
        plugin = await identified(host)
        for index, value in enumerate(values):
            host.wire = bytes([240, 161, field, 1, index, (field + 1 + index) % 256])
            result = await plugin.execute(request("read", parameter=parameter), Context())
            validate_result(result)
            assert result["data"]["value"] == value
            assert type(result["data"]["value"]) is type(value)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "parameter,wire",
    [
        ("output_enabled", "f0a1db0102de"),
        ("protection", "f0a1dc0107e4"),
        ("mode", "f0a1dd0102e0"),
        ("input_voltage", "f0a1c0040000807fc3"),
        ("input_voltage", "f0a1c0040000c07f03"),
    ],
)
def test_invalid_decoded_values(parameter: str, wire: str) -> None:
    async def scenario() -> None:
        host = Host(bytes.fromhex(wire))
        plugin = await identified(host)
        result = await plugin.execute(request("read", parameter=parameter), Context())
        assert result["error"]["code"] == "PROTOCOL_ERROR"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "write",
        "unit",
        "range",
        "binding",
        "key",
        "baud",
        "flow",
        "dependency",
        "permission",
        "api",
        "firmware",
        "path",
        "completion",
    ],
)
def test_descriptor_semantic_mutations(mutation: str) -> None:
    async def scenario() -> None:
        descriptor = build_descriptor()
        value: Any
        if mutation == "duplicate":
            descriptor["parameters"].append(descriptor["parameters"][0].copy())
        elif mutation in {"write", "unit", "range", "binding"}:
            key, value = {
                "write": ("access", "rw"),
                "unit": ("unit", "mV"),
                "range": ("range", [float("nan"), -1]),
                "binding": ("binding", {"kind": "adapter", "key": "other"}),
            }[mutation]
            descriptor["parameters"][0][key] = value
        elif mutation in {"key", "baud", "flow"}:
            if mutation == "key":
                descriptor["transport"]["connection_key"] = "other"
            else:
                descriptor["transport"]["settings"]["baud" if mutation == "baud" else "rtscts"] = 1
        elif mutation in {"dependency", "permission", "api"}:
            key, value = {
                "dependency": ("dependencies", [{"distribution": "unknown", "version": "*"}]),
                "permission": ("permissions", ["artifact_writer"]),
                "api": ("api_version", "1.0"),
            }[mutation]
            descriptor["integration"]["adapter"][key] = value
        elif mutation == "firmware":
            descriptor["identity"]["firmware_policy"] = "listed"
        elif mutation == "path":
            descriptor["provenance"]["test_vectors"][0]["path"] = "../../outside.json"
        else:
            descriptor["operations"]["read"]["completion"] = "physical"
        host = Host()
        with pytest.raises(ValueError):
            await create_plugin().open(descriptor, host, Context())
        assert host.calls == []

    asyncio.run(scenario())


def test_failed_close_retry_and_deadline() -> None:
    class ClosingHost(Host):
        async def close_transport(self, context: Any) -> None:
            self.closes += 1
            if self.closes == 1:
                raise ConnectionError("secret")

    async def scenario() -> None:
        host = ClosingHost()
        plugin = await opened(host)
        with pytest.raises(TimeoutError):
            await plugin.close(Context(deadline=99))
        assert host.closes == 0
        with pytest.raises(ConnectionError):
            await plugin.close(Context())
        assert (await plugin.execute(request(), Context()))["status"] != "ok"
        await plugin.close(Context())
        await plugin.close(Context())
        assert host.closes == 2

    asyncio.run(scenario())


def test_both_identity_queries_share_context_and_absolute_deadline() -> None:
    async def scenario() -> None:
        host = Host()
        host.queue_replies(IDENTITY[:12], IDENTITY[12:])
        plugin = await opened(host)
        host.advance_at = 6
        context = Context()
        result = await plugin.execute(request(), context)
        assert result["error"]["code"] == "TIMEOUT"
        assert all(seen is context for _, seen in host.calls)
        assert len(host.calls) == 6 and context.markers == 1
        assert context.deadline_monotonic == 101.0

    asyncio.run(scenario())


def test_packaged_failure_vectors() -> None:
    async def scenario(vector: dict[str, Any]) -> None:
        host = Host(bytes.fromhex(vector["response_hex"]))
        plugin = await opened(host) if vector["verb"] == "identify" else await identified(host)
        context = Context()
        match vector["fault"]:
            case "deadline":
                context.deadline_monotonic = 100.0
            case "receive_timeout":
                host.failure, host.fail_at = TimeoutError(), 3
            case "cancel":
                context.cancelled = True
            case "cancel_after_send":
                host.cancel_at = 2
            case "send_loss":
                host.failure, host.fail_at = ConnectionError(), 2
            case None:
                pass
            case _:
                raise AssertionError("Unknown mock fault")
        result = await plugin.execute(request(vector["verb"], **vector["arguments"]), context)
        validate_result(result)
        assert result["status"] == vector["status"]
        assert result["error"]["code"] == vector["code"]
        assert result["error"]["dispatch_state"] == vector["dispatch_state"]
        sent = [data.hex() for data in commanded_sends(host.calls)]
        assert sent == ([] if vector["request_hex"] is None else [vector["request_hex"]])

    for vector in json.loads((PACKAGE / "adapter-failure-vectors.json").read_text()):
        asyncio.run(scenario(vector))


def test_negative_numeric_reading_is_not_clamped_to_setpoint_limits() -> None:
    async def scenario() -> None:
        host = Host(bytes.fromhex("f0a1c004000080bf03"))
        plugin = await identified(host)
        result = await plugin.execute(request("read", parameter="input_voltage"), Context())
        validate_result(result)
        assert result["data"]["value"] == -1.0

    asyncio.run(scenario())


class TransportHost:
    """HostServices bridging scoped transfers onto a Transport mock.

    stream_send forwards to the transport; stream_receive buffers whole
    transport chunks and serves the adapter's exact byte counts. A transport
    offering no bytes resolves the transfer with b"", which the adapter's
    drain reads as end-of-stream.
    """

    def __init__(self, transport: Any) -> None:
        self.transport = transport
        self.now = 100.0
        self.timestamp = "2026-09-12T03:00:00Z"
        self.closes = 0
        self.buffer = bytearray()

    def monotonic(self) -> float:
        return self.now

    def utc_now(self) -> str:
        return self.timestamp

    async def transfer(self, transaction: dict[str, Any], context: Any) -> dict[str, Any]:
        if transaction["kind"] == "stream_send":
            assert set(transaction) == {"kind", "data"}
            await self.transport.send(transaction["data"])
            return {}
        assert transaction["kind"] == "stream_receive"
        size = transaction["exact_bytes"]
        while len(self.buffer) < size:
            chunk = await self.transport.receive(260)
            if not chunk:
                break
            self.buffer.extend(chunk)
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return {"data": data}

    async def close_transport(self, context: Any) -> None:
        self.closes += 1


def test_adapter_establishes_the_session_at_first_commanded_use(
    handshaking_transport: Any,
) -> None:
    """The captured negative, replayed through the adapter: the device stays
    silent until the exact handshake, so the adapter must send it itself at
    establishment. The send is unconditional — an already-awake device (a
    reconnect; the wake is power-cycle-bound) ignores it harmlessly."""

    async def scenario() -> None:
        host = TransportHost(handshaking_transport)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        result = await plugin.execute(request(), Context())
        validate_result(result)
        assert result["status"] == "ok"
        assert result["data"]["model"] == "DPS-150"
        assert handshaking_transport.sent[:2] == [SESSION_OPEN, BAUD_NEGOTIATE]

    asyncio.run(scenario())


def test_commanded_read_survives_interleaved_telemetry(
    handshaking_transport: Any,
) -> None:
    """A woken device streams telemetry around every reply; the bounded drain
    before each commanded call keeps the Client's one-frame rule intact
    without discarding the interleaved frames."""

    async def scenario() -> None:
        host = TransportHost(handshaking_transport)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        identified = await plugin.execute(request(), Context())
        assert identified["status"] == "ok"
        for _ in range(2):
            result = await plugin.execute(request("read", parameter="voltage"), Context())
            validate_result(result)
            assert result["status"] == "ok"
            assert result["data"]["parameter"] == "voltage"
            assert result["data"]["value"] == 0.0
        assert handshaking_transport.awake

    asyncio.run(scenario())


def test_trailing_telemetry_never_poisons_sequential_reads(
    trailing_transport: Any,
) -> None:
    """live-stream.jsonl "diagnosis-final" replayed: telemetry trails — and
    races ahead of — the reply inside the commanded receive window, so the
    Client's strict one-frame view poisoned the whole instance after the
    first interleaved window (34 ok / 1 unknown / 235 instant errors on the
    live device). Correlated reply consumption must keep identify and N
    sequential reads healthy on ONE plugin instance."""

    async def scenario() -> None:
        host = TransportHost(trailing_transport)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        result = await plugin.execute(request(), Context())
        validate_result(result)
        assert result["status"] == "ok"
        assert result["data"]["model"] == "DPS-150"
        for _ in range(5):
            read = await plugin.execute(request("read", parameter="input_voltage"), Context())
            validate_result(read)
            assert read["status"] == "ok"
            assert read["data"]["parameter"] == "input_voltage"
            assert read["data"]["value"] == pytest.approx(20.067, abs=1e-3)
        assert trailing_transport.awake

    asyncio.run(scenario())


def test_interleaved_frames_absorbed_from_commanded_windows_still_surface(
    trailing_transport: Any,
) -> None:
    """Telemetry frames absorbed out of a commanded reply window surface
    through latest_telemetry() in the reading shape — same PARAMETERS
    mapping as the drain, one row per parameter, nothing discarded."""

    async def scenario() -> None:
        host = TransportHost(trailing_transport)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        identified = await plugin.execute(request(), Context())
        assert identified["status"] == "ok"
        for parameter in ("input_voltage", "temperature"):
            read = await plugin.execute(request("read", parameter=parameter), Context())
            validate_result(read)
            assert read["status"] == "ok"
        rows = plugin.latest_telemetry()
        by_parameter = {row["parameter"]: row for row in rows}
        assert set(by_parameter) == {
            "voltage",
            "current",
            "power",
            "input_voltage",
            "temperature",
        }
        assert by_parameter["voltage"]["value"] == pytest.approx(0.0)
        assert by_parameter["input_voltage"]["value"] == pytest.approx(20.067, abs=1e-3)
        for row in rows:
            assert row["quality"] == "valid" and row["source"] == "device"
            assert row["age_ms"] >= 0

    asyncio.run(scenario())


def test_drained_telemetry_surfaces_in_the_reading_shape(
    handshaking_transport: Any,
) -> None:
    """Drained telemetry is observable through the adapter's measurement
    surface: field 195 arrives as voltage/current/power (V/A/W) per the
    PARAMETERS contract, in the reading envelope's shape."""

    async def scenario() -> None:
        host = TransportHost(handshaking_transport)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        result = await plugin.execute(request(), Context())
        assert result["status"] == "ok"
        rows = plugin.latest_telemetry()
        by_parameter = {row["parameter"]: row for row in rows}
        assert set(by_parameter) == {
            "voltage",
            "current",
            "power",
            "input_voltage",
            "temperature",
        }
        assert by_parameter["voltage"]["value"] == pytest.approx(0.0)
        assert [by_parameter[name]["unit"] for name in ("voltage", "current", "power")] == [
            "V",
            "A",
            "W",
        ]
        assert by_parameter["input_voltage"]["value"] == pytest.approx(20.067, abs=1e-3)
        assert by_parameter["temperature"]["value"] == pytest.approx(21.454, abs=1e-3)
        for row in rows:
            assert row["observed_at"] == "2026-09-12T03:00:00Z"
            assert row["age_ms"] >= 0
            assert row["quality"] == "valid" and row["source"] == "device"

    asyncio.run(scenario())


def test_drain_edge_straddle_never_poisons_the_session(
    trailing_transport: Any,
) -> None:
    """WP10 Forge W1 replayed: a telemetry frame straddles the drain window
    edge — header bytes inside the window, tail bytes 0.25 s later against
    the 0.15 s drain. Cancel-at-deadline abandoned the frame mid-receive;
    the stale buffered bytes then failed header validation inside the
    commanded window AFTER dispatch, and the ambiguity doctrine poisoned
    the session permanently. A frame-atomic drain keeps the session
    healthy on one plugin instance."""

    async def scenario() -> None:
        telemetry_195 = bytes.fromhex(
            "f0 a1 c3 0c 00 00 00 00 00 00 00 00 00 00 00 00 cf"
        )
        host = TransportHost(trailing_transport)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        identified = await plugin.execute(request(), Context())
        validate_result(identified)
        assert identified["status"] == "ok"
        inner = trailing_transport.receive
        state = {"stage": 0}

        async def straddling(max_bytes: int) -> bytes:
            gets = sum(
                1 for data in trailing_transport.sent if data[:2] == bytes((0xF1, GET))
            )
            if state["stage"] == 0 and trailing_transport.awake and gets >= 2:
                state["stage"] = 1
                return telemetry_195[:8]
            if state["stage"] == 1:
                state["stage"] = 2
                await asyncio.sleep(0.25)
                return telemetry_195[8:]
            return bytes(await inner(max_bytes))

        trailing_transport.receive = straddling
        first = await plugin.execute(request("read", parameter="voltage"), Context())
        validate_result(first)
        assert first["status"] == "ok"
        second = await plugin.execute(request("read", parameter="voltage"), Context())
        validate_result(second)
        assert second["status"] == "ok"

    asyncio.run(scenario())


def test_same_field_telemetry_frame_is_the_reply(same_field_transport: Any) -> None:
    """W2 pin: the protocol has no reply marker, so the correlated wire
    accepts the FIRST frame carrying the requested field — when the ~2 Hz
    telemetry cycle includes that field, the telemetry frame IS the reply.
    The reading is measurement-honest (device-reported, receipt-stamped);
    the superseded reply frame stays in the stream and is absorbed as
    telemetry by a later window (not asserted here — the mock's infinite
    cycle makes latest-wins nondeterministic beyond this window)."""

    async def scenario() -> None:
        host = TransportHost(same_field_transport)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        identified = await plugin.execute(request(), Context())
        validate_result(identified)
        assert identified["status"] == "ok"
        read = await plugin.execute(request("read", parameter="voltage"), Context())
        validate_result(read)
        assert read["status"] == "ok"
        # The telemetry frame (0 V, output off) won the same-field race —
        # not the 2.5 V reply queued behind it in the same window.
        assert read["data"]["value"] == 0.0
        assert same_field_transport.awake

    asyncio.run(scenario())


def test_telemetry_rows_reject_an_invalid_host_timestamp(
    trailing_transport: Any,
) -> None:
    """T5-10: telemetry rows carry the same host-stamp validation as the
    read path — an invalid utc_now during a telemetry-bearing operation
    fails the call (INVALID_ARGUMENT, pre-dispatch) instead of surfacing a
    row with an unvalidated timestamp."""

    async def scenario() -> None:
        host = TransportHost(trailing_transport)
        plugin = create_plugin()
        await plugin.open(build_descriptor(), host, Context())
        identified = await plugin.execute(request(), Context())
        assert identified["status"] == "ok"
        host.timestamp = "yesterday"
        read = await plugin.execute(request("read", parameter="voltage"), Context())
        validate_result(read)
        assert read["status"] != "ok"
        assert read["error"]["code"] == "INVALID_ARGUMENT"
        assert read["error"]["dispatch_state"] == "not_dispatched"

    asyncio.run(scenario())


def test_session_constants_stay_evidence_backed() -> None:
    from benchweave_fnirsi_dps150.adapter import _DRAIN_WINDOW_S, _SESSION_DELAY_S

    assert _SESSION_DELAY_S == 0.05  # connect-v2.jsonl fire-and-forget pacing
    assert _DRAIN_WINDOW_S == 0.15  # above the ~100 ms inter-frame gap of the 2 Hz cycle
