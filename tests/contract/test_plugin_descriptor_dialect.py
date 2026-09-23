"""The plugin descriptor dialect triangle (CON-10) holds.

Three version facts must be the same version, and the tree already commits to
that equation twice over:

- ``descriptor == lock``: the device-plugin lane validates its descriptor
  against ``contracts/<lock directory>/otdp-device-descriptor.schema.json``,
  whose ``properties.otdp_version`` is a ``const`` naming that corpus version.
  A divergence is not a style disagreement — ``jsonschema`` refuses the
  document.
- ``descriptor == active``: CON-10 is "One descriptor dialect, projected".
  Gateway admission resolves the ACTIVE descriptor schema from
  ``standards/standards-manifest.json`` and ``benchweave-sdk check`` validates
  against its vendored tree, so the equivalence census
  (``tests/sdk/test_descriptor_equivalence.py``) pins both gates equivalent
  over the in-tree corpus.

Hence ``lock == descriptor == active``. A tree outside that triangle is broken
by construction in at least one lane — which is exactly how a half-done stamp
cascade shipped: the descriptor half moved, the evidence-lock half did not,
and the two halves were red in two different workflows whose rollups were
never read together.

What this does NOT catch: a descriptor whose ``otdp_version`` is correct but
whose body is not valid active-dialect (admission's job), the fixture-lattice
copies under ``fixtures/execution/`` (they move with the digest chain —
bench -> commissioning -> run-binding — and are pinned by the bootstrap
suite), or any plugin source outside ``plugins/``.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DESCRIPTOR_GLOB = "plugins/*/*/src/*/descriptor.json"
LOCK = REPO / "plugins/fnirsi/dps150/contracts/lock.json"


def _active_otdp_version() -> str:
    """The otdp entry's version in the standards manifest — the same authority
    ``benchweave.control.documents._descriptor_validator`` resolves the active
    descriptor schema through, so this cannot drift from admission."""
    from benchweave.standards.manifest import load_manifest

    entries = [e for e in load_manifest(REPO).standards if e.id == "otdp"]
    assert len(entries) == 1, f"expected one otdp manifest entry, got {len(entries)}"
    return entries[0].version


def _plugin_descriptors() -> dict[str, dict[str, object]]:
    found = {
        str(path.relative_to(REPO)): json.loads(path.read_text())
        for path in sorted(REPO.glob(DESCRIPTOR_GLOB))
    }
    assert found, f"no plugin source descriptors matched {DESCRIPTOR_GLOB}"
    return found


def test_plugin_source_descriptors_declare_the_active_otdp_version() -> None:
    """Every plugin source descriptor names the active OTDP version.

    The set is the glob above (4 of 4 at this commit: sim_psu, sim_controller,
    sim_scope, fnirsi-dps150) — regenerable, not hand-listed. The failure this
    catches is the stamp-cascade miss: a standards bump that moves the active
    corpus without moving the in-tree descriptors, which the equivalence census
    then reports only as an indirect schema-const refusal on a clean cell.
    """
    active = _active_otdp_version()
    stale = {
        path: doc["otdp_version"]
        for path, doc in _plugin_descriptors().items()
        if doc.get("otdp_version") != active
    }
    assert not stale, f"active OTDP is {active} but these descriptors are stale: {stale}"


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
