"""The retained-evidence generators' contracts (WP09 Tasks 7 and 11).

A 3-run smoke over the REAL volume generator — one ephemeral simulation
gateway (the ``benchweave.cli.demo`` fresh-install idiom, booted
in-process) driving three consecutive seeded journey runs — pinning the
summary accounting, the per-run record shape, and the seed derivation.
The per-run consistency gate (outcome, durable record, digest resolution,
dispatch oracle) lives in the generator and aborts loudly; if it ever
fires here the test fails with its truthful message, never a fabricated
summary.

The Task-11 additions pin the two new surfaces without re-running the
acceptance suite: the fault-matrix junit transform (the harvest's pure
projection from a ``--junitxml`` report to lean per-leg rows carrying the
MEASURED values the leg test records via ``record_property`` — never the
expectation tables restated) and the digest index (every artifact listed
with an independently recomputed sha256, the generated/record class
rules, refusal for unclassified strays, and byte-identical regeneration
over an unchanged tree).
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from benchweave.cli.evidence import (
    EvidenceError,
    fault_legs_from_junit,
    generate_index,
    generate_runs,
    scrub_junit_hostname,
)

#: The per-run record's complete key set (lean by contract: ids, digests,
#: outcome, timings — full logs never ride a record).
_RECORD_KEYS = frozenset(
    {
        "index",
        "seed",
        "request_id",
        "run_id",
        "bench_id",
        "state",
        "outcome",
        "safe_state",
        "terminal_sha256",
        "binding_sha256",
        "events_digest",
        "dispatch_occurrences",
        "started_at",
        "duration_s",
    }
)


def test_generate_runs_three_run_smoke(tmp_path: Path) -> None:
    summary = generate_runs(tmp_path, count=3, seed=20260914)

    # Summary accounting (the Step-1 contract).
    assert summary["count"] == 3
    assert summary["outcomes"] == ["passed", "passed", "passed"]
    assert summary["duplicate_dispatch_total"] == 0
    assert summary["seed"] == 20260914
    assert summary["host"], "the host disclosure is non-empty"
    assert summary["simulation"] is True

    # A healthy body dispatches eight device operations (the journey
    # suite's occurrence oracle: configure, enable, note, model, measure,
    # remeasure x3) — three runs, none duplicated.
    assert summary["dispatch_occurrences_total"] == 24

    # The retained evidence tree: one lean record per run + the summary.
    runs_dir = tmp_path / "runs"
    assert sorted(path.name for path in runs_dir.glob("run-*.json")) == [
        "run-001.json",
        "run-002.json",
        "run-003.json",
    ]
    summary_file = runs_dir / "summary.json"
    persisted = json.loads(summary_file.read_text(encoding="utf-8"))
    assert persisted["count"] == 3
    assert persisted["outcomes"] == ["passed", "passed", "passed"]
    assert persisted["duplicate_dispatch_total"] == 0

    first = json.loads((runs_dir / "run-001.json").read_text(encoding="utf-8"))
    assert set(first) == set(_RECORD_KEYS)
    assert first["index"] == 1
    assert first["seed"] == 20260915  # seed + N, per-run derivation
    assert first["request_id"] == "req-volume-20260915"
    assert first["state"] == "terminal"
    assert first["outcome"] == "passed"
    assert first["safe_state"] == "verified"
    assert len(first["terminal_sha256"]) == 64
    assert len(first["binding_sha256"]) == 64
    assert len(first["events_digest"]) == 64
    assert first["dispatch_occurrences"] == 8
    assert first["duration_s"] >= 0.0
    assert first["started_at"].endswith("Z")

    # Consecutive runs are distinct journeys: distinct seeds, requests, runs.
    third = json.loads((runs_dir / "run-003.json").read_text(encoding="utf-8"))
    assert third["seed"] == 20260917
    assert third["request_id"] == "req-volume-20260917"
    assert third["run_id"] != first["run_id"]


# --- the fault-matrix junit transform (WP09 Task 11, Step 1) ----------------------


def _junit_case(
    name: str, *, verdict: str, properties: dict[str, str], seconds: str
) -> ET.Element:
    """One synthetic junit ``<testcase>`` shaped like the harvest's input."""
    case = ET.Element(
        "testcase",
        {
            "classname": "tests.integration.test_poc_acceptance",
            "name": name,
            "time": seconds,
        },
    )
    if properties:
        props = ET.SubElement(case, "properties")
        for key, value in properties.items():
            ET.SubElement(props, "property", {"name": key, "value": value})
    if verdict != "passed":
        ET.SubElement(case, "failure" if verdict == "failed" else verdict)
    return case


