"""The streaming services: subscription registry and event landing
(issue #43 slice 2, Decision 4).

The bridge-held facade over the evidence path — the streaming sibling of
``CaptureController``. Three responsibilities, all host-side:

* **The subscription registry.** Subscription ids are host-minted uuid4
  opaques (:func:`mint_subscription_id`); the registry keys on the full id
  only — host code never parses structure out of it, so the format stays
  reversible. Reservations are check-and-reserve at gate time against the
  host ceiling (``QuotaLimits.max_subscriptions``); a dispatch that fails
  releases its slot. Ended and closed subscriptions stay REGISTERED (the
  refusal taxonomy needs known-but-ended to be a clean refusal), they just
  stop being live.
* **Event landing (the one-way door).** Event rows land as ``event_log``
  kind evidence under the session context key on the kind-scoped
  accounting dimension, transactionally per batch, each batch bounded by
  ``max_event_batch``. The content_ref carries the Decision-4 landing
  contract from event one — ``{subscription_id, sequence, kind,
  host_received_at, payload digest, capture/dataset linkage}`` — because
  retrofitting these fields after accumulation would be a data migration.
* **Teardown and gap honesty.** A host-cause teardown (quota exhaustion,
  poison, plugin close) writes an ``ended`` marker evidence row with
  ``quota=None`` — the C1 forensic mold: a full evidence quota can never
  refuse a teardown marker. A forward sequence jump with no preceding
  ``gap`` event is not protocol-refusable, so the HOST records it as an
  evidence annotation (R4 pins this host mechanism, not the fixture's
  emission duty).

No store migration: event rows ride the existing evidence tables (the
record's slice-2 note — slice 1 landed the capture tables; events land as
evidence).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.control.documents import adapter_permissions
from benchweave.host.services import QuotaLimits, ReadingSinks
from benchweave.state.store import Store

#: The one permission slice 2 gates on (spec §8/S15: "Event production uses
#: next_event and requires ``event_sink`` permission for streaming adapters").
EVENT_SINK = "event_sink"

#: The landing kind — Decision 4: event rows land as ``event_log``-kind
#: evidence, sharing the kind-scoped dimension with the bundle's
#: ``record_evidence`` entries and forensic abort markers (conservative for
#: the stream: its ceiling fills no later).
EVENT_KIND = "event_log"

_ACTIVE = "active"
_ENDED = "ended"  # adapter ``ended`` event or host-cause teardown
_CLOSED = "closed"  # a successful explicit unsubscribe


def mint_subscription_id() -> str:
    """A host-minted globally-unique uuid4 opaque (mirroring the bridge's
    operation ids). The registry keys on the full id only, so the format
    stays reversible — callers must not embed structure in it."""
    return str(uuid.uuid4())


class StreamLimitExceeded(RuntimeError):
    """The host subscription ceiling (``QuotaLimits.max_subscriptions``)
    refused a reservation. A resource condition, never a protocol lie: the
    bridge maps it to a clean ``RESOURCE_LIMIT`` refusal, not_dispatched."""


@dataclass(frozen=True)
class LandedEvent:
    """One validated event paired with its host receipt stamp — the receipt
    moment is when the host's poll accepted the event, not landing time."""

    event: dict[str, Any]
    host_received_at: str


@dataclass
class _Subscription:
    """The registry entry: everything the refusal taxonomy and the landing
    linkage need, keyed on the full subscription id."""

    subscription_id: str
    parameters: tuple[str, ...]
    min_interval_ms: int
    state: str = _ACTIVE
    last_sequence: int | None = None
    last_kind: str | None = None
    # Capture/dataset linkage (the landing contract's field pair): None on
    # the core lane — the dataset slice's reservation is the setter.
    capture_id: str | None = None
    dataset_id: str | None = None


