"""Execute the versioned architecture checks without modifying the document baseline."""

import hashlib
import json
import re
import runpy
import shutil
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUITES = ("devices", "registry", "execution", "interface", "closure", "planning", "documents")


def _active_report_path() -> str:
    """The active report's path, derived from the manifest (#102 D2) — the
    pin follows the manifest's active otdp version, never a literal.

    First-match on the otdp entry: CON-8 keeps the manifest single-row per
    standard, so first == active while the manifest is well-formed.
    """

    manifest = json.loads(
        (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
    )
    entry = next(item for item in manifest["standards"] if item["id"] == "otdp")
    version = entry["version"]
    assert isinstance(version, str) and version
    return f"otdp/{version}/validation-report.md"


REPORT_PATH = _active_report_path()
REPORT_REGEN = "uv run python scripts/architecture/check_devices.py --write-report"


def load_suite(suite: str, docs: Path, standards: Path) -> dict[str, Any]:
    """Execute a validator script's module body and return its namespace."""
    script = ROOT / "scripts" / "architecture" / f"check_{suite}.py"
    assert script.is_file(), f"Missing architecture validator: {script}"
    return runpy.run_path(str(script), init_globals={"DOCS": docs, "STANDARDS": standards})


def run_checks(suite: str, docs: Path, standards: Path) -> list[tuple[str, bool]]:
    checks = load_suite(suite, docs, standards)["CHECKS"]
    assert isinstance(checks, list) and checks, f"No checks executed by {suite}"
    return [(str(name), bool(passed)) for name, passed in checks]


@pytest.mark.parametrize("suite", SUITES)
def test_architecture(suite: str) -> None:
    checks = run_checks(suite, ROOT / "docs", ROOT / "standards")
    failures = [name for name, passed in checks if not passed]
    assert not failures, f"{suite}: {len(failures)}/{len(checks)} failed:\n" + "\n".join(failures)
    print(f"{suite}: {len(checks)} checks passed")


def report_failures(docs: Path, standards: Path) -> list[str]:
    """``[]`` when the committed OTDP report equals a fresh render; else one failure.

    The committed active report (``REPORT_PATH``, manifest-derived) is machine-written
    by its validator; this is the staleness gate the ``gates`` job runs. Byte
    equality is over the sorted rendering, so it is a function of the check set
    only, immune to platform glob order.
    """
    namespace = load_suite("devices", docs, standards)
    assert "render_report" in namespace, (
        "check_devices.py lacks render_report — the validation-report pin needs the writer"
    )
    checks = namespace["CHECKS"]
    assert isinstance(checks, list) and checks, "No checks executed by devices"
    committed = standards / REPORT_PATH
    if not committed.is_file():
        return [f"stale_report: {REPORT_PATH} absent; run {REPORT_REGEN}"]
    rendered = namespace["render_report"]([(str(name), bool(passed)) for name, passed in checks])
    if committed.read_text(encoding="utf-8") != rendered:
        return [
            f"stale_report: {REPORT_PATH} differs from a live devices-suite render; "
            f"run {REPORT_REGEN}"
        ]
    return []


def test_validation_report_matches_live_run() -> None:
    assert report_failures(ROOT / "docs", ROOT / "standards") == []
    report = (ROOT / "standards" / REPORT_PATH).read_text(encoding="utf-8")
    headline = re.search(r"(\d+)/\d+ checks passed", report)
    assert headline is not None, f"{REPORT_PATH} lacks a headline count"
    passed = int(headline.group(1))
    rows = [
        line for line in (ROOT / "docs" / "README.md").read_text(encoding="utf-8").splitlines()
        if f"(../standards/{REPORT_PATH})" in line
    ]
    assert len(rows) == 1, f"docs/README.md must link {REPORT_PATH} exactly once"
    # The href itself carries the active version's digits, so the count is the
    # first integer after the link, not the first integer in the row.
    row_count = re.search(r"\d+", rows[0].split(")", 1)[1])
    assert row_count is not None, "docs/README.md row carries no count"
    assert int(row_count.group()) == passed, (
        f"docs/README.md says {row_count.group()}; {REPORT_PATH} pins {passed}"
    )


@pytest.mark.parametrize("mode", ["flip_pass", "bump_count", "reorder_lines"])
def test_validation_report_tampering_is_detected(tmp_path: Path, mode: str) -> None:
    docs = tmp_path / "docs"
    standards = tmp_path / "standards"
    shutil.copytree(ROOT / "docs", docs)
    shutil.copytree(ROOT / "standards", standards)
    report = standards / REPORT_PATH
    original = report.read_text(encoding="utf-8")
    if mode == "flip_pass":
        assert "- PASS: " in original, "report must carry PASS lines to tamper with"
        mutated = original.replace("- PASS: ", "- FAIL: ", 1)
    elif mode == "reorder_lines":
        # The platform-drift case the sorted renderer exists for: an unsorted
        # check list is a permutation the live (sorted) render can never match.
        lines = original.splitlines(keepends=True)
        passes = [i for i, line in enumerate(lines) if line.startswith("- PASS: ")]
        assert len(passes) >= 2, "report must carry PASS lines to reorder"
        lines[passes[0]], lines[passes[-1]] = lines[passes[-1]], lines[passes[0]]
        mutated = "".join(lines)
        assert mutated != original, "reorder mutation must change the report"
    else:
        mutated = re.sub(
            r"(\d+)/(\d+)",
            lambda match: f"{int(match.group(1)) + 1}/{match.group(2)}",
            original,
            count=1,
        )
        assert mutated != original, "headline-count mutation must change the report"
    report.write_text(mutated, encoding="utf-8", newline="\n")
    failures = report_failures(docs, standards)
    assert any(
        REPORT_PATH in failure and REPORT_REGEN in failure for failure in failures
    ), failures


def test_validation_is_read_only(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    standards = tmp_path / "standards"
    shutil.copytree(ROOT / "docs", docs)
    shutil.copytree(ROOT / "standards", standards)

    def snapshot(root: Path) -> dict[str, str]:
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    before_docs = snapshot(docs)
    before_standards = snapshot(standards)
    for suite in SUITES:
        run_checks(suite, docs, standards)
    assert snapshot(docs) == before_docs, "Validation changed the architecture documents"
    assert snapshot(standards) == before_standards, "Validation changed the corpus"


def test_pinned_checks_pass_through_symlinked_standards_alias(tmp_path: Path) -> None:
    """The pinned check must survive an unresolved STANDARDS root (#119).

    On macOS, raw TMPDIR (``/var/folders/…``) sits under the ``/var`` →
    ``/private/var`` symlink: with an unresolved ``STANDARDS`` root the pinned
    check compared ``.resolve()``d contract paths against an unresolved
    ``OUT`` and every pinned check failed vacuously on a clean tree. (pytest's
    own ``tmp_path`` is pre-resolved, which is why the pytest arms never saw
    this — anything anchored at raw TMPDIR did.) ``OUT`` is now resolved once
    at derivation, so the comparison is resolved-to-resolved; a symlinked
    alias of the real tree is the portable way to demand that on any platform.
    """
    docs = tmp_path / "docs"
    standards = tmp_path / "standards"
    shutil.copytree(ROOT / "docs", docs)
    shutil.copytree(ROOT / "standards", standards)
    alias = tmp_path / "standards-alias"
    alias.symlink_to(standards, target_is_directory=True)
    failures = [name for name, passed in run_checks("devices", docs, alias) if not passed]
    assert failures == [], f"symlinked clean tree must run clean: {len(failures)} failed:\n" + (
        "\n".join(failures)
    )


def test_documents_ignores_markdown_links_inside_fenced_code_blocks(
    tmp_path: Path,
) -> None:
    """A subscript-call expression in a fenced block (``legs[leg](arg)``) is
    code, not a ``](destination)`` link — planning docs may carry such code,
    and the checker must not demand a file for it. Prose links stay checked.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    standards = tmp_path / "standards"
    standards.mkdir()
    (docs / "fences.md").write_text(
        "# Fences\n\nProse [link](other.md) stays checked.\n\n"
        "```python\nresult = legs[leg](arg)\n```\n",
        encoding="utf-8",
    )
    (docs / "other.md").write_text("# Other\n", encoding="utf-8")
    failures = [name for name, passed in run_checks("documents", docs, standards) if not passed]
    assert failures == []


@pytest.mark.parametrize(
    ("suite", "relative_path", "old", "new", "expected"),
    [
        # The devices rows mutate the ACTIVE version's files (path derived
        # below via the manifest, #102 D2) — a hardcoded prior version would
        # mutate a retained tree nothing reads, record zero failures, and
        # break this assertion hint-free on the CI lane (ubuntu). Vacuous
        # pinned failures on tmp trees were a raw-TMPDIR (/var-anchored)
        # harness wound, fixed by resolving OUT once (#119) and pinned by
        # the symlinked-alias test; pytest's tmp_path is pre-resolved, so
        # these arms always saw real mutation failures. The second row's
        # byte pattern must exist in the active derivation-vectors.json; a
        # corpus edit that removes it moves this pattern with it (ordinary
        # corpus obligation).
        (
            "devices",
            _active_report_path().rsplit("/", 1)[0]
            + "/otdp-measurement.schema.json",
            "",
            "\n",
            "pinned",
        ),
        (
            "devices",
            _active_report_path().rsplit("/", 1)[0]
            + "/examples/derivation-vectors.json",
            '"values": [\n            9.0\n          ]',
            '"values": [\n            9.1\n          ]',
            "census",
        ),
        (
            "registry",
            "registry/0.1.1/examples/release-manifest.json",
            '"version": "1.0.0"',
            '"version": "latest"',
            "positive fixture",
        ),
        (
            "execution",
            "execution/0.1.0/examples/run-record.json",
            '"safe_state": "verified"',
            '"safe_state": "unknown"',
            "positive fixture",
        ),
        (
            "interface",
            "interface/0.1.0/examples/operation-vectors.json",
            '"ok": true',
            '"ok": false',
            "Stored fixture agrees",
        ),
        (
            "closure",
            "acceptance/composition-fixtures.json",
            '"digest": "a"',
            '"digest": "changed"',
            "Stored fixture agrees",
        ),
        (
            "planning",
            "implementation-planning/requirements-trace.json",
            '"WP01"',
            '"WP99"',
            "Stored fixture agrees",
        ),
        ("documents", "project-index.md", "", "\n[Broken](missing.md)\n", "local link"),
        (
            "documents",
            "interface/0.1.0/interface.schema.json",
            '"$ref": "#/$defs/',
            '"$ref": "#/$defs/missing-',
            "resolves",
        ),
    ],
)
def test_contract_regressions_are_detected(
    tmp_path: Path, suite: str, relative_path: str, old: str, new: str, expected: str
) -> None:
    docs = tmp_path / "docs"
    standards = tmp_path / "standards"
    shutil.copytree(ROOT / "docs", docs)
    shutil.copytree(ROOT / "standards", standards)
    path = (
        standards / relative_path
        if (standards / relative_path).is_file()
        else docs / relative_path
    )
    original = path.read_text(encoding="utf-8")
    assert not old or old in original, "Mutation must change the intended fixture"
    changed = original.replace(old, new, 1) if old else original + new
    path.write_text(changed, encoding="utf-8")
    if path.suffix == ".json":
        json.loads(changed)  # Test semantic damage rather than invalid JSON syntax.
    failures = [name for name, passed in run_checks(suite, docs, standards) if not passed]
    assert any(expected in name for name in failures), failures
