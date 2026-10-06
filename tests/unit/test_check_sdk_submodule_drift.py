"""The declared-pin lane for the SDK submodule mount (issue #408 S2).

The committed ``packages/sdk`` gitlink must equal the DECLARED pin in
``.gitmodules`` (``submodule.packages/sdk.pin`` — a ``vX.Y.Z`` release tag
or a 40-hex SHA). The pin and the gitlink move in the SAME commit and the
gate enforces exactly that; the freshness signal moves from hard-red to
annotation (a trailing pin is green with ``::warning::`` — the honest
trade the design record discloses, F3).

Parsing, the pin resolution and the verdict are pure functions over
fixture ``git ls-remote --tags`` output; every test but one is
network-free — the one deliberate exception is the self-referential
arm, which shells the real checker at this repository's root (its pin
is a tag, so the verdict genuinely needs the remote; that is the arm's
point). The fail-closed paths (exit 2 — pin absent, malformed, or a
tag-pin fetch failure) are proven in-process against monkeypatched
readers and black-box against a local repository pair and an
unreachable remote path."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_sdk_submodule_drift.py"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_INDETERMINATE = 2


def _synth(seed: str) -> str:
    """A deterministic synthetic 40-hex SHA — invented, never a real object
    (and genuinely 40 hex chars: under the pin contract the string must BE
    a well-formed SHA to read as a SHA pin)."""
    return (seed * 20)[:40]


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


# --- the verdict: evaluate(gitlink, pin, ls_remote_output) ---------------------


def test_pin_at_the_mount_reads_ok_with_no_annotation_on_a_current_tag() -> None:
    """The release state: tag pin == latest tag, gitlink at its commit —
    green, and NO trailing annotation (the window is closed)."""
    drift = _load()
    code, message = drift.evaluate(_synth("a4"), "v0.4.1", _v041_annotated())
    assert code == EXIT_OK
    assert "v0.4.1" in message
    assert "::warning::" not in message


def test_stale_gitlink_reads_drift_naming_both_shas_and_the_pin() -> None:
    """Red is the pin/gitlink disagreement, enforced: the mount moved
    without the pin (or the pin without the mount)."""
    drift = _load()
    gitlink = _synth("99")
    code, message = drift.evaluate(gitlink, "v0.4.1", _v041_annotated())
    assert code == EXIT_DRIFT
    assert gitlink in message
    assert _synth("a4") in message
    assert "v0.4.1" in message


def test_sha_pin_disagreeing_with_the_mount_reads_drift_locally(
    monkeypatch: Any,
) -> None:
    """m4, and the structural improvement in one arm: the red decision is
    LOCAL for SHA pins — no remote, no network (the old gate reddened every
    mid-train push by construction)."""
    drift = _load()
    code, message = drift.evaluate(_synth("99"), _synth("a4"), None)
    assert code == EXIT_DRIFT
    assert _synth("a4") in message


def test_sha_pin_at_the_mount_is_green_offline() -> None:
    """m5 offline half: a SHA pin whose mount matches is green WITHOUT any
    remote at all — network failure cannot produce this verdict any more."""
    drift = _load()
    code, message = drift.evaluate(_synth("a4"), _synth("a4"), None)
    assert code == EXIT_OK
    assert "::warning::non-tag pin" in message
    assert "::notice::pin freshness unknowable" in message


def test_sha_pin_with_an_older_latest_tag_warns_trailing() -> None:
    """m5 online half: SHA pin at the mount, but the remote's latest
    release is ahead — green with the pairing-pending warning (F3: a walk
    row reads it, not a machine gate)."""
    drift = _load()
    code, message = drift.evaluate(_synth("a4"), _synth("a4"), _v041_annotated())
    assert code == EXIT_OK
    assert "::warning::non-tag pin" in message


def test_trailing_tag_pin_warns_but_stays_green() -> None:
    """The v0.7.1-mount-before-pairing state: green + the pairing-pending
    annotation — the freshness signal moved from hard-red to annotation
    (the honest trade, disclosed in the design record's risks)."""
    drift = _load()
    remote = _remote(
        (_synth("a4"), "refs/tags/v0.4.1"),
        (_synth("a4"), "refs/tags/v0.4.1^{}"),
        (_synth("e1"), "refs/tags/v0.5.0"),
        (_synth("e1"), "refs/tags/v0.5.0^{}"),
    )
    code, message = drift.evaluate(_synth("a4"), "v0.4.1", remote)
    assert code == EXIT_OK
    assert "::warning::pin v0.4.1 trails latest v0.5.0 — pairing pending" in message


def test_unparsable_remote_output_reads_indeterminate_not_ok() -> None:
    """A remote we cannot read the pin's tag from is a failed check, never
    a drift-free pass (tag pins fail closed on resolution)."""
    drift = _load()
    code, _ = drift.evaluate(_synth("a4"), "v0.4.1", "no tabs no tags\n")
    assert code == EXIT_INDETERMINATE


def test_tag_pin_absent_from_the_remote_fails_closed() -> None:
    drift = _load()
    code, message = drift.evaluate(_synth("a4"), "v0.9.9", _v041_annotated())
    assert code == EXIT_INDETERMINATE
    assert "v0.9.9" in message


def test_malformed_pin_fails_closed_at_the_main_level(monkeypatch: Any) -> None:
    """A pin that is neither vX.Y.Z nor a 40-hex SHA is an undeclared
    mount: main fails closed (the pin IS the declaration — anything else
    means nobody declared)."""
    drift = _load()
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: _synth("a4"))
    monkeypatch.setattr(drift, "configured_pin", lambda repo: "latest")
    monkeypatch.setattr(drift, "remote_tag_list", lambda remote: _v041_annotated())
    code = drift.main([])
    assert code == EXIT_INDETERMINATE
    assert "pin_malformed" in _stderr_of(drift.main, [])

