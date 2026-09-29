#!/usr/bin/env python3
"""Count standards-version literals across the governed trees — ZERO-MODE.

Issue #203 slice 1 (design §3.7, acceptance A4): a committed script — the
gate's counter, not a hand count — enumerated version literals in ratchet
mode (the count could not rise; the baseline was committed beside this
script: 12 sites at merge base ``403c061``). Slice 7 (issue #221) flips the
ratchet to ZERO-MODE: per requested scope, the count of literals OUTSIDE
the register below must be 0, and every register row's expected site count
must hold exactly. The docstring's own rule still governs: changing the
definition re-baselines by editorial decision, not silently — this rewrite
is that decision, and the slice record is its review surface.

HISTORY (the honest-partial posture this script inherits): the PRD §1.5
hand count was 13 gateway sites at ``ef969af``; #201 re-versioned values
without removing any; the committed slice-1 definition counted the SAME 12
sites at ``ef969af`` and at ``403c061``, so the hand count's extra site was
one this definition classifies as prose — unnameable from committed
evidence, and never invented. The #221 design's §0 re-measured the SDK the
same way: the arc record's "17 SDK sites" hand count is superseded by this
definition's 22 at ``1b2cc74`` and 12 at the pin and the tip.

DEFINITION (committed; changing it re-baselines by editorial decision, not
silently):

- A **version literal** is a string constant in EXECUTABLE code — docstrings
  are excluded (the first string statement of a module, class, or function
  body). Comments are not code and never count.
- Pattern A: a string containing ``<standard-id>/<X.Y.Z>`` for one of the six
  governed standards ids — the path-shaped literal (``execution/0.2.0``).
- Pattern B: a string that IS a bare ``X.Y.Z`` (three-component pure semver),
  counted EVERYWHERE in executable code.
- The docs scope (below) is a PROSE scan: every three-component literal in
  the scanned markdown, not an AST walk.

SCOPES (#221 §1.3):

- ``gateway``: ``src/benchweave/`` — the slice-1 scope, unchanged.
- ``plugins``: every ``*.py`` under a ``plugins/**/src/**`` path, ignoring
  any path carrying a ``venv``/``.venv``/``node_modules``/``site-packages``
  component (defense in depth: a venv created inside ``src/`` makes
  zero-mode FAIL loudly, never silently pass). The dps150 test-tree
  literals and the stray venv bytes are outside the scope BY THIS NAMED
  RULE, never by silence.
- ``sdk``: ``packages/sdk/src/benchweave_sdk/`` (paths relativize to
  ``packages/sdk/`` so register rows are checkout-independent). An absent
  tree for a REQUESTED scope is a refusal (``sdk_tree_absent:``, exit 1),
  never a silent skip — the primary checkout keeps the submodule
  deinitialized by convention; local runs use
  ``--scope gateway,plugins,docs``; every CI lane that runs the default
  checks out submodules recursively.
- ``docs`` (VR-24, RATCHET mode): a prose scan over ``docs/*.md`` at the
  repo root, the plugin READMEs, and ``user_guide/**`` the day that tree
  appears — EXCLUDING, by the named constants below (never silently):
  ``docs/internal/``, ``docs/implementation-planning/`` and
  ``docs/superpowers/`` (internal and historical records whose frozen
  version citations are the point) and ``docs/compatibility-matrix.md``
  (machine-rendered; CON-12's own gate owns it). The gate refuses any
  three-component literal NOT in the committed snapshot
  (``scripts/standards/docs-literal-baseline.json``); removals only lower
  the count. Regenerate ONLY with ``--refresh-docs-baseline`` (the diff is
  the review surface). The zero end-state for prose rides the
  render-from-the-lock work D4/18(m) already own (deferral Z2).
- ``all``: the four scopes (the default).

THE REGISTER — the exemption list with teeth (#221 §1.3): each entry names
a file, the reason it is authored data rather than a derivation site, and
the EXACT number of literals it may carry. A new literal inside a
registered file fails the gate until the register row is edited — a
visible editorial diff. This is the register's anti-laundering defense
(design risk 1): the register cannot become a laundering list without a
reviewable register edit.

Exit status: 0 when every requested scope holds (zero outside the
register, every register expectation true, the docs scope adds no literal
beyond the snapshot), 1 otherwise (or on any parse failure — a count that
cannot be computed is a refusal, never a guess). ``--json`` prints per-site
rows for review — registered-file sites carry ``exempt: true`` and the
register reason; the display never hides what the gate forgives.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any

STANDARD_IDS = ("otdp", "registry", "execution", "interface", "plugin-ui", "plugin-ui-preview")
PATTERN_A = re.compile(r"\b(?:" + "|".join(STANDARD_IDS) + r")/\d+\.\d+\.\d+")
PATTERN_BARE = re.compile(r"^\d+\.\d+\.\d+$")
PATTERN_DOCS = re.compile(r"\d+\.\d+\.\d+")

# The docs scope's exclusion set — named constants with their reasons, so
# the scope cannot quietly shrink (#221 design risk 4):
#   internal/history trees: frozen version citations ARE their content;
#   compatibility-matrix: machine-rendered, CON-12's gate owns it.
DOCS_EXCLUDED_DIRS = ("docs/internal", "docs/implementation-planning", "docs/superpowers")
DOCS_EXCLUDED_FILES = ("docs/compatibility-matrix.md",)
DOCS_SNAPSHOT = Path(__file__).resolve().parent / "docs-literal-baseline.json"

# Environment components ignored in the plugins and docs scopes (§0.3 of
# the design: a stray environment inside a scanned tree must make zero-mode
# fail loudly if it ever lands in scope — the ignore exists so third-party
# bytes already in the tree do not gate the lane).
ENVIRONMENT_COMPONENTS = frozenset({"venv", ".venv", "node_modules", "site-packages"})

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "sdk"

# The registered-exception register (VR-25 branch 2; #221 §1.3): scope ->
# display-relative path -> (reason, expected_sites). A registered file's
# literal count must EQUAL expected_sites — a fourth site in
# presentation/contracts.py fails until D2's trigger is honestly met.
REGISTER: dict[str, dict[str, tuple[str, int]]] = {
    "gateway": {
        "src/benchweave/presentation/contracts.py": (
            "VR-25 branch 2 / D2: plugin-ui corpus-owned code, byte-identical "
            "to its SDK twin (tests/sdk/test_presentation_packaging.py pins "
            "the identity); motion = the D2 reopen trigger (the first "
            "plugin-ui bump after the arc, or the owner's F1 call)",
            3,
        ),
    },
    "sdk": {
        "src/benchweave_sdk/standards/plugin-ui/contracts.py": (
            "D2 twin of the gateway's registered copy — the same corpus-owned "
            "code at plugin-ui 0.2.0 bytes; same reopen trigger",
            3,
        ),
        "src/benchweave_sdk/scaffold.py": (
            "authored example-template fields that are not standards "
            "references (descriptor_version, firmware version, adapter "
            "version, provenance revision); the otdp_version example IS "
            "derived (served.active_version) and stays outside this row",
            4,
        ),
    },
    "plugins": {
        "plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.py": (
            "a plugin's own pin declaration is data, not a literal (VR-21's "
            "own sentence) — deriving dps150's pin from any served set would "
            "let gateway state rewrite the plugin's declaration",
            3,
        ),
    },
    "docs": {},
}

ALL_SCOPES = ("gateway", "plugins", "sdk", "docs")


class ScopeAbsent(Exception):
    """A requested scope's tree does not exist in this checkout."""


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


