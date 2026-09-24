"""Issue #43 slice 3 (Decision 8): the retention report — pure projection.

The mirror of :mod:`benchweave.cli.report` (``build_report`` →
:func:`build_retention_report`; ``report_from_data_dir`` →
:func:`retention_from_data_dir`; ``render_markdown``/``render_json``;
caller-injected ``now`` — the model never reads a clock). The standing
rule (the record's Decision 8): **slice 3 writes nothing back** — no
data-class stamps into durable rows, no cached disposal dates, no
write-back of any projection result; S3-1 pins this over every table in
the store — and (issue #184 fork A) a retention run NEVER migrates the
store: a schema mismatch (pending migrations, or a store newer than the
gateway) refuses with the typed ``retention_store:`` family, naming the
mismatch (S3-1's down-level arm pins the no-write-back claim over
``schema_migrations``). Nothing here deletes or archives:
``on_disposition`` is a report label only, and no automated disposition
ships until the disposition-audit-trail slice (the record's sequencing
invariant).

Disclosed derivations:

- **Governed rows.** Finalised ``capture_staging`` rows (charged bytes +
  the artifact link) and every ``evidence`` row, enumerated in stored
  order over the store connection exactly like
  ``cli/report.py::_evidence_rows`` (the WP07 content tables have no list
  API). Non-finalised staging rows are NOT governed — they are disclosed
  as a count ("reclaimed by the next startup sweep").
- **Classification is report-time** (the record's join-key rule): captures
  read ``capture:<format>`` from ``capture_staging.format`` (NULL/unknown
  → ``capture:unknown``; the in-tree format vocabulary is
  ``host/otdp_bridge.py``'s ``("waveform_f64le", "raw_binary")``);
  evidence reads its literal ``evidence:<kind>`` — an open vocabulary, so
  a novel kind gets its literal class and falls to the default.
- **Anchors.** ``landing`` resolves from ``evidence.stored_at`` or, for
  captures, the finalise-time ``capture_staging.updated_at`` (the staging
  table's stored-at analogue — disclosed; no migration is permitted this
  slice). ``run_end`` resolves to the owning run's TERMINAL RECORD
  ``ended_at`` (``runs.terminal_json`` — written once at finalise by
  ``build_terminal_record`` and never moved). A ``run_end`` row whose run
  has no terminal record (live, interrupted, closed-without-record) or is
  unattributed yields status ``anchor_unresolved`` with
  ``disposal_date: null`` — never a substituted anchor. Every stamp parses
  defensively (issue #184 fork C): naive (no offset) or unparseable stamps
  resolve to nothing rather than a host-timezone-localized guess, so the
  report is byte-identical under any host ``TZ`` and no single stamp can
  crash the build (no escaping ``TypeError``/``OverflowError``/
  ``ValueError``).
- **Byte accounting.** Stored bytes are ``SELECT SUM(LENGTH(data)) FROM
  artifacts`` — the artifact table is the source of truth and
  content-addressed dedup UNDER-counts (the honest direction); both
  emitters label the method. Ingest rates anchor on immutable per-row
  stamps (``evidence.stored_at``, ``capture_staging.updated_at``) and
  never on ``artifacts.stored_at`` — that column refreshes on re-put, so
  a re-put of identical bytes changes no report figure (S3-6's companion
  arm).
- **Growth projection (issue #184 fork B).** Per subscription from landed
  ``event_log`` ``content_ref`` (``subscription_id``/``host_received_at``
  — the fields ``stream_services.land_events`` lands) and per capture
  context key: the wire carries ``observed_bytes``, ``observed_span_s``,
  ``n``, ``rate_Bps = observed_bytes / observed_span_s`` and
  ``projected_horizon_bytes = rate_Bps × horizon_s`` — ONE operator-
  chosen horizon (``--horizon-s``, default 30 days) for every row, so
  projections are comparable and no report-global window couples one
  stream's rows to another's (the old rate × duty × window algebra
  cancelled the span into a global-window rescale: an old row in one key
  shrank another key's projection). Stamps parse, then compare as
  instants (string ordering inverted offset-mixed pairs). Unestimable
  streams render absence — excluded, counted (``single_event`` /
  ``zero_span`` / ``unstamped``) and disclosed — never a clean zero
  projection; the "single event" sentence can only ever describe an
  ``n == 1`` stream. A stream every governing rule of which is a hold
  rule is labeled ``held`` and projects the same rate × horizon growth:
  it never empties at disposal time, and the projection must not pretend
  otherwise.
- **Quota wedge.** The ceiling comes from ``--max-dataset-bytes`` or env
  ``BENCHWEAVE_MAX_DATASET_BYTES`` (the same knob
  ``interfaces/app_entry._limits_from_env`` reads), labelled
  ``ceiling_source``; absent → ``ceiling: unknown`` and the exhaustion
  projection is omitted, disclosed. Scope is per context key — the
  resolved owner fork: G3's ``_used_bytes_locked`` sums
  ``WHERE context_key = ?`` and the production key is ``run:<run_id>``
  (``interfaces/app.py``) — and ``used_bytes`` REUSES
  ``CaptureStagingStore.used_bytes``
  (the writer's own ledger read; zero formula-drift copies), plus
  ``time_to_exhaustion_s = (ceiling − used) / rate``. Runs group under
  benches for display via ``run_states.bench_id``; context keys mapping
  to no run report as their own group. The wedge disclosure: hold-heavy
  exhaustion hard-blocks G3 with no deletion path until the audit-trail
  slice; remediation is manual by design.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from benchweave.cli.atrest import AtRestError, db_path
from benchweave.cli.report import now_iso
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.control.retention_policy import (
    MAX_DURATION_S,
    RETENTION_POLICY_FILENAME,
    RetentionPolicy,
    RetentionPolicyRejected,
    load_retention_policy,
)
from benchweave.state.hold import StoreHold
from benchweave.state.store import Store

__all__ = [
    "build_retention_report",
    "now_iso",
    "render_json",
    "render_markdown",
    "retention_from_data_dir",
]

#: The report's closed capture-class vocabulary (the in-tree format
#: vocabulary plus the unknown-format class). The evidence lane stays open.
_CAPTURE_CLASSES = ("waveform_f64le", "raw_binary")
#: Default growth horizon — 30 days (issue #184 fork B): the operator-
#: chosen window every rate is extrapolated over, the same value for every
#: row so projections are comparable. Override per run with --horizon-s.
_DEFAULT_HORIZON_S = 2_592_000
_RUN_CONTEXT_PREFIX = "run:"
_STAGED = "staged"
_FINALISED = "finalised"
#: Both emitters carry this method label verbatim (S3-6).
_STORED_BYTES_METHOD = (
    "SELECT SUM(LENGTH(data)) FROM artifacts — content-addressed dedup "
    "under-counts byte-identical captures"
)
_WEDGE_DISCLOSURE = (
    "quota wedge: hold-heavy exhaustion hard-blocks new captures (G3) with "
    "no deletion path until the disposition audit-trail slice; remediation "
    "is manual by design — raise the ceiling or wait for that slice"
)
# Per-lane method labels (issue #184 finding 10): every emitted figure's
# basis and denominator is named IN ITS OWN LANE — the old single
# "under-counts" label is true only of stored bytes; the growth lanes'
# per-row referenced bytes OVER-count shared artifacts (the writer's
# content-addressed store gives byte-identical payloads one artifact row,
# and each referencing row counts it).
_SUBS_METHOD = (
    "referenced bytes = sum of per-row artifact lengths over the n placed "
    "events — a shared artifact counts once per row, so the lane "
    "over-counts byte-identical shared payloads (denominator: the n placed "
    "rows); rate = observed_bytes / observed_span_s"
)
_CAPS_METHOD = (
    "observed bytes = sum of charged_bytes over the n finalised captures "
    "(the writer's reservation-ledger basis, not artifact bytes); "
    "rate = observed_bytes / observed_span_s"
)
_WEDGE_LEDGER_METHOD = (
    "used = Σ reserved over staged + Σ charged over finalised per context "
    "key — the capture writer's reservation ledger, the same figure G3 "
    "enforces (denominator: the ledger rows of that key). The ledger is "
    "not monotone: finalise re-prices reservations to charged bytes and "
    "the abort sweep refunds aborted reservations — those drops are ledger "
    "events, not storage reclamation"
)
_DISPOSAL_ROWS_METHOD = (
    "evidence rows carry their artifact's LENGTH(data) (a shared artifact "
    "counts once per row); capture rows carry charged_bytes (the writer's "
    "reservation ledger, not artifact bytes)"
)


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    """Parse a stored stamp defensively; naive (no offset) or unparseable →
    None (issue #184 fork C: a foreign stamp is never resolved into a
    host-timezone-localized guess — the row reports ``anchor_unresolved``
    / is excluded from span math and counted instead)."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    return moment if moment.tzinfo is not None else None


