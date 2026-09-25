"""Issue #194: the disposition audit trail + audited delete-tier disposition.

The pre-committed acceptance controls A1-A9 plus the scale smoke, from the
design record at ``.claude/deep-review/2026-09-25-issue194-disposition-design.md``
(written before any implementation number existed). Every control is exact
fixture arithmetic and must fail when the mechanism commit is reverted
(absence arm). Fixture vocabulary is invented; no bench, client or DUT
identifiers from any real corpus are named.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from benchweave.cli.atrest import db_path, setup
from benchweave.cli.commands import cli
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.store import ContentStore
from benchweave.state.hold import StoreHold
from benchweave.state.store import Store

BENCH = "alpha-bench"
BENCH_TWO = "beta-bench"

T0 = "2026-09-20T00:00:00Z"
T1 = "2026-09-20T00:01:40Z"  # T0 + 100 s
T2 = "2026-09-20T00:02:00Z"  # T0 + 120 s
NOW = "2026-09-27T00:00:00Z"  # seven days after T0

_CAP_ONE = b"\x01" * 100
_CAP_TWO = b"\x02" * 300
_CAP_DUP = b"\x7f" * 64


def _combined(result: Result) -> str:
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _write_policy(path: Path) -> Path:
    """The dispose fixture policy: waveform captures delete-tier (overdue at
    NOW), raw captures review-tier (overdue), event_log evidence
    archive-tier (overdue), the default review-tier (overdue), a far-future
    delete class (not yet overdue), and a run_end class whose fixture rows
    have no run (anchor unresolved)."""
    doc: dict[str, Any] = {
        "config_version": "1",
        "default": {"duration_s": 3600, "retain_after": "landing",
                    "on_disposition": "review"},
        "classes": [
            {"selector": "capture:waveform_f64le", "duration_s": 3600,
             "retain_after": "landing", "on_disposition": "delete"},
            {"selector": "capture:raw_binary", "duration_s": 7200,
             "retain_after": "landing", "on_disposition": "review"},
            {"selector": "evidence:event_log", "duration_s": 86400,
             "retain_after": "landing", "on_disposition": "archive"},
            {"selector": "evidence:futurekind", "duration_s": 315_360_000,
             "retain_after": "landing", "on_disposition": "delete"},
            {"selector": "evidence:unreskind", "duration_s": 3600,
             "retain_after": "run_end", "on_disposition": "delete"},
        ],
        "benches": {},
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _open(data_dir: Path) -> tuple[Store, ContentStore]:
    store = Store.open(db_path(data_dir))
    return store, ContentStore(store)


def _seed(tmp_path: Path) -> Path:
    """The #194 fixture: two benches, terminal + live runs, finalised
    captures at three context keys (one byte-identical pair sharing an
    artifact), a staged capture, evidence rows of five kinds — including
    ``keepkind``, which RETAINS the deleted cap-wave's artifact (the GC
    shared-survival arm), a not-yet-overdue ``futurekind`` row and an
    anchor-unresolved ``unreskind`` row (the skip lanes)."""
    import shutil

    data_dir = tmp_path / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    setup(data_dir)
    store, content = _open(data_dir)
    try:
        store.put_bench(BENCH, 1, "qualified", "{}", "op", T0)
        store.put_bench(BENCH_TWO, 1, "qualified", "{}", "op", T0)
        for run, bench in (("run-a", BENCH), ("run-b", BENCH_TWO), ("run-c", BENCH)):
            store.create_run(run, {"procedure_id": "demo"}, "op", T0)
            store.put_run_state(run, bench, "running" if run == "run-c" else "terminal", T2)
            if run != "run-c":
                store.finalize_run(run, {"run_id": run, "outcome": "passed",
                                         "ended_at": T2})

        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        shared_wave_artifact: list[str] = []
        for cid, ctx, fmt, payload, finalise_at in (
            ("cap-wave", "run:run-a", "waveform_f64le", _CAP_ONE, T0),
            ("cap-raw", "run:run-b", "raw_binary", _CAP_TWO, T1),
            ("cap-dup-a", "run:run-a", "waveform_f64le", _CAP_DUP, T0),
            ("cap-dup-b", "run:run-a", "waveform_f64le", _CAP_DUP, T0),  # byte-identical
        ):
            writer.open_capture(capture_id=cid, context_key=ctx, fmt=fmt,
                                sample_count=None, max_bytes=1_000_000, now=T0)
            writer.append(cid, payload, ctx)
            record = writer.finalise(cid, finalise_at, ctx)
            if cid == "cap-wave":
                shared_wave_artifact.append(str(record["artifact_id"]))
        # one never-finalised capture: not governed, reclaimed by the sweep
        writer.open_capture(capture_id="cap-open", context_key="run:run-c",
                            fmt="raw_binary", sample_count=None, max_bytes=512,
                            now=T0)
        writer.append("cap-open", b"\x00" * 16, "run:run-c")

        def _put_evidence(kind: str, ctx: str | None, payload: bytes,
                          artifact: str | None = None) -> None:
            art = artifact if artifact is not None else content.put_artifact(payload, T0)
            content.put_evidence(
                kind,
                {"id": f"ref-{kind}", "version": "1",
                 "sha256": hashlib.sha256(payload).hexdigest()},
                art, ctx, T0,
            )

        for i in range(3):  # three event_log events at run-a -> archive-tier
            _put_evidence("event_log", "run:run-a", json.dumps({"i": i}).encode())
        _put_evidence("event_log", "run:run-b", b'{"single": true}')  # archive-tier
        _put_evidence("dataset", "manual-labbook", b"labbook-bytes")  # review (default)
        _put_evidence("spectrummap", "manual-labbook", b"map-bytes")  # review (default)
        # RETAINS cap-wave's artifact: review-tier, never deleted, so the
        # shared artifact must survive the artifact GC (A5).
        _put_evidence("keepkind", "run:run-a", b"keep-payload",
                      artifact=shared_wave_artifact[0])
        _put_evidence("futurekind", "run:run-a", b"future-payload")  # not yet overdue
        _put_evidence("unreskind", "manual-labbook", b"unres-payload")  # no run -> unresolved
    finally:
        store.close()
    return data_dir


def _dispose(data_dir: Path, **kw: Any) -> dict[str, Any]:
    from benchweave.cli.dispose import dispose_from_data_dir

    return dispose_from_data_dir(data_dir, **kw)


#: The classification the fixture implies at NOW (exact arithmetic):
#: deletes cap-wave(100) + cap-dup-a(64) + cap-dup-b(64); review blocks
#: cap-raw + dataset + spectrummap + keepkind; archive blocks the four
#: event_log rows; futurekind is not yet overdue and unreskind is
#: anchor-unresolved (the skip lanes, split by the report's vocabulary).
_EXPECTED_COUNTS = {"deleted": 3, "archived": 0, "blocked_review": 4,
                    "blocked_archive": 4, "held": 0, "anchor_unresolved": 1,
                    "ungoverned": 0, "not_yet_overdue": 1, "skipped": 0}
_EXPECTED_BYTES = 100 + 64 + 64


def _snapshot_all(data_dir: Path) -> dict[str, tuple[int, str]]:
    """S3-1's method with the census REGENERATED from ``sqlite_master``
    (A7): every table that exists, before and after, byte-identical."""
    uri = f"{db_path(data_dir).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%'")}
        snap: dict[str, tuple[int, str]] = {}
        for t in sorted(names):
            # t iterates sqlite_master's own name column, not user input
            rows = conn.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall()  # noqa: S608
            snap[t] = (len(rows), hashlib.sha256(repr(rows).encode()).hexdigest())
        return snap
    finally:
        conn.close()


def _rows(data_dir: Path, sql: str, args: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    uri = f"{db_path(data_dir).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return list(conn.execute(sql, args))
    finally:
        conn.close()


def _audit_rows(data_dir: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path(data_dir).resolve()}?mode=ro", uri=True)
    try:
        cursor = conn.execute("SELECT * FROM dispositions ORDER BY rowid")
        columns = [str(d[0]) for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor]
    finally:
        conn.close()


def _recomputed_digest(row: dict[str, Any]) -> str:
    """A8's INDEPENDENT recomputation: the envelope is the table row minus
    its two digest columns, canonical-JSON serialized, sha256'd — no
    production code involved. The v7 two-shape rule applies here too
    (issue #199 §2.3): the four archive columns join the envelope IFF the
    row's outcome is 'archived' — delete-tier rows keep the exact v6
    19-field shape, so their blobs are byte-identical to v6's."""
    envelope = {k: v for k, v in row.items()
                if k not in ("decision_artifact_id", "decision_sha256")}
    if row.get("outcome") != "archived":
        for field in ("archived_artifact_id", "archived_byte_length",
                      "archive_destination", "archive_verified_at"):
            envelope.pop(field, None)
    blob = json.dumps(envelope, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


# --- A1: audit atomicity -----------------------------------------------------------


def test_a1_audit_rows_match_deleted_rows_exactly(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    model = _dispose(data_dir, now=NOW, execute=True)
    assert model["counts"]["deleted"] == 3
    audit = _audit_rows(data_dir)
    assert len(audit) == 3, f"expected 3 audit rows, got {len(audit)}"
    assert {r["target_id"] for r in audit} == {"cap-wave", "cap-dup-a", "cap-dup-b"}
    assert all(r["row_kind"] == "capture" for r in audit)
    invocations = _rows(data_dir, "SELECT invocation_id, actor, counts_json,"
                                  " policy_sha256 FROM disposition_invocations")
    assert len(invocations) == 1, "exactly one invocation row per --execute"
    counts = json.loads(str(invocations[0][2]))
    assert counts["deleted"] == 3 and counts["bytes_reclaimed"] == _EXPECTED_BYTES
    # the invocation pins the governing policy digest (A1's triple check arm)
    import hashlib as _hl
    assert counts is not None
    policy_digest = _hl.sha256(
        (data_dir / "retention-policy.json").read_bytes()).hexdigest()
    assert str(invocations[0][3]) == policy_digest


def test_a1_every_deleted_target_is_gone_and_every_blocked_row_remains(
    tmp_path: Path,
) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    _dispose(data_dir, now=NOW, execute=True)
    captures = {str(r[0]) for r in _rows(
        data_dir, "SELECT capture_id FROM capture_staging")}
    assert captures == {"cap-raw", "cap-open"}, captures
    evidence = {str(r[0]) for r in _rows(data_dir, "SELECT kind FROM evidence")}
    assert evidence == {"event_log", "dataset", "spectrummap", "keepkind",
                        "futurekind", "unreskind"}, evidence


# --- A2: review blocks ----------------------------------------------------------------


def test_a2_overdue_review_rows_survive_and_are_counted(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    model = _dispose(data_dir, now=NOW, execute=True)
    assert model["counts"]["blocked_review"] == 4
    kinds = {str(r[0]) for r in _rows(
        data_dir, "SELECT kind FROM evidence WHERE kind IN ('dataset',"
                  " 'spectrummap', 'keepkind')")}
    assert kinds == {"dataset", "spectrummap", "keepkind"}, (
        "overdue review-tier evidence must remain after --execute"
    )
    assert _rows(data_dir, "SELECT capture_id FROM capture_staging"
                           " WHERE capture_id = 'cap-raw'"), (
        "the overdue review-tier capture must remain after --execute"
    )
    assert any("review" in d for d in model["disclosures"])


# --- A3: archive never deletes ------------------------------------------------------------


def test_a3_overdue_archive_rows_survive_counted_and_disclosed(
    tmp_path: Path,
) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    model = _dispose(data_dir, now=NOW, execute=True)
    assert model["counts"]["blocked_archive"] == 4
    remaining = _rows(data_dir, "SELECT COUNT(*) FROM evidence"
                                " WHERE kind = 'event_log'")
    assert int(remaining[0][0]) == 4, (
        "archive-tier rows are NEVER deleted — the archival tier is unbuilt"
    )
    assert any("archive" in d for d in model["disclosures"])


# --- A4: ledger relief (the wedge remediation, measured) ------------------------------


def test_a4_used_bytes_drop_by_exactly_the_deleted_charged_bytes(
    tmp_path: Path,
) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    ceiling = 228  # run-a's charged total: 100 + 64 + 64
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=ceiling)
        assert writer.used_bytes("run:run-a") == ceiling
        with pytest.raises(Exception, match="allowance"):
            writer.open_capture(capture_id="cap-blocked", context_key="run:run-a",
                                fmt="raw_binary", sample_count=None,
                                max_bytes=1, now=NOW)  # at ceiling -> G3 refuses
    finally:
        store.close()

    _dispose(data_dir, now=NOW, execute=True)

    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=ceiling)
        # denominator: the key's deleted finalised rows (all three of them)
        assert writer.used_bytes("run:run-a") == 0, (
            "used_bytes must drop by exactly the deleted rows' charged bytes"
        )
        # the G3 allowance formula recovered headroom: the same open now passes
        writer.open_capture(capture_id="cap-after", context_key="run:run-a",
                            fmt="raw_binary", sample_count=None,
                            max_bytes=1, now=NOW)
        writer.abort("cap-after")
    finally:
        store.close()


# --- A5: artifact GC reference-check ----------------------------------------------------


def test_a5_shared_artifact_survives_unreferenced_collected_once_decisions_kept(
    tmp_path: Path,
) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    wave_artifact = _rows(
        data_dir, "SELECT artifact_id FROM capture_staging"
                  " WHERE capture_id = 'cap-wave'")[0][0]
    dup_artifact = _rows(
        data_dir, "SELECT artifact_id FROM capture_staging"
                  " WHERE capture_id = 'cap-dup-a'")[0][0]
    assert wave_artifact != dup_artifact

    model = _dispose(data_dir, now=NOW, execute=True)

    assert model["artifacts_collected"] == 1, (
        "exactly one artifact collected: the byte-identical pair's shared "
        "artifact, once — cap-wave's artifact survives (keepkind retains it)"
    )
    assert _rows(data_dir, "SELECT artifact_id FROM artifacts"
                           " WHERE artifact_id = ?", (wave_artifact,)), (
        "an artifact shared by a retained row must survive the GC"
    )
    assert not _rows(data_dir, "SELECT artifact_id FROM artifacts"
                               " WHERE artifact_id = ?", (dup_artifact,)), (
        "a fully unreferenced artifact must be collected"
    )
    orphans = _rows(
        data_dir,
        "SELECT d.disposition_id FROM dispositions d"
        " LEFT JOIN artifacts a ON a.artifact_id = d.decision_artifact_id"
        " WHERE a.artifact_id IS NULL",
    )
    assert orphans == [], "decision artifacts are live references — never collected"


# --- fold fix 2: digest recompute at deletion ---------------------------------------------


def test_fold2_corrupted_dropped_artifact_refuses_typed_and_rolls_back(
    tmp_path: Path,
) -> None:
    """The finalise-mirroring guard: before GC deletes a dropped
    artifact, its bytes are re-read and re-hashed against the
    content-address embedded in its id — stored bytes are verified, never
    trusted. A corrupted-in-place artifact (data flipped, id kept) makes
    ``--execute`` refuse typed (StoreChangedUnderPlan family) and the
    whole invocation rolls back: nothing deleted, no audit rows, no
    invocation row, ledger untouched."""
    from benchweave.state.dispositions import StoreChangedUnderPlan

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    dup_artifact = _rows(
        data_dir, "SELECT artifact_id FROM capture_staging"
                  " WHERE capture_id = 'cap-dup-a'")[0][0]
    conn = sqlite3.connect(str(db_path(data_dir)))
    conn.execute("UPDATE artifacts SET data = ? WHERE artifact_id = ?",
                 (b"corrupted-in-place", dup_artifact))
    conn.commit()
    conn.close()

    with pytest.raises(StoreChangedUnderPlan, match="store changed under the plan"):
        _dispose(data_dir, now=NOW, execute=True)

    audit, invocations = _rows(
        data_dir, "SELECT (SELECT COUNT(*) FROM dispositions),"
                  " (SELECT COUNT(*) FROM disposition_invocations)")[0]
    assert (int(audit), int(invocations)) == (0, 0), "the refusal must roll back whole"
    captures = {str(r[0]) for r in _rows(
        data_dir, "SELECT capture_id FROM capture_staging")}
    assert captures == {"cap-wave", "cap-raw", "cap-dup-a", "cap-dup-b", "cap-open"}, (
        "no governed row may be deleted by a refused invocation"
    )
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=10_000_000)
        assert writer.used_bytes("run:run-a") == 228, "the ledger must be untouched"
    finally:
        store.close()


# --- fold fix 1: the StoreChangedUnderPlan refusal lanes ------------------------------------


def _patched_plan(
    monkeypatch: pytest.MonkeyPatch, doctor: Any,
) -> None:
    """Replace the plan builder at dispose's import site with a wrapper
    that calls the real builder then doctors one row — the deterministic
    seam for plan-vs-store drift (the guard's whole job)."""
    from benchweave.cli import dispose as dispose_module

    real = dispose_module.build_retention_report

    def wrapper(store: Any, **kw: Any) -> dict[str, Any]:
        model = real(store, **kw)
        doctor(store, model)
        return model

    monkeypatch.setattr(dispose_module, "build_retention_report", wrapper)


def _assert_clean_rollback(
    data_dir: Path, captures: set[str], ledger_run_a: int = 228,
) -> None:
    """The rollback shape: zero audit rows, zero invocation rows, exactly
    the given capture rows, and run:run-a's ledger at the given baseline —
    the pristine 228, or the post-doctor figure when the doctor itself
    removed a row (the vanished lane deletes cap-dup-b = 64 bytes outside
    the transaction; the refusal must change nothing FURTHER)."""
    audit, invocations = _rows(
        data_dir, "SELECT (SELECT COUNT(*) FROM dispositions),"
                  " (SELECT COUNT(*) FROM disposition_invocations)")[0]
    assert (int(audit), int(invocations)) == (0, 0), (
        "a refused invocation must roll back whole — no audit rows, no invocation row"
    )
    assert {str(r[0]) for r in _rows(
        data_dir, "SELECT capture_id FROM capture_staging")} == captures
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=10_000_000)
        assert writer.used_bytes("run:run-a") == ledger_run_a, (
            "the refusal must not move the ledger"
        )
    finally:
        store.close()


