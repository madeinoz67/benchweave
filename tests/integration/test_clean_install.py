"""Task 15: the clean-install gate — the operator guide's executable form.

A session-scoped fixture builds the wheel (``uv build``), installs it into
a TEMP venv (never the dev venv), and yields the REAL console-script
binary. Every step then drives ``<venv>/bin/benchweave`` as a subprocess —
no CliRunner, no in-process imports of the shipped code — so the gate
proves the PRD-01 flow on a genuinely fresh install:

``setup`` (fresh store + 0600 credential) → fresh-install ``demo``
(SIMULATION label asserted; ``--fixtures`` passed explicitly — the T11
disclosure: the demo's fixture default resolves relative to the REPO, so a
wheel-installed CLI cannot use it) → ``report --json`` over the kept
scratch (the demo run, its outcome, and its evidence digests) → ``backup``
(every manifest digest independently recomputed) → simulated damage to the
live copy of a backed-up artifact → ``restore`` (heals it) → ``verify``
exit 0. The archive digest gate is then pinned from the other side:
damaging a file INSIDE the backup makes ``restore`` refuse.

Fixture/credential separation (controller ruling 1): the operator data dir
that ``setup`` credentials and the demo's scratch tree live under DISTINCT
roots, asserted here — the demo never writes (or reads) a credential, and
the credential survives the whole flow byte-for-byte.

Marker: ``@pytest.mark.slow`` per the repo convention (real child-process
orchestration; deselect locally with ``-m 'not slow'``). There is no
separate slow CI lane — the ``gates`` job runs ``uv run pytest -q`` with no
marker filter, so this suite runs in CI alongside the rest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXECUTION_LATTICE = REPO / "fixtures" / "execution"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class WheelInstall:
    """The clean-install surface: the wheel-installed entrypoint binary."""

    binary: Path

    def run(
        self, *args: str, timeout: float = 360.0
    ) -> subprocess.CompletedProcess[str]:
        """Run the real binary; BENCHWEAVE_* env is stripped so the outer
        test environment cannot leak into the fresh install's defaults."""
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("BENCHWEAVE_")
        }
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            [str(self.binary), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )


@pytest.fixture(scope="session")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Iterator[WheelInstall]:
    """Build the wheel and install it into a throwaway venv (never the dev
    venv) — the clean install under test."""
    root = tmp_path_factory.mktemp("clean-install")
    dist = root / "dist"
    build = subprocess.run(  # noqa: S603, S607 - fixed argv; uv is the toolchain
        ["uv", "build", "--out-dir", str(dist)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert build.returncode == 0, f"uv build failed:\n{build.stderr}"
    wheels = sorted(dist.glob("benchweave-*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, found: {wheels}"
    venv = root / "venv"
    created = subprocess.run(  # noqa: S603, S607
        ["uv", "venv", str(venv)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert created.returncode == 0, f"uv venv failed:\n{created.stderr}"
    installed = subprocess.run(  # noqa: S603, S607
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv / "bin" / "python"),
            str(wheels[0]),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert installed.returncode == 0, f"wheel install failed:\n{installed.stderr}"
    binary = venv / "bin" / "benchweave"
    assert binary.is_file(), "the wheel must install the benchweave console script"
    yield WheelInstall(binary=binary)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- the gate: the full PRD-01 operator flow on a fresh install ------------------


@pytest.mark.slow
def test_clean_install_operator_flow(wheel: WheelInstall, tmp_path: Path) -> None:
    """setup → demo (SIMULATION) → report → backup → damage → restore → verify."""
    # Step 0 — the entrypoint itself: --version/--help answer from the wheel.
    version = wheel.run("--version", timeout=60)
    assert version.returncode == 0, version.stderr
    assert "benchweave" in version.stdout
    assert wheel.run("--help", timeout=60).returncode == 0

    # Two distinct roots: the operator's credentialed data dir, and the
    # demo's simulation scratch. Neither tree may contain the other.
    data_root = tmp_path / "operator"
    scratch_root = tmp_path / "simulation"
    data_dir = data_root / "data"
    scratch = scratch_root / "demo"

    # Step 1 — setup: fresh store + 0600 credential file; secret never printed.
    result = wheel.run("setup", "--data-dir", str(data_dir), "--json")
    assert result.returncode == 0, result.stderr
    setup_payload = json.loads(result.stdout)
    assert setup_payload["data_dir"] == str(data_dir)
    assert setup_payload["db_path"] == str(data_dir / "state.sqlite")
    assert "secret" not in setup_payload, "setup never prints the secret unasked"
    credential = data_dir / "benchweave.env"
    assert credential.is_file()
    assert stat.S_IMODE(credential.stat().st_mode) == 0o600
    secret_before = credential.read_bytes()

    # Step 2 — fresh-install demo: SIMULATION-labelled, fixtures explicit
    # (the T11 disclosure — the wheel's fixture default points into the
    # venv's site-packages parent, where no lattice exists).
    assert (EXECUTION_LATTICE / "run-binding.json").is_file()
    result = wheel.run(
        "demo",
        "--scratch",
        str(scratch),
        "--keep",
        "--fixtures",
        str(EXECUTION_LATTICE),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    demo = json.loads(result.stdout)
    assert demo["mode"] == "simulation"
    assert demo["simulation"] is True
    assert demo["label"] == "SIMULATION"
    assert demo["scratch_dir"] == str(scratch)
    assert demo["bench_id"] == "sim-bench"
    assert demo["state"] == "terminal"
    assert demo["outcome"] == "passed"
    assert demo["safe_state"] == "verified"
    assert demo["run_id"].startswith("run-")
    terminal_sha = demo["terminal_record"]["sha256"]
    assert _SHA256.match(terminal_sha)
    assert demo["evidence_digests"], "the simulator run retains evidence digests"
    assert all(_SHA256.match(digest) for digest in demo["evidence_digests"])

    # Fixture/credential separation (ruling 1): distinct roots, and the demo
    # neither touches the credential nor writes one of its own.
    assert not scratch.is_relative_to(data_root)
    assert not credential.is_relative_to(scratch_root)
    assert not any(
        path.name == "benchweave.env" for path in scratch_root.rglob("*")
    ), "the demo must never write a credential file under its scratch root"
    assert credential.read_bytes() == secret_before, "the credential survived untouched"
    assert (scratch / "state.sqlite").is_file(), "--keep retains the demo store"

    # Step 3 — report over the kept scratch: the demo's run, outcome, and
    # evidence digests, read back from the store at rest.
    result = wheel.run("report", "--data-dir", str(scratch), "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["simulation"] is True
    assert any(bench.get("simulation") for bench in report["benches"])
    runs = [run for run in report["runs"] if run["id"] == demo["run_id"]]
    assert len(runs) == 1, f"the demo run {demo['run_id']} must be in the report"
    assert runs[0]["state"] == "terminal"
    assert runs[0]["outcome"] == demo["outcome"]
    assert runs[0].get("simulation") is True
    assert report["evidence"], "the demo run must leave evidence in the store"
    assert all(_SHA256.match(entry["digest"]) for entry in report["evidence"])
    assert all(entry["present"] for entry in report["evidence"])
    assert report["missing_evidence"] == []

    # Step 4 — backup: snapshot + manifest; every digest independently
    # recomputed here (the digests-verified gate), credentials excluded.
    backups = tmp_path / "backups"
    result = wheel.run("backup", "--data-dir", str(scratch), "--out", str(backups), "--json")
    assert result.returncode == 0, result.stderr
    archive = Path(json.loads(result.stdout)["backup"])
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    assert "state.sqlite" in manifest["files"]
    for rel, expected in manifest["files"].items():
        assert _sha256(archive / rel) == expected, f"manifest digest wrong for {rel}"
    assert "benchweave.env" not in manifest["files"]
    assert not (archive / "benchweave.env").exists(), (
        "credentials are deliberately never backed up (T10 note)"
    )

    # Step 5 — simulated damage: corrupt the live copy of a backed-up
    # artifact (the store the backup carries).
    live_db = scratch / "state.sqlite"
    clean_digest = _sha256(live_db)
    damaged = bytearray(live_db.read_bytes())
    damaged[-1] ^= 0xFF
    live_db.write_bytes(bytes(damaged))
    assert _sha256(live_db) != clean_digest, "the damage must change the artifact"

    # Step 6 — restore: the verified archive is swapped in, healing the damage.
    result = wheel.run(
        "restore", "--archive", str(archive), "--data-dir", str(scratch), "--json"
    )
    assert result.returncode == 0, result.stderr
    restored = json.loads(result.stdout)
    assert restored["archive"] == str(archive)
    assert _sha256(scratch / "state.sqlite") == manifest["files"]["state.sqlite"], (
        "restore must heal the corrupted artifact with the snapshot's bytes"
    )
    assert not (scratch / "benchweave.env").exists(), (
        "restore never writes a credential (T10 note)"
    )

    # Step 7 — verify: exit 0 on the restored directory.
    result = wheel.run("verify", "--data-dir", str(scratch), "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True

    # The digest gate from the other side: damage a file INSIDE the backup
    # and restore must refuse — the archive gate is not decorative.
    tampered_archive = tmp_path / "tampered" / archive.name
    shutil.copytree(archive, tampered_archive)
    victim = tampered_archive / "state.sqlite"
    damaged_archive = bytearray(victim.read_bytes())
    damaged_archive[0] ^= 0xFF
    victim.write_bytes(bytes(damaged_archive))
    result = wheel.run(
        "restore",
        "--archive",
        str(tampered_archive),
        "--data-dir",
        str(tmp_path / "recovery"),
        "--json",
    )
    assert result.returncode != 0, "a damaged backup must not restore"
    assert "mismatch" in result.stderr or "verification failed" in result.stderr


@pytest.mark.slow
def test_wheel_demo_default_fixtures_refuse_truthfully(
    wheel: WheelInstall, tmp_path: Path
) -> None:
    """The T11 disclosure pinned at the wheel level: with no ``--fixtures``
    (and no ``BENCHWEAVE_FIXTURES`` — the fixture scrubs it), the demo's
    repo-relative default does not exist in a wheel install, and the
    refusal names the fix instead of tracebacking."""
    result = wheel.run("demo", "--scratch", str(tmp_path / "s"), "--json")
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "fixture lattice not found" in combined
    assert "--fixtures" in combined
    assert "Traceback" not in combined
