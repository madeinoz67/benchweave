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
- ``plugins``: every ``*.py`` under ``plugins/`` with no ``tests``
  component and no environment component (issue #269 3.1: a plugin's
  code is gated wherever it lays out its package — the ``src/``
  requirement is gone; the fold row 8 ``tests/`` rule is unchanged, and
  a plugin shipping a ``tests`` subpackage inside its distributed tree
  stays excluded — the named residual). Census 15 (the two dps150 script
  files joined: zero literals in either).
- Environments are detected BY MARKER, not by name (issue #269 3.2): a
  directory is a Python environment iff it carries ``pyvenv.cfg``;
  ``node_modules``/``site-packages`` stay name-based (no marker exists —
  a named residual). A directory merely NAMED ``venv``/``.venv`` now
  SCANS; an environment whose marker was deleted scans as third-party
  bytes and FAILS the gate loudly (disposition = a named path exclusion)
  — never a silent pass. The former name-set filter is superseded by the
  marker rule (measured zero census change today: no environment
  directory exists in any gated tree).
- ``sdk``: ``packages/sdk/src/benchweave_sdk/`` (paths relativize to
  ``packages/sdk/`` so register rows are checkout-independent). An absent
  tree for a REQUESTED scope is a refusal (``sdk_tree_absent:``, exit 1),
  never a silent skip — the primary checkout keeps the submodule
  deinitialized by convention; local runs use
  ``--scope gateway,plugins,docs,scripts``; every CI lane that runs the default
  checks out submodules recursively.
- ``docs`` (VR-24, EXACT-CONTENT RATCHET): a prose scan over every
  ``.md`` under ``docs/`` (subtrees included — acceptance, devices,
  evidence), the plugin READMEs, and ``user_guide/**`` the day that tree
  appears — EXCLUDING, by the named constants below (never silently):
  ``docs/internal/``, ``docs/implementation-planning/`` and
  ``docs/superpowers/`` (internal and historical records whose frozen
  version citations are the point) and ``docs/compatibility-matrix.md``
  (machine-rendered; CON-12's own gate owns it). The gate refuses any
  scanned literal whose per-file count DIFFERS from the committed snapshot
  (``scripts/standards/docs-literal-baseline.json``) in EITHER direction —
  growth AND shrinkage refuse; only an explicit ``--refresh-docs-baseline``
  (whose diff is the review surface) moves the bound, and the scanned-file
  census is checked in-gate the same way. The zero end-state for prose
  rides the render-from-the-lock work D4/18(m) already own (deferral Z2).
- ``scripts`` (issue #269 §2): every ``*.py`` under ``scripts/`` with the
  environment filter applied — EXCLUDING the counter ITSELF by the named
  constant below (the register's ``expected_values`` tuples ARE the
  gate's own data and are literals by construction — the same class as
  the docs snapshot JSON, which no AST scope scans). The three policy
  facts are DERIVED (the adc control's two pins from the committed
  manifest; the docs site's corpus path from the active family); the
  twenty authored fixture/self-test values are REGISTERED with value
  pins. Census pinned at 16 files (17 ``.py`` minus the self-exempted
  counter).
- ``all``: the five scopes (the default).

THE REGISTER — the exemption list with teeth (#221 §1.3): each entry names
a file, the reason it is authored data rather than a derivation site, and
the EXACT number of literals it may carry. A new literal inside a
registered file fails the gate until the register row is edited — a
visible editorial diff. This is the register's anti-laundering defense
(design risk 1): the register cannot become a laundering list without a
reviewable register edit. Authored-data rows additionally pin the literal
VALUES (``expected_values``): a semantics-changing substitution inside a
registered file fails even at unchanged cardinality. The corpus-owned
``contracts.py`` rows carry no value pin because the copies are
digest-pinned whole (``tests/sdk/test_presentation_packaging.py``).

DENOMINATOR BOUNDARY (G1's honest scope, fold row 13; issue #269 §2
shrinks it): the gated trees are gateway ``src/benchweave/``, the SDK's
``src/benchweave_sdk/``, in-tree plugins (flat rule — any ``.py`` under
``plugins/`` outside ``tests/`` and environments), ``docs/`` (ratchet),
and ``scripts/`` (the adc control's two policy pins DERIVED from the
committed manifest — the move-to-equals-active equivalence is a theorem
of the policy shape whose failure mode is a loud control failure — and
the docs site's corpus path DERIVED from the active family; twenty
authored fixture/self-test values REGISTERED with value pins).
``tests/`` and ``.github/`` are OUTSIDE the gates (tests carry
legitimate fixture literals; assembly there equally so) — named so the
denominators cannot silently move.

WHAT THE MATCHER DOES NOT CATCH (G4; the fold-wave residual, REGENERABLE
from the allowlist — issue #269 fold wave row 3): the fold evaluator's
allowlist is exactly — ``Constant``; ``JoinedStr`` whose
``FormattedValue``s carry no conversion and no format-spec; ``BinOp``
``+`` on two folded strings, ``*`` string×int, ``%`` with a folded string
left side; ``List``/``Tuple`` displays; attribute calls ``.join`` (one
literal list/tuple of str), ``.format`` (positional args only — no
kwargs, no format-spec or conversion in the template), ``.decode`` (no
arguments); name calls ``chr(i)``/``str(x)`` (one argument, unshadowed at
module level). EVERY OTHER input class is a documented miss, and the
classes are named: format-specs and conversions; ``.format`` kwargs;
``%-with-dict``; decode with argument(s) (only the no-argument form
folds); conditional-expression arms (an ``IfExp`` anywhere in the
expression blocks the fold around it); starred format arguments;
``os.path.join`` and every other stdlib string constructor (outside the
allowlist — deferral D-3); folds bounded out by the caps (fold
depth > 24, folded length > 4096) — a bounded-out fold is
indistinguishable from dynamic assembly, the same disclosure class; and
dynamic (non-literal) input — a variable, parameter, function result,
comprehension, or
a value read from data, environment, or configuration — where catching
needs taint tracking, still deliberately not attempted (deferral D-1).
One scope residual on the shadow guard: the ``chr``/``str`` shadow
prepass sees module-level bindings; a function-local shadow is not seen
(named residual). The battery pins BOTH sides:
``tests/standards/assembly_shapes.py`` carries the twelve caught shapes
(refused), the documented-miss shapes (must pass), and the boundary table
(24 chained BinOps fold, 25 bounded out; a 4096-char fold is caught,
4097 bounded out).

Exit status: 0 when every requested scope holds (zero outside the
register, every register expectation true, the docs scope matches the
snapshot exactly), 1 otherwise (or on any parse failure — a count that
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

# >>> BEGIN SHARED COUNTER REGION (digest-pinned against the twin; issue #269 #4) >>>
STANDARD_IDS = ("otdp", "registry", "execution", "interface", "plugin-ui", "plugin-ui-preview")
PATTERN_A = re.compile(r"\b(?:" + "|".join(STANDARD_IDS) + r")/\d+\.\d+\.\d+")
PATTERN_BARE = re.compile(r"^\d+\.\d+\.\d+$")

# Environments are detected BY MARKER, not by name (issue #269 3.2): a
# directory is a Python environment iff it carries ``pyvenv.cfg`` — the
# marker every ``venv``/``virtualenv``/``uv venv`` writes. Project code in
# a directory merely NAMED ``venv`` or ``.venv`` is SCANNED — the
# collision case closed. ``node_modules``/``site-packages`` stay
# name-based: no marker file exists for either and the names are
# convention-owned by npm and pip's layout — a real package so named is
# unrepresentable in practice (NAMED RESIDUAL, not a silent one).
# Direction of failure stays loud: an environment whose marker was
# deleted scans as third-party bytes and its literals FAIL the gate
# (disposition = a named path exclusion) — never a silent pass.
ENVIRONMENT_MARKER = "pyvenv.cfg"
ENVIRONMENT_NAMED_COMPONENTS = frozenset({"node_modules", "site-packages"})

_is_environment_dir_cache: dict[Path, bool] = {}


def _is_environment_dir(directory: Path) -> bool:
    """True iff the directory is an environment BY MARKER AND LAYOUT: it
    carries ``pyvenv.cfg`` as a FILE and real environment structure
    (``bin/`` or ``lib/python*/``). The layout conjunct is the truth
    re-check (fold wave row 1): a planted marker — even a directory so
    named — without the layout does NOT exempt a tree; the tree scans and
    its literals refuse. Memoized: one stat set per directory under a
    scan root, cached."""
    cached = _is_environment_dir_cache.get(directory)
    if cached is None:
        marker = directory / ENVIRONMENT_MARKER
        cached = marker.is_file() and (
            (directory / "bin").is_dir() or any(directory.glob("lib/python*/"))
        )
        _is_environment_dir_cache[directory] = cached
    return cached


def _outside_environment(scan_root: Path, relative_parts: tuple[str, ...]) -> bool:
    """True when no directory on the relative path is a Python environment
    (by the ``pyvenv.cfg`` marker) and no component is a named environment
    component. The parts are relative to ``scan_root`` — absolute parts
    would stat every ancestor directory of the checkout."""
    if any(component in ENVIRONMENT_NAMED_COMPONENTS for component in relative_parts):
        return False
    return not any(
        _is_environment_dir(scan_root.joinpath(*relative_parts[: index + 1]))
        for index in range(len(relative_parts) - 1)
    )


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


# --- constant-folding assembly detection (issue #269, design §1.1) ---------
# Bounds: a fold attempt exceeding either is UNFOLDABLE (an honest miss,
# never an error).
FOLD_MAX_DEPTH = 24
FOLD_MAX_LENGTH = 4096


class _Unfoldable(Exception):
    """The evaluator's universal miss: this expression is not constant-only."""


