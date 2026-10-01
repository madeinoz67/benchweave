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
    load_cross_constraints,
    load_prior_lock,
    normalized_equal,
    parse_interval,
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


def _prior_map(root: Path, version: str) -> dict[str, str]:
    """The at-revision truth for a synthetic prior lock: every top-level
    file of the version directory, digested (fold F3's allowlist prior arm
    and F4's scissors comparison both consume it)."""
    directory = root / "standards" / "otdp" / version
    if not directory.is_dir():
        return {}  # a fictional prior pin (an out-of-interval 9.9.9) has no map
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _package(
    root: Path,
    *,
    constraints: dict[str, str] | None,
    otdp_version: str = "0.2.2",
) -> Path:
    """A synthetic in-tree package over the copied standards tree.

    The v1 prior lock carries the provenance keys, the otdp projection's
    version, and the REAL top-level file map of the pinned version (the
    projection's other values are re-derived; the map's names are the
    allowlist's prior arm, so a fixture with a fictional map would refuse
    at the first pin under fold F3).
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
                "sha256": _prior_map(root, otdp_version),
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
        ("^0.0.0", "0.0.0", "0.0.1"),
        ("^1.0", "1.0.0", "2.0.0"),
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
    [
        "^0",
        "~1.2",
        "~1",
        "^1",
        "0.2",
        ">=0.2.0,<0.3.0",
        "^x.y",
        "^0.2.3.4",
        "^01.2",
        "^0..2",
        "^0.02",
    ],
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


def test_b4_dev_shape_refuses_naming_the_opt_in_carrier(tmp_path: Path) -> None:
    """VR-38 prefix stability across slice 4's landing (#218): the prefix and
    its meaning (the INTERVAL block never carries a dev pin) are unchanged;
    the remediation now names the landed carrier — the content-addressed
    opt-in — instead of the interim "lands with slice 4" pointer."""
    root = _copy_standards(tmp_path)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="dev_pin_unsupported") as raised:
        classify_pin(policy, root, "otdp", "0.3.0-dev")
    assert "opt_in" in str(raised.value)


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
    "plugin-ui": ">=0.3.0,<0.4.0",
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
    import copy

    (package / "contracts" / "lock.json").write_text(
        json.dumps(copy.deepcopy(_DPS150_V1_LOCK), indent=2)
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
        "0.3.0",
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
    # Fold F3: the historical v1 map under-covers the directory (the two
    # unrowed latecomers are neither corpus-rowed nor prior-mapped), so the
    # first relock REFUSES naming them — the governed transition is the
    # refusal's own disposition: extend the prior map deliberately, then pin.
    refused = _run(root, "pin", "--package", "plugins/fnirsi/dps150")
    assert refused.returncode == 1, refused.stderr
    assert "corpus_file_stray" in refused.stderr
    for latecomer in ("transport-providers.md", "validation-report.md"):
        assert latecomer in refused.stderr
        extended = json.loads((package / "contracts" / "lock.json").read_text())
        extended["sha256"][latecomer] = hashlib.sha256(
            (root / "standards/otdp/0.2.2" / latecomer).read_bytes()
        ).hexdigest()
        (package / "contracts" / "lock.json").write_text(json.dumps(extended, indent=2))
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
    # Fold F3: 0.2.2 carries transport-providers.md (unrowed, absent from the
    # 0.2.0 prior map) — the upgrade refuses naming it; the governed move
    # extends the prior map deliberately, then proceeds.
    refused = _run(
        root, "upgrade", "otdp", "--precise", "0.2.2", "--package", "plugins/acme/widget"
    )
    assert refused.returncode == 1, refused.stderr
    assert "corpus_file_stray" in refused.stderr
    assert "transport-providers.md" in refused.stderr
    prior = json.loads(before_raw)
    prior["sha256"]["transport-providers.md"] = hashlib.sha256(
        (root / "standards/otdp/0.2.2/transport-providers.md").read_bytes()
    ).hexdigest()
    _lock_path(package).write_text(json.dumps(prior))
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
    """plugin-ui's served set is {0.3.0} (the F1 narrow range): the design's
    `upgrade plugin-ui --precise 0.3.0` control is the no-op arm — the lock
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
        "0.3.0",
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
    target.mkdir()
    corpus = json.loads((root / "standards/corpus-manifest.json").read_bytes())
    for path in sorted(source.iterdir()):
        # machine files only, all rowed: the allowlist (fold F3) admits
        # corpus-rowed ∪ prior-mapped, and this synthetic prior (a fictional
        # out-of-interval pin) carries no map.
        if path.is_file() and path.suffix == ".json":
            shutil.copy2(path, target / path.name)
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


