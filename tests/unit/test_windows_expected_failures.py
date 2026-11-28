"""The Windows expected-failures baseline comparison (issue #457).

``scripts/ci/windows_expected_failures.py`` is the strict gate over the Windows
evidence lanes' own junit artifacts: an unlisted failing id (new Windows
breakage) or a healed ``strict`` row reds the lane (exit 1); a run that matches
the reviewed manifest is green (exit 0); anything unreadable or ambiguous
fails closed (exit 2). These tests prove each direction of that contract
against synthetic junit and manifest fixtures — the real-artifact replay
(Nov 25 wincore, Nov 23 full, Oct 2 plant branch) is the PR-body evidence,
run POSIX-side against the downloaded artifacts.

The lane-scoping semantics (design record §3) are load-bearing here: a
``strict`` row is only judgable over the ids the lane actually collected and
ran — an id the selection does not collect, or a skipped testcase, is inert
for both directions (skipping is neither failing nor passing; it also keeps
fork PRs green when the signing-key rows skip instead of fail).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "windows_expected_failures.py"

EXIT_MATCH = 0
EXIT_DRIFT = 1
EXIT_FAIL_CLOSED = 2


def _load() -> Any:
    """Import the script as a module (it is not on any package path)."""
    spec = importlib.util.spec_from_file_location("windows_expected_failures", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _junit(cases: list[dict[str, str]]) -> str:
    """Render a junit xml over (name, classname, file, outcome) case dicts.

    ``outcome`` is ``pass`` | ``fail`` | ``error`` | ``skip``; ``file`` and
    ``classname`` carry the Windows shapes the canonicalizer must survive
    (backslash paths, dotted modules, ``Test``-classes, ``[param]`` ids).
    """
    parts = ['<?xml version="1.0" encoding="utf-8"?>', "<testsuites>"]
    for case in cases:
        parts.append(
            f'<testcase classname="{case["classname"]}" name="{case["name"]}" '
            f'file="{case["file"]}" line="7" time="0.01">'
        )
        if case["outcome"] == "fail":
            parts.append('<failure message="AssertionError: synthetic" />')
        elif case["outcome"] == "error":
            parts.append('<error message="PermissionError: synthetic" />')
        elif case["outcome"] == "skip":
            parts.append('<skipped type="pytest.skip" />')
        parts.append("</testcase>")
    parts.append("</testsuites>")
    return "".join(parts)


def _manifest(rows: dict[str, dict[str, str]], tmp_path: Path) -> Path:
    path = tmp_path / "expected.json"
    path.write_text(
        json.dumps({"schema": "benchweave.windows-expected-failures/1", "rows": rows}),
        encoding="utf-8",
    )
    return path


ATREST = "tests/cli/test_atrest.py::test_setup_creates_layout"
DEV_PIN = "tests/standards/test_dev_pins.py::test_d1_wheel_posture_refuses"
RECOVERY_ROW = "tests/faults/test_state_recovery.py::test_kill_after_commit"


def _one_case(tmp_path: Path, outcome: str, node: str = ATREST) -> Path:
    file, _, rest = node.partition("::")
    klass, _, name = rest.rpartition("::") if "::" in rest else ("", "", rest)
    classname = file[:-3].replace("/", ".")
    if klass:
        classname += f".{klass}"
    path = tmp_path / "run.xml"
    path.write_text(
        _junit(
            [{"classname": classname, "name": name, "file": file, "outcome": outcome}]
        ),
        encoding="utf-8",
    )
    return path


class TestCompare:
    def test_unlisted_failure_reds(self, tmp_path: Path) -> None:
        module = _load()
        junit = _one_case(tmp_path, "fail", ATREST)
        manifest = _manifest({DEV_PIN: {"kind": "strict", "reason": "r"}}, tmp_path)
        ran, failed = module.parse_junit(junit)
        rows = module.load_manifest(manifest)
        problems = module.compare(ran, failed, rows)
        assert any(ATREST in p and "unlisted" in p for p in problems), problems

    def test_healed_strict_row_reds(self, tmp_path: Path) -> None:
        module = _load()
        junit = _one_case(tmp_path, "pass", DEV_PIN)
        manifest = _manifest({DEV_PIN: {"kind": "strict", "reason": "r"}}, tmp_path)
        ran, failed = module.parse_junit(junit)
        rows = module.load_manifest(manifest)
        problems = module.compare(ran, failed, rows)
        assert any(DEV_PIN in p and "not failing" in p for p in problems), problems

    def test_matching_run_is_green(self, tmp_path: Path) -> None:
        module = _load()
        cases = [
            {"classname": "tests.cli.test_atrest", "name": "test_setup_creates_layout",
             "file": "tests\\cli\\test_atrest.py", "outcome": "fail"},
            {"classname": "tests.faults.test_state_recovery",
             "name": "test_kill_after_commit", "file": "tests\\faults\\test_state_recovery.py",
             "outcome": "fail"},
            {"classname": "tests.cli.test_commands", "name": "test_status_json",
             "file": "tests\\cli\\test_commands.py", "outcome": "pass"},
        ]
        junit = tmp_path / "run.xml"
        junit.write_text(_junit(cases), encoding="utf-8")
        manifest = _manifest(
            {
                ATREST: {"kind": "strict", "reason": "r"},
                RECOVERY_ROW: {"kind": "non-strict", "reason": "kill-family intermittent"},
            },
            tmp_path,
        )
        ran, failed = module.parse_junit(junit)
        rows = module.load_manifest(manifest)
        assert module.compare(ran, failed, rows) == []

    def test_nonstrict_row_passing_never_reds(self, tmp_path: Path) -> None:
        module = _load()
        junit = _one_case(tmp_path, "pass", RECOVERY_ROW)
        manifest = _manifest(
            {RECOVERY_ROW: {"kind": "non-strict", "reason": "kill-family"}}, tmp_path
        )
        ran, failed = module.parse_junit(junit)
        rows = module.load_manifest(manifest)
        assert module.compare(ran, failed, rows) == []

    def test_strict_row_not_collected_is_inert(self, tmp_path: Path) -> None:
        """A full-lane-only row must not read as healed in the core lane."""
        module = _load()
        junit = _one_case(tmp_path, "fail", ATREST)
        manifest = _manifest(
            {
                ATREST: {"kind": "strict", "reason": "r"},
                "tests/unit/test_lane_park.py::test_check_active_without_ack": {
                    "kind": "strict", "reason": "bash lane-park",
                },
            },
            tmp_path,
        )
        ran, failed = module.parse_junit(junit)
        rows = module.load_manifest(manifest)
        assert module.compare(ran, failed, rows) == []

    def test_skipped_strict_row_is_inert(self, tmp_path: Path) -> None:
        """Skip is neither failing nor passing (fork PRs skip signing rows)."""
        module = _load()
        # A second live case keeps the artifact off the zero-ran fail-closed
        # arm — this test judges the SKIP semantics, not the empty-junit one.
        junit = tmp_path / "run.xml"
        junit.write_text(
            _junit(
                [
                    {"classname": "tests.cli.test_atrest", "name": "test_setup_creates_layout",
                     "file": "tests\\cli\\test_atrest.py", "outcome": "skip"},
                    {"classname": "tests.cli.test_commands", "name": "test_status_json",
                     "file": "tests\\cli\\test_commands.py", "outcome": "pass"},
                ]
            ),
            encoding="utf-8",
        )
        manifest = _manifest(
            {
                ATREST: {"kind": "strict", "reason": "r"},
            },
            tmp_path,
        )
        ran, failed = module.parse_junit(junit)
        rows = module.load_manifest(manifest)
        assert module.compare(ran, failed, rows) == []
        assert ATREST not in ran


class TestFailClosed:
    def test_absent_junit_fails_closed(self, tmp_path: Path) -> None:
        module = _load()
        with pytest.raises(module.FailClosed):
            module.parse_junit(tmp_path / "absent.xml")

    def test_malformed_junit_fails_closed(self, tmp_path: Path) -> None:
        module = _load()
        junit = tmp_path / "run.xml"
        junit.write_text("<not-junit at all", encoding="utf-8")
        with pytest.raises(module.FailClosed):
            module.parse_junit(junit)

    def test_empty_junit_fails_closed(self, tmp_path: Path) -> None:
        """A collector crash yields zero testcases; that must never read green."""
        module = _load()
        junit = tmp_path / "run.xml"
        junit.write_text(
            '<?xml version="1.0"?><testsuites><testsuite name="pytest" '
            'tests="0" failures="0" errors="0"/></testsuites>',
            encoding="utf-8",
        )
        with pytest.raises(module.FailClosed):
            module.parse_junit(junit)

    def test_duplicate_ids_fail_closed(self, tmp_path: Path) -> None:
        module = _load()
        junit = tmp_path / "run.xml"
        junit.write_text(
            _junit(
                [
                    {"classname": "tests.cli.test_atrest",
                     "name": "test_setup_creates_layout",
                     "file": "tests\\cli\\test_atrest.py", "outcome": "pass"},
                    {"classname": "tests.cli.test_atrest",
                     "name": "test_setup_creates_layout",
                     "file": "tests\\cli\\test_atrest.py", "outcome": "fail"},
                ]
            ),
            encoding="utf-8",
        )
        with pytest.raises(module.FailClosed):
            module.parse_junit(junit)

    def test_malformed_manifest_fails_closed(self, tmp_path: Path) -> None:
        module = _load()
        path = tmp_path / "expected.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(module.FailClosed):
            module.load_manifest(path)

    def test_foreign_schema_fails_closed(self, tmp_path: Path) -> None:
        module = _load()
        path = _manifest({}, tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["schema"] = "some.other.schema/9"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(module.FailClosed):
            module.load_manifest(path)

    @pytest.mark.parametrize(
        "row",
        [
            {"kind": "loose", "reason": "r"},
            {"kind": "strict"},
            {"kind": "strict", "reason": ""},
        ],
    )
    def test_bad_row_shape_fails_closed(
        self, tmp_path: Path, row: dict[str, str]
    ) -> None:
        module = _load()
        path = _manifest({ATREST: row}, tmp_path)
        with pytest.raises(module.FailClosed):
            module.load_manifest(path)

    def test_duplicate_json_key_fails_closed(self, tmp_path: Path) -> None:
        """json last-wins would let a non-strict twin silently shadow a
        strict row (the refute pass's F3) — a duplicated key is malformed."""
        module = _load()
        path = tmp_path / "dup.json"
        path.write_text(
            '{"schema": "benchweave.windows-expected-failures/1",'
            f' "rows": {{}}, "rows": {{{json.dumps(ATREST)}: '
            '{"kind": "non-strict", "reason": "shadow"}}}}',
            encoding="utf-8",
        )
        with pytest.raises(module.FailClosed):
            module.load_manifest(path)


class TestCanonicalId:
    def test_windows_shapes_render_pytest_nodeids(self) -> None:
        module = _load()
        assert (
            module.canonical_id(
                "tests\\cli\\test_atrest.py", "tests.cli.test_atrest", "test_setup"
            )
            == "tests/cli/test_atrest.py::test_setup"
        )
        assert (
            module.canonical_id(
                "tests\\standards\\test_zero_literal_gate.py",
                "tests.standards.test_zero_literal_gate.TestDocsRatchet",
                "test_refresh[param-1]",
            )
            == "tests/standards/test_zero_literal_gate.py::TestDocsRatchet::"
            "test_refresh[param-1]"
        )

    def test_markdown_collected_rows_keep_their_row_chain(self) -> None:
        """The ui-contract gate collects from a .md file: classname there is
        the PATH-dotted form (extension included). Distinct rows whose leaf
        names collide must NOT collapse onto one id — found by replaying the
        real full-lane artifact (two ``::measured`` rows, 2026-11-23)."""
        module = _load()
        first = module.canonical_id(
            "docs\\internal\\ui-contract.md",
            "docs.internal.ui-contract.md.row.e-2-6-trace-provenance",
            "measured",
        )
        second = module.canonical_id(
            "docs\\internal\\ui-contract.md",
            "docs.internal.ui-contract.md.row.e-3-setpoint-presentation-reading-tile-sub-rows",
            "measured",
        )
        assert first != second
        assert first == (
            "docs/internal/ui-contract.md::row.e-2-6-trace-provenance::measured"
        )
        assert second == (
            "docs/internal/ui-contract.md::"
            "row.e-3-setpoint-presentation-reading-tile-sub-rows::measured"
        )


class TestBlackBox:
    """The exit contract end to end, the way the CI step invokes it."""

    def test_green_then_drift_then_fail_closed(self, tmp_path: Path) -> None:
        junit = tmp_path / "run.xml"
        junit.write_text(
            _junit(
                [
                    {"classname": "tests.cli.test_atrest", "name": "test_setup_creates_layout",
                     "file": "tests\\cli\\test_atrest.py", "outcome": "fail"},
                ]
            ),
            encoding="utf-8",
        )
        good = _manifest(
            {ATREST: {"kind": "strict", "reason": "born ACL entries"}}, tmp_path
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--junit", str(junit), "--manifest", str(good)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == EXIT_MATCH, proc.stdout + proc.stderr

        healed = _manifest(
            {ATREST: {"kind": "strict", "reason": "born ACL entries"},
             "tests/other.py::test_strict_heal": {"kind": "strict", "reason": "r"}},
            tmp_path,
        )
        extra = tmp_path / "extra.xml"
        extra.write_text(
            _junit(
                [
                    {"classname": "tests.cli.test_atrest", "name": "test_setup_creates_layout",
                     "file": "tests\\cli\\test_atrest.py", "outcome": "fail"},
                    {"classname": "tests.other", "name": "test_strict_heal",
                     "file": "tests\\other.py", "outcome": "pass"},
                ]
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--junit", str(extra), "--manifest", str(healed)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == EXIT_DRIFT, proc.stdout + proc.stderr
        assert "test_strict_heal" in proc.stdout

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--junit", str(tmp_path / "absent.xml"),
             "--manifest", str(good)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == EXIT_FAIL_CLOSED, proc.stdout + proc.stderr
