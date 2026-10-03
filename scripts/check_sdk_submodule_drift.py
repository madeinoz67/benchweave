"""CI gate: refuse a stale ``packages/sdk`` gitlink (issue #347 WS1, R-2).

The gateway mounts the SDK as a git submodule. Every existing gate proves
CONSISTENCY of the mount (gateway standards vs the SDK lock vs the vendored
tree, via ``make check-sdk-standards``); none proves FRESHNESS — a
self-consistent mount pinned many commits behind the SDK's latest release
tag passed every lane green, which is the staleness symptom #347 filed.

The check compares two commits:

- the gitlink COMMITTED in this repository's HEAD (``git ls-tree`` — not
  the submodule working tree's HEAD, which moves before the pointer is
  committed), and
- the commit the SDK's latest ``vX.Y.Z`` RELEASE tag dereferences to
  (``git ls-remote --tags``: the ``^{}`` line when the tag is annotated —
  the plain ref line names the tag OBJECT for annotated tags, and comparing
  against it would report permanent drift on a current mount).

Exit codes (the contract the CI job and the unit tests pin):

- 0 — no drift: the gitlink sits at the latest release tag's commit.
- 1 — drift: the gitlink is not the latest release tag's commit; the
  message names both commits and the tag.
- 2 — INDETERMINATE: the drift could not be determined (fetch failed or
  timed out, no vX.Y.Z tag parsed, HEAD carries no packages/sdk gitlink).
  Fail closed: a network blip must never read as "no drift" — and never
  masquerade as drift either.

What this check deliberately does NOT catch, each with its own lane: lock
or vendored-tree inconsistency against the pinned SDK (``make
check-sdk-standards``); a DELIBERATELY older pin — pinning below the latest
release on purpose still reads as drift here and is answered by shipping a
fresh release pin, not by ignoring the gate; prerelease-suffixed tags
(``vX.Y.Z-rc1`` names no release — the highest plain ``vX.Y.Z`` wins).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SUBMODULE_PATH = "packages/sdk"
DEFAULT_REMOTE = "https://github.com/madeinoz67/benchweave-sdk.git"
LS_REMOTE_TIMEOUT_S = 30

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_INDETERMINATE = 2

# A release ref is exactly refs/tags/v<major>.<minor>.<patch>. Suffixed
# (prerelease/build) tags name no release and are excluded by this pattern
# itself, not by post-filtering.
_RELEASE_REF = re.compile(r"^refs/tags/v(\d+)\.(\d+)\.(\d+)$")
_DEREF_SUFFIX = "^{}"


class IndeterminateError(Exception):
    """The drift could not be determined — never read as "no drift"."""


@dataclass(frozen=True)
class ReleaseTag:
    """A parsed release tag and the commit it denotes."""

    tag: str
    commit: str


def latest_release(ls_remote_output: str) -> ReleaseTag | None:
    """Parse ``git ls-remote --tags`` output and return the highest
    ``vX.Y.Z`` release tag with its PEELED commit — the ``^{}`` deref line
    when the tag is annotated, the ref line itself for a lightweight tag.
    None when no release tag parses."""
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
        # A deref line wins for its tag: it names the commit the annotated
        # tag object points at.
        (derefs if peeled else refs)[tag] = sha
    if not refs:
        return None
    best = max(refs, key=lambda tag: tuple(int(part) for part in tag[1:].split(".")))
    return ReleaseTag(tag=best, commit=derefs.get(best, refs[best]))


def evaluate(gitlink: str, ls_remote_output: str) -> tuple[int, str]:
    """The drift verdict as a pure function of its inputs: (exit code,
    message) per the module's exit-code contract."""
    release = latest_release(ls_remote_output)
    if release is None:
        return (
            EXIT_INDETERMINATE,
            "no vX.Y.Z release tag parsed from the remote — cannot determine drift",
        )
    if release.commit != gitlink:
        return (
            EXIT_DRIFT,
            f"packages/sdk gitlink {gitlink} is stale: latest SDK release "
            f"{release.tag} sits at {release.commit} — advance the pointer "
            f"(git -C packages/sdk checkout {release.tag} && git add packages/sdk)",
        )
    return EXIT_OK, f"packages/sdk gitlink {gitlink} is at {release.tag}"


def committed_gitlink(repo: Path) -> str:
    """The gitlink COMMITTED at HEAD for the submodule path. Deliberately
    not the submodule working tree's HEAD: that moves before the pointer
    commit lands, and this gate judges committed state."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-tree", "HEAD", SUBMODULE_PATH],
            capture_output=True,
            text=True,
            timeout=LS_REMOTE_TIMEOUT_S,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise IndeterminateError(f"git ls-tree failed: {exc}") from exc
    if proc.returncode != 0:
        raise IndeterminateError(
            f"git ls-tree exited {proc.returncode}: {proc.stderr.strip()}"
        )
    # "160000 commit <sha>\t<path>" — tab-split fields.
    fields = proc.stdout.split()
    if len(fields) < 3 or fields[0] != "160000" or fields[1] != "commit":
        raise IndeterminateError(
            f"HEAD carries no packages/sdk gitlink (ls-tree: {proc.stdout.strip()!r})"
        )
    return fields[2]


def remote_tag_list(remote: str) -> str:
    """``git ls-remote --tags`` against the SDK remote."""
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--tags", remote],
            capture_output=True,
            text=True,
            timeout=LS_REMOTE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise IndeterminateError(
            f"git ls-remote timed out after {LS_REMOTE_TIMEOUT_S}s"
        ) from exc
    except OSError as exc:
        raise IndeterminateError(f"git ls-remote failed to start: {exc}") from exc
    if proc.returncode != 0:
        raise IndeterminateError(
            f"git ls-remote exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refuse a stale packages/sdk gitlink (issue #347 WS1, R-2)."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="gateway repository root (default: current directory)",
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help="SDK remote to read release tags from (any git URL or local path)",
    )
    args = parser.parse_args(argv)
    try:
        gitlink = committed_gitlink(args.repo)
        output = remote_tag_list(args.remote)
    except IndeterminateError as exc:
        print(f"sdk-drift INDETERMINATE: {exc}", file=sys.stderr)
        return EXIT_INDETERMINATE
    code, message = evaluate(gitlink, output)
    prefix = {EXIT_OK: "OK", EXIT_DRIFT: "DRIFT", EXIT_INDETERMINATE: "INDETERMINATE"}
    print(f"sdk-drift {prefix[code]}: {message}", file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
