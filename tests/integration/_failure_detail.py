"""Self-describing outcome failures for the integration suites (issue #48).

The intermittent ubuntu CI failure (run 35328823772) landed two runs
``terminal``/``execution_error`` whose asserts truncated the run record to
``{...}`` — nothing in the log said WHAT errored, and the next occurrence
would be equally undiagnosable. These helpers attach the diagnosis to the
failure itself:

- :func:`format_run_failure` — a pure formatter over the terminal record
  and the run's error events. The terminal record's ``reasons`` carry the
  exception class and message the executor mapped (``control/executor.py``);
  the run's events carry per-step ``error_code``/``status``. For the
  in-process suites that hold a store handle.
- :func:`dump_at_rest_runs` — for the subprocess-driven suites (the
  clean-install gate, the child-process kill test) that hold no store
  handle: stdlib sqlite3, read-only, over the kept store's ``runs`` table.
  No benchweave imports — the clean-install gate's own rule (no in-process
  imports of the shipped code) holds for its diagnostics too.

Both are bounded (``_MAX_*`` caps) and never raise on odd input — a
diagnostic that crashes is worse than a truncated assert.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

__all__ = [
    "dump_at_rest_runs",
    "format_run_failure",
]

#: Bound the diagnosis: a runaway reasons list or event stream must not
#: turn the assert message into its own log-flood.
_MAX_REASONS = 40
_MAX_EVENTS = 40
#: Per-string cap for the at-rest dump (terminal records carry the full
#: evidence_refs lattice; the reasons live early in the document).
_MAX_TERMINAL_JSON_CHARS = 8000

#: Event statuses that mean the step did not cleanly complete. The
#: vocabulary is the executor's dispatch/status set; anything carrying an
#: ``error_code`` is featured regardless of status.
_ERROR_STATUSES = frozenset({"unknown", "error", "failed", "rejected"})


def _feature_events(events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """The events worth naming in a failure: every event carrying an
    ``error_code`` or an error-ish ``status``, else (when nothing matched)
    the last few events for context."""
    if not events:
        return []
    featured = [
        event
        for event in events
        if event.get("error_code") is not None
        or str(event.get("status", "")) in _ERROR_STATUSES
    ]
    if not featured:
        featured = events[-3:]
    return featured[:_MAX_EVENTS]


def format_run_failure(
    run_id: str,
    terminal: dict[str, Any] | None,
    events: list[dict[str, Any]] | None,
) -> str:
    """A bounded, self-describing failure body for an outcome mismatch.

    Names the run, the terminal record's outcome/safe_state and every
    reason (the executor's exception mapping rides ``reasons``), then each
    error event's operation/status/error_code. A missing terminal record
    (the honest-unknown case) is named, never papered over.
    """
    lines = [f"run {run_id}:"]
    if terminal is None:
        lines.append("  no terminal record (honest unknown — see gateway log)")
    else:
        lines.append(f"  body_outcome: {terminal.get('body_outcome')}")
        lines.append(f"  safe_state:   {terminal.get('safe_state')}")
        reasons = [str(reason) for reason in (terminal.get("reasons") or [])]
        if reasons:
            lines.append(f"  reasons ({min(len(reasons), _MAX_REASONS)}/{len(reasons)}):")
            lines.extend(f"    - {reason}" for reason in reasons[:_MAX_REASONS])
        else:
            lines.append("  reasons: (none recorded)")
    featured = _feature_events(events)
    if featured:
        lines.append(f"  error events ({len(featured)} shown of {len(events or [])}):")
        for event in featured:
            parts = [
                str(event.get("operation_id") or event.get("kind") or "?"),
                f"status={event.get('status')}",
            ]
            if event.get("error_code") is not None:
                parts.append(f"error_code={event.get('error_code')}")
            lines.append(f"    - {'  '.join(parts)}")
    else:
        lines.append(f"  events: none recorded ({len(events or [])} total)")
    return "\n".join(lines)


def dump_at_rest_runs(db_path: Path) -> str:
    """Every run's terminal record from the kept store, at rest.

    Stdlib sqlite3 only, opened read-only (``mode=ro`` — no WAL side
    files, no writes to the evidence under diagnosis). A missing or
    unreadable store reports itself truthfully; it never raises.
    """
    db_path = Path(db_path)
    if not db_path.is_file():
        return f"no store at {db_path} to dump"
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as error:
        return f"store {db_path} unreadable: {error}"
    try:
        rows = connection.execute(
            "SELECT run_id, terminal_json FROM runs ORDER BY started_at"
        ).fetchall()
    except sqlite3.Error as error:
        return f"store {db_path} unreadable: {error}"
    finally:
        connection.close()
    lines = [f"runs at rest in {db_path} ({len(rows)}):"]
    for run_id, terminal_json in rows:
        if not terminal_json:
            lines.append(f"  {run_id}: no terminal record")
            continue
        body = str(terminal_json)
        if len(body) > _MAX_TERMINAL_JSON_CHARS:
            body = body[:_MAX_TERMINAL_JSON_CHARS] + "…(truncated)"
        lines.append(f"  {run_id}: {body}")
    return "\n".join(lines)
