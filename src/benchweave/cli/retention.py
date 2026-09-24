"""Issue #43 slice 3 (Decision 8): the retention report — pure projection.

The mirror of :mod:`benchweave.cli.report` (``build_report`` →
:func:`build_retention_report`; ``report_from_data_dir`` →
:func:`retention_from_data_dir`; ``render_markdown``/``render_json``;
caller-injected ``now`` — the model never reads a clock). The standing
rule (the record's Decision 8): **slice 3 writes nothing back** — no
data-class stamps into durable rows, no cached disposal dates, no
write-back of any projection result; S3-1 pins this over every table in
the store. Nothing here deletes or archives: ``on_disposition`` is a
report label only, and no automated disposition ships until the
disposition-audit-trail slice (the record's sequencing invariant).

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
  slice). ``run_end`` resolves to the owning run's terminal transition
  stamp (``run_states.updated_at`` where the state is terminal; terminal
  = not in ``interfaces.operations.LIVE_RUN_STATES``). A ``run_end`` row
  whose run is non-terminal or unattributed yields status
  ``anchor_unresolved`` with ``disposal_date: null`` — never a
  substituted anchor.
- **Byte accounting.** Stored bytes are ``SELECT SUM(LENGTH(data)) FROM
  artifacts`` — the artifact table is the source of truth and
  content-addressed dedup UNDER-counts (the honest direction); both
  emitters label the method. Ingest rates anchor on immutable per-row
  stamps (``evidence.stored_at``, ``capture_staging.updated_at``) and
  never on ``artifacts.stored_at`` — that column refreshes on re-put, so
  a re-put of identical bytes changes no report figure (S3-6's companion
  arm).
- **Growth projection.** Per subscription from landed ``event_log``
  ``content_ref`` (``subscription_id``/``host_received_at`` — the fields
  ``stream_services.land_events`` lands): ``rate = observed referenced
  bytes / observed span``, ``duty = observed span / report window``,
  ``projected = rate × duty × retention window``; the capture lane runs
  analogously per context key (window = the longest governing duration
  among the key's rows — a disclosed worst-case bound, since one key's
  rows may govern under different classes). Zero-span streams (a single
  event) are structurally excluded and disclosed by count; every
  projected row carries ``n`` and ``span``. No numeric threshold is
  invented anywhere.
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
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from benchweave.cli.atrest import AtRestError, db_path
from benchweave.cli.report import now_iso
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.store import ContentStore
from benchweave.control.retention_policy import (
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


def _parse(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    """Parse a stored stamp; unparseable → None (treated as unresolved)."""
    return _parse(value) if isinstance(value, str) else None


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


def _in_scope(context: str | None, covered: set[str] | None) -> bool:
    """The report scope rule: a run-prefixed context is in scope iff its
    run is covered; unattributed contexts never silently vanish."""
    if covered is None:
        return True
    if not isinstance(context, str) or not context.startswith(_RUN_CONTEXT_PREFIX):
        return True
    return context.removeprefix(_RUN_CONTEXT_PREFIX) in covered


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
    rule = policy.resolve(bench=bench, data_class=data_class)
    scoped = policy.benches.get(bench) if bench is not None else None
    if (scoped is not None and data_class in scoped.classes) or data_class in policy.classes:
        row["matched_selector"] = data_class
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
    disposal = anchor_dt.timestamp() + rule.duration_s
    row["disposal_date"] = _iso(datetime.fromtimestamp(disposal, tz=anchor_dt.tzinfo))
    row["status"] = "scheduled"
    row["overdue"] = disposal <= now_dt.timestamp()
    return row


def build_retention_report(
    store: Store,
    content: ContentStore,
    *,
    policy: RetentionPolicy | None,
    bench_id: str | None = None,
    now: str,
    max_dataset_bytes: int | None = None,
) -> dict[str, Any]:
    """Build the retention model from the store at rest (pure: caller-
    injected clock, no store writes, everything derived from store state).

    ``policy`` None ⇒ every row ``ungoverned`` (the no-policy-file case).
    ``bench_id`` scopes rows exactly like ``report``'s bench filter;
    ``max_dataset_bytes`` fixes the wedge ceiling (env
    ``BENCHWEAVE_MAX_DATASET_BYTES`` is the fallback).
    """
    from benchweave.interfaces.operations import LIVE_RUN_STATES

    now_dt = _parse(now)
    if now_dt is None:
        raise ValueError(f"now {now!r} is not an ISO-8601 timestamp")
    if bench_id is not None and store.get_bench(bench_id) is None:
        raise ValueError(f"no bench {bench_id!r} in the store")
    covered = _covered(store, bench_id)
    run_states = _run_state_rows(store)

    rows: list[dict[str, Any]] = []
    earliest: datetime | None = None

    def _anchor(rule_after: str | None, landing_at: Any, context: str | None) -> str | None:
        """Resolve the row's anchor stamp under the governing retain_after."""
        if rule_after != "run_end":
            return landing_at if isinstance(landing_at, str) else None
        if not isinstance(context, str) or not context.startswith(_RUN_CONTEXT_PREFIX):
            return None
        state_row = run_states.get(context.removeprefix(_RUN_CONTEXT_PREFIX))
        if state_row is None or state_row["state"] in LIVE_RUN_STATES:
            return None
        stamp = state_row["updated_at"]
        return stamp if isinstance(stamp, str) else None

    # --- governed captures: finalised staging rows in stored order --------
    for cap_id, context, fmt, charged, _artifact, updated_at in store.connection.execute(
        "SELECT capture_id, context_key, format, charged_bytes, artifact_id, updated_at"
        " FROM capture_staging WHERE state = ? ORDER BY updated_at, capture_id",
        (_FINALISED,),
    ):
        if not _in_scope(context, covered):
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
        stamp = _parse_utc(anchor_at)
        if stamp is not None and (earliest is None or stamp < earliest):
            earliest = stamp
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
        if not _in_scope(context, covered):
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
        stamp = _parse_utc(anchor_at)
        if stamp is not None and (earliest is None or stamp < earliest):
            earliest = stamp
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

    stored_total = int(
        store.connection.execute(
            "SELECT COALESCE(SUM(LENGTH(data)), 0) FROM artifacts"
        ).fetchone()[0]
    )

    # --- growth projection ---------------------------------------------------
    window_s = max((now_dt - earliest).total_seconds(), 0.0) if earliest else 0.0
    subscriptions: list[dict[str, Any]] = []
    captures_lane: dict[str, dict[str, Any]] = {}
    zero_span = 0

    sub_groups: dict[tuple[str, str | None], list[tuple[str, int]]] = {}
    for ref_json, artifact, context, _stored_at in store.connection.execute(
        "SELECT content_ref_json, artifact_id, context_key, stored_at FROM evidence"
        " WHERE kind = 'event_log' ORDER BY stored_at, evidence_id"
    ):
        try:
            ref = json.loads(ref_json) if isinstance(ref_json, str) else {}
        except json.JSONDecodeError:
            ref = {}
        sub = ref.get("subscription_id") if isinstance(ref, dict) else None
        received = ref.get("host_received_at") if isinstance(ref, dict) else None
        if not isinstance(sub, str) or not _in_scope(context, covered):
            continue
        sub_groups.setdefault((sub, context), []).append(
            (str(received), _artifact_bytes(store, artifact))
        )
    for (sub, context), events in sorted(sub_groups.items()):
        stamps = [e[0] for e in events]
        span = 0.0
        first, last = _parse_utc(min(stamps)), _parse_utc(max(stamps))
        if first is not None and last is not None:
            span = max((last - first).total_seconds(), 0.0)
        n = len(events)
        referenced = sum(b for _, b in events)
        if span <= 0 or n < 2:
            zero_span += 1
            continue
        bench = _bench_of(context, run_states)
        window = (
            policy.resolve(bench=bench, data_class="evidence:event_log").duration_s
            if policy is not None
            else 0
        )
        duty = span / window_s if window_s > 0 else 0.0
        subscriptions.append(
            {
                "subscription_id": sub,
                "context_key": context,
                "n": n,
                "span_s": span,
                "rate_bytes_per_s": referenced / span,
                "duty": duty,
                "window_s": window,
                "projected_bytes": referenced / span * duty * window,
            }
        )

    for context, created_at, updated_at, charged, fmt in store.connection.execute(
        "SELECT context_key, created_at, updated_at, charged_bytes, format"
        " FROM capture_staging WHERE state = ? ORDER BY updated_at, capture_id",
        (_FINALISED,),
    ):
        if not _in_scope(context, covered):
            continue
        lane = captures_lane.setdefault(
            str(context),
            {"context_key": str(context), "opened": [], "closed": [], "bytes": 0, "windows": []},
        )
        # The capture lane's observed span runs open→finalise: a key's first
        # open to its last finalise (a single capture still contributes its
        # own acquisition window; anchors stay the finalise stamps).
        lane["opened"].append(str(created_at))
        lane["closed"].append(str(updated_at))
        lane["bytes"] += int(charged)
        if policy is not None:
            fmt_class = (
                f"capture:{fmt}"
                if isinstance(fmt, str) and fmt in _CAPTURE_CLASSES
                else "capture:unknown"
            )
            lane["windows"].append(
                policy.resolve(
                    bench=_bench_of(context, run_states), data_class=fmt_class
                ).duration_s
            )
    capture_growth: list[dict[str, Any]] = []
    lane_rates: dict[str, float] = {}
    for context, lane in sorted(captures_lane.items()):
        first = _parse_utc(min(lane["opened"])) if lane["opened"] else None
        last = _parse_utc(max(lane["closed"])) if lane["closed"] else None
        span = max((last - first).total_seconds(), 0.0) if first and last else 0.0
        rate = lane["bytes"] / span if span > 0 else 0.0
        lane_rates[context] = rate
        window = max(lane["windows"]) if lane["windows"] else 0
        duty = span / window_s if window_s > 0 else 0.0
        capture_growth.append(
            {
                "context_key": context,
                "n": len(lane["closed"]),
                "span_s": span,
                "rate_bytes_per_s": rate,
                "duty": duty,
                "window_s": window,
                "projected_bytes": rate * duty * window,
            }
        )
    if zero_span:
        disclosures.append(
            f"{zero_span} zero-span stream(s) (a single event over the observed "
            "window) are structurally excluded from the rate projection"
        )

    # --- the quota wedge -------------------------------------------------------
    ceiling: int | None
    ceiling_source: str | None
    if max_dataset_bytes is not None:
        if max_dataset_bytes < 1:
            raise ValueError("--max-dataset-bytes must be an integer >= 1")
        ceiling, ceiling_source = max_dataset_bytes, "flag"
    else:
        env_raw = os.environ.get("BENCHWEAVE_MAX_DATASET_BYTES")
        if env_raw is not None:
            ceiling, ceiling_source = int(env_raw), "env"
        else:
            ceiling, ceiling_source = None, None
    if ceiling is None:
        disclosures.append(
            "no --max-dataset-bytes and BENCHWEAVE_MAX_DATASET_BYTES is unset: "
            "ceiling unknown; the exhaustion projection is omitted"
        )
    writer = CaptureStagingStore(store)
    wedge_contexts: list[dict[str, Any]] = []
    wedge_keys = [
        str(row[0])
        for row in store.connection.execute(
            "SELECT DISTINCT context_key FROM capture_staging ORDER BY context_key"
        )
    ]
    for key in wedge_keys:
        if not _in_scope(key, covered):
            continue
        used = writer.used_bytes(key)
        rate = lane_rates.get(key, 0.0)
        tte = (ceiling - used) / rate if ceiling is not None and rate > 0 else None
        wedge_contexts.append(
            {
                "context_key": key,
                "bench": _bench_of(key, run_states),
                "used_bytes": used,
                "rate_bytes_per_s": rate,
                "time_to_exhaustion_s": tte,
                "exhaustion_at": (
                    _iso(datetime.fromtimestamp(now_dt.timestamp() + tte, tz=now_dt.tzinfo))
                    if tte is not None
                    else None
                ),
                "ceiling": ceiling,
                "ceiling_source": ceiling_source,
            }
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
        "stored_bytes": {"total": stored_total, "method": _STORED_BYTES_METHOD},
        "growth": {
            "report_window_s": window_s,
            "subscriptions": subscriptions,
            "captures": capture_growth,
            "zero_span_excluded": zero_span,
        },
        "quota_wedge": {
            "ceiling": ceiling,
            "ceiling_source": ceiling_source,
            "contexts": wedge_contexts,
            "disclosure": _WEDGE_DISCLOSURE,
        },
    }


