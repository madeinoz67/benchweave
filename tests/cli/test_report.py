"""Task 13: the report MODEL, its emitters, and the ``report`` command.

The model is pure and store-derived — every field reads the store at rest
(never an in-memory claim), ``generated_at`` comes from the caller's
injected clock, and evidence presence is computed against the content
store. The truth bar (ISC-14): a deliberately-deleted artifact lands in
``missing_evidence`` AND ``present: false`` — missing evidence is NAMED,
never papered over. Markdown carries every digest and the SIMULATION
labels; ``--json`` round-trips the model exactly.

Covered groups:

- ``build_report`` populates every model field from a seeded store
  (bench inventory with busy/generation, runs with state/outcome/principal,
  evidence with digests, the simulation labels, ``generated_at`` from the
  injected clock).
- The deleted-artifact truth bar: ``present: false`` + a named
  ``missing_evidence`` entry; markdown names it too.
- Emitters: markdown carries every digest and every SIMULATION label;
  JSON round-trips the model exactly.
- The command: markdown default / ``--json`` machine form / ``--out FILE``
  for both; the daemon-hold refusal (at-rest discipline); the documented
  ``--gateway`` stub; unknown bench and missing store refuse truthfully.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from benchweave.cli.atrest import db_path, setup
from benchweave.cli.commands import cli
from benchweave.content.store import ContentStore
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.state.hold import StoreHold
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
NOW = "2026-09-14T00:00:00Z"
BENCH = "sim-bench"  # the fixture lattice's bench (bootstrap-derived, not a label source)
RUN = "run-1"
PRINCIPAL = "benchweave-demo"

_BLOB_OK = b'{"voltage_v": 3.3}'
_BLOB_GONE = b'{"voltage_v": 12.0}'


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _combined(result: Result) -> str:
    """stdout + stderr, robust to click < 8.2's mixed-stream Result."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _seed(tmp_path: Path) -> Path:
    """A data dir whose store carries one simulated bench, one terminal
    run, and two artifact-backed evidence rows — one of whose artifacts is
    deliberately deleted (the truth-bar fixture)."""
    data_dir = tmp_path / "data"
    setup(data_dir)
    store = Store.open(db_path(data_dir))
    try:
        content = ContentStore(store)
        admit_startup_bench(store, content, FIXTURES, now=NOW)
        store.create_run(RUN, {"procedure_id": "voltage-check"}, PRINCIPAL, NOW)
        store.put_run_state(RUN, BENCH, "terminal", NOW)
        store.finalize_run(
            RUN,
            {
                "run_id": RUN,
                "contract_version": "1.0.0",
                "outcome": "passed",
                "safe_state": "safe",
                "reasons": [],
                "evidence_refs": [],
            },
        )
        art_ok = content.put_artifact(_BLOB_OK, NOW)
        art_gone = content.put_artifact(_BLOB_GONE, NOW)
        content.put_evidence(
            "dataset",
            {"id": f"run:{RUN}", "version": "1", "sha256": _sha(_BLOB_OK)},
            art_ok,
            f"run:{RUN}",
            NOW,
        )
        content.put_evidence(
            "dataset",
            {"id": f"run:{RUN}", "version": "1", "sha256": _sha(_BLOB_GONE)},
            art_gone,
            f"run:{RUN}",
            NOW,
        )
        # The deliberate deletion: the artifact row vanishes, the evidence
        # row pointing at it stays — the report must name it.
        store.connection.execute(
            "DELETE FROM artifacts WHERE artifact_id = ?", (art_gone,)
        )
    finally:
        store.close()
    return data_dir


def _model(tmp_path: Path) -> dict[str, Any]:
    from benchweave.cli.report import build_report

    data_dir = _seed(tmp_path)
    store = Store.open(db_path(data_dir))
    try:
        return build_report(store, ContentStore(store), now=NOW)
    finally:
        store.close()


# --- the model -------------------------------------------------------------------


def test_build_report_populates_every_field(tmp_path: Path) -> None:
    report = _model(tmp_path)
    assert report["generated_at"] == NOW
    benches = report["benches"]
    assert [b["id"] for b in benches] == [BENCH]
    assert benches[0]["busy"] is False
    assert benches[0]["generation"] == 1
    runs = report["runs"]
    assert [r["id"] for r in runs] == [RUN]
    assert runs[0]["bench"] == BENCH
    assert runs[0]["state"] == "terminal"
    assert runs[0]["outcome"] == "passed"
    assert runs[0]["principal"] == PRINCIPAL
    kinds = [e["kind"] for e in report["evidence"]]
    assert kinds == ["dataset", "dataset"]
    assert report["simulation"] is True


def test_simulation_label_is_on_every_simulated_bench_and_run(tmp_path: Path) -> None:
    report = _model(tmp_path)
    assert report["benches"][0]["simulation"] is True
    assert report["runs"][0]["simulation"] is True


def test_deleted_artifact_is_present_false_and_named_missing(tmp_path: Path) -> None:
    report = _model(tmp_path)
    by_digest = {e["digest"]: e for e in report["evidence"]}
    ok, gone = by_digest[_sha(_BLOB_OK)], by_digest[_sha(_BLOB_GONE)]
    assert ok["present"] is True
    assert gone["present"] is False
    missing = report["missing_evidence"]
    assert len(missing) == 1
    entry = missing[0]
    assert entry["digest"] == _sha(_BLOB_GONE)
    assert entry["evidence_id"] == gone["evidence_id"]
    assert entry["kind"] == "dataset"


