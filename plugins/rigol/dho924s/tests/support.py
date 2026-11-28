# author: Stephen Eaton
"""Shared test doubles. EVERY exchange driven through them is SYNTHETIC.

Nothing here was recorded on an instrument. The ``*IDN?`` reply follows the
response shape the manufacturer's programming guide documents; its serial and
firmware tokens are invented. No vector in this project is hardware-qualified.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "benchweave_rigol_dho924s"
EVIDENCE_SHEET = ROOT / "docs" / "device-evidence.md"
SYNTHETIC_PROVENANCE = "synthetic — not hardware-qualified (issue #92)"


def contracts_dir() -> Path:
    """The local fetched-copy directory named by the contract lock.

    Same destination formula as scripts/fetch_contracts.py: the lock's
    directory field names the corpus; the local dir is its last two parts
    joined on a dash (standards/otdp/<version> -> contracts/otdp-<version>).
    """
    lock = json.loads((ROOT / "contracts/lock.json").read_text())
    return ROOT / "contracts" / "-".join(Path(lock["directory"]).parts[-2:])


def vectors(name: str) -> dict[str, Any]:
    """A packaged vector file, asserting it names itself synthetic."""
    document = json.loads((PACKAGE / name).read_text())
    assert document["provenance"] == SYNTHETIC_PROVENANCE
    return document


class Context:
    """The OperationContext double: one operation, one deadline."""

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
        if self.marker_error is not None:
            raise self.marker_error


class Host:
    """Wire-scripted host speaking the OTDP scoped stream grammar.

    This is the synthetic link between the adapter and a synthetic device.
    Each ``stream_send`` pops the next scripted reply frame into the receive
    buffer, so a reply exists only after its command was sent. One
    ``stream_receive`` returns exactly one complete frame, terminator
    included, as the grammar defines. When no complete frame is available the
    real host would block until the operation deadline; this double models
    that block by advancing its clock past the deadline and offering EOF.
    A complete frame longer than the requested bound is a host refusal.

    ``calls`` records every transfer with its context: the evidence that no
    I/O happened outside what a test scripted.
    """

    def __init__(self, *replies: bytes) -> None:
        self.replies: list[bytes] = list(replies)
        self.buffer = bytearray()
        self.now = 100.0
        self.calls: list[tuple[dict[str, Any], Context]] = []
        self.closes = 0
        self.failure: BaseException | None = None
        self.fail_at = 0
        self.advance_at = 0
        self.cancel_at = 0

    def monotonic(self) -> float:
        return self.now

    def utc_now(self) -> str:
        return "2026-11-28T00:00:00Z"

    def sent(self) -> list[bytes]:
        """Every ``stream_send`` payload, in order."""
        return [
            transaction["data"]
            for transaction, _ in self.calls
            if transaction["kind"] == "stream_send"
        ]

    def _frame(self, termination: str, max_bytes: int) -> bytes:
        marker = {"lf": b"\n", "crlf": b"\r\n", "eom": b""}[termination]
        end = len(self.buffer) if termination == "eom" else self.buffer.find(marker)
        if end < 0:
            # No terminator yet: the host blocks, the deadline passes.
            self.now = 102.0
            return b""
        frame = bytes(self.buffer[: end + len(marker)])
        if len(frame) > max_bytes:
            raise ValueError("receive exceeds max_bytes")
        del self.buffer[: end + len(marker)]
        return frame

    async def transfer(self, transaction: dict[str, Any], context: Context) -> dict[str, Any]:
        self.calls.append((transaction, context))
        count = len(self.calls)
        if count == self.advance_at:
            self.now = 102.0
        if count == self.cancel_at:
            context.cancelled = True
        if count == self.fail_at and self.failure is not None:
            raise self.failure
        if transaction["kind"] == "stream_send":
            # The dispatch marker precedes the first transmission (spec section 8).
            assert context.markers == 1
            assert set(transaction) == {"kind", "data"}
            data = transaction["data"]
            assert type(data) is bytes
            if self.replies:
                self.buffer.extend(self.replies.pop(0))
            return {}
        assert transaction["kind"] == "stream_receive"
        assert set(transaction) == {"kind", "max_bytes", "termination", "exact_bytes"}
        # A line of unknown length: the terminator delimits it, not a byte count.
        assert transaction["exact_bytes"] is None
        return {"data": self._frame(transaction["termination"], transaction["max_bytes"])}

    async def close_transport(self, context: Context) -> None:
        self.closes += 1


class RecordingTransport:
    """The client-level Transport double: it records every exchange.

    Each receive returns the next scripted frame, terminator included, or EOF
    when none is left. The knobs inject failures: ``send_error`` raises at the
    send, ``hang`` never completes a receive, and ``receive_hook`` replaces
    the receive outright.
    """

    def __init__(self, *replies: bytes) -> None:
        self.replies: list[bytes] = list(replies)
        self.sent: list[bytes] = []
        self.received_sizes: list[int] = []
        self.send_error: BaseException | None = None
        self.hang = False
        self.receive_hook: Callable[[int], Awaitable[bytes]] | None = None

    async def send(self, data: bytes) -> None:
        self.sent.append(data)
        if self.send_error is not None:
            raise self.send_error

    async def receive(self, max_bytes: int) -> bytes:
        self.received_sizes.append(max_bytes)
        if self.receive_hook is not None:
            return await self.receive_hook(max_bytes)
        if self.hang:
            await asyncio.Future[None]()
        return self.replies.pop(0) if self.replies else b""


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Drive one coroutine on a fresh event loop."""
    return asyncio.run(coroutine)


def request(verb: str, **arguments: Any) -> dict[str, Any]:
    return {"operation_id": "host-op", "verb": verb, "arguments": arguments}


def validate_result(result: dict[str, Any]) -> None:
    """The result must be a valid OTDP operationResult."""
    schema = json.loads((contracts_dir() / "otdp-runtime.schema.json").read_text())
    schema["$ref"] = "#/$defs/operationResult"
    schema.pop("oneOf")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
    assert result["operation_id"] == "host-op"


@pytest.fixture
def validate() -> Callable[[dict[str, Any]], None]:
    return validate_result
