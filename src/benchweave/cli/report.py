"""The Task 13 report MODEL plus its markdown/JSON emitters (at-rest).

The model — :func:`build_report` — is pure and store-derived: every field
reads the store at rest through its public surface (never an in-memory
claim), ``generated_at`` comes from the caller's injected clock (the model
never reads a wall clock), and evidence presence is computed against the
content store. Model shape (the additive ``--json`` contract)::

    {
      "generated_at": str,             # the caller-injected timestamp
      "simulation": bool,              # any covered bench is simulated
      "benches": [ {"id", "busy", "generation"[, "simulation": true]} ],
      "runs": [ {"id", "bench", "state", "outcome", "principal"
                 [, "simulation": true]} ],
      "evidence": [ {"evidence_id", "kind", "digest", "present"} ],
      "missing_evidence": [ <the same entry shape, present=false> ]
    }

Derivations, disclosed (controller rulings 3-5):

- **Simulation label.** The store has no first-class simulation field (the
  benches table carries id/generation/qualification/configuration/licence),
  so the label derives from the store's own configuration document: a bench
  is simulated iff its stored commissioning configuration declares the
  ``simulator-only`` limitation — the fixture lattice's own declaration
  (``commissioning.json`` evidence limitations), stored verbatim as the
  bench's ``configuration_json`` at bootstrap. No bench names are
  hardcoded; a simulated bench whose commissioning omits the limitation
  would read as not simulated (the derivation's disclosed boundary). A run
  is simulated iff its bench is. Simulated entries carry
  ``"simulation": true``; non-simulated entries omit the key.
- **busy.** The §5/D9 run-side busy oracle, mirrored from the seam: a run
  owns its bench from acceptance until its queue state closes terminal
  (``interfaces.operations.LIVE_RUN_STATES`` over ``Store.list_run_states``).
- **outcome.** The seam's honesty rule: ``None`` until terminal;
  ``outcome_unknown`` for a terminal run without a durable record — never
  a fabricated pass.
- **Evidence scope.** Evidence rows carry no bench linkage (only a
  ``context_key``; the gateway's retain adapter keys them ``run:<run_id>``).
  A row is covered iff its context names a covered run or it carries no
  run-prefixed key at all — unattributed evidence never silently vanishes
  from a report whose job is naming it. Rows are enumerated in stored
  order via the store connection (the WP07 content tables have no list
  API); each row is then read and presence-checked through the
  :class:`~benchweave.content.store.ContentStore` public surface.

The at-rest command wrapper — :func:`report_from_data_dir` — reads the
store AT REST under the one-coordinator rule's read posture: it refuses
(through the same :func:`~benchweave.cli.atrest.daemon_holds` gate as the
Task 10/11 discipline), naming the holder, while a live gateway owns the
store. ``--gateway`` composition (a report built from REST reads) is a
documented not-implemented stub: wiring it here would fork the model into
two read paths, so this task ships the at-rest one only.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchweave.cli.atrest import AtRestError, daemon_holds, db_path, holder_info
from benchweave.cli.demo import SIMULATION_LABEL
from benchweave.content.store import ContentStore
from benchweave.state.hold import StoreHeldError
from benchweave.state.store import Store

__all__ = [
    "SIMULATION_MARK",
    "build_report",
    "render_json",
    "render_markdown",
    "report_from_data_dir",
]

#: The commissioning limitation that declares a simulated bench (the
#: fixture lattice's own marker, read from the stored configuration).
SIMULATION_MARK = "simulator-only"
#: Evidence context keys the gateway's retain adapter prefixes with a run
#: id (``run:<run_id>``) — the only bench-adjacent linkage evidence rows carry.
_RUN_CONTEXT_PREFIX = "run:"
#: Bench listing page size (the store's list API pages; reports read all).
_PAGE = 1000


def _bench_rows(store: Store) -> list[dict[str, Any]]:
    """Every bench row, paged through the store's listing API."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        items, has_more = store.list_benches(_PAGE, offset)
        rows.extend(items)
        if not has_more:
            return rows
        offset += _PAGE


def _is_simulated(bench_row: dict[str, Any]) -> bool:
    """True iff the bench's stored commissioning configuration declares the
    simulator-only limitation (see the module docstring's derivation)."""
    try:
        configuration: object = json.loads(bench_row["configuration_json"])
    except (json.JSONDecodeError, TypeError, KeyError):
        return False
    if not isinstance(configuration, dict):
        return False
    evidence = configuration.get("evidence")
    if not isinstance(evidence, list):
        return False
    for item in evidence:
        if (
            isinstance(item, dict)
            and item.get("limitations") is not None
            and SIMULATION_MARK in item["limitations"]
        ):
            return True
    return False