def test_generated_at_comes_from_the_injected_clock(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    from benchweave.cli.report import build_report

    store = Store.open(db_path(data_dir))
    try:
        first = build_report(store, ContentStore(store), now="2020-01-01T00:00:00Z")
        second = build_report(store, ContentStore(store), now="2030-01-01T00:00:00Z")
    finally:
        store.close()
    assert first["generated_at"] == "2020-01-01T00:00:00Z"
    assert second["generated_at"] == "2030-01-01T00:00:00Z"


def test_busy_derives_from_live_runs(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    store = Store.open(db_path(data_dir))
    try:
        # A second, still-live run makes the bench busy (the §5/D9 oracle:
        # a run owns its bench from acceptance until terminal).
        store.create_run("run-2", {"procedure_id": "voltage-check"}, PRINCIPAL, NOW)
        store.put_run_state("run-2", BENCH, "running", NOW)
        from benchweave.cli.report import build_report

        report = build_report(store, ContentStore(store), now=NOW)
    finally:
        store.close()
    assert report["benches"][0]["busy"] is True
    assert {r["state"] for r in report["runs"]} == {"terminal", "running"}
    # A running run has no outcome yet — honest null, never fabricated.
    running = next(r for r in report["runs"] if r["id"] == "run-2")
    assert running["outcome"] is None


def test_bench_filter_scopes_the_report(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    from benchweave.cli.report import build_report

    store = Store.open(db_path(data_dir))
    try:
        scoped = build_report(store, ContentStore(store), bench_id=BENCH, now=NOW)
    finally:
        store.close()
    assert [b["id"] for b in scoped["benches"]] == [BENCH]
    assert {r["bench"] for r in scoped["runs"]} == {BENCH}


def test_unknown_bench_refuses_truthfully(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    from benchweave.cli.report import build_report

    store = Store.open(db_path(data_dir))
    try:
        with pytest.raises(ValueError, match="no bench"):
            build_report(store, ContentStore(store), bench_id="no-such-bench", now=NOW)
    finally:
        store.close()


# --- the emitters ------------------------------------------------------------------


def test_markdown_carries_every_digest_and_simulation_labels(tmp_path: Path) -> None:
    from benchweave.cli.report import render_markdown

    report = _model(tmp_path)
    text = render_markdown(report)
    assert _sha(_BLOB_OK) in text and _sha(_BLOB_GONE) in text
    assert "SIMULATION" in text  # the banner
    bench_lines = [ln for ln in text.splitlines() if BENCH in ln]
    assert any("SIMULATION" in ln for ln in bench_lines)
    run_lines = [ln for ln in text.splitlines() if RUN in ln]
    assert any("SIMULATION" in ln for ln in run_lines)
    missing_section = text.split("## Missing evidence", 1)[1]
    assert _sha(_BLOB_GONE) in missing_section
    assert _sha(_BLOB_OK) not in missing_section


def test_json_round_trips_the_model_exactly(tmp_path: Path) -> None:
    from benchweave.cli.report import render_json

    report = _model(tmp_path)
    assert json.loads(render_json(report)) == report


# --- the command --------------------------------------------------------------------


def test_cli_report_defaults_to_markdown_on_stdout(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    result = CliRunner().invoke(cli, ["report", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, _combined(result)
    assert _sha(_BLOB_OK) in result.output and _sha(_BLOB_GONE) in result.output
    assert "SIMULATION" in result.output


def test_cli_report_json_matches_the_model(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    result = CliRunner().invoke(cli, ["report", "--data-dir", str(data_dir), "--json"])
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.output)
    store = Store.open(db_path(data_dir))
    try:
        from benchweave.cli.report import build_report

        reference = build_report(store, ContentStore(store), now=NOW)
    finally:
        store.close()
    for key in ("simulation", "benches", "runs", "evidence", "missing_evidence"):
        assert payload[key] == reference[key]
    assert payload["generated_at"]


def test_cli_report_out_writes_both_forms(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    md = tmp_path / "report.md"
    js = tmp_path / "report.json"
    result = CliRunner().invoke(
        cli, ["report", "--data-dir", str(data_dir), "--out", str(md)]
    )
    assert result.exit_code == 0, _combined(result)
    text = md.read_text(encoding="utf-8")
    assert _sha(_BLOB_OK) in text and "SIMULATION" in text
    result = CliRunner().invoke(
        cli,
        ["report", "--data-dir", str(data_dir), "--out", str(js), "--json"],
    )
    assert result.exit_code == 0, _combined(result)
    assert json.loads(js.read_text(encoding="utf-8"))["simulation"] is True


def test_cli_report_refuses_under_daemon_hold(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    with StoreHold(db_path(data_dir), label="live gateway pid 1"):
        result = CliRunner().invoke(cli, ["report", "--data-dir", str(data_dir)])
    assert result.exit_code != 0
    assert "held" in _combined(result)


def test_cli_report_gateway_is_a_documented_stub(tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    result = CliRunner().invoke(
        cli, ["report", "--data-dir", str(data_dir), "--gateway", "http://127.0.0.1:8123"]
    )
    assert result.exit_code != 0
    assert "not implemented" in _combined(result)


def test_cli_report_refuses_without_a_store(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(cli, ["report", "--data-dir", str(empty)])
    assert result.exit_code != 0
    assert "no store" in _combined(result)