# --- main(): the wiring, in-process with injected readers ----------------------


def _wired(
    drift: Any,
    monkeypatch: Any,
    *,
    gitlink: str,
    pin: str | None,
    output: str | None,
    fetch_raises: bool = False,
) -> None:
    """Wire main()'s three readers to synthetic values."""

    def _pin_reader(repo: Any) -> str:
        assert pin is not None
        return pin

    def _boom(remote: str) -> str:
        raise drift.IndeterminateError("synthetic network blip")

    monkeypatch.setattr(drift, "configured_pin", _pin_reader)
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: gitlink)
    monkeypatch.setattr(
        drift, "remote_tag_list", _boom if fetch_raises else (lambda remote: output or "")
    )


def test_main_returns_drift_code_on_a_stale_mount(monkeypatch: Any) -> None:
    drift = _load()
    _wired(drift, monkeypatch, gitlink=_synth("99"), pin="v0.4.1", output=_v041_annotated())
    assert drift.main([]) == EXIT_DRIFT


def test_main_returns_ok_on_a_current_mount(monkeypatch: Any) -> None:
    drift = _load()
    _wired(drift, monkeypatch, gitlink=_synth("a4"), pin="v0.4.1", output=_v041_annotated())
    assert drift.main([]) == EXIT_OK


def test_main_tag_pin_fetch_failure_reads_indeterminate(monkeypatch: Any) -> None:
    """Tag pins still need the remote: a fetch failure reads indeterminate —
    identical sensitivity to the old gate, never worse."""
    drift = _load()
    _wired(
        drift, monkeypatch,
        gitlink=_synth("a4"), pin="v0.4.1", output=None, fetch_raises=True,
    )
    assert drift.main([]) == EXIT_INDETERMINATE


def _stderr_of(fn: Any, argv: list[str], monkeypatch: Any = None) -> str:
    """main() prints its verdict to stderr; capture it (capsys is not
    available inside an arm that also needs monkeypatch wiring, so the
    caller wires capsys through)."""
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        fn(argv)
    return buffer.getvalue()


def test_main_pin_absent_fails_closed(monkeypatch: Any) -> None:
    """m6: an undeclared mount fails closed — every pointer PR must carry
    the pin."""
    drift = _load()
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: _synth("a4"))
    monkeypatch.setattr(drift, "configured_pin", lambda repo: "")
    monkeypatch.setattr(drift, "remote_tag_list", lambda remote: _v041_annotated())
    assert drift.main([]) == EXIT_INDETERMINATE


def test_main_fails_closed_when_no_release_tag_parses(monkeypatch: Any) -> None:
    drift = _load()
    _wired(drift, monkeypatch, gitlink=_synth("a4"), pin="v0.4.1", output="")
    assert drift.main([]) == EXIT_INDETERMINATE


