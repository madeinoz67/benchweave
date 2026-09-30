"""The why surface: VR-40's constraint -> locked-version explanation (#233 D5).

Design record ``.claude/deep-review/2026-09-29-issue233-register-design.md``
§3 (owner-fired trigger, disclosed there): the four-rung ladder in
``resolve_package`` computed each row's rung and discarded it; the slice
records provenance inside the loop and renders it. Acceptance is the
record's pre-committed §3.7:

- **M1** rung discrimination — 8 planted fixtures, 2 per rung; any
  misnamed rung kills the slice.
- **M2** no-lie equality — why's rendered version map equals
  ``resolve_package``'s resolved map across the dependency corpus's lock
  fixtures. Pre-committed underpowered rule: the precise-override rung is
  a call-time input, so no on-disk lock fixture can produce it; if fewer
  than four distinct rungs occur across the sweep, M2 is recorded
  underpowered and M1 is the operative proof.
- **M3** read-only — ``why`` on a clean tree leaves ``git status
  --porcelain`` empty, before and after, pinned by test.
- **RED control** — neutralizing the in-loop provenance recording must
  fail M1 (and M2 with it); the tests test the mechanism, not the fixture.

The fixtures reuse the dependency corpus's own builders (``test_dependency``,
``test_dev_pins``) — no second fixture lattice, and the sweep enumerates the
corpus's lock-fixture shapes, each named with the corpus test it mirrors.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from test_dependency import (
    _SYNTHETIC_CONSTRAINTS,
    _add_otdp_version,
    _copy_standards,
    _run,
)
from test_dependency import (
    _package as _plain_package,
)
from test_dev_pins import (
    HEAD_LABEL,
    _git,
    _git_root,
)
from test_dev_pins import (
    _package as _dev_package,
)

from benchweave.standards.dependency import resolve_package, why_lines
from benchweave.standards.export import canonical_json
from benchweave.standards.manifest import StandardsError

#: The four rung names — the why surface's public vocabulary.
RUNG_DEV = "dev-opt-in"
RUNG_PRECISE = "precise-override"
RUNG_PRIOR = "prior-retained"
RUNG_AUTO = "auto-highest-served"

ROOT = Path(__file__).resolve().parents[2]


# --- M1: rung discrimination — 8 planted fixtures, 2 per rung ---------------------


def _arm_dev_plain(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, str], bool]:
    """The canonical dev arm: an opt-in pin resolves from the object store."""
    root, sha = _git_root(tmp_path)
    package = _dev_package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    return root, package, {}, {"otdp": RUNG_DEV}, True


def _arm_dev_with_neighbour(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, str], bool]:
    """The dev row must not disturb its neighbours' rungs: one fixture, two
    rungs (dev-opt-in beside auto-highest-served)."""
    root, sha = _git_root(tmp_path)
    package = _dev_package(
        root,
        constraints={"otdp": ">=0.2.0,<0.3.0", "registry": ">=0.1.0,<0.2.0"},
        opt_in={"otdp": f"{HEAD_LABEL}@{sha}"},
    )
    return (
        root,
        package,
        {},
        {"otdp": RUNG_DEV, "registry": RUNG_AUTO},
        True,
    )


def _arm_precise_served(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, str], bool]:
    """The precise arm to a served target: the override wins over the prior.
    The synthetic 0.2.10 is the target because its directory is fully
    corpus-rowed (the helper rows every file) — a resolution onto the real
    0.2.2 directory from a 0.2.0 prior hits the corpus's stray-file gate."""
    root = _copy_standards(tmp_path)
    _add_otdp_version(root, "0.2.10")
    package = _plain_package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    return root, package, {"precise": {"otdp": "0.2.10"}}, {"otdp": RUNG_PRECISE}, False