class StreamController:
    """The bridge-held streaming facade (Decision 4): registry, landing,
    teardown markers, gap honesty."""

    def __init__(
        self,
        *,
        store: Store,
        context_key: str,
        wall: Callable[[], str],
        quota: QuotaLimits,
        reading_sinks: ReadingSinks | None = None,
    ) -> None:
        self._conn = store.connection
        self._content = ContentStore(store)
        self._context_key = context_key
        self._wall = wall
        self._quota = quota
        self._sinks = reading_sinks
        self._subscriptions: dict[str, _Subscription] = {}

    # --- the registry ------------------------------------------------------------

    def reserve(
        self, *, subscription_id: str, parameters: tuple[str, ...], min_interval_ms: int
    ) -> None:
        """Check-and-reserve one subscription slot at gate time (the G3
        mirror: the slot is consumed before the adapter is called).

        Raises :class:`StreamLimitExceeded` when the host ceiling is full;
        ``ValueError`` for a duplicate id (a host-caller bug — ids are
        minted, and the registry is the uniqueness authority; checked
        FIRST so a caller bug surfaces at any occupancy)."""
        if subscription_id in self._subscriptions:
            raise ValueError(f"subscription id already registered: {subscription_id!r}")
        live = sum(1 for entry in self._subscriptions.values() if entry.state == _ACTIVE)
        if live + 1 > int(self._quota.max_subscriptions):
            raise StreamLimitExceeded(
                f"host subscription ceiling {self._quota.max_subscriptions} reached "
                f"({live} live) for {self._context_key!r}"
            )
        self._subscriptions[subscription_id] = _Subscription(
            subscription_id=subscription_id,
            parameters=parameters,
            min_interval_ms=min_interval_ms,
        )

    def release(self, subscription_id: str) -> bool:
        """Drop a reservation whose dispatch failed: nothing streamed, so
        no teardown marker — the subscription never went live (the A6
        no-epilogue mirror)."""
        entry = self._subscriptions.get(subscription_id)
        if entry is None or entry.state != _ACTIVE:
            return False
        del self._subscriptions[subscription_id]
        return True

    def subscription(self, subscription_id: str) -> _Subscription | None:
        """The registry entry (the bridge's refusal-taxonomy read)."""
        return self._subscriptions.get(subscription_id)

    def is_known(self, subscription_id: str) -> bool:
        """True iff the registry holds the id at all (live, ended or closed)."""
        return subscription_id in self._subscriptions

    def is_live(self, subscription_id: str) -> bool:
        """True iff the subscription is still pollable."""
        entry = self._subscriptions.get(subscription_id)
        return entry is not None and entry.state == _ACTIVE

    def live_subscription_ids(self) -> list[str]:
        """The ids still pollable, sorted for deterministic rotation."""
        return sorted(
            subscription_id
            for subscription_id, entry in self._subscriptions.items()
            if entry.state == _ACTIVE
        )

    def record_event(self, subscription_id: str, *, sequence: int, kind: str) -> None:
        """Advance the per-subscription stream state after a validated
        event. An ``ended`` event is terminal: the subscription stops being
        live (it stays registered — known-but-ended)."""
        entry = self._subscriptions.get(subscription_id)
        if entry is None:
            raise ValueError(f"unknown subscription: {subscription_id!r}")
        entry.last_sequence = sequence
        entry.last_kind = kind
        if kind == "ended":
            entry.state = _ENDED

    def mark_closed(self, subscription_id: str) -> bool:
        """A successful explicit unsubscribe: the subscription closes
        without a marker (the unsubscribe result is the record)."""
        entry = self._subscriptions.get(subscription_id)
        if entry is None or entry.state != _ACTIVE:
            return False
        entry.state = _CLOSED
        return True

    def mark_ended(self, subscription_id: str, *, cause: str) -> bool:
        """Host-cause teardown: registry ``ended`` plus the marker row
        (quota=None). False for an unknown or already-terminal subscription
        — no spurious markers."""
        entry = self._subscriptions.get(subscription_id)
        if entry is None or entry.state != _ACTIVE:
            return False
        entry.state = _ENDED
        self._marker(
            subscription_id,
            marker="host_ended",
            cause=cause,
        )
        return True

    def sweep(self, *, reason: str) -> list[str]:
        """Tear down every live subscription with a host-cause ``ended``
        marker (``plugin_close`` and poison both arrive here — no stream
        outlives its host-owned subscription authority). Ended/closed
        entries stay registered for honest refusal; only live ones tear
        down."""
        torn: list[str] = []
        for subscription_id in sorted(self._subscriptions):
            entry = self._subscriptions[subscription_id]
            if entry.state != _ACTIVE:
                continue
            entry.state = _ENDED
            self._marker(subscription_id, marker="host_ended", cause=reason)
            torn.append(subscription_id)
        return torn

    # --- gap honesty ---------------------------------------------------------------

    def note_sequence_jump(
        self, subscription_id: str, *, from_sequence: int, to_sequence: int
    ) -> None:
        """The host's jump-without-gap evidence annotation (R4's pinned
        mechanism): a forward sequence jump the stream did not preface with
        a ``gap`` event is recorded, never silently accepted as contiguous."""
        self._marker(
            subscription_id,
            marker="sequence_jump_without_gap",
            cause="forward sequence jump with no preceding gap event",
            from_sequence=from_sequence,
            to_sequence=to_sequence,
        )

    # --- the landing ------------------------------------------------------------------

    def land_events(self, entries: list[LandedEvent]) -> list[str]:
        """Land one batch of validated events as ``event_log`` evidence,
        transactionally: the kind-scoped ceiling is checked per row inside
        the transaction (rows landed earlier in the batch count), so an
        exhausted ceiling mid-batch rolls the WHOLE batch back — the
        partial-batch posture is refused, not half-landed.

        ``max_event_batch`` bounds each landing batch (a host-side contract
        violation is refused loudly, never silently split). Telemetry
        readings are delivered to the registered sinks after the batch
        commits (contained — a raising sink never fails a landed batch)."""
        if not entries:
            return []
        bound = int(self._quota.max_event_batch)
        if len(entries) > bound:
            raise ValueError(
                f"landing batch {len(entries)} exceeds max_event_batch {bound}"
            )
        evidence_ids: list[str] = []
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            for entry in entries:
                event = entry.event
                subscription = self._subscriptions.get(str(event["subscription_id"]))
                payload = json.dumps(event, sort_keys=True, default=str).encode()
                digest = hashlib.sha256(payload).hexdigest()
                artifact_id = self._content.put_artifact(payload, entry.host_received_at)
                reference: dict[str, Any] = {
                    "id": str(event["subscription_id"]),
                    "version": "1",
                    "sha256": digest,
                    "subscription_id": str(event["subscription_id"]),
                    "sequence": event["sequence"],
                    "kind": event["kind"],
                    "host_received_at": entry.host_received_at,
                    # The capture/dataset linkage lands from event one (the
                    # one-way door): the reservation's linkage, explicit
                    # nulls on the core lane.
                    "capture_id": subscription.capture_id if subscription else None,
                    "dataset_id": subscription.dataset_id if subscription else None,
                }
                evidence_ids.append(
                    self._content.put_evidence(
                        EVENT_KIND,
                        reference,
                        artifact_id,
                        self._context_key,
                        entry.host_received_at,
                        quota=int(self._quota.max_evidence_entries),
                    )
                )
            self._conn.execute("COMMIT")
        except BaseException:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        if self._sinks is not None:
            for entry in entries:
                if entry.event.get("kind") == "telemetry":
                    self._sinks.deliver(entry.event.get("reading"))
        return evidence_ids

    # --- the marker mold ------------------------------------------------------------

    def _marker(
        self, subscription_id: str, *, marker: str, cause: str, **extra: Any
    ) -> None:
        """The C1 forensic mold, streaming: payload content-addressed, an
        ``event_log`` row carrying the marker fields with ``quota=None`` —
        a full evidence quota can never refuse a teardown or annotation
        marker."""
        payload = {
            "subscription_id": subscription_id,
            "marker": marker,
            "cause": cause,
            **extra,
        }
        blob = json.dumps(payload, sort_keys=True).encode()
        now = self._wall()  # a fresh stamp per marker
        artifact_id = self._content.put_artifact(blob, now)
        reference = {
            "id": subscription_id,
            "version": "1",
            "sha256": hashlib.sha256(blob).hexdigest(),
            "marker": marker,
            "cause": cause,
            **extra,
        }
        self._content.put_evidence(
            EVENT_KIND, reference, artifact_id, self._context_key, now, quota=None
        )