# --- emitters -----------------------------------------------------------------------


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
            f"- {row['id']}  class={row['data_class']} bench={row['bench'] or '-'}"
            f" status={row['status']} anchor={row['anchor_kind'] or '-'}"
            f"@{row['anchor_at'] or '-'} disposal={row['disposal_date'] or '-'}"
            f" on_disposition={row['on_disposition'] or '-'} bytes={row['bytes']}{overdue}"
        )
    lines.append("")
    lines.append("## Stored bytes")
    lines.append(
        f"- total: {report['stored_bytes']['total']} bytes"
        f" (method: {report['stored_bytes']['method']})"
    )
    growth = report["growth"]
    lines.append("")
    lines.append("## Growth projection")
    lines.append(f"- report window: {growth['report_window_s']}s")
    for sub in growth["subscriptions"]:
        lines.append(
            f"- subscription {sub['subscription_id']}: n={sub['n']} "
            f"span={sub['span_s']}s rate={sub['rate_bytes_per_s']:.3f} B/s "
            f"duty={sub['duty']:.3f} projected={sub['projected_bytes']:.0f} B "
            f"over {sub['window_s']}s"
        )
    for cap in growth["captures"]:
        lines.append(
            f"- captures {cap['context_key']}: n={cap['n']} span={cap['span_s']}s "
            f"rate={cap['rate_bytes_per_s']:.3f} B/s duty={cap['duty']:.3f} "
            f"projected={cap['projected_bytes']:.0f} B over {cap['window_s']}s"
        )
    lines.append(f"- zero-span streams excluded: {growth['zero_span_excluded']}")
    wedge = report["quota_wedge"]
    lines.append("")
    lines.append("## Quota wedge")
    if wedge["ceiling"] is None:
        lines.append("- ceiling: unknown — exhaustion projection omitted")
    else:
        lines.append(f"- ceiling: {wedge['ceiling']} (source: {wedge['ceiling_source']})")
    for ctx in wedge["contexts"]:
        tte = (
            f"{ctx['time_to_exhaustion_s']:.1f}s (at {ctx['exhaustion_at']})"
            if ctx["time_to_exhaustion_s"] is not None
            else "no estimate (zero rate or unknown ceiling)"
        )
        lines.append(
            f"- {ctx['context_key']} bench={ctx['bench'] or '-'}: "
            f"used={ctx['used_bytes']} B rate={ctx['rate_bytes_per_s']:.3f} B/s "
            f"exhaustion in {tte}"
        )
    lines.append(f"- {wedge['disclosure']}")
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


def retention_from_data_dir(
    data_dir: Path,
    *,
    bench_id: str | None = None,
    policy_path: Path | None = None,
    now: str,
    max_dataset_bytes: int | None = None,
) -> dict[str, Any]:
    """Open the data directory's store AT REST and build the retention
    report under the one-coordinator rule (the whole open→read→close
    window holds the store's exclusive hold, exactly like the sibling
    at-rest commands; refuses naming the holder while a live gateway
    owns the store).

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
        try:
            store = Store.open(db)
        except sqlite3.Error as error:
            raise AtRestError(f"cannot open {db}: {error}") from error
        try:
            model = build_retention_report(
                store,
                ContentStore(store),
                policy=policy,
                bench_id=bench_id,
                now=now,
                max_dataset_bytes=max_dataset_bytes,
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