def test_main_sha_pin_fetch_failure_stays_green_with_a_notice(monkeypatch: Any) -> None:
    """The structural improvement end to end: a SHA pin at the mount stays
    green when the fetch fails — the verdict is local; the annotation
    degrades (notice), never the verdict."""
    drift = _load()
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: _synth("a4"))
    monkeypatch.setattr(drift, "configured_pin", lambda repo: _synth("a4"))

    def _boom(remote: str) -> str:
        raise drift.IndeterminateError("synthetic network blip")

    monkeypatch.setattr(drift, "remote_tag_list", _boom)
    assert drift.main([]) == EXIT_OK



# --- black-box: the real CLI against local repositories, zero network ----------


def _init_repo(path: Path) -> None:
    """Create a fixture repo whose identity and hooks are its OWN. CI
    runners carry no usable ambient git identity — PR #360 red the gates
    lane with 'fatal: empty ident name' (a machine's global identity
    masks this locally, and an explicit EMPTY global user.name also
    disables the OS fallback, which is how the identity test reproduces
    the runner on any host). Repo-local config sits above the global
    file, so every ident the fixtures mint — commits and annotated tags
    alike — comes from the repo itself, on any host."""
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "synthetic-fixture")
    _git(path, "config", "user.email", "fixture@example.invalid")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # core.hooksPath=/dev/null keeps fixture commits hermetic: a machine's
    # GLOBAL hooks path (this one carries a post-commit enrich hook) fires
    # inside synthetic repos too — observed stalling a fixture commit for
    # ~40s and, on a wedged hook, hanging the suite (verified: hookless
    # commits run in ~25ms with the global hook present). /dev/null is not
    # a directory, so git finds no executable hook there and runs none.
    proc = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(repo),
            *args,
        ],
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
    _git(gateway, "commit", "-q", "-m", "pin sdk")


def _repo_pair(base: Path) -> tuple[Path, Path, str, str]:
    """A local SDK remote carrying an annotated release tag (plus an older
    lightweight one), and a gateway repo whose HEAD carries a packages/sdk
    gitlink pinned at the tagged commit. The gateway carries a .gitmodules
    whose pin DECLARES the mount (owner fork F2). Returns (remote,
    gateway, tagged_commit, other_commit)."""
    remote = base / "sdk-remote"
    _init_repo(remote)
    (remote / "README.md").write_text("synthetic sdk remote\n", encoding="utf-8")
    _git(remote, "add", "README.md")
    _git(remote, "commit", "-q", "-m", "seed")
    tagged = _git(remote, "rev-parse", "HEAD").stdout.strip()
    _git(remote, "tag", "-a", "v0.4.1", "-m", "synthetic release")
    _git(remote, "tag", "v0.3.0", tagged)  # an older lightweight tag

    gateway = base / "gateway"
    _init_repo(gateway)
    (gateway / "README.md").write_text("synthetic gateway\n", encoding="utf-8")
    _git(gateway, "add", "README.md")
    _git(gateway, "commit", "-q", "-m", "seed")
    other = _git(gateway, "rev-parse", "HEAD").stdout.strip()
    _pin(gateway, tagged)
    _declare(gateway, "v0.4.1", url=str(remote))
    return remote, gateway, tagged, other


_SYNTHETIC_URL = "https://sdk.example.invalid/synthetic.git"


def _declare(gateway: Path, pin: str, url: str = _SYNTHETIC_URL) -> None:
    """Write the DECLARED pin into .gitmodules (owner fork F2): a tag or a
    40-hex SHA — writing a SHA is how a train declares itself."""
    text = gateway / ".gitmodules"
    text.write_text(
        '[submodule "packages/sdk"]\n'
        f"\tpath = packages/sdk\n"
        f"\turl = {url}\n"
        f"\tpin = {pin}\n",
        encoding="utf-8",
    )
    _git(gateway, "add", ".gitmodules")
    _git(gateway, "commit", "-q", "-m", f"declare pin {pin}")


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_black_box_current_gitlink_exits_zero(tmp_path: Path) -> None:
    """Green WITHOUT --remote: the .gitmodules url + pin carry the whole
    declaration (the F2 single-home)."""
    _, gateway, _, _ = _repo_pair(tmp_path)
    proc = _run_script("--repo", str(gateway))
    assert proc.returncode == EXIT_OK, proc.stdout + proc.stderr
    assert "v0.4.1" in proc.stdout
    assert "::warning::" not in proc.stdout  # pin == latest: window closed