def _shadowed_builtin_names(tree: ast.Module) -> frozenset[str]:
    """Module-level names binding ``chr``/``str`` — a module that shadows a
    builtin must never have its calls folded AS the builtin (a local
    ``def chr`` returning something else would fold lies)."""
    shadowed: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if node.name in ("chr", "str"):
                shadowed.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("chr", "str"):
                    shadowed.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id in ("chr", "str"):
                shadowed.add(node.target.id)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                if bound in ("chr", "str"):
                    shadowed.add(bound)
    return frozenset(shadowed)


def _folded_string(value: object) -> str:
    """The one choke point a folded str passes through: type-checked and
    length-bounded (a longer assembly is pathological — unfoldable)."""
    if not isinstance(value, str):
        raise _Unfoldable
    if len(value) > FOLD_MAX_LENGTH:
        raise _Unfoldable
    return value


def _stringify(value: object) -> str:
    """The f-string/``str()`` conversion over folded values (design §1.1:
    ``int`` → ``"2"``); every other type is unfoldable, not guessed."""
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    raise _Unfoldable


def _fold_expression(node: ast.expr, shadowed: frozenset[str], depth: int = 0) -> object:
    """Fold a constant-only expression to its value, or raise _Unfoldable.

    The allowlist, exactly (design §1.1): constants; f-strings (no
    conversion, no format-spec); ``+`` on two folded strings, ``*``
    string×int (Python's own repetition semantics), ``%`` with a folded
    string left side — the operation APPLIED with Python's own ``%``, never
    re-implemented; ``sep.join(<literal list/tuple of str>)``,
    ``fmt.format(*folded)`` (kwargs unfoldable), ``bytes.decode()``;
    ``chr(i)``/``str(x)`` unless the module shadows the name; list/tuple
    displays fold to list/tuple — the TUPLE rule is load-bearing: ``%``
    accepts only a real tuple, so folding tuples to lists would silently
    unfold every ``%``-tuple shape (battery S5). Every failure is a raise:
    the caller treats ANY exception as an honest miss.
    """
    if depth > FOLD_MAX_DEPTH:
        raise _Unfoldable
    if isinstance(node, ast.Constant):
        if node.value is None or isinstance(node.value, str | int | float | bytes):
            return node.value
        raise _Unfoldable
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(_folded_string(value.value))
            elif isinstance(value, ast.FormattedValue):
                if value.conversion != -1 or value.format_spec is not None:
                    raise _Unfoldable
                parts.append(_stringify(_fold_expression(value.value, shadowed, depth + 1)))
            else:
                raise _Unfoldable
        return _folded_string("".join(parts))
    if isinstance(node, ast.BinOp):
        left = _fold_expression(node.left, shadowed, depth + 1)
        if isinstance(node.op, ast.Add):
            right = _folded_string(_fold_expression(node.right, shadowed, depth + 1))
            return _folded_string(_folded_string(left) + right)
        if isinstance(node.op, ast.Mult):
            right = _fold_expression(node.right, shadowed, depth + 1)
            if isinstance(left, str) and isinstance(right, int) and not isinstance(right, bool):
                return _folded_string(left * right)
            if isinstance(right, str) and isinstance(left, int) and not isinstance(left, bool):
                return _folded_string(right * left)
            raise _Unfoldable
        if isinstance(node.op, ast.Mod):
            template = _folded_string(left)
            operand = _fold_expression(node.right, shadowed, depth + 1)
            try:
                formatted = template % operand
            except Exception as exc:
                raise _Unfoldable from exc
            return _folded_string(formatted)
        raise _Unfoldable
    if isinstance(node, ast.List):
        return [_fold_expression(elt, shadowed, depth + 1) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_fold_expression(elt, shadowed, depth + 1) for elt in node.elts)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            if node.func.attr == "join" and len(node.args) == 1 and not node.keywords:
                separator = _folded_string(_fold_expression(receiver, shadowed, depth + 1))
                argument = node.args[0]
                if not isinstance(argument, ast.List | ast.Tuple):
                    raise _Unfoldable  # comprehensions/generators: unfoldable
                elements = [
                    _folded_string(_fold_expression(elt, shadowed, depth + 1))
                    for elt in argument.elts
                ]
                return _folded_string(separator.join(elements))
            if node.func.attr == "format" and not node.keywords:
                template = _folded_string(_fold_expression(receiver, shadowed, depth + 1))
                if "{" in template and re.search(r"{[^}]*[!:]", template):
                    # format-specs and conversions: documented miss
                    # (fold wave row 3) — Python's own .format would APPLY
                    # them; the allowlist stops at the positional form.
                    raise _Unfoldable
                arguments = [_fold_expression(arg, shadowed, depth + 1) for arg in node.args]
                try:
                    return _folded_string(template.format(*arguments))
                except Exception as exc:
                    raise _Unfoldable from exc
            if node.func.attr == "decode" and not node.args and not node.keywords:
                payload = _fold_expression(receiver, shadowed, depth + 1)
                if not isinstance(payload, bytes):
                    raise _Unfoldable
                return _folded_string(payload.decode())
            raise _Unfoldable
        if isinstance(node.func, ast.Name):
            if (
                node.func.id == "chr"
                and "chr" not in shadowed
                and len(node.args) == 1
                and not node.keywords
            ):
                code = _fold_expression(node.args[0], shadowed, depth + 1)
                if not isinstance(code, int) or isinstance(code, bool):
                    raise _Unfoldable
                try:
                    return _folded_string(chr(code))
                except ValueError as exc:
                    raise _Unfoldable from exc
            if (
                node.func.id == "str"
                and "str" not in shadowed
                and len(node.args) == 1
                and not node.keywords
            ):
                return _stringify(_fold_expression(node.args[0], shadowed, depth + 1))
        raise _Unfoldable
    raise _Unfoldable


