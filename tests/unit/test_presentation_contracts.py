"""Strict presentation input parsing without importing plugin code."""

import importlib.util
from types import ModuleType

import pytest


def api() -> ModuleType:
    assert importlib.util.find_spec("benchweave.presentation") is not None, (
        "Presentation validation is missing"
    )
    from benchweave.presentation import contracts

    return contracts


@pytest.mark.parametrize(
    "raw",
    [
        b'{"id":"a","id":"b"}',
        b'{"value":NaN}',
        b'{"value":1e999}',
        b"[]",
        b"\xff",
        b'{"x":' + b"[" * 33 + b"0" + b"]" * 33 + b"}",
        b" " * 262145,
    ],
    ids=["duplicate-key", "nan", "overflow", "array", "utf8", "depth", "bytes"],
)
def test_strict_document_rejects_invalid_input(raw: bytes) -> None:
    contract = api()
    with pytest.raises(contract.DocumentError):
        contract.parse_document(raw)


def test_strict_document_preserves_finite_values() -> None:
    assert api().parse_document(b'{"value":3.3}') == {"value": 3.3}


def test_string_brackets_are_not_counted_as_nesting() -> None:
    raw = b'{"text":"[[[\\"{{{{"}'
    assert api().parse_document(raw)["text"] == '[[["{{{{'
