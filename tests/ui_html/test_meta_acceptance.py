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

G1b reconciliation (design record §1.5, open item O1): the plugin now
auto-registers the canonical artifacts at collection, so the plain-invocation
arms assert the REGISTERED state (every unregistered row red with exactly
the no-canonical-artifact message class) instead of the empty-registry 168.
The empty-registry control moved to the pure function
(``tests/ui_html/test_artifacts_meta.py``) with a collection-level variant
here that explicitly neutralizes the registration hook; the prelude-based
arms (Metric C, full registration, delete-and-pad, toggle) work unchanged
because ``ensure_registered`` is sentinel-idempotent — a prelude that
registered the button row first suppresses auto-registration instead of
colliding with it. The parser-defect arms (Metric B, the F1 identity
mutations) neutralize the hook for the same reason: they pin G1a's parser
mechanism, and with registration live a mutated contract would red via the
orphan check before any pin item emits.
"""

from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

import pytest

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

#: G1b: neutralizes the plugin's auto-registration hook in the measured
#: process, restoring G1a's empty-registry evidence shape for the arms that
#: pin the parser's own fail-closed defects (Metric B, the F1 identity
#: mutations) and the collection-level empty-registry control. The parser
#: mechanisms these arms prove are G1a's; registration-live mutation arms
#: would red via the orphan check before any pin item emits.
NEUTRALIZE_REGISTRATION = (
    "import types\n"
    "import benchweave_ui_html.contract_harness.plugin as plugin\n"
    "plugin.artifacts = types.SimpleNamespace(ensure_registered=lambda: None)\n"
)


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
    extra_args: list[str] | None = None,
) -> int:
    """Run pytest on ``target`` writing junitxml; return the TRUE exit code.

    Without ``prelude`` this is the plain Metric A invocation
    (``uv run pytest <contract> --junitxml=...``). With ``prelude`` the run is
    in-process instead: the prelude executes first (artifact registration or
    the REQUIRE_ARTIFACT flip), then ``pytest.main`` with the same arguments —
    the only way a module constant can be flipped inside the measured process.
    ``extra_args`` adds further collection targets (the F2 mixed invocation).
    """
    args = [
        str(target),
        *(extra_args or []),
        "-q",
        f"--junitxml={junit}",
        "-o",
        "junit_family=xunit1",
    ]
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


# --- Metric A: the registered state at a plain invocation ---------------------


def _assert_registered_state_shape(
    attrib: dict[str, str], buckets: dict[str, list[ET.Element]]
) -> None:
    """The plain-invocation invariants that hold at every G1b slice: 28 green
    pins, 168 rows split passed+failed with no skips, nothing outside the two
    layers, and every failed row carrying exactly the missing-artifact message
    class (a failed row with ``unsatisfied contract items`` there would mean
    something registered-and-failed — a different defect)."""
    rows = _stats(buckets["row"])
    pins = _stats(buckets["pin"])
    assert rows["collected"] == ROW_ITEMS, rows
    assert rows["skipped"] == 0, rows
    assert rows["passed"] + rows["failed"] == ROW_ITEMS, rows
    assert pins == {"collected": PIN_ITEMS, "failed": 0, "passed": PIN_ITEMS, "skipped": 0}, pins
    assert buckets["other"] == []
    assert attrib.get("tests") == str(TOTAL_ITEMS), attrib
    assert attrib.get("errors") == "0", attrib
    assert attrib.get("skipped") == "0", attrib
    texts = _failure_texts(buckets["row"])
    assert len(texts) == rows["failed"]
    for row_id, text in texts.items():
        assert f"no canonical artifact for {row_id}" in text, (row_id, text)
        assert "unsatisfied contract items" not in text, (row_id, text)


def test_plain_invocation_is_the_registered_state(tmp_path: Path) -> None:
    """The plain invocation auto-registers G1b's artifacts: pins green, the
    registered rows green, and every OTHER row red with exactly the
    no-canonical-artifact message (the ten G1d-deferred rows keep this run
    red until the compositions slice lands). The failed count is exactly the
    unregistered rows — no more (an over-count would mean a registered row
    failing its own items), no fewer (an under-count would mean an
    unregistered row going green)."""
    from benchweave_ui_html import artifacts, registry

    artifacts.ensure_registered()
    expected_failed = ROW_ITEMS - len(registry.REGISTRY)
    junit = tmp_path / "metric-a.xml"
    exit_code = _run(CONTRACT, junit)
    assert exit_code != 0, "unregistered rows must leave the run red (exit non-zero)"
    attrib, buckets = _suite(junit)
    _assert_registered_state_shape(attrib, buckets)
    rows = _stats(buckets["row"])
    assert rows["failed"] == expected_failed, rows
    assert rows["passed"] == len(registry.REGISTRY), rows


def test_empty_registry_collection_control_registration_neutralized(
    tmp_path: Path,
) -> None:
    """G1a's Metric A, preserved with the registration hook explicitly off in
    the measured process: the empty registry reds every row with the canonical
    message. This is the collection-level half of the fail-closed control; the
    pure-function half lives in test_artifacts_meta.py (design record §1.5)."""
    junit = tmp_path / "metric-a-empty.xml"
    exit_code = _run(CONTRACT, junit, prelude=NEUTRALIZE_REGISTRATION)
    assert exit_code != 0, "empty registry must leave the run red (exit non-zero)"
    attrib, buckets = _suite(junit)
    _assert_metric_a_shape(attrib, buckets)
    texts = _failure_texts(buckets["row"])
    assert len(texts) == ROW_ITEMS
    for row_id, text in texts.items():
        assert f"no canonical artifact for {row_id}" in text, (row_id, text)


def test_no_environment_variable_flips_the_gate(tmp_path: Path) -> None:
    """The REQUIRE_ARTIFACT constant has no environment surface (design section 2).
    G1b: the expected shape is the registered state — the env vars must not
    turn the run all-green either (the gate being off would be exactly that)."""
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
    _assert_registered_state_shape(attrib, buckets)


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
        # G1b: registration neutralized — these arms pin the parser's own
        # defect classes; with registration live a mutated contract reds via
        # the orphan check before any pin item emits.
        exit_code = _run(scratch / "ui-contract.md", junit, prelude=NEUTRALIZE_REGISTRATION)
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
    """UR-11: the renderer namespace never pulls pytest. G1b extends the
    imported set to the artifact/rendering modules AND renders one partial
    per family — jinja2 must land in sys.modules, pytest must not."""
    code = (
        "import sys\n"
        "import benchweave_ui_html\n"
        "import benchweave_ui_html.grammar\n"
        "import benchweave_ui_html.manifest\n"
        "import benchweave_ui_html.registry\n"
        "import benchweave_ui_html.roles\n"
        "import benchweave_ui_html.tokens\n"
        "import benchweave_ui_html.items\n"
        "import benchweave_ui_html.assertions\n"
        "import benchweave_ui_html.env\n"
        "import benchweave_ui_html.data\n"
        "import benchweave_ui_html.partials\n"
        "import benchweave_ui_html.fixtures\n"
        "import benchweave_ui_html.artifacts\n"
        "from benchweave_ui_html.partials import render_button\n"
        "render_button(__import__('benchweave_ui_html.fixtures', fromlist=['x']).button())\n"
        "assert 'jinja2' in sys.modules, 'rendering must have pulled jinja2'\n"
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


# --- F1 fold: identity mutations (the refute's corruption classes) -------------

SLUG_E41 = "e-4-1-lane-layout"
SLUG_E45 = "e-4-5-time-axis"
DEFECT_WRONG_ROW_KEYS = "wrong row keys"
DEFECT_TABLE_INTERRUPTED = "table interrupted"


def _line_starting_with(lines: list[str], prefix: str) -> int:
    return next(i for i, line in enumerate(lines) if line.startswith(prefix))


def _identity_mutations() -> dict[str, tuple[list[tuple[str, str]], str]]:
    """The refuter's classes (a)-(d): each must red its pin naming the defect
    class. All keep counts and header cells intact — they corrupt identity."""
    text = CONTRACT.read_text(encoding="utf-8")

    # (a) row swap between equal-count same-schema tables (§E.4.1 <-> §E.4.5).
    lines = text.split("\n")
    i, j = _line_starting_with(lines, "| Hidden lanes |"), _line_starting_with(lines, "| Cursors |")
    lines[i], lines[j] = lines[j], lines[i]
    swap = "\n".join(lines)

    # (b) mid-table interleaved non-pipe line under §E.1.
    lines = text.split("\n")
    lines.insert(_line_starting_with(lines, "| `button` |") + 1, "interleaved prose")
    interleave = "\n".join(lines)

    # (c) §A.1 token delete-and-pad: delete --bw-canvas, duplicate --bw-surface.
    lines = text.split("\n")
    del lines[_line_starting_with(lines, "| `--bw-canvas` |")]
    i = _line_starting_with(lines, "| `--bw-surface` |")
    lines.insert(i + 1, lines[i])
    token_pad = "\n".join(lines)

    # (d) §E.4.5 delete-and-pad plus a duplicated whole §A.1 section at EOF.
    lines = text.split("\n")
    del lines[_line_starting_with(lines, "| Axis label |")]
    i = _line_starting_with(lines, "| Cursors |")
    lines.insert(i + 1, lines[i])
    start = _line_starting_with(lines, "### §A.1 Colour palette")
    end = _line_starting_with(lines, "### §A.2 Spacing and layout")
    section = lines[start:end]
    section_pad = "\n".join(lines).rstrip("\n") + "\n\n" + "\n".join(section)

    return {
        "cross-table-row-swap": (
            [(SLUG_E41, DEFECT_WRONG_ROW_KEYS), (SLUG_E45, DEFECT_WRONG_ROW_KEYS)],
            swap,
        ),
        "mid-table-interleave": ([(SLUG_E1, DEFECT_TABLE_INTERRUPTED)], interleave),
        "token-delete-and-pad": ([(SLUG_A1, DEFECT_WRONG_ROW_KEYS)], token_pad),
        "delete-and-pad-plus-duplicate-section": (
            [(SLUG_E45, DEFECT_WRONG_ROW_KEYS)],
            section_pad,
        ),
    }


@pytest.mark.parametrize("arm", sorted(_identity_mutations()))
def test_f1_identity_mutations_red_their_pins(arm: str, tmp_path: Path) -> None:
    expected, mutated = _identity_mutations()[arm]
    scratch = tmp_path / arm
    scratch.mkdir()
    (scratch / "ui-contract.md").write_text(mutated, encoding="utf-8")
    junit = tmp_path / f"{arm}.xml"
    # G1b: registration neutralized (the arms pin G1a's parser identity
    # classes; a registration-live mutation reds via the orphan check first).
    exit_code = _run(scratch / "ui-contract.md", junit, prelude=NEUTRALIZE_REGISTRATION)
    _attrib, buckets = _suite(junit)
    pin_failures = _failure_texts(buckets["pin"])
    for slug, defect_class in expected:
        assert exit_code != 0, arm
        assert slug in pin_failures, f"{arm}: {slug} pin must fail: {sorted(pin_failures)}"
        message = pin_failures[slug]
        assert defect_class in message, f"{arm}: need {defect_class!r} in: {message}"
    assert _stats(buckets["row"])["passed"] == 0


# --- F1 fold: the orphan check (delete-with-registered-artifact) ---------------


FULL_REGISTRATION_PRELUDE = """
import benchweave_ui_html.manifest as manifest
import benchweave_ui_html.registry as registry

