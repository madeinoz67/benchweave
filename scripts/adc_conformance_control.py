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
  clone-and-edit. The tested tree IS the archive (unmodified by
  construction), and the INSTALLED package is byte-asserted against the
  archive's ``src/`` tree per file (``assert_installed_matches_archive``) —
  the suite imports the installed copy, so that is the copy whose bytes
  must be the archive's (#215 fold row 17).
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
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Third-party dependency (#215 fold row 17): the INSTALL phase fetches this
# public contributor fork at the pinned commit below. Failure mode: the repo
# or commit becoming unavailable (renamed, archived, force-pushed away) fails
# this control's fetch step before any test runs — the lane cannot run, and
# the committed ADC_COMMIT is the only authority. The external repo is
# deliberately NOT vendored: the dependency is named here, not inlined.
ADC_REPO = "https://github.com/parkview/benchweave.git"
ADC_COMMIT = "de132a292040415f9935b93b424ce15b9980843d"
ADC_CONFORMANCE_LANE = "tests/adc/test_adapter_conformance.py"
EXPECTED_TESTS = 26

REPO_ROOT = Path(__file__).resolve().parents[1]


def _otdp_policy_facts() -> tuple[str, str]:
    """(yanked_pin, move_to) derived from the committed policy block — the
    authority the built wheel's lock mirrors (``make check-sdk-standards``
    refuses drift between them). Deriving replaces the hand-swept literals
    the zero-literal gate exists to remove (issue #269 §2.1): the
    anti-gaming arm then always plants the CURRENT yanked version, and the
    recorded motion mechanism ("both flip with the yank policy block")
    becomes mechanical instead of remembered. Tautology boundary: the
    control asserts OBSERVED warning content (from the built wheel + the
    external plugin) against this AUTHORITY read (the checkout manifest) —
    different objects; the residual is consistent corruption of manifest
    AND lock together, which ``make check-sdk-standards``'s sync lane
    owns. The move-to == active equivalence is a theorem of the policy
    shape (the served rule's move-to is the version-tuple-max of the SERVED
    set, else the range's lower bound — ``dependency.py::_move_to``, with
    no >=pin filter and a real lower-bound fallback; while the active
    entry is the highest served version, move-to IS the active entry);
    its failure mode is this control failing loudly below — the redesign
    trigger, never a silent wrong assertion. The yanked == active shape
    is REFUSED outright (``adc_yank_is_active:`` — fold wave row 4): it
    would make the warning checks vacuous.
    """
    manifest_path = REPO_ROOT / "standards" / "standards-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Unreadable/unparsable authority exits with the adc_ prefix (fold
        # wave row 8) — never a raw traceback.
        raise SystemExit(f"adc_policy_unreadable: {manifest_path}: {exc}") from exc
    entry = next((s for s in manifest["standards"] if s.get("id") == "otdp"), None)
    if entry is None:
        raise SystemExit("adc_policy_absent: no otdp entry in the standards manifest")
    policy = manifest["dependency_policy"]["standards"].get("otdp", {})
    yanked = sorted(policy.get("yanked", {}))
    if len(yanked) != 1:
        raise SystemExit(
            "adc_yank_not_unique: the control's anti-gaming arm needs exactly "
            f"one yanked otdp version, found {yanked}"
        )
    active = str(entry["version"])
    if yanked[0] == active:
        # Fold wave row 4 (adv-lane1 F1): under yanked == active the
        # derivation would return (active, active) and the warning
        # substring checks would pass against ANY output naming the active
        # version — the anti-gaming arm would go vacuous. The shape is
        # refused; re-rolling a yank ONTO the active version is a policy
        # redesign the control must not silently absorb.
        raise SystemExit(
            f"adc_yank_is_active: the only yanked otdp version ({yanked[0]}) "
            "equals the active entry — the anti-gaming arm's warning checks "
            "would be vacuous; redesign the policy shape first"
        )
    return yanked[0], active


YANKED_PIN, MOVE_TO = _otdp_policy_facts()

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


def assert_installed_matches_archive(plugin: Path, venv: Path) -> None:
    """The installed ``benchweave`` package must be the archive's bytes.

    #215 fold row 17: the conformance suite runs from the archive tree but
    IMPORTS the installed package, so "unmodified" needs a real assertion on
    the installed copy, not only the by-construction posture of running from
    the archive. Every ``src/benchweave/**/*.py`` file is sha256-compared
    against its installed counterpart; any difference, or any missing file,
    fails the control before a test runs.
    """
    source = plugin / "src" / "benchweave"
    installed = sorted((venv / "lib").glob("python3.*/site-packages/benchweave"))
    if len(installed) != 1 or not installed[0].is_dir():
        raise SystemExit(
            "adc_control_failed: the installed benchweave package was not found; "
            "the byte assertion cannot run"
        )
    files = sorted(source.rglob("*.py"))
    if not files:
        raise SystemExit("adc_control_failed: the archive carries no src/benchweave files")
    for relative in files:
        digest = hashlib.sha256(relative.read_bytes()).hexdigest()
        counterpart = installed[0] / relative.relative_to(source)
        if not counterpart.is_file():
            raise SystemExit(
                f"adc_control_failed: {relative.name} is missing from the installed package"
            )
        if hashlib.sha256(counterpart.read_bytes()).hexdigest() != digest:
            raise SystemExit(
                "adc_control_failed: an installed file differs from the archive bytes "
                f"({relative.relative_to(source)})"
            )


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
    checkout = REPO_ROOT
    workspace = arguments.workspace or Path(tempfile.mkdtemp(prefix="adc-control-"))
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        plugin = fetch_plugin(workspace)
        wheel = build_sdk_wheel(checkout, workspace / "wheels")
        python = make_venv(workspace, wheel, plugin)
        assert_installed_matches_archive(plugin, workspace / "venv")
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