# --- the model ----------------------------------------------------------------------


def _run_state_rows(store: Store) -> dict[str, dict[str, Any]]:
    """Every ``run_states`` projection row keyed by run id (the run→bench
    map and the terminal-stamp oracle — read over the store connection,
    the ``_evidence_rows`` precedent for tables without a list API)."""
    rows: dict[str, dict[str, Any]] = {}
    for run_id, bench_id, state, updated_at in store.connection.execute(
        "SELECT run_id, bench_id, state, updated_at FROM run_states"
    ):
        rows[str(run_id)] = {
            "bench": str(bench_id) if bench_id is not None else None,
            "state": str(state),
            "updated_at": updated_at,
        }
    return rows


def _artifact_bytes(store: Store, artifact_id: str | None) -> int:
    if artifact_id is None:
        return 0
    row = store.connection.execute(
        "SELECT LENGTH(data) FROM artifacts WHERE artifact_id = ?", (artifact_id,)
    ).fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0


def _terminal_ended_at(store: Store) -> dict[str, str | None]:
    """``runs.terminal_json['ended_at']`` keyed by run id — the immutable
    terminal-record stamp (``build_terminal_record`` writes it once at
    finalise). The run_end anchor reads exactly this (issue #184 finding 1):
    ``run_states.updated_at`` moves with every later ``put_run_state`` (the
    worker's post-finalize terminal put, the recovery stale-projection
    close), so it is the projection's freshness, never the run's end."""
    ended: dict[str, str | None] = {}
    for run_id, terminal_json in store.connection.execute(
        "SELECT run_id, terminal_json FROM runs"
    ):
        ended_at: str | None = None
        if isinstance(terminal_json, str):
            try:
                record: Any = json.loads(terminal_json)
            except json.JSONDecodeError:
                record = None
            if isinstance(record, dict):
                candidate = record.get("ended_at")
                ended_at = candidate if isinstance(candidate, str) else None
        ended[str(run_id)] = ended_at
    return ended


def _bench_of(context: str | None, run_states: dict[str, dict[str, Any]]) -> str | None:
    """The row's bench via ``run_states.bench_id`` — never a fabricated
    bench (the ``_evidence_rows`` honesty rule: unattributed keys report
    as their own group)."""
    if not isinstance(context, str) or not context.startswith(_RUN_CONTEXT_PREFIX):
        return None
    row = run_states.get(context.removeprefix(_RUN_CONTEXT_PREFIX))
    return row["bench"] if row is not None else None


def _covered(store: Store, bench_id: str | None) -> set[str] | None:
    """Covered run ids under a bench filter (None = unscoped)."""
    if bench_id is None:
        return None
    return {
        str(row[0])
        for row in store.connection.execute(
            "SELECT run_id FROM run_states WHERE bench_id = ?", (bench_id,)
        )
    }


