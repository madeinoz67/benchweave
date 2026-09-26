"""Issue #43 slice 3 (Decision 8): the retention report — pure projection.

The S3 controls. Every control is exact fixture arithmetic, and each must fail
when the mechanism is reverted (absence arm). The standing rule under test:
**slice 3 writes nothing back** — S3-1 pins it over every table in the store
(seventeen since the issue #194 disposition-audit tables landed).

Fixture vocabulary is invented; no bench, client or DUT identifiers from any
real corpus are named.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
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


def _write_policy(path: Path, **kw: Any) -> Path:
    # kw["retain_after_all"] overrides every rule's anchor (fix-wave tests
    # exercise run_end on class-governed rows too, not only default-governed).
    def _anchor(default: str) -> str:
        return str(kw.get("retain_after_all", default))

    doc: dict[str, Any] = {
        "config_version": "1",
        "default": {
            "duration_s": kw.get("default_s", 3600),
            "retain_after": _anchor("run_end" if kw.get("run_end") else "landing"),
            "on_disposition": "review",
        },
        "classes": [
            {
                "selector": "capture:waveform_f64le",
                "duration_s": kw.get("waveform_s", 3600),
                "retain_after": _anchor("landing"),
                "on_disposition": "delete",
            },
            {
                "selector": "capture:raw_binary",
                "duration_s": 7200,
                "retain_after": _anchor("landing"),
                "on_disposition": "review",
            },
            {
                "selector": "evidence:event_log",
                "duration_s": kw.get("event_log_s", 86400),
                "retain_after": _anchor("landing"),
                "on_disposition": "archive",
                **({"hold": True} if kw.get("hold_event_log") else {}),
            },
        ],
        "benches": {
            BENCH_TWO: {
                "default": {
                    "duration_s": kw.get("bench_two_default", 60),
                    "retain_after": "landing",
                    "on_disposition": "review",
                },
                "classes": [],
            }
        },
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _open(data_dir: Path) -> tuple[Store, ContentStore]:
    store = Store.open(db_path(data_dir))
    return store, ContentStore(store)


def _seed(tmp_path: Path) -> Path:
    """A data dir with two benches, terminal runs on both benches plus one live
    run, finalised captures at three context keys (including a byte-identical
    pair), one never-finalised capture, event_log evidence with a nonzero span,
    and evidence under an unattributed context key."""
    import shutil

    data_dir = tmp_path / "data"
    if data_dir.exists():  # pytest can reuse a numbered dir across runs
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
                # A real terminal record carries ended_at (build_terminal_record);
                # the retention report anchors run_end on exactly that field.
                store.finalize_run(
                    run, {"run_id": run, "outcome": "passed", "ended_at": T2}
                )

        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        for cid, ctx, fmt, payload, finalise_at in (
            ("cap-wave", "run:run-a", "waveform_f64le", _CAP_ONE, T0),
            ("cap-raw", "run:run-b", "raw_binary", _CAP_TWO, T1),
            ("cap-dup-a", "run:run-a", "waveform_f64le", _CAP_DUP, T0),
            ("cap-dup-b", "run:run-a", "waveform_f64le", _CAP_DUP, T0),  # byte-identical
        ):
            writer.open_capture(
                capture_id=cid, context_key=ctx, fmt=fmt,
                sample_count=None, max_bytes=1_000_000, now=T0)
            writer.append(cid, payload, ctx)
            writer.finalise(cid, finalise_at, ctx)
        # one never-finalised capture (staged row + chunk) for the sweep disclosure
        writer.open_capture(
            capture_id="cap-open", context_key="run:run-c", fmt="raw_binary",
            sample_count=None, max_bytes=512, now=T0)
        writer.append("cap-open", b"\x00" * 16, "run:run-c")

        for i, (kind, ctx, sub) in enumerate((
            ("event_log", "run:run-a", "sub-alpha"),
            ("event_log", "run:run-a", "sub-alpha"),
            ("event_log", "run:run-a", "sub-alpha"),  # three events over T0..T1
            ("event_log", "run:run-b", "sub-beta"),   # single event → zero-span
            ("dataset", "manual-labbook", None),
            ("spectrummap", "manual-labbook", None),   # novel evidence kind
        )):
            payload = json.dumps({"i": i}).encode()
            art = content.put_artifact(payload, T0)
            ref: dict[str, Any] = {"id": f"ref-{i}", "version": "1",
                                   "sha256": hashlib.sha256(payload).hexdigest()}
            if sub:
                ref |= {"subscription_id": sub, "host_received_at": T1 if i % 2 else T0}
            content.put_evidence(kind, ref, art, ctx, T0)
    finally:
        store.close()
    return data_dir


def _model(data_dir: Path, **kw: Any) -> dict[str, Any]:
    from benchweave.cli.retention import retention_from_data_dir

    return retention_from_data_dir(data_dir, **kw)


_TABLES = {
    "schema_migrations", "requests", "runs", "leases", "events", "benches",
    "devices", "generations", "run_states", "changes", "documents", "artifacts",
    "evidence", "capture_staging", "capture_chunks",
    "disposition_invocations", "dispositions",
}


def _snapshot(
    data_dir: Path, tables: frozenset[str] | set[str] | None = None
) -> dict[str, tuple[int, str]]:
    uri = f"{db_path(data_dir).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        expected = _TABLES if tables is None else tables
        assert names == expected, f"table set drifted: {sorted(names ^ expected)}"
        snap: dict[str, tuple[int, str]] = {}
        for t in sorted(names):
            # t iterates the asserted frozenset of table names, not user input
            rows = conn.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall()  # noqa: S608
            digest = hashlib.sha256(repr(rows).encode()).hexdigest()
            snap[t] = (len(rows), digest)
        return snap
    finally:
        conn.close()


def _full_path(data_dir: Path, now: str = NOW) -> None:
    from benchweave.cli.retention import render_json, render_markdown

    model = _model(data_dir, now=now, max_dataset_bytes=10_000)
    render_markdown(model)
    render_json(model)
    result = CliRunner().invoke(
        cli, ["retention", "--data-dir", str(data_dir), "--max-dataset-bytes", "10000"])
    assert result.exit_code == 0, _combined(result)


# --- S3-1: the no-write-back pin -------------------------------------------------


def test_s3_1_the_complete_report_path_writes_nothing_back(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    before = _snapshot(data_dir)
    _full_path(data_dir)
    after = _snapshot(data_dir)
    assert after == before


def test_s3_1_sensitivity_the_snapshot_detects_a_write(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    before = _snapshot(data_dir)
    store, content = _open(data_dir)
    try:
        content.put_artifact(b"extra-payload", NOW)
    finally:
        store.close()
    assert _snapshot(data_dir) != before


# --- fix wave (issue #184, fork A): the never-migrate read posture --------------

_V4_TABLES = _TABLES - {"capture_staging", "capture_chunks"}


def test_fw4_retention_never_migrates_a_down_level_store(tmp_path: Path) -> None:
    """Finding 4 (MED, fork A): a retention run NEVER migrates the store.
    The v4-store fixture (drop the v5 migration row + capture tables, the
    maintainer's P1 template): the complete report path refuses with a
    typed, operator-readable refusal naming the mismatch, and the S3-1
    snapshot — extended over the down-level table set — proves
    schema_migrations (and everything else) is unchanged."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    conn = sqlite3.connect(str(db_path(data_dir)))
    conn.execute("DELETE FROM schema_migrations WHERE version = 5")
    conn.execute("DROP TABLE IF EXISTS capture_staging")
    conn.execute("DROP TABLE IF EXISTS capture_chunks")
    conn.commit()
    conn.close()
    before = _snapshot(data_dir, _V4_TABLES)
    result = CliRunner().invoke(
        cli, ["retention", "--data-dir", str(data_dir), "--max-dataset-bytes", "10000"]
    )
    assert result.exit_code == 1
    combined = _combined(result)
    assert "retention_store:" in combined
    assert "never migrates" in combined or "behind" in combined
    assert "Traceback" not in combined
    after = _snapshot(data_dir, _V4_TABLES)
    assert after == before, "the refusal path wrote back (or migrated) the store"
    assert after["schema_migrations"] == before["schema_migrations"]


def test_fw4a_interior_migration_hole_refuses_typed_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """R2 fold item 1 (BLOCKING, fork A): the precheck compared only
    MAX(schema_migrations.version) against the newest known migration, but
    ``Store._apply_migrations`` re-applies ANY migration whose version row
    is absent. Deleting the MIDDLE v4 row (v5/MAX intact) passed the
    precheck, the idempotent v4 DDL (``CREATE INDEX IF NOT EXISTS``)
    re-applied silently, and the re-inserted ``schema_migrations`` row was
    a store write inside the "never migrates" command. The comparison is
    set-based now: any missing version refuses naming it; the snapshot
    pins the table (the DDL is idempotent, so only the row-set pin catches
    the write)."""
    data_dir = _seed(tmp_path)
    conn = sqlite3.connect(str(db_path(data_dir)))
    conn.execute("DELETE FROM schema_migrations WHERE version = 4")  # keep v5/MAX
    conn.commit()
    conn.close()
    before = _snapshot(data_dir)
    # v7 made seven migration rows; deleting the middle v4 leaves six.
    assert before["schema_migrations"][0] == 6, "fixture: the v4 row is gone"
    result = CliRunner().invoke(
        cli, ["retention", "--data-dir", str(data_dir), "--max-dataset-bytes", "10000"]
    )
    combined = _combined(result)
    assert result.exit_code == 1, (
        f"the holey store must refuse, got exit {result.exit_code}:\n{combined}"
    )
    assert "retention_store:" in combined
    assert "missing versions: 4" in combined, combined
    assert "Traceback" not in combined
    after = _snapshot(data_dir)
    assert after == before, (
        "the refusal path wrote back — the re-inserted v4 row is a "
        "migration applied inside the never-migrate command"
    )
    assert after["schema_migrations"] == before["schema_migrations"]


def test_fw13_refuse_newer_is_a_typed_refusal_not_a_traceback(
    tmp_path: Path,
) -> None:
    """Finding 13 (LOW): a store written by a newer gateway (version-99
    fixture) raised RuntimeError outside the CLI catch tuple — a raw
    traceback. It is a typed refusal now (exit 1, machine-matchable)."""
    data_dir = _seed(tmp_path)
    conn = sqlite3.connect(str(db_path(data_dir)))
    conn.execute(
        "UPDATE schema_migrations SET version = 99"
        " WHERE version = (SELECT MAX(version) FROM schema_migrations)"
    )
    conn.commit()
    conn.close()
    result = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir)])
    assert result.exit_code == 1
    combined = _combined(result)
    assert "retention_store:" in combined
    assert "newer" in combined
    assert "Traceback" not in combined
    assert "RuntimeError" not in combined


