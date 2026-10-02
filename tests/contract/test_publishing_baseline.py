"""The A1 RED baseline: no signed submission path exists in current tooling.

Committed FIRST, before the publishing lane's mechanism (design §4 slice 1,
acceptance A1). Two honest facts about the tools at the slice-1 merge base,
pinned here:

1. ``publish_dev.py`` cannot package the ADC-class control at all — the
   DPS-150 is an adapter plugin (``adapter.py``), the dev publisher requires
   the legacy ``plugin.py`` entry shape, so the flow refuses before any bytes
   are written.
2. Where the dev publisher does work (the legacy sim-plugin shape), its output
   is dev-unsigned BY CONSTRUCTION — zero signature files, a ``dev-local``
   registry id — and it stays that way forever (its docstring's promise; the
   keyless property is a pinned posture).

A signed third-party-style submission therefore required manual assembly; the
step count at baseline is recorded below with its denominator.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DPS150 = REPO / "plugins" / "fnirsi" / "dps150"

#: The manual-assembly step count a signed third-party-style submission needed
#: at the merge base, before ``benchweave-sdk package`` existed. Denominator:
#: the 25 required top-level manifest fields (standards/registry 0.1.1
#: release-manifest.schema.json's required array), none derivable by the dev
#: publisher for a third-party tree (it hardcodes the fixture identity), plus
#: 4 hand-built documents (SBOM, build provenance, dependency lock, review
#: record), plus 1 hand-run signing step (fixture-key tooling wired to the
#: fixed catalogue). 25 + 4 + 1 = 30 manual steps — the ADC-class friction
#: the PRD measured as two hand-restamps.
MANUAL_STEPS_AT_BASELINE = 25 + 4 + 1


def _export_tree(tmp_path: Path, ref: str, tree: str) -> Path:
    tar = tmp_path / (tree.rsplit("/", 1)[-1] + ".tar")
    subprocess.run(
        ["git", "archive", "--format=tar", ref, "--", tree],
        cwd=REPO,
        check=True,
        stdout=open(tar, "wb"),  # noqa: SIM115 — the run closes the fd
    )
    export = tmp_path / "export"
    shutil.unpack_archive(tar, export, format="tar")
    return export / tree


def _publish_dev(plugin: Path, out: Path) -> subprocess.CompletedProcess[str]:
    script = str(REPO / "scripts" / "registry" / "publish_dev.py")
    return subprocess.run(
        [sys.executable, script, str(plugin), "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_publish_dev_cannot_package_the_adc_class_control(tmp_path: Path) -> None:
    """The DPS-150 (adapter shape) refuses at the dev publisher's entry check."""
    plugin = _export_tree(tmp_path, "HEAD", "plugins/fnirsi/dps150")
    completed = _publish_dev(plugin, tmp_path / "dev-registry")
    assert completed.returncode != 0
    assert "plugin entry missing" in completed.stderr
    assert not (tmp_path / "dev-registry").exists() or not list(
        (tmp_path / "dev-registry").rglob("*.sig")
    )


def test_publish_dev_output_is_dev_unsigned_by_construction(tmp_path: Path) -> None:
    """Where the dev loop works (legacy sim shape), it writes no signatures."""
    plugin = _export_tree(tmp_path, "HEAD", "plugins/benchweave/sim_psu")
    out = tmp_path / "dev-registry"
    completed = _publish_dev(plugin, out)
    assert completed.returncode == 0, completed.stderr
    assert sorted(out.rglob("*.sig")) == [], "the dev loop is keyless by construction"
    manifest = json.loads(sorted(out.rglob("manifest.json"))[0].read_bytes())
    assert manifest["registry_id"] == "dev-local"


def test_the_manual_step_count_is_recorded() -> None:
    """The baseline's denominator is pinned: 25 fields + 4 documents + 1 signing."""
    schema = json.loads(
        (REPO / "standards" / "registry" / "0.1.1" / "release-manifest.schema.json").read_bytes()
    )
    assert len(schema["required"]) == 25
    assert MANUAL_STEPS_AT_BASELINE == 30


@pytest.mark.parametrize("exists", [True])
def test_no_signed_third_party_path_existed_at_baseline(exists: bool) -> None:
    """The gateway's only signing tool at base was the fixture builder.

    ``build_fixtures.py`` emits the fixed five-release catalogue from
    hardcoded fixture identities — it cannot sign a third-party submission,
    which is why A1's falsifier had to wait for the lane.
    """
    assert exists
    fixture_builder = REPO / "scripts" / "registry" / "build_fixtures.py"
    text = fixture_builder.read_text(encoding="utf-8")
    assert '"plugins"' in text and '"benchweave"' in text  # in-tree fixtures only
    assert "fnirsi" not in text  # the ADC-class control is not a fixture input
