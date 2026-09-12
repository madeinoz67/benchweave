# src/benchweave/registry/authenticity.py
"""Authenticated metadata: signatures, expiry, monotonic status sequences.

PoC scope (spec decision 1): ed25519 detached signatures over original bytes
behind this interface; TUF role topology belongs to service qualification.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from benchweave.content.json_document import JsonDocument

_FUTURE_TOLERANCE_NS = 300 * 1_000_000_000


class AuthenticityRejected(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class TrustRoot:
    origin_id: str
    verify_key_pem: bytes


def load_trust_root(origin_id: str, pub_pem_path: Path) -> TrustRoot:
    return TrustRoot(origin_id=origin_id, verify_key_pem=pub_pem_path.read_bytes())


def _public_key(root: TrustRoot) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(root.verify_key_pem)
    except ValueError as exc:
        raise AuthenticityRejected("unknown_trust") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise AuthenticityRejected("unknown_trust")
    return key


def verify_document(doc: JsonDocument, signature: bytes, root: TrustRoot) -> None:
    try:
        _public_key(root).verify(signature, doc.raw)
    except InvalidSignature as exc:
        raise AuthenticityRejected("bad_signature") from exc


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def check_status(
    status: dict[str, Any],
    *,
    root: TrustRoot | None,
    now_ns: int,
    high_water: Mapping[tuple[str, str, str], int],
) -> int:
    """Enforce a status document's expiry, freshness, and sequence honesty.

    ``root`` authenticates nothing here — signature verification happens
    before these gates run — and is carried (as ``None`` under a
    ``dev-unsigned`` origin) for interface parity with :func:`verify_document`
    and future role-aware checks; every gate below is root-independent and
    stays on for dev origins.
    """
    release = status["release"]
    key = (release["registry_id"], release["package_id"], release["version"])
    if _ns(_parse_utc(status["expires_at"])) <= now_ns:
        raise AuthenticityRejected("expired_status")
    if _ns(_parse_utc(status["updated_at"])) > now_ns + _FUTURE_TOLERANCE_NS:
        raise AuthenticityRejected("future_updated_at")
    sequence: int = status["sequence"]
    if sequence <= high_water.get(key, 0):
        raise AuthenticityRejected("stale_sequence")
    return sequence
