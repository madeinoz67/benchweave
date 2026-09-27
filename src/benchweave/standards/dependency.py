"""The plugin dependency resolver: intervals, classification, carriers (issue #216).

#203 slice 2 (design record §3.4, `.claude/deep-review/
2026-09-27-issue216-slice2-resolver-design.md`): a package's requirement is
authored data (``contracts/constraints.json``), its resolved pin is generated
(``contracts/lock.json``, the DPS-150 shape extended to v2), and the decision
between them is a deterministic, offline, pure function of committed bytes
plus the authored constraints (CON-14's resolution clauses — this slice makes
them true). Caret sugar is AUTHORING input, expanded at the CLI boundary and
refused wherever it is found stored; the dev clauses of CON-14 (content-
addressed dev pins, wheel refusal) ride slice 4.

Input kinds. The RESOLUTION — which version each standard resolves to — reads
committed data of exactly four kinds: the dependency-policy block in
``standards/standards-manifest.json``, the rows of
``standards/corpus-manifest.json``, ``standards/cross-constraints.json``, and
the package's ``contracts/{constraints,lock}.json``. Never git, never the
network, never a clock (A04). The lock WRITER additionally reads the resolved
OTDP version's committed directory bytes for the legacy otdp projection —
the descriptor schema's ``api_version`` const (the ``validate_identity``
derivation relocated to the pinned version, digest-verified against its
corpus row) and the top-level file map (the fetch-verify set, deliberately
not the corpus-row set) — disclosed as the design's §1.1 four-kinds sentence
resolved in favour of §1.3's explicit derivation; still committed bytes
only, so CON-14's purity clause holds.

Prefix vocabulary (deliberate drift from the SDK, design risk 3): the SDK's
``version_not_served:`` folds "never carried" into "not served"; this
resolver splits ``version_unknown:`` out per acceptance rule B4 — distinct
remediations (publish-or-widen vs re-pin). Slice 3's gateway admission
adopts the same three-way split so the vocabularies converge deliberately.

Refusal prefixes, each machine-matchable: ``constraint_syntax_unexpanded:``,
``constraint_document_invalid:``, ``lock_document_invalid:``,
``constraint_standard_unknown:``, ``constraint_unresolvable:``,
``version_shape_invalid:``, ``dev_pin_unsupported:``,
``retired_identifier:``, ``version_unknown:``, ``version_not_served:``,
``plugin_constraints_absent:``, ``plugin_lock_absent:``,
``plugin_lock_drift:``, ``cross_constraint_invalid:``,
``cross_constraint_unresolved:``, ``cross_constraint_violation:``,
``adapter_api_unresolved:``, ``lock_otdp_absent:``,
``version_directory_absent:``, ``corpus_file_unpinned:``,
``corpus_pin_mismatch:``. Every classification refusal carries the five
VR-37 fields inline: standard, pinned version, supported range, move-to,
migration-note pointer ("migration guidance pending" until slice 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest import DependencyPolicy


@dataclass(frozen=True)
class Interval:
    """An explicit half-open ``>=lower,<upper`` constraint interval."""

    lower: str
    upper: str

    def contains(self, version: str) -> bool:
        raise NotImplementedError(self.__class__.__qualname__)

    def text(self) -> str:
        raise NotImplementedError(self.__class__.__qualname__)


def expand_caret(value: str) -> Interval:
    """Expand caret authoring sugar per the 0.x table (refuses all else)."""
    raise NotImplementedError(expand_caret.__name__)


def parse_interval(value: object) -> Interval:
    """Parse an explicit interval; sugar and bad shapes refuse."""
    raise NotImplementedError(parse_interval.__name__)


@dataclass(frozen=True)
class PinClassification:
    """The outcome of classifying one pin against the policy block."""

    state: str
    warning: str | None


def classify_pin(
    policy: DependencyPolicy, root: Path, standard_id: str, version: str
) -> PinClassification:
    """Classify a pin: served, or yanked-with-warning; refusals raise."""
    raise NotImplementedError(classify_pin.__name__)


@dataclass(frozen=True)
class Constraints:
    """One package's authored constraints, parsed into intervals."""

    standards: dict[str, Interval]
    path: Path


def load_constraints(package: Path) -> Constraints:
    """Load and validate ``contracts/constraints.json``; fail closed."""
    raise NotImplementedError(load_constraints.__name__)


def apply_set(root: Path, package: Path, pairs: list[tuple[str, str]]) -> None:
    """Author constraints through the CLI boundary: expand sugar, never store it."""
    raise NotImplementedError(apply_set.__name__)


@dataclass(frozen=True)
class PriorLock:
    """The prior lock's projection: provenance plus one version per standard."""

    version: int
    repository: str
    revision: str
    rows: dict[str, str]


def load_prior_lock(package: Path) -> PriorLock | None:
    """Parse ``contracts/lock.json`` (v1 projection or v2 rows); None when absent."""
    raise NotImplementedError(load_prior_lock.__name__)


@dataclass(frozen=True)
class CrossConstraintRow:
    """One cross-standard constraint row (``standards/cross-constraints.json``)."""

    standard: str
    version: str
    requires: dict[str, str]
    evidence: str


def load_cross_constraints(root: Path) -> tuple[CrossConstraintRow, ...]:
    """Load the cross-constraints side table; fail closed on shape and retention."""
    raise NotImplementedError(load_cross_constraints.__name__)


@dataclass(frozen=True)
class Resolution:
    """A resolved lock document with its canonical bytes and warnings."""

    document: dict[str, Any]
    raw: bytes
    warnings: tuple[str, ...]


def resolve_package(
    root: Path, package: Path, *, precise: dict[str, str] | None = None
) -> Resolution:
    """Resolve constraints to a lock document (minimal motion; deterministic)."""
    raise NotImplementedError(resolve_package.__name__)


def row_digest(root: Path, standard_id: str, version: str) -> str:
    """The digest-of-digests over the corpus-manifest rows of one version."""
    raise NotImplementedError(row_digest.__name__)


def normalized_equal(path_a: Path, path_b: Path, version_a: str, version_b: str) -> bool:
    """Version-normalized subtree comparison (the B6 raw-digest control)."""
    raise NotImplementedError(normalized_equal.__name__)


def list_lines(root: Path) -> list[str]:
    """The ``standards list`` render: policy block + corpus rows, deterministic."""
    raise NotImplementedError(list_lines.__name__)
