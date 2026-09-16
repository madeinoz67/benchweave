# src/benchweave/registry/schemas.py
"""Strict loading of registry documents against the vendored 1.0.0 schemas.

Structural validity never establishes trust (schema descriptions say so);
authenticity and lifecycle checks live in authenticity.py / admission.py.
"""
from __future__ import annotations

import json
from functools import cache

from jsonschema import Draft202012Validator, FormatChecker

from benchweave.content.json_document import JsonDocument, load_document
from benchweave.vendoring import contract_family

#: Vendored registry schemas, resolved exactly as ``control/documents.py``
#: resolves its vendored execution/0.1.0 schemas (packaged in the wheel,
#: repo-relative in a dev checkout — :mod:`benchweave.vendoring`). The
#: schema bytes are pinned in ``contracts/manifest.json`` and verified by
#: ``tests/contract/test_baseline.py``.
_CONTRACTS = contract_family("registry/0.1.0")


class RegistryRejected(ValueError):
    """A registry document failed structure or schema validation.

    ``detail`` (optional) widens the human-readable message — e.g. the first
    failing schema path — without touching ``reason``; callers match on
    ``reason`` alone.
    """

    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason} ({detail})")
        self.reason = reason


def _load_schema_bytes(schema_filename: str) -> bytes:
    return (_CONTRACTS / schema_filename).read_bytes()


@cache
def _make_validator(schema_filename: str) -> Draft202012Validator:
    schema = json.loads(_load_schema_bytes(schema_filename))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.check_schema(schema)
    return validator


def _load_validated(
    raw: bytes, expected_sha256: str, *, max_bytes: int, schema_filename: str
) -> JsonDocument:
    doc = load_document(raw, expected_sha256, max_bytes=max_bytes)
    errors = sorted(
        _make_validator(schema_filename).iter_errors(doc.content),
        key=lambda error: error.json_path,
    )
    if errors:
        # Diagnostic pointer only: ``reason`` stays exactly ``schema_invalid``;
        # the message carries the first sorted error's JSON path so a schema
        # rejection points at its subject (surface-audit wave 1, item 8).
        first = errors[0]
        raise RegistryRejected(
            "schema_invalid", detail=f"first failing path: {first.json_path}"
        )
    return doc


def load_manifest_document(raw: bytes, expected_sha256: str, *, max_bytes: int) -> JsonDocument:
    """Decode one release-manifest document and validate it against its schema."""
    return _load_validated(
        raw, expected_sha256, max_bytes=max_bytes, schema_filename="release-manifest.schema.json"
    )


def load_status_document(raw: bytes, expected_sha256: str, *, max_bytes: int) -> JsonDocument:
    """Decode one release-status document and validate it against its schema."""
    return _load_validated(
        raw, expected_sha256, max_bytes=max_bytes, schema_filename="release-status.schema.json"
    )


def load_lock_document(raw: bytes, expected_sha256: str, *, max_bytes: int) -> JsonDocument:
    """Decode one package-lock document and validate it against its schema."""
    return _load_validated(
        raw, expected_sha256, max_bytes=max_bytes, schema_filename="package-lock.schema.json"
    )