def _fold_sites(tree: ast.Module, relative: str) -> list[dict[str, Any]]:
    """The assembly sites one file's folded expressions produce, outermost
    only: a folded match nested inside another folded match (by span
    containment) is dropped — the OUTER assembled expression is the
    reported site. Inner plain ``Constant`` fragments that independently
    match are NOT touched here (the textual walk owns them; a shape can
    contribute both sites — battery S6/S9)."""
    shadowed = _shadowed_builtin_names(tree)
    folded: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp | ast.JoinedStr | ast.Call | ast.List | ast.Tuple):
            continue
        try:
            value = _fold_expression(node, shadowed)
        except Exception:  # noqa: S112 — ANY raise is an honest miss (design §1.1)
            continue
        if not isinstance(value, str):
            continue  # list/tuple folds only feed nested folds
        kind = None
        if PATTERN_A.search(value):
            kind = "ASM-A"
        elif PATTERN_BARE.match(value.strip()):
            kind = "ASM-BARE"
        if kind is None:
            continue
        folded.append(
            {
                "file": relative,
                "line": node.lineno,
                "pattern": kind,
                "text": value[:80],
                "_box": (
                    node.lineno,
                    node.col_offset,
                    node.end_lineno if node.end_lineno is not None else node.lineno,
                    node.end_col_offset if node.end_col_offset is not None else node.col_offset,
                ),
            }
        )
    unique: dict[tuple[int, int, int, int], dict[str, Any]] = {}
    for row in folded:
        unique.setdefault(row["_box"], row)
    kept = [
        row
        for box, row in unique.items()
        if not any(
            other != box
            and other[0] <= box[0]
            and other[1] <= box[1]
            and other[2] >= box[2]
            and other[3] >= box[3]
            for other in unique
        )
    ]
    for row in kept:
        del row["_box"]
    return kept

