"""F11 boundary: a naive (offset-less) ``started_at`` is read as UTC.

The current parse's promotion, DISCLOSED in the dev head's
execution-contract §5 (fold wave, issue #176 increment 2 — F11) and
deferred with the clock/time-seam row (Rhea's dissent recorded in the
design record). These tests PIN today's behavior so an unannounced parse
change fails here first: the disclosure and the test move together, or
neither moves.

The quantified hazard: a device that stamps local time (AWST, UTC+8)
produces a naive stamp whose true instant is 8 hours EARLIER than the
UTC reading; the promotion therefore UNDERSTATES acquisition age by the
sender's offset, and stale evidence can satisfy a finite
``max_age_ms``. The fresh arm below is fresh ONLY under the UTC
promotion — a parser that began interpreting the naive stamp as local
(+08:00) would age the same evidence 9 hours and flip it stale, failing
the pin.
"""

from __future__ import annotations

from benchweave.control.executor import (
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


def test_naive_started_at_is_promoted_to_utc() -> None:
    """The parse promotes the naive stamp to UTC — the disclosed behavior."""
    parsed = _parse_wall("2026-01-01T00:00:00")
    assert parsed is not None
    offset = parsed.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0  # read as +00:00


def test_naive_started_at_ages_as_utc_not_as_local_time() -> None:
    """The 8-hour AWST-class shift, pinned.

    ``started_at`` 00:00 naive evaluated at 01:00Z is ONE hour old under
    the UTC promotion, so it satisfies a two-hour ``max_age_ms``. Had the
    stamp been ``+08:00`` (the device's local wall time), the same bytes
    would denote 16:00Z the previous day — nine hours old — and the
    sample would be ``SAMPLE_STALE``. The outcome below is therefore
    exactly the promotion's fingerprint: fresh here, stale under any
    offset-aware re-reading.
    """
    outcome = select_sample(
        _freshness_step(max_age_ms=2 * 60 * 60 * 1000),
        _invoke_result("2026-01-01T00:00:00"),
        evaluated_at_wall="2026-01-01T01:00:00Z",
    )
    assert isinstance(outcome, SampleOutcome)
    assert outcome.invalid_reason is None, (
        "the naive stamp read as UTC ages 1h — fresh at max_age 2h; "
        "a local-offset reading would age 9h and refuse"
    )
    assert outcome.value == 5.0
    # The evidence bytes are untouched: only the INTERPRETATION shifts.
    assert outcome.acquired_at == "2026-01-01T00:00:00"
    assert outcome.max_age_ms == 2 * 60 * 60 * 1000


def test_naive_started_at_still_refuses_a_window_the_promotion_cannot_hide() -> None:
    """The promotion understates age; it does not abolish it.

    At ``max_age_ms`` 10 minutes the promoted one-hour age still refuses
    ``SAMPLE_STALE`` — the disclosure names a shift, not an unbounded
    freshness grant.
    """
    outcome = select_sample(
        _freshness_step(max_age_ms=10 * 60 * 1000),
        _invoke_result("2026-01-01T00:00:00"),
        evaluated_at_wall="2026-01-01T01:00:00Z",
    )
    assert outcome.invalid_reason == SAMPLE_STALE
    assert outcome.value is None
