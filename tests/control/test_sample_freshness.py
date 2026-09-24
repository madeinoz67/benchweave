"""F11 boundary: a naive (offset-less) ``started_at`` is REFUSED.

Rhea's position, riding its named trigger (the row-B time seam — the
design record's recorded dissent, now the code of record): a naive stamp
misstates its instant by the sender's whole offset, and bytes that
misstate UTC cannot ground evidence-exact records. The seam wave's
disclosure — the naive→UTC promotion with the quantified hazard — is
upgraded to the fix: the parse no longer promotes; a parseable but
offset-less ``started_at`` refuses with the named reason
``naive_timestamp`` (distinct from ``stale``: unknown timing is a
freshness verdict, a mis-stated instant is a document defect), and an
UNPARSEABLE stamp still reads ``stale`` (unknown timing cannot satisfy a
finite bound).

The quantified hazard the fix removes: a device that stamps local time
(AWST, UTC+8) produces a naive stamp whose true instant is 8 hours
EARLIER than the UTC reading; the promotion UNDERSTATED acquisition age
by the sender's offset, and stale evidence could satisfy a finite
``max_age_ms``.
"""

from __future__ import annotations

from benchweave.control.executor import (
    SAMPLE_NAIVE_TIMESTAMP,
    SAMPLE_STALE,
    SampleOutcome,
    _parse_wall,
    select_sample,
)
from benchweave.host.types import OperationResult, OperationVerb


def _invoke_result(started_at: str) -> OperationResult:
    """One scalar-set invoke result whose ``started_at`` is the given stamp."""
    return OperationResult.ok(
        "op-f11",
        OperationVerb.INVOKE,
        {
            "result": {
                "kind": "scalar_set",
                "started_at": started_at,
                "configuration_id": "cfg-f11",
                "variables": [
                    {
                        "id": "voltage",
                        "unit": "V",
                        "values": [5.0],
                        "dimensions": [],
                        "status": "valid",
                    }
                ],
            }
        },
    )


def _freshness_step(max_age_ms: int) -> dict[str, object]:
    return {
        "id": "voltage",
        "kind": "sample",
        "source_step": "measure",
        "variable_id": "voltage",
        "unit": "V",
        "max_age_ms": max_age_ms,
        "require_known_uncertainty": False,
    }


def test_naive_started_at_is_refused_not_promoted() -> None:
    """The parse refuses the naive stamp — the promotion is gone. The
    refusal is the NAMED document-defect reason, not the stale verdict."""
    assert _parse_wall("2026-01-01T00:00:00") is None
    outcome = select_sample(
        _freshness_step(max_age_ms=2 * 60 * 60 * 1000),
        _invoke_result("2026-01-01T00:00:00"),
        evaluated_at_wall="2026-01-01T01:00:00Z",
    )
    assert isinstance(outcome, SampleOutcome)
    assert outcome.invalid_reason == SAMPLE_NAIVE_TIMESTAMP
    assert outcome.value is None


def test_aware_started_at_still_ages_normally() -> None:
    """The honest sibling arm: an offset-aware stamp keeps the ordinary
    freshness arithmetic — one hour old at evaluation, fresh at 2h."""
    outcome = select_sample(
        _freshness_step(max_age_ms=2 * 60 * 60 * 1000),
        _invoke_result("2026-01-01T00:00:00Z"),
        evaluated_at_wall="2026-01-01T01:00:00Z",
    )
    assert isinstance(outcome, SampleOutcome)
    assert outcome.invalid_reason is None
    assert outcome.value == 5.0


def test_unparseable_started_at_still_reads_stale() -> None:
    """Unknown timing is a freshness verdict: garbage the parser cannot
    read at all still refuses ``stale`` — distinct from the naive
    refusal, and unchanged by this fix."""
    outcome = select_sample(
        _freshness_step(max_age_ms=10 * 60 * 1000),
        _invoke_result("not-a-timestamp"),
        evaluated_at_wall="2026-01-01T01:00:00Z",
    )
    assert outcome.invalid_reason == SAMPLE_STALE
    assert outcome.value is None


def test_naive_started_at_refused_even_inside_a_generous_window() -> None:
    """The refusal does not depend on the window: the promotion used to
    hide an 8-hour lie inside any ``max_age_ms`` wide enough; the refusal
    fires wherever the freshness check runs."""
    outcome = select_sample(
        _freshness_step(max_age_ms=24 * 60 * 60 * 1000),
        _invoke_result("2026-01-01T00:00:00"),
        evaluated_at_wall="2026-01-01T01:00:00Z",
    )
    assert outcome.invalid_reason == SAMPLE_NAIVE_TIMESTAMP
    assert outcome.value is None
