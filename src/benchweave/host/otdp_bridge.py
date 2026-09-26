"""Explicit OTDP 0.2.0/adapter API 1.1 compatibility for the synchronous host.

Identify, scalar read and scalar write are supported, plus single-channel
capture (the ``artifact_writer``-gated capture verb: staged appends, a
host-computed manifest, and an abort with a forensic record on failure),
streaming (the ``event_sink``-gated subscribe/unsubscribe verbs with
``next_event`` poll mediation: host-minted subscription ids, a normative
interval floor, validated events landed as ``event_log`` evidence, gap
annotations for unannounced sequence jumps, and host-cause teardown
markers on quota exhaustion, poison and close), and invoke (issue #146:
the pinned-contract lane — the descriptor's pinned catalog and
measurement schema resolve at load, the dispatch gates run before the
device, results validate against the action's pinned output schema, and
a dataset-shaped result that was not admitted through the dataset
services is a protocol lie from day one).
Dataset publishing/lookup and the payload services still need the
dataset-services slice; profile scheduling still needs a native async
host — for poll multiplexing across devices on one thread (subscriptions
on ONE bridge multiplex synchronously through the poll engine),
explicitly NOT for capture/stream correctness.
Services are
caller-supplied, including the SAME monotonic timebase used for host
deadlines (seconds versus nanoseconds). No transport provider is created.
Adapters are trusted Python, not sandboxed; deadlines require cooperative
async code. Each bridge owns one event loop and serialises its lifecycle
and dispatch. An uncertain failure poisons the session.

Capture budget: a capture dispatch's deadline is the step's ``timeout_ms``
clamped to the body deadline (``min(now + timeout_ms, body_deadline)``,
shortened only — no new budget mechanism). The asyncio timeout is the
detection bound for yielding adapters; blocking SQLite cannot be
interrupted by it, so the whole capture dispatch runs inside a
deadline-aware busy-timeout clamp (issue #176 row B): the store's
``busy_timeout`` is set, for the dispatch only, to
``min(open busy_timeout, REMAINING DEADLINE AT BRACKET ENTRY)`` and
restored on every exit path. ENTRY-TIME-REMAINING semantics, stated
exactly: the clamp bounds the wait to the remaining budget computed at
bracket entry; pre-BEGIN time inside the bracket (the gate reserve, the
envelope deepcopy, the adapter execute — the common mid-capture shape
consumes budget the clamp never sees) widens the possible busy-wait
overshoot past the step deadline by that amount. Not a regression: the
static open-time default it replaced was strictly worse. Per-BEGIN
re-derivation is deferred (the design record's final-fold deferral
row). The abort epilogue runs under its OWN bounded floor
(``min(CAPTURE_EPILOGUE_FLOOR_MS, the open busy_timeout)``) so a
clamped-out capture still reclaims its staging rows; ``sweep_open``,
``plugin_close`` and the startup reclaim stay unclamped. A clamped-out
BEGIN fails as the same classified RESOURCE_LIMIT (the writer-stamp
discipline); the session survives.
"""

from __future__ import annotations

import asyncio
import copy
import json
import math
import re
import sqlite3
import threading
from collections.abc import Awaitable, Callable
from contextlib import ExitStack, suppress
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator

from benchweave.content.capture_services import evidence_originated
from benchweave.content.capture_store import writer_originated
from benchweave.content.dataset_services import (
    dataset_evidence_originated,
)
from benchweave.content.store import EvidenceQuotaExceeded
from benchweave.content.stream_services import (
    LandedEvent,
    StreamLimitExceeded,
    landing_originated,
)
from benchweave.host.plugin import SimulationInfo
from benchweave.host.types import (
    Assurance,
    CaptureFinaliseRejected,
    CaptureQuotaExceeded,
    DispatchState,
    ErrorCode,
    Identity,
    IdentitySource,
    OperationError,
    OperationRequest,
    OperationResult,
    OperationStatus,
    Quality,
    Reading,
    ReadingSource,
    WriteReceipt,
)


