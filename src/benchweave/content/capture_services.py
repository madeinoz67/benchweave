"""Composing capture services over the staged writer (issue #43 slice 1).

The SDK §8 shape per plugin session: injected clocks read FRESH per call
(never a construction-frozen ``now`` — the ``RetainingServices``
anti-pattern the record names), evidence lands under the host-minted
context key (the caller-controlled key in the existing evidence path is a
live quota-bypass; the capture path must not inherit it), artifacts flow
through the staged writer, and transport delegates to an injected
provider or refuses loudly. Constructed without ``artifact_writer``
permission the bundle omits the three capture attributes entirely —
structural absence, not a runtime flag (spec §8/S15: only artifact_writer
permission grants these services).

The controller is the bridge-held facade (§0.3): capture control flows
through it, never through the bridge's ``self._services`` — the pinned
exercised services subset stays ``{monotonic}`` until the streaming
slice. Its abort writes the forensic record through the proven, served,
contract-legal mold (C1): the JSON payload is content-addressed as an
artifact and an ``event_log`` evidence row carries the closed doc-ref
with ``quota=None`` — a full evidence quota can never refuse a forensic
marker.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from typing import Any

from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.provider_transport import (
    declares_provider,
    provider_transport_for,
)
from benchweave.content.store import ContentStore, EvidenceQuotaExceeded
from benchweave.control.documents import adapter_permissions
from benchweave.host.types import EvidenceStamp

#: The one permission slice 1 gates on (spec §8/S15).
ARTIFACT_WRITER = "artifact_writer"

#: The bundle module's private identity token (C3 as amended: identity +
#: operation binding, never attribute presence).
_BUNDLE_STAMP_TOKEN = object()


def evidence_originated(exception: BaseException, operation_id: str) -> bool:
    """True iff the exception carries THIS module's token bound to the named
    operation — the classification discriminator for evidence-quota
    refusals raised through the bundle's record_evidence."""
    stamp = getattr(exception, "capture_stamp", None)
    return (
        isinstance(stamp, EvidenceStamp)
        and stamp.token is _BUNDLE_STAMP_TOKEN
        and stamp.operation_id == operation_id
    )