def _arm_precise_yanked(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, str], bool]:
    """The precise arm to a yanked target: still precise-override, with the
    deprecation warning riding the resolution (the Q10 ruling). The yank is
    a synthetic policy row over the fully-rowed synthetic version."""
    root = _copy_standards(tmp_path)
    _add_otdp_version(root, "0.2.10")
    manifest_path = root / "standards" / "standards-manifest.json"
    document = json.loads(manifest_path.read_bytes())
    document["dependency_policy"]["standards"]["otdp"]["yanked"]["0.2.10"] = {
        "reason": "fixture yank (synthetic)",
        "since": "2026-09-29",
    }
    manifest_path.write_bytes(canonical_json(document))
    package = _plain_package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    return root, package, {"precise": {"otdp": "0.2.10"}}, {"otdp": RUNG_PRECISE}, False


def _arm_prior_held(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, str], bool]:
    """The synthetic three-standard fixture: prior otdp retained, the other
    two auto-selected (mirrors the corpus's minimal-motion test)."""
    root = _copy_standards(tmp_path)
    package = _plain_package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    return (
        root,
        package,
        {},
        {
            "otdp": RUNG_PRIOR,
            "plugin-ui": RUNG_AUTO,
            "registry": RUNG_AUTO,
        },
        True,
    )


def _arm_prior_yanked(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, str], bool]:
    """A prior AT the yanked version is still prior-retained (minimal motion;
    the deprecation warning rides along) — mirrors the corpus's R7 test."""
    root = _copy_standards(tmp_path)
    package = _plain_package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.1")
    return (
        root,
        package,
        {},
        {
            "otdp": RUNG_PRIOR,
            "plugin-ui": RUNG_AUTO,
            "registry": RUNG_AUTO,
        },
        True,
    )


def _arm_auto_without_prior_row(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, str], bool]:
    """registry has no prior row at all (a v1 lock carries only the otdp
    projection) and otdp's prior 9.9.9 is out of interval: both auto-select.
    The synthetic 0.2.10 is planted because only its directory is fully
    corpus-rowed — a resolution onto the real 0.2.2 directory from an empty
    prior map hits the corpus's stray-file gate (the F3 latecomers)."""
    root = _copy_standards(tmp_path)
    _add_otdp_version(root, "0.2.10")
    package = _plain_package(
        root,
        constraints={"otdp": ">=0.2.0,<0.3.0", "registry": ">=0.1.0,<0.2.0"},
        otdp_version="9.9.9",
    )
    return (
        root,
        package,
        {},
        {"otdp": RUNG_AUTO, "registry": RUNG_AUTO},
        True,
    )


def _arm_auto_version_ordered(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, str], bool]:
    """0.2.10 planted (the corpus's F1 helper): auto-selection must pick it
    over 0.2.2 by version order and name 0.2.1 as the yanked exclusion."""
    root = _copy_standards(tmp_path)
    _add_otdp_version(root, "0.2.10")
    package = _plain_package(
        root, constraints={"otdp": ">=0.2.0,<0.3.0"}, otdp_version="9.9.9"
    )
    return root, package, {}, {"otdp": RUNG_AUTO}, True


_M1_ARMS = [
    _arm_dev_plain,
    _arm_dev_with_neighbour,
    _arm_precise_served,
    _arm_precise_yanked,
    _arm_prior_held,
    _arm_prior_yanked,
    _arm_auto_without_prior_row,
    _arm_auto_version_ordered,
]


@pytest.mark.parametrize("arm", _M1_ARMS, ids=lambda arm: arm.__name__)
def test_m1_rung_discrimination(tmp_path: Path, arm: Any) -> None:
    """Each planted fixture must name its rung — via the recorded provenance
    and, where the rung is reachable from on-disk state, via the rendered
    why output and the CLI. KILL: any misnamed rung."""
    root, package, kwargs, expected, cli_reachable = arm(tmp_path)
    resolution = resolve_package(root, package, **kwargs)
    for standard_id, rung in expected.items():
        assert resolution.provenance[standard_id].rung == rung, standard_id
    if not kwargs:
        # The why render has no precise input (design §3.3: `why [--package]`),
        # so a call-time precise arm is named by the recorded provenance only.
        lines = why_lines(root, package)
        assert any(
            f"— {rung}" in line for standard_id, rung in expected.items() for line in lines
        )
    if cli_reachable and not kwargs:
        result = _run(root, "why", "--package", "plugins/acme/widget")
        assert result.returncode == 0, result.stderr
        assert "Traceback" not in result.stderr
        for standard_id, rung in expected.items():
            assert f"{standard_id}@" in result.stdout, standard_id
            assert rung in result.stdout, rung