def build_stream_services(
    *,
    descriptor_digest: str,
    store: Store,
    wall: Callable[[], str],
    quota: QuotaLimits,
    context_key: str,
    reading_sinks: ReadingSinks | None = None,
) -> StreamController | None:
    """The event_sink permission gate's construction point (spec §8/S15 —
    the streaming sibling of ``build_capture_services``).

    Re-derives the RAW full-form descriptor by pinned digest (the CON-10
    projection drops ``integration``, so the raw form is the only
    permission source) and returns the stream controller, or — without the
    ``event_sink`` permission — ``None``: no event services exist at all,
    and the bridge refuses ``stream_subscribe`` ``not_dispatched`` at the
    gate.
    """
    content = ContentStore(store)
    document = content.get_document(descriptor_digest)
    if document is None:
        raise ValueError(
            "raw descriptor not cached at its pinned digest: the stream "
            "factory re-derives the full form from the content store "
            f"(digest {descriptor_digest[:12]}… is absent — descriptors are "
            "cached when a binding pins them)"
        )
    permissions = adapter_permissions(document["content"])
    if EVENT_SINK in permissions:
        return StreamController(
            store=store,
            context_key=context_key,
            wall=wall,
            quota=quota,
            reading_sinks=reading_sinks,
        )
    return None