def test_fold1_drifted_landing_stamp_refuses_typed_and_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard lane (three converged review lanes): a governed row whose
    landing stamp moved between plan and execution (here: the plan lies —
    same shape as the store moving) refuses typed and the WHOLE invocation
    rolls back, including the rows already audited-and-deleted earlier in
    the same transaction (cap-wave, cap-dup-a precede the drifted
    cap-dup-b in plan order)."""
    from benchweave.state.dispositions import StoreChangedUnderPlan

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")

    def drift(_store: Any, model: dict[str, Any]) -> None:
        for row in model["rows"]:
            if row["id"] == "cap-dup-b":
                row["anchor_at"] = "2026-09-20T00:00:01Z"  # store says T0

    _patched_plan(monkeypatch, drift)
    with pytest.raises(StoreChangedUnderPlan, match="landing stamp moved"):
        _dispose(data_dir, now=NOW, execute=True)
    _assert_clean_rollback(
        data_dir, {"cap-wave", "cap-raw", "cap-dup-a", "cap-dup-b", "cap-open"})


def test_fold1_vanished_row_refuses_typed_and_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard lane: a governed row deleted between plan and execution (a
    non-flock concurrent writer; the disclosed row-16 residual) refuses
    typed — never a silent skip and never a wrong-row deletion — with the
    same whole-invocation rollback."""
    from benchweave.state.dispositions import StoreChangedUnderPlan

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")

    def vanish(store: Any, model: dict[str, Any]) -> None:
        assert any(row["id"] == "cap-dup-b" for row in model["rows"])
        store.connection.execute(
            "DELETE FROM capture_staging WHERE capture_id = 'cap-dup-b'")

    _patched_plan(monkeypatch, vanish)
    with pytest.raises(StoreChangedUnderPlan, match="vanished"):
        _dispose(data_dir, now=NOW, execute=True)
    _assert_clean_rollback(
        data_dir, {"cap-wave", "cap-raw", "cap-dup-a", "cap-open"},
        ledger_run_a=164)  # the doctor's own delete (cap-dup-b, 64 B) stands


# --- fold fix 3: the evidence-tier acceptance arm --------------------------------------------


