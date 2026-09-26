"""Non-mutating check that the pinned SDK mirrors the canonical standards.

The bundle re-exported to a throwaway directory is the authority: the lock and
the vendored tree are compared against it, never rewritten. An empty failure
list is the only clean state; every failure is one ``prefix: detail`` line.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from .export import export_bundle
from .manifest import load_identity, load_manifest, load_sdk_compatibility

LOCK_NAME = "standards-lock.json"
VENDORED = "src/benchweave_sdk/standards"
STAMP_NAME = "_GENERATED.txt"
# Mirrors standards_sync.STAMP_LINE in the SDK; a format change there must be
# mirrored here or every stamp reads as stale.
STAMP_LINE = "{path} — Generated from {identifier}@{version} — do not edit"


def run_check(root: Path, sdk_root: Path | None = None) -> list[str]:
    """Verify the pinned SDK against a fresh export; ``[]`` means clean.

    Re-exports the bundle into a temporary directory (never the working tree),
    then compares versions, digests, the vendored file set, the compatibility
    block, and the manifest's ``sdk_compatibility`` mirror against the lock,
    and anchors the lock's ``compatibility.sdk`` to the pinned SDK's own
    pyproject version.
    """
    sdk = sdk_root if sdk_root is not None else root / "packages" / "sdk"
    workspace = Path(tempfile.mkdtemp(prefix="benchweave-standards-check-"))
    try:
        bundle_root = workspace / "bundle"
        export_bundle(root, bundle_root)
        document: dict[str, Any] = json.loads(
            (bundle_root / "bundle-manifest.json").read_bytes()
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    failures: list[str] = []
    # An unreadable lock is refused by name — never a raw traceback and never
    # laundered into the empty-lock "unpinned" noise (lane-2 finding 3, #187).
    try:
        lock = _read_lock(sdk)
    except OSError:
        failures.append(
            "sdk_lock_unreadable: cannot read the SDK lock (unreadable); "
            "fix the file's readability and re-run"
        )
        lock = {"standards": []}
    # The submodule state gate is computed once, shared, and reported FIRST:
    # on a fresh clone the actionable remediation must not drown under the
    # empty-lock unpinned noise (#158 posture; fold ordering rider, #187).
    state = _submodule_state_failures(root, sdk)
    failures.extend(state)
    failures.extend(_compare_lock(document, lock))
    failures.extend(_compare_policy(document, lock))
    failures.extend(_compare_tree(document, sdk))
    failures.extend(_compare_compatibility(document, lock))
    # The mirror lane and the compatibility.sdk anchor both refuse when the
    # working tree is not the pin (#158 posture), and the anchor adds nothing
    # on top of that refusal (#187).
    failures.extend(_compare_mirror(root, sdk, lock, state))
    failures.extend(_compare_anchor(root, sdk, lock, state))
    return failures


def version_lines(root: Path, sdk_root: Path | None = None) -> list[str]:
    """Version table: main project, per standard, adapter api, SDK lock, submodule SHA.

    An open dev head adds one line naming its target and open date — the
    shared-state glance (devstage record §13.5): the machine-readable token
    a contributor re-reads before opening or editing a head. A head the
    coordinator declared a release candidate carries the marker (§13.9).
    Headless trees render byte-identically to the pre-dev-stage output.
    """
    sdk = sdk_root if sdk_root is not None else root / "packages" / "sdk"
    lines = [f"benchweave {main_version(root)}"]
    for entry in load_manifest(root).standards:
        lines.append(f"standard {entry.id}@{entry.version} ({entry.status})")
        if entry.dev is not None:
            marker = ", release candidate" if entry.dev.candidate else ""
            lines.append(
                f"standard {entry.id} dev-head {entry.dev.version} "
                f"(opened {entry.dev.opened}{marker})"
            )
    # Reported, not trusted: the declared value is derive-checked at every
    # export/check (manifest.validate_identity); undeclared says so.
    lines.append(f"adapter api {load_identity(root).get('adapter_api', 'undeclared')}")
    for row in sorted(_read_lock(sdk).get("standards", []), key=lambda item: str(item["id"])):
        lines.append(f"sdk lock {row['id']}@{row['version']}")
    lines.append(f"submodule packages/sdk {submodule_sha(sdk)}")
    return lines


def main_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def submodule_sha(sdk: Path) -> str:
    result = subprocess.run(  # noqa: S603 — fixed argv
        ["git", "-C", str(sdk), "rev-parse", "--short", "HEAD"],  # noqa: S607 — PATH git is the supported invocation
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _read_lock(sdk: Path) -> dict[str, Any]:
    """An absent lock reads as empty: every standard then reports as unpinned."""
    path = sdk / LOCK_NAME
    if not path.is_file():
        return {"standards": []}
    lock: dict[str, Any] = json.loads(path.read_bytes())
    return lock


def _digests(row: dict[str, Any]) -> dict[str, str]:
    return {str(file["path"]): str(file["sha256"]) for file in row["files"]}


def _compare_lock(document: dict[str, Any], lock: dict[str, Any]) -> list[str]:
    """Main manifest vs SDK lock: pinning, versions and same-version drift.

    Since issue #203 slice 1 both sides carry one row per SERVED (id,
    version); the served-set agreement is refused by name
    (``served_set_drift:`` — the #166 disagreement class) while the existing
    prefixes keep their meanings: ``pinned_sdk_incompatible`` for a standard
    entirely absent, ``sdk_version_mismatch`` for the ACTIVE version
    disagreeing, ``content_drift_without_version`` for same-(id, version)
    digest drift. A lock row with no ``active`` field is the active row of
    its id (the pre-multi-version one-row-per-id shape).
    """
    failures: list[str] = []
    lock_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in lock.get("standards", []):
        lock_by_id.setdefault(str(row["id"]), []).append(row)

    def _lock_active(identifier: str) -> dict[str, Any] | None:
        rows = lock_by_id.get(identifier, [])
        marked = [row for row in rows if row.get("active")]
        if marked:
            return marked[0]
        return rows[0] if rows else None

    lock_pairs = {
        (str(row["id"]), str(row["version"])): bool(row.get("yanked", False))
        for row in lock.get("standards", [])
    }
    bundle_pairs = {
        (str(row["id"]), str(row["version"])): bool(row.get("yanked", False))
        for row in document["standards"]
    }
    for identifier, version in sorted(set(bundle_pairs) - set(lock_pairs)):
        failures.append(
            f"served_set_drift: {identifier}@{version} is served by the manifest "
            "but absent from the SDK lock; run make sync-sdk-standards and land "
            "lock + pointer together"
        )
    for identifier, version in sorted(set(lock_pairs) - set(bundle_pairs)):
        failures.append(
            f"served_set_drift: {identifier}@{version} is in the SDK lock but not "
            "in the served set (retained ∧ in-range ∧ ¬yanked); run make "
            "sync-sdk-standards and land lock + pointer together"
        )
    lock_rows = {str(row["id"]): row for row in lock.get("standards", [])}
    bundle_rows = {str(row["id"]): row for row in document["standards"]}
    for row in document["standards"]:
        identifier = str(row["id"])
        prior = _lock_active(identifier)
        if prior is None:
            failures.append(f"pinned_sdk_incompatible: {identifier} absent from the SDK lock")
            continue
        if not row.get("active", True):
            continue  # served-set membership already compared above
        if prior["version"] != row["version"]:
            failures.append(
                f"sdk_version_mismatch: {identifier} manifest {row['version']} "
                f"vs SDK lock {prior['version']}"
            )
            continue
        exported = _digests(row)
        recorded = _digests(prior)
        for path in sorted(set(exported) | set(recorded)):
            if exported.get(path) != recorded.get(path):
                failures.append(
                    f"content_drift_without_version: {path} differs between manifest "
                    f"and SDK lock at {row['version']}"
                )
    # A yank-marker disagreement changes the served set every consumer
    # derives from the lock plus policy mirror — served_set_drift (the
    # disagreement class the design names).
    for pair, yanked in sorted(bundle_pairs.items()):
        if pair in lock_pairs and lock_pairs[pair] != yanked:
            failures.append(
                f"served_set_drift: {pair[0]}@{pair[1]} yank marker disagrees between "
                "the manifest and the SDK lock; run make sync-sdk-standards and land "
                "lock + pointer together"
            )
    # Same-(id, version) digest drift on NON-active rows carries the
    # same prefix — same meaning, same-version drift.
    lock_by_pair = {
        (str(row["id"]), str(row["version"])): row for row in lock.get("standards", [])
    }
    for row in document["standards"]:
        pair = (str(row["id"]), str(row["version"]))
        prior = lock_by_pair.get(pair)
        if prior is None or row.get("active", True):
            continue
        exported = _digests(row)
        recorded = _digests(prior)
        for path in sorted(set(exported) | set(recorded)):
            if exported.get(path) != recorded.get(path):
                failures.append(
                    f"content_drift_without_version: {path} differs between manifest "
                    f"and SDK lock at {row['version']}"
                )
    for identifier in sorted(set(lock_rows) - set(bundle_rows)):
        failures.append(
            f"stale_generated: {identifier}/ vendored for a standard the manifest "
            "no longer lists"
        )
    return failures


def _compare_policy(document: dict[str, Any], lock: dict[str, Any]) -> list[str]:
    """The dependency-policy block must be mirrored verbatim into the SDK lock.

    The gateway manifest stays the authority (design §3.1: one committed
    authority); the lock's copy exists so the SDK can classify pins offline
    (PKG-1). Any disagreement — including an absent mirror — is
    ``policy_mirror_drift:``.
    """
    expected = json.dumps(document.get("dependency_policy"), sort_keys=True)
    actual = json.dumps(lock.get("dependency_policy"), sort_keys=True)
    if expected != actual:
        return [
            "policy_mirror_drift: the dependency_policy block disagrees between the "
            "standards manifest and the SDK lock (or the lock carries no mirror); "
            "run make sync-sdk-standards and land lock + pointer together"
        ]
    return []


def _compare_tree(document: dict[str, Any], sdk: Path) -> list[str]:
    """Vendored bytes and file set vs what sync-standards would write."""
    failures: list[str] = []
    tree = sdk / VENDORED
    if not tree.is_dir():
        failures.append(f"missing_asset: {VENDORED}/ absent; run sync-standards first")
        return failures
    exported: dict[str, str] = {}
    stamps: dict[str, set[str]] = {}
    for row in document["standards"]:
        identifier = str(row["id"])
        for path, digest in _digests(row).items():
            exported[path] = digest
        # One stamp per standard id accumulates every served version's files
        # (issue #203 slice 1); each line already carries its own version.
        stamps.setdefault(identifier, set()).update(
            STAMP_LINE.format(path=path, identifier=identifier, version=str(row["version"]))
            for path in _digests(row)
        )
    present = {
        path.relative_to(tree).as_posix()  # lock rows are '/'-separated (#138)
        for path in tree.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    stamp_paths = {f"{identifier}/{STAMP_NAME}" for identifier in stamps}
    for path in sorted(present - set(exported) - stamp_paths):
        failures.append(f"stale_generated: {VENDORED}/{path} is not written by sync-standards")
    for path in sorted(set(exported) - present):
        failures.append(f"missing_asset: {VENDORED}/{path} absent from the vendored tree")
    for path in sorted(exported):
        target = tree / path
        if not target.is_file():
            continue  # already reported as missing_asset
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != exported[path]:
            failures.append(
                f"hash_mismatch: {VENDORED}/{path} bytes differ from the exported digest"
            )
            failures.append(
                f"stale_generated: {VENDORED}/{path} differs from what sync would write"
            )
    for identifier, expected_lines in sorted(stamps.items()):
        stamp = tree / identifier / STAMP_NAME
        if not stamp.is_file():
            failures.append(f"stale_generated: {VENDORED}/{identifier}/{STAMP_NAME} missing")
            continue
        if set(stamp.read_text(encoding="utf-8").splitlines()) != expected_lines:
            failures.append(
                f"stale_generated: {VENDORED}/{identifier}/{STAMP_NAME} does not "
                "match the exported standard"
            )
    return failures


def _compare_mirror(
    root: Path, sdk: Path, lock: dict[str, Any], state: list[str]
) -> list[str]:
    """The manifest's ``sdk_compatibility`` mirror must equal the SDK lock's block.

    The lock stays the authority; the mirror exists so the matrix render can
    read committed state (CON-12). The authority is the lock of the PINNED
    commit: a submodule working tree that sits away from the parent's gitlink
    (moved, or locally committed past it) is refused by name before any
    comparison — mirroring from it would commit bytes for a version the
    gitlink does not pin, the issue-#158 defect class with a manifest-edit
    instruction attached. Empty-string and null notes normalise equal — the
    lock's nullable semantics. The state refusal is computed once in
    ``run_check`` and shared with the ``compatibility.sdk`` anchor (#187);
    this lane simply stays silent when the gate already refused.
    """
    if state:
        return []
    mirror = load_sdk_compatibility(root)
    sdk_block = lock.get("compatibility")
    sdk_block = sdk_block if isinstance(sdk_block, dict) else {}
    failures: list[str] = []
    for field in ("main_project", "notes", "sdk"):
        actual_raw = sdk_block.get(field)
        if actual_raw is not None and not isinstance(actual_raw, str):
            failures.append(
                f"sdk_compatibility_drift: SDK lock {field} is not a string or null "
                f"({type(actual_raw).__name__}); fix the SDK lock compatibility block"
            )
            continue
        expected = _nullable_text(getattr(mirror, field))
        actual = _nullable_text(actual_raw)
        if expected != actual:
            failures.append(
                f"sdk_compatibility_drift: manifest {field}={expected!r} vs SDK lock "
                f"{field}={actual!r}; update whichever side the pinned SDK's "
                "pyproject.toml disagrees with — the mirror (standards-manifest.json "
                "sdk_compatibility) or the lock (make sync-sdk-standards)"
            )
    return failures


def _compare_anchor(
    root: Path, sdk: Path, lock: dict[str, Any], state: list[str]
) -> list[str]:
    """compatibility.sdk must equal the pinned SDK's own pyproject version.

    The lock's ``sdk`` field is a writer contract (the SDK sync stamps its own
    version into it; issue #187 fork (a): the version this lock state is
    certified for). The state gate proved HEAD is the gitlink pin, and the
    pyproject read here is the pinned commit's OWN bytes — read through git
    from the submodule's object store, never the working tree, so a dirty
    checkout at the pin can neither false-red a healthy pairing nor
    false-green the defect (the dirt-at-pin residual #187 D5 is closed; its
    revisit trigger fired). Where the parent records no gitlink — the
    synthetic-root harness posture, the same no-state-to-be-wrong-about
    distinction the state gate itself draws — there is no commit to read and
    the working tree is the only input. Both sides staling together — mirror
    equal, lock stale — is exactly the state this refuses (the #187 defect
    shape). Degrades loudly: an unreadable pyproject or an undeclared lock
    field is a failure, never a skip and never a degraded ``"unknown"``
    comparison.

    The failure prefix is a family of its own, deliberately not
    ``sdk_compatibility_drift:`` — the two failures have different meanings
    and different fixes (unanchored = "regenerate the SDK lock"; drift's
    remediation names the pinned pyproject as the decider, so it stays
    correct whether the lock or the mirror is the stale side).
    """
    if state:
        return []
    failures: list[str] = []
    block = lock.get("compatibility")
    block = block if isinstance(block, dict) else {}
    declared = block.get("sdk")
    if declared is not None and not isinstance(declared, str):
        failures.append(
            "sdk_version_unanchored: SDK lock compatibility.sdk is not a string or "
            f"null ({type(declared).__name__}); fix the SDK lock compatibility block"
        )
        declared = None  # a non-string declares nothing comparable
    elif not declared:
        failures.append(
            "sdk_version_unanchored: SDK lock compatibility.sdk is undeclared; "
            "run make sync-sdk-standards and land lock + mirror + pointer together"
        )
    pinned = _pinned_sdk_package_version(root, sdk)
    if pinned is None:
        failures.append(
            "sdk_version_unanchored: cannot read the pinned SDK's pyproject.toml "
            "(absent, unreadable, or malformed); the lock's compatibility.sdk "
            "is unanchored"
        )
    elif isinstance(declared, str) and declared != pinned:
        failures.append(
            f"sdk_version_unanchored: SDK lock compatibility.sdk {declared!r} vs the "
            f"pinned SDK's pyproject.toml {pinned!r}; run make sync-sdk-standards and "
            "land lock + mirror + pointer together"
        )
    return failures


def _submodule_state_failures(root: Path, sdk: Path) -> list[str]:
    """Refuse the mirror comparison unless the working tree IS the pin.

    A parent that records no gitlink (a non-git root, as in the test
    fixtures) carries no submodule state to be wrong about — the comparison
    proceeds. Against a recorded gitlink, an uninitialized submodule (no
    ``.git`` inside ``packages/sdk``) is refused by name with no SHAs:
    rev-parse inside it would discover the superproject and report the
    wrong repository's HEAD as submodule state. An initialized working tree
    at another commit is refused with both SHAs named. Never a manifest-edit
    instruction.
    """
    pinned = _pinned_sdk_sha(root)
    if pinned is None:
        return []
    if not (sdk / ".git").exists():
        return [
            "sdk_compatibility_drift: submodule packages/sdk is not initialized; "
            "run git submodule update --init packages/sdk"
        ]
    head = _sdk_head_sha(sdk)
    if head == pinned:
        return []
    return [
        "sdk_compatibility_drift: submodule working tree is not at the pinned "
        f"commit (working {head or 'unknown'} vs pinned {pinned}); "
        "run git submodule update --init packages/sdk"
    ]


def _pinned_sdk_sha(root: Path) -> str | None:
    """The gitlink the parent records for ``packages/sdk``; None when absent."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        [  # noqa: S607 — PATH git is the supported invocation
            "git",
            "-C",
            str(root),
            "ls-tree",
            "HEAD",
            "packages/sdk",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    # "<mode> commit <sha>\t<path>"
    tokens = result.stdout.split()
    if len(tokens) >= 3 and len(tokens[2]) == 40:
        return tokens[2]
    return None


def _sdk_head_sha(sdk: Path) -> str | None:
    """The submodule working tree's HEAD commit; None when not a repository."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        ["git", "-C", str(sdk), "rev-parse", "HEAD"],  # noqa: S607 — PATH git is the supported invocation
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _pinned_sdk_package_version(root: Path, sdk: Path) -> str | None:
    """The pinned SDK commit's own pyproject version, from its committed bytes.

    Where the parent records a gitlink, the version is read with
    ``git show <gitlink>:pyproject.toml`` through the submodule's object
    store — the working tree's content is never consulted, so a dirty
    checkout at HEAD==pin cannot sway the verdict in either direction
    (#187 D5's revisit trigger fired; the state gate has already proved
    HEAD is the pin, so the object is present). A git failure, absent or
    malformed bytes degrade to None — the caller refuses by name.

    Where the parent records NO gitlink (a non-git root, the synthetic-root
    harness — the same no-state-to-be-wrong-about distinction
    ``_submodule_state_failures`` draws) there is no commit to read; the
    working-tree pyproject is the only input and OSError degrades loudly —
    the refusal, not a traceback.

    The check-side dual of the SDK's ``standards_sync._sdk_version``: the
    writer degrades to ``"unknown"`` because it must write something; the
    checker degrades loudly because green must mean verified. A format
    change there must be mirrored here.
    """
    pinned = _pinned_sdk_sha(root)
    if pinned is None:
        pyproject = sdk / "pyproject.toml"
        if not pyproject.is_file():
            return None
        try:
            with pyproject.open("rb") as handle:
                return str(tomllib.load(handle)["project"]["version"])
        except (tomllib.TOMLDecodeError, KeyError, OSError):
            return None
    result = subprocess.run(  # noqa: S603 — fixed argv
        [  # noqa: S607 — PATH git is the supported invocation
            "git",
            "-C",
            str(sdk),
            "show",
            f"{pinned}:pyproject.toml",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return str(
            tomllib.loads(result.stdout.decode("utf-8"))["project"]["version"]
        )
    except (tomllib.TOMLDecodeError, KeyError, UnicodeDecodeError):
        return None


def _nullable_text(value: str | None) -> str | None:
    # "" and null are the same value — the lock's nullable notes semantics.
    return value if value else None


def _compare_compatibility(document: dict[str, Any], lock: dict[str, Any]) -> list[str]:
    """Changed or deprecated standards require a complete compatibility block.

    Multi-version serving (#203 slice 1): the trigger compares each id's
    ACTIVE rows on both sides — a non-active carried row appearing or moving
    is served-set motion (``served_set_drift:`` owns it), not a version
    change of the standard, and must not demand a compatibility block."""
    triggers: list[str] = []
    lock_rows_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in lock.get("standards", []):
        lock_rows_by_id.setdefault(str(row["id"]), []).append(row)
    lock_active: dict[str, dict[str, Any]] = {}
    for identifier, rows in lock_rows_by_id.items():
        marked = [row for row in rows if row.get("active")]
        if marked:
            lock_active[identifier] = marked[0]
        elif len(rows) == 1:
            # The pre-multi-version one-row-per-id shape: its single row is
            # the id's active row.
            lock_active[identifier] = rows[0]
    for row in document["standards"]:
        identifier = str(row["id"])
        if not row.get("active", True):
            continue
        prior = lock_active.get(identifier)
        if row["status"] == "deprecated" or (
            prior is not None and str(prior["version"]) != str(row["version"])
        ):
            triggers.append(identifier)
    if not triggers:
        return []
    compatibility = lock.get("compatibility")
    compatibility = compatibility if isinstance(compatibility, dict) else {}
    missing = [
        field for field in ("main_project", "sdk", "notes") if not compatibility.get(field)
    ]
    if missing:
        return [
            "compatibility_incomplete: "
            f"{', '.join(sorted(triggers))} changed or deprecated but the SDK lock "
            f"compatibility block lacks {', '.join(missing)}"
        ]
    return []