def _in_scope(
    context: str | None,
    covered: set[str] | None,
    run_states: dict[str, dict[str, Any]],
) -> bool:
    """The report scope rule (issue #184 finding 17): a run-prefixed
    context is in scope iff its run is covered by the bench filter OR the
    key is unattributed (its run has NO ``run_states`` row at all — it was
    never mapped to a bench, exactly like a non-run key). Unattributed
    contexts never silently vanish; only runs that EXIST on another bench
    filter out."""
    if covered is None:
        return True
    if not isinstance(context, str) or not context.startswith(_RUN_CONTEXT_PREFIX):
        return True
    run = context.removeprefix(_RUN_CONTEXT_PREFIX)
    return run in covered or run not in run_states


def _disposal_row(
    *,
    row_kind: str,
    id_: str,
    context_key: str | None,
    bench: str | None,
    data_class: str,
    bytes_: int,
    anchor_kind: str | None,
    anchor_at: str | None,
    policy: RetentionPolicy | None,
    now_dt: datetime,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "row_kind": row_kind,
        "id": id_,
        "context_key": context_key,
        "bench": bench,
        "data_class": data_class,
        "matched_selector": None,
        "matched_scope": None,
        "matched_rule": None,
        "anchor_kind": anchor_kind,
        "anchor_at": anchor_at,
        "disposal_date": None,
        "status": "ungoverned",
        "overdue": False,
        "on_disposition": None,
        "duration_s": None,
        "bytes": bytes_,
    }
    if policy is None:
        return row
    # issue #184 finding 7: report the WINNING entry's identity — a class
    # rule merely present somewhere while a shadowing default governs is
    # never named.
    rule, matched_scope, matched_selector = policy.resolve_origin(
        bench=bench, data_class=data_class
    )
    row["matched_selector"] = matched_selector
    row["matched_scope"] = matched_scope
    row["matched_rule"] = "class" if matched_selector is not None else "default"
    row["on_disposition"] = rule.on_disposition
    row["duration_s"] = rule.duration_s
    row["anchor_kind"] = rule.retain_after
    if rule.hold:
        row["status"] = "held"
        return row
    if rule.retain_after == "run_end" and anchor_at is None:
        row["status"] = "anchor_unresolved"
        return row
    anchor_dt = _parse_utc(anchor_at)
    if anchor_dt is None:
        row["status"] = "anchor_unresolved"
        return row
    row["anchor_at"] = anchor_at
    try:
        disposal_dt = anchor_dt + timedelta(seconds=rule.duration_s)
    except (OverflowError, OSError, ValueError) as error:
        # issue #184 finding 3: a duration that pushes the disposal date
        # past the datetime domain is a typed refusal, never an unmapped
        # OverflowError/ValueError from timestamp math.
        raise ValueError(
            f"retention_policy: duration_s {rule.duration_s} plus anchor "
            f"{anchor_at} exceeds the datetime domain (year 9999) — the "
            "disposal date cannot be rendered"
        ) from error
    row["disposal_date"] = _iso(disposal_dt)
    row["status"] = "scheduled"
    row["overdue"] = disposal_dt <= now_dt
    return row


