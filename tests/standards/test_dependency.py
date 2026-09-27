"""The dependency resolver surface: intervals, caret expansion, classification.

Issue #216 (#203 slice 2, design record §1.1): the resolver is a pure
function of committed bytes plus authored constraints; caret sugar is
authoring input expanded at the CLI boundary and refused wherever it is
found stored; yanked/retired/unknown are three answers with one comparator,
every refusal carrying the five VR-37 fields inline.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from benchweave.standards.dependency import (
    Interval,
    apply_set,
    classify_pin,
    expand_caret,
    load_constraints,
    load_prior_lock,
)
from benchweave.standards.export import canonical_json
from benchweave.standards.manifest import StandardsError, load_dependency_policy

ROOT = Path(__file__).resolve().parents[2]


def _copy_standards(tmp_path: Path) -> Path:
    """A non-git root carrying the real standards tree, mutable per test."""
    root = tmp_path / "root"
    root.mkdir()
    shutil.copytree(ROOT / "standards", root / "standards")
    return root


def _package(
    root: Path,
    *,
    constraints: dict[str, str] | None,
    otdp_version: str = "0.2.2",
) -> Path:
    """A synthetic in-tree package over the copied standards tree.

    The v1 prior lock carries only the provenance keys plus the otdp
    projection's version: the v2 writer re-derives every other projection
    value, so the fixture never needs a real file map.
    """
    package = root / "plugins" / "acme" / "widget"
    (package / "contracts").mkdir(parents=True)
    if constraints is not None:
        (package / "contracts" / "constraints.json").write_bytes(
            canonical_json(
                {"constraint_version": 1, "standards": constraints, "opt_in": {}}
            )
        )
    (package / "contracts" / "lock.json").write_text(
        json.dumps(
            {
                "repository": "https://example.invalid/acme-widget",
                "revision": "0" * 40,
                "directory": f"standards/otdp/{otdp_version}",
                "otdp_version": otdp_version,
                "adapter_api_version": "1.1",
                "sha256": {"otdp-specification.md": "0" * 64},
            }
        )
    )
    return package


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "benchweave.standards", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


# --- B3: caret expansion is one pure function; sugar never persists ---------------


@pytest.mark.parametrize(
    ("value", "lower", "upper"),
    [
        ("^0.2", "0.2.0", "0.3.0"),
        ("^0.2.5", "0.2.5", "0.3.0"),
        ("^0.0.3", "0.0.3", "0.0.4"),
        ("^1.2.3", "1.2.3", "2.0.0"),
        ("^0.0", "0.0.0", "0.1.0"),
    ],
)
def test_b3_expand_caret_table(value: str, lower: str, upper: str) -> None:
    """The 0.x table: 0.x bumps the MINOR position, 0.0.x the PATCH position,
    x>=1 the MAJOR position (design §1.1)."""
    interval = expand_caret(value)
    assert (interval.lower, interval.upper) == (lower, upper)
    assert interval.text() == f">={lower},<{upper}"


def test_b3_zero_minor_boundary_is_not_the_major_jump() -> None:
    """Design risk 3's falsifier: ``^0.2`` is NOT ``>=0.2.0,<1.0.0``."""
    interval = expand_caret("^0.2")
    assert interval.upper == "0.3.0"
    assert interval.contains("0.2.2")
    assert not interval.contains("1.0.0")


@pytest.mark.parametrize(
    "value",
    ["^0", "~1.2", "~1", "^1", "0.2", ">=0.2.0,<0.3.0", "^x.y", "^0.2.3.4", "^01.2"],
)
def test_b3_unexpandable_authoring_sugar_refuses(value: str) -> None:
    """Sugar beyond the caret table refuses ``constraint_syntax_unexpanded:`` —
    sugar is authoring input only, never silently interpreted."""
    with pytest.raises(StandardsError, match="constraint_syntax_unexpanded"):
        expand_caret(value)


def test_b3_interval_grammar_round_trips_through_text() -> None:
    interval = expand_caret("^1.2.3")
    assert Interval(lower="1.2.3", upper="2.0.0") == interval
    assert interval.contains("1.9.9")
    assert not interval.contains("2.0.0")  # half-open: the upper bound is excluded
    assert not interval.contains("1.2.2")


def test_b3_stored_caret_in_constraints_refuses(tmp_path: Path) -> None:
    """A caret persisted in any committed file refuses — the loader never
    expands it (mirroring ``manifest.py::_parse_range``)."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": "^0.2"})
    with pytest.raises(StandardsError, match="constraint_syntax_unexpanded"):
        load_constraints(package)


def test_b3_stored_caret_in_the_lock_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    lock = json.loads((package / "contracts" / "lock.json").read_text())
    lock["otdp_version"] = "^0.2"
    (package / "contracts" / "lock.json").write_text(json.dumps(lock))
    with pytest.raises(StandardsError, match="constraint_syntax_unexpanded"):
        load_prior_lock(package)


def test_b3_set_expands_the_caret_into_the_authored_file(tmp_path: Path) -> None:
    """The authoring path accepts ``^0.2`` and writes the expanded interval;
    a caret never persists into the committed file."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    apply_set(root, package, [("otdp", "^0.2")])
    raw = (package / "contracts" / "constraints.json").read_text()
    document = json.loads(raw)
    assert document["standards"]["otdp"] == ">=0.2.0,<0.3.0"
    assert "^" not in raw and "~" not in raw