# <<< END SHARED COUNTER REGION <<<


# The PROSE matcher (docs scope): three-component versions with the cheap
# widenings (fold row 7b) — an optional v/V prefix and a -dev/-rc/-alpha/
# -beta prerelease suffix — anchored so dotted quads stop counting: an IP
# fragment like ``127.0.0`` inside ``127.0.0.1`` is preceded by or followed
# by another dotted component and matches neither boundary rule. A
# sentence-final period survives (``(?!\.\d)`` only excludes a FOLLOWING
# dotted component).
PATTERN_DOCS = re.compile(r"(?<![\w.])(?:[vV])?\d+\.\d+\.\d+(?:-(?:dev|rc|alpha|beta)\d*)?(?!\.\d)")

# The docs scope's exclusion set — named constants with their reasons, so
# the scope cannot quietly shrink (#221 design risk 4):
#   internal/history trees: frozen version citations ARE their content;
#   compatibility-matrix: machine-rendered, CON-12's gate owns it.
DOCS_EXCLUDED_DIRS = ("docs/internal", "docs/implementation-planning", "docs/superpowers")
DOCS_EXCLUDED_FILES = ("docs/compatibility-matrix.md",)
DOCS_SNAPSHOT = Path(__file__).resolve().parent / "docs-literal-baseline.json"

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "sdk"

