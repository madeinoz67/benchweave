"""Content-addressed dev pins: the opt-in, the sha-addressed lock row, the
wheel posture (issue #218, #203 slice 4, design §3.6).

A plugin opts in per standard in ``contracts/constraints.json`` with a
content-addressed pin (``"0.4.0-dev@<git-sha>"`` in ``opt_in``); resolution
is repo-checkout only — the head's bytes materialize from the object store
at the recorded sha (the ``check.py::_pinned_sdk_package_version`` git-show
precedent), never from a wheel's packaged tree, never falling back to the
active family. The lock row carries ``stage: dev``, the sha and per-file
digests (VR-29); editing the head after locking breaks revalidation on the
changed file's digest (D2) — the label is mutable, the pin is not.

The fixture head targets ``0.4.0-dev`` deliberately: OTDP 0.3.0 is a retired
identifier on this corpus (used and dead, never reissued — the design's own
re-target hint says "the next minor is 0.4.0"), so the fixture head names
the next live minor, and the retired-target refusal has its own arm.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from benchweave.standards.dependency import (
    load_constraints,
    resolve_package,
)
from benchweave.standards.export import canonical_json
from benchweave.standards.manifest import StandardsError

ROOT = Path(__file__).resolve().parents[2]

#: The content-addressed opt-in grammar's label half — the design's own
#: next-minor example for this corpus (0.3.0 is retired).
HEAD_LABEL = "0.4.0-dev"
OPENED = "2026-09-28"


def _plant_head(root: Path, *, target: str = HEAD_LABEL, candidate: bool = False) -> None:
    """Plant a dev head on the copied standards tree.

    The head is a copy of the active 0.2.2 directory whose descriptor schema
    accepts the dev label in ``otdp_version`` (the one-token edit a head's
    author makes first — the const swap is what makes a dev-pinned descriptor
    valid against the HEAD's bytes and only those); corpus rows cite the
    active path as ``source`` (the OPEN shape), and the manifest entry gains
    the ``dev`` block naming every head file normative.
    """
    active = root / "standards" / "otdp" / "0.2.2"
    head = root / "standards" / "otdp" / target
    shutil.copytree(active, head)
    schema_path = head / "otdp-device-descriptor.schema.json"
    schema = json.loads(schema_path.read_bytes())
    schema["properties"]["otdp_version"]["const"] = target
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    manifest_path = root / "standards" / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    names = sorted(path.name for path in head.iterdir() if path.is_file())
    for entry in manifest["standards"]:
        if entry["id"] == "otdp":
            entry["dev"] = {
                "version": target,
                "opened": OPENED,
                "normative": [f"standards/otdp/{target}/{name}" for name in names],
                **({"candidate": True} if candidate else {}),
            }
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    for name in names:
        raw = (head / name).read_bytes()
        corpus["files"].append(
            {
                "path": f"otdp/{target}/{name}",
                "source": f"standards/otdp/0.2.2/{name}",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {args} failed:\n{result.stderr}"
    return result.stdout.strip()


def _git_root(tmp_path: Path, *, target: str = HEAD_LABEL) -> tuple[Path, str]:
    """A planted-head standards tree committed to a fresh git repository.

    The recorded HEAD sha is the content address the opt-in pins — every
    object-store read in the resolver names it.
    """
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(ROOT / "standards", root / "standards")
    _plant_head(root, target=target)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-q",
        "-m",
        "plant dev head",
    )
    return root, _git(root, "rev-parse", "HEAD")


def _package(
    root: Path,
    *,
    opt_in: dict[str, str] | None = None,
    constraints: dict[str, str] | None = None,
    otdp_version: str = "0.2.2",
) -> Path:
    """A synthetic in-tree package over the git fixture root (the slice-2
    ``_package`` pattern: a v1 prior lock carrying the released map)."""
    package = root / "plugins" / "acme" / "widget"
    (package / "contracts").mkdir(parents=True)
    standards = constraints if constraints is not None else {"otdp": ">=0.2.0,<0.3.0"}
    (package / "contracts" / "constraints.json").write_bytes(
        canonical_json(
            {
                "constraint_version": 1,
                "standards": standards,
                "opt_in": opt_in or {},
            }
        )
    )
    directory = root / "standards" / "otdp" / otdp_version
    mapping = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }
    (package / "contracts" / "lock.json").write_text(
        json.dumps(
            {
                "repository": "https://example.invalid/acme-widget",
                "revision": "0" * 40,
                "directory": f"standards/otdp/{otdp_version}",
                "otdp_version": otdp_version,
                "adapter_api_version": "1.1",
                "sha256": mapping,
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


# --- D1 (wheel arm): a packaged posture cannot resolve a dev head -----------------


def test_d1_wheel_posture_refuses_by_name_never_falling_back(tmp_path: Path) -> None:
    """D1's wheel arm: with the head's bytes ON DISK but no git object store
    (the packaged/wheel posture — a wheel physically cannot carry one), the
    opt-in refuses ``dev_head_unresolvable:`` by name. The head directory
    existing is the point: resolution must not quietly read working-tree
    bytes, and it must not fall back to the released/active family either."""
    root, _sha = _git_root(tmp_path)
    shutil.rmtree(root / ".git")  # the wheel posture: bytes present, store absent
    package = _package(root, opt_in={"otdp": f"{HEAD_LABEL}@{'a' * 40}"})
    with pytest.raises(StandardsError) as raised:
        resolve_package(root, package)
    message = str(raised.value)
    assert message.startswith("dev_head_unresolvable:"), message
    assert "otdp" in message and HEAD_LABEL in message
    assert "never" in message and "substituted" in message, (
        f"the refusal must name the no-fallback posture: {message}"
    )


def test_d1_wheel_posture_never_resolves_the_released_row(tmp_path: Path) -> None:
    """The structural half of never-fallback: a dev opt-in that cannot
    resolve leaves NO lock behind — the resolution raises rather than
    emitting a lock whose otdp row quietly names the released version."""
    root, _sha = _git_root(tmp_path)
    shutil.rmtree(root / ".git")
    package = _package(root, opt_in={"otdp": f"{HEAD_LABEL}@{'a' * 40}"})
    with pytest.raises(StandardsError):
        resolve_package(root, package)
    assert not (package / "contracts" / "lock.json").read_bytes().startswith(
        b'{"lock_version"'
    ), "a v2 lock must not have been rewritten onto the v1 prior"


# --- D2: content addressing -------------------------------------------------------


def test_d2_dev_pin_locks_with_content_identity(tmp_path: Path) -> None:
    """The lock row records content identity (VR-29): ``stage: dev``, the
    git sha, per-file digests over the head's bytes AT THE SHA, and the
    digest-of-digests over the same — a claim every consumer re-derives from
    the object store, never from the mutable working tree."""
    root, sha = _git_root(tmp_path)
    package = _package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    resolution = resolve_package(root, package)
    rows = {str(row["id"]): row for row in resolution.document["standards"]}
    row = rows["otdp"]
    assert row["stage"] == "dev"
    assert row["version"] == HEAD_LABEL
    assert row["git_sha"] == sha
    expected_files = {
        name: hashlib.sha256(
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "show",
                    f"{sha}:standards/otdp/{HEAD_LABEL}/{name}",
                ],
                capture_output=True,
                check=False,
            ).stdout
        ).hexdigest()
        for name in row["files"]
    }
    assert row["files"] == expected_files
    assert row["digest"] == hashlib.sha256(
        canonical_json(
            [[name, expected_files[name]] for name in sorted(expected_files)]
        )
    ).hexdigest()
    # The legacy projection mirrors the resolved row (moves iff it moves).
    assert resolution.document["otdp_version"] == HEAD_LABEL
    assert resolution.document["directory"] == f"standards/otdp/{HEAD_LABEL}"


def test_d2_pre_edit_lock_validates_then_the_edit_refuses_naming_the_digest(
    tmp_path: Path,
) -> None:
    """D2's RED shape, both halves on one fixture: the pre-edit lock validates
    (``pin --locked`` clean), then editing the head's file breaks revalidation
    with the changed file's digest NAMED — the lock's recorded digest and the
    head's current bytes (VR-29's accept criterion)."""
    root, sha = _git_root(tmp_path)
    _package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    written = _run(root, "pin", "--package", "plugins/acme/widget")
    assert written.returncode == 0, written.stderr
    locked = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert locked.returncode == 0, locked.stderr
    assert "dev_pin_drift" not in locked.stderr

    schema_path = root / "standards" / "otdp" / HEAD_LABEL / "device-classes.md"
    original = schema_path.read_bytes()
    schema_path.write_bytes(original + b"\nA moved-head edit the pin did not record.\n")
    moved = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert moved.returncode == 1, moved.stdout
    assert "dev_pin_drift:" in moved.stderr, moved.stderr
    assert "device-classes.md" in moved.stderr
    assert hashlib.sha256(original).hexdigest() in moved.stderr, (
        "the refusal must name the lock's recorded digest"
    )
    moved_digest = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    assert moved_digest in moved.stderr, "the refusal must name the head's current digest"


def test_d2_repinning_at_the_moved_sha_heals_the_drift(tmp_path: Path) -> None:
    """The remediation the refusal names: commit the head's new state, move
    the opt-in to the new sha, re-pin — the drift refusal clears and the lock
    carries the NEW content identity."""
    root, sha = _git_root(tmp_path)
    package = _package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    schema_path = root / "standards" / "otdp" / HEAD_LABEL / "device-classes.md"
    schema_path.write_bytes(
        schema_path.read_bytes() + b"\nA moved-head edit the pin did not record.\n"
    )
    # The edit → repin loop (GOVERNANCE's dev-stage flow) moves the row too.
    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    for row in corpus["files"]:
        if row["path"] == f"otdp/{HEAD_LABEL}/device-classes.md":
            row["sha256"] = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    corpus_path.write_text(json.dumps(corpus, indent=1), encoding="utf-8")
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-q",
        "-m",
        "move the head",
    )
    new_sha = _git(root, "rev-parse", "HEAD")
    constraints_path = package / "contracts" / "constraints.json"
    document = json.loads(constraints_path.read_bytes())
    document["opt_in"]["otdp"] = f"{HEAD_LABEL}@{new_sha}"
    constraints_path.write_bytes(canonical_json(document))
    healed = _run(root, "pin", "--package", "plugins/acme/widget")
    assert healed.returncode == 0, healed.stderr
    lock = json.loads((package / "contracts" / "lock.json").read_bytes())
    (otdp_row,) = (r for r in lock["standards"] if r["id"] == "otdp")
    assert otdp_row["git_sha"] == new_sha
    again = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert again.returncode == 0, again.stderr


# --- VR-28: the opt-in is per standard, never ambient -----------------------------


def test_vr28_no_opt_in_resolves_released_with_the_head_open(tmp_path: Path) -> None:
    """With a head open and NO opt-in, the released version resolves (the
    head never auto-selects)."""
    root, _sha = _git_root(tmp_path)
    package = _package(root, constraints={"otdp": ">=0.2.0,<0.3.0"})
    resolution = resolve_package(root, package)
    (otdp_row,) = (r for r in resolution.document["standards"] if r["id"] == "otdp")
    assert otdp_row["stage"] == "released"
    assert otdp_row["version"] == "0.2.2"


def test_vr28_an_opt_in_for_one_standard_affects_only_that_standard(
    tmp_path: Path,
) -> None:
    """The opt-in moves exactly its own standard's row; the sibling stays on
    its released resolution (minimal motion across stages)."""
    root, sha = _git_root(tmp_path)
    package = _package(
        root,
        constraints={"otdp": ">=0.2.0,<0.3.0", "plugin-ui": ">=0.2.0,<0.3.0"},
        opt_in={"otdp": f"{HEAD_LABEL}@{sha}"},
    )
    resolution = resolve_package(root, package)
    rows = {str(row["id"]): row for row in resolution.document["standards"]}
    assert (rows["otdp"]["stage"], rows["otdp"]["version"]) == ("dev", HEAD_LABEL)
    assert (rows["plugin-ui"]["stage"], rows["plugin-ui"]["version"]) == (
        "released",
        "0.2.0",
    )


# --- the refusal ladder ------------------------------------------------------------


def test_opt_in_label_must_name_the_declared_head(tmp_path: Path) -> None:
    """One head per standard: the opt-in's label must equal the manifest's
    declared head (accept-exactly-the-declared-head); any other dev label
    refuses ``dev_head_unresolvable:`` naming the declared one."""
    root, sha = _git_root(tmp_path)
    package = _package(root, opt_in={"otdp": f"0.9.9-dev@{sha}"})
    with pytest.raises(StandardsError) as raised:
        resolve_package(root, package)
    message = str(raised.value)
    assert message.startswith("dev_head_unresolvable:"), message
    assert HEAD_LABEL in message, "the refusal names the declared head"


def test_opt_in_targeting_a_retired_identifier_refuses(tmp_path: Path) -> None:
    """A head targeting a retired identifier could never promote (retired is
    used-and-dead, never reissued) — the resolver refuses the opt-in with its
    own prefix rather than locking a dead-end pin."""
    root, _sha = _git_root(tmp_path, target="0.3.0-dev")
    package = _package(root, opt_in={"otdp": f"0.3.0-dev@{_git(root, 'rev-parse', 'HEAD')}"})
    with pytest.raises(StandardsError, match="dev_target_retired:") as raised:
        resolve_package(root, package)
    assert "0.4.0" in str(raised.value), "the refusal names the re-target hint"


def test_a_stored_caret_in_the_opt_in_refuses(tmp_path: Path) -> None:
    """The sugar ladder covers the opt-in too: authoring sugar never persists
    in any committed document."""
    root, _sha = _git_root(tmp_path)
    package = _package(root, opt_in={"otdp": "^0.4.0-dev@123"})
    with pytest.raises(StandardsError, match="constraint_syntax_unexpanded"):
        load_constraints(package)


def test_headless_tree_opt_in_refuses_naming_the_state(tmp_path: Path) -> None:
    """An opt-in against a tree whose manifest declares no head (promoted or
    abandoned) refuses naming that state — a dead head is never silently
    resolved from history alone."""
    root, sha = _git_root(tmp_path)
    manifest_path = root / "standards" / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for entry in manifest["standards"]:
        entry.pop("dev", None)
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    package = _package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    with pytest.raises(StandardsError) as raised:
        resolve_package(root, package)
    message = str(raised.value)
    assert message.startswith("dev_head_unresolvable:"), message
    assert "declares no dev head" in message


# --- the constraints carrier -------------------------------------------------------


def test_opt_in_for_a_standard_absent_from_standards_refuses(tmp_path: Path) -> None:
    """The opt-in documents a per-standard override, so the standard must
    carry its released interval in the same document."""
    root, sha = _git_root(tmp_path)
    package = _package(
        root,
        constraints={"plugin-ui": ">=0.2.0,<0.3.0"},
        opt_in={"otdp": f"{HEAD_LABEL}@{sha}"},
    )
    with pytest.raises(StandardsError, match="constraint_document_invalid"):
        load_constraints(package)


def test_the_interval_block_still_refuses_dev_shapes_pointing_at_opt_in(
    tmp_path: Path,
) -> None:
    """VR-38 prefix stability: ``dev_pin_unsupported:`` keeps its meaning (the
    INTERVAL block never carries a dev pin) while the remediation now names
    the landed mechanism — the opt-in — instead of a future slice."""
    from benchweave.standards.dependency import classify_pin
    from benchweave.standards.manifest import load_dependency_policy

    root, _sha = _git_root(tmp_path)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="dev_pin_unsupported") as raised:
        classify_pin(policy, root, "otdp", HEAD_LABEL)
    assert "opt_in" in str(raised.value)
    assert "slice 4" not in str(raised.value)


# --- refute fold (lane A): the always-on check lane sees dev drift -----------------


def test_check_lane_refuses_a_moved_dev_head_naming_both_digests(
    tmp_path: Path,
) -> None:
    """Lane A's B-arm: ``standards check`` is the always-on drift lane and
    must refuse a dev head that moved under a locked pin with
    ``dev_pin_drift:`` naming both digests — before this fold the drift
    check rode only ``pin_lock`` and the check lane stayed GREEN on a
    drifted head."""
    from benchweave.standards.check import _compare_plugin_dependencies

    root, sha = _git_root(tmp_path)
    _package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    written = _run(root, "pin", "--package", "plugins/acme/widget")
    assert written.returncode == 0, written.stderr
    head_file = root / "standards" / "otdp" / HEAD_LABEL / "device-classes.md"
    head_file.write_bytes(head_file.read_bytes() + b"\nA moved-head edit.\n")
    failures = _compare_plugin_dependencies(root)
    drift = [line for line in failures if line.startswith("dev_pin_drift:")]
    assert drift, f"the check lane stayed green on a drifted head: {failures}"
    assert "device-classes.md" in drift[0]
    assert hashlib.sha256(head_file.read_bytes()).hexdigest() in drift[0]


def test_an_added_head_file_trips_drift(tmp_path: Path) -> None:
    """Lane A's C-arm: a file ADDED to the head after locking is drift the
    lock cannot name — the head-state check must enumerate the head
    directory and refuse names absent from the lock's per-file map (before
    this fold ``pin --locked`` stayed green with the addition)."""
    root, sha = _git_root(tmp_path)
    _package(root, opt_in={"otdp": f"{HEAD_LABEL}@{sha}"})
    written = _run(root, "pin", "--package", "plugins/acme/widget")
    assert written.returncode == 0, written.stderr
    added = root / "standards" / "otdp" / HEAD_LABEL / "added-by-adversary.schema.json"
    added.write_text("{}\n", encoding="utf-8")
    locked = _run(root, "pin", "--locked", "--package", "plugins/acme/widget")
    assert locked.returncode == 1, locked.stdout
    assert "dev_pin_drift:" in locked.stderr, locked.stderr
    assert "added-by-adversary.schema.json" in locked.stderr