class ScopedServicesBundle:
    """The five-member ``HostServices`` shape (§8) over gateway capabilities.

    One bundle per plugin session, bound at ``open``. Clocks are injected
    callables read FRESH on every call; evidence is retained under the
    host-minted session context key on the kind-scoped accounting dimension
    (``(context_key, kind)`` — the streaming slice's quota-stack design,
    landed): the bundle's ``event_log`` rows count toward their own
    dimension, never toward another retention path's number.
    """

    def __init__(
        self,
        *,
        content: ContentStore,
        clock: Callable[[], float],
        wall: Callable[[], str],
        quota_evidence: int,
        context_key: str,
        transport: Any = None,
    ) -> None:
        self._content = content
        self._clock = clock
        self._wall = wall
        self._quota_evidence = quota_evidence
        self._context_key = context_key
        self._transport = transport

    def monotonic(self) -> float:
        """The host's monotonic clock, read fresh (seconds)."""
        return self._clock()

    def utc_now(self) -> str:
        """The host's wall clock as an ISO-8601 string, read fresh."""
        return self._wall()

    async def record_evidence(self, entry: dict[str, Any], context: Any) -> None:
        """Retain one evidence entry under the host-minted context key.

        The entry is preserved verbatim as a content-addressed artifact;
        the evidence row carries the closed ``{id, version, sha256}``
        doc-ref (the contract-legal mold) and the session context key —
        never a caller-supplied one.
        """
        now = self._wall()  # a fresh stamp per call
        blob = json.dumps(entry, sort_keys=True, default=str).encode()
        artifact_id = self._content.put_artifact(blob, now)
        reference = {
            "id": "evdoc-" + uuid.uuid4().hex,
            "version": "1",
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
        try:
            self._content.put_evidence(
                "event_log",
                reference,
                artifact_id,
                self._context_key,
                now,
                quota=self._quota_evidence,
            )
        except EvidenceQuotaExceeded as error:
            # The bundle-originated record: quota exhaustion raised through
            # adapter.execute joins the bridge's NON-POISONING classification
            # (a resource condition, not a protocol lie) — the stamp carries
            # this module's token AND the operation id, so a bare raise, a
            # forged attribute, or a saved instance replayed on another
            # dispatch stays poison.
            error.capture_stamp = EvidenceStamp(
                _BUNDLE_STAMP_TOKEN,
                getattr(context, "operation_id", None),
            )
            raise

    async def transfer(self, transaction: dict[str, Any], context: Any) -> dict[str, Any]:
        """One bounded transport exchange, through the injected provider."""
        if self._transport is None:
            raise NotImplementedError(
                "transfer: no transport is bound to this session's services"
            )
        return await self._transfer(transaction, context)

    async def _transfer(self, transaction: dict[str, Any], context: Any) -> dict[str, Any]:
        transport = self._transport
        result = transport.transfer(transaction, context)
        if hasattr(result, "__await__"):
            outcome: dict[str, Any] = await result
            return outcome
        answer: dict[str, Any] = result
        return answer

    async def close_transport(self, context: Any) -> None:
        """Close the session's transport, through the injected provider."""
        if self._transport is None:
            raise NotImplementedError(
                "close_transport: no transport is bound to this session's services"
            )
        closer = self._transport.close_transport
        result = closer(context)
        if hasattr(result, "__await__"):
            await result


class CaptureServicesBundle(ScopedServicesBundle):
    """The eight-member ``CaptureServices`` shape (§8): the scoped services
    plus the three capture methods over the staged writer. One capture in
    flight per services instance."""

    def __init__(self, *, writer: CaptureStagingStore, **base: Any) -> None:
        super().__init__(**base)
        self._writer = writer

    async def artifact_append(self, capture_id: str, data: bytes, context: Any) -> None:
        """Append one chunk through the staged writer (the writer's own
        reservation, session and stamping rules apply)."""
        self._writer.append(capture_id, data, self._context_key)

    async def artifact_abort(self, capture_id: str) -> None:
        """Abort through the writer — idempotent, publishes nothing, and a
        no-op retract after finalise."""
        self._writer.abort(capture_id)

    async def artifact_finalise(
        self, capture_id: str, metadata: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        """Validate the adapter's finalise metadata, publish through the
        writer, and return the complete manifest.

        The adapter supplies the format, the capture's start time and the
        optional waveform metadata (spec §8: finalise "accepts format/start
        time and optional waveform metadata"); the writer computes the
        digest and length over the real bytes, and the manifest's
        host-managed fields come from the writer's published record —
        adapter-supplied values cannot override them.
        """
        if not isinstance(metadata, dict):
            raise ValueError("finalise metadata must be an object")
        fmt = metadata.get("format")
        if not isinstance(fmt, str) or not fmt:
            raise ValueError("finalise metadata requires a format string")
        started_at = metadata.get("started_at")
        if not isinstance(started_at, str) or not started_at:
            raise ValueError("finalise metadata requires a non-empty started_at")
        # The manifest's format echoes the OPENED capture (the dispatch
        # request's format, the host-side authority) — an adapter-declared
        # disagreement is refused before anything publishes.
        staged = self._writer.staged_capture(capture_id)
        if staged is None:
            raise ValueError(f"no staged capture {capture_id!r} to finalise")
        if fmt != staged["format"]:
            raise ValueError(
                f"finalise format {fmt!r} disagrees with the opened capture's"
                f" format {staged['format']!r}"
            )
        if fmt == "waveform_f64le":
            # sample_interval_s and unit arrive ONLY through the adapter's
            # metadata (the two-sided manifest contract); sample_count is
            # host-authoritative — it echoes the dispatch request via the
            # staging row.
            for field in ("sample_interval_s", "unit"):
                if field not in metadata:
                    raise ValueError(
                        "waveform_f64le finalise requires waveform metadata: "
                        f"{field} is mandatory (the corpus captureManifest allOf)"
                    )
        record = self._writer.finalise(
            capture_id, self._wall(), self._context_key
        )  # fresh stamp
        manifest: dict[str, Any] = {
            "capture_id": capture_id,
            "format": fmt,
            "artifact_id": record["artifact_id"],
            "byte_length": record["byte_length"],
            "sha256": record["sha256"],
            "started_at": started_at,
        }
        if fmt == "waveform_f64le":
            manifest["sample_count"] = staged["sample_count"]
            manifest["sample_interval_s"] = metadata["sample_interval_s"]
            manifest["unit"] = metadata["unit"]
        return manifest


class CaptureController:
    """The bridge-held facade over the staged writer (§0.3).

    Capture control flows through this object, never through the bridge's
    services; the writer is the session's ONE instance, shared with the
    bundle. ``abort`` reclaims and writes the forensic record exactly once
    per capture (a controller-side record, not a class-name coincidence);
    ``sweep_open`` is ``plugin_close``'s in-process retry over still-open
    captures.
    """

    def __init__(
        self,
        *,
        writer: CaptureStagingStore,
        content: ContentStore,
        context_key: str,
        wall: Callable[[], str],
    ) -> None:
        self._writer = writer
        self._content = content
        self._context_key = context_key
        self._wall = wall
        self._open: dict[str, int] = {}  # capture_id -> reserved_bytes
        self._recorded: set[str] = set()

    def open_capture(
        self, *, capture_id: str, fmt: str, sample_count: int | None, max_bytes: int
    ) -> None:
        """Open a capture on the session's context key (the bridge has
        already validated the id shape; the writer's PRIMARY KEY enforces
        session-uniqueness)."""
        self._writer.open_capture(
            capture_id=capture_id,
            context_key=self._context_key,
            fmt=fmt,
            sample_count=sample_count,
            max_bytes=max_bytes,
            now=self._wall(),
        )
        # The once-guard keys LIFECYCLE, not identity: a same-id retry (legal
        # — a prior abort deleted the staging row, so the writer re-opens
        # it) gets a fresh forensic lifecycle. A stale _recorded entry would
        # suppress the retry's abort and leak its row + reservation.
        self._recorded.discard(capture_id)
        self._open[capture_id] = max_bytes

    def finalise_record(self, capture_id: str) -> dict[str, Any] | None:
        """The writer's published record, for the bridge's G4 cross-checks."""
        return self._writer.finalise_record(capture_id)

    def retire(self, capture_id: str) -> None:
        """Retire a SUCCESSFULLY completed capture: no forensic record, no
        sweep at close — a published, acknowledged capture stands."""
        self._open.pop(capture_id, None)
        self._recorded.discard(capture_id)

    def abort(self, capture_id: str, *, reason: str, operation_id: str | None) -> bool:
        """Reclaim the capture and write its forensic record — once.

        Returns False without writing anything for a capture this
        controller never opened or already recorded (the epilogue's
        no-spurious-markers rule). The forensic mold (C1): the JSON payload
        ``{capture_id, operation_id, reason, staged_bytes, reserved_bytes}``
        is content-addressed as an artifact, then an ``event_log`` evidence
        row carries the closed doc-ref ``{id: capture_id, version: "1",
        sha256}`` with ``quota=None`` — durable, caller-visible through
        ``stg_v1_evidence_get``, and legal by isomorphism with the shape
        ``retain_evidence`` serves today.
        """
        if capture_id not in self._open or capture_id in self._recorded:
            return False
        reserved = self._open[capture_id]
        staged = self._writer.staged_bytes(capture_id)
        published = self._writer.finalise_record(capture_id)
        reclaimed = self._writer.abort(capture_id)
        payload = {
            "capture_id": capture_id,
            "operation_id": operation_id,
            # None for a plain abort; the artifact id when the capture
            # published and the dispatch then failed (the refused-after-
            # publish and late-after-publish arms route identically — the
            # payload's artifact_id distinguishes published cases).
            "artifact_id": published["artifact_id"] if published else None,
            "reason": reason,
            "staged_bytes": staged,
            "reserved_bytes": reserved,
        }
        blob = json.dumps(payload, sort_keys=True).encode()
        now = self._wall()  # a fresh stamp per record
        artifact_id = self._content.put_artifact(blob, now)
        reference = {
            "id": capture_id,
            "version": "1",
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
        self._content.put_evidence(
            "event_log", reference, artifact_id, self._context_key, now, quota=None
        )
        # Only NOW is the forensic record durable: retire from _open and mark
        # recorded AFTER the writes land. A forensic-write failure (suppressed
        # by the bridge's containment) leaves the capture in _open, so
        # plugin_close's sweep — B15-iii's designated in-process retry —
        # retries the record instead of losing it permanently. The retry's
        # payload then reflects post-reclaim state (staged_bytes zero): an
        # honest record of the retry, not of the failed first attempt.
        self._open.pop(capture_id, None)
        self._recorded.add(capture_id)
        return reclaimed

    def sweep_open(self, *, reason: str) -> list[str]:
        """Abort every still-open capture (plugin_close's in-process retry);
        each gets its own forensic record."""
        reclaimed: list[str] = []
        for capture_id in sorted(self._open):
            if self.abort(capture_id, reason=reason, operation_id=None) or (
                capture_id in self._recorded
            ):
                reclaimed.append(capture_id)
        return reclaimed


def build_capture_services(
    *,
    descriptor_digest: str,
    content: ContentStore,
    writer: CaptureStagingStore,
    clock: Callable[[], float],
    wall: Callable[[], str],
    quota: Any,
    context_key: str,
    transport: Any = None,
    providers: Any = None,
) -> tuple[ScopedServicesBundle, CaptureController | None]:
    """The permission gate's construction point (A11/A17).

    Re-derives the RAW full-form descriptor by pinned digest (one
    ``get_document`` call — the CON-10 projection drops ``integration``, so
    the raw form is the only permission source) and returns either the
    eight-member capture bundle with its controller, or — without the
    ``artifact_writer`` permission — the five-member scoped bundle with NO
    controller: no capture writer exists at all.

    The provider grant (issue #147 increment 3): when the re-derived raw
    descriptor declares a transport provider and a validated
    ``providers`` registry is supplied, the transport is the GRANT's —
    the grammar guard over the admitted contract, or a bound refusal
    naming the failed check (permission / admission / resolution) — never
    the caller's injection. A provider-less descriptor is untouched: the
    caller's ``transport`` stands exactly as before.
    """
    document = content.get_document(descriptor_digest)
    if document is None:
        raise ValueError(
            "raw descriptor not cached at its pinned digest: the capture "
            "factory re-derives the full form from the content store "
            f"(digest {descriptor_digest[:12]}… is absent — descriptors are "
            "cached when a binding pins them)"
        )
    permissions = adapter_permissions(document["content"])
    if declares_provider(document["content"]):
        transport = provider_transport_for(document["content"], providers)
    quota_evidence = int(quota.max_evidence_entries)
    if ARTIFACT_WRITER in permissions:
        bundle = CaptureServicesBundle(
            content=content,
            clock=clock,
            wall=wall,
            quota_evidence=quota_evidence,
            context_key=context_key,
            transport=transport,
            writer=writer,
        )
        controller = CaptureController(
            writer=writer,
            content=content,
            context_key=context_key,
            wall=wall,
        )
        return bundle, controller
    scoped = ScopedServicesBundle(
        content=content,
        clock=clock,
        wall=wall,
        quota_evidence=quota_evidence,
        context_key=context_key,
        transport=transport,
    )
    return scoped, None

