"""Issue #194: the audited delete-tier disposition command.

The sibling of ``cli/retention.py`` on the write side: ``retention`` is
the read-only projection, ``dispose`` is the audited path it was waiting
for (Decision 8's sequencing invariant — audit trail first, then, and
only through it, deletion). The command composes three proven mechanisms
and invents no architecture: the report builder as the plan (imported,
never re-implemented — the executor's executable set IS
``build_retention_report``'s ``scheduled ∧ overdue ∧
on_disposition=delete`` rows, so selection, scoping and matched-rule
identity carry zero formula drift), the transactional audit writer
(``state/dispositions.py`` — one ``BEGIN IMMEDIATE`` per invocation),
and the at-rest wrapper (``StoreHold`` → typed never-migrate precheck →
``Store.open``), mirroring ``retention_from_data_dir`` line by line.

Posture:

- **Dry run by default, ``--execute`` to act** (fork F2): without the
  flag the command writes nothing — every table byte-identical (A7's
  census over ``sqlite_master``). The report remains the plan surface.
- **Never migrates** (fork F4): ``refuse_schema_mismatch`` runs before
  ``Store.open`` — a store missing v6 (or carrying any drift) refuses
  typed in the ``retention_store:`` family naming the upgrade path.
  Deliberately stricter than ``report``'s migration-on-open; the family
  inconsistency stays row 15's to carry (record deferral D8).
- **Never runs ungoverned**: a missing policy file (explicit or default
  location) is a typed refusal, never a silent no-op; explicit
  configuration is never silently substituted.
- **Review rows are blocked** (``blocked_review``) — the policy is the
  operator's intent channel; moving a row out of review is a policy
  edit. **Archive rows are blocked** (``blocked_archive``) and NEVER
  deleted — the archival tier is unbuilt (record deferral D1), and an
  archive row falling through to delete would be the worst lie this
  command could tell.
- STO-1: the model never reads a clock — ``now`` is caller-injected at
  the CLI boundary exactly like the retention command.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from benchweave.cli.atrest import AtRestError, db_path
from benchweave.cli.report import now_iso
from benchweave.cli.retention import (
    RetentionStoreRefused,
    _md_text,
    build_retention_report,
    refuse_schema_mismatch,
)
from benchweave.control.retention_policy import (
    RETENTION_POLICY_FILENAME,
    RetentionPolicyRejected,
    load_retention_policy_with_digest,
)
from benchweave.state.dispositions import DispositionLog, new_invocation_id
from benchweave.state.hold import StoreHold
from benchweave.state.store import Store

__all__ = [
    "dispose_from_data_dir",
    "now_iso",
    "render_json",
    "render_markdown",
]

_DELETED = "deleted"
_REVIEW = "blocked_review"
_ARCHIVE = "blocked_archive"
_SKIPPED = "skipped"

_IRREVERSIBLE_DISCLOSURE = (
    "delete is irreversible: each audit row retains the deleted content's "
    "digest and byte length (deleted_artifact_id / deleted_byte_length), "
    "never the bytes — delete reclaims space, it is not a backup; "
    "recoverable disposition is the archival tier (unbuilt)"
)


def _classify(row: dict[str, Any]) -> str:
    """The executable-set rule, verbatim from the design: only
    ``scheduled ∧ overdue ∧ on_disposition=delete`` rows execute. Review
    and archive rows that are overdue are counted as blocked; everything
    else (held, anchor-unresolved, ungoverned, not yet overdue, or any
    label outside the enum) is skipped — an unknown label can never widen
    into a harder action than it names."""
    if row["status"] != "scheduled" or not row["overdue"]:
        return _SKIPPED
    if row["on_disposition"] == "delete":
        return _DELETED
    if row["on_disposition"] == "review":
        return _REVIEW
    if row["on_disposition"] == "archive":
        return _ARCHIVE
    return _SKIPPED


def dispose_from_data_dir(
    data_dir: Path,
    *,
    bench_id: str | None = None,
    policy_path: Path | None = None,
    now: str,
    execute: bool = False,
    mid_transaction_hook: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Open the data directory's store AT REST and dispose overdue
    delete-tier rows through the audit trail (the whole window holds the
    store's exclusive hold, refusing to name the holder while a live
    gateway owns the store).

    Without ``execute`` this is a pure dry run: the plan is projected and
    NOTHING is written. With ``execute`` the whole invocation — audit
    rows, guarded deletions, artifact GC — commits as ONE transaction.

    ``mid_transaction_hook`` is TEST SUPPORT (the ``begin_kill_window``
    precedent) forwarded into the writer's open transaction; production
    callers never pass it.
    """
    data_dir = Path(data_dir)
    db = db_path(data_dir)
    if not db.is_file():
        raise AtRestError(f"no store at {db} — run setup first")

    path = Path(policy_path) if policy_path is not None else (
        data_dir / RETENTION_POLICY_FILENAME
    )
    if not path.is_file():
        # Disposition never runs ungoverned, and explicit configuration is
        # never silently substituted: a missing policy (named or default)
        # is a typed refusal, not a no-op over an ungoverned store.
        raise AtRestError(
            f"dispose: no retention policy at {path} — disposition never "
            "runs ungoverned; write one or pass --policy"
        )
    try:
        policy, policy_sha256 = load_retention_policy_with_digest(path)
    except RetentionPolicyRejected:
        raise
    except OSError as error:
        raise AtRestError(f"cannot read policy {path}: {error}") from error

    actor = f"dispose pid {os.getpid()}"
    with StoreHold(db, label=actor):
        # fork F4: never migrate — refuse on any schema mismatch first.
        refuse_schema_mismatch(db)
        try:
            store = Store.open(db)
        except RuntimeError as error:
            # Belt-and-braces (the retention wrapper's posture): the
            # precheck makes Store.open's refuse-newer guard unreachable,
            # but a RuntimeError from there is still typed here.
            raise RetentionStoreRefused(f"retention_store: {error}") from error
        except sqlite3.Error as error:
            raise AtRestError(f"cannot open {db}: {error}") from error
        try:
            report = build_retention_report(
                store, policy=policy, bench_id=bench_id, now=now
            )
            rows = [{**row, "outcome": _classify(row)} for row in report["rows"]]
            counts = {
                outcome: sum(1 for row in rows if row["outcome"] == outcome)
                for outcome in (_DELETED, _REVIEW, _ARCHIVE, _SKIPPED)
            }
            selected = [row for row in rows if row["outcome"] == _DELETED]
            bytes_reclaimed = sum(int(row["bytes"]) for row in selected)

            disclosures: list[str] = []
            if counts[_REVIEW]:
                disclosures.append(
                    f"{counts[_REVIEW]} overdue review-tier row(s) blocked — "
                    "the policy is the operator's intent channel; moving a "
                    "row out of review is a policy edit"
                )
            if counts[_ARCHIVE]:
                disclosures.append(
                    f"{counts[_ARCHIVE]} overdue archive-tier row(s) blocked — "
                    "the archival tier is not built; archive rows are never "
                    "deleted"
                )
            if counts[_SKIPPED]:
                disclosures.append(
                    f"{counts[_SKIPPED]} row(s) skipped (held, "
                    "anchor-unresolved, ungoverned or not yet overdue) — "
                    "counted, never executed"
                )
            if selected:
                disclosures.append(_IRREVERSIBLE_DISCLOSURE)
            if not execute:
                disclosures.append(
                    "dry run (no --execute): nothing was written — every "
                    "table is unchanged; re-run with --execute to dispose"
                )

            model: dict[str, Any] = {
                "generated_at": now,
                "executed": False,
                "invocation_id": None,
                "policy": {"path": str(path), "sha256": policy_sha256},
                "bench_filter": bench_id,
                "counts": counts,
                "bytes_reclaimed": bytes_reclaimed,
                "artifacts_collected": None,
                "rows": rows,
                "disclosures": disclosures,
            }
            if not execute:
                return model

            result = DispositionLog(store).execute_invocation(
                selected,
                invocation_id=new_invocation_id(),
                actor=actor,
                policy_path=str(path),
                policy_sha256=policy_sha256,
                bench_filter=bench_id,
                counts=counts,
                now=now,
                mid_hook=mid_transaction_hook,
            )
            model["executed"] = True
            model["invocation_id"] = result["invocation_id"]
            model["artifacts_collected"] = result["artifacts_collected"]
            return model
        except sqlite3.Error as error:
            raise AtRestError(f"cannot read {db}: {error}") from error
        finally:
            store.close()