def scope_tree(scope: str) -> tuple[Path, Path, str]:
    """(scan_root, display_root, glob) for one scope.

    Display paths relativize per scope (gateway/plugins/docs to the repo
    root; sdk to ``packages/sdk/``) so register rows are
    checkout-independent. Raises :class:`ScopeAbsent` for a requested scope
    whose tree does not exist.
    """
    if scope == "gateway":
        return REPO_ROOT, REPO_ROOT, "src/benchweave/**/*.py"
    if scope == "plugins":
        return REPO_ROOT, REPO_ROOT, "plugins/**/*.py"
    if scope == "sdk":
        root = SDK_ROOT
        if not (root / "src/benchweave_sdk").is_dir():
            raise ScopeAbsent(
                "packages/sdk/src/benchweave_sdk (the submodule is absent — "
                "check it out, or pass --scope gateway,plugins,docs)"
            )
        return root, root, "src/benchweave_sdk/**/*.py"
    if scope == "docs":
        return REPO_ROOT, REPO_ROOT, "docs/*.md"
    raise ValueError(f"unknown scope: {scope}")


def _outside_environment(relative_parts: tuple[str, ...]) -> bool:
    """True when the relative path carries no environment component."""
    return not any(component in ENVIRONMENT_COMPONENTS for component in relative_parts)


