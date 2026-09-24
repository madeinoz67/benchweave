"""Issue #43 slice 3 (Decision 8): the retention report — pure projection.

The S3 controls. Every control is exact fixture arithmetic, and each must fail
when the mechanism is reverted (absence arm). The standing rule under test:
**slice 3 writes nothing back** — S3-1 pins it over all fifteen tables.

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
    doc: dict[str, Any] = {
        "config_version": "1",
        "default": {
            "duration_s": kw.get("default_s", 3600),
            "retain_after": "run_end" if kw.get("run_end") else "landing",
            "on_disposition": "review",
        },
        "classes": [
            {
                "selector": "capture:waveform_f64le",
                "duration_s": kw.get("waveform_s", 3600),
                "retain_after": "landing",
                "on_disposition": "delete",
            },
            {
                "selector": "capture:raw_binary",
                "duration_s": 7200,
                "retain_after": "landing",
                "on_disposition": "review",
            },
            {
                "selector": "evidence:event_log",
                "duration_s": kw.get("event_log_s", 86400),
                "retain_after": "landing",
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
                store.finalize_run(run, {"run_id": run, "outcome": "passed"})

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
}


def _snapshot(data_dir: Path) -> dict[str, tuple[int, str]]:
    uri = f"{db_path(data_dir).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        assert names == _TABLES, f"table set drifted: {sorted(names ^ _TABLES)}"
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
        if f[rid]["matched_selector"] is None:
            assert delta == 86400 - 3600  # default-level rows recompute fully
            checked_default += 1
        else:
            assert delta == 0  # class rules are identical in both files
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
        # run-b: one capture 300 B finalised at T1, opened at T0 → span 100 s → rate 3 B/s
        used_b = writer.used_bytes("run:run-b")
        assert contexts["run:run-b"]["used_bytes"] == used_b == 300
        assert contexts["run:run-b"]["rate_bytes_per_s"] == pytest.approx(3.0)
        tte_b = contexts["run:run-b"]["time_to_exhaustion_s"]
        assert tte_b == pytest.approx((10_000 - 300) / 3)
        # run-c holds only the never-finalised capture: 512 reserved, 0 charged
        used_c = writer.used_bytes("run:run-c")
        assert contexts["run:run-c"]["used_bytes"] == used_c == 512
        assert contexts["run:run-c"]["rate_bytes_per_s"] == 0
        # zero rate → no exhaustion estimate
        assert contexts["run:run-c"]["time_to_exhaustion_s"] is None
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

    data_dir = _seed(tmp_path)
    model = _model(data_dir, now=NOW)
    assert model["policy"]["loaded"] is False
    assert model["rows"] and all(r["status"] == "ungoverned" for r in model["rows"])


def test_s3_8_ungoverned_rows_and_disclosure(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    model = _model(data_dir, now=NOW)
    assert model["rows"] and all(r["status"] == "ungoverned" for r in model["rows"])
    assert any("ungoverned" in d.lower() for d in model["disclosures"])

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", hold_event_log=True)
    model = _model(data_dir, now=NOW)
    held = [r for r in model["rows"] if r["status"] == "held"]
    assert held and all(r["disposal_date"] is None for r in held)
    assert all(r["data_class"] == "evidence:event_log" for r in held)

    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", run_end=True)
    model = _model(data_dir, now=NOW)
    rows = {r["id"]: r for r in model["rows"]}
    unresolved = [r for r in rows.values() if r["status"] == "anchor_unresolved"]
    assert unresolved and all(r["disposal_date"] is None for r in unresolved)
    # run-c is live (non-terminal) under run_end; manual-labbook is unattributed
    assert any(r["context_key"] == "manual-labbook" for r in unresolved)




def test_s3_8_scheduled_has_a_date(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json", run_end=True)
    model = _model(data_dir, now=NOW)
    rows = {r["id"]: r for r in model["rows"]}
    # run-a/run-b are terminal -> their run_end anchors resolve to run_states T2
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
    data_dir = _seed(tmp_path)
    _write_policy(data_dir / "retention-policy.json")
    model = _model(data_dir, now=NOW, max_dataset_bytes=10_000)
    g = model["growth"]
    subs = g["subscriptions"]
    assert subs, "subscription lane must have rows"
    alpha = next(s for s in subs if s["subscription_id"] == "sub-alpha")
    assert alpha["n"] == 3 and alpha["span_s"] == pytest.approx(100.0)
    assert alpha["rate_bytes_per_s"] > 0
    assert alpha["duty"] == pytest.approx(100.0 / g["report_window_s"])
    # sub-beta landed a single event -> zero-span, excluded and disclosed
    assert {s["subscription_id"] for s in subs} == {"sub-alpha"}
    assert g["zero_span_excluded"] >= 1
    caps = g["captures"]
    assert {c["context_key"] for c in caps} == {"run:run-a", "run:run-b"}


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
