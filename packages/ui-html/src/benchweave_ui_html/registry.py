"""The fixture registry and the REQUIRE_ARTIFACT enforcement constant.

Design record §2, the RED mechanism: fail-closed on unknown or unregistered —
never pass-by-default. An unregistered row-id fails with
``no canonical artifact for <row-id>``; an unknown kind fails with
``unimplemented row-kind: <kind>``. No skip, no xfail, no empty-pass.

``REQUIRE_ARTIFACT`` is a plain module constant and the ONLY switch: nothing
reads an ini option, an environment variable or a marker to flip it, and the
meta-acceptance pins that (the toggle control flips the module attribute
in-process; the env arm proves no environment variable reaches it).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from benchweave_ui_html.grammar import Row

# The only switch. The harness reads this module attribute at call time, so an
# in-process flip (the mechanism-toggle control) takes effect — nothing else
# can turn the gate off where it is live.
REQUIRE_ARTIFACT: bool = True

# Artifact kinds (design record §2), plus sequence_partial for §E.2.2 — see
# manifest.py's docstring for the disclosed design-gap closure.
KNOWN_KINDS: frozenset[str] = frozenset(
    {
        "component_render",
        "label_render",
        "refusal_render",
        "token_pair",
        "token_value",
        "slot_value",
        "hint_row",
        "severity_row",
        "mode_row",
        "state_row",
        "triad_row",
        "icon_partial",
        "sequence_partial",
        "rule_proof",
    }
)


class Artifact(Protocol):
    """A row's canonical artifact: ``satisfies(row)`` returns the unsatisfied
    item descriptions; an empty list means the row is green."""

    kind: str

    def satisfies(self, row: Row) -> list[str]: ...


class ArtifactRegistry:
    """Maps row-id (``<table-slug>::<key-cell>``) to that row's canonical
    artifact. Duplicate registration is refused — a silent overwrite could
    swap a canonical artifact without leaving evidence."""

    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}

    def register(self, row_id: str, artifact: Artifact) -> None:
        if row_id in self._artifacts:
            raise ValueError(f"artifact already registered for {row_id}")
        self._artifacts[row_id] = artifact

    def unregister(self, row_id: str) -> None:
        del self._artifacts[row_id]

    def get(self, row_id: str) -> Artifact | None:
        return self._artifacts.get(row_id)

    def orphaned_artifacts(self, row_ids: set[str]) -> list[str]:
        """F1 fold: registered keys with no row in the parsed contract —
        sorted, so the defect message is stable. A registered-but-unparsed
        key means the contract and the registry disagree about what exists;
        that disagreement must red, never pass silently."""
        return sorted(key for key in self._artifacts if key not in row_ids)

    def clear(self) -> None:
        self._artifacts.clear()

    def __contains__(self, row_id: object) -> bool:
        return row_id in self._artifacts

    def __iter__(self) -> Iterator[str]:
        return iter(self._artifacts)

    def __len__(self) -> int:
        return len(self._artifacts)


REGISTRY = ArtifactRegistry()


def evaluate_row(
    row: Row,
    artifact: Artifact | None,
    *,
    require_artifact: bool,
    expected_kind: str,
) -> str | None:
    """The row-item check as a pure function (unit-testable without pytest).

    Returns the failure message, or ``None`` when the row is green. Order:
    the artifact requirement (gated by REQUIRE_ARTIFACT), the kind checks,
    then the artifact's own item assertions.
    """
    if not require_artifact:
        return None
    if artifact is None:
        return f"no canonical artifact for {row.row_id}"
    if artifact.kind not in KNOWN_KINDS:
        return f"unimplemented row-kind: {artifact.kind}"
    if artifact.kind != expected_kind:
        return f"row-kind mismatch for {row.row_id}: expected {expected_kind}, got {artifact.kind}"
    unsatisfied = artifact.satisfies(row)
    if unsatisfied:
        joined = "; ".join(unsatisfied)
        return f"{row.row_id}: unsatisfied contract items: {joined}"
    return None