# --- fold F3: the derived map is an allowlist, not directory coverage ---------------


def test_f3_a_stray_ds_store_refuses_and_is_never_adopted(tmp_path: Path) -> None:
    """.DS_Store is neither corpus-rowed nor in the prior map: both pin modes
    refuse naming it, and the committed lock never adopts it."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    (root / "standards/otdp/0.2.2/.DS_Store").write_bytes(b"junk\n")
    for *args, in (
        ("pin", "--locked"),
        ("pin",),
    ):
        result = _run(root, *args, "--package", "plugins/acme/widget")
        assert result.returncode == 1, (args, result.stdout, result.stderr)
        assert "corpus_file_stray" in result.stderr, result.stderr
        assert ".DS_Store" in result.stderr, result.stderr
    assert ".DS_Store" not in json.loads(_lock_path(package).read_bytes())["sha256"]


def test_f3_b_an_uppercase_stray_json_refuses(tmp_path: Path) -> None:
    """STRAY.JSON dodges the case-sensitive .json pin check today and enters
    unpinned; the allowlist refuses it regardless of suffix case."""
    root = _copy_standards(tmp_path)
    _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    (root / "standards/otdp/0.2.2/STRAY.JSON").write_text("{}\n")
    result = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert result.returncode == 1, result.stderr
    assert "corpus_file_stray" in result.stderr and "STRAY.JSON" in result.stderr


def test_f3_c_the_shipped_dps150_map_rederives_clean() -> None:
    """The honest case: every one of the shipped lock's 12 entries is
    corpus-rowed or prior-mapped, so the allowlist admits the exact map and
    the resolution is byte-identical to the committed lock."""
    package = ROOT / "plugins" / "fnirsi" / "dps150"
    resolution = resolve_package(ROOT, package)
    assert len(resolution.document["sha256"]) == 12
    assert resolution.raw == (package / "contracts" / "lock.json").read_bytes()


# --- fold F4: revision scissors — the map digests the bytes AT the revision ---------


def test_f4_the_revision_scissors_chain(tmp_path: Path) -> None:
    """The executed chain: same-version byte motion after a relock (a
    regenerated report) first surfaces as --locked drift, then pin WITHOUT
    --revision refuses naming the scissors invariant, and WITH --revision it
    relocks, recording the motion's revision alongside it."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    report = root / "standards/otdp/0.2.2/validation-report.md"
    moved = report.read_bytes() + b"regenerated\n"
    report.write_bytes(moved)
    locked = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert locked.returncode == 1, locked.stderr
    assert "plugin_lock_drift" in locked.stderr
    refused = _run(root, "pin", "--package", "plugins/acme/widget")
    assert refused.returncode == 1, refused.stderr
    assert "revision_scissors" in refused.stderr
    assert "validation-report.md" in refused.stderr
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 1
    relock = _run(
        root, "pin", "--revision", "f" * 40, "--package", "plugins/acme/widget"
    )
    assert relock.returncode == 0, relock.stderr
    document = json.loads(_lock_path(package).read_bytes())
    assert document["revision"] == "f" * 40
    assert document["sha256"]["validation-report.md"] == hashlib.sha256(moved).hexdigest()
    # the recorded motion is now stable: a plain re-pin is a no-op
    again = _run(root, "pin", "--package", "plugins/acme/widget")
    assert again.returncode == 0, again.stderr


