"""The dataset/invoke lane's composing services (issue #146, slice-3 form).

The direct sibling of ``capture_services.py``, structure for structure
(design §2.2): a ``DatasetServicesBundle`` over the scoped base (the SDK §3
seven-member shape, constructed by permission), a ``DatasetController``
held by the bridge, and the permission-gated ``build_dataset_services``
builder that re-derives the raw descriptor by digest (the grant-seam
precedent). The controller's slice-2 dispatch half (the compiled action
registry, the ``ds:`` mint, the admitted-manifest state, clamp forwarding)
grows in place here into the full form: the open-payload-id registry
(load-bearing — the writer's quota stamp binds to the ``pay:`` staging id
and only the controller knows which ids an operation minted), the
finalise-record table M11 cross-checks, and the failure-path reclaims.

The payload lane's allowance differs from captures by one term (design
§2.2): payload bytes belong to the dataset budget and are NOT clamped by
``max_capture_bytes`` — the writer's ``open_payload`` enforces exactly
``min(byte_limit, max_dataset_bytes − used)`` and refuses at create, never
silently reduces (the owner ruling on MEDIUM-1; R12). Payload aborts are
idempotent local cleanup with NO forensic row — the corpus §3's own words,
unlike capture's #43-decided forensic marker; the difference is the
record's, disclosed here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import nullcontext, suppress
from typing import TYPE_CHECKING, Any

from benchweave.content.capture_services import ScopedServicesBundle
from benchweave.content.capture_store import CaptureStagingStore, writer_originated
from benchweave.content.store import ContentStore, EvidenceQuotaExceeded
from benchweave.host.types import EvidenceStamp

if TYPE_CHECKING:
    from benchweave.registry.otdp_contracts import CompiledAction, ResolvedOtdpContracts

#: The permission slices the builder gates on (spec §3/S15).
ARTIFACT_WRITER = "artifact_writer"
ARTIFACT_READER = "artifact_reader"

#: The dataset bundle module's private identity token (C3 as amended:
#: identity + operation binding, never attribute presence — the
#: capture_services.py:44-58 precedent verbatim in shape).
_BUNDLE_STAMP_TOKEN = object()


def dataset_evidence_originated(exception: BaseException, operation_id: str) -> bool:
    """True iff the exception carries THIS module's token bound to the named
    operation — the discriminator for the publish path's evidence-quota
    refusals raised through this bundle."""
    stamp = getattr(exception, "capture_stamp", None)
    return (
        isinstance(stamp, EvidenceStamp)
        and stamp.token is _BUNDLE_STAMP_TOKEN
        and stamp.operation_id == operation_id
    )


class DatasetServiceRejected(ValueError):
    """The dataset lane's typed refusal channel: the manifest failed
    identity, schema, an M-check of the implemented subset, idempotency or
    the quota routing. A subclass of ValueError so the adapter sees a typed,
    message-carrying refusal; what the adapter does with it is its own
    business — propagation reaches the bridge as adapter misconduct."""


class DatasetController:
    """The bridge-held dataset/invoke facade (the §0.3 pattern: invoke's
    control flows through this object, never through the bridge's
    ``self._services``).

    Holds the resolved contracts, mints both id families (``ds:`` dataset
    ids per dispatch — unique per occurrence-keyed operation id; ``pay:``
    payload staging ids per session counter), and carries the per-operation
    state the bundle correlates against: the dispatch's action/input, the
    LIVE payload-id registry (the R10 discriminator's membership source —
    minted ids enter it, terminal ids leave it), the finalise records M11
    cross-checks, and the admitted manifests (bridge cross-check +
    idempotency + lookup).
    """

    def __init__(
        self,
        *,
        contracts: ResolvedOtdpContracts,
        writer: Any = None,
        content: ContentStore | None = None,
        context_key: str | None = None,
        wall: Any = None,
    ) -> None:
        self._contracts = contracts
        self._writer = writer
        self._content = content
        self._context_key = context_key
        self._wall = wall
        self._payload_counter = 0
        # operation_id -> {dataset_id, action_id, input, payload_ids:
        # {pay_id: state}, finalise_records: {artifact_id: record},
        # admitted: dict | None}
        self._operations: dict[str, dict[str, Any]] = {}
        # dataset_id -> admitted manifest (idempotency + this-run lookup)
        self._admitted_by_dataset: dict[str, dict[str, Any]] = {}

    # --- the slice-2 dispatch half (unchanged surface) -----------------------

    @property
    def actions(self) -> Mapping[str, CompiledAction]:
        """§2.1's compiled action registry (I3/I4 and result conversion)."""
        return self._contracts.actions

    @property
    def dataset_required_keys(self) -> frozenset[str]:
        return self._contracts.dataset_required_keys

    def dispatch_clamp(self, deadline_ns: int, *, now_ns: int) -> Any:
        """Forward the dispatch clamp to the session's writer (issue #176
        row B's seam, extended to invoke by design §2.3)."""
        if self._writer is None:
            return nullcontext()
        return self._writer.dispatch_clamp(deadline_ns, now_ns=now_ns)

    def mint_dataset_id(
        self,
        operation_id: str,
        *,
        action_id: str | None = None,
        input: dict[str, Any] | None = None,  # the SDK protocol's own name
    ) -> str:
        """Mint and record the host-reserved dataset id for one dispatch
        (gate I6), with the dispatch's action and resolved input recorded
        for the publish path's M10-correlation cross-check."""
        dataset_id = f"ds:{operation_id}"
        self._operations[operation_id] = {
            "dataset_id": dataset_id,
            "action_id": action_id,
            "input": input,
            "payload_ids": {},
            "finalise_records": {},
            "admitted": None,
        }
        return dataset_id

    # --- the payload-id registry (Amendment 1 HIGH-1's load-bearing set) ----

    def mint_payload_id(self, operation_id: str) -> str:
        """Mint the next per-session payload staging id and enter it in the
        operation's LIVE registry (mint-before-open: a create-refused id is
        registry-live so its stamped quota refusal classifies through the
        discriminator's dataset arm, exactly a mid-append one does)."""
        self._payload_counter += 1
        payload_id = f"pay:{operation_id}:{self._payload_counter}"
        state = self._operations.get(operation_id)
        if state is None:
            # A bundle used outside a minted dispatch (host-side routing in
            # publish): track it under its own operation key.
            state = {
                "dataset_id": f"ds:{operation_id}",
                "action_id": None,
                "input": None,
                "payload_ids": {},
                "finalise_records": {},
                "admitted": None,
            }
            self._operations[operation_id] = state
        state["payload_ids"][payload_id] = "open"
        return payload_id

    def live_payload_ids(self, operation_id: str) -> tuple[str, ...]:
        """The operation's LIVE (minted, not terminal) payload ids — the R10
        discriminator's membership source."""
        state = self._operations.get(operation_id)
        if state is None:
            return ()
        return tuple(
            payload_id
            for payload_id, marker in state["payload_ids"].items()
            if marker == "open"
        )

    def payload_stamp_originated(
        self, exception: BaseException, operation_id: str
    ) -> bool:
        """The discriminator's dataset arm (R10): the writer's stamp bound
        to one of THIS operation's live payload ids. A genuine saved
        exception from ANOTHER operation's payload (same module token,
        wrong binding) does not classify — `writer_originated` requires the
        exact id."""
        return any(
            writer_originated(exception, payload_id)
            for payload_id in self.live_payload_ids(operation_id)
        )

    def note_payload_finalised(
        self, operation_id: str, payload_id: str, record: dict[str, Any]
    ) -> None:
        state = self._operations.get(operation_id)
        if state is not None and payload_id in state["payload_ids"]:
            state["payload_ids"][payload_id] = "finalised"
            state["finalise_records"][str(record["artifact_id"])] = dict(record)

    def note_payload_aborted(self, payload_id: str) -> None:
        """Mark a payload id terminal wherever it is registered —
        ``payload_abort`` carries no context (corpus §3), so the id is
        located by scan."""
        for state in self._operations.values():
            if payload_id in state["payload_ids"]:
                state["payload_ids"][payload_id] = "aborted"

    def finalise_records(self, operation_id: str) -> Mapping[str, dict[str, Any]]:
        """THIS operation's payload finalise records — M11's cross-check
        source (operation-scoped, Amendment 1 MEDIUM-4)."""
        state = self._operations.get(operation_id)
        return state["finalise_records"] if state is not None else {}

    # --- the admitted-manifest state -------------------------------------------

    def is_dataset_shaped(self, result: Any) -> bool:
        """The manifest's required keys all present (§2.3's detector)."""
        return isinstance(result, dict) and (
            self._contracts.dataset_required_keys <= set(result)
        )

    def admitted_for(self, operation_id: str) -> dict[str, Any] | None:
        """The admitted manifest for THIS operation, if any — the bridge's
        §2.3 result cross-check source."""
        state = self._operations.get(operation_id)
        if state is None:
            return None
        admitted = state.get("admitted")
        return admitted if isinstance(admitted, dict) else None

    def record_admitted(
        self, operation_id: str, manifest: dict[str, Any]
    ) -> None:
        """Record the admitted manifest (the publish path's final step):
        per-operation for the bridge cross-check, per-dataset-id for
        idempotency and this-run lookup."""
        state = self._operations.get(operation_id)
        if state is not None:
            state["admitted"] = manifest
        dataset_id = str(manifest.get("dataset_id"))
        self._admitted_by_dataset[dataset_id] = manifest

    def admitted_by_dataset_id(self, dataset_id: str) -> dict[str, Any] | None:
        """The admitted manifest for a dataset id THIS controller published
        (idempotency + ``dataset_lookup``'s this-run scope)."""
        return self._admitted_by_dataset.get(dataset_id)

    # --- the failure-path reclaims ------------------------------------------------

    def abort_open(self, operation_id: str) -> list[str]:
        """Reclaim an operation's still-open payloads (the classified-failure
        epilogue — the ``_abort_contained`` precedent minus the forensic
        row, payloads following the corpus text). Contained: failures are
        suppressed, never replacing the refusal being returned."""
        reclaimed: list[str] = []
        if self._writer is None:
            return reclaimed
        for payload_id in self.live_payload_ids(operation_id):
            with suppress(Exception):
                if self._writer.abort(payload_id):
                    reclaimed.append(payload_id)
                self.note_payload_aborted(payload_id)
        return reclaimed

    def sweep_open(self, *, reason: str) -> list[str]:
        """``plugin_close``'s sweep of every still-open payload across all
        operations (idempotent local cleanup, no forensic rows)."""
        reclaimed: list[str] = []
        for operation_id in list(self._operations):
            reclaimed.extend(self.abort_open(operation_id))
        return reclaimed


