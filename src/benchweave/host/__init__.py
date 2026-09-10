"""Host services and the published device ABI (WP04).

The host serves plugins — scoped services, typed envelopes, enforced limits.
Network serving to operators and AI clients is WP07 by design.
"""

from __future__ import annotations

from benchweave.host.plugin import DevicePlugin, SimulationInfo
from benchweave.host.services import HostServices, QuotaLimits, QuotaState
from benchweave.host.types import (
    Assurance,
    DeviceErrors,
    Diagnostic,
    DiagnosticDetail,
    DispatchState,
    ErrorCode,
    ErrorEntry,
    Identity,
    IdentitySource,
    OperationError,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationVerb,
    Quality,
    Reading,
    ReadingSource,
    Value,
    WriteReceipt,
)

__all__ = [
    "Assurance",
    "DeviceErrors",
    "DevicePlugin",
    "Diagnostic",
    "DiagnosticDetail",
    "DispatchState",
    "ErrorEntry",
    "ErrorCode",
    "HostServices",
    "Identity",
    "IdentitySource",
    "OperationError",
    "OperationRequest",
    "OperationResult",
    "OperationStatus",
    "OperationVerb",
    "Quality",
    "QuotaLimits",
    "QuotaState",
    "Reading",
    "ReadingSource",
    "SimulationInfo",
    "Value",
    "WriteReceipt",
]