# The scripts scope's self-exemption (issue #269 §2.3): the counter
# exempts ITSELF — the register's ``expected_values`` tuples ARE the
# gate's own data and are literals by construction (the same class as the
# docs snapshot JSON, which no AST scope scans). Whole-file, by the #269
# design's Fork-3 call; line-scoped exemption was rejected as new
# machinery for a file whose every edit is already an editorial
# re-baseline by this docstring's own rule. RESIDUAL (named, #269 risk 2):
# a plant in this file's NON-shared region is self-exempt and
# parity-invisible — the review lane carries it, the same posture the
# definition-change rule already takes.
SCRIPTS_EXCLUDED_FILES = ("scripts/standards/count_version_literals.py",)

# The registered-exception register (VR-25 branch 2; #221 §1.3): scope ->
# display-relative path -> (reason, expected_sites, expected_values).
# expected_sites is the EXACT literal count the file may carry; a registered
# file's count must EQUAL it — a fourth site in presentation/contracts.py
# fails until D2's trigger is honestly met. expected_values (fold row 6)
# additionally pins the sorted BARE-literal VALUES for authored-data rows,
# so a semantics-changing substitution fails at unchanged cardinality; the
# corpus-owned contracts.py rows carry None there because the copies are
# digest-pinned whole by tests/sdk/test_presentation_packaging.py.
REGISTER: dict[str, dict[str, tuple[str, int, tuple[str, ...] | None]]] = {
    "gateway": {
        "src/benchweave/presentation/contracts.py": (
            "VR-25 branch 2 / D2: plugin-ui corpus-owned code, byte-identical "
            "to its SDK twin (tests/sdk/test_presentation_packaging.py pins "
            "the identity — digest-pinned, so no value pin here); motion: all "
            "THREE version-literal sites (the path-shaped SCHEMA_ROOT literal "
            "and the two bare contract_version consts) moved 0.2.0→0.3.0 with "
            "the digital_lanes bump (issue #244; three sites move, count "
            "unchanged) under the sanctioned narrow-range crossing — the "
            "bundle lists this live code row in every carried version's row, "
            "so single-serving is the only honest posture. The D2 reopen "
            "trigger this row named (the first plugin-ui bump after the arc) "
            "FIRED with this motion; D2 stays OPEN — narrower reopen "
            "conditions re-record in the #244 design record (D-1)",
            3,
            None,
        ),
    },
    "sdk": {
        "src/benchweave_sdk/standards/plugin-ui/contracts.py": (
            "D2 twin of the gateway's registered copy — the same corpus-owned "
            "code at plugin-ui 0.3.0 bytes (digest-pinned whole, so no value "
            "pin here); same reopen trigger",
            3,
            None,
        ),
        "src/benchweave_sdk/scaffold.py": (
            "authored example-template fields that are not standards "
            "references (descriptor_version, firmware version, adapter "
            "version, provenance revision); the otdp_version example IS "
            "derived (served.active_version) and stays outside this row",
            4,
            ("0.1.0", "0.1.0", "0.1.0", "1.0.0"),
        ),
        "src/benchweave_sdk/publishing.py": (
            "authored lane constants — the submission-manifest schema version "
            "stamped by the packager (MANIFEST_SCHEMA_VERSION), the fallback "
            "release version, and the descriptor-derived default otdp pin "
            "(issue #223 slice 1); mirrors the SDK twin's own register row",
            3,
            ("0.1.1", "0.0.0", "0.1.0"),
        ),
    },
    "plugins": {
        "plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.py": (
            "a plugin's own pin declaration is data, not a literal (VR-21's "
            "own sentence) — deriving dps150's pin from any served set would "
            "let gateway state rewrite the plugin's declaration",
            3,
            ("0.1.0", "0.2.0", "0.2.2"),
        ),
    },
    "docs": {},
    "scripts": {
        "scripts/architecture/check_closure.py": (
            "authored synthetic-fixture versions — the closure graph's "
            "invented module versions are test data, not standards "
            "references (issue #269 §2.2; the SDK scaffold row's register "
            "semantics)",
            4,
            ("1.0.0", "1.0.0", "1.0.0", "1.0.0"),
        ),
        "scripts/architecture/check_devices.py": (
            "authored synthetic probe — the identity-disagreement fixture's "
            "invented version is test data",
            1,
            ("2.0.0",),
        ),
        "scripts/architecture/check_interface.py": (
            "authored self-test payload — a synthetic clientInfo version in "
            "the interface self-test",
            1,
            ("0.1.0",),
        ),
        "scripts/architecture/check_registry.py": (
            "authored self-test payload — the review-block arm's 0.1.2 "
            "manifest-version mutation (issue #223 slice 1); the suite's "
            "corpus directory is manifest-derived, never a literal",
            1,
            ("0.1.2",),
        ),
        "scripts/registry/sign_release.py": (
            "authored lane constant — the recorded form's manifest version "
            "(0.1.2; the submission is the 0.1.1 shape), fixed by the "
            "publishing lane's corpus (issue #223; the status-document "
            "literal left with the lane-key signing it labeled, retired by "
            "the 2026-10-02 ruling)",
            1,
            ("0.1.2",),
        ),
        "scripts/registry/build_fixtures.py": (
            "authored fixture-package versions — the fixture packages' "
            "release version and directory names (deriving these from the "
            "schema consts is deferral D-2: it changes emitted fixture "
            "bytes on every bump; the lattice's motion is governed by its "
            "rebuild flow)",
            4,
            ("1.0.0", "1.0.0", "1.0.0", "1.0.0"),
        ),
        "scripts/registry/publish_dev.py": (
            "authored dev-iteration default sentinel (0.0.0 = no dev head)",
            1,
            ("0.0.0",),
        ),
        "scripts/registry/registry_common.py": (
            "authored fixture document data — the registry fixtures' "
            "document formats, compat lists and package versions "
            "(deriving from the schema consts is deferral D-2, same "
            "trigger as build_fixtures)",
            7,
            ("0.1.0", "0.1.0", "0.1.1", "0.1.1", "1.0.0", "1.0.0", "1.0.0"),
        ),
        "scripts/sdk_smoke.py": (
            "authored synthetic descriptor firmware — the scaffold row's "
            "own class: example-template fields, not standards references",
            2,
            ("1.0.0", "1.0.0"),
        ),
    },
}

