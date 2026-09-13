"""Source distributions preserve exact gateway/SDK validator and schema bytes."""

import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sdk_wheel_rebuilt_from_sdist_contains_exact_presentation_contract(tmp_path):
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", str(ROOT / "packages/sdk"), "--out-dir", str(dist)],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(dist.glob("*.whl"))
    schema_path = "benchweave_sdk/contracts/plugin-ui-v0.1.0/ui-manifest.schema.json"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "benchweave_sdk/_presentation_contract.py" in names
        assert schema_path in names
        expected = archive.read("benchweave_sdk/_presentation_contract.py")
        assert expected == (ROOT / "src/benchweave/presentation/contracts.py").read_bytes()
        for name in (
            "ui-manifest",
            "configuration-preset",
            "presentation-envelope",
            "binding-catalogue",
        ):
            relative = f"plugin-ui-v0.1.0/{name}.schema.json"
            assert (
                archive.read(f"benchweave_sdk/contracts/{relative}")
                == (ROOT / "contracts" / relative).read_bytes()
            )
    unpacked = tmp_path / "source"
    unpacked.mkdir()
    with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
        archive.extractall(unpacked, filter="data")
    source = next(unpacked.iterdir())
    rebuilt = tmp_path / "rebuilt"
    subprocess.run(
        ["uv", "build", "--wheel", str(source), "--out-dir", str(rebuilt)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    with zipfile.ZipFile(next(rebuilt.glob("*.whl"))) as archive:
        assert archive.read("benchweave_sdk/_presentation_contract.py") == expected
        assert schema_path in archive.namelist()
