"""The dependency resolver surface: intervals, caret expansion, classification.

Issue #216 (#203 slice 2, design record §1.1): the resolver is a pure
function of committed bytes plus authored constraints; caret sugar is
authoring input expanded at the CLI boundary and refused wherever it is
found stored; yanked/retired/unknown are three answers with one comparator,
every refusal carrying the five VR-37 fields inline.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from benchweave.standards.dependency import (
    Interval,
    apply_set,
    classify_pin,
    expand_caret,
    load_constraints,
    load_prior_lock,
    normalized_equal,
    resolve_package,
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


# --- B1/B2: the writer — determinism and minimal motion ---------------------------


_SYNTHETIC_CONSTRAINTS = {
    "otdp": ">=0.2.0,<0.3.0",
    "plugin-ui": ">=0.2.0,<0.3.0",
    "registry": ">=0.1.0,<0.2.0",
}


#: The DPS-150 v1 lock's committed bytes at the slice's merge base (the
#: historical shape the v2 relock must preserve — the repository's own lock
#: is v2 from this slice on, so the fixture carries the v1 prior).
_DPS150_V1_LOCK: dict[str, Any] = {
    'repository': 'https://github.com/madeinoz67/benchweave',
    'revision': '8a080d149ebfb972f5ab697c252c73f9ebec4019',
    'directory': 'standards/otdp/0.2.2',
    'otdp_version': '0.2.2',
    'adapter_api_version': '1.1',
    "sha256": {
        'otdp-device-descriptor.schema.json':
            'e43fe4583f5f118415f7fbf3dbe55ff681d4ee1e9dd3d4758e93207d9f07e11f',
        'otdp-runtime.schema.json':
            'd2e62a22a118aad11e247c7a087947b24cf8fcf7c1cc3c77a71b5a249f8342ea',
        'otdp-specification.md': '6469e40d9e98a2e52857c0165091fd639e47475893e66a6cc593ed4452c427e6',
        'extension-contract.md': '3595b6655b012af350ccda1a4715c3515cdfbe8163120cc6f369d08922e5e627',
        'device-classes.md': '712ec652c85033f84e79b4679e6756d9bf0eab93af319c55ca45b5962b0a3860',
        'measurement-model.md': '1d40f0c32676149d360c127c6c974a2e227b2dfd190d9044fec24d8c3312305e',
        'otdp-measurement.schema.json':
            '7905795bed6139b9705edfa17b7a17226b99cddda6656030d73bb63dc998a4b3',
        'device-profile-catalog.json':
            '2e8c7841a397f794724ab2f484e7531cef47889c5f514ed68ff2c1273f0b493c',
    },
}


def _dps150_copy(tmp_path: Path) -> Path:
    """The real DPS-150 package (constraints from the committed file; the
    v1 lock planted from its historical bytes) over a copied standards tree."""
    root = _copy_standards(tmp_path)
    package = root / "plugins" / "fnirsi" / "dps150"
    (package / "contracts").mkdir(parents=True)
    shutil.copy(
        ROOT / "plugins" / "fnirsi" / "dps150" / "contracts" / "constraints.json",
        package / "contracts" / "constraints.json",
    )
    (package / "contracts" / "lock.json").write_text(
        json.dumps(_DPS150_V1_LOCK, indent=2)
    )
    return root


def _lock_path(package: Path) -> Path:
    return package / "contracts" / "lock.json"


def _rows(raw: bytes) -> dict[str, dict[str, object]]:
    return {str(row["id"]): row for row in json.loads(raw)["standards"]}


def test_b1_resolve_twice_is_byte_identical(tmp_path: Path) -> None:
    """n=2 runs, same inputs: byte-identical locks. KILL: any diff."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    first = resolve_package(root, package)
    second = resolve_package(root, package)
    assert first.raw == second.raw
    assert first.raw == resolve_package(root, package).raw