def _seed_evidence_tier(tmp_path: Path) -> Path:
    """A minimal evidence-disposition fixture: two ``sharekind`` evidence
    rows SHARING one artifact (both overdue delete-tier), plus one
    retained ``otherkind`` row with its own artifact, under one
    unattributed context key."""
    import shutil

    data_dir = tmp_path / "data-ev"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    setup(data_dir)
    data_dir.joinpath("retention-policy.json").write_text(
        json.dumps({
            "config_version": "1",
            "default": {"duration_s": 3600, "retain_after": "landing",
                        "on_disposition": "review"},
            "classes": [
                {"selector": "evidence:sharekind", "duration_s": 3600,
                 "retain_after": "landing", "on_disposition": "delete"},
            ],
            "benches": {},
        }),
        encoding="utf-8",
    )
    store, content = _open(data_dir)
    try:
        shared = content.put_artifact(b"shared-evidence-bytes", T0)
        for i in range(2):
            content.put_evidence(
                "sharekind",
                {"id": f"share-{i}", "version": "1",
                 "sha256": hashlib.sha256(b"shared-evidence-bytes").hexdigest()},
                shared, "run:ev-run", T0)
        content.put_evidence(
            "otherkind",
            {"id": "other", "version": "1",
             "sha256": hashlib.sha256(b"other-bytes").hexdigest()},
            content.put_artifact(b"other-bytes", T0), "run:ev-run", T0)
    finally:
        store.close()
    return data_dir


def test_fold3_overdue_evidence_delete_tier_disposes_audits_and_gcs(
    tmp_path: Path,
) -> None:
    data_dir = _seed_evidence_tier(tmp_path)
    # the shared artifact is the one whose payload is b"shared-evidence-bytes"
    shared_artifact = _rows(
        data_dir, "SELECT artifact_id FROM artifacts"
                  " WHERE LENGTH(data) = 21")[0][0]

    model = _dispose(data_dir, now=NOW, execute=True)

    assert model["counts"]["deleted"] == 2
    audit = _audit_rows(data_dir)
    assert len(audit) == 2 and all(r["row_kind"] == "evidence" for r in audit)
    for row in audit:
        assert _recomputed_digest(row) == row["decision_sha256"], (
            "evidence-tier audit digests must recompute"
        )
    kinds = {str(r[0]) for r in _rows(data_dir, "SELECT kind FROM evidence")}
    assert kinds == {"otherkind"}, "only the governed delete-tier rows go"
    # evidence never enters the capture ledger: used_bytes is unchanged
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=10_000_000)
        assert writer.used_bytes("run:ev-run") == 0
    finally:
        store.close()
    # the shared artifact is collected exactly once (both rows dropped it)
    assert model["artifacts_collected"] == 1
    assert not _rows(data_dir, "SELECT artifact_id FROM artifacts"
                               " WHERE artifact_id = ?", (shared_artifact,))
    assert _rows(data_dir, "SELECT COUNT(*) FROM artifacts")[0][0] == 3, (
        "the retained row's artifact survives, plus the two decision artifacts"
    )


def test_fold3_kind_drift_between_plan_and_execute_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evidence kind-guard lane: the plan says ``evidence:flipped``
    while the store row still carries ``sharekind`` — the guarded delete's
    kind cross-check refuses typed (never a wrong-row deletion), whole
    invocation rolled back."""
    from benchweave.state.dispositions import StoreChangedUnderPlan

    data_dir = _seed_evidence_tier(tmp_path)

    def flip(_store: Any, model: dict[str, Any]) -> None:
        for row in model["rows"]:
            if row["data_class"] == "evidence:sharekind":
                row["data_class"] = "evidence:flipped"

    _patched_plan(monkeypatch, flip)
    with pytest.raises(StoreChangedUnderPlan, match="kind drifted"):
        _dispose(data_dir, now=NOW, execute=True)
    audit, invocations = _rows(
        data_dir, "SELECT (SELECT COUNT(*) FROM dispositions),"
                  " (SELECT COUNT(*) FROM disposition_invocations)")[0]
    assert (int(audit), int(invocations)) == (0, 0)
    assert int(_rows(data_dir, "SELECT COUNT(*) FROM evidence")[0][0]) == 3, (
        "no evidence row may be deleted by a refused invocation"
    )


# --- issue #199: the archive tier — writer-level two-shape pin (AR8's
# writer half; the with-target arms below drive the same path end to end)


def test_ar8_writer_archived_outcome_lands_two_shape_envelopes(
    tmp_path: Path,
) -> None:
    """The writer-level half of AR8: ``execute_invocation`` with archive
    rows (each carrying the Phase-A staged facts) lands
    ``outcome='archived'`` audit rows whose envelopes carry the 19 base
    fields PLUS the four archive fields (``deleted_*`` NULL/0 — nothing
    was destroyed), while delete rows in the SAME invocation keep the
    exact v6 19-field shape; one invocation row carries ``archived`` and
    the three archive copy figures; the governed rows of both tiers are
    gone through the same guarded deletes."""
    from benchweave.cli.retention import build_retention_report
    from benchweave.control.retention_policy import load_retention_policy
    from benchweave.state.dispositions import DispositionLog, new_invocation_id

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    policy = load_retention_policy(data_dir / "retention-policy.json")
    store = Store.open(db_path(data_dir))
    try:
        report = build_retention_report(store, policy=policy, now=NOW)
        rows = report["rows"]
        deletes = [dict(r) for r in rows
                   if r["status"] == "scheduled" and r["overdue"]
                   and r["on_disposition"] == "delete"]
        archives = [dict(r) for r in rows
                    if r["status"] == "scheduled" and r["overdue"]
                    and r["on_disposition"] == "archive"]
        assert (len(deletes), len(archives)) == (3, 4)
        # Attach the staged facts the Phase-A stager produces (§2.2): the
        # binding content address, its measured byte length, the resolved
        # destination, and the caller-supplied verified-at instant.
        pairs = _rows(
            data_dir,
            "SELECT e.evidence_id, e.artifact_id, LENGTH(a.data)"
            " FROM evidence e JOIN artifacts a ON a.artifact_id = e.artifact_id"
            " WHERE e.kind = 'event_log'",
        )
        facts = {str(p[0]): (str(p[1]), int(p[2])) for p in pairs}
        destination = str(tmp_path / "offline-target")
        for row in archives:
            artifact_id, byte_length = facts[str(row["id"])]
            row["archived_artifact_id"] = artifact_id
            row["archived_byte_length"] = byte_length
            row["archive_destination"] = destination
            row["archive_verified_at"] = NOW
        result = DispositionLog(store).execute_invocation(
            deletes,
            invocation_id=new_invocation_id(),
            actor="writer-probe pid 0",
            policy_path=str(data_dir / "retention-policy.json"),
            policy_sha256="0" * 64,
            bench_filter=None,
            counts={"deleted": 3, "blocked_review": 4, "blocked_archive": 0,
                    "archived": 4, "held": 0, "anchor_unresolved": 1,
                    "ungoverned": 0, "not_yet_overdue": 1, "skipped": 0},
            now=NOW,
            archive_rows=archives,
            archive_figures={
                "archive_objects_placed": 4,
                "archive_objects_deduped": 0,
                "archive_bytes_copied": 0,
            },
        )
    finally:
        store.close()

    assert result["charged_ledger_bytes"] == 228, (
        "the seed's archived rows are evidence — only the delete-tier "
        "captures charge the ledger here"
    )
    audit = _audit_rows(data_dir)
    by_outcome: dict[str, list[dict[str, Any]]] = {}
    for r in audit:
        by_outcome.setdefault(str(r["outcome"]), []).append(r)
    assert len(by_outcome["deleted"]) == 3
    assert len(by_outcome["archived"]) == 4
    for r in by_outcome["deleted"]:
        assert r["archived_artifact_id"] is None, (
            "delete rows keep the v6 shape: archive columns NULL"
        )
        assert r["deleted_artifact_id"] is not None
    for r in by_outcome["archived"]:
        assert r["deleted_artifact_id"] is None, "nothing was destroyed"
        assert r["deleted_byte_length"] == 0
        assert str(r["archived_artifact_id"]).startswith("art-")
        assert r["archive_destination"] == destination
        assert r["archive_verified_at"] == NOW
    for r in audit:
        assert _recomputed_digest(r) == r["decision_sha256"], (
            f"{r['disposition_id']}: both envelope shapes must recompute"
        )
    counts = json.loads(str(_rows(
        data_dir, "SELECT counts_json FROM disposition_invocations")[0][0]))
    assert counts["deleted"] == 3 and counts["archived"] == 4
    assert counts["archive_objects_placed"] == 4
    assert counts["archive_objects_deduped"] == 0
    assert counts["archive_bytes_copied"] == 0
    assert sorted(result["archived"]) == sorted(
        str(r[0]) for r in _rows(
            data_dir, "SELECT target_id FROM dispositions"
                      " WHERE outcome = 'archived'"))


# --- issue #199: the archive tier end to end (AR1/AR2/AR3/AR6/AR9) ------------------


def _tree_snapshot(root: Path) -> dict[str, tuple[int, str]]:
    """AR6's destination census: every file under ``root`` keyed by
    POSIX-relative path, with size and sha256 (a missing root is the
    empty tree — the before/after comparison catches creation too)."""
    files: dict[str, tuple[int, str]] = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files[path.relative_to(root).as_posix()] = (
                    path.stat().st_size,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
    return files


def test_ar1_archive_executes_through_the_trail(tmp_path: Path) -> None:
    """AR1: with a target and ``--execute``, the archive tier executes
    through the audit trail exactly like the delete tier — audit rows
    with ``outcome='archived'`` equal the plan's archive rows (the four
    event_log rows), every governed row gone, every archived row's
    object present at ``objects/<archived_artifact_id>``, re-hashing to
    its content address with the recorded length, one invocation row,
    and a per-invocation manifest describing exactly those objects."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    target = tmp_path / "offline-target"
    model = _dispose(data_dir, now=NOW, execute=True, archive_target=target)
    assert model["counts"]["archived"] == 4, (
        "denominator: the plan's archive rows (the four event_log rows)"
    )
    assert model["counts"]["blocked_archive"] == 0
    assert model["counts"]["deleted"] == 3, "the delete tier still executes"
    audit = [r for r in _audit_rows(data_dir) if r["outcome"] == "archived"]
    assert len(audit) == 4
    assert int(_rows(data_dir, "SELECT COUNT(*) FROM evidence"
                              " WHERE kind = 'event_log'")[0][0]) == 0, (
        "every governed archive row is gone (the same guarded delete)"
    )
    for r in audit:
        obj = target / "objects" / str(r["archived_artifact_id"])
        assert obj.is_file(), f"object missing for {r['disposition_id']}"
        payload = obj.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == str(
            r["archived_artifact_id"]).removeprefix("art-"), (
            "destination bytes must re-hash to the content address"
        )
        assert len(payload) == r["archived_byte_length"]
    assert int(_rows(data_dir, "SELECT COUNT(*) FROM"
                               " disposition_invocations")[0][0]) == 1
    manifest = target / "manifests" / f"{model['invocation_id']}.json"
    assert manifest.is_file(), "one attempt-scoped manifest per invocation"
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    assert doc["invocation_id"] == model["invocation_id"]
    assert doc["written_at"] == NOW  # STO-1: the caller-supplied now
    assert {o["artifact_id"] for o in doc["objects"]} == {
        str(r["archived_artifact_id"]) for r in audit}