def build_retention_report(
    store: Store,
    *,
    policy: RetentionPolicy | None,
    bench_id: str | None = None,
    now: str,
    max_dataset_bytes: int | None = None,
    horizon_s: int | None = None,
) -> dict[str, Any]:
    """Build the retention model from the store at rest (pure: caller-
    injected clock, no store writes, everything derived from store state).

    ``policy`` None ⇒ every row ``ungoverned`` (the no-policy-file case).
    ``bench_id`` scopes rows exactly like ``report``'s bench filter;
    ``max_dataset_bytes`` fixes the wedge ceiling (env
    ``BENCHWEAVE_MAX_DATASET_BYTES`` is the fallback); ``horizon_s`` is the
    growth horizon every rate is extrapolated over (one value for every
    row; default 30 days).
    """
    if horizon_s is None:
        horizon_s = _DEFAULT_HORIZON_S
    # R2 fold item 5: a horizon beyond the datetime domain (a 310-digit
    # integer parsed fine) died later inside rate * horizon_s as a
    # knob-nameless "int too large to convert to float". The knob validates
    # at parse, against the same datetime-domain ceiling duration_s carries.
    if horizon_s < 1 or horizon_s > MAX_DURATION_S:
        raise ValueError(
            f"--horizon-s must be an integer in [1, {MAX_DURATION_S}] "
            "(the datetime-domain ceiling in seconds, the same bound "
            "duration_s carries)"
        )
    # R2 fold item 2a: the caller's clock meets the same UTC-strict parse as
    # stored stamps — a naive ``now`` used to escape mid-build as an
    # uncaught TypeError (aware disposal_dt vs naive now_dt comparison).
    now_dt = _parse_utc(now)
    if now_dt is None:
        raise ValueError(
            f"now {now!r} is not an offset-bearing ISO-8601 timestamp — a "
            "naive now would be host-timezone-localized exactly like a "
            "naive stored stamp (issue #184 fork C)"
        )
    if bench_id is not None and store.get_bench(bench_id) is None:
        raise ValueError(f"no bench {bench_id!r} in the store")
    covered = _covered(store, bench_id)
    run_states = _run_state_rows(store)
    terminal_ended = _terminal_ended_at(store)

    rows: list[dict[str, Any]] = []

    def _anchor(rule_after: str | None, landing_at: Any, context: str | None) -> str | None:
        """Resolve the row's anchor stamp under the governing retain_after.

        ``run_end`` resolves ONLY to the terminal record's immutable
        ``ended_at``; a run with no terminal record (live, interrupted, or
        closed-without-record by the poison guard) is honestly unresolved —
        never the moving ``run_states.updated_at`` projection stamp."""
        if rule_after != "run_end":
            return landing_at if isinstance(landing_at, str) else None
        if not isinstance(context, str) or not context.startswith(_RUN_CONTEXT_PREFIX):
            return None
        return terminal_ended.get(context.removeprefix(_RUN_CONTEXT_PREFIX))

    # --- governed captures: finalised staging rows in stored order --------
    for cap_id, context, fmt, charged, _artifact, updated_at in store.connection.execute(
        "SELECT capture_id, context_key, format, charged_bytes, artifact_id, updated_at"
        " FROM capture_staging WHERE state = ? ORDER BY updated_at, capture_id",
        (_FINALISED,),
    ):
        if not _in_scope(context, covered, run_states):
            continue
        data_class = (
            f"capture:{fmt}"
            if isinstance(fmt, str) and fmt in _CAPTURE_CLASSES
            else "capture:unknown"
        )
        rule_after = (
            policy.resolve(
                bench=_bench_of(context, run_states), data_class=data_class
            ).retain_after
            if policy is not None
            else None
        )
        anchor_at = _anchor(rule_after, updated_at, context)
        rows.append(
            _disposal_row(
                row_kind="capture",
                id_=str(cap_id),
                context_key=context,
                bench=_bench_of(context, run_states),
                data_class=data_class,
                bytes_=int(charged),
                anchor_kind=None,
                anchor_at=anchor_at,
                policy=policy,
                now_dt=now_dt,
            )
        )

    # --- governed evidence: every row in stored order ----------------------
    for ev_id, kind, _ref_json, artifact, context, stored_at in store.connection.execute(
        "SELECT evidence_id, kind, content_ref_json, artifact_id, context_key, stored_at"
        " FROM evidence ORDER BY stored_at, evidence_id"
    ):
        if not _in_scope(context, covered, run_states):
            continue
        data_class = f"evidence:{kind}" if isinstance(kind, str) else "evidence:unknown"
        rule_after = (
            policy.resolve(
                bench=_bench_of(context, run_states), data_class=data_class
            ).retain_after
            if policy is not None
            else None
        )
        anchor_at = _anchor(rule_after, stored_at, context)
        rows.append(
            _disposal_row(
                row_kind="evidence",
                id_=str(ev_id),
                context_key=context,
                bench=_bench_of(context, run_states),
                data_class=data_class,
                bytes_=_artifact_bytes(store, artifact),
                anchor_kind=None,
                anchor_at=anchor_at,
                policy=policy,
                now_dt=now_dt,
            )
        )

    # --- disclosures --------------------------------------------------------
    non_finalised = int(
        store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging WHERE state != ?", (_FINALISED,)
        ).fetchone()[0]
    )
    disclosures: list[str] = []
    if policy is None:
        disclosures.append(
            "no retention policy file: every row is ungoverned — disposition "
            "is not projected"
        )
    if non_finalised:
        disclosures.append(
            f"{non_finalised} non-finalised capture staging row(s) present — not "
            "governed; reclaimed by the next startup sweep"
        )
    unresolved_rows = sum(1 for r in rows if r["status"] == "anchor_unresolved")
    if unresolved_rows:
        disclosures.append(
            f"{unresolved_rows} row(s) anchor_unresolved — no resolvable "
            "offset-bearing anchor (missing terminal record, naive or "
            "unparseable stamp); disposal is not projected for those rows"
        )
    if bench_id is not None:
        # issue #184 finding 17: disclose the unattributed rowless keys the
        # bench filter keeps (they survive by the never-vanish rule)
        rowless = {
            key
            for (key,) in store.connection.execute(
                "SELECT DISTINCT context_key FROM capture_staging"
                " WHERE context_key IS NOT NULL"
                " UNION SELECT DISTINCT context_key FROM evidence"
                " WHERE context_key IS NOT NULL"
            )
            if isinstance(key, str)
            and key.startswith(_RUN_CONTEXT_PREFIX)
            and key.removeprefix(_RUN_CONTEXT_PREFIX) not in run_states
        }
        if rowless:
            disclosures.append(
                f"{len(rowless)} run-prefixed context key(s) map to no run row — "
                "reported as unattributed under the bench filter (never "
                "silently dropped)"
            )

    stored_total = int(
        store.connection.execute(
            "SELECT COALESCE(SUM(LENGTH(data)), 0) FROM artifacts"
        ).fetchone()[0]
    )

    # --- growth projection (issue #184 fork B: per-stream rate × horizon) ----
    # Wire per stream/key: observed_bytes, observed_span_s, n, rate_Bps
    # (exactly observed_bytes / observed_span_s) and
    # projected_horizon_bytes (exactly rate_Bps * horizon_s, ONE horizon for
    # every row). The old rate × duty × window algebra cancelled the span
    # into observed_bytes × window / report_window and coupled every stream
    # through the report-global window, so an old row in one key shrank
    # another key's projection. Unestimable streams render absence:
    # excluded + counted + disclosed (single_event / zero_span / unstamped).
    subscriptions: list[dict[str, Any]] = []
    captures_lane: dict[str, dict[str, Any]] = {}
    excluded = {"single_event": 0, "zero_span": 0, "unstamped": 0}
    dropped_events = {"corrupt_ref": 0, "no_subscription": 0, "unparseable_stamp": 0}

    sub_groups: dict[tuple[str, str | None], list[tuple[datetime | None, int]]] = {}
    for ref_json, artifact, context, _stored_at in store.connection.execute(
        "SELECT content_ref_json, artifact_id, context_key, stored_at FROM evidence"
        " WHERE kind = 'event_log' ORDER BY stored_at, evidence_id"
    ):
        if not _in_scope(context, covered, run_states):
            continue
        # finding 10: corrupt refs are COUNTED, never silently dropped
        ref: Any
        if isinstance(ref_json, str):
            try:
                ref = json.loads(ref_json)
            except json.JSONDecodeError:
                ref = None
        else:
            ref = None
        if not isinstance(ref, dict):
            dropped_events["corrupt_ref"] += 1
            continue
        sub = ref.get("subscription_id")
        received = ref.get("host_received_at")
        if not isinstance(sub, str):
            dropped_events["no_subscription"] += 1
            continue
        # parse FIRST, compare later: raw string ordering inverted
        # offset-mixed and bare-Z-vs-microsecond stamp pairs (finding 6)
        sub_groups.setdefault((sub, context), []).append(
            (_parse_utc(received), _artifact_bytes(store, artifact))
        )
    # R2 fold item 4: a NULL-context event_log row sharing a subscription
    # id with a keyed row makes (sub, None) and (sub, str) tuple keys — a
    # plain sorted() dies comparing them. The None-safe key orders keyed
    # groups first, the NULL-context group after, both reporting.
    for (sub, context), events in sorted(
        sub_groups.items(),
        key=lambda item: (item[0][0], item[0][1] is None, item[0][1] or ""),
    ):
        placed = [(stamp, bytes_) for stamp, bytes_ in events if stamp is not None]
        dropped_events["unparseable_stamp"] += len(events) - len(placed)
        if len(events) == 1:
            excluded["single_event"] += 1
            continue
        if len(placed) < 2:
            excluded["unstamped"] += 1
            continue
        span = (max(s for s, _ in placed) - min(s for s, _ in placed)).total_seconds()
        if span <= 0:
            excluded["zero_span"] += 1
            continue
        observed = sum(b for _, b in placed)
        bench = _bench_of(context, run_states)
        held = (
            policy.resolve(bench=bench, data_class="evidence:event_log").hold
            if policy is not None
            else False
        )
        rate = observed / span
        subscriptions.append(
            {
                "subscription_id": sub,
                "context_key": context,
                "n": len(placed),
                "observed_bytes": observed,
                "observed_span_s": span,
                "rate_Bps": rate,
                "projected_horizon_bytes": rate * horizon_s,
                "held": held,
            }
        )

    for context, created_at, updated_at, charged, fmt in store.connection.execute(
        "SELECT context_key, created_at, updated_at, charged_bytes, format"
        " FROM capture_staging WHERE state = ? ORDER BY updated_at, capture_id",
        (_FINALISED,),
    ):
        if not _in_scope(context, covered, run_states):
            continue
        lane = captures_lane.setdefault(
            str(context),
            {
                "context_key": str(context), "opens": [], "closes": [],
                "bytes": 0, "rows": 0, "total": 0,
                "governs": 0, "holds": 0,
            },
        )
        # The capture lane's observed span runs open→finalise: the key's
        # first parsed open to its last parsed finalise. A row whose BOTH
        # stamps are naive/unparseable cannot be placed in time — its bytes
        # stay out of the observation (counted, never silently dropped).
        opened, closed = _parse_utc(created_at), _parse_utc(updated_at)
        lane["total"] += 1
        if opened is None and closed is None:
            dropped_events["unparseable_stamp"] += 1
            continue
        if opened is not None:
            lane["opens"].append(opened)
        if closed is not None:
            lane["closes"].append(closed)
        lane["bytes"] += int(charged)
        lane["rows"] += 1
        if policy is not None:
            fmt_class = (
                f"capture:{fmt}"
                if isinstance(fmt, str) and fmt in _CAPTURE_CLASSES
                else "capture:unknown"
            )
            lane["governs"] += 1
            if policy.resolve(
                bench=_bench_of(context, run_states), data_class=fmt_class
            ).hold:
                lane["holds"] += 1
    capture_growth: list[dict[str, Any]] = []
    lane_rates: dict[str, dict[str, Any]] = {}
    for context, lane in sorted(captures_lane.items()):
        first = min(lane["opens"]) if lane["opens"] else None
        last = max(lane["closes"]) if lane["closes"] else None
        if lane["total"] == 1:
            excluded["single_event"] += 1
            continue
        if first is None or last is None:
            excluded["unstamped"] += 1
            continue
        span = (last - first).total_seconds()
        if span <= 0:
            excluded["zero_span"] += 1
            continue
        rate = lane["bytes"] / span
        lane_rates[context] = {"rate": rate, "n": lane["rows"], "span": span}
        # held: EVERY governing rule of the key's rows is a hold rule — the
        # stream never empties at disposal time, and its projection must not
        # pretend otherwise (finding 9: held classes used to project aging
        # out at the hold rule's schema-required duration_s).
        held = lane["governs"] > 0 and lane["holds"] == lane["governs"]
        capture_growth.append(
            {
                "context_key": context,
                "n": lane["rows"],
                "observed_bytes": lane["bytes"],
                "observed_span_s": span,
                "rate_Bps": rate,
                "projected_horizon_bytes": rate * horizon_s,
                "held": held,
            }
        )
    if excluded["single_event"]:
        disclosures.append(
            f"{excluded['single_event']} stream(s) excluded from the growth "
            "projection: n == 1 (a single event cannot define a rate)"
        )
    if excluded["zero_span"]:
        disclosures.append(
            f"{excluded['zero_span']} zero-span stream(s) excluded from the "
            "growth projection: every parsed stamp is the same instant"
        )
    if excluded["unstamped"] or dropped_events["unparseable_stamp"]:
        disclosures.append(
            f"{excluded['unstamped']} unstamped stream(s) excluded from the "
            "growth projection (fewer than two offset-bearing parseable "
            "stamps) and "
            f"{dropped_events['unparseable_stamp']} event(s) dropped from "
            "span math (naive or unparseable stamps)"
        )
    if dropped_events["corrupt_ref"]:
        disclosures.append(
            f"{dropped_events['corrupt_ref']} corrupt event_log content_ref "
            "row(s) excluded from the growth projection (unparseable or "
            "non-object reference)"
        )
    if dropped_events["no_subscription"]:
        disclosures.append(
            f"{dropped_events['no_subscription']} event_log row(s) without a "
            "subscription id excluded from the growth projection (not stream "
            "events)"
        )

    # --- the quota wedge -------------------------------------------------------
    # issue #184 finding 8: both ceiling knobs validate identically (the
    # env used to admit 0/-5/abc while the flag refused < 1), and the
    # states never render a negative forecast: over_ceiling says "over
    # ceiling by N bytes", at_ceiling says G3 refuses now, zero_growth
    # ("measured zero growth", n/span shown) is split from
    # ceiling_unknown ("ceiling unknown; projection omitted"), and an
    # unestimable key is unestimable — never a clean 0 rate.
    ceiling: int | None
    ceiling_source: str | None
    if max_dataset_bytes is not None:
        if max_dataset_bytes < 1:
            raise ValueError("--max-dataset-bytes must be an integer >= 1")
        ceiling, ceiling_source = max_dataset_bytes, "flag"
    else:
        env_raw = os.environ.get("BENCHWEAVE_MAX_DATASET_BYTES")
        if env_raw is not None:
            try:
                value = int(env_raw)
            except ValueError:
                value = -1
            if value < 1:
                raise ValueError(
                    "BENCHWEAVE_MAX_DATASET_BYTES must be an integer >= 1"
                )
            ceiling, ceiling_source = value, "env"
        else:
            ceiling, ceiling_source = None, None
    if ceiling is None:
        disclosures.append(
            "no --max-dataset-bytes and BENCHWEAVE_MAX_DATASET_BYTES is unset: "
            "ceiling unknown; the exhaustion projection is omitted"
        )
    writer = CaptureStagingStore(store)
    wedge_contexts: list[dict[str, Any]] = []
    exhaustion_beyond_domain = 0
    wedge_keys = [
        str(row[0])
        for row in store.connection.execute(
            "SELECT DISTINCT context_key FROM capture_staging ORDER BY context_key"
        )
    ]
    from benchweave.interfaces.operations import LIVE_RUN_STATES

    for key in wedge_keys:
        if not _in_scope(key, covered, run_states):
            continue
        used = writer.used_bytes(key)
        measured = lane_rates.get(key)  # a measured rate row, or None
        # issue #184 finding 11: the wedge consults run liveness — a closed
        # run's ledger is historical; a live-looking exhaustion date on it
        # would forecast growth that cannot come.
        run_state: str | None = None
        if key.startswith(_RUN_CONTEXT_PREFIX):
            state_row = run_states.get(key.removeprefix(_RUN_CONTEXT_PREFIX))
            if state_row is not None:
                run_state = (
                    "live" if state_row["state"] in LIVE_RUN_STATES else "closed"
                )
        if ceiling is None:
            state, over_by = "ceiling_unknown", None
        elif used > ceiling:
            state, over_by = "over_ceiling", used - ceiling
        elif used == ceiling:
            state, over_by = "at_ceiling", None
        elif measured is None:
            state, over_by = "unestimable_rate", None
        elif measured["rate"] == 0:
            state, over_by = "zero_growth", None
        else:
            state, over_by = "forecast", None
        tte: float | None = None
        if (
            state == "forecast"
            and run_state != "closed"
            and ceiling is not None
            and measured is not None
        ):
            tte = (ceiling - used) / measured["rate"]
        # R2 fold item 2b: a trickle rate x a huge ceiling pushes the
        # exhaustion instant past the datetime domain — the fw3 posture,
        # per-row: the honest number (time_to_exhaustion_s) is kept, the
        # instant renders absent + a disclosure, and no other row's output
        # dies with it (the old raw fromtimestamp killed the whole report).
        exhaustion_at: str | None = None
        if tte is not None:
            try:
                exhaustion_at = _iso(
                    datetime.fromtimestamp(
                        now_dt.timestamp() + tte, tz=now_dt.tzinfo
                    )
                )
            except (OverflowError, OSError, ValueError):
                exhaustion_beyond_domain += 1
        wedge_contexts.append(
            {
                "context_key": key,
                "bench": _bench_of(key, run_states),
                "run_state": run_state,
                "state": state,
                "over_ceiling_bytes": over_by,
                "used_bytes": used,
                "rate_bytes_per_s": measured["rate"] if measured is not None else None,
                "n": measured["n"] if measured is not None else None,
                "observed_span_s": measured["span"] if measured is not None else None,
                "time_to_exhaustion_s": tte,
                "exhaustion_at": exhaustion_at,
                "ceiling": ceiling,
                "ceiling_source": ceiling_source,
            }
        )
    if exhaustion_beyond_domain:
        disclosures.append(
            f"{exhaustion_beyond_domain} context key(s) forecast exhaustion "
            "beyond the datetime domain (year 9999) — time_to_exhaustion_s "
            "carries the figure; the instant cannot be rendered"
        )

    return {
        "generated_at": now,
        "policy": {
            "loaded": policy is not None,
            "path": None,
            "config_version": None,
        },
        "rows": rows,
        "disclosures": disclosures,
        "stored_bytes": {
            "total": stored_total,
            "method": _STORED_BYTES_METHOD,
            "disposal_rows": _DISPOSAL_ROWS_METHOD,
        },
        "growth": {
            "horizon_s": horizon_s,
            "subscriptions": subscriptions,
            "captures": capture_growth,
            "excluded": dict(excluded),
            "dropped_events": dict(dropped_events),
            "methods": {"subscriptions": _SUBS_METHOD, "captures": _CAPS_METHOD},
        },
        "quota_wedge": {
            "ceiling": ceiling,
            "ceiling_source": ceiling_source,
            "contexts": wedge_contexts,
            "method": _WEDGE_LEDGER_METHOD,
            "disclosure": _WEDGE_DISCLOSURE,
        },
    }


