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

import hashlib
import json
from collections.abc import Mapping
from contextlib import nullcontext, suppress
from typing import TYPE_CHECKING, Any

from benchweave.content.capture_services import ScopedServicesBundle
from benchweave.content.capture_store import CaptureStagingStore, writer_originated
from benchweave.content.store import ContentStore, EvidenceQuotaExceeded
from benchweave.control.documents import adapter_permissions
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


def _canonical(value: Any) -> str:
    """Canonical JSON text (sorted keys, tight separators) — the
    idempotency comparison and the routing bytes share one form; nan/inf
    are refused at serialization (M04's backstop for routed bytes)."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
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
        # this run's published-dataset artifacts (artifact_read's subset)
        self._readable_artifacts: set[str] = set()

    # --- the slice-2 dispatch half (unchanged surface) -----------------------

    @property
    def actions(self) -> Mapping[str, CompiledAction]:
        """§2.1's compiled action registry (I3/I4 and result conversion)."""
        return self._contracts.actions

    @property
    def dataset_required_keys(self) -> frozenset[str]:
        return self._contracts.dataset_required_keys

    @property
    def dataset_validator(self) -> Any:
        """The pinned measurement schema's compiled dataset validator
        (slice 3's publish validation surface)."""
        return self._contracts.dataset_validator

    def action_for(self, action_id: str | None) -> CompiledAction | None:
        """The action registry entry for M10's input-schema declaration
        check (None when unknown — the bridge gate already refused that
        dispatch shape)."""
        if action_id is None:
            return None
        return self._contracts.actions.get(action_id)

    def dispatch_state(self, operation_id: str) -> dict[str, Any] | None:
        """The per-operation state the publish path correlates against
        (action, resolved input, finalise records, admitted manifest)."""
        return self._operations.get(operation_id)

    def dispatch_clamp(self, deadline_ns: int, *, now_ns: int) -> Any:
        """Forward the dispatch clamp to the session's writer (issue #176
        row B's seam, extended to invoke by design §2.3)."""
        if self._writer is None:
            return nullcontext()
        return self._writer.dispatch_clamp(deadline_ns, now_ns=now_ns)

    def epilogue_floor(self) -> Any:
        """Forward the failure-path reclaim's bounded floor to the session's
        writer (§2.2's member list; wave 2 #3): the classified invoke's
        abort_open runs under ``min(CAPTURE_EPILOGUE_FLOOR_MS, open
        default)`` so a clamped-out dispatch still reclaims its open
        payloads — the ``_abort_contained`` precedent, floor and all."""
        if self._writer is None:
            return nullcontext()
        return self._writer.epilogue_floor_window()

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
        """The manifest's required keys all present (§2.3's detector —
        required keys only, so the honest channel for an unpublished
        dataset names the publication lie, not a subschema miss)."""
        return isinstance(result, dict) and (
            self._contracts.dataset_required_keys <= set(result)
        )

    def dataset_shape_note(self, result: Any) -> str | None:
        """The sharper refusal note for a dataset-shaped result that also
        fails the pinned measurement schema (Amendment 2 rider): the
        validator's own finding — e.g. a `kind` outside the corpus's nine
        dataset kinds — appended to the bridge's publication-lie refusal.
        The corpus's check family is M01-M15; this note never claims a
        narrower range."""
        if not self.is_dataset_shaped(result):
            return None
        error = next(iter(self._contracts.dataset_validator.iter_errors(result)), None)
        if error is None:
            return None
        return f"the pinned measurement schema refuses it at {error.json_path}: {error.message}"

    def admitted_for(self, operation_id: str) -> dict[str, Any] | None:
        """The admitted manifest for THIS operation, if any — the bridge's
        §2.3 result cross-check source."""
        state = self._operations.get(operation_id)
        if state is None:
            return None
        admitted = state.get("admitted")
        return admitted if isinstance(admitted, dict) else None

    def record_admitted(
        self, operation_id: str, manifest: dict[str, Any], artifact_id: str | None = None
    ) -> None:
        """Record the admitted manifest (the publish path's final step):
        per-operation for the bridge cross-check, per-dataset-id for
        idempotency and this-run lookup, and — with the routing artifact —
        the read-authorization subset (artifacts belonging to datasets
        this run published; row 3's wider upload-consumption model stays
        deferred)."""
        state = self._operations.get(operation_id)
        if state is not None:
            state["admitted"] = manifest
        dataset_id = str(manifest.get("dataset_id"))
        self._admitted_by_dataset[dataset_id] = manifest
        if artifact_id is not None:
            self._readable_artifacts.add(artifact_id)

    def artifact_readable(self, artifact_id: str) -> bool:
        """artifact_read's authorization subset: one of THIS run's
        published-dataset artifacts."""
        return artifact_id in self._readable_artifacts

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