def test_f4_map_additions_carry_the_fetch_existence_warning(tmp_path: Path) -> None:
    """Additions are not digest motion: a rowed file absent from the prior
    map re-enters the derived map with a warning naming the invariant — the
    file must exist at the recorded revision."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    prior = json.loads(_lock_path(package).read_bytes())
    del prior["sha256"]["device-profile-catalog.schema.json"]
    _lock_path(package).write_text(json.dumps(prior))
    result = _run(root, "pin", "--package", "plugins/acme/widget")
    assert result.returncode == 0, result.stderr
    assert "map addition" in result.stdout
    assert "device-profile-catalog.schema.json" in result.stdout
    assert "recorded revision" in result.stdout
    document = json.loads(_lock_path(package).read_bytes())
    assert "device-profile-catalog.schema.json" in document["sha256"]


# --- fold wave 2, R1: authoring crashes are styled refusals ------------------------


@pytest.mark.parametrize("shape", ["{}", "[]", "not json at all"])
def test_r1_set_on_a_wrong_shape_constraints_file_refuses_styled(
    tmp_path: Path, shape: str
) -> None:
    """A wrong-shape constraints file under ``pin --set`` refuses with its
    own prefix — never a KeyError/TypeError/JSONDecodeError traceback."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints=None)
    (package / "contracts" / "constraints.json").write_text(shape)
    result = _run(root, "pin", "--set", "otdp=^0.2", "--package", "plugins/acme/widget")
    assert result.returncode == 1, result.stderr
    assert "standards pin error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert "constraint_document_invalid" in result.stderr or "corrupt" in result.stderr


def test_r1_set_on_a_missing_package_dir_refuses_styled(tmp_path: Path) -> None:
    """A package directory that does not exist refuses ``package_absent:``
    before any staged write is attempted."""
    root = _copy_standards(tmp_path)
    result = _run(root, "pin", "--set", "otdp=^0.2", "--package", "plugins/acme/widget")
    assert result.returncode == 1, result.stderr
    assert "standards pin error: package_absent" in result.stderr
    assert "Traceback" not in result.stderr


# --- fold wave 2, R2: list refuses desync styled -----------------------------------


def test_r2_list_refuses_a_manifest_policy_desync_styled(tmp_path: Path) -> None:
    """A manifest entry with no policy row is dependency_policy_invalid —
    list must refuse styled, never a raw KeyError traceback."""
    root = _copy_standards(tmp_path)
    manifest = root / "standards" / "standards-manifest.json"
    document = json.loads(manifest.read_bytes())
    del document["dependency_policy"]["standards"]["registry"]
    manifest.write_text(json.dumps(document, indent=2))
    result = _run(root, "list")
    assert result.returncode == 1, result.stdout
    assert "standards list error: dependency_policy_invalid" in result.stderr
    assert "Traceback" not in result.stderr


# --- fold wave 2, R3: requires intervals validate at load --------------------------



def _mutate_cross(root: Path, mutate: Any) -> None:
    cross = root / "standards" / "cross-constraints.json"
    document = json.loads(cross.read_bytes())
    document = mutate(document)
    cross.write_bytes(canonical_json(document))


def test_r3_a_malformed_requirement_interval_refuses_at_load(tmp_path: Path) -> None:
    """A requires value that is neither an explicit interval nor an
    adapter_api shape refuses cross_constraint_invalid AT LOAD — today it
    loads clean and fires later under the wrong prefix."""
    root = _copy_standards(tmp_path)

    def mutate(document: dict[str, Any]) -> dict[str, Any]:
        document["rows"][0]["requires"]["otdp"] = "banana"
        return document

    _mutate_cross(root, mutate)
    with pytest.raises(StandardsError, match="cross_constraint_invalid"):
        load_cross_constraints(root)


