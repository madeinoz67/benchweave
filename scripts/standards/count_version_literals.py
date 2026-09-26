#!/usr/bin/env python3
"""Count executable standards-version literals in the gateway source tree.

Issue #203 slice 1 (design §3.7, acceptance A4): a committed script — the
gate's counter, not a hand count — enumerates version literals in ratchet
mode (the count cannot rise; the baseline is committed beside this script).
The PRD §1.5 hand count was 13 sites at ``ef969af``; #201 re-versioned values
without removing any, so the baseline here is THIS SCRIPT's own measurement
at the slice's merge base (``403c061``) under the definition below — 12
sites. The 13-to-12 delta, regenerable (#215 fold row 20): this definition
counts the SAME 12 sites when re-run at ``ef969af`` and at ``403c061``
(site-for-site; only the values differ), so the hand count's extra site was
one this definition classifies as prose — a docstring or comment, excluded
below. The hand count's worksheet was never committed, so WHICH prose site
it included is unnameable from evidence; naming one would be invention. The
ratchet's authority is the committed baseline number, reproducibly derived
by this script at either ref.

DEFINITION (committed; changing it re-baselines by editorial decision, not
silently):

- A **version literal** is a string constant in EXECUTABLE code — docstrings
  are excluded (the first string statement of a module, class, or function
  body). Comments are not code and never count.
- Pattern A: a string containing ``<standard-id>/<X.Y.Z>`` for one of the six
  governed standards ids — the path-shaped literal (``execution/0.2.0``).
- Pattern B: a string that IS a bare ``X.Y.Z`` (three-component pure semver),
  counted EVERYWHERE in executable code. The DECLARED FILES register below
  documents the sites carrying registered exceptions (the D2 register:
  corpus-owned code whose literals are acknowledged, pending derivation) —
  in ratchet mode they still COUNT (the ceiling holds them); slice 7's
  zero-mode is what turns the register into an exemption list.
- Scope is ``src/benchweave/`` only. Literals in ``scripts/`` are outside the
  counted tree AND registered here when they name a version (#215 fold row
  22): ``scripts/adc_conformance_control.py`` carries ``YANKED_PIN``/
  ``MOVE_TO`` ("0.2.1"/"0.2.2") — the A1 anti-gaming arm's planted pin and
  its expected move-to. Motion mechanism: both flip with the yank policy
  block, in the same arc as the policy row (a future yank or unk of another
  version changes the pair); they never ride a corpus bump silently. The A4
  denominator is unchanged — these sites were never inside the counted
  tree, and registering them adds no exemption, only the record.

Exit status: 0 when the count is at or below the committed baseline, 1 when
it rises (or on any parse failure — a count that cannot be computed is a
refusal, never a guess). ``--json`` prints per-site rows for review.

Slice 7 flips the ratchet to zero-mode; until then the baseline number below
is the ceiling.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

STANDARD_IDS = ("otdp", "registry", "execution", "interface", "plugin-ui", "plugin-ui-preview")
PATTERN_A = re.compile(r"\b(?:" + "|".join(STANDARD_IDS) + r")/\d+\.\d+\.\d+")
PATTERN_BARE = re.compile(r"^\d+\.\d+\.\d+$")
# The D2 registered-exception register (documented; ratchet mode still counts
# these sites — slice 7's zero-mode consumes the register as exemptions):
# plugin-ui corpus-owned code, the VR-25 registered exception, deferral D2.
DECLARED_FILES = ("src/benchweave/presentation/contracts.py",)

# Ratchet baseline: this script's own count at merge base 403c061 (#215).
BASELINE = 12

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src" / "benchweave"


def _docstring_ids(tree: ast.Module) -> set[int]:
    """Ids of the Constant nodes that are docstrings (first string statement)."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                skip.add(id(body[0].value))
    return skip


def count_sites(source_root: Path = SOURCE_ROOT) -> list[dict[str, Any]]:
    """Every executable literal site, sorted for reproducibility."""
    sites: list[dict[str, Any]] = []
    import warnings

    for path in sorted(source_root.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        with warnings.catch_warnings():
            # A docstring escape-sequence warning in scanned source is noise
            # here, not a finding of this counter.
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        skip = _docstring_ids(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in skip:
                continue
            value = node.value
            kind = None
            if PATTERN_A.search(value):
                kind = "A"
            elif PATTERN_BARE.match(value.strip()):
                kind = "BARE"
            if kind is not None:
                sites.append(
                    {"file": relative, "line": node.lineno, "pattern": kind, "text": value[:80]}
                )
    return sorted(sites, key=lambda row: (row["file"], row["line"], row["pattern"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print per-site rows")
    arguments = parser.parse_args(argv)
    try:
        sites = count_sites()
    except (OSError, SyntaxError) as exc:
        print(f"version_literal_count_failed: {exc}", file=sys.stderr)
        return 1
    count = len(sites)
    if arguments.json:
        print(json.dumps({"baseline": BASELINE, "count": count, "sites": sites}, indent=2))
        return 0 if count <= BASELINE else 1
    verdict = "ok" if count <= BASELINE else "EXCEEDED"
    print(f"gateway executable version literals: {count} (baseline {BASELINE}, {verdict})")
    return 0 if count <= BASELINE else 1


if __name__ == "__main__":
    raise SystemExit(main())
