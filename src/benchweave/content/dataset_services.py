"""The dataset/invoke lane's bridge-held facade (issue #146, slice-2 form).

The full module design (issue #146 record §2.2) is the direct sibling of
``capture_services.py``: a ``DatasetServicesBundle`` (the SDK §3
seven-member shape), a ``DatasetController`` and a permission-gated
builder, one bundle per plugin session. This slice lands ONLY the
controller's dispatch half — the pieces §2.3's invoke dispatch gates and
result conversion consume — because the bundle, its writer-backed payload
members and the manifest-routing publish path are slice 3. The controller
grows in place when they land; nothing here is a runtime flag.

What the slice-2 controller holds (all from §2.1's resolution, verified
bundle bytes): the compiled action registry, the dataset-shape detector,
host-minted dataset ids (``ds:{operation_id}`` — unique per dispatch:
operation ids key on occurrence, and recovered steps never re-dispatch),
and the per-operation admitted-manifest state the bridge's result
cross-check consults. Nothing can admit a manifest before slice 3's
``dataset_publish`` exists, so the consultation is structurally
empty-handed today — by design: an unpublished dataset-shaped invoke
result refuses from day one (the design's strict posture, §3 slice 2).
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from benchweave.registry.otdp_contracts import CompiledAction, ResolvedOtdpContracts


class DatasetController:
    """The bridge-held dataset/invoke facade (the §0.3 pattern: invoke's
    control flows through this object, never through the bridge's
    ``self._services``).

    Slice-2 members: the resolved action registry and dataset shape, the
    ``ds:`` id mint, the (empty until slice 3) admitted-manifest state,
    and the row-B dispatch-clamp forwarding to the session's shared staged
    writer — the same one-instance-per-session writer the capture bundle
    shares, handed in by the loader path (a controller constructed
    without one, the unit-test posture, clamps nothing).
    """

    def __init__(
        self, *, contracts: ResolvedOtdpContracts, writer: Any = None
    ) -> None:
        self._contracts = contracts
        self._writer = writer
        self._operations: dict[str, dict[str, Any]] = {}

    @property
    def actions(self) -> Mapping[str, CompiledAction]:
        """§2.1's compiled action registry (I3/I4 and result conversion)."""
        return self._contracts.actions

    def dispatch_clamp(self, deadline_ns: int, *, now_ns: int) -> Any:
        """Forward the dispatch clamp to the session's writer (issue #176
        row B's seam, extended to invoke by design §2.3): the bridge
        brackets every invoke dispatch with this window when the
        controller exists — the store writes a fetch action's evidence and
        (slice 3) payload appends perform during ``execute`` hit the same
        single-writer store a capture's appends do."""
        if self._writer is None:
            return nullcontext()
        return self._writer.dispatch_clamp(deadline_ns, now_ns=now_ns)

    def mint_dataset_id(self, operation_id: str) -> str:
        """Mint and record the host-reserved dataset id for one dispatch
        (gate I6). The adapter never chooses it; ``context.dataset_id``
        carries it, and slice 3's ``dataset_publish`` will require the
        manifest to echo exactly this value."""
        dataset_id = f"ds:{operation_id}"
        self._operations[operation_id] = {"dataset_id": dataset_id, "admitted": None}
        return dataset_id

    def is_dataset_shaped(self, result: Any) -> bool:
        """The manifest's required keys all present (§2.3's detector —
        required keys, not full validation: the honest refusal for an
        unpublished dataset names the publication lie, not a subschema
        miss)."""
        return isinstance(result, dict) and (
            self._contracts.dataset_required_keys <= set(result)
        )

    def admitted_for(self, operation_id: str) -> dict[str, Any] | None:
        """The admitted manifest for THIS operation, if any — the
        bridge-side state behind the §2.3 result cross-check. Slice 3's
        ``dataset_publish`` records it; before that nothing can, so the
        cross-check refuses every dataset-shaped result (strict posture).
        """
        state = self._operations.get(operation_id)
        if state is None:
            return None
        admitted = state.get("admitted")
        return admitted if isinstance(admitted, dict) else None

    def sweep_open(self, *, reason: str) -> list[str]:
        """``plugin_close``'s sweep of still-open payloads. Slice 2 has no
        openable payloads (the ``payload_*`` services are slice 3), so
        this returns empty today; the hook lands now so the bridge's close
        path needs no second change when the writer-backed members do."""
        return []


def build_dataset_controller(
    contracts: ResolvedOtdpContracts, *, writer: Any = None
) -> DatasetController:
    """Construct the reduced controller from §2.1's resolution (the
    loader-path call). Slice 3 grows this into the permission-gated
    ``build_dataset_services`` builder over the raw descriptor by digest
    (the grant-seam precedent, §2.2)."""
    return DatasetController(contracts=contracts, writer=writer)