def _junit_bytes(*cases: ET.Element) -> bytes:
    suite = ET.Element("testsuite", {"name": "integration", "tests": str(len(cases))})
    for case in cases:
        suite.append(case)
    return ET.tostring(suite, encoding="unicode").encode()


def test_fault_legs_from_junit_projects_verdicts_and_measured_values() -> None:
    """The transform is a pure projection: leg rows carry the junit verdict,
    the leg's measured outcome, expected-vs-actual occurrences and the
    testcase duration — properties first, non-leg cases ignored."""
    legs = fault_legs_from_junit(
        _junit_bytes(
            _junit_case(
                "test_journey_fault_legs[trip]",
                verdict="passed",
                properties={
                    "actual_outcome": "outcome_unknown",
                    "expected_outcomes": "outcome_unknown",
                    "occurrences_expected": "2",
                    "occurrences_actual": "2",
                },
                seconds="1.034",
            ),
            _junit_case(
                "test_journey_fault_legs[stale_sample]",
                verdict="failed",
                properties={
                    # The wrong outcome on purpose — the leg failed its pin.
                    "actual_outcome": "passed",
                    "expected_outcomes": "execution_error",
                    "occurrences_expected": "5",
                    "occurrences_actual": "8",
                },
                seconds="0.877",
            ),
            # Not a fault-leg case — the transform must ignore it entirely.
            _junit_case(
                "test_journey_discover_admit_select",
                verdict="passed",
                properties={},
                seconds="0.1",
            ),
        )
    )

    assert [leg["name"] for leg in legs] == ["stale_sample", "trip"]  # sorted by name
    trip = legs[1]
    assert trip["verdict"] == "passed"
    assert trip["outcome"] == "outcome_unknown"
    assert trip["expected_outcomes"] == ["outcome_unknown"]
    assert trip["occurrences"] == {"expected": 2, "actual": 2}
    assert trip["duration_s"] == 1.034
    stale = legs[0]
    assert stale["verdict"] == "failed"
    assert stale["occurrences"] == {"expected": 5, "actual": 8}


def test_fault_legs_from_junit_requires_the_recorded_properties() -> None:
    """A leg row without the measured properties is a wiring break, not a
    leg to guess about — the transform refuses loudly."""
    xml = _junit_bytes(
        _junit_case(
            "test_journey_fault_legs[trip]", verdict="passed", properties={}, seconds="1.0"
        )
    )
    with pytest.raises(EvidenceError, match="occurrences_expected"):
        fault_legs_from_junit(xml)


def test_fault_legs_from_junit_refuses_a_report_with_no_legs() -> None:
    xml = _junit_bytes(
        _junit_case(
            "test_journey_discover_admit_select",
            verdict="passed",
            properties={},
            seconds="0.1",
        )
    )
    with pytest.raises(EvidenceError, match="no test_journey_fault_legs"):
        fault_legs_from_junit(xml)


def test_fault_legs_from_junit_refuses_malformed_xml() -> None:
    """A truncated scratch report is a harvest failure with a named
    message — never an ``xml.etree`` traceback through the CLI."""
    with pytest.raises(EvidenceError, match="not well-formed"):
        fault_legs_from_junit(b"<testsuite><testcase name=")


def test_scrub_junit_hostname_replaces_every_machine_name() -> None:
    """Retention scrub: every ``hostname="..."`` value becomes the fixed
    ``reference-host`` label and every other byte passes through — the
    retained junit carries reproduction context, never a machine name
    (the same doctrine the summaries' host disclosure follows)."""
    report = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b'<testsuites><testsuite name="a" hostname="MacBookPro.lovegroove.io" '
        b'tests="1">'
        b'<testcase classname="c" name="test_journey_fault_legs[trip]" '
        b'time="1.0"/>'
        b'</testsuite>'
        b'<testsuite name="b" hostname="MacBookPro.lovegroove.io" tests="0"/>'
        b'</testsuites>'
    )

    scrubbed = scrub_junit_hostname(report)

    assert scrubbed == report.replace(
        b'hostname="MacBookPro.lovegroove.io"', b'hostname="reference-host"'
    )
    assert b"lovegroove" not in scrubbed
    assert scrubbed.count(b'hostname="reference-host"') == 2


