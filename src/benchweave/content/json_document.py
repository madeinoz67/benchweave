import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any


class DocumentRejected(ValueError):
    pass


@dataclass(frozen=True)
class JsonDocument:
    raw: bytes
    sha256: str
    content: dict[str, Any]


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in items:
        if key in result:
            raise DocumentRejected("duplicate_key")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise DocumentRejected("nonfinite_number")


def _float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise DocumentRejected("nonfinite_number")
    return number


def load_document(raw: bytes, expected_sha256: str, *, max_bytes: int) -> JsonDocument:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise DocumentRejected("invalid_limit")
    if not isinstance(raw, bytes):
        raise DocumentRejected("invalid_bytes")
    if len(raw) > max_bytes:
        raise DocumentRejected("too_large")
    digest_is_valid = (
        isinstance(expected_sha256, str)
        and re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is not None
    )
    if not digest_is_valid:
        raise DocumentRejected("invalid_digest")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise DocumentRejected("digest_mismatch")
    try:
        content = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=_float,
        )
    except DocumentRejected:
        raise
    except (UnicodeError, ValueError, OverflowError, RecursionError) as exc:
        raise DocumentRejected("invalid_json") from exc
    if not isinstance(content, dict):
        raise DocumentRejected("object_required")
    return JsonDocument(raw=raw, sha256=actual, content=content)
