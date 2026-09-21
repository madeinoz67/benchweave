"""Execute the versioned architecture checks without modifying the document baseline."""

import hashlib
import importlib.util
import json
import re
import runpy
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUITES = ("devices", "registry", "execution", "interface", "closure", "planning", "documents")


def _active_standard_dir(standard_id: str) -> str:
    """The active version dir for a standard, derived from the manifest.

    First-match on the standard's entry: CON-8 keeps the manifest single-row
    per standard, so first == active while the manifest is well-formed. The
    #102 D2 rule, generalized — pins follow the manifest's active version,
    never a literal.
    """

    manifest = json.loads(
        (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
    )
    entry = next(item for item in manifest["standards"] if item["id"] == standard_id)
    version = entry["version"]
    assert isinstance(version, str) and version
    return f"{standard_id}/{version}"


def _active_report_path(standard_id: str) -> str:
    return _active_standard_dir(standard_id) + "/validation-report.md"


def _standards_report_spec(suite: str, standard_id: str) -> tuple[str, str, str]:
    return (
        "standards",
        _active_report_path(standard_id),
        f"uv run python scripts/architecture/check_{suite}.py --write-report",
    )


# The machine-written validation-report family (#102 D1): suite → (report root
# kind, report path relative to that root, author-side regen command). The four
# standards suites derive their paths from the manifest's active versions;
# closure's report is the docs-side acceptance surface.
REPORT_SPECS: dict[str, tuple[str, str, str]] = {
    "devices": _standards_report_spec("devices", "otdp"),
    "registry": _standards_report_spec("registry", "registry"),
    "execution": _standards_report_spec("execution", "execution"),
    "interface": _standards_report_spec("interface", "interface"),
    "closure": (
        "docs",
        "acceptance/validation-report.md",
        "uv run python scripts/architecture/check_closure.py --write-report",
    ),
}
FAMILY_SUITES = tuple(REPORT_SPECS)
# README rows link the four standards-tree reports exactly once each; closure's
# docs-side report has no row and none is added.
README_ROW_SUITES = ("devices", "registry", "execution", "interface")


def load_suite(suite: str, docs: Path, standards: Path) -> dict[str, Any]:
    """Execute a validator script's module body and return its namespace."""
    script = ROOT / "scripts" / "architecture" / f"check_{suite}.py"
    assert script.is_file(), f"Missing architecture validator: {script}"
    return runpy.run_path(str(script), init_globals={"DOCS": docs, "STANDARDS": standards})


def run_checks(suite: str, docs: Path, standards: Path) -> list[tuple[str, bool]]:
    checks = load_suite(suite, docs, standards)["CHECKS"]
    assert isinstance(checks, list) and checks, f"No checks executed by {suite}"
    return [(str(name), bool(passed)) for name, passed in checks]


_REAL_TREE_NAMESPACES: dict[str, dict[str, Any]] = {}


def _real_tree_checks(suite: str) -> list[tuple[str, bool]]:
    checks = _real_tree_namespace(suite)["CHECKS"]
    assert isinstance(checks, list) and checks, f"No checks executed by {suite}"
    return [(str(name), bool(passed)) for name, passed in checks]


def _real_tree_namespace(suite: str) -> dict[str, Any]:
    """One real-tree execution per family suite, shared by its read-only
    consumers (the byte pin and the portability guard) — the designed cost
    model is one clean execution per suite, not one per test. The cached
    namespaces are only ever read (``CHECKS`` and the pure ``render_report``),
    so sharing cannot leak state between the consumers.
    """
    if suite not in _REAL_TREE_NAMESPACES:
        _REAL_TREE_NAMESPACES[suite] = load_suite(suite, ROOT / "docs", ROOT / "standards")
    return _REAL_TREE_NAMESPACES[suite]


def _load_shared_writer() -> Any:
    """Load ``scripts/architecture/_validation_report.py``, the family writer."""
    path = ROOT / "scripts" / "architecture" / "_validation_report.py"
    assert path.is_file(), f"Missing shared validation-report writer: {path}"
    spec = importlib.util.spec_from_file_location("_validation_report", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("suite", SUITES)
def test_architecture(suite: str) -> None:
    checks = run_checks(suite, ROOT / "docs", ROOT / "standards")
    failures = [name for name, passed in checks if not passed]
    assert not failures, f"{suite}: {len(failures)}/{len(checks)} failed:\n" + "\n".join(failures)
    print(f"{suite}: {len(checks)} checks passed")


def _report_root(root_kind: str, docs: Path, standards: Path) -> Path:
    return standards if root_kind == "standards" else docs


def _render_suite_report(suite: str, namespace: dict[str, Any]) -> str:
    assert "render_report" in namespace, (
        f"check_{suite}.py lacks render_report — the validation-report pin needs the writer"
    )
    checks = namespace["CHECKS"]
    assert isinstance(checks, list) and checks, f"No checks executed by {suite}"
    rendered = namespace["render_report"]([(str(name), bool(passed)) for name, passed in checks])
    assert isinstance(rendered, str), f"check_{suite}.py render_report must return str"
    return rendered


def _drift_failures(suite: str, docs: Path, standards: Path, rendered: str) -> list[str]:
    """``[]`` when the committed family report equals ``rendered``; else one failure.

    The pure byte-comparison half of the staleness gate, split out so the
    tamper arms can reuse one rendered snapshot across their three mutation
    modes. Byte equality is over the sorted rendering, so it is a function of
    the check set only, immune to platform glob order.
    """
    root_kind, relpath, regen = REPORT_SPECS[suite]
    committed = _report_root(root_kind, docs, standards) / relpath
    if not committed.is_file():
        return [f"stale_report: {relpath} absent; run {regen}"]
    if committed.read_text(encoding="utf-8") != rendered:
        return [f"stale_report: {relpath} differs from a live {suite}-suite render; run {regen}"]
    return []


@pytest.mark.parametrize("suite", FAMILY_SUITES)
def test_validation_report_matches_live_run(suite: str) -> None:
    docs, standards = ROOT / "docs", ROOT / "standards"
    namespace = _real_tree_namespace(suite)
    checks = [(str(name), bool(passed)) for name, passed in namespace["CHECKS"]]
    assert checks, f"No checks executed by {suite}"
    passed = sum(1 for _, ok in checks if ok)
    root_kind, relpath, _regen = REPORT_SPECS[suite]
    report = _report_root(root_kind, docs, standards) / relpath
    committed = report.read_text(encoding="utf-8")
    if suite in README_ROW_SUITES:
        rows = [
            line
            for line in (docs / "README.md").read_text(encoding="utf-8").splitlines()
            if f"(../standards/{relpath})" in line
        ]
        assert len(rows) == 1, f"docs/README.md must link {relpath} exactly once"
        # The href itself carries the active version's digits, so the count is the
        # first integer after the link, not the first integer in the row.
        row_count = re.search(r"\d+", rows[0].split(")", 1)[1])
        assert row_count is not None, "docs/README.md row carries no count"
        assert int(row_count.group()) == passed, (
            f"docs/README.md says {row_count.group()}; the live {suite} suite pins {passed}"
        )
    headline = re.search(r"(\d+)/\d+ checks passed", committed)
    assert headline is not None, f"{relpath} lacks a headline count"
    assert int(headline.group(1)) == passed, (
        f"{relpath} headline says {headline.group(1)}; the live {suite} suite passes {passed}"
    )
    rendered = _render_suite_report(suite, namespace)
    assert _drift_failures(suite, docs, standards, rendered) == []


@pytest.fixture(scope="module")
def rendered_family_report(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[str], tuple[Path, Path, str, str]]:
    """One suite execution per family suite, shared across the tamper modes.

    Copies the trees once per suite and renders the live bytes on the pristine
    copy — render-before-mutate stays the faithful order even if a suite ever
    read its own report. Each mode mutates from the pristine committed bytes,
    so modes cannot contaminate one another.
    """
    cache: dict[str, tuple[Path, Path, str, str]] = {}

    def get(suite: str) -> tuple[Path, Path, str, str]:
        if suite not in cache:
            base = tmp_path_factory.mktemp(f"report-family-{suite}")
            docs = base / "docs"
            standards = base / "standards"
            shutil.copytree(ROOT / "docs", docs)
            shutil.copytree(ROOT / "standards", standards)
            root_kind, relpath, _regen = REPORT_SPECS[suite]
            pristine = (_report_root(root_kind, docs, standards) / relpath).read_text(
                encoding="utf-8"
            )
            rendered = _render_suite_report(suite, load_suite(suite, docs, standards))
            cache[suite] = (docs, standards, rendered, pristine)
        return cache[suite]

    return get


@pytest.mark.parametrize("mode", ["flip_pass", "bump_count", "reorder_lines"])
@pytest.mark.parametrize("suite", FAMILY_SUITES)
def test_validation_report_tampering_is_detected(
    mode: str, suite: str, rendered_family_report: Callable[[str], tuple[Path, Path, str, str]]
) -> None:
    docs, standards, rendered, pristine = rendered_family_report(suite)
    root_kind, relpath, regen = REPORT_SPECS[suite]
    report = _report_root(root_kind, docs, standards) / relpath
    if mode == "flip_pass":
        assert "- PASS: " in pristine, "report must carry PASS lines to tamper with"
        mutated = pristine.replace("- PASS: ", "- FAIL: ", 1)
    elif mode == "reorder_lines":
        # The platform-drift case the sorted renderer exists for: an unsorted
        # check list is a permutation the live (sorted) render can never match.
        lines = pristine.splitlines(keepends=True)
        passes = [i for i, line in enumerate(lines) if line.startswith("- PASS: ")]
        assert len(passes) >= 2, "report must carry PASS lines to reorder"
        lines[passes[0]], lines[passes[-1]] = lines[passes[-1]], lines[passes[0]]
        mutated = "".join(lines)
        assert mutated != pristine, "reorder mutation must change the report"
    else:
        mutated = re.sub(
            r"(\d+)/(\d+)",
            lambda match: f"{int(match.group(1)) + 1}/{match.group(2)}",
            pristine,
            count=1,
        )
        assert mutated != pristine, "headline-count mutation must change the report"
    report.write_text(mutated, encoding="utf-8", newline="\n")
    failures = _drift_failures(suite, docs, standards, rendered)
    assert any(relpath in failure and regen in failure for failure in failures), failures


@pytest.mark.parametrize("suite", FAMILY_SUITES)
def test_check_names_are_path_portable(suite: str) -> None:
    """No family check name may embed an absolute tree path.

    Sorted rendering is byte-stable across platforms only if names are
    host-independent; a name built from ``str(CONTRACT_DIR / ...)`` bakes
    ``/Users/...`` (or the CI checkout path) into the pinned report bytes.
    Runs on the real tree so the absolute prefix is the true repository root.
    """
    docs, standards = ROOT / "docs", ROOT / "standards"
    absolute_roots = (str(docs), str(standards))
    offenders = [
        name
        for name, _ in _real_tree_checks(suite)
        if any(root in name for root in absolute_roots)
    ]
    assert offenders == [], (
        f"{suite}: check names embed absolute roots (unportable report bytes): {offenders}"
    )


def test_report_writer_refuses_failing_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The shared ``--write-report`` epilogue refuses to write on a red run.

    One pin covers every family suite because the refuse path lives in the
    shared writer module, not in each script (#102 D1).
    """
    writer = _load_shared_writer()
    out = tmp_path / "validation-report.md"
    monkeypatch.setattr(sys, "argv", ["check_family.py", "--write-report"])
    with pytest.raises(SystemExit) as raised:
        writer.main(
            [("synthetic failing check", False), ("synthetic passing check", True)],
            out,
            script="scripts/architecture/check_family.py",
            title="# synthetic",
            coverage="synthetic coverage",
        )
    assert raised.value.code == 1
    assert "refusing to write the validation report" in capsys.readouterr().out
    assert not out.exists()


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


def test_pinned_check_detects_path_escape(tmp_path: Path) -> None:
    """The pinned check's escape arm must fail an escaped contract path (#125).

    The regression rows pin the hash-mismatch and census arms; this dedicated
    arm pins ``is_relative_to(OUT)``. The contract's bytes are copied UNCHANGED
    to one directory above the active version directory, and the descriptor's
    contract path is rewritten to ``../``-reach it, so the recorded sha256
    still matches and the file still exists — by construction the only clause
    that can fail is the escape itself, never the hash or existence. The
    resolve-equality guard pins the geometry: if the copy target and the
    ``../`` resolution ever drift apart (the vacuous shape this test replaced),
    the guard fails loudly rather than passing for the wrong reason.

    Ordinary corpus obligation: class-dc_psu.json must keep a non-empty
    ``contracts`` array and its ``profiles`` key — the construction is generic
    over whichever contract is ``contracts[0]``.
    """
    docs = tmp_path / "docs"
    standards = tmp_path / "standards"
    shutil.copytree(ROOT / "docs", docs)
    shutil.copytree(ROOT / "standards", standards)
    version_dir = standards / _active_report_path("otdp").rsplit("/", 1)[0]
    descriptor_path = version_dir / "examples" / "class-dc_psu.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    contract = descriptor["contracts"][0]
    escaped = version_dir.parent / "escaped-contract.json"
    escaped.write_bytes((version_dir / contract["path"]).read_bytes())
    assert (version_dir / "../escaped-contract.json").resolve() == escaped.resolve(), (
        "escape target must be exactly where the descriptor's ../ lands"
    )
    contract["path"] = "../escaped-contract.json"
    descriptor_path.write_text(json.dumps(descriptor, indent=2), encoding="utf-8")
    failures = [name for name, passed in run_checks("devices", docs, standards) if not passed]
    assert failures == [f"class-dc_psu.json pinned {contract['id']}"], failures


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
            _active_standard_dir("otdp") + "/otdp-measurement.schema.json",
            "",
            "\n",
            "pinned",
        ),
        (
            "devices",
            _active_standard_dir("otdp") + "/examples/derivation-vectors.json",
            '"values": [\n            9.0\n          ]',
            '"values": [\n            9.1\n          ]',
            "census",
        ),
        (
            "registry",
            _active_standard_dir("registry") + "/examples/release-manifest.json",
            '"version": "1.0.0"',
            '"version": "latest"',
            "positive fixture",
        ),
        (
            "execution",
            _active_standard_dir("execution") + "/examples/run-record.json",
            '"safe_state": "verified"',
            '"safe_state": "unknown"',
            "positive fixture",
        ),
        (
            "interface",
            _active_standard_dir("interface") + "/examples/operation-vectors.json",
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