class _Fake:
    def __init__(self, kind):
        self.kind = kind

    def satisfies(self, row):
        return []

for _table in manifest.MANIFEST:
    for _key in _table.keys:
        registry.REGISTRY.register(f"{_table.slug}::{_key}", _Fake(_table.kind))
"""


def test_full_registration_runs_fully_green_on_the_pristine_contract(tmp_path: Path) -> None:
    """The G1b end-state control: every manifest key registered, no orphans —
    196 passed, exit 0, and no false positive from the orphan check."""
    junit = tmp_path / "full-green.xml"
    exit_code = _run(CONTRACT, junit, prelude=FULL_REGISTRATION_PRELUDE)
    assert exit_code == 0
    attrib, buckets = _suite(junit)
    assert attrib.get("tests") == "196", attrib
    assert attrib.get("failures") == "0", attrib
    assert _stats(buckets["row"]) == {
        "collected": ROW_ITEMS,
        "failed": 0,
        "passed": ROW_ITEMS,
        "skipped": 0,
    }
    assert buckets["other"] == []


def test_delete_and_pad_with_full_registration_reds_via_orphaned_artifact(
    tmp_path: Path,
) -> None:
    """The forward kill, closed: delete the button row and pad with a
    duplicate so every PARSED row still has its artifact — the deleted row's
    registered artifact is orphaned and the run must red naming it."""
    lines = CONTRACT.read_text(encoding="utf-8").split("\n")
    del lines[_line_starting_with(lines, "| `button` |")]
    i = _line_starting_with(lines, "| `panel` |")
    lines.insert(i + 1, lines[i])
    scratch = tmp_path / "orphan"
    scratch.mkdir()
    (scratch / "ui-contract.md").write_text("\n".join(lines), encoding="utf-8")
    junit = tmp_path / "orphan.xml"
    exit_code = _run(
        scratch / "ui-contract.md", junit, prelude=FULL_REGISTRATION_PRELUDE
    )
    assert junit.exists(), "the measured run must have run (RED if the prelude crashed)"
    assert exit_code != 0, "an orphaned artifact must leave the run red"
    root = ET.parse(junit).getroot()  # noqa: S314 - our own subprocess's junitxml, not untrusted input
    everything = " ".join(root.itertext())
    assert "orphaned artifact" in everything, everything[:400]
    assert "e-1-components::button" in everything, everything[:400]


# --- F2 fold: a mixed invocation carries the gate -------------------------------


def test_mixed_invocation_collects_the_gate(tmp_path: Path) -> None:
    """F2 residual pin: `pytest tests/... docs/internal/ui-contract.md`
    collects BOTH the ordinary suite and the 196 contract items. The refuter's
    PYTEST_ADDOPTS="-m 'not contract'" attack deselects the contract items on
    exactly this shape — the residual class, disclosed in the design record;
    this arm goes red under that attack."""
    junit = tmp_path / "mixed.xml"
    exit_code = _run(
        CONTRACT,
        junit,
        extra_args=["tests/ui_html/test_grammar.py"],
    )
    assert exit_code != 0  # the row layer is red at the empty registry
    _attrib, buckets = _suite(junit)
    assert _stats(buckets["pin"])["collected"] == PIN_ITEMS
    assert _stats(buckets["row"])["collected"] == ROW_ITEMS