def _outcome_of(state: str, terminal: dict[str, Any] | None) -> str | None:
    """The seam's outcome honesty rule (see the module docstring)."""
    if state != "terminal":
        return None
    if terminal is None:
        return "outcome_unknown"
    return str(terminal.get("outcome", "outcome_unknown"))


def _covered_run_ids(store: Store, bench_ids: list[str]) -> set[str]:
    covered: set[str] = set()
    for bench_id in bench_ids:
        for row in store.list_run_states(bench_id):
            covered.add(str(row["run_id"]))
    return covered


def _evidence_rows(
    store: Store, content: ContentStore, covered_runs: set[str]
) -> list[dict[str, Any]]:
    """The evidence inventory with presence computed against the content
    store (see the module docstring's scope rule)."""
    # The WP07 content tables expose no list API, so ids are enumerated in
    # stored order over the store connection (the public single-writer
    # connection the ContentStore shares, WP07).
    ids = [
        str(row[0])
        for row in store.connection.execute(
            "SELECT evidence_id FROM evidence ORDER BY stored_at, evidence_id"
        )
    ]
    entries: list[dict[str, Any]] = []
    for evidence_id in ids:
        row = content.get_evidence(evidence_id)
        if row is None:  # pragma: no cover — the id list just read it
            continue
        context = row["context_key"]
        if (
            isinstance(context, str)
            and context.startswith(_RUN_CONTEXT_PREFIX)
            and context.removeprefix(_RUN_CONTEXT_PREFIX) not in covered_runs
        ):
            continue
        artifact_id = row["artifact_id"]
        digest = ""
        content_ref = row["content_ref"]
        if isinstance(content_ref, dict) and isinstance(content_ref.get("sha256"), str):
            digest = str(content_ref["sha256"])
        elif isinstance(artifact_id, str):
            digest = artifact_id.removeprefix("art-")
        present = _present(content, artifact_id, digest)
        entries.append(
            {
                "evidence_id": evidence_id,
                "kind": str(row["kind"]),
                "digest": digest,
                "present": present,
            }
        )
    return entries


def _present(content: ContentStore, artifact_id: str | None, digest: str) -> bool:
    """Does the backing bytes still exist in the content store?"""
    if artifact_id is not None:
        try:
            content.artifact_chunk(artifact_id, 0, 1)
        except KeyError:
            return False
        return True
    if not digest:
        return False
    return content.get_document(digest) is not None


def build_report(
    store: Store,
    content: ContentStore,
    *,
    bench_id: str | None = None,
    now: str,
) -> dict[str, Any]:
    """Build the report model from the store at rest (pure: no clock reads,
    no writes, no in-memory claims — everything derives from store state).

    ``bench_id`` scopes the report to one bench (unknown ids raise
    ``ValueError``); ``now`` is the caller-injected ``generated_at``
    timestamp (controller ruling 5: testable, never a wall clock inside
    the model). See the module docstring for every disclosed derivation.
    """
    # The §5/D9 busy oracle, imported from its authority (no drift copy):
    # a run owns its bench from acceptance until its state closes terminal.
    from benchweave.interfaces.operations import LIVE_RUN_STATES

    if bench_id is not None:
        row = store.get_bench(bench_id)
        if row is None:
            raise ValueError(f"no bench {bench_id!r} in the store")
        bench_rows = [row]
    else:
        bench_rows = _bench_rows(store)

    simulated = {str(row["bench_id"]) for row in bench_rows if _is_simulated(row)}
    benches: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for row in bench_rows:
        id_ = str(row["bench_id"])
        states = store.list_run_states(id_)
        busy = any(str(state["state"]) in LIVE_RUN_STATES for state in states)
        entry: dict[str, Any] = {
            "id": id_,
            "busy": busy,
            "generation": int(row["generation"]),
        }
        if id_ in simulated:
            entry["simulation"] = True
        benches.append(entry)
        for state in states:
            run = store.get_run(str(state["run_id"]))
            run_entry: dict[str, Any] = {
                "id": str(state["run_id"]),
                "bench": id_,
                "state": str(state["state"]),
                "outcome": _outcome_of(
                    str(state["state"]), run["terminal"] if run else None
                ),
                "principal": str(run["principal_id"]) if run else "",
            }
            if id_ in simulated:
                run_entry["simulation"] = True
            runs.append(run_entry)

    covered = _covered_run_ids(store, [str(r["bench_id"]) for r in bench_rows])
    evidence = _evidence_rows(store, content, covered)
    return {
        "generated_at": now,
        "simulation": bool(simulated),
        "benches": benches,
        "runs": runs,
        "evidence": evidence,
        "missing_evidence": [entry for entry in evidence if not entry["present"]],
    }