def test_black_box_pin_without_the_mount_reads_drift(tmp_path: Path) -> None:
    """m4 black-box: the mount moved without the pin (or the pin without
    the mount) — red, both SHAs named, the same-commit rule enforced."""
    remote, gateway, tagged, other = _repo_pair(tmp_path)
    _pin(gateway, other)  # deliberately stale: pinned at a non-release commit
    proc = _run_script("--repo", str(gateway), "--remote", str(remote))
    assert proc.returncode == EXIT_DRIFT, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert other in combined
    assert tagged in combined
    assert "v0.4.1" in combined


def test_black_box_trailing_pin_warns(tmp_path: Path) -> None:
    """The mount/pin sit at v0.3.0 while the remote's latest is v0.4.1 —
    green + the pairing-pending annotation (F3: a walk row reads it)."""
    remote, gateway, tagged, _ = _repo_pair(tmp_path)
    # a genuinely OLDER release: the fixture's two tags share one commit,
    # so the trailing state needs its own commit + tag below v0.4.1
    (remote / "older.txt").write_text("older release\n", encoding="utf-8")
    _git(remote, "add", "older.txt")
    _git(remote, "commit", "-q", "-m", "older release")
    older = _git(remote, "rev-parse", "HEAD").stdout.strip()
    _git(remote, "tag", "v0.3.1", older)
    _pin(gateway, older)
    _declare(gateway, "v0.3.1", url=str(remote))
    proc = _run_script("--repo", str(gateway), "--remote", str(remote))
    assert proc.returncode == EXIT_OK, proc.stdout + proc.stderr
    assert "::warning::pin v0.3.1 trails latest v0.4.1 — pairing pending" in (
        proc.stdout
    )


def test_black_box_sha_pin_declared_train_green(tmp_path: Path) -> None:
    """The era-bind mid-train state the OLD gate reddened by construction:
    a SHA pin whose mount matches — green, with the non-tag warning; and
    OFFLINE (unreachable remote: a SHA pin needs no network for its
    verdict, with the freshness-unknowable notice)."""
    _, gateway, tagged, _ = _repo_pair(tmp_path)
    # the mount is already at `tagged`; declaring the SHA pin over an
    # UNREACHABLE url is the offline proof (no --remote override: the
    # .gitmodules url itself is the unreachable one)
    _declare(gateway, tagged, url=str(tmp_path / "no-such-remote"))
    proc = _run_script("--repo", str(gateway))
    assert proc.returncode == EXIT_OK, proc.stdout + proc.stderr
    assert f"::warning::non-tag pin {tagged}" in proc.stdout
    assert "::notice::pin freshness unknowable" in proc.stdout


def test_black_box_unreachable_remote_fails_closed_with_distinct_code(
    tmp_path: Path,
) -> None:
    """Tag pin + unreachable remote: exit 2, not 0 and not 1 — a blip must
    never read as 'no drift' (identical sensitivity, never worse)."""
    _, gateway, _, _ = _repo_pair(tmp_path)
    proc = _run_script(
        "--repo", str(gateway), "--remote", str(tmp_path / "no-such-remote")
    )
    assert proc.returncode == EXIT_INDETERMINATE, proc.stdout + proc.stderr
    assert "indeterminate" in (proc.stdout + proc.stderr).lower()


def test_black_box_tagless_remote_fails_closed(tmp_path: Path) -> None:
    """A reachable remote with no vX.Y.Z tags is equally indeterminate."""
    bare = tmp_path / "tagless-remote"
    _init_repo(bare)
    (bare / "README.md").write_text("no releases here\n", encoding="utf-8")
    _git(bare, "add", "README.md")
    _git(bare, "commit", "-q", "-m", "seed")
    _git(bare, "tag", "not-a-release")
    _, gateway, _, _ = _repo_pair(tmp_path / "pair")
    proc = _run_script("--repo", str(gateway), "--remote", str(bare))
    assert proc.returncode == EXIT_INDETERMINATE, proc.stdout + proc.stderr
    # The message assertion is load-bearing: python's own launcher also
    # exits 2 on a missing script, so the code alone can pass accidentally.
    assert "indeterminate" in (proc.stdout + proc.stderr).lower()


