# Contract Document Integrity — First Implementation Slice

> **For agentic workers:** Use the executing-plans skill when implementation is authorised. Execute the checked steps in order and review the result before expanding the next slice. No subagent dispatch is required.

**Goal:** Establish exact-byte document integrity and strict JSON loading as the first testable part of WP01.

**Architecture:** A pure internal decoder accepts bytes and an already trusted expected digest; it returns the original bytes, digest and parsed object. It performs no filesystem, network, database or device I/O. Package authenticity and semantic schema admission are separate later WP01 responsibilities.

**Tech stack:** Python 3.13 standard library and pytest. Commands below run from the future `smart-test-gateway` repository root; they have not been executed as part of planning.

## Global constraints

Preserve original document bytes; reject duplicate keys, nonfinite numbers, invalid UTF-8 and non-object root documents. A caller-supplied digest does not establish trust. This slice implements integrity only and cannot admit a package or control equipment. API 1.1.0 exact-byte document semantics are the source requirement.

## Task 1 — Strict decoder and regression tests

**Create:** `src/stg/content/json_document.py`, `tests/unit/test_json_document.py`. Namespace packaging is sufficient for this pure slice; install/build/dependency pinning belongs to the remaining WP01 setup before G1.

**Consumes:** raw UTF-8 JSON bytes, a lower-case SHA-256 from a trusted caller context, positive byte limit.

**Produces:** `load_document(raw: bytes, expected_sha256: str, *, max_bytes: int) -> JsonDocument`. Raises `DocumentRejected` on any rejected input. `JsonDocument` fields are raw, sha256 and content. No other task may assume this proves signature validity or physical authority.

- [ ] Create the test file with the complete contents below.

```python
import hashlib
import pytest
from stg.content.json_document import DocumentRejected, load_document


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def test_preserves_original_bytes():
    raw = b'{ "answer": 42 }\n'
    result = load_document(raw, digest(raw), max_bytes=1024)
    assert result.raw == raw
    assert result.sha256 == digest(raw)
    assert result.content == {"answer": 42}


def test_whitespace_changes_digest():
    raw = b'{"answer":42}'
    with pytest.raises(DocumentRejected, match="digest_mismatch"):
        load_document(raw + b" ", digest(raw), max_bytes=1024)


@pytest.mark.parametrize("raw", [
    b'{"x":1,"x":2}',
    b'{"outer":{"x":1,"x":2}}',
    b'{"x":NaN}',
    b'{"x":Infinity}',
    b'{"x":1e999}',
    b'{"x":"\xff"}',
    b'[]',
    b'null',
    b'{',
])
def test_rejects_invalid_document(raw):
    with pytest.raises(DocumentRejected):
        load_document(raw, digest(raw), max_bytes=1024)


def test_enforces_size_before_decode():
    raw = b'{"payload":"long"}'
    with pytest.raises(DocumentRejected, match="too_large"):
        load_document(raw, digest(raw), max_bytes=2)


def test_rejects_invalid_digest_format():
    with pytest.raises(DocumentRejected, match="invalid_digest"):
        load_document(b'{}', "not-a-digest", max_bytes=1024)


def test_rejects_invalid_limit():
    with pytest.raises(DocumentRejected, match="invalid_limit"):
        load_document(b'{}', digest(b'{}'), max_bytes=0)
```

- [ ] Run `PYTHONPATH=src python -m pytest tests/unit/test_json_document.py -q` in the selected test environment. Expected initial result: collection fails because `stg.content.json_document` does not exist. If pytest itself is unavailable, establish and record the test environment first; that is not the expected functional failure.
- [ ] Create the implementation file with these complete contents.

```python
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any


class DocumentRejected(ValueError):
    pass


@dataclass(frozen=True)
class JsonDocument:
    raw: bytes
    sha256: str
    content: dict[str, Any]


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise DocumentRejected("duplicate_key")
        result[key] = value
    return result


def _constant(value):
    raise DocumentRejected("nonfinite_number")


def _float(value):
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
    if not isinstance(expected_sha256, str) or re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None:
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
```

- [ ] Run the same test command. Expected: 14 test cases pass. Do not claim that result until executed in the implementation repository.
- [ ] Review that no source file opens a file/socket, imports a plugin or normalises bytes before hashing. Treat parsed content as caller-local data; raw is the canonical immutable evidence, and downstream stores must not expose shared mutable dictionaries.
- [ ] Commit only these two reviewed files with message `feat: validate exact-byte JSON documents`.

## Task 2 — Finish WP01 planning against the new repository

- [ ] Record exact Python, pytest, packaging and Draft 2020-12 validator versions in the selected environment and create the reproducible lock before claiming clean installation.
- [ ] Import the STG 1.5 architecture archive's normative files, preserving its manifest and verifying every hash. Do not import obsolete 1.0.0 interface files alongside 1.1.0.
- [ ] Expand the next WP01 task to validate local schema IDs and cross-document references, including cycle/unknown-reference rejection and a ban on remote `$ref` fetching.
- [ ] Define persistence/content-store atomicity and quotas before connecting this decoder to disk-backed admission. Add tests for the implemented boundary rather than assuming this pure function is a complete store.
- [ ] Proceed to WP02's live MCP/client risk gate and WP03's durability plan only after the resulting baseline is reviewable.

This document intentionally expands the first small coding slice, not every future module. It is ready to use as a task proposal; the PRD and staged delivery plan remain the controlling scope.