ALL_SCOPES = ("gateway", "plugins", "sdk", "docs", "scripts")


class ScopeAbsent(Exception):
    """A requested scope's tree does not exist in this checkout."""


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
                "check it out, or pass --scope gateway,plugins,docs,scripts)"
            )
        return root, root, "src/benchweave_sdk/**/*.py"
    if scope == "docs":
        return REPO_ROOT, REPO_ROOT, "docs/*.md"
    if scope == "scripts":
        return REPO_ROOT, REPO_ROOT, "scripts/**/*.py"
    raise ValueError(f"unknown scope: {scope}")


def _in_scope(scope: str, scan_root: Path, relative_parts: tuple[str, ...]) -> bool:
    """The per-scope membership rule beyond the glob (named, never silent).

    Membership is judged on the parts of the path RELATIVE TO ITS SCAN
    ROOT — an absolute path's parts carry every ancestor directory of the
    checkout (a repo checked out under any ``.../src/`` directory — a
    common developer layout — would admit every file into the plugins
    scope and silently grow the denominator).
    """
    if not _outside_environment(scan_root, relative_parts):
        return False
    if scope == "plugins":
        # Flat-plugin rule (issue #269 3.1): a plugin's code is gated
        # WHEREVER it lays out its package — the ``src/`` requirement is
        # gone (census 13 -> 15: the two dps150 script files, zero
        # literals in either). The ``tests/`` exclusion is the fold row 8
        # rule, unchanged (a ``tests/src/`` path shape is a test tree
        # however it is laid out). RESIDUAL, named: a plugin shipping a
        # ``tests`` subpackage inside its distributed package tree is
        # excluded — the same residual as before this row.
        return "tests" not in relative_parts
    return True


