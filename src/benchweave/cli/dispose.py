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
  edit. **Archive rows execute only with ``--archive-target``** (issue
  #199): each archived object is staged at the destination and
  re-verified against its content address BEFORE the store transaction
  opens (STO-6); without a target they stay ``blocked_archive`` and are
  NEVER deleted — an archive row falling through to delete would be the
  worst lie this command could tell. ``--verify-archive`` re-proves
  committed archived rows' objects read-only.
- STO-1: the model never reads a clock — ``now`` is caller-injected at
  the CLI boundary exactly like the retention command.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from benchweave.cli.atrest import AtRestError, db_path
from benchweave.cli.report import now_iso

# build_retention_report is re-exported (in __all__): the plan authority.
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
from benchweave.state.dispositions import (
    DispositionLog,
    StoreChangedUnderPlan,
    new_invocation_id,
)
from benchweave.state.hold import StoreHold
from benchweave.state.store import Store

__all__ = [
    "ArchiveTargetRefused",
    "build_retention_report",
    "dispose_from_data_dir",
    "now_iso",
    "render_json",
    "render_markdown",
    "render_verify_markdown",
]

_DELETED = "deleted"
_REVIEW = "blocked_review"
_ARCHIVE = "blocked_archive"
#: The EXECUTABLE archive outcome (issue #199): an overdue archive-tier
#: row reclassified because the operator named a target. Without one the
#: row keeps ``blocked_archive`` (fork F3) and no bytes move.
_ARCHIVED = "archived"
_HELD = "held"
_UNRESOLVED = "anchor_unresolved"
_UNGOVERNED = "ungoverned"
_NOT_YET_OVERDUE = "not_yet_overdue"
#: The residual bucket: an overdue scheduled row whose on_disposition
#: label is outside the policy enum — never executable, never one of the
#: named statuses (an unknown label can never widen into a harder action
#: than it names).
_SKIPPED = "skipped"

#: The outcome vocabulary the counts carry (the report's own status
#: vocabulary for the skip lanes, the block tiers for review/archive).
_OUTCOMES = (
    _DELETED,
    _ARCHIVED,
    _REVIEW,
    _ARCHIVE,
    _HELD,
    _UNRESOLVED,
    _UNGOVERNED,
    _NOT_YET_OVERDUE,
    _SKIPPED,
)

_IRREVERSIBLE_DISCLOSURE = (
    "delete is irreversible: each audit row retains the deleted content's "
    "digest and byte length (deleted_artifact_id / deleted_byte_length), "
    "never the bytes — delete reclaims space, it is not a backup; "
    "archival is the recoverable tier: with --archive-target each "
    "archived row's bytes are staged offline, verified at copy time "
    "(archive_verified_at), and restoring them into a store is deferred "
    "(first operator request; --verify-archive re-proves the copies)"
)

_UNITS_DISCLOSURE = (
    "byte units are named, never summed across meanings: "
    "charged_ledger_bytes is the G3 reservation-ledger relief (deleted "
    "capture rows' charged bytes); artifact_bytes_freed is what the GC "
    "physically removed from disk; bytes_reclaimed (the row-bytes sum) "
    "double-counts artifacts shared by several deleted rows and is kept "
    "only as the disposal-rows method figure"
)


class ArchiveTargetRefused(ValueError):
    """A typed archival-destination refusal (the ``retention_store:``/
    ``retention_policy:`` family posture): the message carries the
    machine-matchable ``archive_target:`` prefix. Raised for an
    unwritable or uncreatable target, a target resolving inside the data
    dir, and a pre-existing destination object whose bytes do not hash
    to its content address — never resolved by retrying the same
    destination."""


def _resolve_archive_target(
    target: Path, data_dir: Path, *, create: bool
) -> Path:
    """Resolve and validate the archive destination (the ``hold_path``
    resolve() precedent for path spelling). Containment refuses a target
    inside the data dir in EVERY mode — pure path arithmetic, so the dry
    run refuses it too. With ``create`` (the execute path) the
    ``objects/`` and ``manifests/`` subdirectories are created; the dry
    run and the verify arm never write."""
    resolved = Path(target).expanduser().resolve()
    data_resolved = Path(data_dir).resolve()
    if resolved == data_resolved or data_resolved in resolved.parents:
        raise ArchiveTargetRefused(
            f"archive_target: {resolved} resolves inside the data dir "
            f"{data_resolved} — restore swaps the whole data directory "
            "with os.replace, so an archive inside it would be destroyed "
            "or moved by disaster recovery, the opposite of preservation; "
            "choose a target outside the data dir"
        )
    if create:
        # Which ancestors mkdir(parents=True) will have to create — the
        # whole new-directory chain must reach the platter, not just the
        # leaf directories (review-wave finding 1: an unfsynced new
        # directory entry can vanish with its subtree on power loss,
        # orphaning the objects the committed trail references).
        missing = [
            ancestor
            for ancestor in (resolved, *resolved.parents)
            if not ancestor.exists()
        ]
        for sub in ("objects", "manifests"):
            try:
                (resolved / sub).mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise ArchiveTargetRefused(
                    f"archive_target: cannot create {resolved / sub}: {error}"
                ) from error
        # Durability chain: the leaf directories, every ancestor that was
        # newly created, and the parent (the entry naming the target
        # lives there, created or not).
        _fsync_dir(resolved / "objects")
        _fsync_dir(resolved / "manifests")
        for ancestor in missing:
            _fsync_dir(ancestor)
        _fsync_dir(resolved.parent)
    return resolved


def _content_artifact(
    conn: sqlite3.Connection, plan: dict[str, Any]
) -> str | None:
    """The plan row's content artifact id, read from the governed row
    (evidence or finalised capture); ``None`` for a row that references
    no artifact."""
    sql = (
        "SELECT artifact_id FROM evidence WHERE evidence_id = ?"
        if plan["row_kind"] == "evidence"
        else "SELECT artifact_id FROM capture_staging WHERE capture_id = ?"
    )
    row = conn.execute(sql, (plan["id"],)).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _fsync_dir(path: Path) -> None:
    """fsync a directory entry so placed names survive power loss. On a
    platform that cannot open a directory for fsync at all (Windows
    raises ``PermissionError`` on the open) this is a no-op — the
    platform offers no directory-durability primitive to lose. Every
    OTHER failure on the open or the fsync propagates as a typed
    ``archive_target:`` refusal: a durability error must never be
    laundered into a committed trail that asserts preservation
    (review-wave finding 2)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except PermissionError:
        return
    except OSError as error:
        raise ArchiveTargetRefused(
            f"archive_target: cannot fsync {path}: {error}"
        ) from error
    try:
        os.fsync(fd)
    except OSError as error:
        raise ArchiveTargetRefused(
            f"archive_target: fsync of {path} failed: {error}"
        ) from error
    finally:
        os.close(fd)


def _place_object(objects_dir: Path, artifact_id: str, data: bytes) -> int:
    """Place one object durably: temp file in ``objects_dir`` (same
    volume) → bytes → flush → fsync → ``os.replace`` (atomic) → re-read
    from the destination → re-hash against the content address. Returns
    the object's byte length. Destination bytes are verified, never
    trusted — the write syscall returning is not proof the bytes are
    there (the GC's verify-before-collect mirror, on the write side)."""
    destination = objects_dir / artifact_id
    temp = objects_dir / f".stage-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as error:
        raise ArchiveTargetRefused(
            f"archive_target: cannot write into {objects_dir}: {error}"
        ) from error
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    os.replace(temp, destination)
    placed = destination.read_bytes()
    if hashlib.sha256(placed).hexdigest() != artifact_id.removeprefix("art-"):
        raise ArchiveTargetRefused(
            f"archive_target: freshly placed object {destination} does "
            "not hash to its content address when re-read from the "
            "destination (medium error or tampering); refusing to commit "
            "a trail row over unverifiable bytes"
        )
    return len(placed)


def _stage_archive_objects(
    conn: sqlite3.Connection,
    archive_rows: list[dict[str, Any]],
    target: Path,
    stage_hook: Callable[[int], None] | None,
) -> tuple[dict[str, int], dict[str, int]]:
    """Phase A (issue #199 §2.2): stage every DISTINCT content artifact
    of the archive rows at the destination, BEFORE any store
    transaction opens. Two passes keep AR3's contract deterministic:

    1. every NEEDED artifact that already exists at the destination is
       re-read and re-hashed — equal to the content address counts
       ``objects_deduped``; UNEQUAL refuses typed and nothing has been
       placed yet (a corrupt pre-existing object is never overwritten:
       overwriting would launder destination corruption into a fresh
       "verified" copy);
    2. every absent artifact is placed durably and re-verified
       (``_place_object``).

    Content addressing dedups byte-identical content for free: across
    invocations, across stores, after a rolled-back attempt. Returns
    ``{artifact_id: byte_length}`` for every needed artifact and the
    measured figures (``objects_placed`` / ``objects_deduped`` /
    ``bytes_copied`` — the bytes physically written this invocation, the
    disk-write unit, NOT the row-bytes sum).

    ``stage_hook`` is TEST SUPPORT (the ``mid_transaction_hook``
    precedent), firing once per distinct object AFTER its bytes verify —
    the Phase-A fault arm's kill window. Production callers never pass
    it.
    """
    objects_dir = target / "objects"
    order: list[str] = []
    payloads: dict[str, bytes] = {}
    for plan in archive_rows:
        artifact_id = _content_artifact(conn, plan)
        if artifact_id is None:
            continue
        if artifact_id in payloads:
            continue
        row = conn.execute(
            "SELECT data FROM artifacts WHERE artifact_id = ?", (artifact_id,)
        ).fetchone()
        if row is None:
            raise StoreChangedUnderPlan(
                f"dispose: store changed under the plan — artifact "
                f"{artifact_id!r} vanished before archival staging"
            )
        order.append(artifact_id)
        payloads[artifact_id] = bytes(row[0])
    facts: dict[str, int] = {}
    placed = deduped = copied = 0
    # Pass 1: verify every pre-existing destination object BEFORE placing
    # anything (AR3: the refusal leaves the destination unmodified beyond
    # the pre-existing files).
    for artifact_id in order:
        destination = objects_dir / artifact_id
        if not destination.is_file():
            continue
        existing = destination.read_bytes()
        if hashlib.sha256(existing).hexdigest() != artifact_id.removeprefix(
            "art-"
        ):
            raise ArchiveTargetRefused(
                f"archive_target: pre-existing object {destination} does "
                "not hash to its content address (destination corrupt or "
                "tampered); refusing to overwrite it — overwriting would "
                "launder destination corruption into a fresh 'verified' "
                "copy"
            )
        deduped += 1
        facts[artifact_id] = len(existing)
    # Pass 2: place the absent objects, durably, verifying each.
    for index, artifact_id in enumerate(order):
        if artifact_id in facts:
            if stage_hook is not None:
                stage_hook(index)
            continue
        byte_length = _place_object(objects_dir, artifact_id, payloads[artifact_id])
        copied += byte_length
        placed += 1
        facts[artifact_id] = byte_length
        if stage_hook is not None:
            stage_hook(index)
    if placed:
        _fsync_dir(objects_dir)
    return facts, {
        "objects_placed": placed,
        "objects_deduped": deduped,
        "bytes_copied": copied,
    }


def _write_archive_manifest(
    target: Path,
    *,
    invocation_id: str,
    actor: str,
    policy_sha256: str,
    now: str,
    counts: dict[str, int],
    facts: dict[str, int],
) -> Path:
    """Write the attempt-scoped manifest ``manifests/<invocation_id>.json``
    (canonical JSON, sort_keys) describing the objects this invocation
    needs — placed and deduped — with their byte lengths. Manifests are
    ATTEMPT-scoped, not commitment-scoped: a crashed attempt leaves a
    manifest describing objects that exist and hash-verify; the
    committed trail is the commitment record (the disclosed
    over-preservation window)."""
    manifest = {
        "invocation_id": invocation_id,
        "actor": actor,
        "policy_sha256": policy_sha256,
        "written_at": now,
        "destination_resolved": str(target),
        "objects": [
            {"artifact_id": artifact_id, "byte_length": byte_length}
            for artifact_id, byte_length in facts.items()
        ],
        "counts": counts,
    }
    path = target / "manifests" / f"{invocation_id}.json"
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    _fsync_dir(target / "manifests")
    return path


def _verify_archive_model(
    store: Store, target: Path | None, *, now: str
) -> dict[str, Any]:
    """The read-only verify arm (issue #199 §2.5, review-wave finding 3):
    for every committed ``outcome='archived'`` row, re-prove the object
    at the row's RECORDED ``archive_destination`` — the column exists for
    exactly this, so a second target (or any later disposition to
    another destination) never makes earlier rows read as drift. The
    ``--archive-target`` flag is only a FALLBACK for rows that lack a
    recorded destination; it stays the store/dispose-time argument.
    Relocating a destination reads as ``absent`` at the recorded path —
    the trail names where the copy was verified, never a flag-supplied
    guess.

    Each row's object must be present, re-hash to its content address,
    and match the trail's recorded length. Rows with no artifact
    binding, or no destination to check at all, are COUNTED as skipped —
    never silently passed (review-wave finding 5's verify half).
    Destination objects no trail row references are ORPHANS (the
    disclosed over-preservation window) — reported, never deleted
    (record deferral D2). Drift is named per object, machine-matchable
    (``absent`` / ``digest_mismatch`` / ``length_mismatch``);
    ``digest_mismatch`` takes precedence — the bytes are re-hashed
    first, never trusted from ``archived_byte_length``
    (``length_mismatch`` alone fires only when intact bytes disagree
    with a tampered trail length)."""
    fallback = (
        str(Path(target).expanduser().resolve()) if target is not None else None
    )
    drift: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    verified = 0
    referenced: dict[str, set[str]] = {}
    for disposition_id, artifact_id, byte_length, recorded in (
        store.connection.execute(
            "SELECT disposition_id, archived_artifact_id,"
            " archived_byte_length, archive_destination"
            " FROM dispositions WHERE outcome = 'archived' ORDER BY rowid"
        )
    ):
        disposition_id = str(disposition_id)
        if artifact_id is None:
            skipped.append({
                "disposition_id": disposition_id,
                "reason": "no artifact binding",
            })
            continue
        artifact_id = str(artifact_id)
        destination = str(recorded) if recorded else fallback
        if destination is None:
            skipped.append({
                "disposition_id": disposition_id,
                "archived_artifact_id": artifact_id,
                "reason": "no recorded destination",
            })
            continue
        referenced.setdefault(destination, set()).add(artifact_id)
        path = Path(destination) / "objects" / artifact_id
        if not path.is_file():
            drift.append({
                "disposition_id": disposition_id,
                "archived_artifact_id": artifact_id,
                "destination": destination,
                "problem": "absent",
            })
            continue
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != artifact_id.removeprefix(
            "art-"
        ):
            drift.append({
                "disposition_id": disposition_id,
                "archived_artifact_id": artifact_id,
                "destination": destination,
                "problem": "digest_mismatch",
            })
            continue
        if byte_length is not None and len(payload) != int(byte_length):
            drift.append({
                "disposition_id": disposition_id,
                "archived_artifact_id": artifact_id,
                "destination": destination,
                "problem": "length_mismatch",
            })
            continue
        verified += 1
    orphans: list[dict[str, str]] = []
    for destination in sorted(referenced):
        objects_dir = Path(destination) / "objects"
        if not objects_dir.is_dir():
            continue
        for entry in sorted(objects_dir.iterdir()):
            if (
                entry.is_file()
                and not entry.name.startswith(".")
                and entry.name not in referenced[destination]
            ):
                orphans.append({
                    "artifact_id": entry.name,
                    "destination": destination,
                })
    return {
        "generated_at": now,
        "executed": False,
        "mode": "verify-archive",
        "destinations": sorted(referenced),
        "verified": verified,
        "drift": drift,
        "skipped": skipped,
        "orphans": orphans,
        "clean": not drift and not skipped,
    }


def _classify(row: dict[str, Any]) -> str:
    """The executable-set rule, verbatim from the design: only
    ``scheduled ∧ overdue ∧ on_disposition=delete`` rows execute. Review
    and archive rows that are overdue are counted as blocked; the skip
    lanes split by the report's own status vocabulary (held,
    anchor-unresolved, ungoverned, not-yet-overdue), and a label outside
    the enum lands in the residual ``skipped`` bucket — never executed."""
    if row["status"] == "held":
        return _HELD
    if row["status"] == "anchor_unresolved":
        return _UNRESOLVED
    if row["status"] == "ungoverned":
        return _UNGOVERNED
    if row["status"] != "scheduled" or not row["overdue"]:
        # scheduled-but-anchored rows are never overdue before resolution;
        # an unknown status value never executes either.
        return _NOT_YET_OVERDUE if row["status"] == "scheduled" else _SKIPPED
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
    archive_target: Path | None = None,
    verify_archive: bool = False,
    mid_transaction_hook: Callable[[int], None] | None = None,
    stage_hook: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Open the data directory's store AT REST and dispose overdue
    delete-tier rows through the audit trail (the whole window holds the
    store's exclusive hold, refusing to name the holder while a live
    gateway owns the store).

    Without ``execute`` this is a pure dry run: the plan is projected and
    NOTHING is written — not to the store and not to ``archive_target``
    when one is named. With ``execute`` the whole invocation — audit
    rows, guarded deletions, artifact GC — commits as ONE transaction.

    ``archive_target`` (issue #199) makes overdue archive-tier rows
    executable: every distinct content artifact is staged at the
    destination and re-verified BEFORE the store transaction opens
    (Phase A, STO-6); without a target those rows stay
    ``blocked_archive`` and the delete tier still proceeds (fork F3).

    ``verify_archive`` (with ``archive_target``) is the read-only verify
    arm: every committed ``outcome='archived'`` row's object is re-proved
    against its content address; orphans are reported, never deleted;
    the command verifies and exits — never executes.

    ``mid_transaction_hook`` and ``stage_hook`` are TEST SUPPORT (the
    ``begin_kill_window`` precedent), firing inside the open transaction
    and after each staged object's bytes verify respectively; production
    callers never pass them.
    """
    data_dir = Path(data_dir)
    db = db_path(data_dir)
    if not db.is_file():
        raise AtRestError(f"no store at {db} — run setup first")
    if verify_archive and execute:
        raise AtRestError(
            "dispose: --verify-archive verifies and exits — never "
            "executes; drop --execute"
        )

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
            if verify_archive:
                # The read-only verify arm rides the same hold (STO-3's
                # site list stays regenerable from grep StoreHold( src/).
                return _verify_archive_model(
                    store, archive_target, now=now
                )
            report = build_retention_report(
                store, policy=policy, bench_id=bench_id, now=now
            )
            rows = [{**row, "outcome": _classify(row)} for row in report["rows"]]
            # With a target the overdue archive rows become executable
            # (issue #199 §2.6); without one they keep ``blocked_archive``
            # (fork F3) and the delete tier proceeds. The reclassification
            # is a pure label flip over the SAME plan rows — selection and
            # matched-rule identity still carry zero formula drift (AR9).
            if archive_target is not None:
                for row in rows:
                    if row["outcome"] == _ARCHIVE:
                        row["outcome"] = _ARCHIVED
            counts = {
                outcome: sum(1 for row in rows if row["outcome"] == outcome)
                for outcome in _OUTCOMES
            }
            selected = [row for row in rows if row["outcome"] == _DELETED]
            archived_rows = [row for row in rows if row["outcome"] == _ARCHIVED]
            bytes_reclaimed = sum(int(row["bytes"]) for row in selected) + sum(
                int(row["bytes"]) for row in archived_rows
            )
            charged_ledger_bytes = sum(
                int(row["bytes"])
                for row in [*selected, *archived_rows]
                if row["row_kind"] == "capture"
            )

            # The report's own disclosures ride through (the non-finalised
            # staging count, anchor-unresolved counts, scope notes) — the
            # dispose additions join them, never replace them.
            disclosures: list[str] = list(report["disclosures"])
            if counts[_REVIEW]:
                disclosures.append(
                    f"{counts[_REVIEW]} overdue review-tier row(s) blocked — "
                    "the policy is the operator's intent channel; moving a "
                    "row out of review is a policy edit"
                )
            if counts[_ARCHIVE]:
                disclosures.append(
                    f"{counts[_ARCHIVE]} overdue archive-tier row(s) blocked — "
                    "no --archive-target configured; pass one to archive "
                    "overdue archive-tier rows (verified content-addressed "
                    "copies; the store copy is reclaimed); archive rows are "
                    "never deleted"
                )
            skip_lanes = (
                f"held {counts[_HELD]}, anchor-unresolved "
                f"{counts[_UNRESOLVED]}, ungoverned {counts[_UNGOVERNED]}, "
                f"not-yet-overdue {counts[_NOT_YET_OVERDUE]}"
            )
            if any(counts[outcome] for outcome in
                   (_HELD, _UNRESOLVED, _UNGOVERNED, _NOT_YET_OVERDUE, _SKIPPED)):
                disclosures.append(
                    f"skipped rows by lane — {skip_lanes} (residual "
                    f"{counts[_SKIPPED]}): counted, never executed"
                )
            if selected or archived_rows:
                disclosures.append(_IRREVERSIBLE_DISCLOSURE)
                disclosures.append(_UNITS_DISCLOSURE)
            archive_figures: dict[str, int] | None = None
            archive_resolved: str | None = None
            if archive_target is not None:
                # Containment refuses in every mode (pure path
                # arithmetic); creation happens on the execute path only.
                archive_resolved = str(_resolve_archive_target(
                    archive_target, data_dir, create=execute
                ))
            if not execute:
                disclosures.append(
                    "dry run (no --execute): nothing was written — every "
                    "table is unchanged; re-run with --execute to dispose "
                    "(artifact bytes freed are known at execution; the dry "
                    "run reports the ledger figure only)"
                )
                if archived_rows and archive_target is not None:
                    disclosures.append(
                        "dry run with an archive target: the destination is "
                        "untouched — no objects, no manifests; objects to "
                        "place are known at execution"
                    )

            model: dict[str, Any] = {
                "generated_at": now,
                "executed": False,
                "invocation_id": None,
                "policy": {"path": str(path), "sha256": policy_sha256},
                "bench_filter": bench_id,
                "counts": counts,
                "bytes_reclaimed": bytes_reclaimed,
                "charged_ledger_bytes": charged_ledger_bytes,
                "artifact_bytes_freed": None,
                "artifacts_collected": None,
                "archive_target": (
                    {"given": str(archive_target), "resolved": archive_resolved}
                    if archive_target is not None else None
                ),
                "archive_objects_placed": None,
                "archive_objects_deduped": None,
                "archive_bytes_copied": None,
                "rows": rows,
                "disclosures": disclosures,
            }
            if not execute:
                return model

            # Phase A (STO-6): stage and re-verify every distinct archive
            # object at the destination BEFORE the store transaction
            # opens. A refusal here leaves the store untouched and the
            # destination over-preserved at worst (disclosed); the
            # invocation id is minted now so the attempt-scoped manifest
            # can name it before the transaction exists.
            invocation_id = new_invocation_id()
            staged: list[dict[str, Any]] = []
            if archived_rows and archive_resolved is not None:
                facts, archive_figures = _stage_archive_objects(
                    store.connection, archived_rows,
                    Path(archive_resolved), stage_hook,
                )
                for row in archived_rows:
                    artifact_id = _content_artifact(store.connection, row)
                    row["archived_artifact_id"] = artifact_id
                    row["archived_byte_length"] = facts.get(str(artifact_id), 0)
                    row["archive_destination"] = archive_resolved
                    row["archive_verified_at"] = now
                    staged.append(row)
                _write_archive_manifest(
                    Path(archive_resolved),
                    invocation_id=invocation_id,
                    actor=actor,
                    policy_sha256=policy_sha256,
                    now=now,
                    counts=counts,
                    facts=facts,
                )

            result = DispositionLog(store).execute_invocation(
                selected,
                invocation_id=invocation_id,
                actor=actor,
                policy_path=str(path),
                policy_sha256=policy_sha256,
                bench_filter=bench_id,
                counts=counts,
                now=now,
                archive_rows=staged,
                archive_figures=(
                    {
                        "archive_objects_placed": archive_figures["objects_placed"],
                        "archive_objects_deduped": archive_figures["objects_deduped"],
                        "archive_bytes_copied": archive_figures["bytes_copied"],
                    }
                    if archive_figures is not None else None
                ),
                mid_hook=mid_transaction_hook,
            )
            model["executed"] = True
            model["invocation_id"] = result["invocation_id"]
            model["artifacts_collected"] = result["artifacts_collected"]
            model["artifact_bytes_freed"] = result["artifact_bytes_freed"]
            model["charged_ledger_bytes"] = result["charged_ledger_bytes"]
            if archive_target is not None:
                # An executed invocation WITH a target reports measured
                # figures — zeros for the full-no-op re-run (the
                # idempotency claim is measured, never implied by
                # absence); `None` stays the dry-run placeholder only.
                figures = archive_figures or {
                    "objects_placed": 0, "objects_deduped": 0, "bytes_copied": 0,
                }
                model["archive_objects_placed"] = figures["objects_placed"]
                model["archive_objects_deduped"] = figures["objects_deduped"]
                model["archive_bytes_copied"] = figures["bytes_copied"]
            return model
        except sqlite3.Error as error:
            # The block covers the plan read AND the execution writes —
            # name the failure honestly, not "cannot read".
            raise AtRestError(f"store operation on {db} failed: {error}") from error
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
    freed = model["artifact_bytes_freed"]
    freed_text = f"{freed}" if freed is not None else "— (known at execution)"
    if model.get("archive_target") is not None:
        lines.append(f"archive target: {model['archive_target']['resolved']}")
    lines.append(
        f"- deleted: {counts['deleted']}"
        f" (charged ledger bytes: {model['charged_ledger_bytes']};"
        f" artifact bytes freed: {freed_text})"
    )
    placed = model.get("archive_objects_placed")
    if counts.get("archived") or model.get("archive_target") is not None:
        figures = (
            f"{placed} placed, {model['archive_objects_deduped']} deduped, "
            f"{model['archive_bytes_copied']} bytes copied"
            if placed is not None else "figures known at execution"
        )
        lines.append(f"- archived: {counts.get('archived', 0)} ({figures})")
    lines.append(f"- blocked_review: {counts['blocked_review']}")
    lines.append(f"- blocked_archive: {counts['blocked_archive']}")
    lines.append(
        f"- skipped — held: {counts['held']},"
        f" anchor-unresolved: {counts['anchor_unresolved']},"
        f" ungoverned: {counts['ungoverned']},"
        f" not-yet-overdue: {counts['not_yet_overdue']},"
        f" residual: {counts['skipped']}"
    )
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


def render_verify_markdown(model: dict[str, Any]) -> str:
    """The verify arm's operator markdown: the destinations checked (each
    row's recorded one), verified count, per-object drift with its
    destination, skipped rows, orphans."""
    lines = [
        "# BenchWeave archive verification",
        f"generated_at: {model['generated_at']}",
        "destinations (each row's recorded archive_destination):",
    ]
    lines.extend(f"- {d}" for d in model["destinations"])
    lines.extend([
        "",
        f"- verified: {model['verified']}",
        f"- clean: {model['clean']}",
    ])
    if model["drift"]:
        lines.append("- drift:")
        for item in model["drift"]:
            lines.append(
                f"  - {item['problem']}: {item['disposition_id']}"
                f" ({item['archived_artifact_id']}) at {item['destination']}"
            )
    if model["skipped"]:
        lines.append(
            "- skipped (cannot be verified — counted, never silently"
            " passed):"
        )
        for item in model["skipped"]:
            artifact = item.get("archived_artifact_id", "-")
            lines.append(
                f"  - {item['disposition_id']} ({artifact}):"
                f" {item['reason']}"
            )
    if model["orphans"]:
        lines.append(
            "- orphans (objects no trail row references — reported, never"
            " deleted):"
        )
        for item in model["orphans"]:
            lines.append(
                f"  - {item['artifact_id']} at {item['destination']}"
            )
    if not model["drift"] and not model["orphans"] and not model["skipped"]:
        lines.append("- no drift, no skips, no orphans")
    return "\n".join(lines)
