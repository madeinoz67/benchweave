"""Scoped host services: the capability surface devices may touch.

Per docs/device-developer-guide.md the host exposes ONLY scoped, admitted
services — verified-local content resolution, evidence retention, event
emission, dataset quotas — and never host paths or credentials. This module
declares the surface as protocols; concrete scoped implementations arrive
with the slices that need them. Pure: no I/O, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from benchweave.host.types import Reading


@dataclass(frozen=True)
class QuotaLimits:
    """Finite limits enforced BEFORE any write or retention happens.

    ``max_capture_bytes`` and ``max_subscriptions`` are the fork-3 HINT
    defaults (16 MiB covers the 16 MB class-lane worst case at 2x the 8 MB
    core-lane anchor; 16 subscriptions) — commissioned values come from
    bench qualification (A02), and ``max_subscriptions`` is unread until
    the streaming slice. ``max_dataset_bytes`` stays REQUIRED: explicit at
    every construction site, and it is honestly a per-context CAPTURE-byte
    ceiling in the G3 allowance formula (evidence-lane artifact bytes are
    excluded — the record scopes ``used`` to the capture ledger).
    """

    max_dataset_bytes: int
    max_evidence_entries: int
    max_event_batch: int
    max_capture_bytes: int = 16 * 1024 * 1024
    max_subscriptions: int = 16

    def __post_init__(self) -> None:
        for name, value in (
            ("max_dataset_bytes", self.max_dataset_bytes),
            ("max_evidence_entries", self.max_evidence_entries),
            ("max_event_batch", self.max_event_batch),
            ("max_capture_bytes", self.max_capture_bytes),
            ("max_subscriptions", self.max_subscriptions),
        ):
            if value < 1:
                raise ValueError(f"{name} must be >= 1")


@dataclass(frozen=True)
class QuotaState:
    dataset_bytes_used: int
    evidence_entries_used: int
    events_emitted: int


class ReadingSinks:
    """The ``register_reading_sink`` surface, live since the streaming
    slice (issue #43 slice 2): callable receivers for every Reading a
    plugin produces, delivered as telemetry events land. Delivery is
    contained — a raising sink is counted on ``failures``, never allowed
    to fail the landing that carries the reading."""

    def __init__(self) -> None:
        self._sinks: list[Any] = []
        self.failures = 0

    def register(self, sink: Any) -> None:
        """Register one callable; a non-callable is refused loudly (the
        member stores receivers — a silent no-op would look like delivery)."""
        if not callable(sink):
            raise TypeError("reading sink must be callable")
        self._sinks.append(sink)

    def deliver(self, reading: Any) -> None:
        """Hand one landed reading to every sink, containing failures."""
        for sink in self._sinks:
            try:
                sink(reading)
            except Exception:
                self.failures += 1


class HostServices(Protocol):
    """The complete scoped surface a device plugin may touch."""

    def resolve_content(self, content_id: str) -> bytes:
        """Resolve verified local content by id; never fetches remotely."""
        ...

    def retain_evidence(self, key: str, payload: bytes) -> str:
        """Retain an evidence blob under quota; returns its evidence id."""
        ...

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        """Emit a host event within the event batch quota."""
        ...

    def quota_state(self) -> QuotaState:
        """Current quota consumption (observable, not advisory)."""
        ...

    def register_reading_sink(self, sink: Any) -> None:
        """Register a callable receiving every Reading the plugin produces."""
        ...


_ = Reading  # re-exported for implementers of scoped services