# --- S3-2: the policy is live ----------------------------------------------------


def test_s3_2_disposal_dates_recompute_per_policy_file(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    short = _write_policy(tmp_path / "short.json", default_s=3600)
    long = _write_policy(tmp_path / "long.json", default_s=86400)
    def by_id(m: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {r["id"]: r for r in m["rows"]}

    f = by_id(_model(data_dir, policy_path=short, now=NOW))
    s = by_id(_model(data_dir, policy_path=long, now=NOW))
    assert f and s
    checked_default = checked_class = 0
    for rid in f:
        if f[rid]["disposal_date"] is None or s[rid]["disposal_date"] is None:
            continue
        dt_f = datetime.fromisoformat(f[rid]["disposal_date"].replace("Z", "+00:00"))
        dt_s = datetime.fromisoformat(s[rid]["disposal_date"].replace("Z", "+00:00"))
        delta = (dt_s - dt_f).total_seconds()
        # S3-2 under the finding-7 matched fields (honest contract): the two
        # policy files differ ONLY in the global default duration, so every
        # row the GLOBAL DEFAULT governs recomputes fully, while class rules
        # and bench-scoped rows (whose rules are identical in both files)
        # stay put.
        governs_global_default = (
            f[rid]["matched_rule"] == "default"
            and f[rid]["matched_scope"] == "global"
        )
        if governs_global_default:
            assert delta == 86400 - 3600  # default-level rows recompute fully
            checked_default += 1
        else:
            assert delta == 0  # class + bench rules are identical in both files
            checked_class += 1
    assert checked_default and checked_class, "need both default- and class-governed rows"


# --- S3-3: the clock is live, the dates are row-anchored ---------------------------


def test_s3_3_now_shifts_relative_fields_not_the_dates(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", default_s=3600)
    early = _model(data_dir, now=T2)
    late = _model(data_dir, now=NOW)
    rows_e = {r["id"]: r for r in early["rows"]}
    rows_l = {r["id"]: r for r in late["rows"]}
    for rid in rows_e:
        assert rows_e[rid]["disposal_date"] == rows_l[rid]["disposal_date"]
    scheduled = [r for r in rows_l.values() if r["status"] == "scheduled"]
    assert scheduled
    for rid in rows_e:
        if rows_l[rid]["status"] == "scheduled":
            # NOW is seven days past every anchor: all scheduled rows are overdue
            assert rows_l[rid]["overdue"] is True
            # at T2 the flag is exactly "disposal passed T2" — row-anchored,
            # so the bench-scoped 60s row can legitimately read overdue already
            assert rows_e[rid]["overdue"] == (rows_e[rid]["disposal_date"] <= T2)
    # now-relative wedge horizon: exhaustion_at shifts with now, used/rate do not
    w_e, w_l = early["quota_wedge"], late["quota_wedge"]
    for c_e, c_l in zip(w_e["contexts"], w_l["contexts"], strict=False):
        assert c_e["used_bytes"] == c_l["used_bytes"]
        if c_e.get("time_to_exhaustion_s") is not None:
            assert c_e["exhaustion_at"] != c_l["exhaustion_at"]


# --- S3-4 lives in tests/control/test_retention_policy.py -------------------------


# --- S3-5: quota scope + arithmetic ----------------------------------------------


def test_s3_5_quota_scope_and_arithmetic(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000)
    wedge = model["quota_wedge"]
    assert wedge["ceiling"] == 10_000 and wedge["ceiling_source"] == "flag"
    contexts = {c["context_key"]: c for c in wedge["contexts"]}
    assert len(contexts) == 3, f"expected 3 seeded contexts, got {sorted(contexts)}"
    assert all(c["ceiling_source"] == "flag" for c in contexts.values())

    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        # run-a charged: cap-wave(100) + cap-dup-a(64) + cap-dup-b(64) = 228
        # (the never-finalised cap-open belongs to run:run-c, not run-a)
        assert contexts["run:run-a"]["used_bytes"] == writer.used_bytes("run:run-a") == 228
        # run-b: its single 300 B capture is a single-event key under the
        # fork-B wire (one capture cannot define an ingest rate) — used
        # still reads the writer's ledger; the rate is honestly ABSENT
        # (None + unestimable_rate state), never a clean 0
        used_b = writer.used_bytes("run:run-b")
        assert contexts["run:run-b"]["used_bytes"] == used_b == 300
        assert contexts["run:run-b"]["rate_bytes_per_s"] is None
        assert contexts["run:run-b"]["state"] == "unestimable_rate"
        assert contexts["run:run-b"]["time_to_exhaustion_s"] is None
        # the wedge arithmetic arm rides the LIVE run-c key (a closed run's
        # row carries no exhaustion forecast — finding 11): two 100 B
        # captures, opens T0/T1 and closes T1/T2 -> 200 B over 120 s
        for cid, opened, closed in (("cap-c1", T0, T1), ("cap-c2", T1, T2)):
            writer.open_capture(
                capture_id=cid, context_key="run:run-c", fmt="raw_binary",
                sample_count=None, max_bytes=1000, now=opened)
            writer.append(cid, b"\x02" * 100, "run:run-c")
            writer.finalise(cid, closed, "run:run-c")
        used_c = writer.used_bytes("run:run-c")
        m2 = _model(data_dir, now=NOW, max_dataset_bytes=10_000)
        ctx2 = {c["context_key"]: c for c in m2["quota_wedge"]["contexts"]}
        c2 = ctx2["run:run-c"]
        assert c2["used_bytes"] == used_c == 712  # 512 reserved + 200 charged
        assert c2["rate_bytes_per_s"] == pytest.approx(200 / 120)
        assert c2["time_to_exhaustion_s"] == pytest.approx(
            (10_000 - 712) / (200 / 120)
        )
    finally:
        store.close()


def test_s3_5_ceiling_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    monkeypatch.setenv("BENCHWEAVE_MAX_DATASET_BYTES", "4096")
    model = _model(data_dir, now=NOW)
    assert model["quota_wedge"]["ceiling"] == 4096
    assert model["quota_wedge"]["ceiling_source"] == "env"


def test_s3_5_ceiling_unknown_discloses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = _seed(tmp_path)
    monkeypatch.delenv("BENCHWEAVE_MAX_DATASET_BYTES", raising=False)
    model = _model(data_dir, now=NOW)
    assert model["quota_wedge"]["ceiling"] is None
    assert model["quota_wedge"]["ceiling_source"] is None
    assert any("ceiling" in d.lower() for d in model["disclosures"])


# --- S3-6: dedup accounting -------------------------------------------------------


def test_s3_6_dedup_and_method_label(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    from benchweave.cli.retention import render_json, render_markdown

    store = Store.open(db_path(data_dir))
    try:
        dup_rows = store.connection.execute(
            "SELECT COUNT(*) FROM artifacts WHERE data = ?", (_CAP_DUP,)).fetchone()[0]
        total = store.connection.execute(
            "SELECT COALESCE(SUM(LENGTH(data)),0) FROM artifacts").fetchone()[0]
    finally:
        store.close()
    # two byte-identical captures through the real writer share one row
    assert dup_rows == 1
    model = _model(data_dir, now=NOW)
    # stored bytes equal SUM(LENGTH(data)) over artifacts, never 2x payload
    assert model["stored_bytes"]["total"] == total
    assert "SUM(LENGTH(data))" in model["stored_bytes"]["method"]
    assert "SUM(LENGTH(data))" in render_markdown(model)
    assert "SUM(LENGTH(data))" in render_json(model)


def test_s3_6_reput_changes_no_report_figure(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    before = _model(data_dir, now=NOW)
    store, content = _open(data_dir)
    try:
        content.put_artifact(_CAP_DUP, T2)  # re-put refreshes artifacts.stored_at only
    finally:
        store.close()
    after = _model(data_dir, now=NOW)
    assert after["stored_bytes"] == before["stored_bytes"]
    assert after["rows"] == before["rows"]


# --- S3-7: report-time classification ---------------------------------------------


def test_s3_7_report_time_classification(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", waveform_s=3600, default_s=86400)
    model = _model(data_dir, now=NOW)
    rows = {r["id"]: r for r in model["rows"]}
    assert rows["cap-wave"]["data_class"] == "capture:waveform_f64le"
    assert rows["cap-raw"]["data_class"] == "capture:raw_binary"
    # each capture class governed by its own class duration (3600 vs 7200), not the default 86400
    def dt(r: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(r["disposal_date"].replace("Z", "+00:00"))
    def anchored(r: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(r["anchor_at"].replace("Z", "+00:00"))

    assert (dt(rows["cap-wave"]) - anchored(rows["cap-wave"])).total_seconds() == 3600
    # bench-two's default governs: no bench class for raw_binary
    assert (dt(rows["cap-raw"]) - anchored(rows["cap-raw"])).total_seconds() == 60
    # the bench override governs only rows whose context maps to that bench
    assert rows["cap-raw"]["bench"] == BENCH_TWO
    assert rows["cap-raw"]["on_disposition"] == "review" and rows["cap-raw"]["duration_s"] == 60
    # unattributed keys fall to global, never a fabricated bench
    unattributed = [r for r in rows.values() if r["context_key"] == "manual-labbook"]
    assert len(unattributed) == 2  # dataset + novel-kind rows
    assert all(r["bench"] is None and r["duration_s"] == 86400 for r in unattributed)
    # a novel evidence kind gets its literal class and falls to the default
    novel = next(r for r in unattributed if r["data_class"] == "evidence:spectrummap")
    assert novel["matched_selector"] is None


# --- S3-8: the four statuses ------------------------------------------------------


def test_s3_8_ungoverned_rows_and_disclosure(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    model = _model(data_dir, now=NOW)
    assert model["rows"] and all(r["status"] == "ungoverned" for r in model["rows"])
    assert any("ungoverned" in d.lower() for d in model["disclosures"])


def test_s3_8_scheduled_has_a_date(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", run_end=True)
    model = _model(data_dir, now=NOW)
    rows = {r["id"]: r for r in model["rows"]}
    # run-a/run-b are terminal -> their run_end anchors resolve to the
    # terminal record's ended_at (T2 in the fixture)
    sched = [r for r in rows.values() if r["status"] == "scheduled"]
    assert sched and all(r["disposal_date"] for r in sched)
    for r in sched:
        delta = (
            datetime.fromisoformat(r["disposal_date"].replace("Z", "+00:00"))
            - datetime.fromisoformat(r["anchor_at"].replace("Z", "+00:00"))
        )
        assert delta.total_seconds() == r["duration_s"]


def test_s3_8_ungoverned_when_no_policy_file(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    model = _model(data_dir, now=NOW)
    assert model["policy"]["loaded"] is False
    assert model["rows"] and all(r["status"] == "ungoverned" for r in model["rows"])
    assert any("ungoverned" in d.lower() for d in model["disclosures"])


def test_s3_8_held_has_no_date(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", hold_event_log=True)
    model = _model(data_dir, now=NOW)
    held = [r for r in model["rows"] if r["status"] == "held"]
    assert held and all(r["disposal_date"] is None for r in held)
    assert all(r["data_class"] == "evidence:event_log" for r in held)


def test_s3_8_anchor_unresolved(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", run_end=True)
    # one evidence row under the LIVE run: run_end with a non-terminal run
    store, content = _open(data_dir)
    try:
        art = content.put_artifact(b'{"live": 1}', T0)
        content.put_evidence(
            "dataset", {"id": "live", "version": "1",
                        "sha256": hashlib.sha256(b'{"live": 1}').hexdigest()},
            art, "run:run-c", T0)
    finally:
        store.close()
    model = _model(data_dir, now=NOW)
    rows = {r["id"]: r for r in model["rows"]}
    unresolved = [r for r in rows.values() if r["status"] == "anchor_unresolved"]
    assert unresolved and all(r["disposal_date"] is None for r in unresolved)
    # manual-labbook is unattributed; run-c is live (non-terminal)
    assert any(r["context_key"] == "manual-labbook" for r in unresolved)
    assert any(r["context_key"] == "run:run-c" for r in unresolved)


def test_growth_projection_carries_n_and_span_and_excludes_zero_span(
    tmp_path: Path,
) -> None:
    """S3 growth control under the fork-B wire (issue #184): per stream the
    row carries observed_bytes/observed_span_s/n/rate_Bps and ONE horizon;
    single-event and zero-span keys render absence + their own counters
    (the honest contract change: run-a's three captures all land on the
    same instant, so the key is zero-span, and run-b's single capture is a
    single-event key — neither can define an ingest rate)."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000, horizon_s=3600)
    g = model["growth"]
    subs = g["subscriptions"]
    assert subs, "subscription lane must have rows"
    alpha = next(s for s in subs if s["subscription_id"] == "sub-alpha")
    assert alpha["n"] == 3 and alpha["observed_span_s"] == pytest.approx(100.0)
    assert alpha["rate_Bps"] == pytest.approx(alpha["observed_bytes"] / 100.0)
    assert alpha["projected_horizon_bytes"] == pytest.approx(alpha["rate_Bps"] * 3600)
    # sub-beta landed a single event -> excluded by its own counter
    assert {s["subscription_id"] for s in subs} == {"sub-alpha"}
    assert g["excluded"]["single_event"] >= 1
    # both capture keys are unestimable in the seed (zero-span / single)
    assert g["captures"] == []
    assert g["excluded"]["zero_span"] >= 1


def test_cli_retention_refuses_under_daemon_hold(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    with StoreHold(db_path(data_dir), label="gateway gw-retention pid 424242"):
        result = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir)])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "held" in combined
    assert "gw-retention" in combined and "424242" in combined, "must name the holder"


def test_cli_retention_default_policy_absent_is_ungoverned(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    result = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir), "--json"])
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.output)
    assert payload["policy"]["loaded"] is False
    assert payload["rows"] and all(r["status"] == "ungoverned" for r in payload["rows"])


def test_cli_retention_explicit_policy_missing_refuses(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    result = CliRunner().invoke(
        cli,
        ["retention", "--data-dir", str(data_dir), "--policy", str(tmp_path / "nope.json")],
    )
    assert result.exit_code != 0
    assert "retention" in _combined(result).lower()


def test_cli_retention_explicit_policy_invalid_refuses(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"config_version": "1", "default": {"duration_s": 0, "retain_after": "landing",'
        ' "on_disposition": "review"}, "classes": [], "benches": {}}',
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli,
        ["retention", "--data-dir", str(data_dir), "--policy", str(bad)],
    )
    assert result.exit_code != 0
    assert "retention_policy:" in _combined(result)


def test_cli_retention_json_matches_the_model(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    result = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir), "--json"])
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.output)
    reference = _model(data_dir, now=payload["generated_at"])
    assert payload == reference


def test_cli_retention_out_writes_both_forms(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    md = tmp_path / "ret.md"
    js = tmp_path / "ret.json"
    r1 = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir), "--out", str(md)])
    r2 = CliRunner().invoke(
        cli, ["retention", "--data-dir", str(data_dir), "--out", str(js), "--json"]
    )
    assert r1.exit_code == 0 and r2.exit_code == 0
    assert md.read_text(encoding="utf-8").startswith("#")
    assert json.loads(js.read_text(encoding="utf-8"))["policy"]["loaded"] is True


def test_cli_retention_unknown_bench_refuses(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    result = CliRunner().invoke(
        cli, ["retention", "--data-dir", str(data_dir), "--bench", "no-such-bench"]
    )
    assert result.exit_code != 0


# --- fix wave (issue #184): adjudicated findings, RED-first -------------------------

NAIVE = "2026-09-20T00:03:00"  # no offset — never a host-TZ-localized guess
T3 = "2026-09-25T00:00:00Z"  # five days after T2


def test_fw1_run_end_anchors_on_the_terminal_record_not_the_projection(
    tmp_path: Path,
) -> None:
    """Finding 1 (HIGH): the run_end anchor is the terminal run record's
    immutable ``ended_at`` (``runs.terminal_json``), never
    ``run_states.updated_at`` — which every later ``put_run_state`` (the
    worker's post-finalize terminal put, the recovery stale-projection
    close) moves."""
    data_dir = _seed(tmp_path)
    pol = _write_policy(
        data_dir / "retention-policy.json", retain_after_all="run_end"
    )

    def disposal_of(model: dict[str, Any]) -> str:
        row = next(r for r in model["rows"] if r["id"] == "cap-wave")
        assert row["status"] == "scheduled", row
        return str(row["disposal_date"])

    # The seed finalised run-a with ended_at=T2; run_states.updated_at is T2.
    first = disposal_of(_model(data_dir, policy_path=pol, now=NOW))
    assert first == "2026-09-20T01:02:00Z"  # T2 + 3600 s default duration

    # The worker's completion close / recovery re-stamp moves ONLY the
    # projection (run_states.updated_at); the terminal record is immutable.
    store = Store.open(db_path(data_dir))
    try:
        store.put_run_state("run-a", BENCH, "terminal", T3)
    finally:
        store.close()
    after = disposal_of(_model(data_dir, policy_path=pol, now=NOW))
    assert after == first, "run_end disposal moved with a later put_run_state"


def test_fw5_naive_stamps_anchor_unresolved_and_never_host_local(
    tmp_path: Path,
) -> None:
    """Finding 5 (MED): naive (no offset) stamps yield ``anchor_unresolved``
    with ``disposal_date: null`` — never a host-TZ-localized guess; the
    rendered report is byte-identical under different host timezones."""
    import time

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", run_end=True)
    # one capture finalised with a NAIVE stamp (a foreign writer's shape)
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        writer.open_capture(
            capture_id="cap-naive", context_key="run:run-a", fmt="raw_binary",
            sample_count=None, max_bytes=512, now=T0)
        writer.append("cap-naive", b"\x03" * 32, "run:run-a")
        writer.finalise("cap-naive", NAIVE, "run:run-a")
    finally:
        store.close()

    from benchweave.cli.retention import render_json

    def report_bytes() -> tuple[str, dict[str, dict[str, Any]]]:
        model = _model(data_dir, now=NOW)
        payload = render_json(model)
        rows = {r["id"]: r for r in model["rows"]}
        return payload, rows

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setenv("TZ", "Australia/Perth")
        time.tzset()
        perth, perth_rows = report_bytes()
        monkey.setenv("TZ", "UTC")
        time.tzset()
        utc, utc_rows = report_bytes()
    finally:
        monkey.undo()
        time.tzset()

    assert perth == utc, "report is host-timezone dependent"
    for rows in (perth_rows, utc_rows):
        naive_row = rows["cap-naive"]
        assert naive_row["status"] == "anchor_unresolved"
        assert naive_row["disposal_date"] is None


def test_fw5_unparseable_and_naive_terminal_records_stay_unresolved(
    tmp_path: Path,
) -> None:
    """Finding 5 arm: a run_end anchor whose terminal record is missing,
    unparseable, or naive resolves to ``anchor_unresolved`` — no crash, no
    guess."""
    data_dir = _seed(tmp_path)
    pol = _write_policy(
        data_dir / "retention-policy.json", retain_after_all="run_end"
    )

    def run_a_rows() -> list[dict[str, Any]]:
        # alpha-bench carries no bench scope, so its rows resolve to the
        # global run_end rules and read the terminal record's ended_at
        model = _model(data_dir, policy_path=pol, now=NOW)
        return [r for r in model["rows"] if r["context_key"] == "run:run-a"]

    for bad_ended_at in ("not-a-timestamp", NAIVE):
        store = Store.open(db_path(data_dir))
        try:
            store.finalize_run(
                "run-a", {"run_id": "run-a", "outcome": "passed",
                          "ended_at": bad_ended_at})
        finally:
            store.close()
        rows = run_a_rows()
        assert rows, "run-a must own report rows"
        assert all(
            r["status"] == "anchor_unresolved" and r["disposal_date"] is None
            for r in rows
        ), (bad_ended_at, rows)


def _seed_growth(tmp_path: Path, *, policy: bool = True, horizon: int | None = None
                 ) -> tuple[Path, dict[str, Any]]:
    """The fork-B repro shape: one bench, run:run-a terminal, and TWO
    captures of 1000 B each (10 s open->finalise windows, 20 s apart —
    2000 B over a 30 s observed span). A later probe adds an OLDER key
    whose rows must not move run-a's projection (the old global report
    window coupled every stream: adding an old key shrank run-a's
    projection by the window-stretch ratio)."""
    import shutil

    data_dir = tmp_path / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    from benchweave.cli.atrest import setup

    setup(data_dir)
    store = Store.open(db_path(data_dir))
    try:
        store.put_bench(BENCH, 1, "qualified", "{}", "op", T0)
        store.create_run("run-a", {"procedure_id": "demo"}, "op", T0)
        store.put_run_state("run-a", BENCH, "terminal", T2)
        store.finalize_run("run-a", {"run_id": "run-a", "outcome": "passed",
                                     "ended_at": T2})
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        writer.open_capture(
            capture_id="cap-g1", context_key="run:run-a", fmt="waveform_f64le",
            sample_count=None, max_bytes=1_000_000, now=T0)
        writer.append("cap-g1", b"\x01" * 1000, "run:run-a")
        writer.finalise("cap-g1", "2026-09-20T00:00:10Z", "run:run-a")
        writer.open_capture(
            capture_id="cap-g2", context_key="run:run-a", fmt="waveform_f64le",
            sample_count=None, max_bytes=1_000_000, now="2026-09-20T00:00:20Z")
        writer.append("cap-g2", b"\x01" * 1000, "run:run-a")
        writer.finalise("cap-g2", "2026-09-20T00:00:30Z", "run:run-a")
    finally:
        store.close()
    if policy:
        _write_policy(data_dir / "retention-policy.json")
    return data_dir, _model(
        data_dir, now=NOW, max_dataset_bytes=10_000, horizon_s=horizon
    )


def _add_capture(data_dir: Path, cid: str, opened_at: str, closed_at: str,
                 payload: bytes, fmt: str = "waveform_f64le") -> None:
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        writer.open_capture(
            capture_id=cid, context_key="run:run-b", fmt=fmt,
            sample_count=None, max_bytes=1_000_000, now=opened_at)
        writer.append(cid, payload, "run:run-b")
        writer.finalise(cid, closed_at, "run:run-b")
    finally:
        store.close()


def _projection(model: dict[str, Any], lane: str, key: str) -> float | None:
    """Read a stream's projection across the wire rename (RED runs against
    the old wire's projected_bytes, GREEN against projected_horizon_bytes)."""
    for row in model["growth"][lane]:
        if row.get("context_key", row.get("subscription_id")) == key:
            value = row.get("projected_horizon_bytes", row.get("projected_bytes"))
            return None if value is None else float(value)
    return None


def test_fw2_growth_wire_fields_are_meaningful(tmp_path: Path) -> None:
    """Finding 2 (HIGH, fork B invariants iii): per stream/key the wire
    carries observed_bytes, observed_span_s, n, rate_Bps (exactly
    observed_bytes/observed_span_s) and projected_horizon_bytes (exactly
    rate_Bps * horizon_s, one horizon for every row); the cancelling
    rate/duty/window intermediates are gone."""
    data_dir, model = _seed_growth(tmp_path)
    g = model["growth"]
    assert g["horizon_s"] >= 1
    assert set(g) == {
        "horizon_s", "subscriptions", "captures", "excluded",
        "dropped_events", "methods",
    }, sorted(g)
    for lane in ("subscriptions", "captures"):
        for row in g[lane]:
            assert row["n"] >= 2 and row["observed_bytes"] > 0
            assert row["observed_span_s"] > 0
            assert row["rate_Bps"] == pytest.approx(
                row["observed_bytes"] / row["observed_span_s"]
            )
            assert row["projected_horizon_bytes"] == pytest.approx(
                row["rate_Bps"] * g["horizon_s"]
            )
            assert "duty" not in row and "window_s" not in row
            assert "projected_bytes" not in row
    assert "report_window_s" not in g
    # one horizon for every row: doubling it doubles every projection and
    # changes nothing else
    _, doubled = _seed_growth(tmp_path, horizon=(model["growth"]["horizon_s"] * 2))
    base = {
        r["context_key"]: r["projected_horizon_bytes"] for r in g["captures"]
    }
    for row in doubled["growth"]["captures"]:
        assert row["projected_horizon_bytes"] == pytest.approx(
            base[row["context_key"]] * 2
        )
        assert row["rate_Bps"] == pytest.approx(
            next(r["rate_Bps"] for r in g["captures"]
                 if r["context_key"] == row["context_key"])
        )


def test_fw2_adding_a_row_never_shrinks_another_projection(tmp_path: Path) -> None:
    """Finding 2 (HIGH, fork B invariant i): the old algebra coupled every
    stream through the report-global window (now - earliest anchor), so an
    OLD row in one key shrank ANOTHER key's projection ~10x. Projections
    are per-stream now: run:run-a's projection is byte-stable when an older
    key lands, and its own measurements (bytes, n) are monotone."""
    data_dir, before = _seed_growth(tmp_path)
    a_before = _projection(before, "captures", "run:run-a")
    assert a_before is not None and a_before > 0
    # an OLDER key: 2 x 10 B captures finalised 19 days before every run-a
    # stamp (two rows, so the key is estimable in its own right)
    _add_capture(
        data_dir, "cap-old-a",
        opened_at="2026-09-01T00:00:00Z", closed_at="2026-09-01T00:00:10Z",
        payload=b"\x04" * 10, fmt="raw_binary",
    )
    _add_capture(
        data_dir, "cap-old-b",
        opened_at="2026-09-01T00:00:20Z", closed_at="2026-09-01T00:00:30Z",
        payload=b"\x04" * 10, fmt="raw_binary",
    )
    after = _model(data_dir, now=NOW, max_dataset_bytes=10_000)
    a_after = _projection(after, "captures", "run:run-a")
    assert a_after is not None
    assert a_after == pytest.approx(a_before), (
        f"run:run-a projection moved with another key's row: {a_before} -> {a_after}"
    )
    row_before = next(r for r in before["growth"]["captures"]
                      if r["context_key"] == "run:run-a")
    row_after = next(r for r in after["growth"]["captures"]
                     if r["context_key"] == "run:run-a")
    # within the stream, measurements are monotone under row addition
    assert row_after["observed_bytes"] >= row_before["observed_bytes"]
    assert row_after["n"] >= row_before["n"]
    # the new key projects independently at its own rate (20 B / 30 s)
    b_after = _projection(after, "captures", "run:run-b")
    assert b_after is not None and b_after > 0


def test_fw2_unestimable_windows_render_absence(tmp_path: Path) -> None:
    """Finding 2 (HIGH, fork B invariant ii) + the boundary table: over
    {span > horizon, span = 0, span unparseable, n = 1, n = 2} each case
    renders a decidable, distinct output — an unestimable window is absent
    and counted, never a clean zero projection."""
    horizon = 3600
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    store, content = _open(data_dir)
    try:
        def event(sub: str, received: str, payload: bytes) -> None:
            art = content.put_artifact(payload, T0)
            content.put_evidence(
                "event_log",
                {"id": f"ref-{sub}-{received}", "version": "1",
                 "sha256": hashlib.sha256(payload).hexdigest(),
                 "subscription_id": sub, "host_received_at": received},
                art, "run:run-a", T0)

        # span > horizon: two events horizon*3 apart
        event("sub-spanny", "2026-09-26T00:00:00Z", b"\x05" * 40)
        event("sub-spanny", "2026-09-26T03:00:00Z", b"\x05" * 40)
        # span = 0: two events, identical instants
        event("sub-twin", T1, b"\x06" * 8)
        event("sub-twin", T1, b"\x06" * 8)
        # span unparseable: naive (no offset) host_received_at
        event("sub-naive", NAIVE, b"\x07" * 4)
        event("sub-naive", "2026-09-20T00:04:00Z", b"\x07" * 4)
        # n = 1
        event("sub-solo", T0, b"\x08" * 2)
    finally:
        store.close()
    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000, horizon_s=horizon)
    g = model["growth"]
    subs = {s["subscription_id"]: s for s in g["subscriptions"]}
    # span > horizon renders present, with the span disclosed on the row
    assert subs["sub-spanny"]["observed_span_s"] > horizon
    assert subs["sub-spanny"]["projected_horizon_bytes"] > 0
    # the seed's sub-alpha lands with n == 3 (two events at T0, one at T1)
    assert "sub-alpha" in subs and subs["sub-alpha"]["n"] == 3
    # span = 0 / unparseable / n = 1 render ABSENCE + their own counters
    for absent in ("sub-twin", "sub-naive", "sub-solo"):
        assert absent not in subs, (absent, subs.get(absent))
    excluded = g["excluded"]
    assert excluded["zero_span"] >= 1
    assert excluded["unstamped"] >= 1
    assert excluded["single_event"] >= 1
    # ... and each counter is disclosed
    joined = "\n".join(model["disclosures"])
    for phrase in ("zero-span", "unstamped", "single event"):
        assert phrase in joined, phrase


def test_fw6_spans_compare_chronologically_after_parsing(tmp_path: Path) -> None:
    """Finding 6 (MED): raw string min/max inverted offset-mixed and
    bare-Z-vs-microsecond-Z stamp pairs — span collapsed to 0 and the
    report disclosed 'a single event' for n >= 2 streams. Stamps parse,
    then compare as instants."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    store, content = _open(data_dir)
    try:
        def event(sub: str, received: str) -> None:
            payload = f"{sub}-{received}".encode()
            art = content.put_artifact(payload, T0)
            content.put_evidence(
                "event_log",
                {"id": f"ref-{sub}-{len(received)}", "version": "1",
                 "sha256": hashlib.sha256(payload).hexdigest(),
                 "subscription_id": sub, "host_received_at": received},
                art, "run:run-a", T0)

        # offset-mixed pair: 12:00+08:00 == 04:00Z, then 05:00Z -> 3600 s
        event("sub-mixed", "2026-09-20T12:00:00+08:00")
        event("sub-mixed", "2026-09-20T05:00:00+00:00")
        # bare Z vs microsecond Z, same second: true span 0.5 s
        event("sub-mu", "2026-09-20T00:00:00Z")
        event("sub-mu", "2026-09-20T00:00:00.500000Z")
    finally:
        store.close()
    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000, horizon_s=3600)
    subs = {s["subscription_id"]: s for s in model["growth"]["subscriptions"]}
    assert subs["sub-mixed"]["observed_span_s"] == pytest.approx(3600.0), subs.get(
        "sub-mixed"
    )
    assert subs["sub-mixed"]["n"] == 2
    assert subs["sub-mu"]["observed_span_s"] == pytest.approx(0.5), subs.get("sub-mu")
    # the "single event" sentence may never print for an n >= 2 stream
    for note in model["disclosures"]:
        if "single event" in note:
            assert "n == 1" in note or "one event" in note, note


def test_fw9_held_classes_project_unbounded_growth_and_say_so(tmp_path: Path) -> None:
    """Finding 9 (MED): held classes used to project aging out at the hold
    rule's (schema-required) duration_s — a hold: true rule with
    duration_s 1 projected one second of growth. Held streams now project
    the same rate x horizon growth as everything else, labeled held."""
    data_dir = _seed(tmp_path)
    _write_policy(
        data_dir / "retention-policy.json",
        hold_event_log=True, event_log_s=1,
    )
    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000, horizon_s=3600)
    subs = {s["subscription_id"]: s for s in model["growth"]["subscriptions"]}
    alpha = subs["sub-alpha"]
    assert alpha["held"] is True
    assert alpha["observed_span_s"] == pytest.approx(100.0)
    assert alpha["projected_horizon_bytes"] == pytest.approx(
        alpha["rate_Bps"] * 3600
    )
    from benchweave.cli.retention import render_markdown

    md = render_markdown(model)
    assert "held" in md
    # run-a's event_log rows resolve to the held global class (alpha-bench
    # carries no scope): held in the disposal lane too — no aging-out fiction
    rows = [
        r for r in model["rows"]
        if r["data_class"] == "evidence:event_log" and r["context_key"] == "run:run-a"
    ]
    assert rows and all(r["status"] == "held" for r in rows)


def test_fw10_corrupt_and_unsubscribed_refs_are_counted_not_silent(
    tmp_path: Path,
) -> None:
    """Finding 10 (MOD): corrupt ``content_ref`` rows vanished uncounted from
    the growth lane. They are counted and disclosed now — silence is the
    defect."""
    data_dir = _seed(tmp_path)
    store = Store.open(db_path(data_dir))
    try:
        store.connection.executemany(
            "INSERT INTO evidence (evidence_id, kind, content_ref_json, artifact_id,"
            " context_key, stored_at) VALUES (?, 'event_log', ?, NULL, 'run:run-a', ?)",
            [
                ("ev-corrupt-json", "{not json", T0),
                ("ev-corrupt-nonstr", b"\x00\x01", T0),  # non-str ref column
                ("ev-nosub", json.dumps({"host_received_at": T0}), T0),
            ],
        )
        store.connection.commit()
    finally:
        store.close()
    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000, horizon_s=3600)
    dropped = model["growth"]["dropped_events"]
    assert dropped["corrupt_ref"] == 2, dropped
    assert dropped["no_subscription"] == 1, dropped
    joined = "\n".join(model["disclosures"])
    assert "corrupt" in joined and "subscription" in joined


def test_fw10_shared_artifacts_count_per_row_with_both_labels(tmp_path: Path) -> None:
    """Finding 10 (MOD): the growth lane's per-row referenced bytes
    over-count N x when payloads share one artifact (the writer's
    content-addressed store gives byte-identical payloads one artifact row)
    — the old single 'under-counts' label was wrong for this lane. Both
    bases are labeled now, each naming its basis and denominator."""
    data_dir = _seed(tmp_path)
    payload = b"\xab" * 500
    store, content = _open(data_dir)
    try:
        art = content.put_artifact(payload, T0)
        for received in (T0, T1):  # one subscription, two byte-identical events
            content.put_evidence(
                "event_log",
                {"id": f"shared-{received}", "version": "1",
                 "sha256": hashlib.sha256(payload).hexdigest(),
                 "subscription_id": "sub-shared", "host_received_at": received},
                art, "run:run-a", T0)
    finally:
        store.close()

    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000, horizon_s=3600)
    g = model["growth"]
    shared = next(s for s in g["subscriptions"] if s["subscription_id"] == "sub-shared")
    # referenced basis: per-row artifact lengths — 2 rows x 500 B
    assert shared["observed_bytes"] == 1000
    # stored basis: the artifact table — one 500 B row for the shared payload
    assert model["stored_bytes"]["total"] >= 500
    store = Store.open(db_path(data_dir))
    try:
        shared_rows = store.connection.execute(
            "SELECT COUNT(*) FROM artifacts WHERE data = ?", (payload,)
        ).fetchone()[0]
        total = store.connection.execute(
            "SELECT COALESCE(SUM(LENGTH(data)),0) FROM artifacts"
        ).fetchone()[0]
    finally:
        store.close()
    assert shared_rows == 1  # the writer dedups byte-identical payloads
    assert model["stored_bytes"]["total"] == total
    # every lane's method label names its basis and denominator
    methods = g["methods"]
    assert "per-row artifact lengths" in methods["subscriptions"]
    assert "over-counts" in methods["subscriptions"] and "shared" in methods["subscriptions"]
    assert "charged_bytes" in methods["captures"]
    assert "SUM(LENGTH(data))" in model["stored_bytes"]["method"]
    wedge_method = model["quota_wedge"]["method"]
    assert "reservation ledger" in wedge_method and "G3" in wedge_method
    from benchweave.cli.retention import render_json, render_markdown

    md = render_markdown(model)
    assert "per-row artifact lengths" in md and "reservation ledger" in md
    assert "per-row artifact lengths" in render_json(model)


def test_fw11_terminal_run_wedge_rows_render_closed(tmp_path: Path) -> None:
    """Finding 11 (LOW): wedge rows never consulted run liveness — a CLOSED
    run's key rendered a live-looking exhaustion date. A terminal run's
    wedge row is labeled closed and carries no exhaustion forecast (the
    used ledger is historical); a live run's row keeps its estimate."""
    data_dir, model = _seed_growth(tmp_path)  # run-a terminal, rate 2000/30 B/s
    wedge = model["quota_wedge"]
    ctx = {c["context_key"]: c for c in wedge["contexts"]}
    a = ctx["run:run-a"]
    assert a["used_bytes"] == 2000
    assert a["rate_bytes_per_s"] == pytest.approx(2000 / 30)
    assert a["run_state"] == "closed"
    assert a["time_to_exhaustion_s"] is None, "closed run must not forecast"
    assert a["exhaustion_at"] is None
    from benchweave.cli.retention import render_markdown

    md = render_markdown(model)
    line = next(ln for ln in md.splitlines() if ln.startswith("- run:run-a "))
    assert "closed" in line and "exhaustion" not in line
    # a live run keeps its live forecast
    store = Store.open(db_path(data_dir))
    try:
        store.create_run("run-live", {"procedure_id": "demo"}, "op", T0)
        store.put_run_state("run-live", BENCH, "running", T2)
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        for cid, opened, closed in (
            ("cap-l1", T0, T1), ("cap-l2", T1, T2),
        ):
            writer.open_capture(
                capture_id=cid, context_key="run:run-live", fmt="raw_binary",
                sample_count=None, max_bytes=1000, now=opened)
            writer.append(cid, b"\x09" * 100, "run:run-live")
            writer.finalise(cid, closed, "run:run-live")
    finally:
        store.close()
    model2 = _model(data_dir, now=NOW, max_dataset_bytes=10_000)
    ctx2 = {c["context_key"]: c for c in model2["quota_wedge"]["contexts"]}
    live = ctx2["run:run-live"]
    assert live["run_state"] == "live"
    assert live["rate_bytes_per_s"] == pytest.approx(200 / 120)
    assert live["time_to_exhaustion_s"] == pytest.approx((10_000 - 200) / (200 / 120))


def _matched_fields(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        row.get("matched_selector"),
        row.get("matched_scope"),
        row.get("matched_rule"),
    )


def test_fw7_matched_rule_names_the_winning_entry_all_four_branches(
    tmp_path: Path,
) -> None:
    """Finding 7 (MED): every disposal row reports the WINNING entry's
    identity — matched_selector = the selector string when a class rule
    won (else null), matched_scope = bench|global, matched_rule =
    class|default — for all four resolve branches (bench class → bench
    default → global class → global default)."""
    data_dir = _seed(tmp_path)
    pol = tmp_path / "four.json"
    pol.write_text(json.dumps({
        "config_version": "1",
        "default": {"duration_s": 86400, "retain_after": "landing",
                    "on_disposition": "review"},
        "classes": [
            {"selector": "capture:waveform_f64le", "duration_s": 3600,
             "retain_after": "landing", "on_disposition": "delete"},
            {"selector": "evidence:event_log", "duration_s": 86400,
             "retain_after": "landing", "on_disposition": "archive"},
        ],
        "benches": {
            BENCH_TWO: {
                "default": {"duration_s": 60, "retain_after": "landing",
                            "on_disposition": "review"},
                "classes": [
                    {"selector": "capture:raw_binary", "duration_s": 7200,
                     "retain_after": "landing", "on_disposition": "review"},
                ],
            }
        },
    }), encoding="utf-8")
    # one more beta-bench capture whose class has NO bench rule: bench default
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        writer.open_capture(
            capture_id="cap-beta-default", context_key="run:run-b",
            fmt="waveform_f64le", sample_count=None, max_bytes=512, now=T0)
        writer.append("cap-beta-default", b"\x0a" * 32, "run:run-b")
        writer.finalise("cap-beta-default", T1, "run:run-b")
    finally:
        store.close()
    model = _model(data_dir, policy_path=pol, now=NOW)
    rows = {r["id"]: r for r in model["rows"]}
    # global class wins (alpha-bench has no scope)
    assert _matched_fields(rows["cap-wave"]) == (
        "capture:waveform_f64le", "global", "class")
    # bench class wins (beta-bench scoped raw_binary)
    assert _matched_fields(rows["cap-raw"]) == ("capture:raw_binary", "bench", "class")
    # bench default wins (beta-bench, no class rule for waveform)
    assert _matched_fields(rows["cap-beta-default"]) == (None, "bench", "default")
    # global default wins (unattributed key, novel kind)
    novel = next(r for r in model["rows"] if r["data_class"] == "evidence:spectrummap")
    assert _matched_fields(novel) == (None, "global", "default")


def test_fw7_shadowed_class_rule_never_claimed(tmp_path: Path) -> None:
    """Finding 7 repro (the maintainer's P2): ``matched_selector`` used to
    be set when the class existed in ANY scope while the bench default
    governed — the row named a rule that did not govern it."""
    data_dir = _seed(tmp_path)
    pol = tmp_path / "shadow.json"
    pol.write_text(json.dumps({
        "config_version": "1",
        "default": {"duration_s": 3600, "retain_after": "landing",
                    "on_disposition": "review"},
        "classes": [
            {"selector": "capture:raw_binary", "duration_s": 7200,
             "retain_after": "landing", "on_disposition": "delete"},
        ],
        "benches": {
            BENCH_TWO: {
                "default": {"duration_s": 60, "retain_after": "landing",
                            "on_disposition": "review"},
                "classes": [],
            }
        },
    }), encoding="utf-8")
    model = _model(data_dir, policy_path=pol, now=NOW)
    row = next(r for r in model["rows"] if r["id"] == "cap-raw")
    # the bench default (60 s, review) governs — the shadowed global class
    # (7200 s, delete) must not be named
    assert row["duration_s"] == 60 and row["on_disposition"] == "review"
    assert _matched_fields(row) == (None, "bench", "default")


def _add_zero_charged_capture(data_dir: Path, cid: str, opened_at: str,
                              closed_at: str, ctx: str = "run:run-a") -> None:
    """A finalised staging row with charged_bytes = 0 (the writer refuses
    zero-byte finalises; this fixture-level row reaches the wire's honest
    measured-zero-growth branch)."""
    store = Store.open(db_path(data_dir))
    try:
        store.connection.execute(
            "INSERT INTO capture_staging (capture_id, context_key, state,"
            " reserved_bytes, charged_bytes, format, created_at, updated_at)"
            " VALUES (?, ?, 'finalised', 0, 0, 'raw_binary', ?, ?)",
            (cid, ctx, opened_at, closed_at),
        )
        store.connection.commit()
    finally:
        store.close()


def test_fw8_ceiling_knobs_validate_identically(tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 8 (MED): env BENCHWEAVE_MAX_DATASET_BYTES used to admit
    0 / -5 / abc while the flag refused < 1. Both knobs validate the same
    way now — a typed refusal naming the knob."""
    data_dir = _seed(tmp_path)
    for raw in ("0", "-5", "abc"):
        monkeypatch.setenv("BENCHWEAVE_MAX_DATASET_BYTES", raw)
        with pytest.raises(ValueError) as exc:
            _model(data_dir, now=NOW)
        assert "BENCHWEAVE_MAX_DATASET_BYTES" in str(exc.value)
        assert "integer >= 1" in str(exc.value)
    monkeypatch.delenv("BENCHWEAVE_MAX_DATASET_BYTES", raising=False)
    for flag in ("0", "-5"):
        with pytest.raises(ValueError) as exc:
            _model(data_dir, now=NOW, max_dataset_bytes=int(flag))
        assert "--max-dataset-bytes" in str(exc.value)
    # the CLI maps both refusals to exit 1, no traceback
    monkeypatch.setenv("BENCHWEAVE_MAX_DATASET_BYTES", "abc")
    result = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir)])
    assert result.exit_code == 1
    assert "BENCHWEAVE_MAX_DATASET_BYTES" in _combined(result)
    assert "Traceback" not in _combined(result)


def test_fw8_wedge_states_boundary_table(tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 8 (MED): the boundary table — (ceiling-used) in {>, =, < 0}
    x rate in {measured > 0, measured = 0, unestimable} x ceiling in
    {absent} — each cell renders decidable, distinct output. An over-
    ceiling key renders 'over ceiling by N bytes', NEVER a negative
    forecast; measured zero growth is labeled with n/span and split from
    the unknown-ceiling label."""
    from benchweave.cli.retention import render_markdown

    monkeypatch.delenv("BENCHWEAVE_MAX_DATASET_BYTES", raising=False)
    data_dir = _seed(tmp_path)
    # measured rate > 0: run-c's two 100 B captures (S3-5's shape) — add them
    store = Store.open(db_path(data_dir))
    try:
        store.create_run("run-z", {"procedure_id": "demo"}, "op", T0)
        store.put_run_state("run-z", BENCH, "running", T2)
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        for cid, opened, closed in (("cap-c1", T0, T1), ("cap-c2", T1, T2)):
            writer.open_capture(
                capture_id=cid, context_key="run:run-c", fmt="raw_binary",
                sample_count=None, max_bytes=1000, now=opened)
            writer.append(cid, b"\x02" * 100, "run:run-c")
            writer.finalise(cid, closed, "run:run-c")
    finally:
        store.close()
    # measured rate = 0: live run:run-z gains two zero-charged rows over a
    # span (run-a is terminal: a closed row renders the closed line first)
    _add_zero_charged_capture(data_dir, "cap-z1", T0, T1, ctx="run:run-z")
    _add_zero_charged_capture(data_dir, "cap-z2", T1, T2, ctx="run:run-z")
    # unestimable: run:run-b keeps its single capture (single_event key)

    def wedge_by(ceiling: int | None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        model = _model(data_dir, now=NOW, max_dataset_bytes=ceiling)
        return {c["context_key"]: c for c in model["quota_wedge"]["contexts"]}, model

    # ceiling absent: every row labels itself ceiling_unknown (split from
    # zero-rate: the old wire conflated both into one sentence)
    unknown, model = wedge_by(None)
    assert all(c["state"] == "ceiling_unknown" for c in unknown.values())
    assert any("ceiling unknown" in d for d in model["disclosures"])
    joined = "\n".join(render_markdown(model).splitlines())
    assert "ceiling unknown; projection omitted" in joined

    # measured rate > 0: run-c's used is 512 (reserved cap-open) + 200 = 712
    w, model = wedge_by(10_000)  # ceiling - used > 0 for every key
    c = w["run:run-c"]
    assert c["state"] == "forecast"
    assert c["rate_bytes_per_s"] == pytest.approx(200 / 120)
    assert c["n"] == 2 and c["observed_span_s"] == pytest.approx(120.0)
    assert c["time_to_exhaustion_s"] == pytest.approx((10_000 - 712) / (200 / 120))

    w, _ = wedge_by(712)  # ceiling - used == 0
    assert w["run:run-c"]["state"] == "at_ceiling"
    assert w["run:run-c"]["time_to_exhaustion_s"] is None

    w, model = wedge_by(612)  # ceiling - used < 0
    over = w["run:run-c"]
    assert over["state"] == "over_ceiling"
    assert over["over_ceiling_bytes"] == 100
    assert over["time_to_exhaustion_s"] is None
    assert over["exhaustion_at"] is None, "no negative forecast, ever"
    line = next(ln for ln in render_markdown(model).splitlines()
                if ln.startswith("- run:run-c "))
    assert "over ceiling by 100 bytes" in line and "-9" not in line

    # measured rate = 0: run-z's zero-charged pair (n=2, span 120 s)
    w, model = wedge_by(10_000)
    zero = w["run:run-z"]
    assert zero["state"] == "zero_growth"
    assert zero["rate_bytes_per_s"] == 0.0
    assert zero["n"] == 2 and zero["observed_span_s"] == pytest.approx(120.0)
    zero_line = next(ln for ln in render_markdown(model).splitlines()
                     if ln.startswith("- run:run-z "))
    assert "measured zero growth" in zero_line

    # unestimable rate: run-b (single capture) — never a clean 0 rate
    unest = w["run:run-b"]
    assert unest["state"] == "unestimable_rate"
    assert unest["rate_bytes_per_s"] is None
    assert unest["time_to_exhaustion_s"] is None



def test_fw3_governed_row_refuses_typed_on_domain_overflow(tmp_path: Path) -> None:
    """Finding 3, governed-row arm: ``duration_s`` at the datetime domain
    ceiling plus a real (2026) anchor pushes the disposal date out of the
    datetime domain — the report-time refusal is typed
    (``retention_policy:``), never an unmapped OverflowError/ValueError
    from the timestamp math."""
    from benchweave.cli.retention import RetentionStoreRefused  # noqa: F401 (family)

    data_dir = _seed(tmp_path)
    pol = tmp_path / "forever.json"
    pol.write_text(json.dumps({
        "config_version": "1",
        "default": {"duration_s": 253_402_300_799, "retain_after": "landing",
                    "on_disposition": "review"},
        "classes": [], "benches": {},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match=r"retention_policy:"):
        _model(data_dir, policy_path=pol, now=NOW)


def test_fw17_rowless_run_prefixed_keys_survive_bench_filtering(tmp_path: Path) -> None:
    """Finding 17 (lane conflict, settled): a run-prefixed context key whose
    run has NO run_states row is UNATTRIBUTED — it must survive --bench
    filtering exactly like any unattributed key (lane 1's never-silently-
    vanish claim wins), disclosed by count. The old scope rule dropped it."""
    data_dir = _seed(tmp_path)
    store, content = _open(data_dir)
    try:
        art = content.put_artifact(b'{"orphan": 1}', T0)
        content.put_evidence(
            "dataset",
            {"id": "orphan", "version": "1",
             "sha256": hashlib.sha256(b'{"orphan": 1}').hexdigest()},
            art, "run:run-zz", T0)  # no run_states row for run-zz
    finally:
        store.close()
    unscoped = _model(data_dir, now=NOW)
    scoped = _model(data_dir, now=NOW, bench_id=BENCH)
    orphan_unscoped = [r for r in unscoped["rows"] if r["context_key"] == "run:run-zz"]
    orphan_scoped = [r for r in scoped["rows"] if r["context_key"] == "run:run-zz"]
    assert orphan_unscoped, "rowless key present unscoped"
    assert orphan_scoped, "unattributed keys never silently vanish under --bench"
    assert all(r["bench"] is None for r in orphan_scoped)  # never a fabricated bench
    assert any(
        "run-prefixed" in d and "no run" in d for d in scoped["disclosures"]
    ), scoped["disclosures"]
    # a run that EXISTS on another bench still filters out (true scope)
    gone = [r for r in scoped["rows"] if r["context_key"] == "run:run-b"]
    assert not gone


def test_fw15_each_test_s3_function_carries_only_its_own_scenario() -> None:
    """Finding 15 (NIT): S3-8 statements were stranded inside
    test_s3_7_report_time_classification (a col-0 comment does not end a
    function) and three scenarios were merged into one test. Structural
    guard: every test_s3_* function seeds its fixture at most once."""
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_s3_"):
            seeds = sum(
                1
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "_seed"
            )
            if seeds > 1:
                offenders.append(f"{node.name}: {seeds} _seed calls")
    assert not offenders, f"merged scenarios (issue #184 finding 15): {offenders}"


def test_fw16_build_retention_report_takes_no_unused_content_store() -> None:
    """Finding 16 (NIT): build_retention_report's content parameter was
    unused (the model reads the store connection directly)."""
    import inspect

    from benchweave.cli.retention import build_retention_report

    params = inspect.signature(build_retention_report).parameters
    assert "content" not in params, params
    assert set(params) == {"store", "policy", "bench_id", "now",
                           "max_dataset_bytes", "horizon_s"}


def test_fw1_anchor_unresolved_rows_are_counted(tmp_path: Path) -> None:
    """Finding 1's honesty surface: rows whose anchor could not resolve are
    per-row anchor_unresolved AND counted in the disclosures."""
    data_dir = _seed(tmp_path)
    pol = _write_policy(data_dir / "retention-policy.json", retain_after_all="run_end")
    model = _model(data_dir, policy_path=pol, now=NOW)
    unresolved = [r for r in model["rows"] if r["status"] == "anchor_unresolved"]
    assert unresolved  # run-c (live) + manual-labbook (unattributed) rows
    assert any(
        str(len(unresolved)) in d and "anchor_unresolved" in d
        for d in model["disclosures"]
    ), model["disclosures"]


# --- the consolidated review fold (issue #184 R2) -------------------------------------


def test_fold2_naive_now_refuses_typed_naming_the_parameter(tmp_path: Path) -> None:
    """R2 fold item 2a: ``_parse`` accepted a naive caller ``now`` while
    ``_parse_utc`` rejects naive STORED stamps — a naive ``now`` escaped
    mid-build as an uncaught TypeError (aware disposal_dt vs naive now_dt
    comparison). The caller's clock meets the same UTC-strict parse: a
    typed ValueError naming the parameter, never a traceback."""
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")  # scheduled rows exist
    with pytest.raises(ValueError) as exc:
        _model(data_dir, now=NAIVE)
    assert "now" in str(exc.value), exc.value
    assert "offset" in str(exc.value), exc.value


def test_fold2_wedge_exhaustion_beyond_domain_renders_decidable_output(
    tmp_path: Path,
) -> None:
    """R2 fold item 2b: the wedge's ``exhaustion_at`` did raw
    ``datetime.fromtimestamp(now + (ceiling-used)/rate)`` — a trickle rate
    × a 10**13 ceiling overflowed the datetime domain (year ~178000) as an
    untyped whole-report error, killing every other row's output. The
    exhaustion arithmetic now wraps with the fw3 posture: the overflowing
    key keeps ``time_to_exhaustion_s`` (the honest number) and renders an
    absent instant + a disclosure; other keys' forecasts survive."""
    from benchweave.cli.retention import render_markdown

    data_dir = _seed(tmp_path)
    store = Store.open(db_path(data_dir))
    try:
        # a live trickle key: 4 B over a 2 s span -> rate 2 B/s; with a
        # 10**13 ceiling the exhaustion instant is ~158,000 years out
        store.create_run("run-trickle", {"procedure_id": "demo"}, "op", T0)
        store.put_run_state("run-trickle", BENCH, "running", T1)
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10**13
        )
        for cid, opened, closed in (
            ("cap-tr1", T0, "2026-09-20T00:00:01Z"),
            ("cap-tr2", "2026-09-20T00:00:01Z", "2026-09-20T00:00:02Z"),
        ):
            writer.open_capture(
                capture_id=cid, context_key="run:run-trickle", fmt="raw_binary",
                sample_count=None, max_bytes=1000, now=opened)
            writer.append(cid, b"\x0b" * 2, "run:run-trickle")
            writer.finalise(cid, closed, "run:run-trickle")
        # a healthy live key: 200 B over a 2 s span -> rate 100 B/s; the
        # same ceiling exhausts ~year 5200, INSIDE the datetime domain
        store.create_run("run-fatpipe", {"procedure_id": "demo"}, "op", T0)
        store.put_run_state("run-fatpipe", BENCH, "running", T1)
        for cid, opened, closed in (
            ("cap-fat1", T0, "2026-09-20T00:00:01Z"),
            ("cap-fat2", "2026-09-20T00:00:01Z", "2026-09-20T00:00:02Z"),
        ):
            writer.open_capture(
                capture_id=cid, context_key="run:run-fatpipe", fmt="raw_binary",
                sample_count=None, max_bytes=1000, now=opened)
            writer.append(cid, b"\x0c" * 100, "run:run-fatpipe")
            writer.finalise(cid, closed, "run:run-fatpipe")
    finally:
        store.close()

    model = _model(data_dir, now=NOW, max_dataset_bytes=10**13)
    wedge = {c["context_key"]: c for c in model["quota_wedge"]["contexts"]}
    trickle = wedge["run:run-trickle"]
    assert trickle["state"] == "forecast"
    assert trickle["rate_bytes_per_s"] == pytest.approx(2.0)
    assert trickle["time_to_exhaustion_s"] == pytest.approx(
        (10**13 - trickle["used_bytes"]) / 2.0
    ), "the honest number is kept"
    assert trickle["exhaustion_at"] is None, "the instant cannot be rendered"
    assert any(
        "beyond the datetime domain" in d for d in model["disclosures"]
    ), model["disclosures"]
    # the healthy key's forecast survives the trickle key's overflow
    fatpipe = wedge["run:run-fatpipe"]
    assert fatpipe["state"] == "forecast"
    assert fatpipe["exhaustion_at"] is not None
    assert fatpipe["exhaustion_at"].startswith("5")  # a rendered year ~52xx
    md = render_markdown(model)
    trickle_line = next(ln for ln in md.splitlines() if ln.startswith("- run:run-trickle"))
    assert "beyond the datetime domain" in trickle_line
    assert fatpipe["exhaustion_at"][:4] in md


def test_fold3_markdown_escapes_store_sourced_identifiers(tmp_path: Path) -> None:
    """R2 fold item 3: evidence kinds (an open vocabulary) and subscription
    ids (read back from ``content_ref`` JSON) were interpolated into
    markdown unescaped — a newline in either forged arbitrary lines in the
    operator's deletion-decision report. The emitter escapes control
    characters in every store-sourced string now; the JSON form is
    untouched (``json.dumps`` already encodes controls)."""
    from benchweave.cli.retention import render_json, render_markdown

    data_dir = _seed(tmp_path)
    store, content = _open(data_dir)
    try:
        # a forged subscription id over two events (n = 2 -> the stream
        # lands in the subscriptions lane, where the id is interpolated)
        for received in (T0, T1):
            payload = f"inject-{received}".encode()
            art = content.put_artifact(payload, T0)
            content.put_evidence(
                "event_log",
                {"id": f"ref-inject-{received}", "version": "1",
                 "sha256": hashlib.sha256(payload).hexdigest(),
                 "subscription_id": "sub-a\n- FORGED-SUB-LINE",
                 "host_received_at": received},
                art, "run:run-a", T0)
        # a forged evidence kind (fixture-level row, the fw10 precedent):
        # the kind is an open vocabulary the store does not constrain
        store.connection.execute(
            "INSERT INTO evidence (evidence_id, kind, content_ref_json, artifact_id,"
            " context_key, stored_at) VALUES (?, ?, '{}', NULL, 'run:run-a', ?)",
            ("ev-forged-kind", "x status=held disposal=2099\n- FORGED-ROW", T0),
        )
        store.connection.commit()
    finally:
        store.close()

    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000)
    md = render_markdown(model)
    lines = md.splitlines()
    assert not any(
        ln.startswith("- FORGED-ROW") for ln in lines
    ), "a forged disposal row was injected as its own report line"
    assert not any(
        ln.startswith("- FORGED-SUB-LINE") for ln in lines
    ), "a forged subscription line was injected as its own report line"
    assert "\\x0a" in md, "the newline renders as its visible escape"
    carrier = next(ln for ln in lines if "FORGED-ROW" in ln)
    assert carrier.startswith("- "), carrier  # stays inside its own row line
    sub_carrier = next(ln for ln in lines if "FORGED-SUB-LINE" in ln)
    assert sub_carrier.startswith("- subscription "), sub_carrier
    # the JSON machine form keeps the raw bytes of the store's identifiers
    payload = json.loads(render_json(model))
    kinds = {r["data_class"] for r in payload["rows"]}
    assert "evidence:x status=held disposal=2099\n- FORGED-ROW" in kinds
    subs = {s["subscription_id"] for s in payload["growth"]["subscriptions"]}
    assert "sub-a\n- FORGED-SUB-LINE" in subs


def test_fold4_null_context_subscription_group_sorts_and_reports(
    tmp_path: Path,
) -> None:
    """R2 fold item 4: ``sorted(sub_groups.items())`` compared tuple keys
    ``(sub, None)`` vs ``(sub, str)`` — one NULL-context event_log row
    sharing a subscription id with a keyed row killed the whole report
    with an uncaught TypeError. The sort key is None-safe now; both
    groups report (the NULL-context group under its own key)."""
    data_dir = _seed(tmp_path)  # sub-alpha: 3 events at run:run-a
    store = Store.open(db_path(data_dir))
    try:
        for i, received in enumerate((T0, T1)):
            store.connection.execute(
                "INSERT INTO evidence (evidence_id, kind, content_ref_json,"
                " artifact_id, context_key, stored_at)"
                " VALUES (?, 'event_log', ?, NULL, NULL, ?)",
                (
                    f"ev-nullctx-{i}",
                    json.dumps(
                        {"subscription_id": "sub-alpha", "host_received_at": received}
                    ),
                    received,
                ),
            )
        store.connection.commit()
    finally:
        store.close()
    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000)
    by_ctx = {
        s["context_key"]: s
        for s in model["growth"]["subscriptions"]
        if s["subscription_id"] == "sub-alpha"
    }
    assert set(by_ctx) == {"run:run-a", None}, by_ctx
    assert by_ctx["run:run-a"]["n"] == 3
    assert by_ctx[None]["n"] == 2


def test_fold5_horizon_domain_refusal_names_the_knob(tmp_path: Path) -> None:
    """R2 fold item 5: ``--horizon-s 1e309`` (a 310-digit integer) parsed
    fine and died later inside ``rate * horizon_s`` as 'int too large to
    convert to float' — exit 1 through the CLI belt, but the message named
    no knob and no domain. The knob validates at parse now: a typed
    refusal naming ``--horizon-s`` and its domain (the datetime-domain
    ceiling ``duration_s`` already carries, ``MAX_DURATION_S``)."""
    data_dir = _seed(tmp_path)
    with pytest.raises(ValueError) as exc:
        _model(data_dir, now=NOW, horizon_s=10**309)
    assert "--horizon-s" in str(exc.value), exc.value
    assert "253402300799" in str(exc.value), exc.value
    result = CliRunner().invoke(
        cli,
        ["retention", "--data-dir", str(data_dir), "--horizon-s", "1" + "0" * 309],
    )
    assert result.exit_code == 1, _combined(result)
    combined = _combined(result)
    assert "--horizon-s" in combined, combined
    assert "253402300799" in combined, combined
    assert "Traceback" not in combined


# --- the G6 fold refute: claim-accuracy fixes (findings 1-4, 6, 7) -----------------


def test_g6_1_unicode_separators_cannot_forge_markdown_lines(tmp_path: Path) -> None:
    """G6 finding 1 (+6): ``_md_text`` escaped C0+DEL only, so U+2028/U+2029/
    NEL (line separators outside C0) still forged report lines, and a literal
    ``\\x0a`` in an identifier rendered indistinguishably from an escaped
    newline. The escape class now covers every remaining ``str.splitlines``
    separator plus the RTL override, and the backslash is escaped first so
    literal escape text cannot collide with a real escape."""
    from benchweave.cli.retention import render_json, render_markdown

    data_dir = _seed(tmp_path)
    store, content = _open(data_dir)
    try:
        carriers = {
            "sub-ls": "sub-ls - FORGED-U2028: n=2",
            "sub-ps": "sub-ps - FORGED-U2029: n=2",
            "sub-nel": "sub-nel- FORGED-NEL: n=2",
            "sub-rtl": "sub-rtl‮FORGED-RTL",
            "sub-lit": "sub-lit\\x0a- COLLIDE-LINE",
        }
        for name, sub in carriers.items():
            for i, received in enumerate((T0, T1)):
                payload = f"{name}-{i}".encode()
                art = content.put_artifact(payload, T0)
                content.put_evidence(
                    "event_log",
                    {"id": f"ref-{name}-{i}", "version": "1",
                     "sha256": hashlib.sha256(payload).hexdigest(),
                     "subscription_id": sub,
                     "host_received_at": received},
                    art, "run:run-a", T0)
    finally:
        store.close()

    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000)
    md = render_markdown(model)
    for raw in (" ", " ", "", "‮"):
        assert raw not in md, f"raw separator survived: {raw!r}"
    lines = md.splitlines()
    assert not any(
        ln.startswith(("- FORGED-", "- COLLIDE-LINE")) for ln in lines
    ), "a forged line survived escaping"
    ids = {
        s["subscription_id"]
        for s in json.loads(render_json(model))["growth"]["subscriptions"]
    }
    assert "sub-ls - FORGED-U2028: n=2" in ids  # JSON round-trips raw


def test_g6_2_ceiling_knob_upper_bound_is_named(tmp_path: Path) -> None:
    """G6 finding 2: ``--max-dataset-bytes`` had no upper bound, so a huge
    ceiling turned the wedge's int-to-float division into an unmapped
    OverflowError that killed the whole report — the exact class fold 5
    closed on ``--horizon-s``. Both ceiling knobs now refuse above the
    float-exact domain, naming the knob."""
    data_dir = _seed(tmp_path)
    with pytest.raises(ValueError) as exc:
        _model(data_dir, now=NOW, max_dataset_bytes=10**400)
    assert "--max-dataset-bytes" in str(exc.value), exc.value
    model = _model(data_dir, now=NOW, max_dataset_bytes=2**53)
    assert model["rows"], "the bound itself must be admissible"
    result = CliRunner().invoke(
        cli, ["retention", "--data-dir", str(data_dir),
              "--max-dataset-bytes", "1" + "0" * 400])
    assert result.exit_code == 1, _combined(result)
    combined = _combined(result)
    assert "--max-dataset-bytes" in combined, combined
    assert "Traceback" not in combined


def test_g6_3_unknown_low_version_asserts_no_false_direction(
    tmp_path: Path,
) -> None:
    """G6 findings 3 (+7): the refuse-newer message claimed ``is newer than``
    from ``max(unknown)`` without comparing — false for an unknown-LOW row
    (``version 0 is newer than the gateway's 5``) — and the missing branch
    named a ``1..N`` range instead of the migrations list. The message states
    direction only when it compared, names the known set, and a mixed store
    names its hole alongside the unknown row."""
    data_dir = _seed(tmp_path)
    db = db_path(data_dir)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at)"
        " VALUES (0, 'applied-by-migration')"
    )
    conn.commit()
    conn.close()
    result = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir)])
    assert result.exit_code == 1, _combined(result)
    combined = _combined(result)
    assert "retention_store:" in combined, combined
    assert "is newer" not in combined, combined
    assert "unknown" in combined, combined

    data_dir = _seed(tmp_path / "mixed")
    db = db_path(data_dir)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM schema_migrations WHERE version = 4")
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at)"
        " VALUES (0, 'applied-by-migration')"
    )
    conn.commit()
    conn.close()
    result = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir)])
    combined = _combined(result)
    assert result.exit_code == 1, combined
    assert "missing" in combined and "4" in combined, (
        "the mixed store must name its hole alongside the unknown row"
    )


def test_g6_4_corrupt_version_rows_stay_in_the_typed_family(
    tmp_path: Path,
) -> None:
    """G6 finding 4: a non-integer ``schema_migrations.version`` row (a
    rebuilt or corrupt table) escaped as a bare ``invalid literal for
    int()`` — outside the ``retention_store:`` family the module contract
    promises. The corrupt row is a typed refusal now."""
    data_dir = _seed(tmp_path)
    db = db_path(data_dir)
    conn = sqlite3.connect(db)
    conn.execute("DROP TABLE schema_migrations")
    conn.execute("CREATE TABLE schema_migrations (version TEXT)")
    conn.execute("INSERT INTO schema_migrations (version) VALUES ('abc')")
    conn.commit()
    conn.close()
    result = CliRunner().invoke(cli, ["retention", "--data-dir", str(data_dir)])
    assert result.exit_code == 1, _combined(result)
    combined = _combined(result)
    assert "retention_store:" in combined, combined
    assert "Traceback" not in combined


def test_w5_pay_rows_carry_the_dataset_row_kind(tmp_path: Path) -> None:
    """Item 5 rider 2 (adversary F4): a payload-lane staging row (a pay:
    id, format carrying the payload encoding) is a DATASET row, not a
    capture — the report must label it row_kind 'dataset' with an honest
    data_class ('dataset:<encoding>'), never the inherited
    'capture:unknown'. Capture rows stay byte-identical in shape."""
    from benchweave.cli.retention import build_retention_report

    data_dir = _seed(tmp_path)
    store, content = _open(data_dir)
    try:
        writer = CaptureStagingStore(
            store, max_capture_bytes=10_000_000, max_dataset_bytes=10_000_000
        )
        writer.open_payload(
            payload_id="pay:run-a:1",
            context_key="run:run-a",
            encoding="f64le",
            byte_limit=64,
            now=T0,
        )
        writer.append("pay:run-a:1", b"\x07" * 8, "run:run-a")
        writer.finalise("pay:run-a:1", T1, "run:run-a")
        report = build_retention_report(store, policy=None, now=NOW)
        rows = {r["id"]: r for r in report["rows"]}
        pay_row = rows["pay:run-a:1"]
        assert pay_row["row_kind"] == "dataset", pay_row
        assert pay_row["data_class"] == "dataset:f64le", pay_row
        # Capture rows keep their exact historical labels.
        assert rows["cap-wave"]["row_kind"] == "capture"
        assert rows["cap-wave"]["data_class"] == "capture:waveform_f64le"
        assert rows["cap-raw"]["data_class"] == "capture:raw_binary"
    finally:
        store.close()