def build_dataset_controller(
    contracts: ResolvedOtdpContracts,
    *,
    writer: Any = None,
    content: ContentStore | None = None,
    context_key: str | None = None,
    wall: Any = None,
) -> DatasetController:
    """Construct the controller from §2.1's resolution (the loader-path
    call; ``build_dataset_services`` is the permission-gated full
    construction)."""
    return DatasetController(
        contracts=contracts,
        writer=writer,
        content=content,
        context_key=context_key,
        wall=wall,
    )


class DatasetServicesBundle(ScopedServicesBundle):
    """The invoke lane's base bundle (§3's shape): the scoped services plus
    ``dataset_publish`` and ``dataset_lookup``, one bundle per plugin
    session. The payload members and ``artifact_read`` join by permission
    through the mixin subclasses below — structural absence, never a
    runtime flag (spec §3/S15)."""

    def __init__(
        self,
        *,
        controller: DatasetController,
        writer: CaptureStagingStore,
        channels: tuple[str, ...] = (),
        **base: Any,
    ) -> None:
        super().__init__(**base)
        self._controller = controller
        self._writer = writer
        self._channels = frozenset(channels)

    # --- dataset_publish lands in slice S3b (dataset_publish + lookup) ----

    async def dataset_lookup(
        self, dataset_id: str, context: Any
    ) -> dict[str, Any]:
        """The validated admitted manifest for ``dataset_id``, THIS run's
        publishes only (the cross-principal authorization model is design
        row 2's deferral). Unknown or not-this-run ids refuse."""
        if not isinstance(dataset_id, str) or not dataset_id:
            raise DatasetServiceRejected("dataset_lookup requires a dataset id")
        admitted = self._controller.admitted_by_dataset_id(dataset_id)
        if admitted is None:
            raise DatasetServiceRejected(
                f"unknown dataset id for this run: {dataset_id!r}"
            )
        private_copy: dict[str, Any] = json.loads(json.dumps(admitted))
        return private_copy  # a private copy, never the admitted state

    def _stamp_evidence_quota(
        self, error: EvidenceQuotaExceeded, context: Any
    ) -> EvidenceQuotaExceeded:
        error.capture_stamp = EvidenceStamp(
            _BUNDLE_STAMP_TOKEN,
            getattr(context, "operation_id", None),
        )
        return error


