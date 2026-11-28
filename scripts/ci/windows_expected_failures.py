"""The Windows expected-failures baseline comparison (issue #457).

The Windows evidence lanes (``windows`` per-PR core subset, ``windows-full``
weekly complement) run with ``continue-on-error`` on the pytest step only:
test reds are DATA, carried by the ``::warning::`` annotation, the job
summary and the junitxml artifact (PR #343's evidence posture — unchanged).
What that posture cannot see is NEW breakage: a fresh Windows regression
fails identically to a known platform truth and the lane stays green. This
script is the strict half over the same junit artifact: the reviewed
manifest (``tests/windows_expected_failures.json``) lists every
currently-known Windows-failing test id with a one-line reason, and the
comparison REDS the lane when the run disagrees with it.

Exit contract (the win_core_manifest shape): 0 the run matches the
manifest; 1 drift — a failing id NOT in the manifest (new Windows
breakage: fix it or add a reviewed row in the same change) or a ``strict``
row whose id RAN in this lane and did not fail (healing is visible: remove
or update the row in the same change); 2 fail-closed — junit absent or
unreadable, zero collected testcases, duplicate ids (skip-first included),
a testcase without derivable id attributes, manifest absent, unreadable or
non-UTF-8, malformed (including a duplicate JSON key — last-wins would
silently shadow a strict row), foreign-schema, an empty rows object, or a
bad row shape. A comparison step that cannot read its inputs must never
read as green.

Lane scoping (design record §3): one manifest serves two selections, so a
``strict`` row is judged ONLY over the ids the lane's junit actually
collected and ran. An id the selection does not collect is inert for that
lane — not "healed". A SKIPPED testcase is inert both ways: skip is
neither failing nor passing (and fork PRs legitimately skip the
signing-key rows when the fixture secrets are absent). What this gate does
NOT catch: a test that goes failing→skipped (the win-core ratchet
``tests/win_core_manifest.json`` and the #207 census discipline carry
selection changes); non-strict rows healing (pruning them is census-time
maintenance, by design — the kill-family intermittents are pure data until
50 executions, PR #343's doctrine); a strict row whose test is RENAMED
(same-count rename: the old id stops being collected and the stale row is
inert forever — prune rows when tests rename); an aborted-but-well-formed
session that contains only listed failures (the coverage-anchor follow-up
under #207).

Maintenance flow: the red IS the forcing function. Unlisted failing id →
fix the breakage or add the row (id, kind, one-line reason citing the
census run) in the same change. Healed strict row → remove or update the
row in the same change. The manifest is the machine-checked distillation
of the #207 census, never its replacement. Coverage residual (disclosed,
from the adversarial pass): a WELL-FORMED junit from an aborted session
that contains only listed failures still reads green — the gate cannot
distinguish "not in this lane's selection" from "this run never got
there". The zero-testcase fail-closed and the win-core ratchet catch the
coarser collapses; the fine-grained anchor (artifact count == the
ratchet's pinned selection count) is a named follow-up under #207.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = "benchweave.windows-expected-failures/1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "tests" / "windows_expected_failures.json"
KINDS = ("strict", "non-strict")


class FailClosed(Exception):
    """An input this gate cannot read unambiguously (exit 2)."""


def canonical_id(file_attr: str, classname: str, name: str) -> str:
    """The pytest nodeid for a junit testcase's Windows-shaped attributes.

    ``file`` arrives with backslashes; ``classname`` is the dotted module
    (plus any ``Test``-class chain); ``name`` carries any ``[param]`` id.
    Non-``.py`` collected files (the ui-contract markdown gate) carry the
    PATH-dotted form in ``classname`` — extension included — so the prefix
    strip keeps the row chain (``...ui-contract.md.row.e-2-6-...``) instead
    of collapsing distinct rows onto one id. The manifest keys on the
    forward-slash nodeid so one row spelling serves every platform that
    ever parses the artifact.
    """
    file_posix = file_attr.replace("\\", "/")
    if file_posix.endswith(".py"):
        prefix_dotted = file_posix[:-3].replace("/", ".")
    else:
        prefix_dotted = file_posix.replace("/", ".")
    classes = ""
    if classname.startswith(prefix_dotted + "."):
        classes = classname[len(prefix_dotted) + 1 :]
    return "::".join(part for part in (file_posix, classes, name) if part)


def parse_junit(path: Path) -> tuple[set[str], set[str]]:
    """Collect ``(ran, failed)`` nodeid sets from a pytest junitxml artifact.

    ``ran`` excludes skipped testcases (skip is neither failing nor
    passing). Fail-closed: absent/unparseable file, a testcase missing its
    ``file``/``name`` attributes, zero collected testcases (a collector
    crash must never read as all-healed green), and duplicate ids (an
    ambiguous outcome cannot be judged).
    """
    try:
        # S314: parses the junit this lane's own pytest step just wrote —
        # same-job artifact, not untrusted input (the gate.py precedent).
        root = ET.parse(path).getroot()  # noqa: S314
    except (OSError, ET.ParseError) as exc:
        raise FailClosed(f"junit unreadable at {path}: {exc}") from exc
    ran: set[str] = set()
    failed: set[str] = set()
    seen: set[str] = set()
    for tc in root.iter("testcase"):
        file_attr = tc.get("file")
        name = tc.get("name")
        if not file_attr or not name:
            raise FailClosed(
                f"testcase without file/name attributes (classname="
                f"{tc.get('classname')!r}) — the id cannot be derived safely"
            )
        node = canonical_id(file_attr, tc.get("classname", ""), name)
        if node in seen:
            raise FailClosed(f"duplicate testcase id in junit: {node}")
        seen.add(node)
        if tc.find("skipped") is not None:
            continue
        if tc.find("failure") is not None or tc.find("error") is not None:
            failed.add(node)
        ran.add(node)
    if not ran:
        raise FailClosed(
            f"junit at {path} collected zero testcases — a collector crash "
            "must never read as green"
        )
    return ran, failed


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """object_pairs_hook: a repeated JSON key is a malformed manifest.

    ``json.loads`` keeps the LAST occurrence of a duplicate key before any
    validation can see it — a hand-edit or merge-conflict resolution that
    duplicates a row (worst case: a strict row shadowed by a non-strict
    twin) would silently disable the healing check. Refuse it here.
    """
    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            raise FailClosed(f"manifest carries duplicate JSON key: {key!r}")
        seen.add(key)
    return dict(pairs)


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    """Read the manifest, refusing anything not shaped like ours (fail closed)."""
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates
        )
    except FileNotFoundError:
        raise FailClosed(
            f"manifest absent at {path} — the baseline cannot be checked "
            "without it"
        ) from None
    except UnicodeDecodeError as exc:
        # A Windows editor saving the manifest as UTF-16 lands here; an
        # unreadable manifest is fail-closed, not drift.
        raise FailClosed(
            f"manifest at {path} is not valid UTF-8 ({exc.reason} at byte "
            f"{exc.start}) — re-save it as UTF-8"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise FailClosed(f"manifest unreadable at {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise FailClosed(f"manifest schema mismatch (want {SCHEMA}) at {path}")
    rows = data.get("rows")
    if not isinstance(rows, dict) or not rows:
        raise FailClosed(
            "manifest carries no rows — an empty baseline reds nothing and "
            "protects nothing; populate it from the census"
        )
    for row_id, row in rows.items():
        if not isinstance(row, dict) or row.get("kind") not in KINDS:
            raise FailClosed(
                f"bad row shape for {row_id}: kind must be one of {KINDS} "
                "with a non-empty reason"
            )
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise FailClosed(f"bad row shape for {row_id}: reason must be a "
                             "non-empty string")
    return rows


def compare(
    ran: set[str], failed: set[str], rows: dict[str, dict[str, str]]
) -> list[str]:
    """Diff one lane's run against the manifest. Returns problem lines.

    Pure function: exit-code mapping and printing live in :func:`main`.
    """
    problems: list[str] = []
    for node in sorted(failed - set(rows)):
        problems.append(
            f"unlisted failing id: {node} — NEW Windows breakage (or an "
            "unreviewed census change): fix it, or add a reviewed row to "
            "tests/windows_expected_failures.json in this change"
        )
    for row_id, row in sorted(rows.items()):
        if row["kind"] != "strict":
            continue
        if row_id in ran and row_id not in failed:
            problems.append(
                f"strict row not failing: {row_id} — healing is visible: "
                "remove or update the manifest row in this change"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--junit", type=Path, required=True,
                        help="the lane's junitxml artifact to compare")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help="manifest path override (default: "
                             "tests/windows_expected_failures.json)")
    parser.add_argument("--lane", default="windows",
                        help="lane name for messages (windows | windows-full)")
    args = parser.parse_args(argv)
    try:
        rows = load_manifest(args.manifest)
        ran, failed = parse_junit(args.junit)
    except FailClosed as exc:
        print(f"windows-expected-failures [{args.lane}]: FAIL-CLOSED — {exc}",
              file=sys.stderr)
        return 2
    strict_rows = sum(1 for row in rows.values() if row["kind"] == "strict")
    nonstrict_rows = len(rows) - strict_rows
    inert = sum(1 for row_id in rows if row_id not in ran)
    problems = compare(ran, failed, rows)
    if problems:
        print(
            f"windows-expected-failures [{args.lane}]: {len(problems)} "
            f"drift problem(s) against tests/windows_expected_failures.json:"
        )
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"windows-expected-failures [{args.lane}]: ok — {len(failed)} "
        f"failing id(s), all listed ({strict_rows} strict, "
        f"{nonstrict_rows} non-strict rows; {inert} row(s) not exercised "
        "by this run — not collected by this lane's selection, or "
        "skipped — inert by design)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
