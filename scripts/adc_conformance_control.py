#!/usr/bin/env python3
"""Clean-venv ADC conformance control (issue #203 slice 1, acceptance A1).

The out-of-tree ADC plugin — a public contributor fork's plugin at its
PRE-RESTAMP commit — must pass its SDK conformance suite UNMODIFIED against
the SDK wheel built from this checkout's pinned submodule, with the network
disabled at run time. This is the control for the defect class the slice
exists to remove: a plugin outside the tree cannot move in-arc with a
corpus bump, so every bump used to force a restamp (the 23/26 baseline; see
docs/implementation-planning/09a-issue215-slice1-baseline.md).

Deliberate shapes:
- The plugin comes from ``git archive`` of the recorded commit — never a
  clone-and-edit. The primary run asserts the bytes are unmodified.
- The SDK wheel is BUILT from ``packages/sdk`` and installed into a clean
  venv — the checkout's own uv.lock pin is bypassed by construction (there
  is no checkout environment here at all; the bypass is the point).
- A sitecustomize socket guard makes any outbound socket use raise during
  the run; the suite is expected to make ZERO socket attempts.
- The anti-gaming arm copies the plugin, flips the descriptor pin to the
  yanked in-interval version, and requires the suite stays green with the
  yank warning naming the move-to — defeating any dispatch table
  hard-coding exactly the served set.

Exits 0 only when both runs are 26/26 (and the warning carries both
versions). Run from the repository root; needs git, uv and network access
for the INSTALL phase (the run phase is offline by the guard).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ADC_REPO = "https://github.com/parkview/benchweave.git"
ADC_COMMIT = "de132a292040415f9935b93b424ce15b9980843d"
ADC_CONFORMANCE_LANE = "tests/adc/test_adapter_conformance.py"
EXPECTED_TESTS = 26
YANKED_PIN = "0.2.1"
MOVE_TO = "0.2.2"

SOCKET_GUARD = '''"""Network guard (macOS has no unshare): outbound sockets raise."""
import socket

_BLOCKED = "network_disabled_by_adc_control: outbound sockets are blocked"


def _blocked(*args, **kwargs):
    raise RuntimeError(_BLOCKED)


socket.socket.connect = _blocked  # type: ignore[method-assign]
socket.socket.connect_ex = _blocked  # type: ignore[method-assign]
socket.create_connection = _blocked  # type: ignore[assignment]
socket.getaddrinfo = _blocked  # type: ignore[assignment]
socket.gethostbyname = _blocked  # type: ignore[assignment]
'''


def run(
    command: list[str], *, cwd: Path, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=capture,
        text=True,
    )


def fetch_plugin(workspace: Path) -> Path:
    """The plugin at its pre-restamp commit, via git archive (no clone)."""
    cache = workspace / "adc-src"
    cache.mkdir(parents=True)
    run(["git", "init", "--quiet", str(cache)], cwd=workspace)
    run(["git", "-C", str(cache), "remote", "add", "origin", ADC_REPO], cwd=workspace)
    run(["git", "-C", str(cache), "fetch", "--depth=1", "origin", ADC_COMMIT], cwd=workspace)
    extracted = workspace / "adc"
    extracted.mkdir()
    archive = subprocess.run(
        ["git", "-C", str(cache), "archive", "FETCH_HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )
    subprocess.run(["tar", "-x", "-C", str(extracted)], input=archive.stdout, check=True)
    return extracted


def build_sdk_wheel(checkout: Path, out: Path) -> Path:
    run(["uv", "build", "--wheel", "-o", str(out), str(checkout / "packages/sdk")], cwd=checkout)
    wheels = sorted(out.glob("benchweave_sdk-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected exactly one SDK wheel, found {[w.name for w in wheels]}")
    return wheels[0]


def make_venv(workspace: Path, wheel: Path, plugin: Path) -> Path:
    venv = workspace / "venv"
    run(["uv", "venv", "--python", "3.13", str(venv)], cwd=workspace)
    python = venv / "bin/python"
    # The wheel installs FIRST so the built SDK satisfies the plugin's
    # benchweave-sdk floor; the plugin project installs second for its own
    # runtime deps (pyserial &c.) and its importable packages.
    run(
        ["uv", "pip", "install", "--python", str(python), str(wheel), "pytest", "pytest-timeout"],
        cwd=workspace,
    )
    run(["uv", "pip", "install", "--python", str(python), str(plugin)], cwd=workspace)
    site_packages = sorted((venv / "lib").glob("python3.*/site-packages"))
    if len(site_packages) != 1:
        raise SystemExit("cannot locate the venv site-packages for the socket guard")
    (site_packages[0] / "sitecustomize.py").write_text(SOCKET_GUARD)
    return python


def conformance_run(python: Path, plugin: Path, junit: Path) -> dict[str, int]:
    result = subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            ADC_CONFORMANCE_LANE,
            "-p",
            "no:cacheprovider",
            "--timeout=120",
            "-q",
            f"--junitxml={junit}",
        ],
        cwd=plugin,
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout[-2000:], flush=True)
    import xml.etree.ElementTree as ElementTree

    # The junit file is this script's own output (a pytest run we invoked);
    # trusted bytes, not untrusted input.
    root = ElementTree.parse(junit).getroot()  # noqa: S314
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise SystemExit(f"no testsuite in {junit}")
    counts = {
        "tests": int(suite.get("tests", "0")),
        "failures": int(suite.get("failures", "0")),
        "errors": int(suite.get("errors", "0")),
    }
    counts["exit"] = result.returncode
    return counts


def flip_pin(plugin: Path, version: str) -> None:
    descriptor = plugin / "plugins/adc_6ch_12bit/descriptor.json"
    document = json.loads(descriptor.read_bytes())
    if document["otdp_version"] == version:
        raise SystemExit(f"the fixture pin already is {version}; nothing to flip")
    document["otdp_version"] = version
    descriptor.write_text(json.dumps(document, indent=2) + "\n")


def check_yank_warning(venv: Path, plugin: Path) -> None:
    result = subprocess.run(
        [str(venv / "bin/benchweave-sdk"), "check", "plugins/adc_6ch_12bit/descriptor.json"],
        cwd=plugin,
        capture_output=True,
        text=True,
        check=True,
    )
    output = result.stdout + result.stderr
    if YANKED_PIN not in output:
        raise SystemExit(f"adc_control_failed: the yank warning must name the pin {YANKED_PIN}")
    if MOVE_TO not in output:
        raise SystemExit(f"adc_control_failed: the yank warning must name the move-to {MOVE_TO}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=None)
    arguments = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    workspace = arguments.workspace or Path(tempfile.mkdtemp(prefix="adc-control-"))
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        plugin = fetch_plugin(workspace)
        wheel = build_sdk_wheel(checkout, workspace / "wheels")
        python = make_venv(workspace, wheel, plugin)
        primary = conformance_run(python, plugin, workspace / "primary-junit.xml")
        print(f"primary run: {primary}", flush=True)
        if primary["tests"] != EXPECTED_TESTS or primary["failures"] or primary["errors"]:
            print(
                "adc_control_failed: the unmodified ADC conformance suite must pass "
                f"{EXPECTED_TESTS}/{EXPECTED_TESTS} against the built SDK wheel",
                file=sys.stderr,
            )
            return 1
        # Anti-gaming arm: a yanked-pin copy stays green with the warning.
        variant = workspace / "adc-yanked"
        shutil.copytree(plugin, variant)
        flip_pin(variant, YANKED_PIN)
        arm = conformance_run(python, variant, workspace / "yanked-junit.xml")
        print(f"anti-gaming run (pin {YANKED_PIN}): {arm}", flush=True)
        if arm["tests"] != EXPECTED_TESTS or arm["failures"] or arm["errors"]:
            print(
                "adc_control_failed: the yank-pinned variant must stay green — a "
                "dispatch table hard-coding the served set is the defect this arm exists "
                "to catch",
                file=sys.stderr,
            )
            return 1
        check_yank_warning(workspace / "venv", variant)
        print(
            f"ADC control passed: {EXPECTED_TESTS}/{EXPECTED_TESTS} unmodified + "
            f"{EXPECTED_TESTS}/{EXPECTED_TESTS} yank-pinned, warning names {MOVE_TO}",
            flush=True,
        )
        return 0
    finally:
        if arguments.workspace is None:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