def test_m1_the_render_reads_provenance_not_a_rung_rederivation(tmp_path: Path) -> None:
    """The why render names the rung the loop recorded, per row, from
    ``Resolution.provenance`` — a row's line carries its own rung, so a
    second ladder in the renderer would be the design-level kill."""
    root = _copy_standards(tmp_path)
    package = _plain_package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.1")
    lines = why_lines(root, package)
    otdp_line = next(line for line in lines if line.startswith("otdp@"))
    assert otdp_line == "otdp@0.2.1 — prior-retained"
    auto_line = next(line for line in lines if line.startswith("registry@"))
    assert auto_line.split(" — ", 1)[1] == RUNG_AUTO


# --- M2: no-lie equality — why's rendered map equals the resolved map --------------


_WHY_ROW = re.compile(r"^([a-z][a-z0-9-]*)@(.+?)(?: \(dev\))?$")


def _why_map(lines: list[str]) -> dict[str, str]:
    """The version map the render names: one row per top-level
    ``<id>@<version>`` line (drift/warning lines carry no such shape)."""
    rendered: dict[str, str] = {}
    for line in lines:
        head = line.split(" — ", 1)[0]
        match = _WHY_ROW.match(head)
        if match is not None:
            rendered[match.group(1)] = match.group(2)
    return rendered


def _doc_map(resolution: Any) -> dict[str, str]:
    return {
        str(row["id"]): str(row["version"]) for row in resolution.document["standards"]
    }


_M2_SCENARIOS = [
    (
        "synthetic-prior-held",
        _arm_prior_held,
        "test_b1_synthetic_pin_is_deterministic_and_minimal",
    ),
    ("yanked-prior-held", _arm_prior_yanked, "test_b1_prior_yanked_retention"),
    (
        "auto-version-ordered",
        _arm_auto_version_ordered,
        "test_f1_auto_selection_is_version_ordered",
    ),
    (
        "auto-without-prior-row",
        _arm_auto_without_prior_row,
        "test_b1_synthetic_pin (registry row)",
    ),
    ("dev-opt-in", _arm_dev_plain, "test_dev_pins D2/D3 shapes"),
]


@pytest.mark.parametrize(
    ("name", "build", "mirrors"),
    _M2_SCENARIOS,
    ids=[row[0] for row in _M2_SCENARIOS],
)
def test_m2_why_map_equals_the_resolved_map(
    tmp_path: Path, name: str, build: Any, mirrors: str
) -> None:
    """No-lie equality: for every lock-fixture shape the dependency corpus
    constructs, the map the why render names equals ``resolve_package``'s
    resolved map exactly. KILL: any divergence.

    Underpowered rule (design §3.7, measured): the sweep's distinct rungs
    are prior-retained, auto-highest-served and dev-opt-in — three kinds;
    precise-override is a call-time input no on-disk lock fixture can
    produce, so this control is recorded UNDERPOWERED and M1 is the
    operative proof, per the pre-committed rule.
    """
    root, package, kwargs, _expected, _cli = build(tmp_path)
    resolution = resolve_package(root, package, **kwargs)
    lines = why_lines(root, package)
    assert _why_map(lines) == _doc_map(resolution), name


def test_m2_the_real_shipped_package_agrees() -> None:
    """The corpus's real-package arm (mirrors test_f3_c exactly, against the
    committed tree): the shipped DPS-150 package's why map equals its
    resolution exactly."""
    package = ROOT / "plugins" / "fnirsi" / "dps150"
    resolution = resolve_package(ROOT, package)
    assert _why_map(why_lines(ROOT, package)) == _doc_map(resolution)