def _docs_files() -> list[Path]:
    """The VR-24 class set: every .md under docs/ (subtrees included), the
    plugin READMEs, and user_guide if present.

    Exclusions are the named constants above — each carries its reason
    beside its definition, and the census test pins the resulting file set
    so a silently widened exclusion is a visible diff. The subtree walk
    (fold row 3) brings docs/acceptance, docs/devices and docs/evidence
    into the ratchet alongside the root files.
    """
    files: list[Path] = []
    for path in sorted((REPO_ROOT / "docs").rglob("*.md")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in DOCS_EXCLUDED_FILES:
            continue
        files.append(path)
    for path in sorted(REPO_ROOT.glob("plugins/**/README.md")):
        # A README is docs regardless of where the plugin keeps its code —
        # the environment filter is the only membership rule here (the
        # plugins scope's src-only rule governs *.py, not prose).
        if not _outside_environment(REPO_ROOT, path.relative_to(REPO_ROOT).parts):
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
        if not _in_scope(scope, display_root, relative_parts):
            continue
        relative = path.relative_to(display_root).as_posix()
        if relative in SCRIPTS_EXCLUDED_FILES:
            # The counter exempts ITSELF (the constant's comment carries
            # the reason and the named residual) — not scanned, not
            # counted: the census is 16, not 17.
            continue
        scanned += 1
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
        sites.extend(_fold_sites(tree, relative))
    sites.sort(key=lambda row: (row["file"], row["line"], row["pattern"]))
    return sites, scanned


def _snapshot_counts() -> dict[str, dict[str, int]]:
    """The committed docs snapshot as {file: {literal: count}}."""
    document = json.loads(DOCS_SNAPSHOT.read_text(encoding="utf-8"))
    return document["files"]


def _snapshot_file_count() -> int | None:
    """The snapshot's recorded scanned-file census (absent in hand-made
    snapshots; the census check skips when the key is missing)."""
    document = json.loads(DOCS_SNAPSHOT.read_text(encoding="utf-8"))
    value = document.get("file_count")
    return value if isinstance(value, int) else None


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


def _check_docs_ratchet(
    sites: list[dict[str, Any]], scanned: int
) -> list[str]:
    """Refuse any (file, literal) count that DIFFERS from the committed
    snapshot, in either direction (fold row 4): growth refuses because a new
    claim must be reviewed; SHRINKAGE refuses too — the snapshot is an
    exact-content bound, so deleting a literal is a content change that
    only an explicit ``--refresh-docs-baseline`` may bless (its diff is the
    review surface). The scanned-file census is checked in-gate the same
    way: a silently added or removed file refuses.
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
            if have != allowed:
                direction = "beyond" if have > allowed else "removed from"
                violations.append(
                    f"docs literal {direction} snapshot: {file_name}: {literal} "
                    f"(snapshot records {allowed}, found {have}) — refresh "
                    "with --refresh-docs-baseline if this change is intended"
                )
    for file_name in sorted(snapshot):
        if file_name not in observed:
            for literal in sorted(snapshot[file_name]):
                if snapshot[file_name][literal] > 0:
                    violations.append(
                        f"docs literal removed from snapshot: {file_name}: "
                        f"{literal} (snapshot records "
                        f"{snapshot[file_name][literal]}, found 0) — refresh "
                        "with --refresh-docs-baseline if this change is intended"
                    )
    expected_files = _snapshot_file_count()
    if expected_files is not None and scanned != expected_files:
        violations.append(
            f"docs census changed: snapshot records {expected_files} scanned "
            f"files, found {scanned} — refresh with --refresh-docs-baseline "
            "if this change is intended"
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
        reason, expected, expected_values = register[file_name]
        found_rows = by_file.get(file_name, [])
        found = len(found_rows)
        if found != expected:
            violations.append(
                f"register expectation failed: {file_name} expects {expected} "
                f"literals, found {found} ({reason})"
            )
        if expected_values is not None:
            # Fold row 6: pin the VALUES for authored-data rows — a
            # semantics-changing substitution fails at unchanged cardinality.
            found_values = sorted(row["text"] for row in found_rows)
            if found_values != sorted(expected_values):
                violations.append(
                    f"register value pin failed: {file_name} expects "
                    f"{sorted(expected_values)}, found {found_values} ({reason})"
                )
    if scope == "docs":
        violations.extend(_check_docs_ratchet(sites, scanned))

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


def _pin_standard_ids() -> None:
    """The committed standard-id set is the matcher's authority (fold row 5):
    ``STANDARD_IDS`` must equal the standards manifest's entry ids. A
    seventh standard (or a rename) would otherwise silently narrow Pattern
    A's coverage — the script refuses instead, and adding the id becomes a
    deliberate, reviewable edit to this file.
    """
    manifest = json.loads(
        (REPO_ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
    )
    manifest_ids = sorted(str(entry.get("id")) for entry in manifest.get("standards", []))
    if manifest_ids != sorted(STANDARD_IDS):
        raise StandardsDrift(
            f"standard_set_drift: the manifest declares {manifest_ids} but the "
            f"matcher pins {sorted(STANDARD_IDS)} — update STANDARD_IDS in this "
            "script in the same work as the manifest change"
        )


class StandardsDrift(Exception):
    """A committed authority disagrees with the matcher's pinned sets."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print per-site rows")
    parser.add_argument(
        "--scope",
        default="all",
        help="comma-separated scopes: gateway,plugins,sdk,docs,scripts (or all)",
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
        _pin_standard_ids()
        reports: dict[str, dict[str, Any]] = {}
        ok = True
        for scope in scopes:
            scope_ok, report = _check_scope(scope)
            reports[scope] = report
            ok = ok and scope_ok
    except ScopeAbsent as exc:
        print(f"sdk_tree_absent: {exc}", file=sys.stderr)
        return 1
    except StandardsDrift as exc:
        print(str(exc), file=sys.stderr)
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
