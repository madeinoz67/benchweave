"""Local test issuer for principal/audience/scope credentials.

WP02 risk-gate primitive. This is explicitly a LOCAL TEST ISSUER: tokens carry
no production identity claim, the secret is caller-supplied, and validation
performs no I/O and reads no clock (``now`` is injected, keeping issue and
validate pure and deterministic). Token format: base64url(payload) "." 
base64url(hmac_sha256(secret, payload)) where payload is
"v1|principal|audience|space-sorted-scopes|expires_at-unix".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Iterable
from dataclasses import dataclass


class IdentityRejected(ValueError):
    """Machine-matchable rejection; str(exc) is always the reason token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Identity:
    principal: str
    audience: str
    scopes: frozenset[str]
    expires_at: int


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _payload(identity_args: dict[str, object]) -> bytes:
    principal = identity_args["principal"]
    audience = identity_args["audience"]
    scopes = identity_args["scopes"]
    expires_at = identity_args["expires_at"]
    if not isinstance(principal, str) or not principal or "|" in principal:
        raise IdentityRejected("malformed_token")
    if not isinstance(audience, str) or not audience or "|" in audience:
        raise IdentityRejected("malformed_token")
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise IdentityRejected("malformed_token")
    if isinstance(scopes, (set, frozenset, list)):
        for scope in scopes:
            if (
                not isinstance(scope, str)
                or not scope
                or "|" in scope
                or any(ch.isspace() for ch in scope)
            ):
                raise IdentityRejected("malformed_token")
        joined = " ".join(sorted(scopes))
    else:
        joined = ""
    # ``|`` is the payload field delimiter and `` `` is the intra-field scope
    # delimiter: both are rejected element-by-element above so a crafted
    # principal/audience/scope can never shift field boundaries, and a single
    # scope element can never round-trip into several granted scopes through
    # the split in ``validate``. The 5-field check there stays as defence in
    # depth.
    return f"v1|{principal}|{audience}|{joined}|{expires_at}".encode()


def issue(
    secret: bytes,
    *,
    principal: str,
    audience: str,
    scopes: Iterable[str],
    expires_at: int,
) -> str:
    """Mint a local test token. Pure: identical inputs yield identical tokens."""
    scope_set = frozenset(scopes)
    payload = _payload(
        {
            "principal": principal,
            "audience": audience,
            "scopes": scope_set,
            "expires_at": expires_at,
        }
    )
    signature = hmac.new(secret, payload, hashlib.sha256).digest()
    return _b64url(payload) + "." + _b64url(signature)


def validate(
    secret: bytes,
    token: str,
    *,
    audience: str,
    required_scopes: Iterable[str] = (),
    now: int,
) -> Identity:
    """Validate a token fail-closed; every rejection carries its reason."""
    if not isinstance(token, str) or token.count(".") != 1:
        raise IdentityRejected("malformed_token")
    encoded_payload, encoded_signature = token.split(".")
    try:
        payload = _b64url_decode(encoded_payload)
        signature = _b64url_decode(encoded_signature)
        fields = payload.decode("utf-8").split("|")
        if len(fields) != 5 or fields[0] != "v1":
            raise IdentityRejected("malformed_token")
        _, principal, token_audience, scopes_field, expires_field = fields
        expires_at = int(expires_field)
    except (ValueError, UnicodeError):
        raise IdentityRejected("malformed_token") from None
    expected = hmac.new(secret, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise IdentityRejected("bad_signature")
    if expires_at <= now:
        raise IdentityRejected("expired")
    if token_audience != audience:
        raise IdentityRejected("wrong_audience")
    granted = frozenset(s for s in scopes_field.split(" ") if s)
    missing = frozenset(required_scopes) - granted
    if missing:
        raise IdentityRejected("insufficient_scope")
    return Identity(
        principal=principal,
        audience=token_audience,
        scopes=granted,
        expires_at=expires_at,
    )
