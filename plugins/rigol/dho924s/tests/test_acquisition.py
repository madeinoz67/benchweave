# author: Stephen Eaton
"""A3: the acquisition state machine.

The machine is hardware-independent machinery: it enforces the order of the
oscilloscope class actions and refuses what the unit has not evidenced, over
an injected backend. The backend used here is SYNTHETIC: it records calls and
returns invented values. No SCPI for configure, arm, fetch or abort is
evidenced for the unit, so none is written and the plugin does not route
these actions to the wire.
"""

from collections.abc import Mapping
from typing import Any

import pytest
from support import Context, Host, request, run, validate_result

from benchweave_rigol_dho924s.adapter import (
    OSCILLOSCOPE_ACTIONS,
    AcquisitionMachine,
    AcquisitionState,
    create_plugin,
)
from benchweave_rigol_dho924s.descriptor import build_descriptor


class FakeBackend:
    """SYNTHETIC backend: records each call and returns invented values."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.fail_at: str | None = None
        self.dataset: dict[str, Any] = {"origin": "synthetic"}

    def _record(self, name: str, argument: object) -> None:
        self.calls.append((name, argument))
        if self.fail_at == name:
            raise ConnectionError("link lost")

    async def apply(self, configuration: Mapping[str, object]) -> Mapping[str, object]:
        self._record("apply", dict(configuration))
        return dict(configuration)

    async def start(self, acquisition_id: str, max_duration_ms: int) -> None:
        self._record("start", (acquisition_id, max_duration_ms))

    async def read(self, acquisition_id: str) -> object:
        self._record("read", acquisition_id)
        return self.dataset

    async def stop(self, acquisition_id: str) -> None:
        self._record("stop", acquisition_id)


# A SYNTHETIC supported set. Nothing says which trigger kinds the unit supports.
EDGE_ONLY = frozenset({"edge"})


def machine(
    backend: FakeBackend | None = None, kinds: frozenset[str] = EDGE_ONLY
) -> AcquisitionMachine:
    return AcquisitionMachine(backend=backend, supported_trigger_kinds=kinds)


def configure(
    target: AcquisitionMachine, operation_id: str = "op-cfg", trigger_kind: str = "edge"
) -> dict[str, Any]:
    return run(
        target.configure(
            operation_id,
            configuration_id="cfg-1",
            trigger_kind=trigger_kind,
            settings={"timebase": "synthetic"},
        )
    )


def arm(target: AcquisitionMachine, acquisition_id: str = "acq-1") -> dict[str, Any]:
    return run(
        target.arm(
            "op-arm",
            configuration_id="cfg-1",
            acquisition_id=acquisition_id,
            max_duration_ms=100,
        )
    )


def armed(backend: FakeBackend | None = None) -> AcquisitionMachine:
    target = machine(backend)
    assert configure(target)["status"] == "ok"
    assert arm(target)["status"] == "ok"
    assert target.state is AcquisitionState.ARMED
    if backend is not None:
        backend.calls.clear()
    return target


def assert_refusal(result: dict[str, Any], code: str, message_part: str, validate: Any) -> None:
    validate_result(result)
    assert result["verb"] == "invoke"
    assert result["status"] == "error"
    assert result["error"]["code"] == code
    assert result["error"]["dispatch_state"] == "not_dispatched"
    assert message_part in result["error"]["message"]
    assert "data" not in result


def test_arm_before_configure_refuses(validate: Any) -> None:
    backend = FakeBackend()
    target = machine(backend)
    result = arm(target)
    assert_refusal(result, "DEVICE_REJECTED", "configure before arm", validate)
    assert target.state is AcquisitionState.IDLE
    assert backend.calls == []


def test_arm_with_another_configuration_id_refuses(validate: Any) -> None:
    backend = FakeBackend()
    target = machine(backend)
    assert configure(target)["status"] == "ok"
    result = run(
        target.arm(
            "op-arm",
            configuration_id="cfg-other",
            acquisition_id="acq-1",
            max_duration_ms=100,
        )
    )
    assert_refusal(result, "DEVICE_REJECTED", "configuration_id", validate)
    assert target.state is AcquisitionState.CONFIGURED
    assert [name for name, _ in backend.calls] == ["apply"]


def test_fetch_before_arm_refuses(validate: Any) -> None:
    backend = FakeBackend()
    target = machine(backend)
    assert_refusal(
        run(target.fetch("op-fetch", acquisition_id="acq-1")),
        "INVALID_ARGUMENT",
        "unknown acquisition",
        validate,
    )
    assert target.state is AcquisitionState.IDLE
    assert configure(target)["status"] == "ok"
    assert_refusal(
        run(target.fetch("op-fetch", acquisition_id="acq-1")),
        "INVALID_ARGUMENT",
        "unknown acquisition",
        validate,
    )
    assert target.state is AcquisitionState.CONFIGURED
    assert [name for name, _ in backend.calls] == ["apply"]


def test_abort_from_armed_returns_to_idle(validate: Any) -> None:
    backend = FakeBackend()
    target = armed(backend)
    result = run(target.abort("op-abort", acquisition_id="acq-1"))
    validate_result(result)
    assert result == {
        "operation_id": "op-abort",
        "verb": "invoke",
        "status": "ok",
        "data": {
            "action_id": "otdp.oscilloscope.abort/1.0.0",
            "result": {"acquisition_id": "acq-1", "state": "aborted"},
        },
    }
    assert target.state is AcquisitionState.IDLE
    assert backend.calls == [("stop", "acq-1")]
    # The acquisition is gone: nothing can be fetched or aborted under its id.
    assert_refusal(
        run(target.fetch("op-fetch", acquisition_id="acq-1")),
        "INVALID_ARGUMENT",
        "unknown acquisition",
        validate,
    )
    assert_refusal(
        run(target.abort("op-abort", acquisition_id="acq-1")),
        "INVALID_ARGUMENT",
        "unknown acquisition",
        validate,
    )
    assert backend.calls == [("stop", "acq-1")]


def test_unsupported_trigger_kind_refuses_with_the_class_shape_and_is_not_substituted(
    validate: Any,
) -> None:
    backend = FakeBackend()
    target = machine(backend)
    result = configure(target, trigger_kind="external")
    assert_refusal(result, "INVALID_ARGUMENT", "trigger kind 'external'", validate)
    assert "'edge'" in result["error"]["message"]
    assert target.state is AcquisitionState.IDLE
    assert backend.calls == []
    # Nothing was substituted: there is still no configuration to arm.
    assert_refusal(arm(target), "DEVICE_REJECTED", "configure before arm", validate)
    assert backend.calls == []
    # A supported kind still configures; the refusal changed no state.
    assert configure(target, trigger_kind="edge")["status"] == "ok"
    assert [name for name, _ in backend.calls] == ["apply"]
    assert backend.calls[0][1] == {
        "configuration_id": "cfg-1",
        "trigger_kind": "edge",
        "settings": {"timebase": "synthetic"},
    }


def test_configure_passes_the_request_to_the_backend_and_returns_the_readback(
    validate: Any,
) -> None:
    backend = FakeBackend()
    target = machine(backend)
    result = configure(target)
    validate_result(result)
    assert result["status"] == "ok"
    assert result["data"]["action_id"] == "otdp.oscilloscope.configure/1.0.0"
    assert result["data"]["result"]["configuration_id"] == "cfg-1"
    assert result["data"]["result"]["effective_configuration"] == backend.calls[0][1]
    assert target.state is AcquisitionState.CONFIGURED


def test_configure_during_a_live_acquisition_refuses(validate: Any) -> None:
    backend = FakeBackend()
    target = armed(backend)
    assert_refusal(configure(target), "DEVICE_REJECTED", "live acquisition", validate)
    assert target.state is AcquisitionState.ARMED
    assert backend.calls == []


def test_arm_twice_refuses_and_keeps_the_first_acquisition(validate: Any) -> None:
    backend = FakeBackend()
    target = armed(backend)
    assert_refusal(
        arm(target, acquisition_id="acq-2"), "DEVICE_REJECTED", "already armed", validate
    )
    assert target.state is AcquisitionState.ARMED
    assert backend.calls == []


def test_fetch_returns_the_backend_dataset_and_completes_the_acquisition(validate: Any) -> None:
    backend = FakeBackend()
    target = armed(backend)
    result = run(target.fetch("op-fetch", acquisition_id="acq-1"))
    validate_result(result)
    assert result["data"] == {
        "action_id": "otdp.oscilloscope.fetch/1.0.0",
        "result": backend.dataset,
    }
    assert target.state is AcquisitionState.FETCHED
    assert backend.calls == [("read", "acq-1")]
    assert_refusal(
        run(target.abort("op-abort", acquisition_id="acq-1")),
        "INVALID_ARGUMENT",
        "unknown acquisition",
        validate,
    )
    # A completed acquisition leaves the configuration in place for the next one.
    assert arm(target, acquisition_id="acq-2")["status"] == "ok"


@pytest.mark.parametrize("failing", ["apply", "start", "read", "stop"])
def test_a_failed_backend_call_leaves_the_state_unknown_and_blocks_reuse(
    failing: str, validate: Any
) -> None:
    backend = FakeBackend()
    target = machine(backend)
    if failing in {"read", "stop"}:
        target = armed(backend)
    elif failing == "start":
        assert configure(target)["status"] == "ok"
    backend.fail_at = failing
    operation = {
        "apply": lambda: configure(target),
        "start": lambda: arm(target),
        "read": lambda: run(target.fetch("op-fetch", acquisition_id="acq-1")),
        "stop": lambda: run(target.abort("op-abort", acquisition_id="acq-1")),
    }[failing]
    with pytest.raises(ConnectionError):
        operation()
    assert target.state is AcquisitionState.FAULTED
    assert_refusal(configure(target), "TRANSPORT_ERROR", "fresh instance", validate)
    assert_refusal(arm(target), "TRANSPORT_ERROR", "fresh instance", validate)
    assert_refusal(
        run(target.fetch("op-fetch", acquisition_id="acq-1")),
        "TRANSPORT_ERROR",
        "fresh instance",
        validate,
    )
    assert_refusal(
        run(target.abort("op-abort", acquisition_id="acq-1")),
        "TRANSPORT_ERROR",
        "fresh instance",
        validate,
    )


def test_without_a_backend_no_acquisition_action_reaches_a_device(validate: Any) -> None:
    target = AcquisitionMachine(backend=None, supported_trigger_kinds=EDGE_ONLY)
    assert_refusal(configure(target), "UNSUPPORTED", "no acquisition backend", validate)
    assert_refusal(arm(target), "DEVICE_REJECTED", "configure before arm", validate)
    assert target.state is AcquisitionState.IDLE


def test_the_plugin_owns_an_inert_machine_and_does_not_route_actions_to_the_wire(
    validate: Any,
) -> None:
    plugin = create_plugin()
    assert plugin.acquisition.backend is None
    assert plugin.acquisition.supported_trigger_kinds == frozenset()
    host = Host()
    run(plugin.open(build_descriptor(), host, Context()))
    assert len(OSCILLOSCOPE_ACTIONS) == 5
    for action_id in OSCILLOSCOPE_ACTIONS:
        result = run(
            plugin.execute(
                request("invoke", action_id=action_id, input={"acquisition_id": "acq-1"}),
                Context(),
            )
        )
        validate_result(result)
        assert result["error"]["code"] == "UNSUPPORTED"
        assert result["error"]["dispatch_state"] == "not_dispatched"
    # No trigger kind is evidenced for the unit, so even the machine refuses.
    assert_refusal(configure(plugin.acquisition), "UNSUPPORTED", "no acquisition backend", validate)
    assert host.calls == []


def test_software_trigger_cannot_be_admitted_without_the_trigger_action() -> None:
    # The class makes the optional trigger action mandatory once `software`
    # is a trigger kind. This adapter has no trigger action.
    with pytest.raises(ValueError):
        AcquisitionMachine(backend=FakeBackend(), supported_trigger_kinds=frozenset({"software"}))
    with pytest.raises(ValueError):
        AcquisitionMachine(backend=None, supported_trigger_kinds={"edge"})  # type: ignore[arg-type]
