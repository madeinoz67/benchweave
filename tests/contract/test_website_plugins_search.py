"""The catalogue search contract (issue #224 slice 2, CR-24/CR-25).

Lane 1 — the predicate proof. ``website/assets/plugins.js`` splits into a
pure predicate ``filterRows(rows, query)`` (data in, data out, no DOM)
and the DOM wiring; the predicate is evaluated against the hand-derived
truth table by ``tests/contract/run_search_spec.mjs`` (node) and driven
from this wrapper, which asserts node's presence and fails loudly when it
is missing — never skips, because a skip would be a silent hole and node
is preinstalled on the GitHub-hosted ubuntu runner (the standing
no-self-hosted-runners posture keeps that true).

The truth table (``tests/contract/fixtures/plugins-search.truth-table.json``)
and the 10-row fixture (``plugins-index.fixture.json``) are committed BEFORE
any search code — C1's discipline — and their internal consistency is pinned
here so a malformed table can never pass by vacuity. Dimension breadth is
this lane's job; the wiring proof on the assembled artifact is lane 2 (the
docs workflow's browser arm).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE = FIXTURES / "plugins-index.fixture.json"
TRUTH_TABLE = FIXTURES / "plugins-search.truth-table.json"
SEARCH_SPEC = Path(__file__).resolve().parent / "run_search_spec.mjs"
PLUGINS_JS = ROOT / "website" / "assets" / "plugins.js"

# The query keys filterRows understands. A case may carry any subset; an
# absent key means no filter on that dimension (the UI's initial state is
# the "default view" case — admitted releases with a valid signature).
QUERY_KEYS = {
    "text",
    "publisher",
    "capabilities",
    "standard_version",
    "signature_state",
    "maintenance",
    "advisories",
    "kind",
}
DIMENSIONS = {"name", "publisher", "capability", "standard_version", "status", "kind",
              "default", "negative", "combined"}


def _rows() -> list[dict[str, Any]]:
    return list(json.loads(FIXTURE.read_text(encoding="utf-8"))["rows"])


def _cases() -> list[dict[str, Any]]:
    return list(json.loads(TRUTH_TABLE.read_text(encoding="utf-8"))["cases"])


def test_truth_table_is_internally_consistent() -> None:
    """Every expected id exists in the fixture; cases are well-formed.

    The guard that makes the truth table's own claims falsifiable: a
    hand-derived expected set naming a package the fixture does not carry
    is a derivation error, and must fail here rather than quietly
    under-counting an arm.
    """
    known = {str(row["package_id"]) for row in _rows()}
    cases = _cases()
    assert cases, "the truth table carries no cases"
    seen_ids: set[str] = set()
    for case in cases:
        case_id = str(case["id"])
        assert case_id not in seen_ids, f"duplicate case id: {case_id}"
        seen_ids.add(case_id)
        assert case["dimension"] in DIMENSIONS, f"{case_id}: unknown dimension {case['dimension']}"
        query = dict(case["query"])
        unknown = sorted(set(query) - QUERY_KEYS)
        assert not unknown, f"{case_id}: unknown query key(s) {unknown}"
        expect = list(case["expect"])
        assert expect == sorted(set(expect)), f"{case_id}: expect must be sorted and unique"
        missing = sorted(set(expect) - known)
        assert not missing, f"{case_id}: expect names id(s) absent from the fixture: {missing}"


def test_truth_table_covers_every_dimension() -> None:
    """CR-24's dimensions are all exercised, plus the negative and combined arms."""
    covered = {str(case["dimension"]) for case in _cases()}
    for dimension in ("name", "publisher", "capability", "standard_version", "status", "kind"):
        assert dimension in covered, f"no truth-table case covers dimension: {dimension}"
    assert "negative" in covered, "the nonexistent-query arm is missing"
    assert "combined" in covered, "the combined-query arm is missing"
    negative = [c for c in _cases() if c["dimension"] == "negative"]
    assert all(list(c["expect"]) == [] for c in negative), "a negative arm must expect zero rows"


def test_fixture_carries_cr24s_denominator() -> None:
    """The 10-row fixture represents every dimension value the arms need.

    CR-24's own denominator: at least 10 rows with all dimensions
    represented — 3 publishers; kinds admitted-release ×7, community-shared
    ×2, in-tree-fixture ×1; signature signed ×8 / unsigned ×2; all four
    maintenance values; stg_versions {1.4, 1.5} and otdp_versions
    {0.2.1, 0.2.2}; all eight capability boolean combinations; advisories on
    at least two rows; and one publisher/name-prefix pair sharing a
    disambiguation boundary.
    """
    rows = _rows()
    assert len(rows) == 10, f"CR-24's fixture is 10 rows, got {len(rows)}"
    assert len({row["publisher"] for row in rows}) == 3
    kinds = [row["kind"] for row in rows]
    assert kinds.count("admitted-release") == 7
    assert kinds.count("community-shared") == 2
    assert kinds.count("in-tree-fixture") == 1
    signatures = [row["signature_state"] for row in rows]
    assert signatures.count("signed-valid") == 8
    assert signatures.count("unsigned") == 2
    assert {row["maintenance"] for row in rows} == {
        "maintained", "maintenance_only", "unmaintained", "unknown",
    }
    stg = {v for row in rows for v in row["compatibility"]["stg_versions"]}
    otdp = {v for row in rows for v in row["compatibility"]["otdp_versions"]}
    assert stg == {"1.4", "1.5"}, stg
    assert otdp == {"0.2.1", "0.2.2"}, otdp
    combos = {
        (
            row["capabilities"]["network_egress"],
            row["capabilities"]["subprocess_or_native_library"],
            row["capabilities"]["filesystem_writes_beyond_evidence_retention"],
        )
        for row in rows
    }
    assert len(combos) == 8, f"all eight capability combinations required, got {len(combos)}"
    assert sum(1 for row in rows if row["advisories"]) >= 2
    # the disambiguation pair: one publisher, one name prefix, two rows
    prefixes = [(row["publisher"], str(row["package_id"]).split("/")[1][:10]) for row in rows]
    assert len(set(prefixes)) < len(prefixes), "no publisher/name-prefix pair to disambiguate"