# --- emitters ----------------------------------------------------------------------


def render_markdown(report: dict[str, Any]) -> str:
    """The operator markdown: every digest present, every simulated
    bench/run labelled, missing evidence named — never papered over."""
    lines = ["# BenchWeave report", f"generated_at: {report['generated_at']}"]
    if report.get("simulation"):
        lines.append(f"{SIMULATION_LABEL} — the report includes simulated benches/runs")
    lines.append("")
    lines.append("## Benches")
    for bench in report["benches"]:
        label = " [SIMULATION]" if bench.get("simulation") else ""
        lines.append(
            f"- {bench['id']}  generation={bench['generation']}"
            f" busy={bench['busy']}{label}"
        )
    lines.append("")
    lines.append("## Runs")
    for run in report["runs"]:
        label = " [SIMULATION]" if run.get("simulation") else ""
        lines.append(
            f"- {run['id']}  bench={run['bench']} state={run['state']}"
            f" outcome={run['outcome']} principal={run['principal']}{label}"
        )
    lines.append("")
    lines.append("## Evidence")
    for entry in report["evidence"]:
        lines.append(
            f"- {entry['evidence_id']}  kind={entry['kind']}"
            f" digest={entry['digest']} present={entry['present']}"
        )
    lines.append("")
    lines.append("## Missing evidence")
    if not report["missing_evidence"]:
        lines.append("- none")
    for entry in report["missing_evidence"]:
        lines.append(
            f"- {entry['evidence_id']}  kind={entry['kind']}"
            f" digest={entry['digest']} — absent from the content store"
        )
    return "\n".join(lines)


def render_json(report: dict[str, Any]) -> str:
    """The machine form (the ``--json`` contract): ``json.loads`` of this
    string round-trips the model exactly."""
    return json.dumps(report, indent=2, sort_keys=True)


# --- the at-rest command wrapper -----------------------------------------------------


def report_from_data_dir(
    data_dir: Path, *, bench_id: str | None = None, now: str
) -> dict[str, Any]:
    """Open the data directory's store AT REST and build the report.

    Refuses (naming the holder, through the ``daemon_holds`` gate) while a
    live gateway owns the store; refuses before that if the data directory
    carries no store.

    Read posture, disclosed truthfully (review I1): unlike the mutating
    at-rest commands this never takes the exclusive hold — but the open is
    ``Store.open``, the app-boot posture, which applies PENDING migrations
    under ``BEGIN IMMEDIATE``. On a store predating the current schema that
    is a write made without a hold (the steady-state case — every store
    ``setup`` creates is already migrated — opens purely read-only, so
    concurrent reports are safe reads exactly there). The window is bounded
    by the gate order (a live gateway is refused before the open, so the
    only concurrent writer possible is another at-rest command or report)
    and by SQLite's own file locking, which serializes the actual writes —
    never corrupting, at worst a brief block. ``atrest.verify`` is NOT a
    precedent for read-only opens: it never calls ``Store.open`` (it opens
    SQLite ``mode=ro``); matching that posture here would bypass the
    Store's public migration path, so the disclosure stands instead.
    """
    data_dir = Path(data_dir)
    db = db_path(data_dir)
    if not db.is_file():
        raise AtRestError(f"no store at {db} — run setup first")
    if daemon_holds(db):
        raise StoreHeldError(holder_info(db))
    try:
        store = Store.open(db)
    except sqlite3.Error as error:
        raise AtRestError(f"cannot open {db}: {error}") from error
    try:
        return build_report(store, ContentStore(store), bench_id=bench_id, now=now)
    except sqlite3.Error as error:
        # Corrupt pages surfacing mid-read (integrity is verify's domain,
        # but a refusal here must still be a message, never a traceback).
        raise AtRestError(f"cannot read {db}: {error}") from error
    finally:
        store.close()


def now_iso() -> str:
    """The CLI's injected clock (the model itself never reads one)."""
    return datetime.now(UTC).isoformat()
