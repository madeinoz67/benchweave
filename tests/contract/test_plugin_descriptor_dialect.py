"""The plugin descriptor dialect triangle (CON-10), within-range (VR-45).

Three version facts must agree, and since #217 the agreement is
``lock == descriptor == a-served-pin`` — NOT ``== active``:

- ``descriptor == a-served-pin``: per-pin admission (design §3.3) validates
  each descriptor against its OWN ``otdp_version`` pin's digest-verified
  bytes, so a plugin stays admissible while the corpus's active version
  advances past it, as long as the pin sits inside the served set
  (retained ∧ in-range ∧ ¬yanked). The forced-restamp invariant — every
  bump invalidating every pin whether or not the plugin's standard moved —
  is what this lane retires.
- ``descriptor == lock``: the device-plugin lane validates its descriptor
  against ``contracts/<lock directory>/otdp-device-descriptor.schema.json``,
  whose ``properties.otdp_version`` is a ``const`` naming that corpus
  version. A divergence is not a style disagreement — ``jsonschema``
  refuses the document.

VR-45's control arm re-derives the OLD assertion's failure on every run:
against a fixture manifest with active advanced past the pins, the
``== active`` form fails all four in-tree descriptors (the pre-#217
behavior), while the within-range form passes — the retirement is pinned,
not assumed.

What this does NOT catch: a descriptor whose ``otdp_version`` is served but
whose body is not valid in that dialect (admission's job), the
fixture-lattice copies under ``fixtures/execution/`` (they move with the
digest chain — bench -> commissioning -> run-binding — and are pinned by
the bootstrap suite), or any plugin source outside ``plugins/``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DESCRIPTOR_GLOB = "plugins/*/*/src/*/descriptor.json"
LOCK = REPO / "plugins/fnirsi/dps150/contracts/lock.json"


def _served_otdp(root: Path = REPO) -> set[str]:
    """The served otdp set from the committed policy block + corpus rows —
    the same authority admission classifies pins against."""
    from benchweave.standards.manifest import (
        load_dependency_policy,
        served_versions,
    )

    return set(served_versions(load_dependency_policy(root), root, "otdp"))


def _plugin_descriptors() -> dict[str, dict[str, object]]:
    found = {
        str(path.relative_to(REPO)): json.loads(path.read_text())
        for path in sorted(REPO.glob(DESCRIPTOR_GLOB))
    }
    assert found, f"no plugin source descriptors matched {DESCRIPTOR_GLOB}"
    return found


def test_plugin_source_descriptors_pin_served_versions() -> None:
    """Every plugin source descriptor names a SERVED OTDP version (VR-45's
    within-range form; the set is the glob above — 4 of 4 at this commit,
    regenerable, not hand-listed). The failure this catches is the pin
    falling out of the served window — retired, yanked-out, or below the
    range's floor — which is the only bump that must move a plugin."""
    served = _served_otdp()
    unserved = {
        path: doc["otdp_version"]
        for path, doc in _plugin_descriptors().items()
        if doc.get("otdp_version") not in served
    }
    assert not unserved, (
        f"served OTDP is {sorted(served)} but these pins are outside it: {unserved}"
    )


def test_dps150_declared_dialect_matches_its_evidence_lock() -> None:
    """dps150's declared dialect is the corpus its evidence lock pins.

    The device-plugin lane validates the descriptor against the lock's schema,
    so a divergence fails there — but in a SEPARATE workflow
    (``.github/workflows/device-plugins.yml``), whose redness a main-repo
    rollup does not show. This states the invariant in the same check run as
    the equivalence arm so the two halves cannot be half-fixed and half-seen.
    """
    descriptor = json.loads(
        (REPO / "plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.json").read_text()
    )
    lock = json.loads(LOCK.read_text())
    assert descriptor["otdp_version"] == lock["otdp_version"], (
        f"dps150 declares otdp_version {descriptor['otdp_version']} but its evidence "
        f"lock pins the {lock['otdp_version']} corpus ({lock['directory']}) — the "
        "descriptor is validated against that corpus's schema, whose otdp_version "
        "const names it"
    )
    assert lock["directory"] == f"standards/otdp/{lock['otdp_version']}", (
        f"lock directory {lock['directory']} does not name its own otdp_version "
        f"{lock['otdp_version']}"
    )


