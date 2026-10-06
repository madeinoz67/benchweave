"""CI gate: the declared-pin lane for the ``packages/sdk`` mount (issue #408 S2).

The gateway mounts the SDK as a git submodule. The OLD gate keyed the
mount's freshness to the SDK remote's LATEST release tag with exact
equality — structurally red on every legitimate branch-tip gitlink (the
era-bind mid-train mounts, the post-merge/pre-tag window); the CI map's
own row carried that cost. The declared-pin pattern kills the coupling:
the pin and the gitlink move in the SAME commit, and the gate checks
pointer-vs-pin.

The declaration lives beside the mount's own metadata (``.gitmodules``,
owner fork F2 — the checker already read the file for the remote; unknown
``submodule.<name>.*`` keys are inert to git tooling)::

    [submodule "packages/sdk"]
        path = packages/sdk
        url = https://github.com/madeinoz67/benchweave-sdk.git
        pin = v0.7.1          # or a 40-hex SHA: the declared-train state

The pin IS the declaration: writing a SHA is how a train declares itself.

Exit codes (the contract the CI job and the unit tests pin):

- 0 — green: ``gitlink == resolved(pin)``. SHA pins compare locally (the
  verdict needs no network — mid-train pushes stay green offline); tag
  pins resolve through the existing peeled-deref machinery.
- 1 — red: ``gitlink != resolved(pin)``. The pin and the gitlink move in
  the same commit — a pin disagreeing with the mount is red. Enforced AT
  EVERY REF THIS LANE OBSERVES: CI sees pushed refs, so an intermediate
  commit of a split train is unobserved until pushed (this branch's own
  pre-advance intermediates sat red); the self-referential fast-lane arm
  extends the observation to every local run of the suite.
- 2 — INDETERMINATE (fail closed): no gitlink at HEAD; the pin key absent
  or malformed (an undeclared mount fails closed — every pointer PR must
  carry the pin); tag-pin resolution failed (network — identical
  sensitivity to the old gate, never worse); undecodable bytes.

Annotations ride the message on green (never a skipped job — the GitHub
skipped-required-check constraint): ``::warning::`` when the pin trails
the latest release tag (``pin vA trails latest vB — pairing pending``) or
names a non-tag SHA (``declared train or unpaired mount``); ``::notice::``
when freshness is unknowable (fetch failed — the annotation degrades, the
verdict does not). Owner fork F3: the trailing-pin condition gates the
gateway cut as a family-doc walk row, NOT a machine gate.

What this check deliberately does NOT catch, each with its own lane: lock
or vendored-tree inconsistency against the pinned SDK (``make
check-sdk-standards``); a pin that trails by more than the pairing window
(a family-doc walk row reads the annotation; the mechanical upgrade is a
"trailing by >1 release is red" rule, which re-accepts network dependence
in that arm only); prerelease-suffixed tags (``vX.Y.Z-rc1`` names no
release); any SECOND submodule mount — the gate reads
``submodule.packages/sdk`` alone, so another submodule (today none) would
be silently undeclared by this lane and needs its own row.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SUBMODULE_PATH = "packages/sdk"
# Only a FALLBACK: the remote is read from this repository's .gitmodules so
# the SDK URL is named once (governor F1) — never duplicated here and there.
FALLBACK_REMOTE = "https://github.com/madeinoz67/benchweave-sdk.git"
LS_REMOTE_TIMEOUT_S = 30

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_INDETERMINATE = 2

# A release ref is exactly refs/tags/v<major>.<minor>.<patch>. Suffixed
# (prerelease/build) tags name no release and are excluded by this pattern
# itself, not by post-filtering.
_RELEASE_REF = re.compile(r"^refs/tags/v(\d+)\.(\d+)\.(\d+)$")
_DEREF_SUFFIX = "^{}"
_PIN_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_PIN_SHA = re.compile(r"^[0-9a-f]{40}$")


class IndeterminateError(Exception):
    """The drift could not be determined — never read as "no drift"."""


@dataclass(frozen=True)
class ReleaseTag:
    """A parsed release tag and the commit it denotes."""

    tag: str
    commit: str


def _parse_refs(ls_remote_output: str) -> tuple[dict[str, str], dict[str, str]]:
    """Split ``git ls-remote --tags`` output into (plain refs, peeled
    derefs) maps for release tags. The deref line wins for its tag: it
    names the commit the annotated tag object points at."""
    refs: dict[str, str] = {}
    derefs: dict[str, str] = {}
    for line in ls_remote_output.splitlines():
        sha, tab, ref = line.partition("\t")
        if not tab:
            continue
        ref = ref.strip()
        peeled = ref.endswith(_DEREF_SUFFIX)
        if peeled:
            ref = ref[: -len(_DEREF_SUFFIX)]
        if _RELEASE_REF.match(ref) is None:
            continue
        tag = ref.removeprefix("refs/tags/")
        (derefs if peeled else refs)[tag] = sha
    return refs, derefs


def latest_release(ls_remote_output: str) -> ReleaseTag | None:
    """Parse ``git ls-remote --tags`` output and return the highest
    ``vX.Y.Z`` release tag with its PEELED commit — the ``^{}`` deref line
    when the tag is annotated, the ref line itself for a lightweight tag.
    None when no release tag parses."""
    refs, derefs = _parse_refs(ls_remote_output)
    if not refs:
        return None
    best = max(refs, key=lambda tag: tuple(int(part) for part in tag[1:].split(".")))
    return ReleaseTag(tag=best, commit=derefs.get(best, refs[best]))


def resolve_tag(ls_remote_output: str, tag: str) -> str | None:
    """The commit ONE release tag denotes — ``latest_release``'s peeled
    handling generalized to a single tag. None when the tag is absent."""
    refs, derefs = _parse_refs(ls_remote_output)
    return derefs.get(tag, refs.get(tag))


def _tag_order(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in tag[1:].split("."))


def evaluate(
    gitlink: str, pin: str, ls_remote_output: str | None
) -> tuple[int, str]:
    """The verdict as a pure function of its inputs: (exit code, message)
    per the module's exit-code contract. Annotation lines (``::warning::``/
    ``::notice::``) ride the message on green — the lane prints them as-is.

    SHA pins decide locally: ``ls_remote_output`` may be None (fetch
    failed) without changing the verdict — that is the structural
    improvement over keying freshness to the latest tag. Tag pins need the
    remote; a failed fetch reads indeterminate, never red-or-green."""
    sha_pin = _PIN_SHA.fullmatch(pin) is not None
    if sha_pin:
        if gitlink != pin:
            return (
                EXIT_DRIFT,
                f"packages/sdk gitlink {gitlink} is not the declared pin {pin} "
                "— the pin and the gitlink move in the same commit",
            )
    else:
        if ls_remote_output is None:
            return (
                EXIT_INDETERMINATE,
                f"cannot resolve pin {pin}: the remote was unreadable "
                "(identical sensitivity to the old gate, never worse)",
            )
        commit = resolve_tag(ls_remote_output, pin)
        if commit is None:
            return (
                EXIT_INDETERMINATE,
                f"pin {pin} not found on the remote — cannot resolve the "
                "declared pin (a removed/renamed tag fails closed)",
            )
        if gitlink != commit:
            return (
                EXIT_DRIFT,
                f"packages/sdk gitlink {gitlink} is not the declared pin {pin} "
                f"({commit}) — the pin and the gitlink move in the same commit",
            )

    lines = [
        f"packages/sdk gitlink {gitlink} is at the declared pin {pin}"
        + ("" if sha_pin else f" ({resolve_tag(ls_remote_output or '', pin)})")
    ]
    release = latest_release(ls_remote_output) if ls_remote_output is not None else None
    if sha_pin:
        lines.append(
            f"::warning::non-tag pin {pin} — declared train or unpaired mount"
        )
        if release is None:
            lines.append(
                "::notice::pin freshness unknowable (the remote was unreadable) "
                "— the annotation degrades, the verdict does not"
            )
    elif release is not None and _tag_order(pin) < _tag_order(release.tag):
        lines.append(
            f"::warning::pin {pin} trails latest {release.tag} — pairing pending"
        )
    return EXIT_OK, "\n".join(lines)


def committed_gitlink(repo: Path) -> str:
    """The gitlink COMMITTED at HEAD for the submodule path. Deliberately
    not the submodule working tree's HEAD: that moves before the pointer
    commit lands, and this gate judges committed state."""
    proc = _run_git(
        ["git", "-C", str(repo), "ls-tree", "HEAD", SUBMODULE_PATH]
    )
    # "160000 commit <sha>\t<path>" — tab-split fields.
    fields = proc.split()
    if len(fields) < 3 or fields[0] != "160000" or fields[1] != "commit":
        raise IndeterminateError(
            f"HEAD carries no packages/sdk gitlink (ls-tree: {proc.strip()!r})"
        )
    return fields[2]


def remote_tag_list(remote: str) -> str:
    """``git ls-remote --tags`` against the SDK remote."""
    try:
        return _run_git(["git", "ls-remote", "--tags", remote], timeout=LS_REMOTE_TIMEOUT_S)
    except IndeterminateError as exc:
        raise IndeterminateError(
            f"git ls-remote against {remote} failed: {exc}"
        ) from exc


def configured_remote(repo: Path) -> str:
    """The SDK remote as this repository configures it — the submodule's
    .gitmodules url, so the URL lives in one place (governor F1).
    FALLBACK_REMOTE when the key is absent, empty, or unreadable."""
    proc = _run_git(
        [
            "git", "-C", str(repo), "config", "--file", ".gitmodules",
            f"submodule.{SUBMODULE_PATH}.url",
        ],
        missing_ok=True,
    )
    return proc.strip() or FALLBACK_REMOTE


def configured_pin(repo: Path) -> str:
    """The DECLARED pin: ``submodule.<name>.pin`` from .gitmodules — read
    from HEAD's BLOB (``git config --blob HEAD:.gitmodules``), not the
    working tree: this gate judges committed state, and an uncommitted
    working-tree pin edit must not green what was committed red (the L-3
    repro: committed pin v0.4.1 + mount moved + working-tree edit to match
    greened the old reader). Empty string when absent — the caller reads
    that as an undeclared mount and fails closed (exit 2), so every
    pointer PR must carry the pin."""
    proc = _run_git(
        [
            "git", "-C", str(repo), "config", "--blob", "HEAD:.gitmodules",
            f"submodule.{SUBMODULE_PATH}.pin",
        ],
        missing_ok=True,
    )
    return proc.strip()


def _run_git(
    cmd: list[str], *, timeout: int = LS_REMOTE_TIMEOUT_S, missing_ok: bool = False
) -> str:
    """One git entry point for every reader: subprocess plumbing plus the
    fail-closed wrapping the decode-raise arms pin (an undecodable byte
    reads indeterminate, never a traceback exiting 1)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise IndeterminateError(f"timed out after {timeout}s") from exc
    except (OSError, UnicodeDecodeError) as exc:
        # UnicodeDecodeError: subprocess's text=True strict-decodes captured
        # bytes INSIDE the call, so undecodable output raises here and reads
        # indeterminate — never an uncaught traceback exiting 1 (adversary
        # row 1 of the original review, preserved).
        raise IndeterminateError(f"{cmd[1]} failed: {exc}") from exc
    if proc.returncode != 0:
        # `git config --file <f> <key>` exits 1 exactly when the key is
        # unset — the readers that distinguish "absent" from "broken"
        # pass missing_ok and read the empty string.
        if missing_ok and proc.returncode == 1:
            return ""
        verb = cmd[3] if len(cmd) > 3 and cmd[1] == "-C" else cmd[1]
        raise IndeterminateError(
            f"{verb} exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "The declared-pin lane for the packages/sdk mount (issue #408 S2): "
            "gitlink vs the .gitmodules pin — tag or SHA. Exit 0 green (annotations "
            "for a trailing pin or a non-tag SHA), 1 red (pin/gitlink disagree — "
            "they move in the same commit), 2 indeterminate (fail closed: no "
            "gitlink, pin absent or malformed, tag-pin resolution failed, "
            "undecodable bytes)."
        )
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="gateway repository root (default: current directory)",
    )
    parser.add_argument(
        "--remote",
        default=None,
        help="SDK remote to read release tags from, any git URL or local path "
        "(default: the submodule's .gitmodules url, else the canonical SDK remote)",
    )
    args = parser.parse_args(argv)
    try:
        gitlink = committed_gitlink(args.repo)
        remote = args.remote if args.remote is not None else configured_remote(args.repo)
        pin = configured_pin(args.repo)
        if not pin:
            raise IndeterminateError(
                "pin_absent: .gitmodules carries no submodule.packages/sdk.pin — "
                "an undeclared mount fails closed; every pointer PR must carry "
                "the pin"
            )
        if _PIN_TAG.fullmatch(pin) is None and _PIN_SHA.fullmatch(pin) is None:
            raise IndeterminateError(
                f"pin_malformed: {pin!r} is neither vX.Y.Z nor a 40-hex SHA — "
                "an undeclared mount fails closed"
            )
        try:
            output: str | None = remote_tag_list(remote)
        except IndeterminateError:
            # The verdict degrades per the pin's kind (evaluate), never to a
            # silent pass: tag pins read indeterminate; SHA pins stay green
            # locally with a notice.
            output = None
        code, message = evaluate(gitlink, pin, output)
    except IndeterminateError as exc:
        print(f"sdk-drift INDETERMINATE: {exc}", file=sys.stderr)
        return EXIT_INDETERMINATE
    prefix = {EXIT_OK: "OK", EXIT_DRIFT: "DRIFT", EXIT_INDETERMINATE: "INDETERMINATE"}
    out = sys.stdout if code == EXIT_OK else sys.stderr
    for line in message.splitlines():
        if line.startswith("::"):
            print(line, file=sys.stdout)
    print(f"sdk-drift {prefix[code]}: {message.splitlines()[0]}", file=out)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