def test_m2_refusals_propagate_identically(tmp_path: Path) -> None:
    """A fixture the corpus refuses (registry-only constraints, no otdp):
    why raises the same typed refusal the resolver raises — the why surface
    reuses refusals, it never catches and paraphrases them."""
    root = _copy_standards(tmp_path)
    package = _plain_package(root, constraints={"registry": ">=0.1.0,<0.2.0"})
    with pytest.raises(StandardsError) as from_resolver:
        resolve_package(root, package)
    with pytest.raises(StandardsError) as from_why:
        why_lines(root, package)
    assert str(from_why.value).startswith(str(from_resolver.value).split(":")[0])


def test_m2_the_dev_refusal_propagates_verbatim(tmp_path: Path) -> None:
    """The design's top risk: a why surface must never soften a mechanism
    refusal. With the object store removed (the wheel posture) the dev
    opt-in refuses ``dev_head_unresolvable:`` — unchanged, by name."""
    root, sha = _git_root(tmp_path)
    package = _dev_package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    shutil.rmtree(root / ".git")
    with pytest.raises(StandardsError, match="dev_head_unresolvable:") as from_resolver:
        resolve_package(root, package)
    with pytest.raises(StandardsError, match="dev_head_unresolvable:") as from_why:
        why_lines(root, package)
    assert str(from_why.value) == str(from_resolver.value)


# --- M3: read-only — a clean tree stays clean --------------------------------------


def test_m3_why_leaves_the_tree_clean(tmp_path: Path) -> None:
    """``why`` on a clean tree leaves ``git status --porcelain`` empty,
    before and after, through both the API and the CLI. KILL: any write."""
    root, sha = _git_root(tmp_path)
    package = _dev_package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-q", "-m", "plant package")
    before = _git(root, "status", "--porcelain")
    assert before == ""
    lines = why_lines(root, package)
    assert lines
    assert _git(root, "status", "--porcelain") == ""
    result = _run(root, "why", "--package", "plugins/acme/widget")
    assert result.returncode == 0, result.stderr
    assert _git(root, "status", "--porcelain") == ""


# --- the drift section: the per-row story plugin_lock_drift cannot produce ---------


def test_the_drift_section_names_each_diverging_row(tmp_path: Path) -> None:
    """When the authored constraints narrow under a committed lock (the
    ``plugin_lock_drift`` feeder — the corpus's b5 hand-edit), the
    resolution moves off the prior row and why names that row and both its
    versions. A tree whose lock agrees renders ``drift none``. A
    values-identical reflow (the drift refusal's fourth hypothesis) shows
    no row divergence here: byte-form drift is the refusal's story, value
    drift is why's, by design."""
    root = _copy_standards(tmp_path)
    package = _plain_package(root, constraints=_SYNTHETIC_CONSTRAINTS)
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    agreeing = why_lines(root, package)
    assert any(line.startswith("drift none") for line in agreeing)
    constraints = json.loads((package / "contracts" / "constraints.json").read_bytes())
    constraints["standards"]["otdp"] = ">=0.2.0,<0.2.2"  # the prior 0.2.2 no longer fits
    (package / "contracts" / "constraints.json").write_bytes(canonical_json(constraints))
    lines = why_lines(root, package)
    drift_rows = [line for line in lines if line.startswith("drift ")]
    assert drift_rows == ["drift otdp: 0.2.2 -> 0.2.0"], drift_rows


def test_why_cli_refuses_styled(tmp_path: Path) -> None:
    """The CLI lane: a typed refusal reaches the operator styled, never as a
    traceback (the list/pin family's posture)."""
    root = _copy_standards(tmp_path)
    _plain_package(root, constraints={"registry": ">=0.1.0,<0.2.0"})
    result = _run(root, "why", "--package", "plugins/acme/widget")
    assert result.returncode == 1
    assert "standards why error: lock_otdp_absent" in result.stderr
    assert "Traceback" not in result.stderr
