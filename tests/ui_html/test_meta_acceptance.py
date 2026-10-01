"""G1a meta-acceptance — the pre-committed RED proof (design record section 8).

Runs the contract-gate plugin in subprocesses against the real contract and
scratch mutations, and asserts the acceptance rule's exact cardinalities from
junitxml attributes only (never a summary line). Written before the plugin
exists; against a missing plugin every metric fails for the right reason
(collected 0, not 196).

Layer scoping (ruled at build time): the primary acceptance numbers are the
ROW layer (168 collected / 168 failed / 0 passed / 0 skipped at an empty
registry); the pin layer (28 collected / 28 passed) and the suite totals
(tests=196 failures=168) are additional evidence from the same junitxml.
"""

from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

# --- pre-committed constants (design record sections 2/5/8, corrected 168) ----

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"

PIN_ITEMS = 28
ROW_ITEMS = 168
TOTAL_ITEMS = PIN_ITEMS + ROW_ITEMS

# Item naming: "pin::<heading-slug>" and "row::<heading-slug>::<key-cell>"
# where the slug is the heading lowercased, section mark dropped, runs of
# non-alphanumerics collapsed to a single dash.
SLUG_A1 = "a-1-colour-palette"
SLUG_C3 = "c-3-refusal-mapping"
SLUG_E1 = "e-1-components"
BUTTON_ROW_ID = f"{SLUG_E1}::button"

HEADING_A1 = "### §A.1 Colour palette"
HEADING_E1 = "### §E.1 Components"


# --- subprocess harness -------------------------------------------------------


def _env(**extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = "venv"
    env.update(extra)
    return env


def _run(
    target: Path,
    junit: Path,
    *,
    prelude: str = "",
    env_extra: dict[str, str] | None = None,
) -> int:
    """Run pytest on ``target`` writing junitxml; return the TRUE exit code.

    Without ``prelude`` this is the plain Metric A invocation
    (``uv run pytest <contract> --junitxml=...``). With ``prelude`` the run is
    in-process instead: the prelude executes first (artifact registration or
    the REQUIRE_ARTIFACT flip), then ``pytest.main`` with the same arguments —
    the only way a module constant can be flipped inside the measured process.
    """
    args = [str(target), "-q", f"--junitxml={junit}", "-o", "junit_family=xunit1"]
    if prelude:
        code = f"{prelude}\nimport pytest\nimport sys\nsys.exit(pytest.main({args!r}))\n"
        cmd: list[str] = ["uv", "run", "python", "-c", code]
    else:
        cmd = ["uv", "run", "pytest", *args]
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_env(**(env_extra or {})),
        capture_output=True,
        text=True,
        timeout=300,
    )
    return proc.returncode


def _suite(junit: Path) -> tuple[dict[str, str], dict[str, list[ET.Element]]]:
    """Read the junitxml testsuite attributes and bucket cases by layer."""
    if not junit.exists():
        return {}, {"pin": [], "row": [], "other": []}
    root = ET.parse(junit).getroot()  # noqa: S314 - our own subprocess's junitxml, not untrusted input
    ts = root if root.tag == "testsuite" else root.find("testsuite")
    assert ts is not None, f"no testsuite element in {junit}"
    buckets: dict[str, list[ET.Element]] = {"pin": [], "row": [], "other": []}
    for case in ts.findall("testcase"):
        buckets[_layer_of(case)].append(case)
    return ts.attrib, buckets


def _layer_of(case: ET.Element) -> str:
    """The xunit1 family splits the nodeid at the last '::' — the layer prefix
    and table slug live in the classname (…​.ui-contract.md.pin for pins,
    …​.ui-contract.md.row.<slug> for rows), the key cell in the name."""
    classname = case.get("classname", "")
    if classname.endswith(".pin"):
        return "pin"
    if ".row." in classname:
        return "row"
    return "other"


def _row_id_of(case: ET.Element) -> str:
    classname = case.get("classname", "")
    slug = classname.split(".row.", 1)[1]
    return f"{slug}::{case.get('name', '')}"


def _stats(cases: list[ET.Element]) -> dict[str, int]:
    out = {"collected": len(cases), "failed": 0, "passed": 0, "skipped": 0}
    for case in cases:
        if case.find("failure") is not None:
            out["failed"] += 1
        elif case.find("skipped") is not None:
            out["skipped"] += 1
        else:
            out["passed"] += 1
    return out


