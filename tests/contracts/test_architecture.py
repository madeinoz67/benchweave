"""Execute the versioned architecture checks without modifying the document baseline."""

import hashlib
import json
import runpy
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUITES = ("devices", "registry", "execution", "interface", "closure", "planning", "documents")


def run_checks(suite: str, docs: Path) -> list[tuple[str, bool]]:
    script = ROOT / "scripts" / "architecture" / f"check_{suite}.py"
    assert script.is_file(), f"Missing architecture validator: {script}"
    namespace = runpy.run_path(str(script), init_globals={"DOCS": docs})
    checks = namespace["CHECKS"]
    assert isinstance(checks, list) and checks, f"No checks executed by {suite}"
    return [(str(name), bool(passed)) for name, passed in checks]


@pytest.mark.parametrize("suite", SUITES)
def test_architecture(suite: str) -> None:
    checks = run_checks(suite, ROOT / "docs")
    failures = [name for name, passed in checks if not passed]
    assert not failures, f"{suite}: {len(failures)}/{len(checks)} failed:\n" + "\n".join(failures)
    print(f"{suite}: {len(checks)} checks passed")


def test_validation_is_read_only(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    shutil.copytree(ROOT / "docs", docs)

    def snapshot() -> dict[str, str]:
        return {
            str(p.relative_to(docs)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in docs.rglob("*")
            if p.is_file()
        }

    before = snapshot()
    for suite in SUITES:
        run_checks(suite, docs)
    assert snapshot() == before, "Validation changed the architecture documents"


def test_documents_ignores_markdown_links_inside_fenced_code_blocks(
    tmp_path: Path,
) -> None:
    """A subscript-call expression in a fenced block (``legs[leg](arg)``) is
    code, not a ``](destination)`` link — planning docs may carry such code,
    and the checker must not demand a file for it. Prose links stay checked.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "fences.md").write_text(
        "# Fences\n\nProse [link](other.md) stays checked.\n\n"
        "```python\nresult = legs[leg](arg)\n```\n",
        encoding="utf-8",
    )
    (docs / "other.md").write_text("# Other\n", encoding="utf-8")
    failures = [name for name, passed in run_checks("documents", docs) if not passed]
    assert failures == []


@pytest.mark.parametrize(
    ("suite", "relative_path", "old", "new", "expected"),
    [
        ("devices", "otdp-v0.3.0/otdp-measurement.schema.json", "", "\n", "pinned"),
        (
            "registry",
            "registry-v1.0.0/examples/release-manifest.json",
            '"version": "1.0.0"',
            '"version": "latest"',
            "positive fixture",
        ),
        (
            "execution",
            "execution-v1.0.0/examples/run-record.json",
            '"safe_state": "verified"',
            '"safe_state": "unknown"',
            "positive fixture",
        ),
        (
            "interface",
            "interface-v1.1.0/examples/operation-vectors.json",
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
            "interface-v1.1.0/interface.schema.json",
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
    shutil.copytree(ROOT / "docs", docs)
    path = docs / relative_path
    original = path.read_text(encoding="utf-8")
    assert not old or old in original, "Mutation must change the intended fixture"
    changed = original.replace(old, new, 1) if old else original + new
    path.write_text(changed, encoding="utf-8")
    if path.suffix == ".json":
        json.loads(changed)  # Test semantic damage rather than invalid JSON syntax.
    failures = [name for name, passed in run_checks(suite, docs) if not passed]
    assert any(expected in name for name in failures), failures
