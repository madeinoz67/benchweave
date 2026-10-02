"""Harness activation-shape tests: dormant by default, live where wired.

The plugin claims ONLY files named ui-contract.md; the repo's default pytest
run (testpaths = ["tests"]) never walks the contract, so the gate is inert
there. These arms pin that boundary with real subprocess runs (the same
invocation shape as the meta-acceptance) plus the generated-item marker.
"""

from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from benchweave_ui_html import artifacts, registry

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"


def _expected_row_failures() -> int:
    """Rows red at a plain invocation = 168 minus the auto-registered set —
    0 since G1d slice 2 registered the ten behaviour rows. Clears first:
    earlier in-process arms legitimately leave partial registrations."""
    registry.REGISTRY.clear()
    artifacts.ensure_registered()
    return 168 - len(registry.REGISTRY)


def _run_pytest(*args: str, junit: Path) -> tuple[int, dict[str, str]]:
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = "venv"
    proc = subprocess.run(
        ["uv", "run", "pytest", *args, f"--junitxml={junit}", "-o", "junit_family=xunit1"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if not junit.exists():
        return proc.returncode, {}
    root = ET.parse(junit).getroot()  # noqa: S314 - our own subprocess's junitxml
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    assert suite is not None
    return proc.returncode, dict(suite.attrib)


def test_only_files_named_ui_contract_md_are_claimed(tmp_path: Path) -> None:
    """A byte-identical copy under another name collects nothing; the same
    bytes as ui-contract.md collect the full 196."""
    other = tmp_path / "not-a-contract.md"
    other.write_text(CONTRACT.read_text(encoding="utf-8"), encoding="utf-8")
    code, attrib = _run_pytest(str(other), "-q", junit=tmp_path / "other.xml")
    # An unclaimed file collects nothing (pytest exits non-zero; 4 usage /
    # 5 no-tests depending on arg handling) and writes no testcases.
    assert code != 0
    assert not attrib or attrib.get("tests") == "0"

    named = tmp_path / "ui-contract.md"
    named.write_text(CONTRACT.read_text(encoding="utf-8"), encoding="utf-8")
    code, attrib = _run_pytest(str(named), "-q", junit=tmp_path / "named.xml")
    # Since G1d slice 2 the full population registers and the run is green
    # (failures == the unregistered rows == 0; the mechanism is derived, so
    # a future deferral would show here as its red count).
    assert code == 0
    assert attrib.get("tests") == "196"
    assert attrib.get("failures") == str(_expected_row_failures())


def test_every_generated_item_carries_the_contract_marker(tmp_path: Path) -> None:
    """`-m contract` keeps all 196; `-m 'not contract'` deselects all — so
    both layers are uniformly marked (no unmarked escape item)."""
    junit_all = tmp_path / "all.xml"
    code, attrib = _run_pytest(
        str(CONTRACT), "-q", "-m", "contract", junit=junit_all
    )
    assert code == 0  # the fully-registered population is green
    assert attrib.get("tests") == "196"

    junit_none = tmp_path / "none.xml"
    code, attrib = _run_pytest(
        str(CONTRACT), "-q", "-m", "not contract", junit=junit_none
    )
    # Every item deselected: 0 collected, exit 5 — and the default run (no
    # -m) applies no such filter; deselect-by-default is a hole the design
    # forbids and the repo's addopts carries no -m.
    assert code == 5
    assert attrib.get("tests") == "0"


def test_default_suite_collection_contains_no_contract_items() -> None:
    """The repo's own default collection (tests/) never walks the contract."""
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = "venv"
    proc = subprocess.run(
        ["uv", "run", "pytest", "tests/ui_html", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ui-contract.md::" not in proc.stdout