def _in_scope(scope: str, relative_parts: tuple[str, ...]) -> bool:
    """The per-scope membership rule beyond the glob (named, never silent).

    Membership is judged on the parts of the path RELATIVE TO ITS SCAN
    ROOT — an absolute path's parts carry every ancestor directory of the
    checkout (this repo lives under ``~/Documents/src/``), which would
    admit every file into the plugins scope and silently grow the
    denominator.
    """
    if not _outside_environment(relative_parts):
        return False
    if scope == "plugins":
        return "src" in relative_parts  # plugins/**/src/** only: tests are out
    return True


def _docs_files() -> list[Path]:
    """The VR-24 class set: root docs, plugin READMEs, user_guide if present.

    Exclusions are the named constants above — each carries its reason
    beside its definition, and the census test pins the resulting file set
    so a silently widened exclusion is a visible diff.
    """
    files: list[Path] = []
    for path in sorted((REPO_ROOT / "docs").glob("*.md")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in DOCS_EXCLUDED_FILES:
            continue
        files.append(path)
    for path in sorted(REPO_ROOT.glob("plugins/**/README.md")):
        # A README is docs regardless of where the plugin keeps its code —
        # the environment filter is the only membership rule here (the
        # plugins scope's src-only rule governs *.py, not prose).
        if not _outside_environment(path.relative_to(REPO_ROOT).parts):
            continue
        files.append(path)
    user_guide = REPO_ROOT / "user_guide"
    if user_guide.is_dir():
        files.extend(sorted(user_guide.rglob("*.md")))
    kept: list[Path] = []
    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if any(rel.startswith(excluded + "/") for excluded in DOCS_EXCLUDED_DIRS):
            continue
        kept.append(path)
    return kept


def count_sites(source_root: Path, scope: str) -> tuple[list[dict[str, Any]], int]:
    """Every executable literal site in one scope, sorted for reproducibility.

    Returns (sites, scanned_file_count); the census rides the same walk so
    silent scope shrinkage is testable (#221 design risk 4).
    """
    scan_root, display_root, pattern = scope_tree(scope)
    sites: list[dict[str, Any]] = []
    scanned = 0
    for path in sorted(source_root.glob(pattern)) if scope != "docs" else _docs_files():
        relative_parts = path.relative_to(display_root).parts
        if not _in_scope(scope, relative_parts):
            continue
        scanned += 1
        relative = path.relative_to(display_root).as_posix()
        if scope == "docs":
            text = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), start=1):
                for match in PATTERN_DOCS.finditer(line):
                    sites.append(
                        {
                            "file": relative,
                            "line": line_number,
                            "pattern": "PROSE",
                            "text": match.group(0),
                        }
                    )
            continue
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
    sites.sort(key=lambda row: (row["file"], row["line"], row["pattern"]))
    return sites, scanned


def _snapshot_counts() -> dict[str, dict[str, int]]:
    """The committed docs snapshot as {file: {literal: count}}."""
    document = json.loads(DOCS_SNAPSHOT.read_text(encoding="utf-8"))
    return document["files"]


def _refresh_snapshot() -> dict[str, dict[str, int]]:
    scan_root, _display_root, _pattern = scope_tree("docs")
    sites, scanned = count_sites(scan_root, "docs")
    files: dict[str, dict[str, int]] = {}
    for row in sites:
        per_file = files.setdefault(row["file"], {})
        per_file[row["text"]] = per_file.get(row["text"], 0) + 1
    document = {
        "comment": (
            "generated by scripts/standards/count_version_literals.py "
            "--refresh-docs-baseline; do not hand-edit — the diff of a "
            "refresh is the review surface"
        ),
        "file_count": scanned,
        "files": {name: dict(sorted(rows.items())) for name, rows in sorted(files.items())},
    }
    DOCS_SNAPSHOT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def _check_docs_ratchet(sites: list[dict[str, Any]]) -> list[str]:
    """Refuse any (file, literal) occurrence beyond the committed snapshot.

    A literal the snapshot does not know refuses; a HIGHER count of a known
    literal refuses; removals only lower the count and pass. Keyed by
    (file, literal) counts, not lines, so unrelated edits do not churn the
    snapshot (the refresh diff stays a review surface, not noise).
    """
    snapshot = _snapshot_counts()
    observed: dict[str, dict[str, int]] = {}
    for row in sites:
        per_file = observed.setdefault(row["file"], {})
        per_file[row["text"]] = per_file.get(row["text"], 0) + 1
    violations: list[str] = []
    for file_name in sorted(observed):
        for literal in sorted(observed[file_name]):
            have = observed[file_name][literal]
            allowed = snapshot.get(file_name, {}).get(literal, 0)
            if have > allowed:
                violations.append(
                    f"docs literal beyond snapshot: {file_name}: {literal} "
                    f"(snapshot allows {allowed}, found {have})"
                )
    return violations