def test_ar2_no_target_still_blocks_archive_but_delete_tier_proceeds(
    tmp_path: Path,
) -> None:
    """AR2 (fork F3, the review-tier precedent): overdue archive rows
    with no ``--archive-target`` SURVIVE, are counted ``blocked_archive``,
    and the disclosure names the missing flag — while delete-tier rows in
    the SAME invocation still execute. Behavior byte-identical to the
    pre-#199 command for archive rows (the old A3 semantics)."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    model = _dispose(data_dir, now=NOW, execute=True)
    assert model["counts"]["blocked_archive"] == 4
    assert model["counts"]["archived"] == 0
    assert model["counts"]["deleted"] == 3, (
        "a missing archive target never punishes the delete tier"
    )
    assert int(_rows(data_dir, "SELECT COUNT(*) FROM evidence"
                              " WHERE kind = 'event_log'")[0][0]) == 4, (
        "archive-tier rows are NEVER deleted"
    )
    assert any("--archive-target" in d for d in model["disclosures"]), (
        "the disclosure must name the missing flag"
    )
    captures = {str(r[0]) for r in _rows(
        data_dir, "SELECT capture_id FROM capture_staging")}
    assert captures == {"cap-raw", "cap-open"}, "the delete tier executed"


def test_ar3_corrupt_preexisting_destination_object_refuses_whole(
    tmp_path: Path,
) -> None:
    """AR3 (never delete-without-copy): a pre-existing destination object
    whose bytes do NOT hash to its content address ⇒ typed
    ``archive_target:`` refusal BEFORE anything is placed or disposed —
    the store stays byte-identical (table census), the governed rows are
    present, and the destination is unmodified beyond the pre-existing
    file. Overwriting would launder destination corruption into a fresh
    'verified' copy."""
    from benchweave.cli.dispose import ArchiveTargetRefused

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    target = tmp_path / "offline-target"
    (target / "objects").mkdir(parents=True)
    needed = _rows(
        data_dir,
        "SELECT e.artifact_id FROM evidence e"
        " WHERE e.kind = 'event_log' ORDER BY e.rowid",
    )
    corrupt_id = str(needed[0][0])
    planted = b"wrong-bytes-under-a-needed-address"
    (target / "objects" / corrupt_id).write_bytes(planted)
    before = _snapshot_all(data_dir)
    with pytest.raises(ArchiveTargetRefused, match="archive_target:"):
        _dispose(data_dir, now=NOW, execute=True, archive_target=target)
    assert _snapshot_all(data_dir) == before, (
        "the refusal must leave the store byte-identical (nothing opened "
        "a transaction)"
    )
    assert int(_rows(data_dir, "SELECT COUNT(*) FROM evidence"
                              " WHERE kind = 'event_log'")[0][0]) == 4
    snapshot = _tree_snapshot(target)
    assert list(snapshot) == [f"objects/{corrupt_id}"], (
        "the destination is unmodified beyond the pre-existing file"
    )
    assert (target / "objects" / corrupt_id).read_bytes() == planted, (
        "a corrupt pre-existing object is NEVER silently overwritten"
    )


def test_ar6_dry_run_with_target_writes_nothing_to_either_tree(
    tmp_path: Path,
) -> None:
    """AR6 (dry-run purity, both trees): the dry run writes nothing to
    the store AND nothing to the destination — no objects, no manifests
    (a target that does not exist yet stays non-existent); the would-be
    archive outcomes and the resolved target are reported with
    placeholder copy figures ('objects to place are known at
    execution')."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    target = tmp_path / "offline-target"
    before = _snapshot_all(data_dir)
    model = _dispose(data_dir, now=NOW, archive_target=target)
    assert _snapshot_all(data_dir) == before, "store byte-identical"
    assert not target.exists(), "no objects, no manifests — tree unchanged"
    assert model["counts"]["archived"] == 4
    assert model["counts"]["deleted"] == 3  # would-be outcomes
    assert model["archive_objects_placed"] is None
    assert model["archive_objects_deduped"] is None
    assert model["archive_bytes_copied"] is None
    assert model["archive_target"] is not None
    assert model["archive_target"]["resolved"]
    # An existing destination tree is equally untouched.
    target.mkdir()
    (target / "objects").mkdir()
    seeded_object = target / "objects" / "art-preexisting"
    seeded_object.write_bytes(b"already-there")
    tree_before = _tree_snapshot(target)
    store_before = _snapshot_all(data_dir)
    _dispose(data_dir, now=NOW, archive_target=target)
    assert _tree_snapshot(target) == tree_before
    assert _snapshot_all(data_dir) == store_before


def test_ar9_archive_plan_parity_with_the_report_builder(tmp_path: Path) -> None:
    """AR9 (plan parity successor): the dry-run plan's archive-outcome
    rows ARE ``build_retention_report``'s ``scheduled ∧ overdue ∧
    on_disposition=archive`` rows — same ids, same matched-rule
    identity; any second derivation in the executor shows here as
    drift."""
    from benchweave.cli.retention import build_retention_report
    from benchweave.control.retention_policy import load_retention_policy

    data_dir = _seed(tmp_path)
    policy_path = _write_policy(data_dir / "retention-policy.json")
    policy = load_retention_policy(policy_path)
    store = Store.open(db_path(data_dir))
    try:
        report = build_retention_report(store, policy=policy, now=NOW)
    finally:
        store.close()
    expected = [
        (r["id"], r["matched_selector"], r["matched_scope"], r["matched_rule"],
         r["data_class"], r["bytes"])
        for r in report["rows"]
        if r["status"] == "scheduled" and r["overdue"]
        and r["on_disposition"] == "archive"
    ]
    model = _dispose(data_dir, now=NOW, archive_target=tmp_path / "t")
    planned = [
        (r["id"], r["matched_selector"], r["matched_scope"], r["matched_rule"],
         r["data_class"], r["bytes"])
        for r in model["rows"] if r["outcome"] == "archived"
    ]
    assert planned == expected, (
        "the executor's archive plan must be the report builder's rows "
        "verbatim — any second derivation shows here as drift"
    )
    assert len(planned) == 4


def test_archive_target_inside_the_data_dir_refuses_typed(
    tmp_path: Path,
) -> None:
    """The containment refusal: a target resolving INSIDE the data dir
    would be destroyed or moved by ``restore``'s whole-directory
    ``os.replace`` — the exact opposite of preservation; typed in the
    ``archive_target:`` family, refusing in the dry run too (the check
    is pure path arithmetic)."""
    from benchweave.cli.dispose import ArchiveTargetRefused

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    inside = data_dir / "offline"
    with pytest.raises(ArchiveTargetRefused, match="archive_target:"):
        _dispose(data_dir, now=NOW, execute=True, archive_target=inside)
    with pytest.raises(ArchiveTargetRefused, match="inside the data dir"):
        _dispose(data_dir, now=NOW, archive_target=inside)


def test_archive_target_uncreatable_refuses_typed(tmp_path: Path) -> None:
    """The unwritable/uncreatable target lane: a target under a FILE (the
    parent path is not a directory) is a typed ``archive_target:``
    refusal, never a traceback."""
    from benchweave.cli.dispose import ArchiveTargetRefused

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    with pytest.raises(ArchiveTargetRefused, match="archive_target:"):
        _dispose(
            data_dir, now=NOW, execute=True,
            archive_target=blocker / "nested" / "target",
        )


def _seed_archive_captures(tmp_path: Path) -> Path:
    """The #199 archive-CAPTURE fixture: one run key with four finalised
    overdue archive-tier captures — ``cap-arch-a``'s artifact is shared
    with a retained review-tier evidence row (the shared-survival arm),
    and the byte-identical ``cap-arch-c``/``cap-arch-d`` pair shares one
    artifact (staged once, deduped at the destination)."""
    import shutil

    data_dir = tmp_path / "data-arch"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    setup(data_dir)
    data_dir.joinpath("retention-policy.json").write_text(
        json.dumps({
            "config_version": "1",
            "default": {"duration_s": 3600, "retain_after": "landing",
                        "on_disposition": "review"},
            "classes": [
                {"selector": "capture:waveform_f64le", "duration_s": 3600,
                 "retain_after": "landing", "on_disposition": "archive"},
            ],
            "benches": {},
        }),
        encoding="utf-8",
    )
    store, content = _open(data_dir)
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=10_000_000)
        shared: list[str] = []
        for cid, payload in (
            ("cap-arch-a", b"\x11" * 40),
            ("cap-arch-b", b"\x22" * 50),
            ("cap-arch-c", b"\x33" * 60),
            ("cap-arch-d", b"\x33" * 60),  # byte-identical pair
        ):
            writer.open_capture(capture_id=cid, context_key="run:arch-run",
                                fmt="waveform_f64le", sample_count=None,
                                max_bytes=1000, now=T0)
            writer.append(cid, payload, "run:arch-run")
            record = writer.finalise(cid, T0, "run:arch-run")
            if cid == "cap-arch-a":
                shared.append(str(record["artifact_id"]))
        # a retained review-tier evidence row sharing cap-arch-a's
        # artifact: the shared-survival arm (in-store AND offline).
        content.put_evidence(
            "keepkind",
            {"id": "ref-keepkind", "version": "1",
             "sha256": hashlib.sha256(b"keep").hexdigest()},
            shared[0], "manual-labbook", T0,
        )
    finally:
        store.close()
    return data_dir