def canonical_json(value: Any) -> str:
    """Canonical JSON text for the invoke dataset cross-check's byte
    equality (sorted keys, tight separators — the manifest-bytes
    discipline)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class _Context:
    def __init__(self, operation_id: str, deadline: float, services: Any) -> None:
        self.operation_id = operation_id
        self.dataset_id = None
        self.deadline_monotonic = deadline
        self.services = services
        self.dispatched = False
        self.cancelled = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    async def mark_dispatch_started(self) -> None:
        if self.cancelled or self.services.monotonic() >= self.deadline_monotonic:
            raise TimeoutError("dispatch deadline expired")
        self.dispatched = True


class InvalidEvent(ValueError):
    """The event validator's refusal channel: the closed ``$defs/event``
    (or its reading subschema, or event-level JSON serializability) did
    not hold. A subclass of ValueError so existing ValueError handling is
    unchanged; poll_event maps it to the PROTOCOL_ERROR poison posture
    WITH the validator's message — the honest invalid-event class, never
    the generic failed-or-late wording (G1/G3, Forge wave)."""


class InvalidInvokeResult(ValueError):
    """The invoke result validator's refusal channel (issue #146 R6, the
    InvalidEvent discipline): the closed ``{action_id, result}`` data
    branch, the action's pinned output schema, or the dataset-publication
    cross-check did not hold. dispatch maps it to the PROTOCOL_ERROR
    poison posture WITH the specific refusal — the honest invalid-result
    class, never the generic failed-or-late wording."""


@dataclass(frozen=True)
class PollOutcome:
    """One ``next_event`` poll's honest outcome — the mediation shape the
    poll engine consumes. The outcome families:

    * ``event`` set (all else clear): one validated event (Decision 4's
      landing contract already landed) with the host's ``host_received_at``
      receipt stamp.
    * all fields clear: a quiet stream (the adapter returned None — no
      error, no landing; spec §8 raises no timeout error for a healthy
      quiet stream).
    * ``refusal`` alone: a clean typed refusal — unknown or ended
      subscription (INVALID_ARGUMENT not_dispatched), no stream controller
      (UNSUPPORTED), an expired poll deadline (TIMEOUT not_dispatched), or
      quota exhaustion at the landing boundary (RESOURCE_LIMIT dispatched,
      with the subscription torn down — never session poison).
    * ``refusal`` together with ``session_failed``: this bridge will do no
      further work — the adapter lied, hung or returned an invalid event
      (poison: the registry is cleared with host-cause ended markers), or
      the bridge was never opened or already closed (no session failure
      occurred, but no work is possible either — every later poll and
      dispatch refuses all the same).
    """

    event: dict[str, Any] | None = None
    host_received_at: str | None = None
    refusal: OperationError | None = None
    session_failed: bool = False


class OTDPBridge:
    """An unopened DevicePlugin wrapping an async adapter with explicit authority."""

    def __init__(
        self,
        adapter: Any,
        *,
        descriptor: dict[str, Any],
        services: Any,
        simulation: SimulationInfo,
        lifecycle_timeout: float = 5.0,
        capture: Any = None,
        stream: Any = None,
        dataset: Any = None,
    ) -> None:
        if not isinstance(simulation, SimulationInfo):
            raise TypeError("explicit SimulationInfo required")
        if not callable(getattr(services, "monotonic", None)):
            raise TypeError("scoped OTDP services with monotonic() required")
        if not math.isfinite(lifecycle_timeout) or lifecycle_timeout <= 0:
            raise ValueError("lifecycle_timeout must be finite and positive")
        self._adapter = adapter
        self._descriptor = copy.deepcopy(descriptor)
        self._services = services
        # §0.3: capture and streaming control flow ONLY through these
        # controller objects, never through self._services (the pinned
        # exercised services subset stays {monotonic} — the streaming slice
        # landed the stream controller beside the capture one; neither
        # touches the services members). None = the session was constructed
        # without the artifact_writer / event_sink permission respectively.
        self._capture = capture
        self._stream = stream
        # The same §0.3 posture for the invoke/dataset lane (issue #146):
        # the controller exists iff the descriptor declares the invoke
        # capability AND §2.1's resolution produced the complete
        # catalog+measurement pair — None is structural (verb-level
        # UNSUPPORTED at the invoke gate), never a runtime flag.
        self._dataset = dataset
        self._simulation = simulation
        self._lifecycle_timeout = lifecycle_timeout
        self._runner: asyncio.Runner | None = None
        self._lock = threading.RLock()
        self._opened = False
        self._closed = False
        self._failed = False
        # Gate I5's compiled descriptor input_constraints, lazily cached per
        # action (the documents.py lazy-singleton precedent — compiled once
        # per bridge, on first use).
        self._invoke_constraints: dict[str, Any] = {}
        self._release_loader: Callable[[], None] = lambda: None

    @property
    def simulation(self) -> SimulationInfo:
        return self._simulation

    def _context(self) -> _Context:
        return _Context(
            str(uuid4()),
            self._services.monotonic() + self._lifecycle_timeout,
            self._services,
        )

    def _run(self, awaitable: Awaitable[Any], context: _Context) -> Any:
        async def bounded() -> Any:
            try:
                remaining = context.deadline_monotonic - self._services.monotonic()
                async with asyncio.timeout(max(0, remaining)):
                    result = await awaitable
                if self._services.monotonic() >= context.deadline_monotonic:
                    raise TimeoutError("late adapter result")
                return result
            except BaseException:
                context.cancelled = True
                raise

        if self._runner is None:
            # Survives python -O: the bridge must never run an operation
            # without its owning runner.
            raise RuntimeError("bridge invariant violated: no runner bound")
        return self._runner.run(bounded())

    @staticmethod
    def _require_sync() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError("OTDPBridge requires a synchronous calling thread")

    def plugin_open(self, services: Any) -> None:
        """Open using the scoped OTDP services supplied at construction."""
        self._require_sync()
        with self._lock:
            if self._opened or self._closed:
                raise RuntimeError("bridge cannot be reopened")
            self._runner = asyncio.Runner()
            try:
                context = self._context()
                self._run(
                    self._adapter.open(copy.deepcopy(self._descriptor), self._services, context),
                    context,
                )
                self._opened = True
            except BaseException:
                # Preserve the original failure, including after partial acquisition.
                with suppress(BaseException):
                    context = self._context()
                    self._run(self._adapter.close(context), context)
                self._runner.close()
                self._closed = True
                self._release_loader()
                raise

    def plugin_close(self) -> None:
        self._require_sync()
        with self._lock:
            if self._closed:
                return
            try:
                if self._runner is not None:
                    context = self._context()
                    self._run(self._adapter.close(context), context)
            finally:
                # The adapter's own cooperative cleanup ran first (above);
                # this is the host-side guarantee for anything still open —
                # abort's no-op-retract makes the double call safe.
                if self._capture is not None:
                    with suppress(Exception):
                        self._capture.sweep_open(reason="plugin_close")
                if self._stream is not None:
                    # No stream outlives its host-owned subscription
                    # authority: close tears down every live subscription
                    # with a host-cause ended marker (§7/§8).
                    with suppress(Exception):
                        self._stream.sweep(reason="plugin_close")
                if self._dataset is not None:
                    # plugin_close sweeps still-open payloads (issue #146
                    # §2.3); slice 2 has no openable payloads — the
                    # controller's sweep is empty until the payload
                    # services land, and the hook rides now so the close
                    # path needs no second change when they do.
                    with suppress(Exception):
                        self._dataset.sweep_open(reason="plugin_close")
                self._closed = True
                self._opened = False
                try:
                    if self._runner is not None:
                        self._runner.close()
                finally:
                    self._release_loader()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        self._require_sync()
        with self._lock:

            def reject(code: ErrorCode, message: str) -> OperationResult:
                return OperationResult.failure(
                    request.operation_id,
                    request.verb,
                    code=code,
                    message=message,
                    dispatch_state=DispatchState.NOT_DISPATCHED,
                )

            if not self._opened or self._closed or self._failed:
                return reject(ErrorCode.INTERNAL_ERROR, "A fresh opened bridge is required")
            supported = {
                "identify": set(),
                "read": {"parameter"},
                "write": {"parameter", "value"},
                "capture": {"capture_id", "format", "sample_count", "max_bytes"},
                "stream_subscribe": {"subscription_id", "parameters", "min_interval_ms"},
                "stream_unsubscribe": {"subscription_id"},
                "invoke": {"action_id", "input"},
            }
            expected = supported.get(request.verb.value)
            if expected is None:
                return reject(
                    ErrorCode.UNSUPPORTED,
                    "Bridge supports identify, read, write, capture, stream and "
                    "invoke verbs",
                )
            if set(request.arguments) != expected:
                return reject(ErrorCode.UNSUPPORTED, "Unsupported arguments for bridge operation")
            try:
                deadline = deadline_ns / 1_000_000_000
            except OverflowError:
                # F7's belt at the bridge: a deadline_ns no float can
                # represent converts to a typed reject — a raw
                # OverflowError can never escape dispatch(). The contract
                # ceiling keeps schema-valid timeout_ms far from this; the
                # guard keeps it structurally unreachable as an escape.
                return reject(
                    ErrorCode.INTERNAL_ERROR,
                    f"operation deadline {deadline_ns} ns is not representable "
                    "as seconds",
                )
            if not math.isfinite(deadline) or self._services.monotonic() >= deadline:
                return reject(ErrorCode.TIMEOUT, "Operation deadline expired")
            with ExitStack() as clamp_stack:
                if request.verb.value == "capture" and self._capture is not None:
                    # Issue #176 row B: the deadline-aware busy-timeout
                    # clamp brackets the WHOLE capture dispatch — gate
                    # region, adapter execute, appends/finalise and the
                    # classified-failure epilogue. The remaining-deadline
                    # arithmetic runs here, on the injected monotonic
                    # (STO-1: the store only sets what it is handed).
                    clamp_stack.enter_context(
                        self._capture.dispatch_clamp(
                            deadline_ns,
                            now_ns=int(self._services.monotonic() * 1_000_000_000),
                        )
                    )
                if request.verb.value == "invoke" and self._dataset is not None:
                    # The same row-B bracket extends to invoke (issue #146
                    # §2.3) when the controller exists: store writes an
                    # adapter performs during execute — evidence rows now,
                    # payload appends once the dataset services land — hit
                    # the same single-writer store a capture's appends do.
                    # Entry-time-remaining semantics and the disclosed
                    # overshoot apply unchanged.
                    clamp_stack.enter_context(
                        self._dataset.dispatch_clamp(
                            deadline_ns,
                            now_ns=int(self._services.monotonic() * 1_000_000_000),
                        )
                    )
                capture_id: str | None = None
                if request.verb.value == "capture":
                    gate = self._capture_gate(request)
                    if isinstance(gate, OperationResult):
                        return gate
                    capture_id = gate
                subscription_id: str | None = None
                if request.verb.value == "stream_subscribe":
                    gate = self._subscribe_gate(request)
                    if isinstance(gate, OperationResult):
                        return gate
                    subscription_id = gate
                elif request.verb.value == "stream_unsubscribe":
                    preflight = self._unsubscribe_preflight(request)
                    if preflight is not None:
                        return preflight
                    subscription_id = str(request.arguments["subscription_id"])
                if request.verb.value == "invoke":
                    invoke_gate = self._invoke_gate(request)
                    if invoke_gate is not None:
                        return invoke_gate
                context = _Context(request.operation_id, deadline, self._services)
                if request.verb.value == "invoke" and self._dataset is not None:
                    # Gate I6: the host mints the dataset id — unique per
                    # dispatch (operation ids key on occurrence ids and
                    # recovered steps never re-dispatch, so replay cannot
                    # collide it; design §2.3), and the adapter never
                    # chooses it. The dispatch's action id and RESOLVED input
                    # ride the per-operation state for the publish path's
                    # M10-correlation cross-check (design §2.2).
                    context.dataset_id = self._dataset.mint_dataset_id(
                        request.operation_id,
                        action_id=request.arguments.get("action_id")
                        if isinstance(request.arguments.get("action_id"), str)
                        else None,
                        input=request.arguments.get("input")
                        if isinstance(request.arguments.get("input"), dict)
                        else None,
                    )
                envelope = {
                    "operation_id": request.operation_id,
                    "verb": request.verb.value,
                    "arguments": copy.deepcopy(request.arguments),
                }

                def poison(exc: BaseException, message: str | None = None) -> OperationResult:
                    self._failed = True
                    return OperationResult.indeterminate(
                        request.operation_id,
                        request.verb,
                        code=ErrorCode.TIMEOUT
                        if isinstance(exc, TimeoutError)
                        else ErrorCode.PROTOCOL_ERROR,
                        message=message
                        if message is not None
                        else "Invalid, failed or late adapter result; no replay",
                    )

                try:
                    result = self._run(self._adapter.execute(envelope, context), context)
                    converted = self._convert(request, result, context)
                    if capture_id is not None and self._capture is not None:
                        # Success: retire the capture — no epilogue, no forensic
                        # record; a published, acknowledged capture stands.
                        self._capture.retire(capture_id)
                    if subscription_id is not None and self._stream is not None:
                        if converted.status is OperationStatus.OK:
                            # A successful unsubscribe closes the subscription
                            # (no marker — the unsubscribe result is the record);
                            # a successful subscribe keeps the reservation live.
                            if request.verb.value == "stream_unsubscribe":
                                self._stream.mark_closed(subscription_id)
                        elif request.verb.value == "stream_subscribe":
                            # The subscription did not establish: release the
                            # reservation (nothing streamed, no marker).
                            self._stream.release(subscription_id)
                    if self._failed:
                        # Poison by result (an error envelope claiming dispatch
                        # or unknown): clear the registry — a poisoned session
                        # cannot leak live subscriptions until close.
                        self._stream_clear()
                    return converted
                except InvalidInvokeResult as exc:
                    # R6's honest invalid-result class (the InvalidEvent
                    # precedent): the invoke conversion's own refusal —
                    # envelope shape, the pinned output schema, or the
                    # dataset-publication cross-check — poisons WITH its
                    # specific message, never the generic wording.
                    self._stream_clear()
                    return poison(exc, message=f"invalid invoke result: {exc}")
                except (
                    CaptureQuotaExceeded,
                    EvidenceQuotaExceeded,
                    sqlite3.OperationalError,
                ) as exc:
                    # Writer/bundle-originated resource conditions only: the
                    # discriminator requires module-token identity AND binding to
                    # THIS dispatch (C3 as amended) — a bare raise, a forged
                    # attribute, or a genuine saved instance replayed on another
                    # dispatch keeps the poison posture. In-process forgery of the
                    # private tokens remains possible: adapters are trusted
                    # Python (the module docstring's boundary); the stamp
                    # separates accidental collision from origin, it does not
                    # prove origin against deliberate hostility. The dataset
                    # lane's payload arm joins the discriminator with the
                    # dataset services (issue #146 slice 3 — the writer's
                    # payload-stamp registry); the classification here is
                    # DELIBERATE for invoke, not incidental class overlap:
                    # slice 2's only invoke-classifiable origin is the
                    # evidence arm, operation-bound.
                    if not self._capture_originated(exc, capture_id, request):
                        if capture_id is not None:
                            self._abort_contained(capture_id, request.operation_id)
                        self._stream_clear()
                        return poison(exc)
                    self._abort_contained(capture_id, request.operation_id)
                    if (
                        subscription_id is not None
                        and self._stream is not None
                        and request.verb.value == "stream_subscribe"
                    ):
                        # The dispatch failed without poisoning the session: the
                        # reservation it held is released (nothing streamed). An
                        # unsubscribe failure keeps its subscription live.
                        self._stream.release(subscription_id)
                    # R17 (issue #146, lane-honest refusal prose): the
                    # classified refusal names the lane that classified it.
                    # Capture dispatches keep the exact historical message;
                    # an invoke-classified refusal names the invoke lane and
                    # its origin — never capture wording. The payload lane's
                    # classification (R10's clean direction) also reclaims
                    # the operation's still-open payloads — the session
                    # survives the resource condition (A6/A7 posture,
                    # identical to captures' abort epilogue, minus the
                    # forensic row per the corpus §3).
                    if request.verb.value == "invoke":
                        lane = "evidence" if isinstance(exc, EvidenceQuotaExceeded) else "payload"
                        if self._dataset is not None:
                            # Wave 2 #3: the reclaim rides the epilogue
                            # floor (the _abort_contained precedent — the
                            # floor rode with it). Bare, it inherits the
                            # dispatch clamp's remaining budget (≈0 on a
                            # clamped-out dispatch) and reclaims nothing
                            # until the close sweep; under the floor it
                            # waits bounded and reclaims now. Contained:
                            # a reclaim failure never replaces the refusal.
                            with suppress(Exception), self._dataset.epilogue_floor():
                                self._dataset.abort_open(request.operation_id)
                        refusal_message = (
                            f"invoke resource condition ({lane}): {exc}"
                        )
                    else:
                        refusal_message = f"Capture resource condition: {exc}"
                    return OperationResult.failure(
                        request.operation_id,
                        request.verb,
                        code=ErrorCode.RESOURCE_LIMIT,
                        message=refusal_message,
                        # A7: every refusal raised after execute entry is
                        # dispatched — never not_dispatched, and the session
                        # survives (no poison).
                        dispatch_state=DispatchState.DISPATCHED,
                    )
                except (Exception, asyncio.CancelledError) as exc:
                    if capture_id is not None:
                        self._abort_contained(capture_id, request.operation_id)
                    self._stream_clear()
                    return poison(exc)

    # The interoperable integer range (spec §4): values outside −(2^53−1)
    # through 2^53−1 are unsupported by the numeric interface — also the
    # structural sqlite-bind safety bound.
    _INT_MAX = 2**53 - 1
    # The contract id class (interface.schema.json's ^[a-z][a-z0-9_.-]*$)
    # with ':' admitted: the procedure executor's host-minted capture ids
    # are `cap:{run_id}:{step_id}{.index-suffix}` (mirroring op: ids —
    # #176 increment 2), and colons are the only separator the minting
    # precedent uses. Every other refusal the shape test parametrizes
    # (uppercase, digit-start, slash, traversal, empty) still refuses.
    _CAPTURE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_.:-]*")
    _STREAM_PARAMETER_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
    _CAPTURE_FORMATS = ("waveform_f64le", "raw_binary")

    def _capture_gate(self, request: OperationRequest) -> str | OperationResult:
        """The pre-dispatch capture gates (R1: bounds before the device).

        Every refusal is a clean typed rejection with zero adapter calls;
        the gate region has no exception frame, so descriptor limits are
        type-validated here rather than trusted — a malformed descriptor
        yields INVALID_ARGUMENT, never an escaping exception.
        """
        arguments = request.arguments
        if self._capture is None:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.UNSUPPORTED,
                message="capture requires artifact_writer permission",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        capture_id = arguments.get("capture_id")
        if not isinstance(capture_id, str) or not self._CAPTURE_ID_PATTERN.fullmatch(
            capture_id
        ):
            return self._invalid(request, "capture_id must match the contract id shape")
        # A5: exact-type ints (bool rejected — the _reading precedent) and
        # the spec §4 interoperable bound, which keeps the sqlite bind
        # structurally safe.
        count = self._exact_int(arguments.get("sample_count"))
        byte_cap = self._exact_int(arguments.get("max_bytes"))
        if count is None or byte_cap is None:
            return self._invalid(
                request, "sample_count and max_bytes must be integers in [1, 2^53-1]"
            )
        if not (1 <= count <= self._INT_MAX) or not (1 <= byte_cap <= self._INT_MAX):
            return self._invalid(
                request, "sample_count and max_bytes must be integers in [1, 2^53-1]"
            )
        fmt = arguments.get("format")
        if fmt not in self._CAPTURE_FORMATS:
            return self._invalid(request, "format must be waveform_f64le or raw_binary")
        # G1 arithmetic: the request's own numbers must agree (spec §7:
        # byte length equals sample_count×8).
        if fmt == "waveform_f64le" and count * 8 > byte_cap:
            return self._invalid(
                request,
                f"waveform_f64le sample_count {count} needs "
                f"{count * 8} bytes, above the declared max_bytes {byte_cap}",
            )
        # G2 descriptor: limits read with type validation — malformed
        # limits are a clean refusal, never an exception.
        limits = self._descriptor.get("capture_limits")
        if not isinstance(limits, dict):
            return self._invalid(request, "descriptor capture_limits must be an object")
        limit_samples = self._exact_int(limits.get("max_samples"))
        limit_bytes = self._exact_int(limits.get("max_bytes"))
        if limit_samples is None or limit_samples < 1:
            return self._invalid(
                request, "descriptor capture_limits.max_samples must be an integer >= 1"
            )
        if limit_bytes is None or limit_bytes < 1:
            return self._invalid(
                request, "descriptor capture_limits.max_bytes must be an integer >= 1"
            )
        if count > limit_samples:
            return self._invalid(
                request,
                f"sample_count {count} exceeds descriptor max_samples {limit_samples}",
            )
        if byte_cap > limit_bytes:
            return self._invalid(
                request,
                f"max_bytes {byte_cap} exceeds descriptor max_bytes {limit_bytes}",
            )
        formats = self._descriptor.get("capture_formats")
        if not isinstance(formats, list) or fmt not in formats:
            return self._invalid(
                request, f"format {fmt!r} is not among the descriptor capture_formats"
            )
        # G3 quota: check-and-reserve in its own local frame (A6) — a quota
        # refusal is RESOURCE_LIMIT not_dispatched; any other store failure
        # is INTERNAL_ERROR not_dispatched. Nothing was opened in either
        # case, so no epilogue runs (zero forensic rows on gate refusals).
        try:
            self._capture.open_capture(
                capture_id=capture_id,
                fmt=fmt,
                sample_count=count,
                max_bytes=byte_cap,
            )
        except CaptureQuotaExceeded as exc:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.RESOURCE_LIMIT,
                message=f"capture allowance exceeded: {exc}",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        except CaptureFinaliseRejected as exc:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.INVALID_ARGUMENT,
                message=f"capture id refused: {exc}",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        except sqlite3.OperationalError as exc:
            # F6: a writer-originated OperationalError at the gate (lock
            # contention on open_capture's BEGIN) is the SAME resource
            # condition C5 names mid-capture — RESOURCE_LIMIT, not
            # INTERNAL_ERROR — verified by the identity+binding stamp.
            # Nothing was opened, so A6's no-epilogue rule still holds.
            if writer_originated(exc, capture_id):
                return OperationResult.failure(
                    request.operation_id,
                    request.verb,
                    code=ErrorCode.RESOURCE_LIMIT,
                    message=f"capture open contended: {exc}",
                    dispatch_state=DispatchState.NOT_DISPATCHED,
                )
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.INTERNAL_ERROR,
                message=f"capture open failed: {exc}",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        except Exception as exc:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.INTERNAL_ERROR,
                message=f"capture open failed: {exc}",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        return capture_id

    def _invoke_gate(self, request: OperationRequest) -> OperationResult | None:
        """The pre-dispatch invoke gates I1–I5 (issue #146 §2.3; R1: bounds
        before the device).

        I1 capability: controller existence IS the capability — the loader
        constructs one iff the descriptor declares invoke AND §2.1's
        resolution produced the complete catalog+measurement pair (the
        soft both-or-neither arm lands here as UNSUPPORTED). I2 declared
        action (defense in depth under binding's admission refusal — the
        bridge reads the raw descriptor it deep-copied at construction).
        I3 catalog resolution (M14: an unknown contract is never opaque
        success). I4 the pinned catalog's input schema — the RESOLVED
        input, post-CTL-6, the only place a $stg_ref-resolved value can be
        schema-checked. I5 the descriptor action's own input_constraints
        narrowing (the policy-rule intersection already ran at the
        executor). Every refusal is a clean typed rejection with zero
        adapter calls; the gate region has no exception frame, so the
        validators' lazy reference resolution is guaranteed by the
        load-time probes — every $ref and $dynamicRef in every compiled
        schema, rooted at the per-action subschema these validators
        actually validate against, resolves in-bundle, and the
        descriptor's input_constraints are probed the same way at load
        (item 8) — never caught here.
        """
        if self._dataset is None:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.UNSUPPORTED,
                message=(
                    "invoke requires the pinned contract set (catalog and "
                    "measurement schema) resolved at load"
                ),
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        arguments = request.arguments
        action_id = arguments.get("action_id")
        if not isinstance(action_id, str) or not action_id:
            return self._invalid(request, "action_id must be a non-empty string")
        declared = self._descriptor.get("actions")
        if not isinstance(declared, dict) or action_id not in declared:
            return self._invalid(
                request,
                f"action {action_id!r} is not declared by the descriptor actions map",
            )
        action = self._dataset.actions.get(action_id)
        if action is None:
            return self._invalid(
                request,
                f"action {action_id!r} does not resolve in the pinned profile "
                "catalog (M14)",
            )
        value = arguments.get("input")
        if not isinstance(value, dict):
            return self._invalid(request, "input must be an object")
        error = next(iter(action.input_validator.iter_errors(value)), None)
        if error is not None:
            return self._invalid(
                request,
                f"input violates the action's catalog input schema at "
                f"{error.json_path}: {error.message}",
            )
        constraints = self._invoke_constraints_validator(action_id, declared[action_id])
        if constraints is not None:
            error = next(iter(constraints.iter_errors(value)), None)
            if error is not None:
                return self._invalid(
                    request,
                    f"input violates the descriptor action's input_constraints at "
                    f"{error.json_path}: {error.message}",
                )
        return None

    def _invoke_constraints_validator(
        self, action_id: str, declaration: Any
    ) -> Any | None:
        """The descriptor action's ``input_constraints`` validator, compiled
        once per bridge and cached (I5)."""
        if not isinstance(declaration, dict):
            return None
        constraints = declaration.get("input_constraints")
        if not isinstance(constraints, dict):
            return None
        validator = self._invoke_constraints.get(action_id)
        if validator is None:
            validator = Draft202012Validator(constraints)
            self._invoke_constraints[action_id] = validator
        return validator

    def _subscribe_gate(self, request: OperationRequest) -> str | OperationResult:
        """The pre-dispatch stream_subscribe gates (the _capture_gate mirror).

        Permission first (no event_sink -> no event services at all), then
        exact-typed argument shapes (the corpus $defs/operationRequest
        stream_subscribe branch), then the descriptor's ``stream_limits`` —
        ``min_interval_ms`` is a NORMATIVE FLOOR (spec §7: requested
        intervals cannot be shorter — refused, never clamped) and
        ``max_subscriptions`` caps admitted live subscriptions — then the
        host ceiling via the controller's check-and-reserve. Every refusal
        is a clean typed rejection with zero adapter calls; the gate region
        has no exception frame, so malformed descriptor limits are
        type-validated here rather than trusted.
        """
        if self._stream is None:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.UNSUPPORTED,
                message="stream_subscribe requires event_sink permission",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        arguments = request.arguments
        subscription_id = arguments.get("subscription_id")
        if not isinstance(subscription_id, str) or not subscription_id:
            return self._invalid(
                request, "subscription_id must be a non-empty string (a host-minted opaque)"
            )
        parameters = arguments.get("parameters")
        if not isinstance(parameters, list) or not parameters:
            return self._invalid(request, "parameters must be a non-empty list")
        if any(
            not isinstance(parameter, str)
            or not self._STREAM_PARAMETER_PATTERN.fullmatch(parameter)
            for parameter in parameters
        ):
            return self._invalid(
                request, "each parameter must match ^[a-z][a-z0-9_]*$ (the corpus pattern)"
            )
        if len(set(parameters)) != len(parameters):
            return self._invalid(request, "parameters must be unique (uniqueItems)")
        interval = self._exact_int(arguments.get("min_interval_ms"))
        if interval is None or interval < 1:
            return self._invalid(
                request, "min_interval_ms must be an integer >= 1 (the corpus minimum)"
            )
        # G2 descriptor: stream_limits read with type validation — malformed
        # limits are a clean refusal, never an exception (the capture
        # gate's discipline, applied to the stream limits).
        limits = self._descriptor.get("stream_limits")
        if not isinstance(limits, dict):
            return self._invalid(request, "descriptor stream_limits must be an object")
        floor = self._exact_int(limits.get("min_interval_ms"))
        if floor is None or floor < 1:
            return self._invalid(
                request, "descriptor stream_limits.min_interval_ms must be an integer >= 1"
            )
        limit_count = self._exact_int(limits.get("max_subscriptions"))
        if limit_count is None or limit_count < 1:
            return self._invalid(
                request, "descriptor stream_limits.max_subscriptions must be an integer >= 1"
            )
        if interval < floor:
            return self._invalid(
                request,
                f"requested min_interval_ms {interval} is shorter than the descriptor "
                f"floor {floor} (spec §7: requested intervals cannot be shorter)",
            )
        if len(self._stream.live_subscription_ids()) + 1 > limit_count:
            return self._invalid(
                request,
                "admitted subscription count cannot exceed the descriptor limit "
                f"{limit_count} (spec §7)",
            )
        # The host ceiling: check-and-reserve against QuotaLimits
        # .max_subscriptions (an author-claimed value alone would allow
        # unbounded bridge state growth).
        try:
            self._stream.reserve(
                subscription_id=subscription_id,
                parameters=tuple(str(parameter) for parameter in parameters),
                min_interval_ms=interval,
            )
        except StreamLimitExceeded as exc:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.RESOURCE_LIMIT,
                message=f"host subscription ceiling reached: {exc}",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        except ValueError as exc:
            return self._invalid(request, f"subscription refused: {exc}")
        return subscription_id

    def _unsubscribe_preflight(self, request: OperationRequest) -> OperationResult | None:
        """The stream_unsubscribe host-side preflight.

        None = proceed to the adapter (an active subscription). An
        OperationResult is a terminal host answer with ZERO adapter calls:
        UNSUPPORTED without event_sink, INVALID_ARGUMENT for an unknown id
        (spec §7: unknown subscriptions are rejected by the host), or the
        idempotent OK for a known terminal subscription (already closed or
        ended — §7: "idempotent for an already-closed known subscription";
        the host already knows it is done, so no re-dispatch).
        """
        if self._stream is None:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.UNSUPPORTED,
                message="stream_unsubscribe requires event_sink permission",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        subscription_id = request.arguments.get("subscription_id")
        if not isinstance(subscription_id, str) or not subscription_id:
            return self._invalid(request, "subscription_id must be a non-empty string")
        if not self._stream.is_known(subscription_id):
            return self._invalid(
                request,
                f"unknown subscription {subscription_id!r}: rejected by the host (spec §7)",
            )
        if not self._stream.is_live(subscription_id):
            return OperationResult.ok(
                request.operation_id, request.verb, {"subscription_id": subscription_id}
            )
        return None

    def _stream_clear(self) -> None:
        """Poison clears the subscription registry (Decision 4): every live
        subscription tears down with a host-cause ``ended`` marker, so a
        poisoned session cannot leak live subscriptions until close. Fully
        contained like the abort epilogue — never replaces the result being
        returned."""
        if self._stream is None:
            return
        with suppress(Exception):
            self._stream.sweep(reason="session poisoned")

    # The closed event vocabulary ($defs/event) and its key set: the
    # x-extension pattern is schema-legal, everything else additional.
    _EVENT_KINDS = ("telemetry", "alarm", "gap", "ended")
    _EVENT_KEYS = frozenset({"subscription_id", "sequence", "kind", "reading", "code", "message"})
    _READING_KEYS = frozenset(
        {"parameter", "value", "unit", "observed_at", "age_ms", "quality", "source"}
    )
    _X_KEY_PATTERN = re.compile(r"x-[a-z0-9]+-[a-z0-9_-]+")

    def poll_event(self, subscription_id: str, *, deadline_ns: int) -> PollOutcome:
        """Mediate one host-driven ``next_event`` poll (spec §8: host-driven,
        one event or None, no hidden background task, a bounded polling
        budget — the deadline the poll engine slices).

        The refusal taxonomy is Decision 4's: unknown or ended subscription
        -> clean INVALID_ARGUMENT not_dispatched (zero adapter calls); quota
        exhaustion at the landing boundary -> clean RESOURCE_LIMIT dispatched
        plus teardown with a host-cause ended marker, never session poison;
        every protocol lie (non-schema event, wrong subscription id,
        non-increasing sequence, an event after ended) poisons and clears
        the registry.
        """
        self._require_sync()
        with self._lock:
            if not self._opened or self._closed or self._failed:
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.INTERNAL_ERROR,
                        "A fresh opened bridge is required",
                        DispatchState.NOT_DISPATCHED,
                    ),
                    session_failed=True,
                )
            if self._stream is None:
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.UNSUPPORTED,
                        "stream polling requires event_sink permission",
                        DispatchState.NOT_DISPATCHED,
                    )
                )
            if not self._stream.is_known(subscription_id):
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"unknown subscription {subscription_id!r}",
                        DispatchState.NOT_DISPATCHED,
                    )
                )
            if not self._stream.is_live(subscription_id):
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"subscription {subscription_id!r} is already ended or closed",
                        DispatchState.NOT_DISPATCHED,
                    )
                )
            deadline = deadline_ns / 1_000_000_000
            if not math.isfinite(deadline) or self._services.monotonic() >= deadline:
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.TIMEOUT,
                        "poll deadline expired",
                        DispatchState.NOT_DISPATCHED,
                    )
                )
            state = self._stream.subscription(subscription_id)
            if state is None:  # defensive: is_live just proved otherwise
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.INTERNAL_ERROR,
                        "registry invariant violated",
                        DispatchState.NOT_DISPATCHED,
                    )
                )
            context = _Context(str(uuid4()), deadline, self._services)
            sequence: int | None = None
            try:
                event = self._run(
                    self._adapter.next_event(subscription_id, context), context
                )
                if event is None:
                    # A healthy quiet stream produced no data — no error
                    # (spec §8), no landing, no state change.
                    return PollOutcome()
                validated = self._validate_event(
                    subscription_id,
                    event,
                    last_sequence=state.last_sequence,
                    last_kind=state.last_kind,
                )
                receipt = self._stream.now_iso()
                sequence = int(validated["sequence"])
                kind = str(validated["kind"])
                # Gap honesty (R4's host mechanism): a forward jump the
                # stream did not preface with a gap event is recorded, not
                # silently accepted as contiguous — including a first event
                # that did not start at zero (§7: sequence starts at zero).
                if state.last_sequence is None:
                    if sequence > 0:
                        self._stream.note_sequence_jump(
                            subscription_id, from_sequence=None, to_sequence=sequence
                        )
                elif sequence > state.last_sequence + 1 and state.last_kind != "gap":
                    self._stream.note_sequence_jump(
                        subscription_id,
                        from_sequence=state.last_sequence,
                        to_sequence=sequence,
                    )
                self._stream.record_event(subscription_id, sequence=sequence, kind=kind)
                # land_events' max_event_batch bound is a host-contract
                # check (the bridge always presents single-event batches);
                # a ValueError from it is a host bug surfacing through the
                # poison channel below — disclosed, not classified.
                self._stream.land_events([LandedEvent(validated, receipt)])
                return PollOutcome(event=validated, host_received_at=receipt)
            except EvidenceQuotaExceeded as exc:
                # Quota exhaustion at a landing boundary: a resource
                # condition, not a protocol lie — clean refusal plus
                # teardown with a host-cause ended marker, never poison.
                # The discriminator (F2, review wave): only a LANDING-
                # originated refusal (token identity + subscription
                # binding) classifies; a bare or replayed raise keeps the
                # poison posture, exactly like the dispatch path's C3.
                # mark_ended_at_boundary (not mark_ended): the discarded
                # event may itself be the terminal `ended` event — the
                # registry already flipped — and the marker must land
                # anyway, carrying the discarded sequence (F1, review
                # wave).
                if not landing_originated(exc, subscription_id):
                    self._failed = True
                    self._stream_clear()
                    return PollOutcome(
                        refusal=OperationError(
                            ErrorCode.PROTOCOL_ERROR,
                            "Invalid, failed or late adapter event; no replay",
                            DispatchState.UNKNOWN,
                        ),
                        session_failed=True,
                    )
                with suppress(Exception):
                    self._stream.mark_ended_at_boundary(
                        subscription_id,
                        cause="event quota exhausted",
                        discarded_sequence=sequence,
                    )
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.RESOURCE_LIMIT,
                        "event quota exhausted at the landing boundary; "
                        "the subscription is torn down",
                        DispatchState.DISPATCHED,
                    )
                )
            except InvalidEvent as exc:
                # The honest invalid-event class (G1/G3, Forge wave): the
                # validator's own refusal — non-schema shape, an invalid
                # conditional-key value, or content the host cannot store —
                # poisons WITH its message, never the generic failed-or-late
                # wording that would mislabel an unserializable-but-legal
                # x-extension value as adapter misconduct.
                self._failed = True
                self._stream_clear()
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.PROTOCOL_ERROR,
                        f"invalid event: {exc}",
                        DispatchState.UNKNOWN,
                    ),
                    session_failed=True,
                )
            except (Exception, asyncio.CancelledError) as exc:
                self._failed = True
                self._stream_clear()
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.TIMEOUT
                        if isinstance(exc, TimeoutError)
                        else ErrorCode.PROTOCOL_ERROR,
                        "Invalid, failed or late adapter event; no replay",
                        DispatchState.UNKNOWN,
                    ),
                    session_failed=True,
                )

    def _validate_event(
        self,
        subscription_id: str,
        event: Any,
        *,
        last_sequence: int | None,
        last_kind: str | None,
    ) -> dict[str, Any]:
        """Enforce the closed ``$defs/event`` (R4). Raises
        :class:`InvalidEvent` — the poison channel — on any protocol lie:
        a non-schema shape, an unknown kind, a subscription_id other than
        the polled subscription (cross-subscription laundering), a
        non-increasing sequence (equal = duplicate, lower = regression),
        an event after the terminal ``ended``, a telemetry event without a
        reading, a non-telemetry event without code+message, an
        INVALID VALUE under any present conditional key (the corpus
        declares ``reading`` and ``code``/``message`` unconditionally —
        the if/then blocks govern presence only; G1, Forge wave), or
        content the host cannot store (JSON-serializability, G3).
        ``x-`` extension keys are schema-legal and pass through.

        The after-ended rule is enforced HERE even though the registry gate
        above refuses polling a dead subscription first (the clean
        INVALID_ARGUMENT arm): the validator is the structural enforcement
        for any path that presents one.
        """
        if not isinstance(event, dict):
            raise InvalidEvent("event must be an object")
        for key in event:
            if key not in self._EVENT_KEYS and not self._X_KEY_PATTERN.fullmatch(str(key)):
                raise InvalidEvent(f"event carries an undeclared key {key!r}")
        if event.get("subscription_id") != subscription_id:
            raise InvalidEvent("event subscription_id does not match the polled subscription")
        kind = event.get("kind")
        if kind not in self._EVENT_KINDS:
            raise InvalidEvent(f"unknown event kind {kind!r}")
        sequence = event.get("sequence")
        if type(sequence) is not int or sequence < 0:
            raise InvalidEvent("event sequence must be an integer >= 0")
        if last_kind == "ended":
            raise InvalidEvent("event after the terminal ended event")
        if last_sequence is not None and sequence <= last_sequence:
            raise InvalidEvent(
                f"sequence {sequence} is not strictly increasing "
                f"(last received {last_sequence}; an equal sequence is a duplicate)"
            )
        # Presence by kind (the if/then blocks)...
        if kind == "telemetry":
            if event.get("reading") is None:
                raise InvalidEvent("telemetry event requires a reading")
        else:
            code = event.get("code")
            message = event.get("message")
            if (
                not isinstance(code, str)
                or not code
                or not isinstance(message, str)
                or not message
            ):
                raise InvalidEvent(f"{kind} event requires code and message strings")
        # ...and VALUE unconditionally: the corpus declares reading and
        # code/message with their shapes on every kind (G1, Forge wave) —
        # a gap event carrying a garbage reading is corpus-illegal.
        if "reading" in event:
            self._event_reading(event["reading"])
        if "code" in event:
            code_value = event["code"]
            if not isinstance(code_value, str) or not code_value:
                raise InvalidEvent("event code, when present, must be a non-empty string")
        if "message" in event:
            message_value = event["message"]
            if not isinstance(message_value, str) or not message_value:
                raise InvalidEvent("event message, when present, must be a non-empty string")
        # Serializability (G3, Forge wave): the corpus admits any
        # x-extension VALUE, and a circular or pathologically deep one is
        # legal content the host cannot STORE — refuse it here, before the
        # landing's json.dumps would raise mid-transaction, as the honest
        # invalid-event class rather than a protocol lie about the adapter.
        try:
            json.dumps(event, sort_keys=True, default=str)
        except (TypeError, ValueError) as exc:
            raise InvalidEvent(
                "event is not JSON-serializable (an x-extension value the "
                f"host cannot store): {exc}"
            ) from exc
        return event

    @classmethod
    def _event_reading(cls, reading: Any) -> None:
        """The ``$defs/reading`` subschema for telemetry events: all seven
        fields present with corpus-valid shapes (no request parameter to
        correlate against — the subscription's parameters are the context)."""
        if not isinstance(reading, dict):
            raise InvalidEvent("telemetry reading must be an object")
        for key in reading:
            if key not in cls._READING_KEYS and not cls._X_KEY_PATTERN.fullmatch(str(key)):
                raise InvalidEvent(f"telemetry reading carries an undeclared key {key!r}")
        for key in cls._READING_KEYS:
            if key not in reading:
                raise InvalidEvent(f"telemetry reading requires {key}")
        if not isinstance(reading["parameter"], str) or not cls._STREAM_PARAMETER_PATTERN.fullmatch(
            reading["parameter"]
        ):
            raise InvalidEvent("telemetry reading parameter must match ^[a-z][a-z0-9_]*$")
        if not cls._scalar(reading["value"]):
            raise InvalidEvent("telemetry reading requires a finite scalar value")
        if reading["unit"] is not None and not isinstance(reading["unit"], str):
            raise InvalidEvent("telemetry reading unit must be a string or null")
        if not isinstance(reading["observed_at"], str) or not reading["observed_at"]:
            raise InvalidEvent("telemetry reading requires an observed_at string")
        if type(reading["age_ms"]) is not int or reading["age_ms"] < 0:
            raise InvalidEvent("telemetry reading age_ms must be an integer >= 0")
        if reading["quality"] not in ("valid", "stale", "invalid"):
            raise InvalidEvent("telemetry reading quality is not in the corpus enum")
        if reading["source"] not in ("device", "cache", "commissioned"):
            raise InvalidEvent("telemetry reading source is not in the corpus enum")

    def _capture_originated(
        self, exc: BaseException, capture_id: str | None, request: OperationRequest
    ) -> bool:
        """C3's discriminator as amended: the writer's stamp must carry the
        writer module's token bound to THIS capture's id; the bundle's
        evidence stamp must carry its bundle module's token bound to THIS
        operation's id (either bundle — capture or dataset); the dataset
        arm (issue #146, Amendment 1 HIGH-1 / R10) matches the writer's
        stamp bound to one of THIS operation's live payload ids. Presence
        alone proves nothing; a genuine saved instance replayed on another
        dispatch keeps the poison posture."""
        if isinstance(exc, EvidenceQuotaExceeded):
            return evidence_originated(
                exc, request.operation_id
            ) or dataset_evidence_originated(exc, request.operation_id)
        if capture_id is not None and writer_originated(exc, capture_id):
            return True
        return self._dataset is not None and self._dataset.payload_stamp_originated(
            exc, request.operation_id
        )

    @staticmethod
    def _exact_int(value: Any) -> int | None:
        """The value iff it is exactly an int (bool is a subclass — rejected),
        else None; the gate's typing discipline."""
        return value if type(value) is int else None

    def _invalid(self, request: OperationRequest, message: str) -> OperationResult:
        return OperationResult.failure(
            request.operation_id,
            request.verb,
            code=ErrorCode.INVALID_ARGUMENT,
            message=message,
            dispatch_state=DispatchState.NOT_DISPATCHED,
        )

    def _abort_contained(self, capture_id: str | None, operation_id: str) -> None:
        """The bounded abort epilogue (A8): host-side synchronous reclaim
        plus the forensic record, without depending on adapter cooperation.
        Fully contained — every failure is suppressed and logged, never
        replacing the OperationResult being returned. Runs ONLY for a
        capture that was actually opened, and (issue #176 row B) under the
        epilogue's own bounded floor: the dispatch deadline may already be
        spent, but the reclaim still waits for the lock up to
        ``min(CAPTURE_EPILOGUE_FLOOR_MS, the store's open busy timeout)`` —
        a clamped-out capture reclaims its staging rows instead of leaking
        them."""
        if capture_id is None or self._capture is None:
            return
        with suppress(Exception), self._capture.epilogue_floor():
            self._capture.abort(
                capture_id, reason="dispatch failed", operation_id=operation_id
            )

    def _capture_manifest(
        self, request: OperationRequest, data: dict[str, Any]
    ) -> dict[str, Any]:
        """The two-sided manifest contract (G4): per-key echo checks against
        the dispatch request, host-computed fields from the writer's
        published record — adapter-supplied digest/length/artifact id are
        ignored, never trusted, and the bridge returns the HOST-constructed
        manifest. Per-key checks on purpose (A12): a raise-gated set
        literal would wrongly close the manifest (``x-`` extension keys are
        schema-legal) and trip the envelope pin.
        """
        arguments = request.arguments
        capture_id = str(arguments["capture_id"])
        record = self._capture.finalise_record(capture_id)
        if record is None:
            raise ValueError("capture result without a published capture")
        if data.get("capture_id") != capture_id:
            raise ValueError("uncorrelated capture manifest")
        if data.get("format") != arguments["format"]:
            raise ValueError("capture manifest format does not echo the request")
        if "sample_count" in data and data["sample_count"] != arguments["sample_count"]:
            raise ValueError("capture manifest sample_count does not echo the request")
        started_at = data.get("started_at")
        if not isinstance(started_at, str) or not started_at:
            raise ValueError("capture manifest requires a started_at string")
        manifest: dict[str, Any] = {
            "capture_id": capture_id,
            "format": record["format"],
            "artifact_id": record["artifact_id"],
            "byte_length": record["byte_length"],
            "sha256": record["sha256"],
            "started_at": started_at,
        }
        if arguments["format"] == "waveform_f64le":
            count = arguments["sample_count"]
            if record["byte_length"] != count * 8:
                raise ValueError("published byte_length disagrees with sample_count×8")
            interval = data.get("sample_interval_s")
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not math.isfinite(interval)
                or not interval > 0
            ):
                raise ValueError("capture manifest requires a positive finite sample_interval_s")
            unit = data.get("unit")
            if not isinstance(unit, str) or not unit:
                raise ValueError("capture manifest requires a non-empty unit")
            manifest["sample_count"] = count
            manifest["sample_interval_s"] = interval
            manifest["unit"] = unit
        return manifest

    @staticmethod
    def _scalar(value: Any) -> bool:
        return (
            value is None
            or type(value) in {str, bool, int}
            or (type(value) is float and math.isfinite(value))
        )

    @staticmethod
    def _reading(data: dict[str, Any], parameter: str) -> Reading:
        if not isinstance(data, dict) or not OTDPBridge._scalar(data.get("value")):
            raise ValueError("reading requires a finite scalar value")
        if type(data.get("age_ms")) is not int:
            raise ValueError("reading age must be an integer")
        if not isinstance(data.get("observed_at"), str):
            raise ValueError("reading timestamp must be a string")
        if data.get("unit") is not None and not isinstance(data["unit"], str):
            raise ValueError("reading unit must be a string or null")
        data = dict(data)
        if data.get("parameter") != parameter:
            raise ValueError("uncorrelated parameter")
        data["quality"] = Quality(data["quality"])
        data["source"] = ReadingSource(data["source"])
        return Reading(**data)

    def _convert(
        self, request: OperationRequest, result: Any, context: _Context
    ) -> OperationResult:
        if (
            not isinstance(result, dict)
            or result.get("operation_id") != request.operation_id
            or result.get("verb") != request.verb.value
        ):
            raise ValueError("uncorrelated result")
        status = OperationStatus(result["status"])
        if status is not OperationStatus.OK:
            if set(result) != {"operation_id", "verb", "status", "error"}:
                raise ValueError("invalid error envelope")
            error = result["error"]
            if set(error) != {"code", "message", "dispatch_state"}:
                raise ValueError("invalid error")
            state = DispatchState(error["dispatch_state"])
            if context.dispatched and state is DispatchState.NOT_DISPATCHED:
                raise ValueError("contradictory dispatch receipt")
            if state is not DispatchState.NOT_DISPATCHED:
                self._failed = True
            return OperationResult(
                request.operation_id,
                request.verb,
                status,
                error=OperationError(ErrorCode(error["code"]), error["message"], state),
            )
        if set(result) != {"operation_id", "verb", "status", "data"}:
            raise ValueError("invalid success envelope")
        if not isinstance(result["data"], dict):
            raise ValueError("success data must be an object")
        data = dict(result["data"])
        value: Any
        if request.verb.value == "identify":
            if any(
                not isinstance(data.get(key), str) or not data[key]
                for key in ("manufacturer", "model")
            ):
                raise ValueError("identity requires nonempty strings")
            if any(
                data.get(key) is not None and not isinstance(data[key], str)
                for key in ("serial", "firmware")
            ):
                raise ValueError("identity fields must be strings or null")
            data["source"] = IdentitySource(data["source"])
            value = Identity(**data)
        elif request.verb.value == "read":
            value = self._reading(data, request.arguments["parameter"])
        elif request.verb.value == "capture":
            value = self._capture_manifest(request, data)
        elif request.verb.value in ("stream_subscribe", "stream_unsubscribe"):
            # Echo correlation (the _convert operation-id precedent,
            # extended to subscription ids — Decision 4): the success data
            # must echo the request's host-minted id; anything else is a
            # protocol lie and poisons through the raise.
            echoed = data.get("subscription_id")
            if not isinstance(echoed, str) or not echoed:
                raise ValueError("stream result requires a subscription_id string")
            if echoed != request.arguments["subscription_id"]:
                raise ValueError("uncorrelated subscription id")
            value = {"subscription_id": echoed}
        elif request.verb.value == "invoke":
            # The runtime schema's invoke data branch is closed: exactly
            # {action_id, result}, no x- extension keys. Failures raise
            # InvalidInvokeResult (the honest invalid-result class, R6) so
            # the specific refusal reaches the record.
            if set(data) != {"action_id", "result"}:
                raise InvalidInvokeResult(
                    "invoke result data must be exactly {action_id, result}"
                )
            if data.get("action_id") != request.arguments["action_id"]:
                raise InvalidInvokeResult("uncorrelated invoke action_id")
            payload = data["result"]
            action = self._dataset.actions[request.arguments["action_id"]]
            errors = list(action.output_validator.iter_errors(payload))
            if errors:
                first = errors[0]
                raise InvalidInvokeResult(
                    f"result violates the action's catalog output schema at "
                    f"{first.json_path}: {first.message}"
                )
            if self._dataset.is_dataset_shaped(payload):
                # The dataset-publication cross-check (§2.3; strict from
                # day one — the design's slice-2 posture): a dataset-shaped
                # result must be an admitted manifest THIS operation
                # published through the dataset services. Bridge-side
                # state, never adapter cooperation.
                admitted = self._dataset.admitted_for(request.operation_id)
                if admitted is None or canonical_json(admitted) != canonical_json(
                    payload
                ):
                    note = self._dataset.dataset_shape_note(payload)
                    refusal = (
                        "invoke returned a dataset-shaped result that was never "
                        "admitted through dataset_publish"
                    )
                    if note is not None:
                        refusal = f"{refusal} ({note})"
                    raise InvalidInvokeResult(refusal)
            value = {"action_id": request.arguments["action_id"], "result": payload}
        else:
            if (
                data.get("parameter") != request.arguments["parameter"]
                or data.get("requested_value") != request.arguments["value"]
            ):
                raise ValueError("uncorrelated write receipt")
            if not self._scalar(data.get("effective_value")):
                raise ValueError("write receipt requires a finite scalar")
            data["assurance"] = Assurance(data["assurance"])
            if data.get("verification") is not None:
                data["verification"] = self._reading(data["verification"], data["parameter"])
            data.setdefault("verification", None)
            value = WriteReceipt(**data)
        return OperationResult.ok(request.operation_id, request.verb, value)
