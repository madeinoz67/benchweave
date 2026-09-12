"""Keep core integration snapshots aligned with plugin-owned projections."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("model", ["sim_psu", "sim_controller"])
def test_execution_descriptor_matches_plugin(model: str) -> None:
    project = ROOT / "plugins" / "benchweave" / model
    source = project / "src" / f"benchweave_{model}"
    snapshot = ROOT / "fixtures" / "execution" / f"descriptor-{model.replace('_', '-')}.json"
    assert (source / "descriptor.json").read_bytes() == snapshot.read_bytes()
    assert (source / "vectors.json").is_file()
    assert (project / "pyproject.toml").is_file()
    assert not (ROOT / "plugins" / model / "plugin.py").exists()
