"""Token issuing rejects the payload delimiter in every caller-shaped field."""

from __future__ import annotations

import pytest

from benchweave.interfaces.identity import IdentityRejected, issue, validate

SECRET = b"wp02-test-secret-not-a-credential"


def test_round_trip_still_works() -> None:
    token = issue(
        SECRET, principal="p-1", audience="stg", scopes=("stg:observe",), expires_at=200
    )
    identity = validate(SECRET, token, audience="stg", now=100)
    assert identity.principal == "p-1"
    assert identity.scopes == frozenset({"stg:observe"})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"principal": "p|admin", "audience": "stg", "scopes": ()},
        {"principal": "p-1", "audience": "stg|other", "scopes": ()},
        {"principal": "p-1", "audience": "stg", "scopes": ("stg:observe|stg:admin",)},
    ],
)
def test_delimiter_rejected_at_issue_time(kwargs: dict[str, object]) -> None:
    # The 5-field parse in validate() is defence in depth; the delimiter must
    # already be impossible to smuggle in at issue time, before any signing.
    with pytest.raises(IdentityRejected):
        issue(SECRET, expires_at=200, **kwargs)  # type: ignore[arg-type]
