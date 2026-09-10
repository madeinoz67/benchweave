"""The device-plugin side of the published ABI.

A plugin is imported (no side effects), then explicitly opened with a scoped
HostServices instance, then dispatched against with typed requests carrying
monotonic deadlines. The timeout-after-dispatch rule: when a deadline passes,
the plugin reports TIMEOUT with dispatch_state DISPATCHED or UNKNOWN — never
silently retries, and never claims not_dispatched for work already sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from benchweave.host.services import HostServices
from benchweave.host.types import OperationRequest, OperationResult


@dataclass(frozen=True)
class SimulationInfo:
    """Simulation is visibly identified everywhere (PRD scope rule)."""

    simulated: bool
    label: str

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("simulation info requires a label")


class DevicePlugin(Protocol):
    """The complete plugin-side surface the host relies on."""

    @property
    def simulation(self) -> SimulationInfo: ...

    def plugin_open(self, services: HostServices) -> None:
        """Explicit open with scoped services; performs no I/O before it."""
        ...

    def plugin_close(self) -> None:
        """Release resources; never re-runs dispatched work."""
        ...

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        """Execute one operation under a monotonic deadline (nanoseconds)."""
        ...
