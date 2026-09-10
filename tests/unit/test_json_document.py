import hashlib

import pytest

from benchweave.content.json_document import DocumentRejected, load_document


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_preserves_original_bytes() -> None:
    raw = b'{ "answer": 42 }\n'
    result = load_document(raw, digest(raw), max_bytes=1024)
    assert result.raw == raw
    assert result.sha256 == digest(raw)
    assert result.content == {"answer": 42}


def test_whitespace_changes_digest() -> None:
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
def test_rejects_invalid_document(raw: bytes) -> None:
    with pytest.raises(DocumentRejected):
        load_document(raw, digest(raw), max_bytes=1024)


def test_enforces_size_before_decode() -> None:
    raw = b'{"payload":"long"}'
    with pytest.raises(DocumentRejected, match="too_large"):
        load_document(raw, digest(raw), max_bytes=2)


def test_rejects_invalid_digest_format() -> None:
    with pytest.raises(DocumentRejected, match="invalid_digest"):
        load_document(b'{}', "not-a-digest", max_bytes=1024)


def test_rejects_invalid_limit() -> None:
    with pytest.raises(DocumentRejected, match="invalid_limit"):
        load_document(b'{}', digest(b'{}'), max_bytes=0)
