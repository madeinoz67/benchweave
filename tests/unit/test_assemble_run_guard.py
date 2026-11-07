"""The done_marker guard on assemble_docs_site.run() (issue #501, design §4).

Ports the SDK twin's template (``packages/sdk/tests/test_assemble_run_guard.py``,
issues #475/#476) plus the two gateway deltas: the ``"bucket"`` marker kind —
the ``uv run`` bucket child's OUTER completion line is its own final
``[assemble] assembled bucket <tag> at <path>`` statement, never the inner
great-docs banner it inherits on its pipe (the gateway has no ``--from-repo``
call site, so the SDK's ``"isolated"`` kind does not transfer literally) — and
``env`` forwarding through the guarded path.

The CI defect does not reproduce on this machine (the twin's design §2.3 — a
local great-docs 0.17.0 run exits cleanly), so these arms reproduce the
measured CI shape synthetically: a child that prints the 0.17.0 completion
banner, then never exits, holding sleeping grandchildren in its process group
(the two python3.13 orphans of cancelled run 38758274375). The F1-
generalization control (inner banner, no bucket line, named timeout) pins the
bucket kind against the twin's fold-F1 defect class one level up: a marker on
the inner banner truncates a healthy assembly — staging cleanup, the
replace_dir lift, standards rename, corpus copy and verify_tree all run after
it.

The fixtures are byte captures of real great-docs 0.17.0 runs, copied
sha256-identical from the SDK twin's ``tests/fixtures/`` (its F4 arm); the
synthetic counts and paths inside them are the twin's, kept untouched so the
two repos pin the same captured bytes.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "assemble_docs_site.py"

# The repo's POSIX-only convention (the twin's template): arms that exercise
# process groups / signals skip on Windows, where CPython silently ignores
# start_new_session and os.getpgrp does not exist.
POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="process-group arm: POSIX only"
)

# The literal great-docs 0.17.0 banner shape (the twin's local 2m20s run;
# counts synthetic, marker strings the tool's own fixed text). The FAIL
# literal is the tool's real non-tty shape (great_docs/_build_log.py:802:
# "[FAIL] Build failed at Step {n} - {title}") — synthetic step/title.
BANNER_OK_HEAD = "[OK] Build complete — 21/19 steps (9 skipped, 1 warning)"
BANNER_TOTAL_TIME = "Total time: 2m 20.1s"
BANNER_SITE_READY = "Site ready (1 warning) → /tmp/sgw/great-docs/_site"
BANNER_FAIL = "[FAIL] Build failed at Step 7 - reference rendering"

# The bucket child's own final statement (scripts/assemble_docs_site.py,
# main()'s --bucket return path): printed after verify_tree, immediately
# before the child returns. Identical wording in the frozen v0.4.0 tag's
# script (its :1435 — the only tag CI builds today), so the marker holds
# against the bytes CI actually runs. Tag and path here are synthetic.
BUCKET_DONE_LINE = "[assemble] assembled bucket v0.4.0 at /tmp/bucket-out"

GRANDCHILD = "import time; time.sleep(3600)"
GRANDCHILD_TERM_IGNORER = (
    "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(3600)"
)

# The synthetic CI shape: banner first, then never exit, holding two sleeping
# grandchildren (the run-38758274375 orphan tree). argv[1] receives a path the
# child writes its process-group id to, so the arms can probe the group after
# run() returns.
_CHILD_OK_HANG = f"""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
for _ in range(2):
    subprocess.Popen([sys.executable, "-c", {GRANDCHILD!r}])
for line in ({BANNER_OK_HEAD!r}, {BANNER_TOTAL_TIME!r}, {BANNER_SITE_READY!r}):
    sys.stdout.write(line + "\\n")