def _advanced_fixture(tmp_path: Path) -> Path:
    """A standards tree whose otdp ACTIVE version has advanced past 0.2.2.

    ``otdp/0.2.3/`` is byte-copies of 0.2.2's files (the corpus example of a
    version-strings-only successor — the B6 pair's shape), with corpus rows
    appended and the manifest entry re-pointed, all inside tmp: the fixture
    advances active WITHOUT moving a single committed byte. The policy range
    (>=0.2.0,<0.3.0) already covers 0.2.3, so the served set grows to
    {0.2.0, 0.2.2, 0.2.3}.
    """
    root = tmp_path / "root"
    root.mkdir()
    shutil.copytree(REPO / "standards", root / "standards")
    shutil.copytree(
        root / "standards" / "otdp" / "0.2.2", root / "standards" / "otdp" / "0.2.3"
    )
    corpus_path = root / "standards" / "corpus-manifest.json"
    corpus = json.loads(corpus_path.read_bytes())
    existing = {row["path"] for row in corpus["files"]}
    standards = root / "standards"
    for path in sorted(standards.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(standards).as_posix()
        if relative.startswith("otdp/0.2.3/") and relative not in existing:
            corpus["files"].append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    corpus_path.write_text(json.dumps(corpus, indent=1))
    manifest_path = root / "standards" / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for entry in manifest["standards"]:
        if entry["id"] == "otdp":
            entry["version"] = "0.2.3"
            entry["normative"] = [
                pinned.replace("0.2.2/", "0.2.3/") for pinned in entry["normative"]
            ]
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return root


def test_vr45_the_old_active_assertion_fails_the_advanced_fixture(
    tmp_path: Path,
) -> None:
    """VR-45's control: the RETIRED ``== active`` form, re-derived red on
    every run. Against the advanced fixture (active 0.2.3) the old
    assertion fails all four in-tree descriptors — the forced-restamp
    invariant this lane removes, kept visible so the retirement is pinned
    rather than assumed."""
    from benchweave.standards.manifest import load_manifest

    root = _advanced_fixture(tmp_path)
    entries = [e for e in load_manifest(root).standards if e.id == "otdp"]
    assert len(entries) == 1 and entries[0].version == "0.2.3"
    active = entries[0].version
    stale = {
        path: doc["otdp_version"]
        for path, doc in _plugin_descriptors().items()
        if doc.get("otdp_version") != active
    }
    assert stale and set(stale.values()) == {"0.2.2"}, (
        "the OLD assertion's premise: every in-tree descriptor pins 0.2.2 "
        f"while the fixture active is {active} — got {stale}"
    )


def test_vr45_the_within_range_form_passes_the_advanced_fixture(
    tmp_path: Path,
) -> None:
    """VR-45's acceptance: DPS-150 (and every in-tree plugin) passes at its
    0.2.2 pin while the fixture manifest advances active past it — the pin
    stays inside the fixture's served set, so the evidence lock and the
    descriptor both stay put."""
    root = _advanced_fixture(tmp_path)
    served = _served_otdp(root)
    assert served >= {"0.2.0", "0.2.2", "0.2.3"}, served
    for path, doc in _plugin_descriptors().items():
        assert doc["otdp_version"] in served, (
            f"{path} pins {doc['otdp_version']}, outside the advanced fixture's "
            f"served set {sorted(served)}"
        )
    lock = json.loads(LOCK.read_text())
    assert lock["otdp_version"] == "0.2.2"
    assert lock["otdp_version"] in served
