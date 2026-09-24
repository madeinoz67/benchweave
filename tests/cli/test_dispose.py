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
#: event_log rows; skips futurekind (not overdue) + unreskind (unresolved).
_EXPECTED_COUNTS = {"deleted": 3, "blocked_review": 4, "blocked_archive": 4,
                    "skipped": 2}
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
    production code involved."""
    envelope = {k: v for k, v in row.items()
                if k not in ("decision_artifact_id", "decision_sha256")}
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