def _check_scope(scope: str) -> tuple[bool, dict[str, Any]]:
    """Zero-mode for one scope. Returns (ok, report)."""
    scan_root, _display_root, _pattern = scope_tree(scope)
    sites, scanned = count_sites(scan_root, scope)
    register = REGISTER[scope]
    by_file: dict[str, list[dict[str, Any]]] = {}
    for row in sites:
        by_file.setdefault(row["file"], []).append(row)

    violations: list[str] = []
    if scope == "docs":
        # The docs scope is the RATCHET scope: its gate is the committed
        # snapshot (below), never the register — the register applies to
        # executable code only, and an empty register must never read as
        # "everything is a violation" for a scope that is not gated by one.
        outside = []
    else:
        outside = [row for row in sites if row["file"] not in register]
        for row in outside:
            violations.append(
                f"unregistered literal: {row['file']}:{row['line']} [{row['pattern']}] "
                f"{row['text']} — derive it from its machine authority or register "
                "it with reason and expected_sites"
            )
    for file_name in sorted(register):
        reason, expected = register[file_name]
        found = len(by_file.get(file_name, []))
        if found != expected:
            violations.append(
                f"register expectation failed: {file_name} expects {expected} "
                f"literals, found {found} ({reason})"
            )
    if scope == "docs":
        violations.extend(_check_docs_ratchet(sites))

    for row in sites:
        entry = register.get(row["file"])
        row["exempt"] = entry is not None
        if entry is not None:
            row["reason"] = entry[0]

    report = {
        "scanned": scanned,
        "count": len(sites),
        "outside": len(outside),
        "ok": not violations,
        "violations": violations,
        "sites": sites,
    }
    return not violations, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print per-site rows")
    parser.add_argument(
        "--scope",
        default="all",
        help="comma-separated scopes: gateway,plugins,sdk,docs (or all)",
    )
    parser.add_argument(
        "--refresh-docs-baseline",
        action="store_true",
        help="regenerate the docs snapshot from the current tree (the diff is "
        "the review surface — never a silent gate input)",
    )
    arguments = parser.parse_args(argv)

    scopes = list(ALL_SCOPES) if arguments.scope == "all" else arguments.scope.split(",")
    if arguments.refresh_docs_baseline and arguments.scope == "all":
        scopes = ["docs"]  # the refresh flag implies the docs scope
    for scope in scopes:
        if scope not in ALL_SCOPES:
            parser.error(f"unknown scope: {scope}")

    if arguments.refresh_docs_baseline:
        if scopes != ["docs"]:
            parser.error("--refresh-docs-baseline runs the docs scope alone")
        document = _refresh_snapshot()
        total = sum(sum(rows.values()) for rows in document["files"].values())
        print(
            f"docs snapshot refreshed: {document['file_count']} files, "
            f"{total} literals, {len(document['files'])} files carry literals"
        )
        return 0

    try:
        reports: dict[str, dict[str, Any]] = {}
        ok = True
        for scope in scopes:
            scope_ok, report = _check_scope(scope)
            reports[scope] = report
            ok = ok and scope_ok
    except ScopeAbsent as exc:
        print(f"sdk_tree_absent: {exc}", file=sys.stderr)
        return 1
    except (OSError, SyntaxError) as exc:
        print(f"version_literal_count_failed: {exc}", file=sys.stderr)
        return 1

    if arguments.json:
        print(
            json.dumps(
                {"mode": "zero", "ok": ok, "scopes": {name: reports[name] for name in scopes}},
                indent=2,
            )
        )
        return 0 if ok else 1

    for scope in scopes:
        report = reports[scope]
        verdict = "ok" if report["ok"] else "FAILED"
        print(
            f"{scope}: {report['outside']} outside register "
            f"({report['count']} sites, {report['scanned']} files scanned, {verdict})"
        )
        for violation in report["violations"]:
            print(f"  {violation}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
