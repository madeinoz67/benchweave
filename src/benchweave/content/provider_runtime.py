"""The commissioned FTDI provider runtime (issue #568, design §2).

The gateway's FIRST live transport: behind ``ProviderTransport``'s
``runtime`` slot, one object that serves the admitted contract's provider
kinds AND the corpus §8.1 stream trio over one commissioned USB interface.
It is a plain object under the bridge's existing deadline/cancel/poison
envelope — no agent keeps it working (A04), and the wire surface for a
provider op does not exist: all provider traffic rides commissioned
procedures and the protective transition (A13, zero interface motion).

Module contract (pinned by ``tests/unit/test_provider_runtime.py``):

- **One bounded attempt, never a retry (A06).** A driver exception maps to
  :class:`ConnectionError` naming the exception class and the driver call
  happens exactly once; a faulted runtime stays faulted (reconnect is a new
  run — a fresh session).
- **Intent-first evidence for the energising ops** (A07): ``set_bitmode``
  and ``reset_device`` land one ``event_log`` evidence row — the
  transaction, the operation id, the monotonic stamp — BEFORE the driver
  call; a row failure refuses ``provider_runtime_audit_refused:`` and the
  driver is never called. The classification is the module's constant pair
  (A04: never a per-call judgement). The ``protect:`` operation-id
  convention's carve-out is A07's own: a safe action dispatches even when
  the intent row fails, and the failed-intent disclosure flushes at close
  — evidence storage is never a dependency of protection.
- **The §8.1 stream trio** rides the data pipe with the corpus row's own
  rules: strict field sets (the hand-carried twin of the SDK's ``_FIELDS``,
  pinned by a spelling test), ``exact_bytes`` precedence over terminator
  detection, ``exact_bytes ≤ max_bytes``, bounded reads, deadline-aware
  pacing with an idle quantum (never a hot spin), and an incomplete frame
  never returned as complete.
- **The reserved can/i2c/spi kinds refuse typed**
  (``provider_runtime_kind_unsupported:``) — reserved but unserved; they
  carry gateway-authorisation semantics the corpus has not designed and
  this runtime does not serve.
- **A missing pyftdi refuses typed** (``provider_runtime_backend_missing:``
  naming the install extra) at the connections load (admission — loud and
  early, maintainer ruling 1) and at the device open. Every open failure —
  absent device, busy, permission, no libusb backend — refuses
  ``provider_runtime_device_unavailable:`` naming the exception class, one
  bounded attempt with no scan and no retry.

What the runtime does NOT do: no retries, no fabrication, no fallback (there
is no second transport — the bridge's dispatch-state honesty is inherited
whole), no store I/O of its own (its evidence rows ride the bundle's
``record_evidence``), and no re-derivation of identity (the endpoint is the
grant's fact; the grammar is the admitted bytes' own).

The pyftdi call surface this module maps onto was VERIFIED against pyftdi
0.57.2 at build (the design's §0 flagged inference, confirmed):
``open_from_url``, ``reset``, the ``timeouts`` property,
``set_latency_timer``, ``set_baudrate``, ``purge_tx_buffer``/
``purge_rx_buffer``, ``set_bitmode``, ``read_pins``, ``write_data``,
``read_data``, ``close``.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from benchweave.control.provider_settings import UsbIdentity

#: The typed refusal prefixes this module emits (C2's machine-matchable
#: family, runtime side).
REFUSAL_PREFIXES = frozenset(
    {
        "provider_runtime_backend_missing:",
        "provider_runtime_device_unavailable:",
        "provider_runtime_op_unsupported:",
        "provider_runtime_kind_unsupported:",
        "provider_runtime_audit_refused:",
    }
)

#: The energising pair (design §1.5): the two ops whose direct physical
#: effect is pin energy (``set_bitmode`` drives the parallel-interface pins;
#: ``reset_device`` returns them to reset defaults). The intent-first rule
#: covers exactly these — a module contract constant, never a per-call
#: judgement (A04). A future contract revision adding an op leaves this
#: table frozen: the new op refuses at grant construction
#: (``provider_runtime_op_unsupported:``), so an unclassified energising op
#: cannot silently skip the rule.
ENERGISING_OPS = frozenset({"set_bitmode", "reset_device"})

#: The protective carve-out's operation-id convention (protection.py mints
#: ``protect:<action_id>`` — a stable in-tree convention, not a new
#: protocol).
PROTECT_PREFIX = "protect:"

#: The §8.1 stream trio's field sets (corpus otdp-specification §8.1):
#: strict, unspecified fields refused — the gateway's hand-carried twin of
#: the SDK's ``_FIELDS`` (obligation 17's family; the vendored runtime
#: schema does not enumerate kinds, so the table is prose-carried and its
#: spelling test pins it against the corpus rows). ``termination`` accepts
#: lf/crlf only on a serial-class data pipe (the corpus: "Serial/raw TCP do
#: not support eom").
STREAM_FIELDS: dict[str, frozenset[str]] = {
    "stream_send": frozenset({"kind", "data"}),
    "stream_receive": frozenset({"kind", "max_bytes", "termination", "exact_bytes"}),
    "stream_exchange": frozenset(
        {"kind", "data", "max_bytes", "termination", "exact_bytes"}
    ),
}

#: The reserved-but-unserved generic kinds (the corpus §8.1 table's
#: can/i2c/spi rows): refused typed, never dispatched.
RESERVED_UNSERVED = frozenset({"can_receive", "can_send", "i2c_transfer", "spi_transfer"})

_TERMINATORS = {"lf": b"\n", "crlf": b"\r\n"}

#: The hard transfer ceiling (the shared 64 KiB bound the sibling lanes
#: enforce): the descriptor-declared clamp is the adapter's own bound on
#: what it requests; this is the runtime's absolute window.
TRANSFER_CEILING = 65536

#: The idle quantum a receive sleeps when the data pipe is empty — pacing,
#: never a hot spin (the pyserial ``timeout=0.05`` posture).
_IDLE_SLEEP_S = 0.005

#: The read chunk size for one bounded data-pipe read.
_READ_CHUNK = 4096


class FtdiDriver(Protocol):
    """The ten hardware calls the seven contract ops plus the data pipe
    need, nothing else — the injectable device boundary; tests never need a
    device. The names are the executor's protocol, spelled for the
    contract's ops; :func:`open_ftdi` owns the whole mapping onto pyftdi's
    own call names, so a pyftdi API change is a one-function change."""

    def reset_device(self) -> None: ...

    def set_timeouts(self, read_ms: int, write_ms: int) -> None: ...

    def set_latency(self, ms: int) -> None: ...

    def set_baud(self, baud: int) -> None: ...

    def purge(self, queue: str) -> None:
        # ``queue`` is ``"tx"`` or ``"rx"`` — the contract's declared enum.
        ...

    def set_bitmode(self, mask: int, mode: int) -> None: ...

    def read_pins(self) -> int: ...

    def write_data(self, data: bytes) -> int: ...

    def read_data(self, size: int) -> bytes: ...

    def close(self) -> None: ...


#: The op dispatch table: each contract op to its parameter names, in the
#: order the driver call receives them — the runtime's declared vocabulary
#: and the grant's table-vs-grammar check's authority. An op outside it
#: refuses at grant construction (the version-skew belt: a newer pinned
#: contract may carry an op this runtime predates).
_OPS: dict[str, tuple[str, ...]] = {
    "reset_device": (),
    "set_timeouts": ("read_ms", "write_ms"),
    "set_latency": ("ms",),
    "set_baud": ("baud",),
    "purge": ("queue",),
    "set_bitmode": ("mask", "mode"),
    "read_pins": (),
}


def _require_backend() -> Any:
    """Refuse a missing pyftdi with the prefixed install hint, never a bare
    ImportError. Returns the imported class so :func:`open_ftdi` never
    re-imports (one import site)."""
    try:
        # The availability probe EXECUTES the import (not find_spec): a
        # pyftdi present but broken — its pyusb dependency missing — is
        # this refusal's class too, and only the real import proves it.
        from pyftdi.ftdi import Ftdi  # type: ignore[import-untyped]  # pyftdi, [provider] extra
    except ImportError as exc:
        raise ValueError(
            "provider_runtime_backend_missing: install 'benchweave[provider]' "
            "for FTDI provider transport support (pyftdi rides the provider "
            "extra)"
        ) from exc
    return Ftdi


def require_backend() -> None:
    """The admission-side backend probe (maintainer ruling 1): a
    provider-descriptor lattice on an extra-less install refuses at the
    connections load — loud and early, never at first transfer."""
    _require_backend()


class _PyftdiDriver:
    """The real driver: pyftdi's ``Ftdi`` behind the executor's protocol
    names. The only class that knows pyftdi's call names;
    :func:`open_ftdi` is the only constructor path."""

    def __init__(self, ftdi: Any) -> None:
        self._ftdi = ftdi

    def reset_device(self) -> None:
        self._ftdi.reset()

    def set_timeouts(self, read_ms: int, write_ms: int) -> None:
        self._ftdi.timeouts = (read_ms, write_ms)

    def set_latency(self, ms: int) -> None:
        self._ftdi.set_latency_timer(ms)

    def set_baud(self, baud: int) -> None:
        self._ftdi.set_baudrate(baud)

    def purge(self, queue: str) -> None:
        if queue == "tx":
            self._ftdi.purge_tx_buffer()
        else:
            self._ftdi.purge_rx_buffer()

    def set_bitmode(self, mask: int, mode: int) -> None:
        self._ftdi.set_bitmode(mask, mode)

    def read_pins(self) -> int:
        return int(self._ftdi.read_pins())

    def write_data(self, data: bytes) -> int:
        return int(self._ftdi.write_data(bytes(data)))

    def read_data(self, size: int) -> bytes:
        return bytes(self._ftdi.read_data(size))

    def close(self) -> None:
        self._ftdi.close()


def open_ftdi(identity: UsbIdentity) -> FtdiDriver:
    """Open one commissioned FTDI-class USB interface through pyftdi.

    The URL is composed from the commissioned identity
    (``ftdi://<vid>:<pid>:<serial>/<interface>``) — the identity is the
    grant's fact, and the serial-bearing URL is what makes wrong-device
    ambiguity unrepresentable at the open (maintainer ruling 2). A missing
    pyftdi refuses ``provider_runtime_backend_missing:``; every open
    failure refuses ``provider_runtime_device_unavailable:`` naming the
    exception class — one bounded attempt, no scan, no retry (A06).
    """
    ftdi_class = _require_backend()
    ftdi = ftdi_class()
    url = (
        f"ftdi://0x{identity.vendor_id:04x}:0x{identity.product_id:04x}:"
        f"{identity.serial}/{identity.interface}"
    )
    try:
        ftdi.open_from_url(url)
    except Exception as exc:
        with contextlib.suppress(Exception):
            ftdi.close()
        raise ConnectionError(
            f"provider_runtime_device_unavailable: {type(exc).__name__}: the "
            f"commissioned FTDI interface at {url!r} did not open (absent, "
            "busy, permission refused, or no USB backend)"
        ) from exc
    return _PyftdiDriver(ftdi)


def grammar_op_consts(contract: dict[str, Any]) -> dict[str, frozenset[str]]:
    """The admitted grammar's request-schema ``op`` consts, per kind — the
    grant's table-vs-grammar check's input.

    The ftdi-control grammar is one kind with an ``op`` discriminator (the
    #562 record §1's ruling): each ``oneOf`` branch's ``properties.op.const``
    names one op. A grammar kind that discriminates NO op consts is
    un-runnable by this runtime and refuses the grant (the design §2.2
    posture — an un-runnable procedure refuses at build, not mid-run).
    """
    consts: dict[str, frozenset[str]] = {}
    for entry in contract.get("transaction_grammar", []):
        kind = str(entry.get("kind"))
        request = entry.get("request_schema") or {}
        found: set[str] = set()
        for branch in request.get("oneOf", []):
            const = (
                (branch.get("properties") or {}).get("op") or {}
            ).get("const")
            if isinstance(const, str):
                found.add(const)
        consts[kind] = frozenset(found)
    return consts


class FtdiRuntime:
    """The commissioned runtime: one device session's transfer ladder.

    Constructed UNOPENED by the factory; :meth:`open` runs the driver
    factory once (the grant opens the device only after the table check
    passes); :meth:`close_transport` closes the one handle. A faulted or
    closed runtime stays that way — reconnect is a new run.
    """

    def __init__(
        self,
        *,
        contract: dict[str, Any],
        identity: UsbIdentity,
        driver_factory: Any,
        evidence: Any = None,
    ) -> None:
        self._contract = contract
        self._identity = identity
        self._driver_factory = driver_factory
        self._evidence = evidence
        self._driver: FtdiDriver | None = None
        self._closed = False
        self._faulted = False
        #: The protective carve-out's per-session disclosure list: an
        #: intent-row failure under ``protect:`` is recorded here and
        #: flushed as one best-effort summary row at close.
        self._failed_intents: list[dict[str, Any]] = []

    def open(self) -> None:
        """Open the one device handle (the driver factory's one call)."""
        if self._driver is not None or self._closed or self._faulted:
            raise RuntimeError(
                "provider_runtime_open_refused: the runtime is already open, "
                "closed or faulted (one handle, one open — reconnect is a new run)"
            )
        self._driver = self._driver_factory(self._identity)

    def attach_evidence(self, record: Any) -> None:
        """Bind the session bundle's ``record_evidence`` (the intent rows'
        writer). Before attachment an energising op refuses — intent that
        cannot be recorded is not actuated (A07)."""
        self._evidence = record

    async def transfer(self, transaction: dict[str, Any], context: Any) -> dict[str, Any]:
        """The runtime ladder (design §2.3), after the guard's grammar gate.

        Kind split: a grammar kind → the provider path; a §8.1 stream kind
        → the stream path; a reserved can/i2c/spi kind → the typed refusal.
        Anything else never reaches the runtime (the guard refused it).
        """
        self._require_live()
        kind = transaction.get("kind")
        grammar = grammar_op_consts(self._contract)
        if kind in grammar:
            return await self._provider_path(transaction, context)
        if kind in STREAM_FIELDS:
            return await self._stream_path(transaction, context)
        raise ValueError(
            f"provider_runtime_kind_unsupported: kind {kind!r} is reserved "
            "but unserved — the can/i2c/spi kinds carry gateway-authorisation "
            "semantics the corpus has not designed and this runtime does not "
            "serve"
        )

    def _require_live(self) -> None:
        if self._faulted:
            raise ConnectionError(
                "provider_runtime_faulted: the driver already faulted — a "
                "faulted runtime stays faulted (reconnect is a new run)"
            )
        if self._closed:
            raise ConnectionError(
                "provider_runtime_closed: the device session is closed"
            )
        if self._driver is None:
            raise ConnectionError(
                "provider_runtime_not_open: the device handle is not open"
            )

    async def _provider_path(
        self, transaction: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        op = transaction.get("op")
        if not isinstance(op, str) or op not in _OPS:
            raise ValueError(
                f"provider_runtime_op_unsupported: op {op!r} is not in this "
                "runtime's dispatch table; the pinned contract may be newer "
                "than the runtime — the grant refused it at build"
            )
        if op in ENERGISING_OPS:
            await self._intent_first(transaction, context)
        args = [transaction[name] for name in _OPS[op]]
        try:
            result = await asyncio.to_thread(
                self._dispatch, op, tuple(args)
            )
        except Exception as exc:
            self._faulted = True
            raise ConnectionError(
                f"provider_runtime_driver_fault: {type(exc).__name__}: {exc}"
            ) from exc
        if op == "read_pins":
            # The document form the guard validates on the way out: the one
            # byte as its padded base64 text (the contract's own spelling).
            if not isinstance(result, int) or isinstance(result, bool) or not (
                0 <= result <= 255
            ):
                raise ValueError(
                    f"provider_runtime_result_grammar: read_pins answered "
                    f"{result!r}, which is not the one byte the admitted "
                    "result schema declares"
                )
            return {"data": base64.b64encode(bytes([result])).decode("ascii")}
        return {}

    def _dispatch(self, op: str, args: tuple[Any, ...]) -> Any:
        """One driver call by op name (the table is the authority)."""
        if self._driver is None:
            # Survives python -O: _require_live checked this immediately
            # before the thread hop.
            raise RuntimeError(
                "provider_runtime_driver_absent: no driver is bound to this "
                "runtime (the device was never opened)"
            )
        return getattr(self._driver, op)(*args)

    async def _intent_first(
        self, transaction: dict[str, Any], context: Any
    ) -> None:
        """A07 made ordering: land the intent row before the driver call.

        A row failure refuses the op (``provider_runtime_audit_refused:``)
        — except under ``protect:``, where the safe action dispatches and
        the failed-intent disclosure joins the per-session list (evidence
        storage is never a dependency of protection).
        """
        entry = {
            "kind": "provider_op_intent",
            "operation_id": getattr(context, "operation_id", None),
            "transaction": {
                key: value
                for key, value in transaction.items()
                if key != "kind"
            }
            | {"kind": transaction["kind"]},
            "monotonic": self._monotonic(context),
        }
        record = self._evidence
        if record is None:
            # No writer bound: intent cannot be recorded → not actuated.
            if self._is_protective(context):
                self._failed_intents.append(entry)
                return
            raise ValueError(
                "provider_runtime_audit_refused: no evidence writer is bound "
                "to this session — an energising op's intent cannot be "
                "recorded and is not actuated (A07)"
            )
        try:
            result = record(entry, context)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            if self._is_protective(context):
                self._failed_intents.append(entry)
                return
            raise ValueError(
                "provider_runtime_audit_refused: the intent evidence row "
                "could not land — an energising op whose intent cannot be "
                "recorded is not actuated (A07)"
            ) from None

    @staticmethod
    def _is_protective(context: Any) -> bool:
        return str(getattr(context, "operation_id", "")).startswith(PROTECT_PREFIX)

    @staticmethod
    def _monotonic(context: Any) -> Any:
        services = getattr(context, "services", None)
        clock = getattr(services, "monotonic", None)
        return clock() if callable(clock) else None

    async def _stream_path(
        self, transaction: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        """The §8.1 stream trio over the data pipe (design §2.3.4)."""
        kind = transaction["kind"]
        fields = STREAM_FIELDS[kind]
        if set(transaction) != fields:
            raise ValueError(
                f"provider_runtime_stream_shape: {kind} carries "
                f"{sorted(set(transaction) - {'kind'})}; the §8.1 row's own "
                f"fields are {sorted(fields - {'kind'})} (unspecified fields "
                "refused)"
            )
        payload: bytes | None = None
        if "data" in fields:
            value = transaction.get("data")
            if not isinstance(value, bytes):
                raise ValueError(
                    "provider_runtime_stream_shape: data is bytes at the "
                    "adapter ABI, never base64 or text"
                )
            payload = value
        max_bytes, terminator, exact = (
            _stream_receive_bounds(transaction) if "max_bytes" in fields else (0, None, 0)
        )
        if payload is not None:
            sent = await self._write(payload)
            if sent != len(payload):
                self._faulted = True
                raise ConnectionError(
                    f"provider_runtime_driver_fault: short write ({sent} of "
                    f"{len(payload)} bytes) on {kind}"
                )
        if kind == "stream_send":
            return {}
        received = await self._receive(
            max_bytes, terminator, exact, context
        )
        return {"data": received}

    async def _write(self, data: bytes) -> int:
        try:
            return await asyncio.to_thread(self._driver_write, data)
        except Exception as exc:
            self._faulted = True
            raise ConnectionError(
                f"provider_runtime_driver_fault: {type(exc).__name__}: {exc}"
            ) from exc

    def _driver_write(self, data: bytes) -> int:
        if self._driver is None:
            raise RuntimeError(
                "provider_runtime_driver_absent: no driver is bound to this "
                "runtime (the device was never opened)"
            )
        return int(self._driver.write_data(data))

    async def _receive(
        self,
        max_bytes: int,
        terminator: bytes | None,
        exact: int,
        context: Any,
    ) -> bytes:
        """Deadline-aware bounded receive: ``exact_bytes`` precedence over
        terminator detection, incomplete frames never returned as complete.
        """
        buffer = bytearray()
        deadline = getattr(context, "deadline_monotonic", None)
        while True:
            want = min(_READ_CHUNK, max_bytes - len(buffer))
            if exact:
                want = min(want, exact - len(buffer))
            if want <= 0:
                # The bound is filled with no complete frame: a frame these
                # bounds cannot complete never returns as complete.
                raise TimeoutError(
                    "provider_runtime_stream_incomplete: no complete frame "
                    f"within max_bytes {max_bytes}"
                )
            try:
                chunk = await asyncio.to_thread(self._driver_read, want)
            except Exception as exc:
                self._faulted = True
                raise ConnectionError(
                    f"provider_runtime_driver_fault: {type(exc).__name__}: {exc}"
                ) from exc
            if chunk:
                buffer += chunk
                if exact and len(buffer) >= exact:
                    return bytes(buffer[:exact])
                if terminator is not None and buffer.endswith(terminator):
                    return bytes(buffer)
                continue
            # The pipe is empty: pace, then judge the deadline.
            await asyncio.sleep(_IDLE_SLEEP_S)
            if deadline is not None and self._monotonic_value(context) >= deadline:
                raise TimeoutError(
                    "provider_runtime_stream_incomplete: the receive deadline "
                    "passed with an incomplete frame — an incomplete frame "
                    "never returns as complete"
                )

    def _driver_read(self, size: int) -> bytes:
        if self._driver is None:
            raise RuntimeError(
                "provider_runtime_driver_absent: no driver is bound to this "
                "runtime (the device was never opened)"
            )
        return bytes(self._driver.read_data(size))

    def _monotonic_value(self, context: Any) -> float:
        services = getattr(context, "services", None)
        clock = getattr(services, "monotonic", None)
        return float(clock()) if callable(clock) else 0.0

    async def close_transport(self, context: Any) -> None:
        """Close the one handle, and flush the protective carve-out's
        failed-intent disclosures as one best-effort summary row (A07's own:
        the disclosure rides the same record path, and a failing flush is
        suppressed — the close is cleanup, not new work)."""
        if self._failed_intents and self._evidence is not None:
            entry = {
                "kind": "provider_intent_disclosure",
                "operation_id": getattr(context, "operation_id", None),
                "failed_intents": list(self._failed_intents),
                "monotonic": self._monotonic(context),
            }
            with contextlib.suppress(Exception):
                result = self._evidence(entry, context)
                if hasattr(result, "__await__"):
                    await result
            self._failed_intents.clear()
        if self._driver is not None and not self._closed:
            self._closed = True
            try:
                await asyncio.to_thread(self._driver.close)
            except Exception as exc:
                # A close failure is disclosed, never fabricated away: the
                # handle is gone from this session's authority either way.
                self._faulted = True
                raise ConnectionError(
                    f"provider_runtime_driver_fault: close failed: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc


def make_ftdi_runtime_factory(driver_factory: Any = None) -> Any:
    """The production runtime factory (design §2.2): ``factory(contract,
    identity)`` returns an UNOPENED :class:`FtdiRuntime` over
    :func:`open_ftdi` (or the injected driver factory, the test seam).

    The factory itself opens nothing: the grant construction runs the
    table-vs-grammar check first (``provider_runtime_op_unsupported:``
    before any device call) and calls ``runtime.open()`` only once the
    check passes — the B4 control's structural guarantee.
    """
    open_driver = driver_factory if driver_factory is not None else open_ftdi

    def factory(contract: dict[str, Any], identity: UsbIdentity) -> FtdiRuntime:
        return FtdiRuntime(
            contract=contract,
            identity=identity,
            driver_factory=open_driver,
        )

    return factory


def _stream_receive_bounds(transaction: dict[str, Any]) -> tuple[int, bytes, int]:
    """The §8.1 receive bounds against the transport ceiling — the shared
    definition's semantics (max_bytes 1..ceiling; termination lf/crlf on a
    serial-class pipe; exact_bytes None or 0..max_bytes), one definition
    family with the sibling lanes (obligation 17)."""
    max_bytes = transaction["max_bytes"]
    termination = transaction["termination"]
    exact = transaction["exact_bytes"]
    if (
        not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or not 1 <= max_bytes <= TRANSFER_CEILING
    ):
        raise ValueError(
            f"provider_runtime_stream_bounds: max_bytes must be 1..{TRANSFER_CEILING}"
        )
    if termination not in _TERMINATORS:
        raise ValueError(
            "provider_runtime_stream_bounds: termination must be 'lf' or "
            "'crlf' on a serial-class data pipe (eom is unsupported)"
        )
    if exact is not None and (
        not isinstance(exact, int)
        or isinstance(exact, bool)
        or not 0 <= exact <= max_bytes
    ):
        raise ValueError(
            "provider_runtime_stream_bounds: exact_bytes must be None or "
            "0..max_bytes"
        )
    return max_bytes, _TERMINATORS[termination], exact or 0