def _failure_texts(cases: list[ET.Element]) -> dict[str, str]:
    """Map row-id (row layer) / slug (pin layer) -> failure text."""
    out: dict[str, str] = {}
    for case in cases:
        parts = [f.get("message", "") or "" for f in case.findall("failure")]
        parts += [(f.text or "") for f in case.findall("failure")]
        if parts:
            key = _row_id_of(case) if _layer_of(case) == "row" else case.get("name", "")
            out[key] = "\n".join(parts)
    return out


def _assert_metric_a_shape(attrib: dict[str, str], buckets: dict[str, list[ET.Element]]) -> None:
    """The Metric A cardinalities: suite totals + both layers."""
    rows = _stats(buckets["row"])
    pins = _stats(buckets["pin"])
    assert rows == {"collected": ROW_ITEMS, "failed": ROW_ITEMS, "passed": 0, "skipped": 0}, rows
    assert pins == {"collected": PIN_ITEMS, "failed": 0, "passed": PIN_ITEMS, "skipped": 0}, pins
    assert buckets["other"] == []
    assert attrib.get("tests") == str(TOTAL_ITEMS), attrib
    assert attrib.get("failures") == str(ROW_ITEMS), attrib
    assert attrib.get("errors") == "0", attrib
    assert attrib.get("skipped") == "0", attrib


# --- Metric A: RED against the empty renderer ---------------------------------


def test_metric_a_red_against_empty_registry(tmp_path: Path) -> None:
    junit = tmp_path / "metric-a.xml"
    exit_code = _run(CONTRACT, junit)
    assert exit_code != 0, "empty registry must leave the run red (exit non-zero)"
    attrib, buckets = _suite(junit)
    _assert_metric_a_shape(attrib, buckets)
    # The canonical RED message: every unregistered row names its missing artifact.
    texts = _failure_texts(buckets["row"])
    assert len(texts) == ROW_ITEMS
    for row_id, text in texts.items():
        assert f"no canonical artifact for {row_id}" in text, (row_id, text)


def test_no_environment_variable_flips_the_gate(tmp_path: Path) -> None:
    """The REQUIRE_ARTIFACT constant has no environment surface (design section 2)."""
    junit = tmp_path / "env-control.xml"
    exit_code = _run(
        CONTRACT,
        junit,
        env_extra={
            "REQUIRE_ARTIFACT": "0",
            "BENCHWEAVE_REQUIRE_ARTIFACT": "false",
            "BW_UI_HTML_REQUIRE_ARTIFACT": "0",
            "BENCHWEAVE_UI_HTML_REQUIRE_ARTIFACT": "no",
        },
    )
    assert exit_code != 0
    attrib, buckets = _suite(junit)
    _assert_metric_a_shape(attrib, buckets)


# --- Metric B: fail-closed mutations ------------------------------------------


def _delete_line(text: str, predicate: Callable[[str], bool]) -> str:
    lines = text.split("\n")
    kept = [line for line in lines if not predicate(line)]
    assert len(kept) == len(lines) - 1, "mutation must delete exactly one line"
    return "\n".join(kept)


def _rename_first_header_cell_under(text: str, heading: str, old: str, new: str) -> str:
    lines = text.split("\n")
    start = lines.index(heading)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("|"):
            assert old in lines[i], f"header row under {heading} does not contain {old!r}"
            lines[i] = lines[i].replace(old, new, 1)
            return "\n".join(lines)
    raise AssertionError(f"no table under {heading}")


def _mutation(arm: str) -> tuple[str, str, str]:
    """Return (slug, defect class, mutated contract text) for a Metric B arm."""
    text = CONTRACT.read_text(encoding="utf-8")
    if arm == "missing-heading":
        return SLUG_A1, "missing heading", _delete_line(
            text, lambda line: line.strip() == HEADING_A1
        )
    if arm == "deleted-row":
        return (
            SLUG_C3,
            "wrong stated row count",
            _delete_line(text, lambda line: line.lstrip().startswith("| `not_found`")),
        )
    if arm == "renamed-header-cell":
        return (
            SLUG_E1,
            "wrong header cells",
            _rename_first_header_cell_under(text, HEADING_E1, "Required roles", "Roles"),
        )
    if arm == "wrong-stated-count":
        assert text.count("— 25 rows") == 1, "the 25-row stated count must be unique to §A.1"
        return SLUG_A1, "wrong stated row count", text.replace("— 25 rows", "— 24 rows", 1)
    raise AssertionError(arm)


