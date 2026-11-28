# author: Stephen Eaton
"""A4 and the adapter lifecycle, driven through the OTDP adapter API 1.1
surface against a SYNTHETIC host.

Every reply here is SYNTHETIC: it has the shape the manufacturer's programming
guide documents and invented values. Nothing was recorded on an instrument
and no result below is hardware-qualified.
"""

from typing import Any

import pytest
from support import Context, Host, request, run, vectors

from benchweave_rigol_dho924s.adapter import (
    IDN_MAX_BYTES,
    OPERATION_BUDGET_S,
    create_plugin,
)
from benchweave_rigol_dho924s.descriptor import MANUFACTURER, MODEL, build_descriptor

UNSUPPORTED_VERBS = [
    "read",
    "write",
    "self_test",
    "get_errors",
    "capture",
    "stream_subscribe",
    "stream_unsubscribe",
    "reset",
    "invoke",
]


def opened(host: Host, descriptor: dict[str, Any] | None = None) -> Any:
    plugin: Any = create_plugin()

    async def scenario() -> None:
        await plugin.open(build_descriptor() if descriptor is None else descriptor, host, Context())

    run(scenario())
    assert host.calls == []
    return plugin


def execute(
    plugin: Any, operation: dict[str, Any], context: Context | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = run(
        plugin.execute(operation, Context() if context is None else context)
    )
    return result


def test_identify_through_the_mock_transport_returns_the_committed_identity_from_a_SYNTHETIC_vector(
    validate: Any,
) -> None:
    for vector in vectors("adapter-vectors.json")["identity"]:
        host = Host(bytes.fromhex(vector["response_hex"]))
        plugin = opened(host)
        result = execute(plugin, request("identify"))
        validate(result)
        assert result == vector["result"]
        assert result["data"]["manufacturer"] == MANUFACTURER == "RIGOL"
        assert result["data"]["model"] == MODEL == "DHO924S"


def test_identify_sends_one_framed_query_and_declares_its_receive_bound(validate: Any) -> None:
    vector = vectors("adapter-vectors.json")["identity"][0]
    host = Host(bytes.fromhex(vector["response_hex"]))
    result = execute(opened(host), request("identify"))
    validate(result)
    assert [transaction for transaction, _ in host.calls] == [
        {"kind": "stream_send", "data": bytes.fromhex(vector["request_hex"])},
        {
            "kind": "stream_receive",
            "max_bytes": IDN_MAX_BYTES,
            "termination": "lf",
            "exact_bytes": None,
        },
    ]
    assert host.sent() == [b"*IDN?\n"]
    assert host.buffer == b""


def test_each_synthetic_identity_failure_never_becomes_an_identity(
    validate: Any,
) -> None:
    failures = vectors("adapter-failure-vectors.json")["identity"]
    assert len(failures) == 10
    for vector in failures:
        host = Host(bytes.fromhex(vector["response_hex"]) if vector["response_hex"] else b"")
        context = Context()
        fault = vector["fault"]
        if fault == "deadline":
            context.deadline_monotonic = 100.0
        elif fault == "receive_timeout":
            host.advance_at = 2
        elif fault == "cancel":
            context.cancelled = True
        elif fault == "cancel_after_send":
            host.cancel_at = 2
        elif fault in {"send_loss", "receive_loss"}:
            host.fail_at = 1 if fault == "send_loss" else 2
            host.failure = ConnectionError("link lost")
        plugin = opened(host)
        result = execute(plugin, request("identify"), context)
        validate(result)
        assert (result["status"], result["error"]["code"], result["error"]["dispatch_state"]) == (
            vector["status"],
            vector["code"],
            vector["dispatch_state"],
        ), vector["id"]
        assert "data" not in result


@pytest.mark.parametrize("verb", UNSUPPORTED_VERBS)
def test_unadvertised_verbs_never_dispatch(verb: str, validate: Any) -> None:
    host = Host()
    plugin = opened(host)
    result = execute(plugin, request(verb))
    validate(result)
    assert result["verb"] == verb
    assert result["error"] == {
        "code": "UNSUPPORTED",
        "message": "Operation is not advertised",
        "dispatch_state": "not_dispatched",
    }
    assert host.calls == []
    assert run(plugin.next_event("anything", Context())) is None


def test_open_and_close_do_no_device_io() -> None:
    host = Host()
    plugin = opened(host)
    assert host.calls == []

    async def scenario() -> None:
        await plugin.close(Context())
        await plugin.close(Context())
        await plugin.close(Context())

    run(scenario())
    assert host.calls == []
    assert host.closes == 1


def test_execute_before_open_is_refused_without_io(validate: Any) -> None:
    plugin = create_plugin()
    result = execute(plugin, request("identify"))
    validate(result)
    assert result["error"]["code"] == "TRANSPORT_ERROR"
    assert result["error"]["dispatch_state"] == "not_dispatched"


def test_nothing_is_dispatched_after_close(validate: Any) -> None:
    host = Host()
    plugin = opened(host)

    async def scenario() -> dict[str, Any]:
        await plugin.close(Context())
        result: dict[str, Any] = await plugin.execute(request("identify"), Context())
        return result

    result = run(scenario())
    validate(result)
    assert result["error"]["code"] == "TRANSPORT_ERROR"
    assert host.calls == []


def test_a_failed_exchange_past_dispatch_blocks_the_instance(validate: Any) -> None:
    host = Host(b"RIGOL TECHNOLOGIES,DHO914S,SYNTHETIC-SERIAL,SYNTHETIC-FIRMWARE\n")
    plugin = opened(host)
    first = execute(plugin, request("identify"))
    assert first["error"]["code"] == "IDENTITY_MISMATCH"
    second = execute(plugin, request("identify"))
    validate(second)
    assert second["error"]["code"] == "TRANSPORT_ERROR"
    assert second["error"]["dispatch_state"] == "not_dispatched"
    assert len(host.calls) == 2


def test_open_refuses_a_changed_descriptor_and_still_allows_close() -> None:
    host = Host()
    changed = build_descriptor()
    changed["capabilities"].append("read")
    plugin: Any = create_plugin()

    async def scenario() -> None:
        with pytest.raises(ValueError):
            await plugin.open(changed, host, Context())
        await plugin.close(Context())

    run(scenario())
    assert host.calls == []
    assert host.closes == 1


def test_open_twice_requires_a_fresh_instance() -> None:
    host = Host()
    plugin = opened(host)
    with pytest.raises(RuntimeError):
        run(plugin.open(build_descriptor(), host, Context()))
    assert create_plugin() is not create_plugin()


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param({"operation_id": "other-op", "verb": "identify", "arguments": {}}),
        pytest.param({"operation_id": "host-op", "verb": "identify", "arguments": {}, "extra": 1}),
        pytest.param({"operation_id": "host-op", "verb": "identify"}),
        pytest.param(
            {"operation_id": "host-op", "verb": "identify", "arguments": {"parameter": "x"}}
        ),
    ],
)
def test_an_invalid_envelope_is_refused_before_io(operation: dict[str, Any], validate: Any) -> None:
    host = Host()
    result = execute(opened(host), operation)
    validate(result)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert result["error"]["dispatch_state"] == "not_dispatched"
    assert host.calls == []


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param({"verb": "identify"}, id="no-operation-id"),
        pytest.param({"operation_id": "host-op", "arguments": {}}, id="no-verb"),
        pytest.param({"operation_id": "host-op", "verb": "no-such-verb", "arguments": {}}),
        # An empty operation id cannot be echoed in a valid result.
        pytest.param({"operation_id": "", "verb": "identify", "arguments": {}}, id="empty-id"),
        pytest.param("identify"),
    ],
)
def test_an_envelope_without_runtime_identity_cannot_be_answered(operation: Any) -> None:
    host = Host()
    plugin = opened(host)
    with pytest.raises(ValueError):
        execute(plugin, operation)
    assert host.calls == []


def test_the_operation_budget_is_the_descriptor_policy() -> None:
    policy = build_descriptor()["operations"]["identify"]
    assert policy["timeout_ms"] == OPERATION_BUDGET_S * 1000
    assert policy["retry"] == "never"
    assert policy["side_effect"] == "none"


def test_the_identity_bound_is_a_software_bound_far_above_any_identity_reply() -> None:
    # A protective bound the adapter declares, not a measurement of the unit.
    assert IDN_MAX_BYTES == 256
