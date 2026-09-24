"""The bridge-leg OTDP adapter for the simulated DC supply (issue #176 row D).

The plugin package serves two consumption shapes:

* ``plugin.py`` — the synchronous DevicePlugin of the fixture-sim leg
  (``_load_sim_plugin``), loaded from the repo by path; it imports
  benchweave types and its create_plugin carries the injected-clock
  form. It is NOT loadable through the registry bundle loader, whose
  admitted imports resolve to stdlib only.
* ``adapter.py`` (this module) — the async OTDP adapter protocol the
  OTDPBridge drives: stdlib-only, zero-argument ``create_plugin``
  factory, entered through the descriptor's
  ``integration.adapter.entry_point``.

Device semantics mirror the synchronous core for the verbs the bridge
dispatches (identify, read, write; bounds and the OVP/OCP trip latch
included) with the deterministic simulator posture (no wall clock, no
I/O — time arrives through the scoped services). Streaming is row D's
increment: ``next_event`` produces telemetry for the subscribed
parameter at the SUBSCRIBED interval (the host gate refuses requests
below the descriptor's declared ``stream_limits.min_interval_ms``
floor), sequences start at zero and strictly increase per subscription,
and the terminal ``ended`` event fires when a fixed synthetic-telemetry
budget exhausts — a simulator authoring choice pinned by the row-D
tests; the bridge's event validators remain the authority a sim must
not trip.
"""

from __future__ import annotations

from typing import Any

MAX_VOLTAGE_V = 30.0
MAX_CURRENT_A = 5.0

WRITABLE_BOUNDS: dict[str, tuple[float, float]] = {
    "voltage_setpoint_v": (0.0, MAX_VOLTAGE_V),
    "current_limit_a": (0.0, MAX_CURRENT_A),
    "ovp_threshold_v": (0.0, MAX_VOLTAGE_V),
    "ocp_threshold_a": (0.0, MAX_CURRENT_A),
    "load_a": (0.0, MAX_CURRENT_A),
}

_EVENTS_PER_SUBSCRIPTION = 4


class _Subscription:
    """Per-subscription emission state (the adapter's own bookkeeping; the
    host's registry is the authority it must agree with)."""

    __slots__ = ("parameter", "min_interval_s", "next_sequence", "next_emit_s")

    def __init__(self, parameter: str, min_interval_ms: int, now: float) -> None:
        self.parameter = parameter
        self.min_interval_s = min_interval_ms / 1000.0
        self.next_sequence = 0
        self.next_emit_s = now


