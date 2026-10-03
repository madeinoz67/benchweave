"""Device-page reading tiles populated from retained observations
(issue #369, design record 2026-10-03 — Fork A, the evidence join).

The one durable, parameter-keyed, schema-validated observation carrier is
the telemetry event lane: events land transactionally as ``event_log``
evidence under the run's context key, the event JSON content-addressed as
an artifact whose id embeds its digest. The frozen seam cannot enumerate
those rows (``evidence_get`` needs an id the wire never hands out), so
this module joins at composition time — the ruled boundary CON-5's
amendment names: read-only, bench-scoped by construction, every rendered
value digest-verified gateway evidence or the honest ``Unavailable``
(GW-22's floor stays the failure mode of every hop).

The join trusts exactly two mechanisms and nothing else: the artifact's
digest (computed here over the served bytes — never the store row's own
self-referential sha256, the #372 H2 discipline) and the landing lane's
OWN reading validator (``OTDPBridge._event_reading``) — a local, weaker
copy of the validation is the fabrication seam this module exists to
close. Every other shape surprise skips its row: never rendered, never
crashed, one bad row never aborts the join.

Honest limits, disclosed on the page rather than hidden: only parameters
whose plugin subscribes and streams telemetry populate (executor
read-step values are not retained — the run-step envelope carries no
value); recency is the OBSERVATION's own ``observed_at`` (GW-23), never
run order; the provenance line names the run so a stale retained value
never reads as a live reading; and outside a live run a retained
observation is usually stale — ST-2 says that verdict is correct, not
broken.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from benchweave.content.store import MAX_CHUNK_BYTES, ContentStore
from benchweave.host.otdp_bridge import InvalidEvent, OTDPBridge
from benchweave.interfaces.ui_presentation import (
    PresentationState,
    reading_staleness,
)
from benchweave.state.store import Store

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetainedReading:
    """One digest-verified telemetry reading retained under a run's
    context key — everything the tile renders, nothing invented."""

    parameter: str
    value: str | float | int | bool  # finite scalar, exactly as landed
    unit: str | None
    observed_at: str  # the reading's OWN stamp (GW-23)
    age_ms_at_land: int
    quality: str  # valid | stale | invalid
    source: str  # device | cache | commissioned
    run_id: str
    stored_at: str


def _verified_payload(
    content: ContentStore, artifact_id: str, expected_sha256: str
) -> bytes | None:
    """One digest-verified artifact read, or ``None`` (skip, never
    render, never crash) on any mismatch. The digest is computed HERE
    over the served bytes and checked against BOTH the evidence
    reference's sha256 and the ADMISSION identity embedded in the
    artifact id (``art-<sha256>``) — the row's own sha256 field is
    derived from the same row being read and proves nothing about it
    (the #372 H2 discipline). A payload larger than one chunk is not a
    tile-shaped event and is skipped rather than reassembled."""
    try:
        chunk = content.artifact_chunk(artifact_id, 0, MAX_CHUNK_BYTES)
    except (KeyError, ValueError):
        return None
    window = chunk["data"]
    if not isinstance(window, (bytes, bytearray)):
        return None
    payload = bytes(window)
    if int(chunk["bytes"]) != int(chunk["total_bytes"]):
        return None
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256 or artifact_id != f"art-{digest}":
        return None
    return payload


def _parse_observed(observed_at: str) -> datetime | None:
    """The observation's own stamp as a comparable instant (a naive
    value reads as UTC, the binding module's convention); ``None`` when
    unparseable — a reading whose recency cannot be established cannot
    be attributed a win."""
    try:
        moment = datetime.fromisoformat(observed_at)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


def latest_retained_readings(
    store: Store,
    content: ContentStore,
    *,
    bench_id: str,
    device_id: str,
    sibling_parameter_owners: Mapping[str, int],
    now_epoch_ms: int,
    scan_rows: int,
) -> dict[str, RetainedReading]:
    """The newest digest-verified reading per parameter this device's
    tiles may render, from runs on THIS bench that bind THIS device.

    The join, newest-first and budget-bounded (design §4): runs by
    ``updated_at`` descending, evidence rows by ``stored_at`` descending
    (the store method's order), recency decided by the observation's OWN
    ``observed_at`` — never run order. ``scan_rows`` bounds ARTIFACT
    OPENS (every payload the join attempts to read, verified or not —
    counting only successful decodes left failing rows unbounded, the
    fold's F2) and the walk stops the moment the budget fills, so no
    further run reads or evidence queries fire. ``now_epoch_ms`` is
    accepted and unused here on purpose: recency inside the join is the
    observation's own stamp; the RENDER clock belongs to
    :func:`populate_tiles` (the design's split — the join is pure over
    retained bytes, the verdict is computed at render).

    There is deliberately NO found-everything early stop (a deviation
    from the design's §4 step 9, reported at review): an early stop on
    first-found would freeze an older observation whenever a newer
    run's reading is older than a first-found one — exactly the case
    arm A8 pins as wrong. The budget is the only work bound; the
    expensive case (many telemetry-free runs) is bounded by the bench's
    run count, not by an early stop. A parameter declared by more than
    one bench device yields NO reading for this render — no attribution
    guess (A7). Tombstoned runs are not skipped: their retained evidence
    is retained truth.

    Attribution is parameter-name-only and CANNOT identify which bound
    device's plugin streamed a reading (the fold's F1): the landing lane
    records subscription_id on the evidence reference but no device
    identity — every device in a run shares the one ``run:<id>`` context
    key and the subscription registry is in-memory — so a sibling
    bound by the same run whose plugin streams a parameter it does not
    declare is NOT caught by the census (see the census clause in
    ``ui_read.device_page`` and the #369 fold addendum for the carrier).
    """
    found: dict[str, RetainedReading] = {}
    newest: dict[str, datetime] = {}
    runs = sorted(
        store.list_run_states(bench_id),
        key=lambda row: str(row["updated_at"]),
        reverse=True,
    )
    opened = 0
    for run in runs:
        if opened >= scan_rows:
            break
        run_id = str(run["run_id"])
        record = store.get_run(run_id)
        if record is None:
            continue
        binding = record.get("binding")
        entries = binding.get("bindings", []) if isinstance(binding, dict) else []
        bound = {
            str(entry.get("device_id", ""))
            for entry in entries
            if isinstance(entry, dict)
        }
        if device_id not in bound:
            continue
        rows = content.evidence_rows_by_context(f"run:{run_id}", limit=scan_rows)
        for row in rows:
            if opened >= scan_rows:
                break
            reference = row["content_ref"]
            if not isinstance(reference, dict):
                continue
            if reference.get("kind") != "telemetry":
                # Plugin record_evidence rows land the same evidence kind
                # with a bare doc-ref and no telemetry fields; teardown
                # and gap markers carry their own marker fields — both
                # are excluded structurally, not by string matching.
                continue
            artifact_id = row["artifact_id"]
            if not isinstance(artifact_id, str) or not isinstance(
                reference.get("sha256"), str
            ):
                continue
            # F2: every attempt counts — an open that fails verification
            # is the cheap-to-forget case that left the walk unbounded.
            opened += 1
            payload = _verified_payload(content, artifact_id, reference["sha256"])
            if payload is None:
                continue
            try:
                event = json.loads(payload)
            except ValueError:
                continue
            reading = event.get("reading") if isinstance(event, dict) else None
            if not isinstance(reading, dict):
                continue
            try:
                OTDPBridge._event_reading(reading)
            except InvalidEvent:
                continue
            parameter = str(reading["parameter"])
            if sibling_parameter_owners.get(parameter) != 1:
                # Unknown here, or declared by more than one bench
                # device: no attribution guess (A7).
                continue
            value = reading["value"]
            if value is None or isinstance(value, (dict, list)):
                # Schema-legal null compounds nothing — a valueless
                # reading renders nothing (never "None" on a tile).
                continue
            observed_at = str(reading["observed_at"])
            moment = _parse_observed(observed_at)
            if moment is None:
                continue
            if parameter in found and moment <= newest[parameter]:
                continue
            unit = reading["unit"]
            found[parameter] = RetainedReading(
                parameter=parameter,
                value=value,
                unit=unit if isinstance(unit, str) else None,
                observed_at=observed_at,
                age_ms_at_land=int(reading["age_ms"]),
                quality=str(reading["quality"]),
                source=str(reading["source"]),
                run_id=run_id,
                stored_at=str(row["stored_at"]),
            )
            newest[parameter] = moment
    return found


def populate_tiles(
    state: PresentationState,
    readings: Mapping[str, RetainedReading],
    descriptor: Mapping[str, Any],
    *,
    now_epoch_ms: int,
) -> PresentationState:
    """A pure function over the frozen state: tiles whose parameter has
    a retained reading render its value, quality and the observation's
    own stamp with the provenance line naming the run; staleness is
    ``reading_staleness`` against the parameter's own declared
    ``read_policy.max_age_ms`` (ST-1/ST-2/ST-3 — a parameter without a
    window renders no verdict, never an invented one). A reading whose
    unit disagrees with the tile's declared unit renders the READING's
    unit — the mismatch is visible, not silently reconciled. Everything
    else keeps the conservative GW-22 floor."""
    parameters = {
        str(row.get("name", "")): row
        for row in descriptor.get("parameters", [])
        if isinstance(row, dict)
    }
    pages = []
    for page in state.pages:
        if not page.tiles:
            pages.append(page)
            continue
        tiles = []
        for tile in page.tiles:
            key = tile.parameter_id
            reading = readings.get(key) if key is not None else None
            if key is None or reading is None:
                tiles.append(tile)
                continue
            window: float | None = None
            policy = parameters.get(key, {}).get("read_policy")
            if isinstance(policy, dict):
                raw = policy.get("max_age_ms")
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    window = float(raw)
            moment = _parse_observed(reading.observed_at)
            freshness_ms: float | None = (
                now_epoch_ms - round(moment.timestamp() * 1000)
                if moment is not None
                else None
            )
            unit = tile.unit
            if reading.unit is not None and reading.unit != tile.unit:
                unit = reading.unit
            tiles.append(
                replace(
                    tile,
                    value=str(reading.value),
                    unit=unit,
                    quality=reading.quality,
                    freshness=(
                        f"{reading.observed_at}"
                        f" (retained observation from run {reading.run_id})"
                    ),
                    stale_verdict=reading_staleness(freshness_ms, window),
                )
            )
        pages.append(replace(page, tiles=tuple(tiles)))
    return replace(state, pages=tuple(pages))