def test_scrub_junit_hostname_passes_a_hostless_report_through() -> None:
    report = b'<testsuite name="a" tests="1"><testcase name="t"/></testsuite>'
    assert scrub_junit_hostname(report) == report


# --- the digest index (WP09 Task 11, Step 1) -------------------------------------


#: The classified evidence classes (three generated roots, two record
#: roots) with representative artifacts — the index's whole classification
#: surface under test.
_INDEX_TREE: dict[str, str] = {
    "runs/run-001.json": "generated",
    "runs/summary.json": "generated",
    "timing/prd-load.json": "generated",
    "timing/stress-16.json": "generated",
    "fault-matrix/legs.json": "generated",
    "fault-matrix/junit.xml": "generated",
    "timed-demos/leg-1-clean-demo.md": "record",
    "decisions/d13-async-posture.md": "record",
}


def _seed_index_tree(root: Path) -> None:
    for relative in _INDEX_TREE:
        artifact = root / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(f"evidence bytes: {relative}\n".encode())
    # A stale prior index must be excluded — the index cannot digest itself.
    (root / "index.md").write_bytes(b"# stale prior index\n")


def _index_rows(index_md: str) -> dict[str, list[str]]:
    """The index table rows: artifact path -> [artifact, class, sha256, cell]."""
    rows: dict[str, list[str]] = {}
    for line in index_md.splitlines():
        if line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows[cells[0].strip("`")] = cells
    return rows


def test_generate_index_lists_every_artifact_with_digest_and_class(tmp_path: Path) -> None:
    _seed_index_tree(tmp_path)

    payload = generate_index(tmp_path)

    assert payload["artifacts"] == len(_INDEX_TREE)
    assert payload["generated"] == 6
    assert payload["record"] == 2
    rows = _index_rows((tmp_path / "index.md").read_text(encoding="utf-8"))
    assert set(rows) == set(_INDEX_TREE)  # every file listed, nothing else
    for relative, evidence_class in _INDEX_TREE.items():
        digest = hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()
        cells = rows[relative]
        assert cells[1] == evidence_class
        assert cells[2].strip("`") == digest  # an independent sha256 over the bytes
        if evidence_class == "generated":
            assert cells[3].strip("`").startswith("benchweave evidence ")
            if relative.startswith("fault-matrix/"):
                # The default --tests node id is repo-relative — the row
                # discloses the repo-root regeneration precondition.
                assert "repository root" in cells[3]
            else:
                assert "repository root" not in cells[3]
        else:
            assert "digest-bound" in cells[3]


def test_generate_index_is_deterministic_over_an_unchanged_tree(tmp_path: Path) -> None:
    _seed_index_tree(tmp_path)
    generate_index(tmp_path)
    first = (tmp_path / "index.md").read_bytes()

    generate_index(tmp_path)

    assert (tmp_path / "index.md").read_bytes() == first


def test_generate_index_refuses_an_unclassified_artifact(tmp_path: Path) -> None:
    stray = tmp_path / "notes" / "stray.md"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"not a classified evidence class\n")
    with pytest.raises(EvidenceError, match="notes"):
        generate_index(tmp_path)


def test_generate_index_skips_dotfiles(tmp_path: Path) -> None:
    """Operator-local dotfiles (macOS ``.DS_Store``, editor droppings) are
    noise, not evidence: skipped wherever they sit — a root dotfile never
    trips the unclassified-artifact refusal and a nested one is never
    indexed."""
    _seed_index_tree(tmp_path)
    (tmp_path / ".DS_Store").write_bytes(b"finder metadata\n")
    (tmp_path / "runs" / ".DS_Store").write_bytes(b"finder metadata\n")

    payload = generate_index(tmp_path)

    assert payload["artifacts"] == len(_INDEX_TREE)
    rows = _index_rows((tmp_path / "index.md").read_text(encoding="utf-8"))
    assert set(rows) == set(_INDEX_TREE)  # neither dotfile indexed