def test_r3_a_wellformed_requirement_still_loads(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    assert len(load_cross_constraints(root)) == 1


# --- fold wave 2, R5: no leading zeros in the stored interval grammar --------------


@pytest.mark.parametrize(
    "value",
    [">=00.2.0,<0.3.0", ">=0.2.0,<00.3.0", ">=0.02.0,<0.3.0"],
)
def test_r5_leading_zero_components_refuse(value: str) -> None:
    """The interval grammar admits canonical numeric components only — a
    leading-zero component is hand-typed drift, not a version."""
    with pytest.raises(StandardsError, match="constraint_document_invalid"):
        parse_interval(value)


# --- fold wave 2, R6: malformed corpus rows refuse typed ---------------------------


def test_r6_a_malformed_corpus_row_refuses_typed(tmp_path: Path) -> None:
    """A corpus-manifest row missing its digest refuses with its own prefix
    wherever the rows are consumed — never a bare KeyError."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    corpus = json.loads((root / "standards/corpus-manifest.json").read_bytes())
    corpus["files"].append({"path": "otdp/0.2.2/ghost.json"})  # no sha256
    (root / "standards/corpus-manifest.json").write_bytes(canonical_json(corpus))
    with pytest.raises(StandardsError, match="corpus_manifest_row_invalid"):
        resolve_package(root, package)


def test_r6_a_non_object_row_refuses_typed(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    corpus = json.loads((root / "standards/corpus-manifest.json").read_bytes())
    corpus["files"].append("not-a-row")
    (root / "standards/corpus-manifest.json").write_bytes(canonical_json(corpus))
    with pytest.raises(StandardsError, match="corpus_manifest_row_invalid"):
        resolve_package(root, package)


# --- fold wave 2, R11: the drift message names the fourth cause --------------------


def test_r11_drift_messages_name_non_canonical_serialization(tmp_path: Path) -> None:
    """A values-identical reflow of the lock is drift too — both refusal
    sites say so (the relock remediation is byte-form, not values)."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    assert _run(root, "pin", "--package", "plugins/acme/widget").returncode == 0
    document = json.loads(_lock_path(package).read_bytes())
    _lock_path(package).write_text(json.dumps(document, indent=2))  # values-identical reflow
    result = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert result.returncode == 1, result.stderr
    assert "plugin_lock_drift" in result.stderr
    assert "non-canonical serialization" in result.stderr


# --- fold wave 2, R15a: the cross-constraints note is bounded ----------------------


def test_r15a_an_unbounded_note_refuses(tmp_path: Path) -> None:
    """The honest-negative note is a bounded field — an unbounded prose
    surface in a governance file is drift bait."""
    root = _copy_standards(tmp_path)

    def mutate(document: dict[str, Any]) -> dict[str, Any]:
        document["note"] = "x" * 3000
        return document

    _mutate_cross(root, mutate)
    with pytest.raises(StandardsError, match="cross_constraint_invalid"):
        load_cross_constraints(root)


# --- fold wave 2, R7: prior yanked retention ---------------------------------------


def test_b1_prior_yanked_retention(tmp_path: Path) -> None:
    """A prior lock AT the yanked 0.2.1 with an unchanged constraint
    retains the pin — minimal motion — and the relock surfaces the
    deprecation warning naming the move-to."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"}, otdp_version="0.2.1")
    result = _run(root, "pin", "--package", "plugins/acme/widget")
    assert result.returncode == 0, result.stderr
    document = json.loads(_lock_path(package).read_bytes())
    assert document["otdp_version"] == "0.2.1"
    assert "deprecation warning" in result.stdout
    assert "move-to: 0.2.2" in result.stdout


# --- issue #288 M4: one derivation, labeled degenerate states -----------------------


def _set_policy(root: Path, **fields: object) -> None:
    """Rewrite the policy block's otdp row (merge over the committed row)."""
    manifest = json.loads((root / "standards/standards-manifest.json").read_bytes())
    manifest["dependency_policy"]["standards"]["otdp"].update(fields)
    (root / "standards/standards-manifest.json").write_bytes(canonical_json(manifest))


def test_yanked_pin_above_served_set_warns_of_downgrade(tmp_path: Path) -> None:
    """The named behavior arm (issue #288 M4): a yanked pin ABOVE every
    served version still names the newest healthy served version as the
    move-to — the actionable remediation (the pin's bytes are yanked;
    nothing newer is servable) — but the warning SAYS it is a downgrade,
    on every gateway surface, with the exact pinned label text."""
    from benchweave.control.documents import classify_descriptor_pin
    from benchweave.standards.matrix import render_matrix

    root = _copy_standards(tmp_path)
    # The matrix surface renders committed repo state: pyproject.toml and
    # .gitmodules ride along (test_matrix._repo_copy's shape).
    shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copy2(ROOT / ".gitmodules", root / ".gitmodules")
    _set_policy(
        root,
        yanked={
            "0.2.1": {"reason": "descriptor dialect drift", "since": "2026-09-24"},
            "0.2.2": {"reason": "synthetic sweep", "since": "2026-10-01"},
        },
    )
    policy = load_dependency_policy(root)
    classification = classify_pin(policy, root, "otdp", "0.2.1")
    assert classification.state == "yanked"
    assert classification.warning is not None
    assert (
        "move-to: 0.2.0 (a downgrade — no served version is newer)"
        in classification.warning
    ), classification.warning
    note = str(classify_descriptor_pin("0.2.1", corpus=root / "standards").note)
    assert "move-to: 0.2.0 (a downgrade — no served version is newer)" in note, note
    cell = next(
        line
        for line in render_matrix(root).splitlines()
        if line.startswith("| otdp | 0.2.1 |")
    )
    assert "move-to 0.2.0 (a downgrade — no served version is newer)" in cell, cell


def test_move_to_one_derivation_five_surfaces(tmp_path: Path) -> None:
    """M4's consolidation table (issue #288): four corpus states, five
    in-process surfaces — the pure derivation, the resolver's yank
    warning, the resolver's VR-37 field, the gateway classifier's yank
    note, and the matrix yank cell — agree on the version AND the label,
    pinned as literal expected strings (the SDK twin test pins the same
    literals cross-repo; the downgrade label is the pinned contract)."""
    from benchweave.control.documents import classify_descriptor_pin
    from benchweave.standards.dependency import _vr37, derive_move_to
    from benchweave.standards.manifest import served_versions
    from benchweave.standards.matrix import render_matrix

    real = {"0.2.1": {"reason": "descriptor dialect drift", "since": "2026-09-24"}}
    synthetic = {"reason": "synthetic yank", "since": "2026-10-01"}
    table = [
        # (name, yanked map, pin, expected version, expected label)
        ("pin below all served", {**real, "0.2.0": synthetic}, "0.2.0", "0.2.2", ""),
        (
            "yanked pin above all served",
            {**real, "0.2.2": synthetic},
            "0.2.1",
            "0.2.0",
            " (a downgrade — no served version is newer)",
        ),
        (
            "served empty",
            {**real, "0.2.0": synthetic, "0.2.2": synthetic},
            "0.2.1",
            "0.2.0",
            " (guidance only — no version is served)",
        ),
        ("yanked pin mid-set", dict(real), "0.2.1", "0.2.2", ""),
    ]
    for name, yanked, pin, version, label in table:
        base = tmp_path / name.replace(" ", "-")
        base.mkdir()
        root = _copy_standards(base)
        shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
        shutil.copy2(ROOT / ".gitmodules", root / ".gitmodules")
        _set_policy(root, yanked=yanked)
        policy = load_dependency_policy(root)
        row = policy.standards["otdp"]
        move = derive_move_to(row, served_versions(policy, root, "otdp"), pin)
        assert (move.version, move.label) == (version, label), (name, move)
        warning = classify_pin(policy, root, "otdp", pin).warning
        assert warning is not None and f"move-to: {version}{label}" in warning, (
            name,
            warning,
        )
        # The VR-37 field carries the version bare (its five-field format
        # is pinned text-equal across the resolver and the classifier).
        vr37 = _vr37(policy, "otdp", pin, row, root)
        assert f"move-to: {version};" in vr37, (name, vr37)
        note = str(classify_descriptor_pin(pin, corpus=root / "standards").note)
        assert f"move-to: {version}{label}" in note, (name, note)
        matrix_line = next(
            line
            for line in render_matrix(root).splitlines()
            if line.startswith(f"| otdp | {pin} |")
        )
        assert f"move-to {version}{label}" in matrix_line, (name, matrix_line)


# --- fold wave 2, R8: the refusal corners ------------------------------------------


def test_r8_locked_and_set_refuse_together(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    result = _run(
        root, "pin", "--locked", "--set", "otdp=^0.2", "--package", "plugins/acme/widget"
    )
    assert result.returncode == 1, result.stderr
    assert "standards pin error: constraint_set_invalid" in result.stderr


def test_r8_adapter_api_unresolved_no_row(tmp_path: Path) -> None:
    """The pinned version's descriptor carries no corpus row."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    corpus = json.loads((root / "standards/corpus-manifest.json").read_bytes())
    corpus["files"] = [
        row
        for row in corpus["files"]
        if row["path"] != "otdp/0.2.2/otdp-device-descriptor.schema.json"
    ]
    (root / "standards/corpus-manifest.json").write_bytes(canonical_json(corpus))
    with pytest.raises(StandardsError, match="adapter_api_unresolved"):
        resolve_package(root, package)


def test_r8_adapter_api_unresolved_no_const(tmp_path: Path) -> None:
    """A self-consistent corpus whose descriptor lost the api_version const
    (bytes AND row digest updated together) — the derivation refuses, not
    a laundered None."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    descriptor = root / "standards/otdp/0.2.2/otdp-device-descriptor.schema.json"
    schema = json.loads(descriptor.read_bytes())
    del schema["$defs"]["adapter"]["properties"]["api_version"]["const"]
    raw = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    descriptor.write_bytes(raw)
    corpus = json.loads((root / "standards/corpus-manifest.json").read_bytes())
    for row in corpus["files"]:
        if row["path"] == "otdp/0.2.2/otdp-device-descriptor.schema.json":
            row["sha256"] = hashlib.sha256(raw).hexdigest()
    (root / "standards/corpus-manifest.json").write_bytes(canonical_json(corpus))
    with pytest.raises(StandardsError, match="adapter_api_unresolved"):
        resolve_package(root, package)


def test_r8_version_directory_absent(tmp_path: Path) -> None:
    """Rows without the directory: retention is row-derived, so the refusal
    fires where the bytes are actually needed."""
    import shutil as _shutil

    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    _shutil.rmtree(root / "standards/otdp/0.2.2")
    with pytest.raises(StandardsError, match="version_directory_absent"):
        resolve_package(root, package)


def test_r8_lock_otdp_absent(tmp_path: Path) -> None:
    """Constraints without otdp: the legacy projection has no source."""
    root = _copy_standards(tmp_path)
    package = _package(root, constraints={"registry": ">=0.1.0,<0.2.0"})
    with pytest.raises(StandardsError, match="lock_otdp_absent"):
        resolve_package(root, package)


# --- fold wave 2, R4: the masking arms around normalized_equal ---------------------


def test_r4_a_difference_in_an_other_version_bearing_field_refuses(tmp_path: Path) -> None:
    """XOR arm 1: two documents differing ONLY in a non-version field that
    bears the OTHER document's version string refuse — each side's own
    version is masked, the other's is not, so the real difference survives."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"requires": "the peer runs 0.2.2"}))
    b.write_text(json.dumps({"requires": "the peer runs 0.2.1"}))
    assert not normalized_equal(a, b, "0.2.1", "0.2.2")


def test_r4_own_version_bearing_fields_mask_to_equal_the_known_limitation(
    tmp_path: Path,
) -> None:
    """XOR arm 2 — the DOCUMENTED false-accept class: a real difference in a
    non-version field that bears each document's OWN version string is
    masked away. Substring replacement cannot tell a version-bearing field
    from a version field; field-scoped replacement is the named fix shape,
    deliberately not taken this slice."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"tested-with": "0.2.1 itself"}))
    b.write_text(json.dumps({"tested-with": "0.2.2 itself"}))
    assert normalized_equal(a, b, "0.2.1", "0.2.2")