def test_metric_b_fail_closed_mutations(tmp_path: Path) -> None:
    for arm in ("missing-heading", "deleted-row", "renamed-header-cell", "wrong-stated-count"):
        slug, defect_class, mutated = _mutation(arm)
        scratch = tmp_path / arm
        scratch.mkdir()
        (scratch / "ui-contract.md").write_text(mutated, encoding="utf-8")
        junit = tmp_path / f"{arm}.xml"
        exit_code = _run(scratch / "ui-contract.md", junit)
        assert exit_code != 0, f"{arm}: a mutated contract must leave the run red"
        _attrib, buckets = _suite(junit)
        pin_failures = _failure_texts(buckets["pin"])
        assert slug in pin_failures, (
            f"{arm}: the {slug} pin item must fail; pin failures: {sorted(pin_failures)}"
        )
        message = pin_failures[slug]
        assert defect_class in message, f"{arm}: need class {defect_class!r} in: {message}"
        assert slug in message, f"{arm}: pin must name the table: {message}"
        # Kill direction: no row is green at an empty registry under any mutation.
        assert _stats(buckets["row"])["passed"] == 0


# --- Metric C: green-able per row ---------------------------------------------


def test_metric_c_registering_one_artifact_greens_exactly_that_row(tmp_path: Path) -> None:
    junit = tmp_path / "metric-c.xml"
    prelude = (
        "import benchweave_ui_html.registry as registry\n"
        "\n"
        "class _FakeArtifact:\n"
        '    kind = "component_render"\n'
        "\n"
        "    def satisfies(self, row):\n"
        "        return []\n"
        "\n"
        f"registry.REGISTRY.register({BUTTON_ROW_ID!r}, _FakeArtifact())\n"
    )
    exit_code = _run(CONTRACT, junit, prelude=prelude)
    assert exit_code != 0, "167 of 168 rows still red keeps the run red"
    _attrib, buckets = _suite(junit)
    rows = _stats(buckets["row"])
    assert rows == {
        "collected": ROW_ITEMS,
        "failed": ROW_ITEMS - 1,
        "passed": 1,
        "skipped": 0,
    }, rows
    # The one green row is exactly the button row; the other 167 carry the
    # canonical missing-artifact message.
    failed_ids = set(_failure_texts(buckets["row"]))
    assert BUTTON_ROW_ID not in failed_ids
    assert len(failed_ids) == ROW_ITEMS - 1
    pins = _stats(buckets["pin"])
    assert pins == {"collected": PIN_ITEMS, "failed": 0, "passed": PIN_ITEMS, "skipped": 0}, pins


# --- Mechanism-toggle control ---------------------------------------------------


def test_mechanism_toggle_flipping_the_constant_makes_the_red_run_green(tmp_path: Path) -> None:
    junit = tmp_path / "toggle.xml"
    prelude = (
        "import benchweave_ui_html.registry as registry\n"
        "registry.REQUIRE_ARTIFACT = False\n"
    )
    exit_code = _run(CONTRACT, junit, prelude=prelude)
    assert exit_code == 0, "REQUIRE_ARTIFACT=False must make the RED run fully green"
    attrib, buckets = _suite(junit)
    rows = _stats(buckets["row"])
    pins = _stats(buckets["pin"])
    assert rows == {"collected": ROW_ITEMS, "failed": 0, "passed": ROW_ITEMS, "skipped": 0}, rows
    assert pins == {"collected": PIN_ITEMS, "failed": 0, "passed": PIN_ITEMS, "skipped": 0}, pins
    assert attrib.get("tests") == str(TOTAL_ITEMS), attrib
    assert attrib.get("failures") == "0", attrib


# --- UR-11: the renderer namespace never pulls pytest ---------------------------


def test_runtime_namespace_imports_without_pytest() -> None:
    code = (
        "import sys\n"
        "import benchweave_ui_html\n"
        "import benchweave_ui_html.grammar\n"
        "import benchweave_ui_html.manifest\n"
        "import benchweave_ui_html.registry\n"
        "import benchweave_ui_html.roles\n"
        "import benchweave_ui_html.tokens\n"
        "sys.exit(0 if 'pytest' not in sys.modules else 1)\n"
    )
    proc = subprocess.run(
        ["uv", "run", "python", "-c", code],
        cwd=REPO_ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
