"""Baseline integrity of the vendored architecture contract corpus.

Proves the four properties WP01 requires of the vendored contracts: byte
hashes, duplicate keys, nonfinite values, schema references and the source
manifest. The corpus under ``standards/`` is the admitted architecture contract
set; this file detects any drift, tampering or
accidental admission of obsolete schema versions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pytest
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "standards"
ADMITTED_DIRS = (
    "otdp/0.1.0",
    "registry/0.1.0",
    "execution/0.1.0",
    "interface/0.1.0",
)


def _strict_loads(text: str) -> Any:
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(
        text,
        object_pairs_hook=reject_pairs,
        parse_constant=reject_constant,
    )


def _load_strict(path: Path) -> Any:
    return _strict_loads(path.read_text(encoding="utf-8"))


def _manifest() -> dict[str, Any]:
    manifest = _load_strict(CONTRACTS / "corpus-manifest.json")
    assert isinstance(manifest, dict)
    return manifest


def _contract_files() -> list[Path]:
    return sorted(
        p
        for p in CONTRACTS.rglob("*.json")
        if p.name not in ("corpus-manifest.json", "standards-manifest.json")
    )


def _walk(value: Any, base: str) -> list[tuple[Any, str]]:
    nodes: list[tuple[Any, str]] = []
    if isinstance(value, dict):
        if "$id" in value and isinstance(value["$id"], str):
            base = urljoin(base, value["$id"])
        nodes.append((value, base))
        for child in value.values():
            nodes.extend(_walk(child, base))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(_walk(child, base))
    return nodes


def test_manifest_lists_every_contract_file() -> None:
    listed = {entry["path"] for entry in _manifest()["files"]}
    # as_posix(): the manifest records forward-slash paths on every OS.
    actual = {p.relative_to(CONTRACTS).as_posix() for p in _contract_files()}
    assert listed == actual, f"manifest drift: missing={actual - listed} extra={listed - actual}"


def test_manifest_hashes_match_contract_files() -> None:
    for entry in _manifest()["files"]:
        path = CONTRACTS / entry["path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == entry["sha256"], f"hash mismatch: {entry['path']}"


def test_no_obsolete_interface_version_present() -> None:
    assert not (CONTRACTS / "interface" / "1.0.0").exists(), "obsolete interface 1.0.0 imported"
    for entry in _manifest()["files"]:
        assert not entry["path"].startswith("interface/1.0.0/")


def test_manifest_identity_pins_admitted_versions() -> None:
    identity = _manifest()["identity"]
    assert identity["architecture"] == "STG 1.5"
    assert identity["interface"] == "0.1.0"
    assert identity["registry"] == "0.1.0"
    assert identity["execution"] == "0.1.0"
    assert identity["otdp"] == "0.1.0"
    assert identity["mcp"] == "2026-07-28"


def test_contract_documents_are_strict_json() -> None:
    for path in _contract_files():
        _load_strict(path)


def test_schema_references_resolve_within_corpus() -> None:
    """Mirrors scripts/architecture/check_documents.py's resolution semantics.

    Root documents follow its conventions: mcp-tools.json validates each tool
    schema as an independent document; operation-catalog.json splices in the
    shared interface.schema.json $defs; every other file is its own root.
    """
    registry = Registry()
    documents: dict[Path, Any] = {p: _load_strict(p) for p in _contract_files()}
    for path, data in documents.items():
        registry = registry.with_resource(
            path.as_uri(),
            Resource.from_contents(data, default_specification=DRAFT202012),
        )
        for node, base in _walk(data, path.as_uri()):
            if "$id" in node:
                registry = registry.with_resource(
                    base,
                    Resource.from_contents(node, default_specification=DRAFT202012),
                )
    unresolved: list[str] = []
    for path, data in documents.items():
        if path.name == "mcp-tools.json":
            roots = [
                (f"{path.as_uri()}?tool={index}&direction={direction}", tool[direction])
                for index, tool in enumerate(data["tools"])
                for direction in ("inputSchema", "outputSchema")
            ]
        elif path.name == "operation-catalog.json":
            shared = documents[path.parent / "interface.schema.json"]
            roots = [(path.as_uri(), {**data, "$defs": shared["$defs"]})]
        else:
            roots = [(path.as_uri(), data)]
        for base_uri, root in roots:
            scoped = registry.with_resource(
                base_uri, Resource.from_contents(root, default_specification=DRAFT202012)
            )
            for node, base in _walk(root, base_uri):
                ref = node.get("$ref") if isinstance(node, dict) else None
                if not isinstance(ref, str):
                    continue
                try:
                    scoped.resolver(base).lookup(ref)
                except Unresolvable:
                    unresolved.append(f"{path.relative_to(CONTRACTS).as_posix()} -> {ref}")
    assert not unresolved, f"unresolvable $refs: {unresolved}"


def test_manifest_tamper_is_detected() -> None:
    """A single flipped byte anywhere in the corpus must fail hash verification."""
    target = _contract_files()[0]
    original = target.read_bytes()
    try:
        target.write_bytes(original[:-1] + bytes([original[-1] ^ 0x01]))
        with pytest.raises(AssertionError, match="hash mismatch"):
            test_manifest_hashes_match_contract_files()
    finally:
        target.write_bytes(original)