def build_dataset_services(
    *,
    controller: DatasetController,
    services: ScopedServicesBundle,
    descriptor_digest: str,
    content: ContentStore,
    writer: CaptureStagingStore,
) -> ScopedServicesBundle:
    """The permission-gated construction point (§2.2's table; the
    build_capture_services precedent). Re-derives the RAW descriptor by
    pinned digest (the grant-seam precedent — CON-10's re-derives-the-
    raw-form-by-digest exactly as the permissions precedent does) and
    composes the dataset members ONTO the caller's services bundle by
    the adapter's declared permissions:

    ==================  ==========================================
    controller          the loader-constructed controller (the
                        invoke capability ∧ resolved contracts —
                        §2.1/§2.2's decision, made loader-side where
                        the verified inventory lives)
    base members        dataset_publish + dataset_lookup always
    artifact_writer     the four payload members join
    artifact_reader     artifact_read joins
    ==================  ==========================================

    The base keeps every member it already holds — a capturing class
    device keeps the capture lane. Structural members, never runtime
    flags (spec §3/S15).
    """
    document = content.get_document(descriptor_digest)
    if document is None:
        raise ValueError(
            "raw descriptor not cached at its pinned digest: the dataset "
            "factory re-derives the full form from the content store "
            f"(digest {descriptor_digest[:12]}… is absent — descriptors are "
            "cached when a binding pins them)"
        )
    raw = document["content"]
    channels = tuple(
        str(channel.get("id"))
        for channel in raw.get("channels", [])
        if isinstance(channel, dict)
    )
    return attach_dataset_members(
        services,
        controller=controller,
        writer=writer,
        channels=channels,
        permissions=adapter_permissions(raw),
    )