sys.stdout.flush()
open(sys.argv[1], "w").write(str(os.getpgrp()))
time.sleep(3600)
"""

_CHILD_FAIL_HANG = f"""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
subprocess.Popen([sys.executable, "-c", {GRANDCHILD!r}])
sys.stdout.write({BANNER_FAIL!r} + "\\n")
sys.stdout.flush()
open(sys.argv[1], "w").write(str(os.getpgrp()))
time.sleep(3600)
"""

# F3's shape: a SUCCESS banner first, the failure banner later — both before
# the OK grace expires. Whichever ending fires says whether FAIL outranks.
_CHILD_OK_THEN_FAIL = f"""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
subprocess.Popen([sys.executable, "-c", {GRANDCHILD!r}])
for line in ({BANNER_OK_HEAD!r}, {BANNER_TOTAL_TIME!r}, {BANNER_SITE_READY!r}):
    sys.stdout.write(line + "\\n")
sys.stdout.flush()
open(sys.argv[1], "w").write(str(os.getpgrp()))
time.sleep(2.5)
sys.stdout.write({BANNER_FAIL!r} + "\\n")
sys.stdout.flush()
time.sleep(3600)
"""

_CHILD_CLEAN_EXIT = f"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
for line in ({BANNER_OK_HEAD!r}, {BANNER_TOTAL_TIME!r}, {BANNER_SITE_READY!r}):
    sys.stdout.write(line + "\\n")
sys.stdout.flush()
"""

_CHILD_EXIT_SEVEN = """
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stdout.write("partial output before failure\\n")
sys.exit(7)
"""

_CHILD_NO_BANNER_HANG = f"""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
for _ in range(2):
    subprocess.Popen([sys.executable, "-c", {GRANDCHILD!r}])
sys.stdout.write("step 12/19 rendering reference pages\\n")
sys.stdout.flush()
open(sys.argv[1], "w").write(str(os.getpgrp()))
time.sleep(3600)
"""

_CHILD_SITE_READY_ONLY = f"""
import os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.stdout.write({BANNER_SITE_READY!r} + "\\n")
sys.stdout.flush()
open(sys.argv[1], "w").write(str(os.getpgrp()))
time.sleep(3600)
"""

# A faithful bucket child (the tag's own script under `uv run`): the INNER
# great-docs build's banner first — uncaptured, inherited onto the child's own
# pipe — then the assembly tail the child still has ahead of it when the inner
# banner lands (staging cleanup, lift, rename, corpus copy, previews, llms.txt,
# verify_tree — four visible tail lines here), then the child's OWN final
# statement, then the CI wedge (never exits, two grandchildren held).
_CHILD_BUCKET_FAITHFUL = f"""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
for _ in range(2):
    subprocess.Popen([sys.executable, "-c", {GRANDCHILD!r}])
for line in ({BANNER_OK_HEAD!r}, {BANNER_TOTAL_TIME!r}, {BANNER_SITE_READY!r}):
    sys.stdout.write(line + "\\n")
sys.stdout.flush()
open(sys.argv[1], "w").write(str(os.getpgrp()))
for step in ("staging cleanup", "bucket lift", "corpus copy", "verify_tree"):
    sys.stdout.write("tail: " + step + "\\n")
sys.stdout.flush()
time.sleep(1.6)
sys.stdout.write({BUCKET_DONE_LINE!r} + "\\n")
sys.stdout.flush()
time.sleep(3600)
"""

# The F1-generalization control: the inner banner arrives, the child hangs
# mid-tail and NEVER prints its own completion line. The bucket kind must not
# treat the inner banner as work-done — only the E4 bound ends this run.
_CHILD_BUCKET_INNER_BANNER_ONLY = f"""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
for _ in range(2):
    subprocess.Popen([sys.executable, "-c", {GRANDCHILD!r}])
for line in ({BANNER_OK_HEAD!r}, {BANNER_TOTAL_TIME!r}, {BANNER_SITE_READY!r}):
    sys.stdout.write(line + "\\n")
sys.stdout.flush()
open(sys.argv[1], "w").write(str(os.getpgrp()))
sys.stdout.write("tail: staging cleanup\\n")
sys.stdout.flush()
time.sleep(3600)
"""

