"""Source distributions preserve exact gateway/SDK validator and schema bytes."""

import hashlib
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_sdk_wheel_rebuilt_from_sdist_contains_exact_presentation_contract(tmp_path: Path) -> None:
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
        preview_schema = "benchweave_sdk/contracts/plugin-ui-preview-v1/fixture.schema.json"
        assert preview_schema in names
        inventory_path = "benchweave_sdk/preview_assets/inventory.json"
        inventory = json.loads(archive.read(inventory_path))
        assert inventory["api_version"] == 1
        assert inventory["assets"]
        for asset in inventory["assets"]:
            packaged = archive.read(f"benchweave_sdk/preview_assets/{asset['path']}")
            assert len(packaged) == asset["size"]
            assert hashlib.sha256(packaged).hexdigest() == asset["sha256"]
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
        assert preview_schema in archive.namelist()
        rebuilt_inventory = json.loads(archive.read(inventory_path))
        assert rebuilt_inventory == inventory
        for asset in rebuilt_inventory["assets"]:
            packaged = archive.read(f"benchweave_sdk/preview_assets/{asset['path']}")
            assert hashlib.sha256(packaged).hexdigest() == asset["sha256"]