# --- emitters -----------------------------------------------------------------------

#: C0 control characters and DEL — a newline inside a store-sourced
#: identifier would otherwise forge report lines (the R2 fold's injection
#: item: evidence kinds are an open vocabulary, subscription ids ride
#: opaque ``content_ref`` JSON, and neither is constrained by the store).
_MD_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _md_text(value: Any) -> Any:
    """Escape control characters in a store-sourced string on its way into
    markdown (``\\x0a`` for a newline) so an identifier can never forge
    report lines. Non-strings pass through; the JSON emitter is untouched
    (``json.dumps`` already encodes control characters)."""
    if not isinstance(value, str):
        return value
    return _MD_CONTROL.sub(lambda match: f"\\x{ord(match.group()):02x}", value)


def render_markdown(report: dict[str, Any]) -> str:
    """The operator markdown: every row with its status and date, the
    byte method label, the growth lanes, the wedge, every disclosure."""
    lines = ["# BenchWeave retention report", f"generated_at: {report['generated_at']}"]
    policy = report["policy"]
    lines.append(
        "policy: loaded" if policy["loaded"] else "policy: absent — every row ungoverned"
    )
    lines.append("")
    lines.append("## Disposal schedule")
    for row in report["rows"]:
        overdue = " OVERDUE" if row["overdue"] else ""
        lines.append(
            f"- {_md_text(row['id'])}  class={_md_text(row['data_class'])}"
            f" bench={_md_text(row['bench']) or '-'}"
            f" status={row['status']} anchor={row['anchor_kind'] or '-'}"
            f"@{_md_text(row['anchor_at']) or '-'}"
            f" disposal={row['disposal_date'] or '-'}"
            f" on_disposition={row['on_disposition'] or '-'} bytes={row['bytes']}{overdue}"
        )
    lines.append("")
    lines.append("## Stored bytes")
    lines.append(
        f"- total: {report['stored_bytes']['total']} bytes"
        f" (method: {report['stored_bytes']['method']})"
    )
    lines.append(f"- {report['stored_bytes']['disposal_rows']}")
    growth = report["growth"]
    lines.append("")
    lines.append("## Growth projection")
    lines.append(
        f"- horizon: {growth['horizon_s']}s — every stream's rate is "
        "extrapolated over this one window (projections are comparable)"
    )
    for sub in growth["subscriptions"]:
        held = " [held — never empties at disposal time]" if sub["held"] else ""
        lines.append(
            f"- subscription {_md_text(sub['subscription_id'])}: n={sub['n']} "
            f"observed={sub['observed_bytes']} B over {sub['observed_span_s']}s "
            f"rate={sub['rate_Bps']:.3f} B/s "
            f"projected={sub['projected_horizon_bytes']:.0f} B{held}"
        )
    for cap in growth["captures"]:
        held = " [held — never empties at disposal time]" if cap["held"] else ""
        lines.append(
            f"- captures {_md_text(cap['context_key'])}: n={cap['n']} "
            f"observed={cap['observed_bytes']} B over {cap['observed_span_s']}s "
            f"rate={cap['rate_Bps']:.3f} B/s "
            f"projected={cap['projected_horizon_bytes']:.0f} B{held}"
        )
    lines.append(f"- {growth['methods']['subscriptions']}")
    lines.append(f"- {growth['methods']['captures']}")
    excluded = growth["excluded"]
    lines.append(
        f"- excluded streams: {excluded['single_event']} single-event, "
        f"{excluded['zero_span']} zero-span, {excluded['unstamped']} unestimable"
        f" (unparsed stamps) — counted, never rendered as zero projections"
    )
    wedge = report["quota_wedge"]
    lines.append("")
    lines.append("## Quota wedge")
    if wedge["ceiling"] is None:
        lines.append("- ceiling: unknown — exhaustion projection omitted")
    else:
        lines.append(f"- ceiling: {wedge['ceiling']} (source: {wedge['ceiling_source']})")
    for ctx in wedge["contexts"]:
        rate_text = (
            f"rate={ctx['rate_bytes_per_s']:.3f} B/s"
            if ctx["rate_bytes_per_s"] is not None
            else "rate=unestimable"
        )
        if ctx.get("run_state") == "closed":
            lines.append(
                f"- {_md_text(ctx['context_key'])} bench={_md_text(ctx['bench']) or '-'}: "
                f"used={ctx['used_bytes']} B {rate_text} "
                "run closed — ledger static, no forecast"
            )
            continue
        state = ctx.get("state")
        if state == "ceiling_unknown":
            tail = "ceiling unknown; projection omitted"
        elif state == "over_ceiling":
            tail = (
                f"over ceiling by {ctx['over_ceiling_bytes']} bytes — G3 "
                "refuses new captures (no negative forecast)"
            )
        elif state == "at_ceiling":
            tail = "at ceiling — G3 refuses new captures"
        elif state == "unestimable_rate":
            tail = (
                "rate unestimable — key excluded from the growth projection "
                "(see growth exclusions)"
            )
        elif state == "zero_growth":
            tail = (
                f"measured zero growth (n={ctx['n']}, span={ctx['observed_span_s']}s)"
            )
        else:
            at = ctx["exhaustion_at"]
            when = (
                f"(at {at})"
                if at is not None
                else "(instant beyond the datetime domain — see the disclosure)"
            )
            tail = f"exhaustion in {ctx['time_to_exhaustion_s']:.1f}s {when}"
        lines.append(
            f"- {_md_text(ctx['context_key'])} bench={_md_text(ctx['bench']) or '-'}: "
            f"used={ctx['used_bytes']} B {rate_text} {tail}"
        )
    lines.append(f"- {wedge['disclosure']}")
    lines.append(f"- {wedge['method']}")
    lines.append("")
    lines.append("## Disclosures")
    if not report["disclosures"]:
        lines.append("- none")
    for note in report["disclosures"]:
        lines.append(f"- {note}")
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> str:
    """The machine form: ``json.loads`` of this string round-trips the
    model exactly."""
    return json.dumps(report, indent=2, sort_keys=True)


