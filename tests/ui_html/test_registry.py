"""Registry unit tests: fail-closed evaluation and the REQUIRE_ARTIFACT switch."""

from __future__ import annotations

import pytest
from benchweave_ui_html import registry
from benchweave_ui_html.grammar import Row
from benchweave_ui_html.registry import REGISTRY, ArtifactRegistry, evaluate_row


def row(row_id: str = "x-1-mini::a") -> Row:
    return Row(row_id=row_id, table_slug=row_id.split("::", 1)[0], cells=("`a`", "1"))


class _Fake:
    def __init__(self, kind: str, unsatisfied: list[str] | None = None) -> None:
        self.kind = kind
        self._unsatisfied = unsatisfied or []

    def satisfies(self, row: Row) -> list[str]:
        return self._unsatisfied


def test_require_artifact_defaults_true() -> None:
    assert registry.REQUIRE_ARTIFACT is True


def test_register_get_and_duplicate_refused() -> None:
    reg = ArtifactRegistry()
    artifact = _Fake("rule_proof")
    reg.register("x-1-mini::a", artifact)
    assert reg.get("x-1-mini::a") is artifact
    with pytest.raises(ValueError, match="already registered"):
        reg.register("x-1-mini::a", _Fake("rule_proof"))
    reg.unregister("x-1-mini::a")
    assert reg.get("x-1-mini::a") is None


def test_unregistered_row_fails_with_the_canonical_message() -> None:
    message = evaluate_row(row(), None, require_artifact=True, expected_kind="rule_proof")
    assert message == "no canonical artifact for x-1-mini::a"


def test_unknown_kind_fails() -> None:
    message = evaluate_row(row(), _Fake("bogus"), require_artifact=True, expected_kind="rule_proof")
    assert message == "unimplemented row-kind: bogus"


def test_kind_mismatch_against_the_table_shape_fails() -> None:
    message = evaluate_row(
        row(), _Fake("token_value"), require_artifact=True, expected_kind="rule_proof"
    )
    assert message is not None
    assert message.startswith("row-kind mismatch for x-1-mini::a:")
    assert "expected rule_proof" in message and "got token_value" in message


def test_satisfied_artifact_is_green() -> None:
    result = evaluate_row(
        row(), _Fake("rule_proof"), require_artifact=True, expected_kind="rule_proof"
    )
    assert result is None


def test_unsatisfied_items_are_reported() -> None:
    message = evaluate_row(
        row(),
        _Fake("rule_proof", ["missing attribute data-x"]),
        require_artifact=True,
        expected_kind="rule_proof",
    )
    assert message is not None
    assert message.startswith("x-1-mini::a: unsatisfied contract items:")
    assert "missing attribute data-x" in message


def test_the_constant_is_the_only_switch() -> None:
    """REQUIRE_ARTIFACT=False is the sole way an unregistered row goes green."""
    assert evaluate_row(row(), None, require_artifact=False, expected_kind="rule_proof") is None
    assert (
        evaluate_row(row(), _Fake("bogus"), require_artifact=False, expected_kind="rule_proof")
        is None
    )


def test_global_registry_starts_empty() -> None:
    assert len(REGISTRY) == 0


def test_orphaned_artifacts_name_registered_keys_not_parsed() -> None:
    """F1 fold: a registered key with no parsed row is an orphan — the
    delete-with-registered-artifact class reds instead of passing green."""
    reg = ArtifactRegistry()
    reg.register("x-1-mini::a", _Fake("rule_proof"))
    reg.register("x-1-mini::gone", _Fake("rule_proof"))
    reg.register("x-1-mini::zzz", _Fake("rule_proof"))
    assert reg.orphaned_artifacts({"x-1-mini::a", "x-1-mini::b"}) == [
        "x-1-mini::gone",
        "x-1-mini::zzz",
    ]
    assert reg.orphaned_artifacts({"x-1-mini::a", "x-1-mini::gone", "x-1-mini::zzz"}) == []