def test_node_is_present() -> None:
    """Fail loudly when node is absent — a skip would be a silent hole.

    The predicate proof runs on node (preinstalled on the ubuntu runner);
    this test is the harness gate, and B1's underpowered-discrimination
    clause says a harness failure is neither pass nor kill — it blocks.
    """
    found = shutil.which("node")
    assert found is not None, (
        "node is required for the search truth-table lane (tests/contract/"
        "run_search_spec.mjs) and is missing from PATH — the harness is "
        "broken, not the predicate"
    )
    result = subprocess.run([found, "--version"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_search_truth_table() -> None:
    """B1's search-truth arm, evaluated by the node spec over filterRows.

    Every dimension arm must return the exactly-correct filtered set for
    all 10 rows (the truth table is the authority, hand-derived before any
    search code). KILL: any wrong row in any dimension arm. On failure the
    node spec's own expected-vs-got lines are the evidence surface.
    """
    node = shutil.which("node")
    assert node is not None, "node missing — see test_node_is_present"
    result = subprocess.run(
        [node, str(SEARCH_SPEC)], capture_output=True, text=True, check=False, cwd=ROOT
    )
    assert result.returncode == 0, (
        "search truth-table mismatch (node spec output follows)\n" + result.stdout + result.stderr
    )
    assert "OK" in result.stdout, result.stdout


def test_pure_predicates_stay_dom_free() -> None:
    """The CommonJS guard export shape: requiring the file from node must not
    need a DOM and must expose the pure half. The wiring half is
    browser-only and silent under node (the typeof document guard)."""
    node = shutil.which("node")
    assert node is not None, "node missing — see test_node_is_present"
    script = (
        "const m = require(process.argv[1]);"
        "if (typeof m.filterRows !== 'function' || typeof m.rowSlots !== 'function') "
        "{ console.error('missing pure exports'); process.exit(1); }"
        "const rows = [{package_id: 'a/b', display_name: 'x', summary: '',"
        " kind: 'admitted-release', signature_state: 'signed-valid', publisher: 'p',"
        " maintenance: 'unknown', advisories: [],"
        " capabilities: {network_egress: false, subprocess_or_native_library: false,"
        " filesystem_writes_beyond_evidence_retention: false},"
        " compatibility: {stg_versions: [], otdp_versions: [], adapter_api_versions: []}}];"
        "const got = m.filterRows(rows, {text: 'nope'});"
        "if (!Array.isArray(got) || got.length !== 0) "
        "{ console.error('predicate needs a DOM'); process.exit(1); }"
        "const slots = m.rowSlots(rows[0]);"
        "if (slots.kind !== 'admitted-release') "
        "{ console.error('rowSlots kind projection broken'); process.exit(1); }"
        "console.log('OK');"
    )
    result = subprocess.run(
        [node, "-e", script, str(PLUGINS_JS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_yanked_release_is_unreachable_by_search() -> None:
    """B1's yank arm, search half (the mirrored consequence): a row the
    registry generator dropped from the index is not in the mirror the page
    fetches, so no query can reach it — search reflects the records of
    record (CR-25). The generator-side drop is the registry suite's arm."""
    mirror = json.loads((ROOT / "website" / "plugins-index.json").read_text(encoding="utf-8"))
    rows = mirror["rows"]
    assert rows, "the dogfooded release must seed the mirror"
    pid = str(rows[0]["package_id"])
    node = shutil.which("node")
    assert node is not None, "node missing — see test_node_is_present"
    script = (
        "const m = require(process.argv[1]);"
        "const fs = require('fs');"
        "const rows = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).rows;"
        "const before = m.filterRows(rows, {text: process.argv[3]});"
        "if (before.length === 0) "
        "{ console.error('precondition: the query reaches the row today'); process.exit(1); }"
        "const after = rows.filter((row) => row.package_id !== process.argv[3]);"
        "const got = m.filterRows(after, {text: process.argv[3]});"
        "if (got.length !== 0) "
        "{ console.error('a dropped row is still reachable'); process.exit(1); }"
        "console.log('OK');"
    )
    result = subprocess.run(
        [node, "-e", script, str(PLUGINS_JS), str(ROOT / "website" / "plugins-index.json"), pid],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
