#!/usr/bin/env python3
"""Build both distributions and test a wheel-installed external adapter.

Run with Python 3.13 and uv on PATH. No repository PYTHONPATH, hardware, registry
installation or publication is used. The installed subprocess receives canonical
contract hashes, never a source fallback. --out-dir retains release artefacts and
a verification report; temporary environments and generated projects are removed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

CONTRACT_SETS = ("otdp-v0.3.0", "registry-v1.0.0", "plugin-ui-v0.1.0")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def run(
    command: list[str], *, cwd: Path, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=cwd,
        env=clean_environment(),
        check=True,
        capture_output=capture,
        text=True,
    )


def resources(directory: Any, prefix: str = "") -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for child in sorted(directory.iterdir(), key=lambda item: item.name):
        relative = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            if child.name != "__pycache__":
                result.update(resources(child, relative))
        else:
            result[relative] = child.read_bytes()
    return result


def installed_check(reference: Path, report: Path) -> None:
    """Executed only by the isolated environment, from outside the checkout."""
    from importlib import import_module
    from importlib.metadata import version
    from importlib.resources import files

    import benchweave
    from benchweave.host.plugin import SimulationInfo
    from benchweave.host.types import Identity, OperationRequest, OperationStatus, Reading
    from benchweave.registry.activation import ActivationRejected
    from benchweave.registry.otdp_loading import load_otdp_plugin

    # These modules exist only after the outer process installs their wheels.
    benchweave_sdk = import_module("benchweave_sdk")
    example_plugin = import_module("example_plugin")
    mock_host = import_module("benchweave_sdk.testing").MockHost
    transaction = import_module("example_plugin.protocol").transaction
    expected = json.loads(reference.read_text())
    checkout = Path(expected["checkout"])
    for module in (benchweave, benchweave_sdk, example_plugin):
        assert module.__file__ is not None
        assert not Path(module.__file__).resolve().is_relative_to(checkout)
    assert version("benchweave") == expected["gateway_version"]
    assert version("benchweave-sdk") == expected["sdk_version"]
    assert benchweave_sdk.__version__ == expected["sdk_version"]
    assert benchweave_sdk.OTDP_VERSION == "0.3.0"
    assert benchweave_sdk.ADAPTER_API_VERSION == "1.1"
    assert files("benchweave").joinpath("py.typed").is_file()
    assert files("benchweave_sdk").joinpath("py.typed").is_file()
    packaged = resources(files("benchweave_sdk").joinpath("contracts"))
    packaged_hashes = {name: digest(data) for name, data in packaged.items()}
    assert packaged_hashes == expected["contracts"], "SDK contract resources drifted"

    payload = {
        f"example_plugin/{name}": data
        for name, data in resources(files("example_plugin")).items()
        if Path(name).suffix in {".py", ".json", ".md"}
    }
    assert "example_plugin/protocol.py" in payload
    assert "example_plugin/descriptor.json" in payload
    assert "example_plugin/vectors.json" in payload
    presentation = import_module("benchweave_sdk.presentation")
    admission = import_module("benchweave.presentation.admission")
    for package, path in (
        ("benchweave_sdk", "_presentation_contract.py"),
        ("benchweave", "presentation/contracts.py"),
    ):
        assert digest(files(package).joinpath(path).read_bytes()) == expected["presentation_sha256"]
    envelope = payload["example_plugin/presentation.json"]
    descriptor_raw = payload["example_plugin/descriptor.json"]
    catalogue = json.loads(payload["example_plugin/binding-catalogue.json"])
    ui_resources = resources(files("example_plugin").joinpath("ui"))
    sdk_report = presentation.validate_presentation(
        envelope,
        descriptor_raw=descriptor_raw,
        resources=ui_resources,
        binding_catalogue=catalogue,
        firmware="1.0.0",
    )
    gateway_report = admission.validate_attachment(
        envelope,
        descriptor_raw=descriptor_raw,
        verified_resources=ui_resources,
        binding_catalogue=catalogue,
        schema_documents=presentation.schemas(),
        supported_features=frozenset(),
        supported_panels=frozenset(),
        firmware="1.0.0",
    )
    assert sdk_report.valid and gateway_report.valid, (sdk_report, gateway_report)
    # A synthetic admitted-cache fixture tests the loader's execution integrity;
    # registry admission/closure policy remains covered by the registry suite.
    manifest = {
        "payload": {
            "files": [
                {
                    "path": name,
                    "bytes": len(data),
                    "sha256": digest(data),
                    "role": "implementation" if name.endswith(".py") else "resource",
                }
                for name, data in sorted(payload.items())
            ]
        }
    }
    manifest_sha = digest(canonical(manifest))
    cache = reference.parent / "cache"
    for name, data in payload.items():
        destination = cache / manifest_sha / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    descriptor = json.loads(payload["example_plugin/descriptor.json"])
    host = mock_host(
        [
            (transaction("identify"), {"data": b"SDK Example,demo,SIM001,1.0.0\n"}),
            (transaction("read"), {"data": b"3.3\n"}),
        ]
    )
    options = {
        "entry_relpath": "example_plugin/adapter.py",
        "descriptor": descriptor,
        "services": host,
        "simulation": SimulationInfo(True, "SDK synthetic wheel smoke"),
    }
    bridge = load_otdp_plugin(cache, manifest, manifest_sha, **options)
    try:
        bridge.plugin_open(object())
        identity = bridge.dispatch(
            OperationRequest.identify("smoke-identify"),
            deadline_ns=int((host.monotonic() + 1) * 1_000_000_000),
        )
        assert identity.status is OperationStatus.OK, identity
        assert isinstance(identity.data, Identity)
        assert identity.data.model == "demo"
        reading = bridge.dispatch(
            OperationRequest.read("smoke-read", parameter="voltage"),
            deadline_ns=int((host.monotonic() + 1) * 1_000_000_000),
        )
        assert reading.status is OperationStatus.OK, reading
        assert isinstance(reading.data, Reading)
        assert reading.data.value == 3.3
        host.assert_complete()
    finally:
        bridge.plugin_close()
    assert host.closed
    tampered = cache / manifest_sha / "example_plugin/protocol.py"
    tampered.write_bytes(tampered.read_bytes() + b"\n# changed after admission\n")
    try:
        load_otdp_plugin(cache, manifest, manifest_sha, **options)
    except ActivationRejected as exc:
        assert exc.reason == "file_hash_mismatch"
    else:
        raise AssertionError("Tampered helper module was accepted")
    report.write_text(
        json.dumps(
            {
                "gateway_version": expected["gateway_version"],
                "sdk_version": expected["sdk_version"],
                "otdp_version": "0.3.0",
                "adapter_api_version": "1.1",
                "contract_files_verified": len(packaged_hashes),
                "example": "wheel installed outside checkout; identify/read passed",
                "tampered_helper": "rejected before import",
                "presentation": (
                    "installed UI resources and identical SDK/gateway validator verified"
                ),
                "hardware": "none; deterministic MockHost only",
            },
            indent=2,
        )
        + "\n"
    )
    print("SDK installed-wheel, contract and gateway smoke passed", flush=True)


def build_and_check(out_dir: Path) -> None:
    checkout = Path(__file__).resolve().parents[1]
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    gateway_out, sdk_out = out_dir / "gateway", out_dir / "sdk"
    # uv's default builds a wheel FROM the sdist, testing both distributions.
    run(["uv", "build", "--out-dir", str(gateway_out), str(checkout)], cwd=checkout)
    run(["uv", "build", "--out-dir", str(sdk_out), str(checkout / "packages/sdk")], cwd=checkout)
    gateway_metadata = tomllib.loads((checkout / "pyproject.toml").read_text())
    sdk_metadata = tomllib.loads((checkout / "packages/sdk/pyproject.toml").read_text())
    expected = {
        "checkout": str(checkout),
        "gateway_version": gateway_metadata["project"]["version"],
        "sdk_version": sdk_metadata["project"]["version"],
        "presentation_sha256": digest(
            (checkout / "src/benchweave/presentation/contracts.py").read_bytes()
        ),
        "contracts": {
            f"{name}/{relative}": digest(data)
            for name in CONTRACT_SETS
            for relative, data in resources(checkout / "contracts" / name).items()
        },
    }
    gateway_wheel = gateway_out / f"benchweave-{expected['gateway_version']}-py3-none-any.whl"
    sdk_wheel = sdk_out / f"benchweave_sdk-{expected['sdk_version']}-py3-none-any.whl"
    assert gateway_wheel.is_file() and sdk_wheel.is_file()
    with tempfile.TemporaryDirectory(prefix="benchweave-sdk-smoke-") as directory:
        workspace = Path(directory).resolve()
        python = workspace / "venv/bin/python"
        run(["uv", "venv", "--python", sys.executable, str(workspace / "venv")], cwd=workspace)
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                str(gateway_wheel),
                str(sdk_wheel),
                "pytest",
            ],
            cwd=workspace,
        )
        # The Click CLI's contract (a bare invocation prints usage and exits 1,
        # so the retired bare-call smoke broke): --version exits 0 and names
        # the installed distribution's version — assert it matches the wheel.
        installed_version = run(
            [str(workspace / "venv/bin/benchweave"), "--version"], cwd=workspace, capture=True
        )
        assert installed_version.stdout
        assert installed_version.stdout.strip() == (
            f"benchweave, version {expected['gateway_version']}"
        ), installed_version.stdout
        generated = workspace / "external-example"
        run(
            [
                str(workspace / "venv/bin/benchweave-sdk"),
                "new",
                str(generated),
                "--package",
                "example_plugin",
                "--with-ui",
            ],
            cwd=workspace,
        )
        example_out = workspace / "example-dist"
        run(["uv", "build", "--out-dir", str(example_out), str(generated)], cwd=workspace)
        example_wheels = list(example_out.glob("*.whl"))
        assert len(example_wheels) == 1
        run(
            ["uv", "pip", "install", "--python", str(python), str(example_wheels[0])], cwd=workspace
        )
        # Test files have no source tree nearby and the interpreter ignores
        # PYTHONPATH/user site. All three projects must import their wheels.
        test_directory = workspace / "installed-tests"
        shutil.copytree(generated / "tests", test_directory)
        run(
            [
                str(python),
                "-I",
                "-m",
                "pytest",
                "--import-mode=importlib",
                "-q",
                str(test_directory),
            ],
            cwd=workspace,
        )
        reference = workspace / "reference.json"
        reference.write_bytes(canonical(expected))
        standalone = workspace / "sdk_smoke.py"
        shutil.copyfile(__file__, standalone)
        run(
            [
                str(python),
                "-I",
                str(standalone),
                "--installed-check",
                str(reference),
                "--report",
                str(out_dir / "sdk-smoke.json"),
            ],
            cwd=workspace,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("dist/packages"))
    parser.add_argument("--installed-check", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.installed_check:
        if not arguments.report:
            parser.error("--installed-check requires --report")
        installed_check(arguments.installed_check, arguments.report)
    else:
        build_and_check(arguments.out_dir)


if __name__ == "__main__":
    main()