class _InvokeMembers:
    """The invoke lane's members (§3's shape): ``dataset_publish`` and
    ``dataset_lookup`` as a pure mixin over any services base. The
    attributes the members rely on are declared here and satisfied by the
    composing base (ScopedServicesBundle or the capture bundle — a class
    device that captures AND fetches keeps both lanes)."""

    _controller: DatasetController
    _writer: CaptureStagingStore
    _channels: frozenset[str]
    _content: ContentStore
    _context_key: str
    _quota_evidence: int
    _wall: Any

    # --- dataset_publish (§2.2 step 1-6; the validation surface) -------------

    #: dtype -> (payload encoding, element bytes). The M03 pairing for
    #: artifact-backed variables; utf8_json is variable-width (element bytes
    #: None — M02's byte-count agreement does not apply, the record
    #: cross-check still does).
    _DTYPE_ENCODING: Mapping[str, tuple[str, int | None]] = {
        "float64": ("f64le", 8),
        "int64": ("i64le", 8),
        "uint64": ("u64le", 8),
        "uint8": ("u8", 1),
        "bool": ("bool_u8", 1),
        "logic": ("logic_u8", 1),
        "complex128": ("complex_f64le", 16),
        "string": ("utf8_json", None),
    }

    async def dataset_publish(
        self, manifest: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        """Validate and admit one measurement manifest for this operation
        (spec §3; design §2.2 steps 1–6). The submitted ``dataset_id`` is
        host-reserved — it must equal ``context.dataset_id``, non-null (a
        null value forbids publishing). The order is load-bearing: identity
        first, then IDEMPOTENCY (a byte-identical manifest under a used
        dataset id returns the admitted manifest with no new rows — never
        re-routed, never double-charged), then the pinned schema, the
        implemented M-check subset (M01–M04, M10-correlation, M11
        operation-scoped, M14 by construction), then the manifest bytes
        ROUTED THROUGH THE STAGED WRITER (Amendment 1 HIGH-2: the staging
        row's reservation and finalise put the manifest's bytes in the
        ``used`` ledger, and the published ``art-<sha256>`` row is the
        manifest's own storage path — R11), and one evidence row (kind
        ``dataset``) under the session's context key — the dimension shared
        with the run's retention rows and the monitor's per-tick retention,
        disclosed (Amendment 1 LOW-3)."""
        operation_id = str(getattr(context, "operation_id", ""))
        dataset_id = getattr(context, "dataset_id", None)
        if not isinstance(manifest, dict):
            raise DatasetServiceRejected("dataset_publish manifest must be an object")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise DatasetServiceRejected(
                "dataset_publish requires the host-minted context.dataset_id "
                "(a null value forbids publishing)"
            )
        if manifest.get("dataset_id") != dataset_id:
            raise DatasetServiceRejected(
                f"manifest dataset_id {manifest.get('dataset_id')!r} does not "
                f"carry the host-minted id {dataset_id!r}"
            )
        admitted = self._controller.admitted_by_dataset_id(dataset_id)
        if admitted is not None:
            if _canonical(manifest) == _canonical(admitted):
                republish: dict[str, Any] = json.loads(json.dumps(admitted))
                return republish  # idempotent: no new rows, no re-routing
            raise DatasetServiceRejected(
                f"dataset {dataset_id!r} is already admitted and immutable: "
                "a divergent manifest under a used id is refused"
            )
        error = next(
            iter(self._dataset_validator().iter_errors(manifest)), None
        )
        if error is not None:
            raise DatasetServiceRejected(
                f"manifest violates the pinned measurement schema at "
                f"{error.json_path}: {error.message}"
            )
        self._check_m_structural(manifest)
        self._check_m10_correlation(manifest, operation_id)
        self._check_m11_records(manifest, operation_id)
        # Route the manifest bytes through the staged writer (HIGH-2): the
        # staging reservation and finalise put them in `used`, and the
        # published art-<sha256> row is the manifest's own storage path.
        blob = _canonical(manifest).encode()
        payload_id = self._controller.mint_payload_id(operation_id)
        self._writer.open_payload(
            payload_id=payload_id,
            context_key=self._context_key,
            encoding="utf8_json",
            byte_limit=len(blob),
            now=self._wall(),
        )
        self._writer.append(payload_id, blob, self._context_key)
        # The evidence row (kind dataset, on the shared disclosed LOW-3
        # dimension) joins the finalise's ONE transaction (wave 2, the
        # one-transaction boundary): a quota refusal rolls the whole
        # publish back — no artifact, no charged bytes, no registry/store
        # divergence — and the bundle's stamp on the raised refusal makes
        # it classifiable at the bridge, exactly the capture bundle's
        # record_evidence is.
        reference = {
            "id": dataset_id,
            "version": "1",
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
        try:
            record = self._writer.finalise(
                payload_id,
                self._wall(),
                self._context_key,
                evidence={
                    "kind": "dataset",
                    "reference": reference,
                    "context_key": self._context_key,
                    "quota": self._quota_evidence,
                },
            )
        except EvidenceQuotaExceeded as error_quota:
            # The rollback returned the routed row to STAGED — its
            # RESERVATION still counts against `used`, so the publish
            # aborts it (a genuinely effective abort now: pre-wave-2 the
            # row was finalised and the abort was a no-op — the leak).
            # Nothing is charged, nothing is staged, and the registry id
            # goes terminal — no divergence.
            self._writer.abort(payload_id)
            self._controller.note_payload_aborted(payload_id)
            raise self._stamp_evidence_quota(error_quota, context) from error_quota
        self._controller.note_payload_finalised(operation_id, payload_id, record)
        self._controller.record_admitted(operation_id, manifest, record["artifact_id"])
        result: dict[str, Any] = json.loads(json.dumps(manifest))
        return result

    def _dataset_validator(self) -> Any:
        """The pinned measurement schema's dataset validator (§2.1 compiled
        it; the bundle consults the controller's contracts)."""
        return self._controller.dataset_validator




    # --- the implemented M-check subset (§2.4; the class-semantic M05-M09,
    # M12, M13 remain author-side obligations, named in the guide) ---------

    def _check_m_structural(self, manifest: dict[str, Any]) -> None:
        """M01 unique/existing references, M02 length agreement, M03
        dtype/encoding consistency, M04 inline finiteness — the structural
        core. The corpus text is the authority (measurement-model §7's
        table); every refusal names its check and the offending id."""
        axes = manifest.get("axes") or []
        axis_ids = [str(axis.get("id")) for axis in axes]
        if len(set(axis_ids)) != len(axis_ids):
            raise DatasetServiceRejected("M01: duplicate axis ids in the manifest")
        by_id = {str(axis["id"]): axis for axis in axes}
        variables = manifest.get("variables") or []
        variable_ids = [str(variable.get("id")) for variable in variables]
        if len(set(variable_ids)) != len(variable_ids):
            raise DatasetServiceRejected("M01: duplicate variable ids in the manifest")
        for axis in axes:
            coordinates = axis.get("coordinates")
            if isinstance(coordinates, dict) and coordinates.get("kind") == "explicit":
                values = coordinates.get("values") or []
                if len(values) != int(axis.get("length", -1)):
                    raise DatasetServiceRejected(
                        f"M02: axis {axis['id']!r} declares length "
                        f"{axis.get('length')} but carries {len(values)} "
                        "explicit coordinates"
                    )
                self._check_finite(values, f"axis {axis['id']!r} coordinates")
            elif isinstance(coordinates, dict) and coordinates.get("kind") == "regular":
                self._check_finite(
                    [coordinates.get("start"), coordinates.get("step")],
                    f"axis {axis['id']!r} regular coordinates",
                )
        for variable in variables:
            vid = str(variable.get("id"))
            for channel_id in variable.get("channel_ids") or []:
                if channel_id not in self._channels:
                    raise DatasetServiceRejected(
                        f"M01: variable {vid!r} references channel "
                        f"{channel_id!r} which the descriptor does not declare"
                    )
            dimensions = variable.get("dimensions") or []
            lengths: list[int] = []
            for dimension in dimensions:
                axis = by_id.get(dimension)
                if axis is None:
                    raise DatasetServiceRejected(
                        f"M01: variable {vid!r} dimension {dimension!r} "
                        "names no axis in the manifest"
                    )
                lengths.append(int(axis["length"]))
            # M02 with the corpus's own arithmetic (mm.md §1/§2, wave 2's
            # narrowing): the flattened element count is the product of
            # axis lengths, WITH SCALAR PRODUCT ONE — a dimensionless
            # variable is a scalar carrying exactly one element (mm.md
            # line 12), never a free count. The ONLY suspension is the
            # DERIVED-INVALID record (mm.md 188-191): empty values AND
            # empty dimensions AND status invalid AND the §8 derivation
            # marker — a shape that was never established asserts no
            # element count.
            product = 1
            for length in lengths:
                product *= length
            derived_invalid = (
                not dimensions
                and (variable.get("values") or []) == []
                and variable.get("status") == "invalid"
                and isinstance(variable.get("derivation"), dict)
            )
            dtype = str(variable.get("dtype"))
            artifact = variable.get("artifact")
            if artifact is None:
                values = variable.get("values") or []
                if not derived_invalid and len(values) != product:
                    raise DatasetServiceRejected(
                        f"M02: variable {vid!r} carries {len(values)} inline "
                        f"values against a dimension product of {product}"
                        + (
                            " (a scalar variable carries exactly one element)"
                            if not dimensions
                            else ""
                        )
                    )
                self._check_finite(values, f"variable {vid!r} values")
            else:
                pair = self._DTYPE_ENCODING.get(dtype)
                if pair is None or pair[0] != artifact.get("encoding"):
                    raise DatasetServiceRejected(
                        f"M03: variable {vid!r} dtype {dtype!r} does not "
                        f"pair with artifact encoding "
                        f"{artifact.get('encoding')!r}"
                    )
                element_bytes = pair[1]
                if (
                    element_bytes is not None
                    and not derived_invalid
                    and int(artifact.get("byte_length", -1))
                    != product * element_bytes
                ):
                    raise DatasetServiceRejected(
                        f"M02: variable {vid!r} artifact byte_length "
                        f"{artifact.get('byte_length')} disagrees with "
                        f"{product} elements x {element_bytes} bytes"
                    )

    @staticmethod
    def _check_finite(values: Any, label: str) -> None:
        """M04: every inline ordinary numeric is finite (invalid elements
        must be explicit nulls per the schema, never NaN/Inf smuggled in
        from Python floats)."""
        for value in values:
            if type(value) is float and (value != value or value in (float("inf"), float("-inf"))):
                raise DatasetServiceRejected(
                    f"M04: {label} carry a non-finite value"
                )

    def _check_m10_correlation(
        self, manifest: dict[str, Any], operation_id: str
    ) -> None:
        """M10's correlation subset: the manifest's configuration_id /
        acquisition_id echo the invoke input's corresponding string fields
        when the dispatched action's pinned input schema declares them —
        a schema-valid result for the wrong acquisition is rejected."""
        state = self._controller.dispatch_state(operation_id)
        if state is None:
            return
        action = self._controller.action_for(state.get("action_id"))
        invoke_input = state.get("input")
        if action is None or not isinstance(invoke_input, dict):
            return
        declared = action.input_validator.schema.get("properties", {})
        if not isinstance(declared, dict):
            return
        for field in ("configuration_id", "acquisition_id"):
            if field not in declared:
                continue
            expected = invoke_input.get(field)
            if isinstance(expected, str) and manifest.get(field) != expected:
                raise DatasetServiceRejected(
                    f"M10: manifest {field} {manifest.get(field)!r} does "
                    f"not echo the invoke input's {expected!r}"
                )

    def _check_m11_records(
        self, manifest: dict[str, Any], operation_id: str
    ) -> None:
        """M11, OPERATION-scoped (Amendment 1 MEDIUM-4): every referenced
        payload artifact is one THIS operation's writer published and
        finalised, with all four record fields agreeing — an artifact
        finalised under a prior operation of the same session refuses
        (R15), and adapter-supplied digests are cross-checked against the
        writer's own record, never trusted."""
        records = self._controller.finalise_records(operation_id)
        for variable in manifest.get("variables") or []:
            vid = str(variable.get("id"))
            artifact = variable.get("artifact")
            if artifact is None:
                continue
            artifact_id = str(artifact.get("artifact_id"))
            record = records.get(artifact_id)
            if record is None:
                raise DatasetServiceRejected(
                    f"M11: variable {vid!r} references artifact "
                    f"{artifact_id!r} which THIS operation never finalised "
                    "(a prior operation's artifact is a different "
                    "acquisition)"
                )
            for field in ("artifact_id", "encoding", "byte_length", "sha256"):
                if artifact.get(field) != record.get(field):
                    raise DatasetServiceRejected(
                        f"M11: variable {vid!r} artifact field {field} "
                        f"{artifact.get(field)!r} disagrees with the "
                        f"writer's published record {record.get(field)!r}"
                    )

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
    structurally absent without the permission — spec §3/S15)."""

    _controller: DatasetController
    _content: ContentStore

    async def artifact_read(
        self,
        artifact_id: str,
        offset: int,
        length: int,
        context: Any,
    ) -> bytes:
        """Read a bounded window of an authorised artifact (spec §3; R13's
        boundary table). The corpus's "nonnegative offset" is a
        precondition this bundle REFUSES on — never the seam's clamp (the
        interface seam clamps negative offsets to zero for ITS pinned MCP
        behavior; a negative offset reaching the store's slicing reads the
        wrong window — measured: offset −1 with length 1 yields zero
        bytes eof=False, a non-terminating read loop). Authorization
        subset: artifacts belonging to datasets this run published (row
        3's wider model stays deferred). EOF and beyond-size follow the
        store's D11 contract: offset == size yields zero bytes at EOF;
        beyond size refuses."""
        if not isinstance(artifact_id, str) or not artifact_id:
            raise DatasetServiceRejected("artifact_read requires an artifact id")
        if type(offset) is not int:
            raise DatasetServiceRejected("artifact_read offset must be an integer")
        if offset < 0:
            raise DatasetServiceRejected(
                f"artifact_read offset {offset} is negative — refused, "
                "never clamped (the corpus precondition)"
            )
        if type(length) is not int or length < 1:
            raise DatasetServiceRejected("artifact_read length must be an integer >= 1")
        if not self._controller.artifact_readable(artifact_id):
            raise DatasetServiceRejected(
                f"artifact {artifact_id!r} does not belong to a dataset "
                "this run published"
            )
        try:
            chunk = self._content.artifact_chunk(artifact_id, offset, length)
        except ValueError as error:
            raise DatasetServiceRejected(f"artifact_read window refused: {error}") from error
        except KeyError as error:
            raise DatasetServiceRejected(
                f"unknown artifact id: {artifact_id!r}"
            ) from error
        window: bytes = chunk["data"]
        return window


class DatasetServicesBundle(_InvokeMembers, ScopedServicesBundle):
    """The invoke lane's standalone bundle over the scoped base — publish
    and lookup only; the payload and reader members join by permission
    through the subclasses below (structural absence, never a runtime
    flag, spec §3/S15)."""

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


class DatasetPayloadBundle(_PayloadMembers, DatasetServicesBundle):
    """invoke ∧ resolved ∧ ``artifact_writer``: the base plus the four
    payload members."""


class DatasetReaderBundle(_ReaderMembers, DatasetServicesBundle):
    """invoke ∧ resolved ∧ ``artifact_reader``: the base plus
    ``artifact_read``."""


class DatasetFullBundle(_PayloadMembers, _ReaderMembers, DatasetServicesBundle):
    """Both permissions: the complete §3 twelve-member shape."""


def attach_dataset_members(
    services: ScopedServicesBundle,
    *,
    controller: DatasetController,
    writer: CaptureStagingStore,
    channels: tuple[str, ...],
    permissions: Any,
) -> ScopedServicesBundle:
    """Compose the dataset members ONTO the adapter's existing services
    bundle by permission (the app.py wiring path). The base keeps every
    member it already has — a capturing class device keeps
    ``artifact_append``/``artifact_finalise``/``artifact_abort`` and gains
    the dataset lane it is permitted to hold; the replacement (rather
    than extension-in-place) keeps each bridge's services object
    one-shot: the adapter receives exactly one bundle at open.

    The published surface is a fresh instance of a composed class —
    ``type(services)`` plus the invoke mixin and, by permission, the
    payload and reader mixins — carrying the base's state verbatim."""
    mixins: list[type] = [_InvokeMembers]
    if ARTIFACT_WRITER in permissions:
        mixins.append(_PayloadMembers)
    if ARTIFACT_READER in permissions:
        mixins.append(_ReaderMembers)
    composed: Any = type(
        f"{type(services).__name__}Dataset",
        (*mixins, type(services)),
        {},
    )
    instance: Any = composed.__new__(composed)
    instance.__dict__.update(services.__dict__)
    instance._controller = controller
    instance._writer = writer
    instance._channels = frozenset(channels)
    result: ScopedServicesBundle = instance
    return result