def test_ar4_archive_relieves_ledger_and_gcs_exactly_like_delete(
    tmp_path: Path,
) -> None:
    """AR4 (ledger + GC): a seeded key with archived captures —
    ``used_bytes`` drops by exactly Σ charged bytes of the archived
    capture rows (denominator: that key's archived finalised rows); an
    unshared archived artifact's in-store row is collected; an artifact
    shared with a retained row survives in-store AND exists offline;
    decision artifacts are never collected. The GC predicate is
    UNCHANGED — ``archived_artifact_id`` is a record, never a live
    reference."""
    data_dir = _seed_archive_captures(tmp_path)
    target = tmp_path / "offline-target"
    ceiling = 40 + 50 + 60 + 60  # the key's charged total
    ids = {str(r[0]): str(r[1]) for r in _rows(
        data_dir, "SELECT capture_id, artifact_id FROM capture_staging")}
    shared_artifact = ids["cap-arch-a"]
    solo_artifact = ids["cap-arch-b"]
    pair_artifact = ids["cap-arch-c"]
    assert ids["cap-arch-d"] == pair_artifact, "the byte-identical pair shares"

    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=ceiling)
        assert writer.used_bytes("run:arch-run") == ceiling
    finally:
        store.close()

    model = _dispose(data_dir, now=NOW, execute=True, archive_target=target)

    assert model["counts"]["archived"] == 4
    assert model["charged_ledger_bytes"] == ceiling, (
        "the ledger relief covers the archived captures' charged bytes"
    )
    assert model["artifact_bytes_freed"] == 50 + 60, (
        "only the unshared artifacts leave disk (solo 50 + pair 60 once); "
        "cap-arch-a's survives in-store (keepkind retains it)"
    )
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=ceiling)
        assert writer.used_bytes("run:arch-run") == 0, (
            "used_bytes must drop by exactly the archived rows' charged bytes"
        )
    finally:
        store.close()
    assert model["artifacts_collected"] == 2
    assert _rows(data_dir, "SELECT artifact_id FROM artifacts"
                          " WHERE artifact_id = ?", (shared_artifact,)), (
        "an artifact shared by a retained row must survive the GC in-store"
    )
    assert (target / "objects" / shared_artifact).is_file(), (
        "…AND the shared artifact's offline copy exists"
    )
    assert not _rows(data_dir, "SELECT artifact_id FROM artifacts"
                               " WHERE artifact_id = ?", (solo_artifact,)), (
        "a fully unreferenced archived artifact must be collected "
        "(the offline object is the surviving copy)"
    )
    assert not _rows(data_dir, "SELECT artifact_id FROM artifacts"
                               " WHERE artifact_id = ?", (pair_artifact,))
    orphans = _rows(
        data_dir,
        "SELECT d.disposition_id FROM dispositions d"
        " LEFT JOIN artifacts a ON a.artifact_id = d.decision_artifact_id"
        " WHERE a.artifact_id IS NULL",
    )
    assert orphans == [], "decision artifacts are live references — never collected"


# --- issue #199: the verify arm (AR7) ------------------------------------------------


def _archived_store(tmp_path: Path) -> tuple[Path, Path]:
    """A seeded store with the archive tier already executed once:
    returns ``(data_dir, target)`` with four committed archived rows and
    their four destination objects."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    target = tmp_path / "offline-target"
    _dispose(data_dir, now=NOW, execute=True, archive_target=target)
    return data_dir, target


def test_ar7_verify_archive_clean_drift_and_orphans(tmp_path: Path) -> None:
    """AR7: a clean destination verifies every archived row with zero
    drift; a flipped object byte is named ``digest_mismatch`` (re-hash,
    never trusting ``archived_byte_length``); a deleted object is named
    ``absent``; a tampered trail length over intact bytes is named
    ``length_mismatch``; a planted orphan object is REPORTED and never
    deleted (an orphan is over-preservation, not drift)."""
    data_dir, target = _archived_store(tmp_path)
    model = _dispose(data_dir, now=NOW, archive_target=target,
                     verify_archive=True)
    assert model["mode"] == "verify-archive"
    assert model["clean"] is True
    assert model["drift"] == []
    assert model["verified"] == 4, (
        "denominator: the store's archived audit rows"
    )
    assert model["executed"] is False  # the verify arm never executes

    audit = _audit_rows(data_dir)
    archived = [r for r in audit if r["outcome"] == "archived"]
    flipped = target / "objects" / str(archived[0]["archived_artifact_id"])
    payload = bytearray(flipped.read_bytes())
    payload[0] ^= 0xFF  # same length, wrong bytes
    flipped.write_bytes(bytes(payload))
    model = _dispose(data_dir, now=NOW, archive_target=target,
                     verify_archive=True)
    assert model["clean"] is False
    assert [(d["problem"], d["disposition_id"]) for d in model["drift"]] == [
        ("digest_mismatch", archived[0]["disposition_id"])
    ]

    gone = target / "objects" / str(archived[1]["archived_artifact_id"])
    gone.unlink()
    model = _dispose(data_dir, now=NOW, archive_target=target,
                     verify_archive=True)
    problems = sorted(d["problem"] for d in model["drift"])
    assert problems == ["absent", "digest_mismatch"], problems

    # length_mismatch fires when the OBJECT re-hashes to its address but
    # the TRAIL's recorded length disagrees (trail tampering over intact
    # bytes — the only lane where it can appear alone).
    conn = sqlite3.connect(str(db_path(data_dir)))
    conn.execute(
        "UPDATE dispositions SET archived_byte_length = archived_byte_length + 1"
        " WHERE disposition_id = ?", (archived[2]["disposition_id"],))
    conn.commit()
    conn.close()
    model = _dispose(data_dir, now=NOW, archive_target=target,
                     verify_archive=True)
    problems = sorted(d["problem"] for d in model["drift"])
    assert problems == ["absent", "digest_mismatch", "length_mismatch"], problems

    # an orphan is reported (with its destination), never deleted, and is
    # not drift
    orphan = target / "objects" / ("art-" + "0" * 64)
    orphan.write_bytes(b"orphan-object-bytes")
    model = _dispose(data_dir, now=NOW, archive_target=target,
                     verify_archive=True)
    assert model["orphans"] == [
        {"artifact_id": orphan.name, "destination": str(target.resolve())}
    ]
    assert orphan.is_file(), "orphans are reported, never deleted"
    assert len(model["drift"]) == 3, "an orphan is over-preservation, not drift"


def test_ar7_cli_exit_codes_and_mode_refusals(tmp_path: Path) -> None:
    """The CLI surface: clean ⇒ exit 0; drift ⇒ exit 1 with the
    machine-matchable problem names; ``--verify-archive --execute`` is a
    typed refusal (the verify arm never executes); ``--verify-archive``
    without a target is a typed refusal."""
    data_dir, target = _archived_store(tmp_path)
    result = CliRunner().invoke(cli, [
        "dispose", "--data-dir", str(data_dir),
        "--verify-archive", "--archive-target", str(target)])
    assert result.exit_code == 0, _combined(result)

    audit = _audit_rows(data_dir)
    archived = [r for r in audit if r["outcome"] == "archived"]
    flipped = target / "objects" / str(archived[0]["archived_artifact_id"])
    payload = bytearray(flipped.read_bytes())
    payload[0] ^= 0xFF
    flipped.write_bytes(bytes(payload))
    result = CliRunner().invoke(cli, [
        "dispose", "--data-dir", str(data_dir),
        "--verify-archive", "--archive-target", str(target)])
    assert result.exit_code == 1
    combined = _combined(result)
    assert "digest_mismatch" in combined
    assert "Traceback" not in combined

    result = CliRunner().invoke(cli, [
        "dispose", "--data-dir", str(data_dir), "--execute",
        "--verify-archive", "--archive-target", str(target)])
    assert result.exit_code == 1
    combined = _combined(result)
    assert "never executes" in combined
    assert "Traceback" not in combined

    # --verify-archive WITHOUT a target works (finding 3): each row
    # verifies against its own recorded destination.
    result = CliRunner().invoke(cli, [
        "dispose", "--data-dir", str(data_dir), "--verify-archive"])
    assert result.exit_code == 1  # drift is still drift without a flag
    combined = _combined(result)
    assert "digest_mismatch" in combined
    assert "Traceback" not in combined


# --- the review-wave fold (six findings, RED-first) -----------------------------------


def test_fold1_fsync_chain_covers_the_target_and_its_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review wave finding 1 (critic#1 + laneB#1, converged): creating
    the destination tree with ``mkdir(parents=True)`` leaves the NEW
    directory entries unfsynced — only ``objects/``, the manifest file,
    and ``manifests/`` ever reach the platter, so a power loss after
    COMMIT can orphan the objects under an unlinked target. The fix
    fsyncs the whole new-directory chain: ``objects``, ``manifests``,
    the target itself, and its parent (the entry naming the target
    lives there). Pinned by spying on ``os.fsync``/``os.open`` over a
    real first-invocation ``--execute`` against a fresh target."""
    import os as os_module

    opened: dict[int, str] = {}
    fsynced: list[str] = []
    real_open = os_module.open
    real_fsync = os_module.fsync

    def spy_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        fd = real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        opened[fd] = str(Path(str(path)).resolve())
        return fd

    def spy_fsync(fd: int) -> None:
        fsynced.append(opened.get(fd, f"fd:{fd}"))
        real_fsync(fd)

    monkeypatch.setattr(os_module, "open", spy_open)
    monkeypatch.setattr(os_module, "fsync", spy_fsync)

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    target = tmp_path / "offline-fsync"
    model = _dispose(data_dir, now=NOW, execute=True, archive_target=target)
    assert model["counts"]["archived"] == 4, "fixture: the archive tier ran"

    resolved_target = str(target.resolve())
    resolved_parent = str(target.resolve().parent)
    assert resolved_target in fsynced, (
        "the target directory itself must be fsynced — an unfsynced new "
        "directory entry can vanish with its subtree on power loss"
    )
    assert resolved_parent in fsynced, (
        "the parent must be fsynced — the directory entry naming the "
        "target is written into it"
    )
    for sub in ("objects", "manifests"):
        assert str((target / sub).resolve()) in fsynced