# --- emitters -----------------------------------------------------------------------


def render_markdown(model: dict[str, Any]) -> str:
    """The operator markdown: execution posture, per-outcome counts, every
    row with its matched-rule identity and outcome, the disclosures."""
    title = "BenchWeave disposition" + (
        " (executed)" if model["executed"] else " (dry run)"
    )
    lines = [f"# {title}", f"generated_at: {model['generated_at']}"]
    policy = model["policy"]
    lines.append(f"policy: {policy['path']} (sha256 {policy['sha256'][:12]}…)")
    if model["bench_filter"] is not None:
        lines.append(f"bench filter: {model['bench_filter']}")
    invocation = model["invocation_id"]
    if model["executed"] and invocation is not None:
        lines.append(f"invocation: {invocation}")
    lines.append("")
    lines.append("## Outcome")
    counts = model["counts"]
    lines.append(
        f"- deleted: {counts['deleted']}"
        f" (bytes reclaimed: {model['bytes_reclaimed']})"
    )
    lines.append(f"- blocked_review: {counts['blocked_review']}")
    lines.append(f"- blocked_archive: {counts['blocked_archive']}")
    lines.append(f"- skipped: {counts['skipped']}")
    if model["artifacts_collected"] is not None:
        lines.append(f"- artifacts collected: {model['artifacts_collected']}")
    lines.append("")
    lines.append("## Rows")
    for row in model["rows"]:
        lines.append(
            f"- {_md_text(row['id'])}  class={_md_text(row['data_class'])}"
            f" bench={_md_text(row['bench']) or '-'}"
            f" status={row['status']} disposal={row['disposal_date'] or '-'}"
            f" on_disposition={row['on_disposition'] or '-'}"
            f" outcome={row['outcome']} bytes={row['bytes']}"
        )
    lines.append("")
    lines.append("## Disclosures")
    if not model["disclosures"]:
        lines.append("- none")
    for note in model["disclosures"]:
        lines.append(f"- {_md_text(note)}")
    return "\n".join(lines)


def render_json(model: dict[str, Any]) -> str:
    """The machine form: ``json.loads`` of this string round-trips the
    model exactly."""
    return json.dumps(model, indent=2, sort_keys=True)