# The load-shape extreme of the CI failure (run 39209775675): a grandchild
# that IGNORES SIGTERM. Polite members die at SIGTERM; this one must be
# SIGKILLed through the group, which the reclaim's escalation has to reach
# on its own (the leader is not the group).
_CHILD_SIGTERM_IGNORE = f"""
import os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
subprocess.Popen([sys.executable, "-c", {GRANDCHILD_TERM_IGNORER!r}])
sys.stdout.write({BANNER_FAIL!r} + "\\n")
sys.stdout.flush()
open(sys.argv[1], "w").write(str(os.getpgrp()))
time.sleep(3600)
"""

# The env-forwarding delta: the guarded path must thread the caller's env into
# the Popen (the SDK's runner has no env parameter). The child proves the
# variable reached it by echoing it, then completes via the bucket marker.
_CHILD_ENV_PROBE = f"""
import os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.stdout.write("env-probe: " + os.environ["BW_GUARD_ENV_PROBE"] + "\\n")
sys.stdout.flush()
sys.stdout.write({BUCKET_DONE_LINE!r} + "\\n")
sys.stdout.flush()
time.sleep(3600)
"""


def _load() -> Any:
    """Load the script once per session (the twin template's loader)."""
    existing = sys.modules.get("assemble_docs_site_under_test")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location("assemble_docs_site_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _group_is_empty(pgid_file: Path, *, deadline_s: float | None = None) -> bool:
    """The arms' claim is a PROPERTY: the child's process group is empty
    AFTERWARDS — no members at all, not even reap-pending zombies. So this
    polls to a bounded deadline instead of sampling one instant: killpg(0)
    success and EPERM both mean members-may-remain (a zombie answers success
    on Linux and EPERM on macOS — a single sample of the Linux shape is what
    reddened the twin's CI run 39209775675), and only ProcessLookupError
    settles the question. The default deadline is the runner's
    RECLAIM_GROUP_DEADLINE_S — one disclosure ceiling, not a second number.
    True = empty within it."""
    if deadline_s is None:
        deadline_s = _load().RECLAIM_GROUP_DEADLINE_S
    pgid = int(pgid_file.read_text(encoding="utf-8"))
    end = time.monotonic() + deadline_s
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True  # empty
        except PermissionError:
            pass  # macOS zombie window — keep polling
        if time.monotonic() >= end:
            return False
        time.sleep(0.05)


@POSIX_ONLY
def test_ok_banner_hang_ends_at_the_banner_and_reclaims_the_group(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance §8 item 1: the banner-then-hang child (holding two
    grandchildren) ends via E2 — success within grace+5s, the disclosure log
    present, the banner forwarded live, and the child's whole process group
    empty afterwards (no orphans). Three trials, all passing."""
    mod = _load()
    for trial in range(3):
        pgid_file = tmp_path / f"ok-hang-pgid-{trial}"
        started = time.monotonic()
        out = mod.run(
            [sys.executable, "-c", _CHILD_OK_HANG, str(pgid_file)],
            cwd=tmp_path,
            done_marker=True,
            grace=3.0,
            timeout=60.0,
        )
        elapsed = time.monotonic() - started
        assert out == "", f"trial {trial}: the guarded path must return ''"
        assert pgid_file.exists(), f"trial {trial}: the child never wrote its pgid"
        assert _group_is_empty(pgid_file), f"trial {trial}: orphans survived reclamation"
        assert elapsed < 8.0, f"trial {trial}: reclaim took {elapsed:.1f}s (grace is 3s)"
        captured = capsys.readouterr()
        assert BANNER_OK_HEAD in captured.out, f"trial {trial}: banner not forwarded live"
        assert "reclaimed after" in captured.out, f"trial {trial}: no E2 disclosure log"


def test_clean_exit_child_pays_no_grace_and_honors_the_real_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E1 — the only case seen locally: a child that exits on its own returns
    immediately, no grace wait, no reclamation log; a non-zero exit fails
    loudly with the REAL code (output was already forwarded live, so there is
    nothing left to reprint)."""
    mod = _load()
    started = time.monotonic()
    out = mod.run(
        [sys.executable, "-c", _CHILD_CLEAN_EXIT],
        cwd=tmp_path,
        done_marker=True,
        grace=30.0,  # a grace wait here would cost 30s and prove the ending wrong
        timeout=60.0,
    )
    elapsed = time.monotonic() - started
    assert out == ""
    assert "reclaimed" not in capsys.readouterr().out
    assert elapsed < 5.0, f"E1 took {elapsed:.1f}s — a clean exit must not pay grace"
    with pytest.raises(SystemExit, match=r"command failed \(7\)"):
        mod.run(
            [sys.executable, "-c", _CHILD_EXIT_SEVEN],
            cwd=tmp_path,
            done_marker=True,
            grace=30.0,
            timeout=60.0,
        )


@POSIX_ONLY
def test_an_ok_banner_then_a_fail_banner_still_fails(tmp_path: Path) -> None:
    """F3 (twin's fold wave): a sighted FAIL banner prohibits E2 outright —
    the earlier OK's grace deadline must not win the race. Both markers land
    inside one grace window here (OK at ~0s, FAIL at ~2.5s, grace 5s): a
    wrong implementation returns SUCCESS at the OK deadline with the FAIL
    banner never gated; the mechanism waits out the fail grace and ends E3."""
    mod = _load()
    pgid_file = tmp_path / "ok-then-fail-pgid"
    with pytest.raises(SystemExit, match=r"command failed \(banner\)"):
        mod.run(
            [sys.executable, "-c", _CHILD_OK_THEN_FAIL, str(pgid_file)],
            cwd=tmp_path,
            done_marker=True,
            grace=5.0,  # both markers sighted inside this window (FAIL at 2.5s)
            timeout=60.0,
        )
    assert _group_is_empty(pgid_file)


@POSIX_ONLY
def test_fail_banner_hang_fails_loudly_naming_the_command(tmp_path: Path) -> None:
    """The FAIL banner outranks everything — a sighted FAIL prohibits E2
    (F3), so the run reclaims the group and raises SystemExit naming the
    command; no exit code exists to report, and the message says 'banner'
    rather than fabricating one."""
    mod = _load()
    pgid_file = tmp_path / "fail-hang-pgid"
    with pytest.raises(SystemExit, match=r"command failed \(banner\)") as excinfo:
        mod.run(
            [sys.executable, "-c", _CHILD_FAIL_HANG, str(pgid_file)],
            cwd=tmp_path,
            done_marker=True,
            grace=3.0,
            timeout=60.0,
        )
    assert sys.executable in str(excinfo.value), "the failure must name the command"
    assert _group_is_empty(pgid_file), "E3 must reclaim the group too"


@POSIX_ONLY
def test_no_marker_timeout_now_reclaims_the_group_too(tmp_path: Path) -> None:
    """E4 backstop: a mid-build wedge with NO banner rides the outer timeout —
    which today (issue #501's shape: no bound at all) holds the step open
    indefinitely. The guarded path reclaims the whole group before the
    named-timeout SystemExit."""
    mod = _load()
    pgid_file = tmp_path / "e4-pgid"
    with pytest.raises(SystemExit, match=r"command timed out after 2s"):
        mod.run(
            [sys.executable, "-c", _CHILD_NO_BANNER_HANG, str(pgid_file)],
            cwd=tmp_path,
            done_marker=True,
            grace=3.0,
            timeout=2.0,
        )
    assert _group_is_empty(pgid_file), "E4 must reclaim the group, not just the child"


@POSIX_ONLY
def test_a_lone_site_ready_line_does_not_complete_the_marker(tmp_path: Path) -> None:
    """R3: the OK marker is a CONJUNCTION — "[OK] Build complete" and a
    following "Site ready" line. A child emitting only the second half (any
    build output quoting the banner's last line) must NOT end the step early:
    with grace below the timeout there is no E2, only the E4 bound."""
    mod = _load()
    pgid_file = tmp_path / "site-only-pgid"
    with pytest.raises(SystemExit, match=r"command timed out after 3s"):
        mod.run(
            [sys.executable, "-c", _CHILD_SITE_READY_ONLY, str(pgid_file)],
            cwd=tmp_path,
            done_marker=True,
            grace=1.0,  # a false-positive marker would end here first, via E2
            timeout=3.0,
        )
    assert _group_is_empty(pgid_file)


@POSIX_ONLY
def test_bucket_marker_waits_for_the_outer_completion_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gateway's F1, one level up: the bucket child's marker is its OWN
    final statement — ``[assemble] assembled bucket <tag> at <path>``,
    printed after verify_tree — never the inner great-docs banner, which
    lands on the child's pipe while staging cleanup, the replace_dir lift,
    the standards rename, the corpus copy and verify_tree still run. A
    faithful child (inner banner, four tail lines, its completion line, then
    the wedge) must end via E2 with EVERY tail line forwarded: a reclaim at
    the inner banner is silent truncation reported as success — the twin's
    lane A measured 1337/3000 files on exactly that defect."""
    mod = _load()
    pgid_file = tmp_path / "bucket-pgid"
    out = mod.run(
        [sys.executable, "-c", _CHILD_BUCKET_FAITHFUL, str(pgid_file)],
        cwd=tmp_path,
        done_marker="bucket",
        grace=1.0,  # below the ~1.6s tail: an inner-banner match fires mid-tail
        timeout=60.0,
    )
    assert out == ""
    captured = capsys.readouterr().out
    for step in ("tail: staging cleanup", "tail: bucket lift", "tail: corpus copy",
                 "tail: verify_tree"):
        assert step in captured, f"a reclaim at the inner banner truncated: {step} missing"
    assert BANNER_OK_HEAD in captured, "the inner banner must still forward live"
    assert captured.index(BUCKET_DONE_LINE) < captured.index(
        "reclaimed after"
    ), "the reclaim must follow the child's completion line, not the inner banner"
    assert "'bucket'" in captured, "the E2 disclosure must name the marker kind"
    assert _group_is_empty(pgid_file)


@POSIX_ONLY
def test_the_inner_banner_alone_does_not_complete_the_bucket_marker(
    tmp_path: Path,
) -> None:
    """The F1-generalization control (design §4 arm d, second half): a bucket
    child that hangs right after the INNER banner and never prints its own
    completion line must hit the named-timeout SystemExit — the inner banner
    does not complete the bucket marker, so E2 cannot fire and only the E4
    bound ends the run. This is the frozen-tag residual shape (R5): a tag
    whose script hangs mid-tail is bounded to a loud red, not rescued."""
    mod = _load()
    pgid_file = tmp_path / "bucket-inner-only-pgid"
    with pytest.raises(SystemExit, match=r"command timed out after 10s"):
        mod.run(
            [sys.executable, "-c", _CHILD_BUCKET_INNER_BANNER_ONLY, str(pgid_file)],
            cwd=tmp_path,
            done_marker="bucket",
            grace=1.5,  # an inner-banner match would return "" here, via E2
            timeout=10.0,
        )
    assert _group_is_empty(pgid_file), "E4 must reclaim the group, not leak it"


@POSIX_ONLY
def test_reclaim_reaps_a_zombie_leader_instead_of_stranding_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The twin's F5b arm: a group whose only member is the unreaped leader
    zombie must drain to EMPTY — the leader is reaped inside the reclamation
    (proc.poll in the wait loop) and the group is addressed by construction
    (pgid = proc.pid, since start_new_session makes the child its own
    leader), so a zombie leader can neither strand itself nor hide its
    grandchildren. The arm constructs the zombie WITHOUT reaping (a live
    leader answers killpg(0) with success on macOS, a zombie-only group
    answers EPERM) and asserts the group ends empty with no survivor warning.
    On Linux a zombie answers kill probes with success, so the construction
    cannot zombify detectably there — the arm pins the macOS class only
    (disclosed)."""
    mod = _load()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
            "sys.stdout.write('exited\\n')",
        ],
        stdout=subprocess.DEVNULL,
        start_new_session=True,
    )
    pgid = os.getpgid(proc.pid)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except PermissionError:
            break  # zombie-only group: the F5b shape is constructed
        except ProcessLookupError:
            break  # reaped out from under the arm; the assert below still holds
        time.sleep(0.02)
    mod._reclaim_group(proc)
    out = capsys.readouterr().out
    assert "still has member processes" not in out
    with pytest.raises(ProcessLookupError):
        os.killpg(pgid, 0)  # pre-fix: EPERM — the stranded zombie remains