class _PayloadMembers:
    """The ``artifact_writer``-gated payload surface (mixin over the
    bundle base; structurally absent without the permission). The bundle
    attributes the members rely on are declared here and satisfied by the
    concrete subclasses' base."""

    _controller: DatasetController
    _writer: CaptureStagingStore
    _context_key: str
    _wall: Any

    _PAYLOAD_ENCODINGS = (
        "f64le",
        "i64le",
        "u64le",
        "u8",
        "bool_u8",
        "logic_u8",
        "complex_f64le",
        "utf8_json",
    )

    async def payload_create(
        self,
        encoding: str,
        byte_limit: int,
        context: Any,
    ) -> str:
        """Reserve a bounded payload and return its host-minted staging id
        (spec §3). REFUSE-AT-CREATE (the owner ruling, capture-G3 parity):
        a ``byte_limit`` above the remaining dataset allowance raises the
        writer's stamped quota refusal naming the actual allowance — never
        a silently reduced ceiling (``payload_create`` returns ``str``,
        corpus-fixed, so a reduction would be undiscoverable); no staging
        row is written."""
        if encoding not in _PayloadMembers._PAYLOAD_ENCODINGS:
            raise DatasetServiceRejected(
                f"encoding {encoding!r} is not one of the manifest artifact "
                "encodings"
            )
        if type(byte_limit) is not int or not 1 <= byte_limit <= 2**53 - 1:
            raise DatasetServiceRejected(
                "byte_limit must be an integer in [1, 2^53-1]"
            )
        payload_id = self._controller.mint_payload_id(
            getattr(context, "operation_id", "")
        )
        self._writer.open_payload(
            payload_id=payload_id,
            context_key=self._context_key,
            encoding=encoding,
            byte_limit=byte_limit,
            now=self._wall(),
        )
        return payload_id

    async def payload_append(
        self,
        artifact_id: str,
        data: bytes,
        context: Any,
    ) -> None:
        """Append under the reservation; cancellation is honored per append
        (§8's rule — a cancelled operation refuses further writes), and a
        payload id from another session is refused by the writer's session
        key (R7's isolation)."""
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise DatasetServiceRejected("payload_append requires non-empty bytes")
        if getattr(context, "is_cancelled", lambda: False)():
            raise TimeoutError("operation cancelled: payload_append refused")
        self._writer.append(str(artifact_id), bytes(data), self._context_key)

    async def payload_finalise(
        self, artifact_id: str, context: Any
    ) -> dict[str, Any]:
        """Seal the payload: the writer publishes the content-addressed
        artifact and THIS method returns the host-computed artifact object
        ``{artifact_id, encoding, byte_length, sha256}`` (G4's discipline —
        adapter-supplied digests are not inputs at all), recording the
        finalise in the controller's per-operation table for M11."""
        payload_id = str(artifact_id)
        record = self._writer.finalise(
            payload_id, self._wall(), self._context_key
        )
        staged = self._writer.finalise_record(payload_id)
        encoding = str(staged["format"]) if staged is not None else ""
        full = {
            "artifact_id": record["artifact_id"],
            "encoding": encoding,
            "byte_length": record["byte_length"],
            "sha256": record["sha256"],
        }
        self._controller.note_payload_finalised(
            getattr(context, "operation_id", ""), payload_id, full
        )
        record_copy: dict[str, Any] = json.loads(json.dumps(full))
        return record_copy

    async def payload_abort(self, artifact_id: str) -> None:
        """Idempotent local cleanup through the writer — no forensic row
        (the corpus §3's own words; the capture marker was a #43 decision,
        not a corpus mandate)."""
        payload_id = str(artifact_id)
        self._writer.abort(payload_id)
        # Unknown/terminal ids are a no-op (abort returns False); open ids
        # are reclaimed. Either way the registry id goes terminal.
        self._controller.note_payload_aborted(payload_id)


class _ReaderMembers:
    """The ``artifact_reader``-gated upload-consumption surface (mixin;
    structurally absent without the permission). artifact_read lands in
    slice S3c."""

    pass


class DatasetPayloadBundle(DatasetServicesBundle, _PayloadMembers):
    """invoke ∧ resolved ∧ ``artifact_writer``: the base plus the four
    payload members."""


class DatasetReaderBundle(DatasetServicesBundle, _ReaderMembers):
    """invoke ∧ resolved ∧ ``artifact_reader``: the base plus
    ``artifact_read``."""


class DatasetFullBundle(DatasetPayloadBundle, DatasetReaderBundle):
    """Both permissions: the complete §3 twelve-member shape."""