# --- the at-rest command wrapper ------------------------------------------------------


class RetentionStoreRefused(AtRestError):
    """The store's schema does not match the gateway's (issue #184 fork A):
    a retention run NEVER migrates the store — it refuses, naming the
    mismatch. The machine-matchable ``retention_store:`` prefix rides the
    same refusal family as ``retention_policy:``."""


def _refuse_schema_mismatch(db: Path) -> None:
    """Fork A's read posture: inspect ``schema_migrations`` read-only and
    refuse on any drift. The comparison is SET-based (the R2 fold's
    blocking item): ``Store._apply_migrations`` re-applies ANY migration
    whose version row is absent — not only those below ``MAX(version)`` —
    so a MAX-only precheck admits a holey store (the middle v4 row
    deleted, v5/MAX intact) and the idempotent re-apply writes a
    ``schema_migrations`` row inside the "never migrates" command. Any
    unknown version present → refuse (``refuse_newer_schema`` — it
    dominates: a newer gateway's store can also read as missing the
    current top version); any known version missing → refuse, naming the
    missing versions; typed, never a traceback (the
    ``report`` command still shares the
    migration-on-open shape — that behavior change is out of this slice's
    scope). The check runs under the exclusive hold, so the subsequent
    ``Store.open`` applies nothing: the applied-version set equaling the
    gateway's known set is what makes "no pending migration exists" true."""
    from benchweave.state.migrations import MIGRATIONS

    known = [migration.version for migration in MIGRATIONS]
    expected = known[-1]
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise RetentionStoreRefused(
            f"retention_store: cannot inspect {db}: {error}"
        ) from error
    try:
        try:
            applied = {
                int(row[0])
                for row in conn.execute("SELECT version FROM schema_migrations")
            }
        except sqlite3.Error as error:
            raise RetentionStoreRefused(
                "retention_store: no schema_migrations table — not a "
                "benchweave store (or one written before the schema "
                "registry); a retention run never migrates the store"
            ) from error
    finally:
        conn.close()
    missing = [version for version in known if version not in applied]
    unknown = sorted(applied - set(known))
    # Precedence: an unknown version (a newer gateway's schema) dominates a
    # missing one — a newer gateway renumbers/replaces the top migrations, so
    # its store can read as "missing" the current top version while the
    # honest verdict is refuse-newer, never a down-level upgrade hint.
    if unknown:
        raise RetentionStoreRefused(
            f"retention_store: on-disk schema version {unknown[-1]} is newer "
            f"than the gateway's {expected} (unknown versions: "
            f"{', '.join(str(version) for version in unknown)}); downgrade "
            "is refused (refuse_newer_schema) — run a gateway version that "
            "knows this schema before opening this database"
        )
    if missing:
        raise RetentionStoreRefused(
            f"retention_store: on-disk schema is behind the gateway's — "
            f"schema_migrations is missing versions: "
            f"{', '.join(str(version) for version in missing)} (of the "
            f"gateway's known 1..{expected}) — a retention run never "
            "migrates the store; open it once with a current gateway "
            "(setup/serve/report) to upgrade, then retry"
        )


