#!/usr/bin/env python3
"""The release-train pre-flight: one local command before a pointer commit.

Issue #459 (design record ``.claude/deep-review/2026-10-20-…-train-preflight
-design.md``): every surface a standards train touches already had an owner,
but every owner ran post-push in CI, and the pre-push aggregate existed only
in a maintainer's head. This script is that aggregate — plus the ONE check no
owner carried: the docs claim register.

THE CLAIM REGISTER (§3 — the only new checking logic in this increment).
Row 10 of the design's ownership table was unowned: docs prose version
claims ("X is active", "Y remains served", the four Baseline sentences) had
no mechanism deriving them from the standards manifest. The motion ratchet
(``count_version_literals.py`` docs scope) pins (file, literal) MOTION — a
green snapshot sat over a FALSE "is active" claim for a full train cycle
(the ``9b879cf8`` miss, 2026-10-14: 0.2.2 claimed active, 0.2.3 active).
The register derives TRUTH: a row is ``(file, anchor regex with one
capture, standard id, kind)``; the checker reads the file, finds the
anchor, extracts the literal, and derives the expectation — ``active``
rows must equal the manifest's active version for the id; ``served`` rows
must name a version the dependency-policy block retains (in range, not
yanked, not retired). Refusals, named, in the house prefix style:

- ``docs_claim_stale: <file>:<line> claims <id> <v> active, … says <w>``
- ``docs_claim_anchor_lost: <file> …`` — a moved or dissolved claim site
  fails until the register row is re-anchored: a visible editorial edit,
  never a silent pass (the counter register's anti-laundering shape).
- ``docs_claim_anchor_ambiguous: <file> …`` — an anchor matching MORE THAN
  ONE site (the anchor-hijack class, fold MED-1/L1: a decoy sentence above
  the declared site must not launder the declared row); the row re-anchors
  on a token unique to its site.
- ``docs_claim_status_nonstable: <file>:<line> asserts <id> whose manifest
  status is <status>, not 'stable'`` — the derivation reads the manifest's
  status, not the version alone (a standard deprecated at the same version
  must not leave is-active rows green; governor M1).
- ``docs_claim_check_failed: …`` — the register's inputs cannot be read
  (manifest absent/corrupt, an unparseable policy clause): a refusal,
  never a guess.

WHAT IT DELEGATES (§4 — rows 1-9 and 11-17 of the ownership table, the
owner's "use the checks that exist; never a second copy"): the drift
checker, ``standards check``, ``matrix --check`` and the counter run as
subprocesses with their exit codes and refusal prefixes surfaced verbatim
(indented under the failed surface). The script is stdlib-only apart from
the two ``uv run`` delegations, which need the project environment — the
same requirement ``make check-sdk-standards`` already makes. Steps 2-4
need an initialized submodule exactly as ``gates`` does (the delegated
commands refuse by name when it is not); the counter's scope set adds
``sdk`` only when the submodule tree is present. NOT OFFLINE (the fold's
LOW-4 correction of the design §4 claim "every delegated check is
offline"): step 1 resolves TAG pins against the SDK remote over
``git ls-remote`` — an unreadable remote reads INDETERMINATE (the
checker's exit 2) and the preflight reds on that step; SHA pins decide
locally, offline.

WHAT THIS SCRIPT DOES NOT CATCH (G4): anything its delegated commands do
not catch — the counter's documented assembly-miss classes, CI-only
surfaces (runner setup, ``--locked`` syncs), and the merge-result gap
(design row 18, deferral D1) all keep their existing owners. The register
verifies only its DECLARED sites: a NEW file with wrong values plus a
``--refresh-docs-baseline`` blessing still passes — a new claim site gets
a row or is a defect (design risk 2; D2's trigger is the tripwire).

Exit status: 0 when every surface holds, 1 otherwise. ``--claims-only``
runs the register alone (the CI arm — no environment, no submodule);
``--root <dir>`` redirects the register's tree (the test arm) and is
refused without ``--claims-only`` because the delegated steps anchor on
this checkout and cannot be redirected.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = "standards/standards-manifest.json"
CLAIMS_SURFACE = "docs version claims"

# The multi-standard Baseline sentences share one row shape: the site's
# minimal stable token (design §3 — `Baseline:**`, `current project
# baseline`, ``docs/` retains``, `consolidates``), a bounded lazy gap that
# spans line wraps (development.md's sentence carries `execution 0.2.0` on
# its second line), then the standard's name and the captured literal.
# Anchors key on tokens, not whole sentences, so ASD-STE100 rewrites that
# preserve the claim tokens do not break rows; the 200-char bound keeps a
# dissolved claim from matching a distant, unrelated literal.


@dataclass(frozen=True)
class ClaimRow:
    """One declared docs claim site (the DECLARED_SURFACES shape of
    ``scripts/release_cut.py``, pointed at docs prose): the anchor's single
    capture group is the claimed literal; the expectation is DERIVED from
    the committed manifest, never carried in this row."""

    file: str
    anchor: str
    standard_id: str
    kind: str  # "active" | "served"


_OTDP_ACTIVE = r"Version (\d+\.\d+\.\d+) is active"
_OTDP_SERVED = r"version (\d+\.\d+\.\d+) remains served"

CLAIMS: tuple[ClaimRow, ...] = (
    # docs/develop-your-device.md — the quickstart's version sentence: the
    # 9b879cf8 site, both halves of it.
    ClaimRow("docs/develop-your-device.md", _OTDP_ACTIVE, "otdp", "active"),
    ClaimRow("docs/develop-your-device.md", _OTDP_SERVED, "otdp", "served"),
    # docs/device-developer-guide.md — the **Baseline:** line.
    ClaimRow(
        "docs/device-developer-guide.md",
        r"Baseline:\*\*[\s\S]{0,200}?OTDP (\d+\.\d+\.\d+)",
        "otdp",
        "active",
    ),
    ClaimRow(
        "docs/device-developer-guide.md",
        r"Baseline:\*\*[\s\S]{0,200}?registry (\d+\.\d+\.\d+)",
        "registry",
        "active",
    ),
    ClaimRow(
        "docs/device-developer-guide.md",
        r"Baseline:\*\*[\s\S]{0,200}?execution (\d+\.\d+\.\d+)",
        "execution",
        "active",
    ),
    ClaimRow(
        "docs/device-developer-guide.md",
        r"Baseline:\*\*[\s\S]{0,200}?interface (\d+\.\d+\.\d+)",
        "interface",
        "active",
    ),
    # docs/ai-device-reviewer.md — the review-baseline sentence.
    ClaimRow(
        "docs/ai-device-reviewer.md",
        r"current project baseline is[\s\S]{0,200}?OTDP (\d+\.\d+\.\d+)",
        "otdp",
        "active",
    ),
    ClaimRow(
        "docs/ai-device-reviewer.md",
        r"current project baseline is[\s\S]{0,200}?registry (\d+\.\d+\.\d+)",
        "registry",
        "active",
    ),
    ClaimRow(
        "docs/ai-device-reviewer.md",
        r"current project baseline is[\s\S]{0,200}?execution (\d+\.\d+\.\d+)",
        "execution",
        "active",
    ),
    ClaimRow(
        "docs/ai-device-reviewer.md",
        r"current project baseline is[\s\S]{0,200}?interface (\d+\.\d+\.\d+)",
        "interface",
        "active",
    ),
    # docs/development.md — the Documentation-baseline sentence (wraps
    # across two lines; the gap spans the wrap).
    ClaimRow(
        "docs/development.md",
        r"`docs/` retains[\s\S]{0,200}?OTDP (\d+\.\d+\.\d+)",
        "otdp",
        "active",
    ),
    ClaimRow(
        "docs/development.md",
        r"`docs/` retains[\s\S]{0,200}?registry (\d+\.\d+\.\d+)",
        "registry",
        "active",
    ),
    ClaimRow(
        "docs/development.md",
        r"`docs/` retains[\s\S]{0,200}?execution (\d+\.\d+\.\d+)",
        "execution",
        "active",
    ),
    ClaimRow(
        "docs/development.md",
        r"`docs/` retains[\s\S]{0,200}?interface (\d+\.\d+\.\d+)",
        "interface",
        "active",
    ),
    # docs/smart-test-gateway-architecture-v1.5.md — §21's consolidation
    # sentence.
    ClaimRow(
        "docs/smart-test-gateway-architecture-v1.5.md",
        r"consolidates[\s\S]{0,200}?OTDP (\d+\.\d+\.\d+)",
        "otdp",
        "active",
    ),
    ClaimRow(
        "docs/smart-test-gateway-architecture-v1.5.md",
        r"consolidates[\s\S]{0,200}?registry (\d+\.\d+\.\d+)",
        "registry",
        "active",
    ),
    ClaimRow(
        "docs/smart-test-gateway-architecture-v1.5.md",
        r"consolidates[\s\S]{0,200}?execution (\d+\.\d+\.\d+)",
        "execution",
        "active",
    ),
    ClaimRow(
        "docs/smart-test-gateway-architecture-v1.5.md",
        r"consolidates[\s\S]{0,200}?interface (\d+\.\d+\.\d+)",
        "interface",
        "active",
    ),
)

_PLAIN_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_POLICY_CLAUSE = re.compile(r"^(>=|<=|==|!=|>|<)\s*(\d+\.\d+\.\d+)$")


class ClaimCheckError(Exception):
    """The register's inputs cannot be read or parsed — a refusal, never a
    guess (the counter's StandardsDrift / count-failed posture)."""


def _version_tuple(value: str) -> tuple[int, ...]:
    if not _PLAIN_VERSION.match(value):
        raise ClaimCheckError(
            f"docs_claim_check_failed: {value!r} is not a plain X.Y.Z version — "
            "the register derives plain versions only"
        )
    return tuple(int(part) for part in value.split("."))


def _retained(policy_entry: dict[str, Any], version: str) -> tuple[bool, str]:
    """(retained, why-not) for one version against a dependency-policy
    entry: in range, not yanked, not retired — the same manifest file the
    counter pins its standard ids from."""
    claimed = _version_tuple(version)
    range_text = str(policy_entry.get("range", ""))
    for clause in range_text.split(","):
        match = _POLICY_CLAUSE.match(clause.strip())
        if match is None:
            raise ClaimCheckError(
                f"docs_claim_check_failed: policy range clause {clause.strip()!r} "
                "does not parse (op + X.Y.Z expected)"
            )
        operator, bound = match.group(1), _version_tuple(match.group(2))
        holds = {
            ">=": claimed >= bound,
            "<=": claimed <= bound,
            "==": claimed == bound,
            "!=": claimed != bound,
            ">": claimed > bound,
            "<": claimed < bound,
        }[operator]
        if not holds:
            return False, f"outside the retained range {range_text}"
    yanked = policy_entry.get("yanked") or {}
    if version in yanked:
        return False, "yanked by the dependency policy"
    retired = policy_entry.get("retired") or ()
    if version in retired:
        return False, "retired by the dependency policy"
    return True, ""


def check_claims(root: Path) -> tuple[int, int, list[str]]:
    """(rows_total, rows_verified, refusals) for the register over one tree.

    A row that cannot even be evaluated (anchor lost, manifest entry
    absent) is a refusal, never a skip: the denominator is the register,
    and nothing leaves it silently.
    """
    try:
        manifest = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ClaimCheckError(
            f"docs_claim_check_failed: {MANIFEST_PATH} unreadable ({exc})"
        ) from exc
    except ValueError as exc:  # json.JSONDecodeError subclasses ValueError
        raise ClaimCheckError(
            f"docs_claim_check_failed: {MANIFEST_PATH} is not valid JSON ({exc})"
        ) from exc
    entries = manifest.get("standards")
    if not isinstance(entries, list):
        raise ClaimCheckError(
            f"docs_claim_check_failed: {MANIFEST_PATH} carries no standards list"
        )
    active = {
        str(entry["id"]): str(entry["version"])
        for entry in entries
        if isinstance(entry, dict) and "id" in entry and "version" in entry
    }
    statuses = {
        str(entry["id"]): str(entry.get("status", ""))
        for entry in entries
        if isinstance(entry, dict) and "id" in entry
    }
    policy = manifest.get("dependency_policy")
    policy_standards = policy.get("standards") if isinstance(policy, dict) else None
    if not isinstance(policy_standards, dict):
        policy_standards = {}

    texts: dict[str, str] = {}
    refusals: list[str] = []
    verified = 0
    for row in CLAIMS:
        if row.file not in texts:
            try:
                texts[row.file] = (root / row.file).read_text(encoding="utf-8")
            except OSError:
                texts[row.file] = ""
        matches = list(re.finditer(row.anchor, texts[row.file])) if texts[row.file] else []
        if not matches:
            refusals.append(
                f"docs_claim_anchor_lost: {row.file} ({row.standard_id} {row.kind} "
                "row) — the anchor moved; re-anchor the register row (a moved "
                "claim site is a reviewable edit, never a silent pass)"
            )
            continue
        if len(matches) > 1:
            # The anchor-hijack guard (fold MED-1/L1): first-match semantics
            # let a decoy sentence above the declared site launder the row —
            # the decoy's TRUE literal verified while the staled real claim
            # went unchecked. An anchor is a declaration of exactly one site;
            # two matches is a register/ prose disagreement, refused with
            # every site named so the re-anchor is a reviewable edit.
            sites = ", ".join(
                str(texts[row.file].count("\n", 0, match.start(1)) + 1)
                for match in matches
            )
            refusals.append(
                f"docs_claim_anchor_ambiguous: {row.file} ({row.standard_id} "
                f"{row.kind} row) — the anchor matches {len(matches)} sites "
                f"(lines {sites}); re-anchor the row on a token unique to the "
                "declared site (a claim laundered by a lookalike sentence is "
                "the anchor-hijack class; a moved claim site is a reviewable "
                "edit, never a silent pass)"
            )
            continue
        match = matches[0]
        claimed = match.group(1)
        line = texts[row.file].count("\n", 0, match.start(1)) + 1
        expected = active.get(row.standard_id)
        if expected is None:
            refusals.append(
                f"docs_claim_check_failed: the manifest carries no "
                f"{row.standard_id} entry — re-derive this register row"
            )
            continue
        entry_status = statuses.get(row.standard_id, "")
        if entry_status != "stable":
            # The status guard (governor M1): the derivation reads the
            # manifest's status, not the version alone — a standard
            # deprecated AT THE SAME VERSION would otherwise leave every
            # is-active row green (a version-only map cannot see it).
            shown = entry_status if entry_status else "absent"
            refusals.append(
                f"docs_claim_status_nonstable: {row.file}:{line} asserts "
                f"{row.standard_id} whose manifest status is {shown!r}, not "
                "'stable' — an active/served claim against a non-stable "
                "standard is a stale-claim class; sweep it in-arc"
            )
            continue
        if row.kind == "active":
            if claimed != expected:
                refusals.append(
                    f"docs_claim_stale: {row.file}:{line} claims "
                    f"{row.standard_id} {claimed} active, {MANIFEST_PATH} says "
                    f"{expected} — sweep the claim in-arc"
                )
                continue
        elif row.kind == "served":
            entry = policy_standards.get(row.standard_id)
            if not isinstance(entry, dict):
                refusals.append(
                    f"docs_claim_check_failed: dependency_policy.standards "
                    f"carries no {row.standard_id} entry"
                )
                continue
            retained, why_not = _retained(entry, claimed)
            if not retained:
                refusals.append(
                    f"docs_claim_stale: {row.file}:{line} claims "
                    f"{row.standard_id} {claimed} served, {MANIFEST_PATH} "
                    f"dependency policy does not retain it ({why_not}) — sweep "
                    "the claim in-arc"
                )
                continue
        else:
            refusals.append(
                f"docs_claim_check_failed: register row kind {row.kind!r} is "
                "not one of active/served"
            )
            continue
        verified += 1
    return len(CLAIMS), verified, refusals


def _delegated_steps(root: Path) -> list[tuple[str, list[str]]]:
    """(surface name, argv) for the four delegated commands (§4's table).
    The counter's scope set adds ``sdk`` only when the submodule tree is
    present; an absent tree is never requested (the counter would name it
    ``sdk_tree_absent:`` — the local, submodule-deinitialized convention)."""
    scopes = "gateway,plugins,docs,scripts"
    if (root / "packages/sdk/src/benchweave_sdk").is_dir():
        scopes += ",sdk"
    return [
        (
            "packages/sdk pointer pin ↔ gitlink (drift checker)",
            ["python3", "scripts/check_sdk_submodule_drift.py"],
        ),
        (
            "sdk mirror/anchor/served-set/policy/plugin-lock (standards check)",
            ["uv", "run", "python", "-m", "benchweave.standards", "check"],
        ),
        (
            "compatibility-matrix render (matrix --check)",
            ["uv", "run", "python", "-m", "benchweave.standards", "matrix", "--check"],
        ),
        (
            "version literals, per scope (counter)",
            [
                "uv",
                "run",
                "python",
                "scripts/standards/count_version_literals.py",
                "--scope",
                scopes,
            ],
        ),
    ]


def _stepOutcome(
    name: str, thunk: Callable[[], tuple[bool, list[str]]]
) -> tuple[bool, str, list[str]]:
    """Run one surface's check; (ok, surface name, refusal lines)."""
    try:
        ok, lines = thunk()
    except Exception as exc:  # a crashed step is a refusal, never a traceback
        return False, name, [f"train_preflight_step_failed: {name}: {exc}"]
    return ok, name, lines


def print_row(surface: str, ok: bool, lines: list[str]) -> None:
    """One surface's report row (the MED-3 seam): `[ok]`/`[UNMOVED]` plus
    the lines that belong under it. On green, a step's single plain line
    rides as the row's detail suffix and `::`-prefixed ANNOTATION lines
    forward indented — never swallowed. The pairing-pending
    `::warning::` is the one green-path signal the release-family walk
    reads at exactly the moment the preflight runs; the delegated checker
    prints it and exits 0, and this orchestrator must not be the place it
    disappears. On refusal every line forwards indented, `::` included."""
    if ok:
        plain = [line for line in lines if not line.startswith("::")]
        annotations = [line for line in lines if line.startswith("::")]
        detail = f" — {plain[0]}" if len(plain) == 1 else ""
        print(f"[ok] {surface}{detail}")
        for line in annotations:
            print(f"  {line}")
        return
    print(f"[UNMOVED] {surface}")
    for line in lines:
        print(f"  {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--claims-only",
        action="store_true",
        help="run the docs claim register alone (the CI arm — no project "
        "environment, no submodule)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="redirect the claim register's tree root (the test arm); "
        "refused without --claims-only — the delegated steps anchor on "
        "this checkout",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="with --claims-only: print the register's file set, row count and "
        "the check's verdict as JSON (the check runs — a stale tree exits 1)",
    )
    arguments = parser.parse_args(argv)
    if arguments.root is not None and not arguments.claims_only:
        parser.error("--root redirects the claim register only; use it with --claims-only")
    root = Path(arguments.root).resolve() if arguments.root is not None else REPO_ROOT

    steps: list[tuple[str, Callable[[], tuple[bool, list[str]]]]] = []
    if not arguments.claims_only:

        def delegated(name: str, argv_delegated: list[str]) -> Callable[[], tuple[bool, list[str]]]:
            def run() -> tuple[bool, list[str]]:
                # a fixed repo-local command (the scripts/** S603 posture)
                completed = subprocess.run(
                    argv_delegated,
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                lines = [
                    line
                    for stream in (completed.stdout, completed.stderr)
                    for line in stream.splitlines()
                    if line.strip()
                ]
                return completed.returncode == 0, lines

            return run

        for name, argv_delegated in _delegated_steps(REPO_ROOT):
            steps.append((name, delegated(name, argv_delegated)))

    def claims() -> tuple[bool, list[str]]:
        try:
            total, verified, refusals = check_claims(root)
        except ClaimCheckError as exc:
            return False, [str(exc)]
        if verified == total:
            return True, [f"{verified}/{total} rows verified against {MANIFEST_PATH}"]
        return False, refusals

    steps.append((CLAIMS_SURFACE, claims))

    if arguments.json:
        if not arguments.claims_only:
            parser.error("--json reports the claim register; use it with --claims-only")
        files = sorted({row.file for row in CLAIMS})
        # The JSON arm performs the check it reports on (LOW-6): a
        # reporting format is not a second verdict path, and it must
        # never exit 0 over a stale tree without having read it.
        try:
            total, verified, refusals = check_claims(root)
        except ClaimCheckError as exc:
            print(
                json.dumps(
                    {"files": files, "rows": len(CLAIMS), "verified": 0, "refusals": [str(exc)]}
                )
            )
            return 1
        print(
            json.dumps(
                {"files": files, "rows": total, "verified": verified, "refusals": refusals}
            )
        )
        return 0 if verified == total else 1

    checked = 0
    unmoved = 0
    for name, thunk in steps:
        ok, surface, lines = _stepOutcome(name, thunk)
        checked += 1
        if ok:
            print_row(surface, True, lines)
            continue
        unmoved += 1
        print_row(surface, False, lines)
    print(f"train-preflight: {checked} surfaces checked, {unmoved} unmoved")
    return 0 if unmoved == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