def test_black_box_pin_absent_fails_closed(tmp_path: Path) -> None:
    """m6 black-box: .gitmodules without the pin key — an undeclared mount
    fails closed; every pointer PR must carry the pin."""
    _, gateway, _, _ = _repo_pair(tmp_path)
    (gateway / ".gitmodules").write_text(
        '[submodule "packages/sdk"]\n'
        "\tpath = packages/sdk\n"
        "\turl = https://sdk.example.invalid/synthetic.git\n",
        encoding="utf-8",
    )
    _git(gateway, "add", ".gitmodules")
    _git(gateway, "commit", "-q", "-m", "strip the pin")
    proc = _run_script("--repo", str(gateway), "--remote", str(tmp_path / "unused"))
    assert proc.returncode == EXIT_INDETERMINATE, proc.stdout + proc.stderr
    assert "pin_absent" in (proc.stdout + proc.stderr)


def test_fixture_repositories_carry_their_own_git_identity(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """PR #360 red the gates lane with 'fatal: empty ident name': CI
    runners carry no usable ambient git identity, and the fixture's
    annotated release tag wore none of its own (the commits did, via
    command-line -c). Fixture repos must mint every ident — commits and
    annotated tags — from their OWN local config. The hostile global here
    (an explicit empty user.name, which also disables the OS auto-detect
    fallback) reproduces the runner: it sits BELOW repo-local config, so a
    self-identifying fixture builds clean while one leaning on the ambient
    environment reds."""
    hostile = tmp_path / "empty-identity.gitconfig"
    hostile.write_text("[user]\n\tname =\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    remote, gateway, _, _ = _repo_pair(tmp_path / "pair")
    # the annotated tag is the ident-minting op that wore no identity of
    # its own; both release tags must exist for the pair to be usable
    tags = _git(remote, "tag", "-l").stdout.split()
    assert "v0.4.1" in tags, tags
    assert "v0.3.0" in tags, tags
    assert _git(gateway, "log", "--oneline", "-1").stdout.strip(), (
        "the gateway seed commit did not land"
    )


# --- fold wave 2, L-3: the pin is read from HEAD BYTES, not the working tree ---


def test_working_tree_pin_edit_cannot_green_a_committed_red_repo(
    tmp_path: Path,
) -> None:
    """L-3 (CON-12 consistency): the gate judges COMMITTED state — the
    gitlink already does; the pin must too. A repo whose HEAD carries
    pin=vX + gitlink=Y (committed red) stays red even when the working
    tree's .gitmodules has been edited to pin=Y: an uncommitted edit must
    not green what was committed red."""
    remote, gateway, tagged, other = _repo_pair(tmp_path)
    # commit a RED state: the mount moves to `other` while HEAD's pin keeps
    # declaring v0.4.1's commit (the _repo_pair declaration) — committed red
    _pin(gateway, other)
    proc = _run_script("--repo", str(gateway), "--remote", str(remote))
    assert proc.returncode == EXIT_DRIFT, proc.stdout + proc.stderr
    # the working-tree edit: pin re-written (NOT committed) to match the mount
    (gateway / ".gitmodules").write_text(
        '[submodule "packages/sdk"]\n'
        "\tpath = packages/sdk\n"
        f"\turl = {remote}\n"
        f"\tpin = {other}\n",
        encoding="utf-8",
    )
    proc = _run_script("--repo", str(gateway), "--remote", str(remote))
    assert proc.returncode == EXIT_DRIFT, (
        "a working-tree pin edit greened a committed-red repo:\n"
        + proc.stdout
        + proc.stderr
    )
    assert "indeterminate" not in (proc.stdout + proc.stderr).lower()


# --- fold wave 2, M-1(b): the self-referential fast-lane arm -------------------


def test_self_referential_root_is_green() -> None:
    """M-1(b): the real repo, the real gate — this arm shells the checker
    at THIS repository's root and asserts exit 0, so any future split-
    motion train (pin and gitlink advancing in separate commits, an
    intermediate landing on main) reddens every fast-lane run, not just
    the push lane. THE module's one deliberate network touch: the root's
    pin is a tag, so the verdict needs the remote; a network-less
    environment fails here loudly (indeterminate), which is honest for a
    gate whose freshness half is remote-adjacent. RED evidence (the lane's
    own captured history): at 93877e6 (this branch's pre-pin-advance
    intermediate) the same invocation exits 1 — pin v0.7.1, gitlink at the
    v0.8.0 mount — the split-motion state this arm exists to catch."""
    proc = _run_script("--repo", str(ROOT))
    assert proc.returncode == EXIT_OK, (
        "the checked-out root is not at its declared pin:\n"
        + proc.stdout
        + proc.stderr
    )


# --- review fold row 1: undecodable remote output is indeterminate ----------


def _raising_run(*args: object, **kwargs: object) -> NoReturn:
    """Reproduce the verified stdlib raise site: subprocess.run(text=True)
    strict-decodes captured bytes INSIDE the call, so an undecodable refname
    byte raises here and never reaches the parser."""
    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


def test_undecodable_remote_output_is_indeterminate_not_drift(
    monkeypatch: Any,
) -> None:
    """Adversary row 1: the decode raise must surface as INDETERMINATE (2),
    never as an uncaught traceback exiting 1 — which reads as drift in CI
    and falsifies the docstring's 'never masquerade as drift either'."""
    drift = _load()
    monkeypatch.setattr(drift, "committed_gitlink", lambda repo: _synth("a4"))
    monkeypatch.setattr(drift.subprocess, "run", _raising_run)
    assert drift.main([]) == EXIT_INDETERMINATE


def test_remote_reader_wraps_undecodable_output_as_indeterminate(
    monkeypatch: Any,
) -> None:
    drift = _load()
    monkeypatch.setattr(drift.subprocess, "run", _raising_run)
    with pytest.raises(drift.IndeterminateError):
        drift.remote_tag_list("synthetic-remote")


def test_gitlink_reader_wraps_undecodable_output_as_indeterminate(
    monkeypatch: Any,
) -> None:
    """Symmetric defense on the local reader: git C-quotes exotic paths so
    ls-tree is not EXPECTED to emit raw non-UTF-8, but any unreadable
    result is indeterminate by the reader's contract, not a crash."""
    drift = _load()
    monkeypatch.setattr(drift.subprocess, "run", _raising_run)
    with pytest.raises(drift.IndeterminateError):
        drift.committed_gitlink(Path("."))


# --- review fold row 2: the remote derives from .gitmodules ------------------


def test_gitmodules_url_is_the_configured_remote(tmp_path: Path) -> None:
    """Governor F1: the SDK URL is named once, in .gitmodules — the gate
    reads it from there instead of re-hardcoding it."""
    remote, gateway, _, _ = _repo_pair(tmp_path)
    (gateway / ".gitmodules").write_text(
        f'[submodule "packages/sdk"]\n\turl = {remote}\n', encoding="utf-8"
    )
    drift = _load()
    assert drift.configured_remote(gateway) == str(remote)


def test_configured_remote_falls_back_when_gitmodules_is_absent(
    tmp_path: Path,
) -> None:
    _, gateway, _, _ = _repo_pair(tmp_path)
    (gateway / ".gitmodules").unlink()
    drift = _load()
    assert drift.configured_remote(gateway) == drift.FALLBACK_REMOTE


def test_black_box_gitmodules_override_selects_the_remote(tmp_path: Path) -> None:
    """End to end without --remote: .gitmodules points the gate at a local
    tagless remote — exit 2 is reachable ONLY through the override (the
    built-in fallback names a network remote this suite never touches; the
    override path is network-free and deterministic once the fold lands)."""
    bare = tmp_path / "tagless-remote"
    _init_repo(bare)
    (bare / "README.md").write_text("no releases here\n", encoding="utf-8")
    _git(bare, "add", "README.md")
    _git(bare, "commit", "-q", "-m", "seed")
    _git(bare, "tag", "not-a-release")
    _, gateway, _, _ = _repo_pair(tmp_path / "pair")
    (gateway / ".gitmodules").write_text(
        f'[submodule "packages/sdk"]\n\turl = {bare}\n', encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=gateway,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == EXIT_INDETERMINATE, proc.stdout + proc.stderr
    assert "indeterminate" in (proc.stdout + proc.stderr).lower()