def retention_from_data_dir(
    data_dir: Path,
    *,
    bench_id: str | None = None,
    policy_path: Path | None = None,
    now: str,
    max_dataset_bytes: int | None = None,
    horizon_s: int | None = None,
) -> dict[str, Any]:
    """Open the data directory's store AT REST and build the retention
    report under the one-coordinator rule (the whole open→read→close
    window holds the store's exclusive hold, exactly like the sibling
    at-rest commands; refuses naming the holder while a live gateway
    owns the store). The store is never migrated (fork A): a schema
    mismatch refuses typed (``retention_store:``), naming the mismatch.

    Policy resolution: an explicit ``policy_path`` must load (missing or
    invalid refuses — the operator asked for it by name); the default
    ``<data-dir>/retention-policy.json`` is optional — absent means every
    row is ungoverned, present-but-invalid refuses.
    """
    data_dir = Path(data_dir)
    db = db_path(data_dir)
    if not db.is_file():
        raise AtRestError(f"no store at {db} — run setup first")

    policy: RetentionPolicy | None
    path = Path(policy_path) if policy_path is not None else data_dir / RETENTION_POLICY_FILENAME
    if policy_path is not None or path.is_file():
        try:
            policy = load_retention_policy(path)
        except RetentionPolicyRejected:
            raise
        except OSError as error:
            raise AtRestError(f"cannot read policy {path}: {error}") from error
    else:
        policy = None

    with StoreHold(db, label=f"retention pid {os.getpid()}"):
        # fork A: never migrate — refuse on any schema mismatch first
        _refuse_schema_mismatch(db)
        try:
            store = Store.open(db)
        except RuntimeError as error:
            # Belt-and-braces (finding 13): Store.open's refuse-newer guard
            # is unreachable behind the pre-check, but a RuntimeError from
            # there is still a typed refusal here, never a traceback.
            raise RetentionStoreRefused(f"retention_store: {error}") from error
        except sqlite3.Error as error:
            raise AtRestError(f"cannot open {db}: {error}") from error
        try:
            model = build_retention_report(
                store,
                policy=policy,
                bench_id=bench_id,
                now=now,
                max_dataset_bytes=max_dataset_bytes,
                horizon_s=horizon_s,
            )
            if policy is not None:
                model["policy"] = {
                    "loaded": True,
                    "path": str(path),
                    "config_version": "1",
                }
            return model
        except sqlite3.Error as error:
            raise AtRestError(f"cannot read {db}: {error}") from error
        finally:
            store.close()
