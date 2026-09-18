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


@pytest.mark.parametrize(
    "scopes",
    [
        ("stg:observe stg:admin",),  # space: the intra-field scope delimiter
        ("stg:observe\tstg:admin",),  # any whitespace is rejected as hygiene
        ("",),  # empty elements would vanish in the round trip
        (b"stg:observe",),  # non-str must reject, not raise a raw TypeError
        (None,),
    ],
)
def test_malformed_scope_elements_rejected_at_issue_time(scopes: tuple[object, ...]) -> None:
    # A single element containing a space would round-trip into SEVERAL
    # granted scopes through the split(" ") in validate(); non-string
    # elements used to escape as a raw TypeError from sorted()/join().
    with pytest.raises(IdentityRejected) as excinfo:
        issue(SECRET, principal="p-1", audience="stg", scopes=scopes, expires_at=200)  # type: ignore[arg-type]
    assert str(excinfo.value) == "malformed_token"


def test_validate_never_grants_more_scopes_than_issued() -> None:
    issued = frozenset({"stg:observe", "stg:control"})
    token = issue(SECRET, principal="p-1", audience="stg", scopes=issued, expires_at=200)
    identity = validate(SECRET, token, audience="stg", now=100)
    assert identity.scopes == issued  # exactly what was issued: no more, no fewer