def test_b3_set_refuses_an_unknown_standard_before_writing(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    before = (package / "contracts" / "constraints.json").read_bytes()
    with pytest.raises(StandardsError, match="constraint_standard_unknown"):
        apply_set(root, package, [("nonexistent", "^0.2")])
    assert (package / "contracts" / "constraints.json").read_bytes() == before


# --- B4: retired / unknown / not-served are three answers, one comparator --------


def test_b4_retired_identifier_is_distinct_from_unknown(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="retired_identifier") as retired:
        classify_pin(policy, root, "otdp", "0.3.0")
    with pytest.raises(StandardsError, match="version_unknown") as unknown:
        classify_pin(policy, root, "otdp", "9.9.9")
    assert str(retired.value) != str(unknown.value)


@pytest.mark.parametrize(
    ("version", "prefix"),
    [
        ("0.3.0", "retired_identifier"),
        ("9.9.9", "version_unknown"),
        ("0.1.2", "version_not_served"),
    ],
)
def test_b4_refusals_carry_the_five_vr37_fields(
    tmp_path: Path, version: str, prefix: str
) -> None:
    """Standard, pinned version, supported range, move-to, migration-note
    pointer — all five inline on every classification refusal."""
    root = _copy_standards(tmp_path)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match=prefix) as raised:
        classify_pin(policy, root, "otdp", version)
    message = str(raised.value)
    assert "otdp" in message
    assert version in message
    assert ">=0.2.0,<0.3.0" in message  # the supported range, verbatim
    assert "move-to: 0.2.2" in message  # the derived move-to (highest served)
    assert "migration guidance pending" in message


def test_b4_retired_names_the_next_minor_retarget(tmp_path: Path) -> None:
    """The re-target hint: a retired identifier never resolves again, and the
    refusal says where the namespace went."""
    root = _copy_standards(tmp_path)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="next minor is 0.4.0"):
        classify_pin(policy, root, "otdp", "0.3.0")


def test_b4_dev_shape_refuses_naming_slice_four(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="dev_pin_unsupported") as raised:
        classify_pin(policy, root, "otdp", "0.3.0-dev")
    assert "slice 4" in str(raised.value)


def test_b4_pre_release_suffix_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="version_shape_invalid"):
        classify_pin(policy, root, "otdp", "0.2.2-rc.1")


def test_b4_yanked_pin_classifies_with_a_deprecation_warning(tmp_path: Path) -> None:
    """An explicit pin to a yanked-in-interval version stays conforming —
    with a warning naming the derived move-to."""
    root = _copy_standards(tmp_path)
    policy = load_dependency_policy(root)
    classification = classify_pin(policy, root, "otdp", "0.2.1")
    assert classification.state == "yanked"
    assert classification.warning is not None
    assert "0.2.2" in classification.warning


def test_b4_served_pin_classifies_clean(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    policy = load_dependency_policy(root)
    classification = classify_pin(policy, root, "otdp", "0.2.2")
    assert classification.state == "served"
    assert classification.warning is None


def test_b4_cli_upgrade_retired_refuses_styled(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    result = _run(
        root, "upgrade", "otdp", "--precise", "0.3.0", "--package", "plugins/acme/widget"
    )
    assert result.returncode == 1
    assert "standards upgrade error: retired_identifier" in result.stderr
    assert "next minor is 0.4.0" in result.stderr
    assert "Traceback" not in result.stderr


def test_b4_cli_upgrade_unknown_refuses_styled(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    result = _run(
        root, "upgrade", "otdp", "--precise", "9.9.9", "--package", "plugins/acme/widget"
    )
    assert result.returncode == 1
    assert "standards upgrade error: version_unknown" in result.stderr
    assert "Traceback" not in result.stderr


def test_b4_cli_refusal_prefixes_differ(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    retired = _run(
        root, "upgrade", "otdp", "--precise", "0.3.0", "--package", "plugins/acme/widget"
    )
    unknown = _run(
        root, "upgrade", "otdp", "--precise", "9.9.9", "--package", "plugins/acme/widget"
    )
    assert retired.stderr != unknown.stderr


# --- the list render --------------------------------------------------------------


def test_list_renders_every_standard_deterministically(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    result = _run(root, "list")
    assert result.returncode == 0
    for identifier in (
        "otdp",
        "registry",
        "execution",
        "interface",
        "plugin-ui",
        "plugin-ui-preview",
    ):
        assert f"standard {identifier}@" in result.stdout
    assert "yanked 0.2.1" in result.stdout
    assert "retired 0.3.0" in result.stdout
    again = _run(root, "list")
    assert result.stdout == again.stdout
