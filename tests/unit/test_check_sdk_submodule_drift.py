"""The SDK-submodule drift gate (issue #347 WS1, R-2): the committed
``packages/sdk`` gitlink must sit at the SDK's latest ``vX.Y.Z`` release tag.
Every existing lane catches *inconsistency* (gateway lock vs vendored tree vs
manifest); none catches *staleness* — a self-consistent mount that is 11
commits behind the latest release passed green, which is the #347 finding.

Parsing and the drift verdict are pure functions over fixture
``git ls-remote --tags`` output; no test in this module touches the network.
The fail-closed path (exit 2 — a fetch failure must never read as "no
drift") is proven in-process against monkeypatched readers and black-box
against a local repository pair and an unreachable remote path."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_sdk_submodule_drift.py"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_INDETERMINATE = 2


def _synth(seed: str) -> str:
    """A deterministic synthetic 40-hex SHA — invented, never a real object."""
    return (seed * 5)[:40]


def _remote(*entries: tuple[str, str]) -> str:
    """Render synthetic ``git ls-remote --tags`` output from (sha, ref) pairs."""
    return "".join(f"{sha}\t{ref}\n" for sha, ref in entries)


def _v041_annotated() -> str:
    """The real remote's latest-release shape: annotated tag, so the ``^{}``
    deref line carries the commit and the plain ref line carries the tag
    object."""
    return _remote(
        (_synth("a3"), "refs/tags/v0.4.1"),
        (_synth("a4"), "refs/tags/v0.4.1^{}"),
    )


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("sdk_drift_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- parsing: fixture ls-remote output ----------------------------------------


def test_annotated_latest_resolves_the_peeled_commit() -> None:
    """The plain ref line names the tag OBJECT; the gitlink must be compared
    against the ``^{}`` deref line's COMMIT — the tag-object SHA leaking into
    the comparison would report permanent drift on a current mount."""
    drift = _load()
    release = drift.latest_release(_v041_annotated())
    assert release is not None
    assert release.tag == "v0.4.1"
    assert release.commit == _synth("a4")


def test_lightweight_tag_has_no_deref_line_and_uses_the_ref_sha() -> None:
    """v0.3.0 on the real remote is lightweight (no ``^{}`` line) — the ref
    line already names the commit."""
    drift = _load()
    release = drift.latest_release(_remote((_synth("b1"), "refs/tags/v0.3.0")))
    assert release is not None
    assert release.tag == "v0.3.0"
    assert release.commit == _synth("b1")


def test_latest_is_numeric_semver_order_not_lexicographic() -> None:
    drift = _load()
    release = drift.latest_release(
        _remote(
            (_synth("c1"), "refs/tags/v0.9.0"),
            (_synth("c2"), "refs/tags/v0.10.0"),
        )
    )
    assert release is not None
    assert release.tag == "v0.10.0"


def test_non_v_and_prerelease_tags_are_not_release_candidates() -> None:
    """``refs/tags/latest`` and suffixed ``v0.5.0-rc1`` name no release; the
    highest plain ``vX.Y.Z`` wins. Only suffixed tags present -> no release
    at all (None), which reads indeterminate, not drift-free."""
    drift = _load()
    noisy = _remote(
        (_synth("d1"), "refs/tags/latest"),
        (_synth("d2"), "refs/tags/release-2026"),
        (_synth("d3"), "refs/tags/v0.4.1"),
        (_synth("d4"), "refs/tags/v0.5.0-rc1"),
    )
    release = drift.latest_release(noisy)
    assert release is not None
    assert release.tag == "v0.4.1"
    only_rc = _remote((_synth("d4"), "refs/tags/v0.5.0-rc1"))
    assert drift.latest_release(only_rc) is None


def test_empty_or_tagless_output_parses_to_none() -> None:
    drift = _load()
    assert drift.latest_release("") is None
    assert drift.latest_release("\n\n") is None


# --- the verdict: evaluate(gitlink, ls_remote_output) --------------------------


def test_stale_gitlink_reads_drift_with_both_shas_and_the_tag() -> None:
    drift = _load()
    gitlink = _synth("99")
    code, message = drift.evaluate(gitlink, _v041_annotated())
    assert code == EXIT_DRIFT
    assert gitlink in message
    assert _synth("a4") in message
    assert "v0.4.1" in message


def test_current_gitlink_reads_ok() -> None:
    drift = _load()
    code, message = drift.evaluate(_synth("a4"), _v041_annotated())
    assert code == EXIT_OK
    assert "v0.4.1" in message


def test_unparsable_remote_output_reads_indeterminate_not_ok() -> None:
    """A remote we cannot read a release from is a failed check, never a
    drift-free pass."""
    drift = _load()
    code, _ = drift.evaluate(_synth("a4"), "no tabs no tags\n")
    assert code == EXIT_INDETERMINATE


# --- main(): the wiring, in-process with injected readers ----------------------


def test_main_returns_drift_code_on_a_stale_mount(monkeypatch: Any) -> None:
    drift = _load()
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: _synth("99"))
    monkeypatch.setattr(drift, "remote_tag_list", lambda remote: _v041_annotated())
    assert drift.main([]) == EXIT_DRIFT


def test_main_returns_ok_on_a_current_mount(monkeypatch: Any) -> None:
    drift = _load()
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: _synth("a4"))
    monkeypatch.setattr(drift, "remote_tag_list", lambda remote: _v041_annotated())
    assert drift.main([]) == EXIT_OK


def test_main_fails_closed_when_the_fetch_fails(monkeypatch: Any) -> None:
    drift = _load()
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: _synth("a4"))

    def _boom(remote: str) -> str:
        raise drift.IndeterminateError("synthetic network blip")

    monkeypatch.setattr(drift, "remote_tag_list", _boom)
    assert drift.main([]) == EXIT_INDETERMINATE


def test_main_fails_closed_when_no_release_tag_parses(monkeypatch: Any) -> None:
    drift = _load()
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: _synth("a4"))
    monkeypatch.setattr(drift, "remote_tag_list", lambda remote: "")
    assert drift.main([]) == EXIT_INDETERMINATE


# --- black-box: the real CLI against local repositories, zero network ----------

_IDENTITY = (
    "-c",
    "user.name=synthetic-fixture",
    "-c",
    "user.email=fixture@example.invalid",
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc


def _pin(gateway: Path, commit: str) -> None:
    """Write the packages/sdk gitlink into HEAD's tree without any submodule
    clone — a gitlink is just a mode-160000 index entry."""
    _git(gateway, "update-index", "--add", "--cacheinfo", f"160000,{commit},packages/sdk")
    _git(gateway, *_IDENTITY, "commit", "-q", "-m", "pin sdk")


def _repo_pair(base: Path) -> tuple[Path, Path, str, str]:
    """A local SDK remote carrying an annotated release tag (plus an older
    lightweight one), and a gateway repo whose HEAD carries a packages/sdk
    gitlink pinned at the tagged commit. Returns (remote, gateway,
    tagged_commit, other_commit)."""
    remote = base / "sdk-remote"
    remote.mkdir(parents=True)
    _git(remote, "init", "-q", "-b", "main")
    (remote / "README.md").write_text("synthetic sdk remote\n", encoding="utf-8")
    _git(remote, "add", "README.md")
    _git(remote, *_IDENTITY, "commit", "-q", "-m", "seed")
    tagged = _git(remote, "rev-parse", "HEAD").stdout.strip()
    _git(remote, "tag", "-a", "v0.4.1", "-m", "synthetic release")
    _git(remote, "tag", "v0.3.0", tagged)  # an older lightweight tag

    gateway = base / "gateway"
    gateway.mkdir(parents=True)
    _git(gateway, "init", "-q", "-b", "main")
    (gateway / "README.md").write_text("synthetic gateway\n", encoding="utf-8")
    _git(gateway, "add", "README.md")
    _git(gateway, *_IDENTITY, "commit", "-q", "-m", "seed")
    other = _git(gateway, "rev-parse", "HEAD").stdout.strip()
    _pin(gateway, tagged)
    return remote, gateway, tagged, other


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_black_box_current_gitlink_exits_zero(tmp_path: Path) -> None:
    remote, gateway, _, _ = _repo_pair(tmp_path)
    proc = _run_script("--repo", str(gateway), "--remote", str(remote))
    assert proc.returncode == EXIT_OK, proc.stdout + proc.stderr
    assert "v0.4.1" in proc.stdout


def test_black_box_stale_gitlink_exits_one_with_both_shas(tmp_path: Path) -> None:
    remote, gateway, tagged, other = _repo_pair(tmp_path)
    _pin(gateway, other)  # deliberately stale: pinned at a non-release commit
    proc = _run_script("--repo", str(gateway), "--remote", str(remote))
    assert proc.returncode == EXIT_DRIFT, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert other in combined
    assert tagged in combined
    assert "v0.4.1" in combined


def test_black_box_unreachable_remote_fails_closed_with_distinct_code(
    tmp_path: Path,
) -> None:
    """The network-failure contract: exit 2, not 0 and not 1 — a blip must
    never read as 'no drift' (and never masquerade as drift either)."""
    _, gateway, _, _ = _repo_pair(tmp_path)
    proc = _run_script(
        "--repo", str(gateway), "--remote", str(tmp_path / "no-such-remote")
    )
    assert proc.returncode == EXIT_INDETERMINATE, proc.stdout + proc.stderr
    assert "indeterminate" in (proc.stdout + proc.stderr).lower()


def test_black_box_tagless_remote_fails_closed(tmp_path: Path) -> None:
    """A reachable remote with no vX.Y.Z tags is equally indeterminate."""
    bare = tmp_path / "tagless-remote"
    bare.mkdir(parents=True)
    _git(bare, "init", "-q", "-b", "main")
    (bare / "README.md").write_text("no releases here\n", encoding="utf-8")
    _git(bare, "add", "README.md")
    _git(bare, *_IDENTITY, "commit", "-q", "-m", "seed")
    _git(bare, "tag", "not-a-release")
    _, gateway, _, _ = _repo_pair(tmp_path / "pair")
    proc = _run_script("--repo", str(gateway), "--remote", str(bare))
    assert proc.returncode == EXIT_INDETERMINATE, proc.stdout + proc.stderr
    # The message assertion is load-bearing: python's own launcher also
    # exits 2 on a missing script, so the code alone can pass accidentally.
    assert "indeterminate" in (proc.stdout + proc.stderr).lower()