class SimPsuStreamAdapter:
    """The async OTDP adapter: bridge verb dispatch plus event production.

    constructed by the zero-argument ``create_plugin`` factory (the OTDP
    ABI); ``open`` receives the descriptor and the scoped OTDP services
    whose ``monotonic``/``utc_now`` are this simulator's only time
    sources.
    """

    def __init__(self) -> None:
        self._services: Any = None
        self._descriptor: Any = None
        self._subscriptions: dict[str, _Subscription] = {}
        self._tripped: str | None = None
        self._state: dict[str, Any] = {
            "output_enabled": False,
            "voltage_setpoint_v": 0.0,
            "current_limit_a": MAX_CURRENT_A,
            "ovp_threshold_v": MAX_VOLTAGE_V,
            "ocp_threshold_a": MAX_CURRENT_A,
            "load_a": 0.0,
            "operator_note": "",
        }

    async def open(self, descriptor: Any, services: Any, context: Any) -> None:
        self._descriptor = descriptor
        self._services = services

    async def close(self, context: Any) -> None:
        self._subscriptions.clear()

    async def execute(self, envelope: dict[str, Any], context: Any) -> dict[str, Any]:
        verb = envelope["verb"]
        arguments = envelope["arguments"]
        operation_id = envelope["operation_id"]
        if verb == "identify":
            return self._ok(operation_id, verb, self._identity_data())
        if verb == "read":
            reading, failure = self._reading_data(arguments.get("parameter"))
            if failure is not None:
                return self._error(operation_id, verb, failure)
            return self._ok(operation_id, verb, reading)
        if verb == "write":
            receipt, failure = self._write(arguments.get("parameter"), arguments.get("value"))
            if failure is not None:
                return self._error(operation_id, verb, failure)
            return self._ok(operation_id, verb, receipt)
        if verb in ("stream_subscribe", "stream_unsubscribe"):
            return self._stream_verb(verb, operation_id, arguments)
        return self._error(
            operation_id,
            verb,
            ("UNSUPPORTED", f"adapter does not implement {verb}", "not_dispatched"),
        )

    async def next_event(self, subscription_id: str, context: Any) -> dict[str, Any] | None:
        subscription = self._subscriptions.get(subscription_id)
        if subscription is None:
            return None
        now = context.services.monotonic()
        if now < subscription.next_emit_s:
            # The declared floor: a healthy quiet stream produces no data
            # and is not an error (spec §8).
            return None
        if subscription.next_sequence >= _EVENTS_PER_SUBSCRIPTION:
            del self._subscriptions[subscription_id]
            return {
                "subscription_id": subscription_id,
                "sequence": subscription.next_sequence,
                "kind": "ended",
                "code": "stream_completed",
                "message": (
                    f"synthetic telemetry budget of {_EVENTS_PER_SUBSCRIPTION} "
                    "events exhausted"
                ),
            }
        reading, failure = self._reading_data(subscription.parameter)
        if failure is not None:
            # The subscribed parameter must exist; a sim that cannot read
            # what it subscribed to is a broken sim — refuse loudly rather
            # than emit a lie.
            raise ValueError(f"subscribed parameter unreadable: {failure[1]}")
        sequence = subscription.next_sequence
        subscription.next_sequence = sequence + 1
        subscription.next_emit_s = now + subscription.min_interval_s
        return {
            "subscription_id": subscription_id,
            "sequence": sequence,
            "kind": "telemetry",
            "reading": reading,
        }

    # -- device semantics (the bridge's verb set) ---------------------------------

    def _identity_data(self) -> dict[str, Any]:
        return {
            "manufacturer": "benchweave-sim",
            "model": "sim-psu-1",
            "serial": "SIM-PSU-0001",
            "firmware": "sim-0.1.0",
            "source": "device",
        }

    def _reading_data(
        self, parameter: Any
    ) -> tuple[dict[str, Any] | None, tuple[str, str, str] | None]:
        """One reading as its wire dict, or a (code, message, state) failure."""
        if not isinstance(parameter, str):
            return None, ("INVALID_ARGUMENT", "read requires parameter", "not_dispatched")
        derived: dict[str, tuple[Any, str | None]] = {
            "output_voltage_v": (self._output_voltage(), "V"),
            "output_current_a": (self._output_current(), "A"),
            "output_power_w": (
                round(self._output_voltage() * self._output_current(), 6),
                "W",
            ),
            "identity_model": ("sim-psu-1", None),
        }
        value: Any
        unit: str | None = None
        if parameter in derived:
            value, unit = derived[parameter]
        elif parameter in self._state:
            value = self._state[parameter]
        else:
            return None, (
                "INVALID_ARGUMENT",
                f"unknown parameter {parameter}",
                "not_dispatched",
            )
        return (
            {
                "parameter": parameter,
                "value": value,
                "unit": unit,
                "observed_at": self._services.utc_now(),
                "age_ms": 0,
                "quality": "valid",
                "source": "device",
            },
            None,
        )

    def _write(
        self, parameter: Any, value: Any
    ) -> tuple[dict[str, Any] | None, tuple[str, str, str] | None]:
        """Apply one write through the sync core's bounds/trip rules; the
        receipt mirrors the core's (requested/effective/assurance with a
        readback verification for bounded parameters)."""
        if not isinstance(parameter, str) or value is None:
            return None, (
                "INVALID_ARGUMENT",
                "write requires parameter and value",
                "not_dispatched",
            )
        if parameter not in self._state:
            return None, (
                "INVALID_ARGUMENT",
                f"unknown parameter {parameter}",
                "not_dispatched",
            )
        if parameter in WRITABLE_BOUNDS and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            return None, ("INVALID_ARGUMENT", f"bad type for {parameter}", "not_dispatched")
        if parameter == "output_enabled" and not isinstance(value, bool):
            return None, (
                "INVALID_ARGUMENT",
                "output_enabled is boolean",
                "not_dispatched",
            )
        if parameter == "operator_note" and not isinstance(value, str):
            return None, (
                "INVALID_ARGUMENT",
                "operator_note is a string",
                "not_dispatched",
            )
        if self._tripped:
            return None, (
                "DEVICE_REJECTED",
                f"tripped ({self._tripped}); reset required",
                "dispatched",
            )
        if parameter in WRITABLE_BOUNDS:
            low, high = WRITABLE_BOUNDS[parameter]
            if not low <= value <= high:
                return None, (
                    "DEVICE_REJECTED",
                    f"{parameter} out of bounds [{low}, {high}]",
                    "dispatched",
                )
        self._state[parameter] = value
        trip = self._check_trips(parameter)
        if trip is not None:
            return None, (
                "DEVICE_REJECTED",
                f"write applied; protective trip: {trip}",
                "dispatched",
            )
        return (
            {
                "parameter": parameter,
                "requested_value": value,
                "effective_value": self._state[parameter],
                "assurance": "dispatched",
                "verification": self._reading_data(parameter)[0]
                if parameter in WRITABLE_BOUNDS
                else None,
            },
            None,
        )

    def _output_voltage(self) -> float:
        if self._tripped or not self._state["output_enabled"]:
            return 0.0
        return float(self._state["voltage_setpoint_v"])

    def _output_current(self) -> float:
        if self._tripped or not self._state["output_enabled"]:
            return 0.0
        return min(float(self._state["load_a"]), float(self._state["current_limit_a"]))

    def _check_trips(self, changed: str) -> str | None:
        enabled = self._state["output_enabled"]
        if (
            enabled
            and changed in ("voltage_setpoint_v", "ovp_threshold_v", "output_enabled")
            and float(self._state["voltage_setpoint_v"]) > float(self._state["ovp_threshold_v"])
        ):
            self._tripped = "OVP_TRIP"
            self._state["output_enabled"] = False
            return "OVP_TRIP"
        if (
            enabled
            and changed in ("load_a", "ocp_threshold_a", "output_enabled", "current_limit_a")
            and float(self._state["load_a"]) > float(self._state["ocp_threshold_a"])
        ):
            self._tripped = "OCP_TRIP"
            self._state["output_enabled"] = False
            return "OCP_TRIP"
        return None

    # -- stream verbs and wire envelopes ---------------------------------------------

    def _stream_verb(
        self, verb: str, operation_id: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        subscription_id = arguments.get("subscription_id")
        if verb == "stream_subscribe":
            parameters = arguments.get("parameters")
            interval = arguments.get("min_interval_ms")
            if (
                not isinstance(subscription_id, str)
                or not subscription_id
                or not isinstance(parameters, list)
                or len(parameters) != 1
                or not isinstance(parameters[0], str)
                or not isinstance(interval, int)
                or isinstance(interval, bool)
                or interval < 1
            ):
                return self._error(
                    operation_id,
                    verb,
                    ("INVALID_ARGUMENT", "malformed stream_subscribe arguments", "not_dispatched"),
                )
            # One parameter per subscription is the run-engine's declared
            # shape; a second would need multiplexed telemetry the demo
            # does not author.
            self._subscriptions[subscription_id] = _Subscription(
                parameters[0], interval, self._services.monotonic()
            )
        else:
            self._subscriptions.pop(subscription_id, None)
        return self._ok(operation_id, verb, {"subscription_id": subscription_id})

    def _ok(self, operation_id: str, verb: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"operation_id": operation_id, "verb": verb, "status": "ok", "data": data}

    def _error(
        self,
        operation_id: str,
        verb: str,
        failure: tuple[str, str, str],
    ) -> dict[str, Any]:
        code, message, dispatch_state = failure
        return {
            "operation_id": operation_id,
            "verb": verb,
            "status": "error",
            "error": {"code": code, "message": message, "dispatch_state": dispatch_state},
        }


def create_plugin() -> SimPsuStreamAdapter:
    """The OTDP ABI factory: zero arguments (the bundle loader's calling
    form), returning the bridge-leg adapter."""
    return SimPsuStreamAdapter()