@POSIX_ONLY
def test_reclaim_kills_a_sigterm_ignoring_grandchild(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The load-shape extreme of CI run 39209775675 (ubuntu, -n auto): a
    grandchild that IGNORES SIGTERM. Two sibling defects let it survive in
    the twin's pre-fix shape: the reclaim's SIGTERM→SIGKILL escalation was
    keyed to the LEADER's exit rather than the GROUP's, and the emptiness
    probe treated killpg(0) success as "alive, done". The arm's contract is
    the property: the group is empty AFTERWARDS (polled to a deadline), and
    no false survivor warning is logged on the way there."""
    mod = _load()
    pgid_file = tmp_path / "term-ignore-pgid"
    with pytest.raises(SystemExit, match=r"command failed \(banner\)"):
        mod.run(
            [sys.executable, "-c", _CHILD_SIGTERM_IGNORE, str(pgid_file)],
            cwd=tmp_path,
            done_marker=True,
            grace=1.0,
            timeout=60.0,
        )
    assert _group_is_empty(pgid_file), "a SIGTERM-ignoring grandchild survived reclamation"
    assert "still has member processes" not in capsys.readouterr().out


def test_reclaim_refuses_loudly_on_a_non_posix_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The twin's F2 arm: CPython on Windows silently ignores
    start_new_session and has no process groups to reclaim, so the guard
    cannot do its work there — _reclaim_group must refuse loudly with the
    platform named, never silently run unprotected. The suite's process-group
    arms skip on win32; this arm runs everywhere, pinning the refusal itself
    (Build Docs is ubuntu-only — .github/workflows/docs.yml)."""
    mod = _load()
    monkeypatch.setattr(sys, "platform", "win32")

    class _Stub:
        pid = -1

        def wait(self, timeout: float | None = None) -> int:
            raise AssertionError("the guard must refuse before touching the process")

    with pytest.raises(SystemExit, match=r"unsupported on win32"):
        mod._reclaim_group(_Stub())


@POSIX_ONLY
def test_env_reaches_the_child_through_the_guarded_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gateway's env delta (design §4 arm h): run() keeps the env=
    parameter the SDK's runner lacks — the bucket child needs
    UV_PROJECT_ENVIRONMENT and the help capture needs its constructed env.
    The guarded path must thread it into the Popen: the child proves the
    variable reached it by echoing it, and completes via the bucket marker."""
    mod = _load()
    mod.run(
        [sys.executable, "-c", _CHILD_ENV_PROBE],
        cwd=tmp_path,
        env={"BW_GUARD_ENV_PROBE": "reached-the-child", "PATH": os.environ.get("PATH", "")},
        done_marker="bucket",
        grace=1.0,
        timeout=30.0,
    )
    captured = capsys.readouterr().out
    assert "env-probe: reached-the-child" in captured, "env= did not reach the child"
    assert "reclaimed after" in captured  # the E2 ending, so the env rode the guarded path


def test_marker_regexes_pin_the_literal_0170_banner() -> None:
    """WIRING check (the twin's F4 re-scoping): the synthetic literals the
    fake children print actually trigger the module's marker regexes — a fake
    child whose banner text missed the markers would silently turn every hang
    arm into an E4 timeout arm. This is NOT the pin-drift tripwire; that is
    the byte-capture fixture arm below."""
    mod = _load()
    assert mod.OK_BANNER_HEAD_RE.search(BANNER_OK_HEAD)
    assert mod.SITE_READY_RE.search(BANNER_SITE_READY)
    assert mod.FAIL_BANNER_RE.search(BANNER_FAIL)
    assert mod.BUCKET_DONE_RE.search(BUCKET_DONE_LINE)


def test_marker_regexes_pin_the_captured_0170_output_and_the_script_line() -> None:
    """The pin-drift tripwire, three sides (the twin's F4 arm plus the
    gateway's bucket contract):

    - REAL captured 0.17.0 output (byte-capture fixtures copied from the SDK
      twin, machine paths sanitized) pins the banner-box shape: the OK head
      precedes the Site ready line inside the box. The isolated fixture is
      the byte-evidence for the bucket kind's rule: a great-docs child's pipe
      carries the inner banner while real work (the copy, then the outer
      completion) still follows it.
    - The script's OWN final line is the bucket marker's authority: the arm
      re-renders the line from the script source, so rewording it reds here —
      and every future tag carries this arm against its own tree (design §8's
      reopen trigger).
    - The frozen v0.4.0 tag (the only tag CI builds) words the line
      identically — verified at its script :1435; the literal pins today's
      frozen bytes so a wording change in a future tag is caught when that
      tag's own tree runs this arm.
    """
    mod = _load()
    inproc = (ROOT / "tests" / "fixtures" / "great_docs_0.17.0_inproc_banner.txt").read_text(
        encoding="utf-8"
    )
    isolated = (
        ROOT / "tests" / "fixtures" / "great_docs_0.17.0_isolated_tail.txt"
    ).read_text(encoding="utf-8")
    inproc_lines = inproc.splitlines()
    assert any(mod.OK_BANNER_HEAD_RE.search(line) for line in inproc_lines)
    assert any(mod.SITE_READY_RE.search(line) for line in inproc_lines)
    i_ok = next(i for i, ln in enumerate(inproc_lines) if mod.OK_BANNER_HEAD_RE.search(ln))
    i_site = next(i for i, ln in enumerate(inproc_lines) if mod.SITE_READY_RE.search(ln))
    assert i_ok < i_site, "inside the box the OK head precedes the Site ready line"
    iso_lines = isolated.splitlines()
    i_banner = next(i for i, ln in enumerate(iso_lines) if mod.OK_BANNER_HEAD_RE.search(ln))
    i_done = next(i for i, ln in enumerate(iso_lines) if "Site built successfully" in ln)
    assert i_banner < i_done, (
        "the captured great-docs child prints its banner with real work still "
        "ahead of it — the byte-evidence for the bucket kind's ignore rule"
    )
    assert not any(
        mod.BUCKET_DONE_RE.search(line) for line in iso_lines
    ), "tool output must not forge the script-authored bucket marker"
    # The script's own final line, re-rendered from source.
    source = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r'log\(f"assembled bucket \{args\.bucket\} at \{dest\}"\)', source)
    assert m is not None, "the --bucket completion line is no longer log()-worded as pinned"
    rendered = "[assemble] assembled bucket v0.4.0 at /tmp/bucket-out"
    assert mod.BUCKET_DONE_RE.search(rendered), (
        "BUCKET_DONE_RE no longer matches the script's own completion line"
    )
    assert mod.BUCKET_DONE_RE.search(BUCKET_DONE_LINE)