def test_fold2_durability_errors_refuse_typed_never_laundered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review wave finding 2 (critic#2): ``_fsync_dir`` swallowed every
    OSError on open AND fsync — an EIO on the durability path committed
    anyway, laundering a failed fsync into a committed trail that
    asserts preservation. An injected EIO at the objects-directory fsync
    must refuse typed in the ``archive_target:`` family with the store
    untouched (Phase A: no transaction was open)."""
    import errno
    import os as os_module

    from benchweave.cli.dispose import ArchiveTargetRefused

    opened: dict[int, str] = {}
    real_open = os_module.open
    real_fsync = os_module.fsync

    def spy_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        fd = real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        opened[fd] = str(Path(str(path)).resolve())
        return fd

    def eio_on_objects_dir(fd: int) -> None:
        if opened.get(fd, "").endswith("/objects"):
            raise OSError(errno.EIO, "injected I/O error")
        real_fsync(fd)

    monkeypatch.setattr(os_module, "open", spy_open)
    monkeypatch.setattr(os_module, "fsync", eio_on_objects_dir)

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    before = _snapshot_all(data_dir)
    with pytest.raises(ArchiveTargetRefused, match="archive_target:"):
        _dispose(data_dir, now=NOW, execute=True,
                 archive_target=tmp_path / "offline-eio")
    assert _snapshot_all(data_dir) == before, (
        "a durability refusal must leave the store untouched"
    )
    assert int(_rows(data_dir, "SELECT COUNT(*) FROM"
                        " disposition_invocations")[0][0]) == 0


def test_fold3_verify_reads_each_rows_recorded_destination(tmp_path: Path) -> None:
    """Review wave finding 3 (critic#3): verify scanned every archived
    row against the one passed flag while ``archive_destination`` was
    write-only — a second target made every earlier row read as drift.
    The fix resolves each row's RECORDED destination (the column exists
    for this); the flag is only a fallback for rows that lack one. Two
    batches to two targets verify clean with no flag; a flipped T1
    object names T1; relocating T2 reads as drift at the recorded
    destination, never at a flag-supplied guess."""
    import shutil

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    t1 = tmp_path / "offline-one"
    t2 = tmp_path / "offline-two"
    first = _dispose(data_dir, now=NOW, execute=True, archive_target=t1)
    assert first["counts"]["archived"] == 4  # batch 1 -> T1

    store, content = _open(data_dir)  # batch 2: two fresh overdue rows
    try:
        for i in range(2):
            payload = json.dumps({"batch-two": i}).encode()
            content.put_evidence(
                "event_log",
                {"id": f"ref-batch-two-{i}", "version": "1",
                 "sha256": hashlib.sha256(payload).hexdigest()},
                content.put_artifact(payload, T0),
                "run:run-a", T0,
            )
    finally:
        store.close()
    second = _dispose(data_dir, now=NOW, execute=True, archive_target=t2)
    assert second["counts"]["archived"] == 2  # batch 2 -> T2

    # No flag, no reliance on one consolidated target: every row verifies
    # against its own recorded destination.
    model = _dispose(data_dir, now=NOW, verify_archive=True)
    assert model["clean"] is True
    assert model["verified"] == 6
    assert model["drift"] == [] and model["skipped"] == []
    assert sorted(model["destinations"]) == sorted(
        {str(t1.resolve()), str(t2.resolve())})

    # A flipped T1 object names T1 — the drift names where it looked.
    t1_objects = {p.name: p for p in (t1 / "objects").iterdir()}
    victim = sorted(t1_objects.values())[0]
    payload_bytes = bytearray(victim.read_bytes())
    payload_bytes[0] ^= 0xFF
    victim.write_bytes(bytes(payload_bytes))
    model = _dispose(data_dir, now=NOW, verify_archive=True)
    assert model["clean"] is False
    assert len(model["drift"]) == 1
    assert model["drift"][0]["destination"] == str(t1.resolve())

    # Relocation: moving T2 away reads as drift at the RECORDED
    # destination (the trail names where the copy was verified), never
    # at a flag-supplied guess. The flipped T1 object from the arm above
    # still reads as digest_mismatch at T1 — three drifted rows total.
    shutil.move(str(t2), str(tmp_path / "offline-moved"))
    model = _dispose(data_dir, now=NOW, verify_archive=True)
    problems = sorted(
        (d["problem"], d["destination"]) for d in model["drift"])
    assert problems == [
        ("absent", str(t2.resolve())),
        ("absent", str(t2.resolve())),
        ("digest_mismatch", str(t1.resolve())),
    ], "relocation reads as absent at the recorded destination"
    # the two absent rows ARE the moved tree's rows
    t2_rows = {
        str(r["disposition_id"]) for r in _audit_rows(data_dir)
        if r["outcome"] == "archived"
        and r["archive_destination"] == str(t2.resolve())
    }
    assert {d["disposition_id"] for d in model["drift"]
            if d["problem"] == "absent"} == t2_rows


def test_fold4_stager_streams_one_payload_at_a_time(tmp_path: Path) -> None:
    """Review wave finding 4 (laneB#2, measured: 4x34MB -> 168MB peak):
    ``_stage_archive_objects`` materialized Σ payloads before placing
    anything. The stager now places artifacts one at a time — read,
    write, fsync, replace, re-read, re-hash, release — bounded at ≤ 1
    payload (hashing streams in 1MiB blocks). Pinned by a tracemalloc
    ceiling over a two-8MB-artifact archive: the peak must stay well
    under the 16MB two-payload sum."""
    import shutil
    import tracemalloc

    data_dir = tmp_path / "data-stream"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    setup(data_dir)
    data_dir.joinpath("retention-policy.json").write_text(
        json.dumps({
            "config_version": "1",
            "default": {"duration_s": 3600, "retain_after": "landing",
                        "on_disposition": "review"},
            "classes": [
                {"selector": "evidence:event_log", "duration_s": 3600,
                 "retain_after": "landing", "on_disposition": "archive"},
            ],
            "benches": {},
        }),
        encoding="utf-8",
    )
    big_one = bytes(bytearray(range(256))) * 32_768  # 8 MiB, distinct
    big_two = bytes(reversed(bytearray(range(256)))) * 32_768  # 8 MiB
    store, content = _open(data_dir)
    try:
        for i, payload in enumerate((big_one, big_two)):
            content.put_evidence(
                "event_log",
                {"id": f"ref-big-{i}", "version": "1",
                 "sha256": hashlib.sha256(payload).hexdigest()},
                content.put_artifact(payload, T0),
                "run:stream-run", T0,
            )
    finally:
        store.close()
    del big_one, big_two

    target = tmp_path / "offline-stream"
    # Warm the one-time costs OUTSIDE the measured window (the policy
    # loader compiles its vendored JSON schema — a fixed ~3.5MB that does
    # not scale with payloads): a dry run first, proven non-writing by
    # AR6, so the ceiling below measures the stager's per-payload bound.
    _dispose(data_dir, now=NOW, archive_target=target)
    tracemalloc.start()
    model = _dispose(data_dir, now=NOW, execute=True, archive_target=target)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert model["counts"]["archived"] == 2
    assert model["archive_objects_placed"] == 2
    assert peak < 12 * 1024 * 1024, (
        f"streaming stager peak {peak / (1024 * 1024):.1f} MiB must stay "
        "well under the 16 MiB two-payload sum (bound: one payload at a "
        "time plus block overhead — the peak must not scale with the "
        "payload count)"
    )


def test_fold5_archive_rows_without_artifacts_refuse_typed(tmp_path: Path) -> None:
    """Review wave finding 5 (laneA F1): an evidence row with
    ``artifact_id=None`` would archive to nothing — the governed row
    destroyed, no offline copy, and verify silently passing it. Dispose
    now refuses typed BEFORE anything is staged (never
    archive-to-nothing); the verify arm COUNTS binding-less rows as
    skipped (clean=False, exit 1), naming them — never a silent pass."""
    import shutil

    from benchweave.cli.dispose import ArchiveTargetRefused

    data_dir = tmp_path / "data-void"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    setup(data_dir)
    data_dir.joinpath("retention-policy.json").write_text(
        json.dumps({
            "config_version": "1",
            "default": {"duration_s": 3600, "retain_after": "landing",
                        "on_disposition": "review"},
            "classes": [
                {"selector": "evidence:event_log", "duration_s": 3600,
                 "retain_after": "landing", "on_disposition": "archive"},
            ],
            "benches": {},
        }),
        encoding="utf-8",
    )
    store, content = _open(data_dir)
    try:
        content.put_evidence(
            "event_log",
            {"id": "ref-void", "version": "1", "sha256": "0" * 64},
            None, "run:void-run", T0,  # the artifact-less row
        )
    finally:
        store.close()

    target = tmp_path / "offline-void"
    with pytest.raises(ArchiveTargetRefused, match="archive_target:"):
        _dispose(data_dir, now=NOW, execute=True, archive_target=target)
    assert int(_rows(data_dir, "SELECT COUNT(*) FROM evidence"
                              " WHERE kind = 'event_log'")[0][0]) == 1, (
        "an artifact-less archive row must SURVIVE — never destroyed "
        "with no offline copy"
    )
    assert _tree_snapshot(target) == {}, (
        "the refusal fires before any object is placed — the created "
        "target tree carries no objects and no manifest"
    )

    # The verify half: a rogue archived row with no binding (inserted
    # directly — dispose can no longer create one) is COUNTED as
    # skipped, named, and fails clean.
    conn = sqlite3.connect(str(db_path(data_dir)))
    conn.execute(
        "INSERT INTO dispositions (disposition_id, invocation_id,"
        " row_kind, target_id, data_class, matched_scope, matched_rule,"
        " on_disposition, anchor_kind, disposal_date, bytes,"
        " deleted_byte_length, decision_artifact_id, decision_sha256,"
        " executed_at, outcome)"
        " VALUES (?, 'dsp-inv-rogue', 'evidence',"
        " 'ref-void', 'evidence:event_log', 'class', 'r1', 'archive',"
        " 'landing', '2026-09-20T00:00:00Z', 0, 0, 'art-rogue',"
        " ?, '2026-09-27T00:00:00Z', 'archived')",
        ("dsp-rogue-void", "0" * 64),
    )
    conn.commit()
    conn.close()
    model = _dispose(data_dir, now=NOW, verify_archive=True)
    assert model["clean"] is False
    assert any(
        item["disposition_id"] == "dsp-rogue-void"
        and item["reason"] == "no artifact binding"
        for item in model["skipped"]
    ), "verify must name the binding-less row, never silently pass it"


def test_fold6_archive_binding_reconciled_inside_the_transaction(
    tmp_path: Path,
) -> None:
    """Review wave finding 6 (laneA F2): the archive binding was read
    pre-transaction while the delete tier binds from the single
    in-transaction read — a rogue non-flock writer repointing a row's
    artifact between Phase A and Phase B would commit a trail row over
    never-verified bytes while the GC destroys the real content. The
    transaction now re-reads the binding and refuses typed on any
    mismatch (the delete tier's guard, mirrored). The lane's repro:
    repoint A→B at the stage_hook(0) interleaving — typed refusal, both
    artifacts intact, whole invocation rolled back."""
    from benchweave.state.dispositions import StoreChangedUnderPlan

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    first = _rows(
        data_dir,
        "SELECT evidence_id, artifact_id FROM evidence"
        " WHERE kind = 'event_log' ORDER BY rowid LIMIT 1",
    )
    evidence_id, artifact_a = str(first[0][0]), str(first[0][1])
    rogue_payload = b"rogue-repointed-payload"
    artifact_b = "art-" + hashlib.sha256(rogue_payload).hexdigest()

    def rogue_repoint(index: int) -> None:
        if index != 0:
            return
        # A rogue non-flock writer (a second connection; Phase A holds
        # no transaction): plant a validly-addressed artifact B and
        # repoint the row whose object just staged.
        rogue = sqlite3.connect(str(db_path(data_dir)))
        rogue.execute(
            "INSERT OR REPLACE INTO artifacts (artifact_id, data, stored_at)"
            " VALUES (?, ?, ?)", (artifact_b, rogue_payload, T0))
        rogue.execute(
            "UPDATE evidence SET artifact_id = ? WHERE evidence_id = ?",
            (artifact_b, evidence_id))
        rogue.commit()
        rogue.close()

    target = tmp_path / "offline-repoint"
    with pytest.raises(StoreChangedUnderPlan, match="store changed under the plan"):
        _dispose(data_dir, now=NOW, execute=True, archive_target=target,
                 stage_hook=rogue_repoint)

    audit, invocations = _rows(
        data_dir, "SELECT (SELECT COUNT(*) FROM dispositions),"
                  " (SELECT COUNT(*) FROM disposition_invocations)")[0]
    assert (int(audit), int(invocations)) == (0, 0), (
        "the binding mismatch must roll the whole invocation back"
    )
    # BOTH artifacts intact: A (staged and verified offline, still the
    # trail's would-be binding) survives in-store; B (never verified)
    # is never destroyed by a GC over a laundered trail.
    assert _rows(data_dir, "SELECT artifact_id FROM artifacts"
                           " WHERE artifact_id = ?", (artifact_a,)), (
        "the staged-and-verified artifact must survive the refusal"
    )
    assert _rows(data_dir, "SELECT artifact_id FROM artifacts"
                           " WHERE artifact_id = ?", (artifact_b,)), (
        "the never-verified repointed artifact must not be GC'd over a "
        "laundered trail"
    )
    # the governed row survived the rollback (still repointed — the
    # rogue write was outside the transaction and stands)
    row = _rows(data_dir, "SELECT artifact_id FROM evidence"
                          " WHERE evidence_id = ?", (evidence_id,))
    assert str(row[0][0]) == artifact_b


def test_r1_empty_and_dot_archive_targets_refuse_typed(tmp_path: Path) -> None:
    """Review wave R1 (guard): an empty or ``.`` ``--archive-target``
    resolves to the current working directory — a silent CWD archive.
    Both refuse typed in the ``archive_target:`` family, and nothing is
    created anywhere (the lane's repro: ``--archive-target ""``
    currently exits 0 and writes objects/ into the CWD)."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    for bad in ("", "."):
        result = CliRunner().invoke(cli, [
            "dispose", "--data-dir", str(data_dir), "--execute",
            "--archive-target", bad])
        combined = _combined(result)
        assert result.exit_code == 1, (
            f"--archive-target {bad!r} must refuse, got exit "
            f"{result.exit_code}: {combined}"
        )
        assert "archive_target:" in combined
        assert "current working directory" in combined
        assert "Traceback" not in combined
    # nothing was disposed and no tree appeared anywhere
    assert int(_rows(data_dir, "SELECT COUNT(*) FROM evidence"
                              " WHERE kind = 'event_log'")[0][0]) == 4
    assert not [p for p in tmp_path.rglob("objects") if p.is_dir()], (
        "no objects/ tree may appear from a refused target"
    )


# --- fold fix 5: output units + skip split + disclosure carry ------------------------------


def test_fold5_units_split_and_carried_disclosures(tmp_path: Path) -> None:
    """Output honesty: ``bytes_reclaimed`` (the row-bytes sum) decomposes
    into ``charged_ledger_bytes`` (the G3 ledger relief — capture rows
    only) and ``artifact_bytes_freed`` (bytes physically removed by GC);
    evidence rows sharing artifacts make the row-bytes sum double-count
    and diverge from disk. The single skipped count splits by the report's
    status vocabulary, and the REPORT's own disclosures (here: the
    non-finalised staging count) ride through instead of being dropped."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")

    dry = _dispose(data_dir, now=NOW)
    assert dry["charged_ledger_bytes"] == 228  # cap-wave + the dup pair
    assert dry["artifact_bytes_freed"] is None  # known at execution only
    assert dry["counts"]["not_yet_overdue"] == 1  # futurekind
    assert dry["counts"]["anchor_unresolved"] == 1  # unreskind
    assert dry["counts"]["held"] == 0 and dry["counts"]["ungoverned"] == 0
    assert any("non-finalised" in d for d in dry["disclosures"]), (
        "the report's disclosures must ride through the dispose model"
    )

    model = _dispose(data_dir, now=NOW, execute=True)
    assert model["charged_ledger_bytes"] == 228
    assert model["artifact_bytes_freed"] == 64, (
        "only the byte-identical pair's artifact is collected (64 B); "
        "cap-wave's survives (keepkind retains it)"
    )
    assert model["bytes_reclaimed"] == 228  # the row-bytes sum, still named
    stored = json.loads(str(_rows(
        data_dir, "SELECT counts_json FROM disposition_invocations")[0][0]))
    assert stored["charged_ledger_bytes"] == 228
    assert stored["artifact_bytes_freed"] == 64
    assert stored["not_yet_overdue"] == 1 and stored["anchor_unresolved"] == 1


# --- A6: refusals ------------------------------------------------------------------------


def test_a6_store_missing_v6_refuses_typed_naming_the_upgrade_path(
    tmp_path: Path,
) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    conn = sqlite3.connect(str(db_path(data_dir)))
    conn.execute("DELETE FROM schema_migrations WHERE version = 6")
    conn.execute("DROP TABLE IF EXISTS dispositions")
    conn.execute("DROP TABLE IF EXISTS disposition_invocations")
    conn.commit()
    conn.close()
    result = CliRunner().invoke(
        cli, ["dispose", "--data-dir", str(data_dir), "--execute"])
    assert result.exit_code == 1
    combined = _combined(result)
    assert "retention_store:" in combined
    assert "missing versions: 6" in combined
    assert "never migrates" in combined
    assert "upgrade" in combined, "the refusal must name the upgrade path"
    assert "Traceback" not in combined


def test_a6_held_store_refuses_naming_the_holder(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    db = db_path(data_dir)
    with StoreHold(db, label="gateway-like holder"):
        result = CliRunner().invoke(
            cli, ["dispose", "--data-dir", str(data_dir), "--execute"])
    assert result.exit_code == 1
    combined = _combined(result)
    assert "gateway-like holder" in combined
    assert "Traceback" not in combined


def test_a6_no_policy_file_is_a_typed_refusal_never_a_silent_no_op(
    tmp_path: Path,
) -> None:
    data_dir = _seed(tmp_path)  # deliberately no policy file
    result = CliRunner().invoke(cli, ["dispose", "--data-dir", str(data_dir)])
    assert result.exit_code == 1
    combined = _combined(result)
    assert "dispose:" in combined
    assert "ungoverned" in combined
    assert "Traceback" not in combined
    # nothing ran: the store is untouched (the deletion path never fired)
    assert _rows(data_dir, "SELECT COUNT(*) FROM dispositions")[0][0] == 0


def test_a6_explicit_invalid_policy_refuses_in_the_policy_family(
    tmp_path: Path,
) -> None:
    data_dir = _seed(tmp_path)
    bad = tmp_path / "bad-policy.json"
    bad.write_text("{not json", encoding="utf-8")
    result = CliRunner().invoke(
        cli, ["dispose", "--data-dir", str(data_dir), "--policy", str(bad)])
    assert result.exit_code == 1
    combined = _combined(result)
    assert "retention_policy:" in combined
    assert "Traceback" not in combined


# --- A7: dry-run purity -------------------------------------------------------------------


def test_a7_default_dry_run_writes_nothing(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    before = _snapshot_all(data_dir)
    result = CliRunner().invoke(cli, ["dispose", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, _combined(result)
    after = _snapshot_all(data_dir)
    assert after == before, "the dry run must leave every table byte-identical"
    model = _dispose(data_dir, now=NOW)  # the library path is pure too
    assert model["counts"] == _EXPECTED_COUNTS


# --- A8: evidence-exactness + tamper arm -----------------------------------------------------


def test_a8_audit_digests_recompute_and_detect_tampering(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    _dispose(data_dir, now=NOW, execute=True)
    for row in _audit_rows(data_dir):
        recomputed = _recomputed_digest(row)
        assert recomputed == row["decision_sha256"], (
            f"{row['disposition_id']}: stored digest does not recompute"
        )
        assert row["decision_artifact_id"] == f"art-{recomputed}"
        blob = _rows(data_dir, "SELECT data FROM artifacts"
                               " WHERE artifact_id = ?",
                     (row["decision_artifact_id"],))[0][0]
        assert hashlib.sha256(bytes(blob)).hexdigest() == recomputed, (
            "the artifact bytes must hash to the pinned digest"
        )

    # tamper arm 1: flip an identity field in the audit ROW -> detected
    conn = sqlite3.connect(str(db_path(data_dir)))
    conn.execute("UPDATE dispositions SET target_id = 'cap-tampered'"
                 " WHERE rowid = (SELECT MIN(rowid) FROM dispositions)")
    conn.commit()
    conn.close()
    tampered = [r for r in _audit_rows(data_dir) if r["target_id"] == "cap-tampered"]
    assert tampered and _recomputed_digest(tampered[0]) != tampered[0]["decision_sha256"], (
        "a flipped identity field must break the digest comparison"
    )

    # tamper arm 2: flip the artifact BYTES -> detected
    conn = sqlite3.connect(str(db_path(data_dir)))
    artifact = conn.execute(
        "SELECT decision_artifact_id FROM dispositions"
        " WHERE target_id != 'cap-tampered'").fetchone()[0]
    conn.execute("UPDATE artifacts SET data = ? WHERE artifact_id = ?",
                 (b"tampered-bytes", artifact))
    conn.commit()
    conn.close()
    stored = _rows(data_dir, "SELECT data FROM artifacts WHERE artifact_id = ?",
                   (artifact,))[0][0]
    assert hashlib.sha256(bytes(stored)).hexdigest() != artifact.removeprefix("art-"), (
        "flipped artifact bytes must break the embedded-digest comparison"
    )


# --- A9: plan parity (import-not-re-implement) ------------------------------------------------


def test_a9_the_dry_run_plan_equals_the_report_builder(tmp_path: Path) -> None:
    from benchweave.cli.retention import build_retention_report
    from benchweave.control.retention_policy import load_retention_policy

    data_dir = _seed(tmp_path)
    policy_path = _write_policy(data_dir / "retention-policy.json")
    policy = load_retention_policy(policy_path)

    store = Store.open(db_path(data_dir))
    try:
        report = build_retention_report(store, policy=policy, now=NOW)
    finally:
        store.close()
    expected = [
        (r["id"], r["matched_selector"], r["matched_scope"], r["matched_rule"],
         r["data_class"], r["bytes"])
        for r in report["rows"]
        if r["status"] == "scheduled" and r["overdue"]
        and r["on_disposition"] == "delete"
    ]

    model = _dispose(data_dir, now=NOW)  # dry run
    planned = [
        (r["id"], r["matched_selector"], r["matched_scope"], r["matched_rule"],
         r["data_class"], r["bytes"])
        for r in model["rows"] if r["outcome"] == "deleted"
    ]
    assert planned == expected, (
        "the executor's plan must be the report builder's rows verbatim — "
        "any second derivation shows here as drift"
    )
    assert len(planned) == 3


# --- command surface -----------------------------------------------------------------------


def test_cli_execute_output_carries_counts_and_disclosures(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    result = CliRunner().invoke(
        cli, ["dispose", "--data-dir", str(data_dir), "--execute"])
    assert result.exit_code == 0, _combined(result)
    combined = _combined(result)
    assert "deleted: 3" in combined
    assert "irreversible" in combined
    assert "audit" in combined


def test_cli_dry_run_says_so(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    result = CliRunner().invoke(cli, ["dispose", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, _combined(result)
    assert "dry run" in _combined(result).lower()


def test_cli_json_round_trips_the_model(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    result = CliRunner().invoke(
        cli, ["dispose", "--data-dir", str(data_dir), "--json"])
    assert result.exit_code == 0, _combined(result)
    model = json.loads(result.output)
    assert model["counts"] == _EXPECTED_COUNTS
    assert model["bytes_reclaimed"] == _EXPECTED_BYTES
    assert model["executed"] is False


def test_wedge_disclosure_names_the_audited_dispose_path(tmp_path: Path) -> None:
    """Issue #194 done-means item 4: the retention report's wedge
    disclosure now names ``benchweave dispose`` (with its --execute
    opt-in) as the remediation, scoped to what ships — delete-tier rows
    reclaim, review/archive stay blocked, or raise the ceiling. Pinned
    through the public surface (the report model's disclosure string)."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    result = CliRunner().invoke(
        cli, ["retention", "--data-dir", str(data_dir), "--json"])
    assert result.exit_code == 0, _combined(result)
    disclosure = json.loads(result.output)["quota_wedge"]["disclosure"]
    assert "benchweave dispose" in disclosure
    assert "--execute" in disclosure
    assert "archive" in disclosure  # the blocked tier is named, not implied


# --- the scale smoke (bounded; wall time disclosed, not gated) ---------------------------------


def test_scale_smoke_5000_rows_audit_equals_deleted(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)  # gives a migrated store + policy location
    _write_policy(data_dir / "retention-policy.json")
    rows: list[tuple[Any, ...]] = []
    artifacts: list[tuple[Any, ...]] = []
    total = 0
    for i in range(5000):
        key = f"smoke-key-{chr(ord('a') + i % 3)}"  # three context keys
        payload = f"smoke-{i}".encode()
        artifact_id = "art-" + hashlib.sha256(payload).hexdigest()
        artifacts.append((artifact_id, payload, T0))
        rows.append((f"smoke-cap-{i}", key, "finalised", 0, len(payload),
                     "waveform_f64le", None, artifact_id, T0, T0, T0))
        total += len(payload)
    store = Store.open(db_path(data_dir))
    try:
        store.connection.executemany(
            "INSERT INTO artifacts (artifact_id, data, stored_at)"
            " VALUES (?, ?, ?)", artifacts)
        store.connection.executemany(
            "INSERT INTO capture_staging (capture_id, context_key, state,"
            " reserved_bytes, charged_bytes, format, sample_count,"
            " artifact_id, started_at, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    finally:
        store.close()

    started = time.monotonic()
    model = _dispose(data_dir, now=NOW, execute=True)
    elapsed = time.monotonic() - started

    # The fixture's own three delete-tier rows (cap-wave, cap-dup-a/b) ride
    # the same invocation: the smoke's exact figures include them.
    assert model["counts"]["deleted"] == 5000 + 3
    assert model["bytes_reclaimed"] == total + _EXPECTED_BYTES
    assert model["artifacts_collected"] == 5000 + 1, (
        "every synthetic artifact (5000, each referenced by exactly one "
        "deleted row) plus the fixture's byte-identical-pair artifact — "
        "collected exactly once each; cap-wave's survives (keepkind)"
    )
    audit = _rows(data_dir, "SELECT COUNT(*), COALESCE(SUM(bytes), 0)"
                            " FROM dispositions")
    assert int(audit[0][0]) == 5000 + 3
    assert int(audit[0][1]) == total + _EXPECTED_BYTES
    assert _rows(data_dir, "SELECT COUNT(*) FROM disposition_invocations"
                           " WHERE invocation_id = ?",
                 (model["invocation_id"],))[0][0] == 1
    remaining = _rows(data_dir, "SELECT COUNT(*) FROM capture_staging"
                                " WHERE capture_id LIKE 'smoke-cap-%'")[0][0]
    assert int(remaining) == 0
    # wall time is disclosed, never gated (CI hardware variance)
    print(f"\ndispose --execute over 5000 rows: {elapsed:.2f}s")


def test_gc_live_reference_lookups_are_served_by_indexes(tmp_path: Path) -> None:
    """Fold fix 4 (lane A F2, measured 4.24x per doubling on the
    no-index code): the GC's live-reference predicate probes
    ``evidence.artifact_id``, ``capture_staging.artifact_id`` and
    ``dispositions.decision_artifact_id`` once per dropped artifact under
    flock + BEGIN IMMEDIATE — unindexed, each probe scans its whole table
    (quadratic in governed rows). The indexes ship INSIDE migration v6
    (v6 is unmerged; amending it, never a v7), and this pin — the D13
    EXPLAIN QUERY PLAN precedent — fails if any lookup regresses to a
    SCAN."""
    from benchweave.state.dispositions import _LIVE_REFERENCE_SQL

    data_dir = _seed(tmp_path)
    uri = f"{db_path(data_dir).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        plans = conn.execute(
            "EXPLAIN QUERY PLAN " + _LIVE_REFERENCE_SQL, ("a", "a", "a")
        ).fetchall()
        detail = " | ".join(str(row[3]) for row in plans)
        # SQLite spells a probe over an index-only column "COVERING INDEX";
        # either index spelling serves the lookup, a SCAN does not.
        for index in ("idx_evidence_artifact", "idx_capture_staging_artifact",
                      "idx_dispositions_decision"):
            assert f"USING INDEX {index}" in detail or (
                f"USING COVERING INDEX {index}" in detail
            ), detail
        assert "SCAN evidence" not in detail, detail
        assert "SCAN capture_staging" not in detail, detail
        assert "SCAN dispositions" not in detail, detail
    finally:
        conn.close()


# --- the archive scale smoke (bounded; wall time disclosed, not gated) ---------------


def test_scale_smoke_5000_archive_rows_objects_and_full_noop_rerun(
    tmp_path: Path,
) -> None:
    """The #199 scale smoke: 5,000 overdue archive rows across three
    context keys (distinct artifacts, 8-byte payloads) — ``--execute``
    with a target completes with archived audit rows == 5,000 exactly,
    destination objects == distinct artifacts exactly, one manifest —
    and an immediate RE-RUN is a full no-op (0 selected rows, 0 objects
    placed): the idempotency claim measured, not asserted. Wall time is
    disclosed, never gated (fsync-bound; CI hardware variance)."""
    import shutil

    data_dir = tmp_path / "data-scale-arch"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    setup(data_dir)
    data_dir.joinpath("retention-policy.json").write_text(
        json.dumps({
            "config_version": "1",
            "default": {"duration_s": 3600, "retain_after": "landing",
                        "on_disposition": "review"},
            "classes": [
                {"selector": "capture:waveform_f64le", "duration_s": 3600,
                 "retain_after": "landing", "on_disposition": "archive"},
            ],
            "benches": {},
        }),
        encoding="utf-8",
    )
    rows: list[tuple[Any, ...]] = []
    artifacts: list[tuple[Any, ...]] = []
    for i in range(5000):
        key = f"scale-arch-key-{chr(ord('a') + i % 3)}"  # three context keys
        payload = f"a{i:07d}".encode()  # 8 bytes, distinct
        artifact_id = "art-" + hashlib.sha256(payload).hexdigest()
        artifacts.append((artifact_id, payload, T0))
        rows.append((f"scale-cap-{i}", key, "finalised", 0, len(payload),
                     "waveform_f64le", None, artifact_id, T0, T0, T0))
    store = Store.open(db_path(data_dir))
    try:
        store.connection.executemany(
            "INSERT INTO artifacts (artifact_id, data, stored_at)"
            " VALUES (?, ?, ?)", artifacts)
        store.connection.executemany(
            "INSERT INTO capture_staging (capture_id, context_key, state,"
            " reserved_bytes, charged_bytes, format, sample_count,"
            " artifact_id, started_at, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    finally:
        store.close()

    target = tmp_path / "offline-scale"
    started = time.monotonic()
    model = _dispose(data_dir, now=NOW, execute=True, archive_target=target)
    elapsed = time.monotonic() - started

    assert model["counts"]["archived"] == 5000
    assert model["counts"]["deleted"] == 0
    audit = _rows(data_dir, "SELECT COUNT(*) FROM dispositions"
                            " WHERE outcome = 'archived'")
    assert int(audit[0][0]) == 5000
    objects = list((target / "objects").iterdir())
    assert len(objects) == 5000, (
        "destination objects == distinct artifacts exactly "
        "(denominator: the 5,000 synthetic payloads, all distinct)"
    )
    assert len(list((target / "manifests").iterdir())) == 1
    assert model["archive_objects_placed"] == 5000
    assert model["archive_bytes_copied"] == 8 * 5000

    # the immediate re-run is a full no-op: the governed rows vanished
    # from the plan, and the destination objects verify-and-skip.
    rerun = _dispose(data_dir, now=NOW, execute=True, archive_target=target)
    assert rerun["counts"]["archived"] == 0
    assert rerun["counts"]["deleted"] == 0
    assert rerun["archive_objects_placed"] == 0
    assert rerun["archive_objects_deduped"] == 0
    assert len(list((target / "manifests").iterdir())) == 1, (
        "a zero-object re-run writes no manifest — manifests ride Phase A "
        "and describe staged objects; the store's invocation row is the "
        "no-op's record"
    )
    # wall time is disclosed, never gated (CI hardware variance)
    print(f"\ndispose --execute --archive-target over 5000 rows: {elapsed:.2f}s")