def test_b1_synthetic_pin_is_deterministic_and_minimal(tmp_path: Path) -> None:
    """The prior otdp 0.2.0 stays (minimal motion: prior ∧ in-interval ∧
    served), plugin-ui and registry resolve to their highest served."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    result = _run(root, "pin", "--package", "plugins/acme/widget")
    assert result.returncode == 0, result.stderr
    raw = _lock_path(package).read_bytes()
    rows = _rows(raw)
    assert [row["version"] for row in (rows["otdp"], rows["plugin-ui"], rows["registry"])] == [
        "0.2.0",
        "0.2.0",
        "0.1.1",
    ]
    again = _run(root, "pin", "--package", "plugins/acme/widget")
    assert again.returncode == 0, again.stderr
    assert _lock_path(package).read_bytes() == raw  # idempotent re-pin


def test_b1_dps150_pin_is_deterministic_with_values_verbatim(tmp_path: Path) -> None:
    """The real package: v1 lock relocks to v2 with every legacy VALUE
    preserved verbatim (repository, revision, directory, otdp and adapter
    API versions), the byte-form reformatted once to canonical JSON, and a
    second pin a no-op.

    The file map is a SUPERSET of the v1 map with identical digests: the
    v1 lock's 8-file set predates four top-level files that later landed in
    the 0.2.2 directory (05354b4's catalog schema and validation report,
    a103a4c's transport-provider schema and prose) — a pre-existing staleness
    nothing verified, disclosed as a design-premise break (the record's
    premise table says 8 files). The derived map covers every top-level
    file of the directory; the digests the v1 lock carried are unchanged.
    """
    root = _dps150_copy(tmp_path)
    package = root / "plugins" / "fnirsi" / "dps150"
    first = _run(root, "pin", "--package", "plugins/fnirsi/dps150")
    assert first.returncode == 0, first.stderr
    raw = _lock_path(package).read_bytes()
    document = json.loads(raw)
    v1 = _DPS150_V1_LOCK
    assert document["lock_version"] == 2
    assert document["otdp_version"] == v1["otdp_version"]
    assert document["repository"] == v1["repository"]
    assert document["revision"] == v1["revision"]
    assert document["directory"] == v1["directory"]
    assert document["adapter_api_version"] == v1["adapter_api_version"]
    for name, digest in v1["sha256"].items():
        assert document["sha256"][name] == digest, name
    directory = root / "standards" / "otdp" / str(document["otdp_version"])
    top_level = {path.name for path in directory.iterdir() if path.is_file()}
    assert set(document["sha256"]) == top_level
    second = _run(root, "pin", "--package", "plugins/fnirsi/dps150")
    assert second.returncode == 0, second.stderr
    assert _lock_path(package).read_bytes() == raw


def test_b2_upgrade_otdp_moves_only_the_otdp_projection(tmp_path: Path) -> None:
    """`upgrade otdp --precise 0.2.2` from a 0.2.0 pin: the otdp row and its
    legacy projection move; every other row and the provenance keys stay
    byte-identical. KILL: any collateral row motion."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    before_raw = _lock_path(package).read_bytes()
    before = json.loads(before_raw)
    result = _run(
        root, "upgrade", "otdp", "--precise", "0.2.2", "--package", "plugins/acme/widget"
    )
    assert result.returncode == 0, result.stderr
    after = json.loads(_lock_path(package).read_bytes())
    assert after["otdp_version"] == "0.2.2"
    assert after["directory"] == "standards/otdp/0.2.2"
    # the projection map moves with the row: it is the TARGET directory's
    # top-level file set (0.2.2 carries the transport-provider pair 0.2.0
    # predates — the map is derived, never carried)
    assert set(after["sha256"]) == {
        path.name
        for path in (root / "standards/otdp/0.2.2").iterdir()
        if path.is_file()
    }
    assert after["repository"] == before["repository"]
    assert after["revision"] == before["revision"]
    rows, rows_before = _rows(_lock_path(package).read_bytes()), _rows(before_raw)
    assert rows["plugin-ui"] == rows_before["plugin-ui"]
    assert rows["registry"] == rows_before["registry"]
    assert rows["otdp"]["version"] == "0.2.2"
    assert rows["otdp"]["digest"] != rows_before["otdp"]["digest"]


def test_b2_upgrade_registry_moves_only_the_registry_row(tmp_path: Path) -> None:
    """The motion control: a deliberate registry downgrade (0.1.1 -> 0.1.0)
    moves exactly the registry row — every other row AND the whole legacy
    otdp projection stay byte-identical."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    before_raw = _lock_path(package).read_bytes()
    result = _run(
        root,
        "upgrade",
        "registry",
        "--precise",
        "0.1.0",
        "--package",
        "plugins/acme/widget",
    )
    assert result.returncode == 0, result.stderr
    after_raw = _lock_path(package).read_bytes()
    before, after = json.loads(before_raw), json.loads(after_raw)
    for key in (
        "repository",
        "revision",
        "directory",
        "otdp_version",
        "adapter_api_version",
        "sha256",
    ):
        assert after[key] == before[key], key
    rows, rows_before = _rows(after_raw), _rows(before_raw)
    assert rows["registry"]["version"] == "0.1.0"
    assert rows["otdp"] == rows_before["otdp"]
    assert rows["plugin-ui"] == rows_before["plugin-ui"]


def test_b2_upgrade_plugin_ui_to_its_only_served_version_is_a_no_op(tmp_path: Path) -> None:
    """plugin-ui's served set is {0.2.0} (the F1 narrow range): the design's
    `upgrade plugin-ui --precise 0.2.0` control is the no-op arm — the lock
    stays byte-identical (the DPS-150 0.2.2->0.2.2 pin is the same shape)."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    before_raw = _lock_path(package).read_bytes()
    result = _run(
        root,
        "upgrade",
        "plugin-ui",
        "--precise",
        "0.2.0",
        "--package",
        "plugins/acme/widget",
    )
    assert result.returncode == 0, result.stderr
    assert _lock_path(package).read_bytes() == before_raw


def test_pin_set_end_to_end_expands_and_relocks(tmp_path: Path) -> None:
    """The CLI authoring arm: `pin --set otdp=^0.2` writes the expanded
    interval into the committed constraints and completes the relock."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints=_SYNTHETIC_CONSTRAINTS, otdp_version="0.2.0")
    result = _run(root, "pin", "--set", "otdp=^0.2", "--package", "plugins/acme/widget")
    assert result.returncode == 0, result.stderr
    constraints = json.loads(
        (package / "contracts" / "constraints.json").read_bytes()
    )
    assert constraints["standards"]["otdp"] == ">=0.2.0,<0.3.0"
    assert json.loads(_lock_path(package).read_bytes())["lock_version"] == 2


# --- cross-constraint enforcement at resolve time ---------------------------------


def test_cross_constraint_violation_refuses_at_resolve(tmp_path: Path) -> None:
    """A resolved set combining execution 0.2.0 with an otdp outside the
    row's requirement refuses, naming both versions and the row's evidence."""
    root = _copy_standards(tmp_path)
    cross = root / "standards" / "cross-constraints.json"
    document = json.loads(cross.read_bytes())
    document["rows"][0]["requires"]["otdp"] = ">=0.2.2,<0.3.0"
    cross.write_bytes(canonical_json(document))
    package = _package(
        root,
        constraints={"execution": ">=0.1.0,<0.3.0", "otdp": ">=0.2.0,<0.3.0"},
        otdp_version="0.2.0",
    )
    with pytest.raises(StandardsError, match="cross_constraint_violation") as raised:
        resolve_package(root, package)
    message = str(raised.value)
    assert "execution" in message and "0.2.0" in message
    assert "PR #201" in message  # the row's evidence rides the refusal


def test_a_satisfied_cross_constraint_row_resolves_clean(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    package = _package(
        root,
        constraints={"execution": ">=0.1.0,<0.3.0", "otdp": ">=0.2.0,<0.3.0"},
        otdp_version="0.2.0",
    )
    resolution = resolve_package(root, package)
    rows = {str(row["id"]): str(row["version"]) for row in resolution.document["standards"]}
    assert rows == {"execution": "0.2.0", "otdp": "0.2.0"}


# --- B6: the version-normalized comparator (the Q6 raw-digest control) ------------


_DESCRIPTOR = "otdp-device-descriptor.schema.json"


def test_b6_normalized_comparator_admits_the_version_strings_only_pair() -> None:
    """0.2.1 <-> 0.2.2 differ only in version strings (const, $id, title,
    description — the verified 4-line diff); the normalized comparator
    admits the pair."""
    a = ROOT / "standards/otdp/0.2.1" / _DESCRIPTOR
    b = ROOT / "standards/otdp/0.2.2" / _DESCRIPTOR
    assert normalized_equal(a, b, "0.2.1", "0.2.2")


def test_b6_a_raw_digest_comparator_fails_the_same_pair() -> None:
    """The control both asserted: a raw sha256 comparison on the same pair
    FAILS — the normalization is doing the work."""
    a = ROOT / "standards/otdp/0.2.1" / _DESCRIPTOR
    b = ROOT / "standards/otdp/0.2.2" / _DESCRIPTOR
    assert hashlib.sha256(a.read_bytes()).digest() != hashlib.sha256(b.read_bytes()).digest()


def test_b6_normalized_comparator_refuses_the_structural_pair() -> None:
    """0.2.0 <-> 0.2.2 differ by the provider element in $defs.customTransport
    (verified live); the comparator has teeth — it is not everything-equals.
    KILL: admitting 0.2.0 <-> 0.2.2."""
    a = ROOT / "standards/otdp/0.2.0" / _DESCRIPTOR
    b = ROOT / "standards/otdp/0.2.2" / _DESCRIPTOR
    assert not normalized_equal(a, b, "0.2.0", "0.2.2")


# --- B5: offline drift and the agreement lane --------------------------------------


class _SocketCounter:
    """Counts attempts instead of blocking them: zero is the proof."""

    def __init__(self) -> None:
        self.attempts = 0

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.attempts += 1
        raise AssertionError("network attempt during offline resolution")


@pytest.fixture
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> _SocketCounter:
    """The five SOCKET_GUARD names from scripts/adc_conformance_control.py,
    monkeypatched with a counter: B5's proof that resolution makes ZERO
    network attempts, offline by construction."""
    import socket

    counter = _SocketCounter()
    monkeypatch.setattr(socket.socket, "connect", counter)
    monkeypatch.setattr(socket.socket, "connect_ex", counter)
    monkeypatch.setattr(socket, "create_connection", counter)
    monkeypatch.setattr(socket, "getaddrinfo", counter)
    monkeypatch.setattr(socket, "gethostbyname", counter)
    return counter


def test_b5_a_hand_edited_constraint_fails_locked(tmp_path: Path) -> None:
    """Narrowing the authored interval after the lock was written changes
    the resolution; ``pin --locked`` refuses ``plugin_lock_drift:`` without
    writing."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    locked = _lock_path(package).read_bytes()
    constraints = json.loads((package / "contracts" / "constraints.json").read_bytes())
    constraints["standards"]["otdp"] = ">=0.2.0,<0.2.2"  # the prior 0.2.2 no longer fits
    (package / "contracts" / "constraints.json").write_bytes(canonical_json(constraints))
    result = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert result.returncode == 1, result.stderr
    assert "standards pin error: plugin_lock_drift" in result.stderr
    assert _lock_path(package).read_bytes() == locked  # verify-only: never writes


def test_b5_locked_greens_on_an_agreeing_tree(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    result = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert result.returncode == 0, result.stderr
    assert "error" not in result.stderr


def test_b5_unresolvable_constraint_refuses_with_zero_socket_attempts(
    tmp_path: Path, socket_guard: _SocketCounter
) -> None:
    """A carried version's rows removed from the corpus manifest, with a
    constraint demanding exactly that version: the named offline refusal
    fires with ZERO network attempts (the five guard names counted)."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.2.1"})
    corpus = json.loads((root / "standards" / "corpus-manifest.json").read_bytes())
    corpus["files"] = [
        row
        for row in corpus["files"]
        if not str(row["path"]).startswith("otdp/0.2.0/")
    ]
    (root / "standards" / "corpus-manifest.json").write_bytes(canonical_json(corpus))
    with pytest.raises(StandardsError, match="constraint_unresolvable"):
        resolve_package(root, package)
    assert socket_guard.attempts == 0


# --- fold F1: version-ordered selection (critic M1 / adv216a, twice reproduced) ----


def _add_otdp_version(root: Path, version: str) -> None:
    """A corpus-rowed new version directory: 0.2.2's bytes under a new number,
    every top-level machine file rowed with its real digest."""
    import hashlib

    source = root / "standards" / "otdp" / "0.2.2"
    target = root / "standards" / "otdp" / version
    shutil.copytree(source, target)
    corpus = json.loads((root / "standards/corpus-manifest.json").read_bytes())
    for path in sorted(target.iterdir()):
        if path.is_file() and path.suffix == ".json":
            corpus["files"].append(
                {
                    "path": f"otdp/{version}/{path.name}",
                    "source": f"standards/otdp/0.2.2/{path.name}",
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    (root / "standards/corpus-manifest.json").write_bytes(canonical_json(corpus))


def test_f1_auto_selection_is_version_ordered_not_string_ordered(tmp_path: Path) -> None:
    """0.2.10 string-sorts below 0.2.2; selection and move-to must order by
    version_tuple (both reproducers: the prior-out-of-interval auto-select
    silently picked 0.2.2 and the yank warning's move-to understated)."""
    root = _copy_standards(tmp_path)
    _add_otdp_version(root, "0.2.10")
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"}, otdp_version="9.9.9")
    resolution = resolve_package(root, package)
    rows = {str(row["id"]): str(row["version"]) for row in resolution.document["standards"]}
    assert rows["otdp"] == "0.2.10", rows
    assert resolution.document["directory"] == "standards/otdp/0.2.10"


def test_f1_the_derived_move_to_is_version_ordered(tmp_path: Path) -> None:
    """Both move-to surfaces: the refusal field and the yank deprecation
    warning name the highest served version by version order, not string
    order."""
    root = _copy_standards(tmp_path)
    _add_otdp_version(root, "0.2.10")
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="version_unknown") as raised:
        classify_pin(policy, root, "otdp", "9.9.9")
    assert "move-to: 0.2.10" in str(raised.value)
    classification = classify_pin(policy, root, "otdp", "0.2.1")
    assert classification.warning is not None
    assert "move-to: 0.2.10" in classification.warning
