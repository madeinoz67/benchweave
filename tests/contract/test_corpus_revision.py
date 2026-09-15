"""D2 errata corpus revision: ``interface-v1.1.1`` is a new, versioned corpus.

The vendored ``interface-v1.1.0`` corpus stays frozen authority — its bytes
are NEVER edited, pinned here against the digests recorded in git HEAD's
manifest. The D2 amendment (the catalog's ``change_apply`` REST body schema
omitted ``approver_token``, which the REST adapter already forwards as the
detached approval credential) ships as a NEW versioned corpus revision,
``standards/interface-v1.1.1/`` (originally vendored from a docs source before
the docs mirror was retired; manifest ``source`` fields remain as historical
provenance):

- only ``change_apply``'s requestBody schema changes — it gains an OPTIONAL
  ``approver_token`` string property (NOT added to ``required``; the adapter
  extracts it with ``body.get`` and the seam accepts it as an optional
  kwarg, so a corpus-literal body without the token must stay valid);
- every other revision file is a byte-copy of 1.1.0;
- the architecture identity stays ``1.1.0`` — the errata revision is
  recorded separately as ``interface_errata`` in the manifest.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from benchweave.interfaces import errors
from benchweave.interfaces.validation import SeamValidator

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "standards"
BASELINE = "interface-v1.1.0"
REVISION = "interface-v1.1.1"
APPLY_ROUTE = "/v1/admin/changes/{change_id}/apply"

#: The revision's corpus set — mirrors the 1.1.0 vendored set exactly.
REVISION_FILES = (
    "examples/mcp-start-exchange.json",
    "examples/operation-vectors.json",
    "interface.schema.json",
    "mcp-tools.json",
    "openapi.json",
    "operation-catalog.json",
)

_APPROVAL_REF: dict[str, Any] = {"id": "approval-1", "version": "1", "sha256": "0" * 64}


def _manifest() -> dict[str, Any]:
    manifest = json.loads((CONTRACTS / "corpus-manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)
    return manifest


def _entries(prefix: str) -> dict[str, dict[str, Any]]:
    return {
        str(entry["path"]): entry
        for entry in _manifest()["files"]
        if str(entry["path"]).startswith(f"{prefix}/")
    }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _head_manifest() -> dict[str, Any]:
    """The manifest as last committed — the frozen-bytes reference point.

    Durability boundary (ISC-5 ledger note): HEAD re-baselines with every
    commit, so this guard catches UNCOMMITTED drift against the last commit
    (and a manifest-row rewrite in the working tree); the durable freeze on
    1.1.0 is git history itself plus the vendoring record — a committed
    edit to the 1.1.0 corpus would re-baseline HEAD and pass here, which is
    why the corpus revision flow ships amendments as NEW revisions, never
    edits to the frozen baseline.
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "show", "HEAD:standards/corpus-manifest.json"],
        capture_output=True,
    )
    if proc.returncode != 0:
        # Pre-relocation history (before the standards/ consolidation) kept
        # the manifest at contracts/manifest.json; HEAD may be either side.
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "show", "HEAD:contracts/manifest.json"],
            check=True,
            capture_output=True,
        )
    manifest = json.loads(proc.stdout)
    assert isinstance(manifest, dict)
    return manifest


def _apply_body_schema(corpus: str) -> dict[str, Any]:
    doc = json.loads((CONTRACTS / corpus / "openapi.json").read_text(encoding="utf-8"))
    schema = (
        doc["paths"][APPLY_ROUTE]["post"]["requestBody"]["content"]["application/json"]["schema"]
    )
    assert isinstance(schema, dict)
    return schema


def test_revision_files_match_manifest_and_cover_the_tree() -> None:
    """Every vendored revision byte matches its manifest digest, and
    nothing vendored escapes the manifest. The retired docs sources survive
    only as provenance in the manifest's ``source`` fields."""
    entries = _entries(REVISION)
    assert set(entries) == {f"{REVISION}/{name}" for name in REVISION_FILES}
    for rel, entry in entries.items():
        vendored = CONTRACTS / rel
        assert vendored.is_file(), f"missing vendored file: {rel}"
        assert _digest(vendored) == entry["sha256"], f"manifest digest drift: {rel}"
    on_disk = {str(p.relative_to(CONTRACTS)) for p in (CONTRACTS / REVISION).rglob("*.json")}
    assert on_disk == set(entries), "vendored files outside the manifest"


def test_baseline_bytes_are_unchanged_since_head() -> None:
    """The 1.1.0 corpus is inviolable: on-disk digests equal the digests git
    HEAD's manifest recorded, the current manifest keeps identical rows, and
    every on-disk 1.1.0 file stays covered by those rows."""
    head = {
        str(entry["path"]): str(entry["sha256"])
        for entry in _head_manifest()["files"]
        if str(entry["path"]).startswith(f"{BASELINE}/")
    }
    assert head, "HEAD manifest carries no interface-v1.1.0 entries"
    for rel, digest in head.items():
        assert _digest(CONTRACTS / rel) == digest, f"1.1.0 byte drift: {rel}"
    current = {rel: str(entry["sha256"]) for rel, entry in _entries(BASELINE).items()}
    assert current == head, "manifest rewrote interface-v1.1.0 rows"
    on_disk = {str(p.relative_to(CONTRACTS)) for p in (CONTRACTS / BASELINE).rglob("*.json")}
    assert set(head) == on_disk, "unlisted interface-v1.1.0 files appeared"


def test_change_apply_body_admits_optional_approver_token() -> None:
    """The revision's single schema change: an optional string property,
    with ``required`` and the closed ``additionalProperties`` untouched."""
    schema = _apply_body_schema(REVISION)
    assert schema["properties"]["approver_token"] == {"type": "string"}
    assert "approver_token" not in schema.get("required", [])
    assert schema["additionalProperties"] is False
    assert schema["required"] == _apply_body_schema(BASELINE)["required"]


def test_revision_copies_everything_else_byte_for_byte() -> None:
    """Scope discipline: the five non-openapi files are byte-copies of the
    1.1.0 corpus, and the amended openapi differs from 1.1.0 by EXACTLY the
    injected property (semantic diff of the whole document)."""
    for name in REVISION_FILES:
        if name == "openapi.json":
            continue
        assert (CONTRACTS / REVISION / name).read_bytes() == (
            CONTRACTS / BASELINE / name
        ).read_bytes(), f"{name} is not a byte-copy of 1.1.0"
    amended = deepcopy(
        json.loads((CONTRACTS / BASELINE / "openapi.json").read_text(encoding="utf-8"))
    )
    amended["paths"][APPLY_ROUTE]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]["properties"]["approver_token"] = {"type": "string"}
    revision = json.loads((CONTRACTS / REVISION / "openapi.json").read_text(encoding="utf-8"))
    assert revision == amended, "openapi.json changed beyond the approver_token property"


def test_identity_records_the_errata_revision() -> None:
    """The architecture interface version stays 1.1.0; the errata revision
    is recorded separately."""
    identity = _manifest()["identity"]
    assert identity["interface"] == "1.1.0"
    assert identity["interface_errata"] == "1.1.1"


def test_amended_validator_accepts_what_the_adapter_sends() -> None:
    """The 1.1.1-validated path accepts the body the REST adapter actually
    forwards (``approver_token`` present, string); the frozen 1.1.0 corpus
    rejects that same payload (``additionalProperties: false``) — proving
    the amendment, not a widened default, admits the field — while a
    corpus-literal body without the token stays valid on BOTH revisions."""
    payload: dict[str, Any] = {
        "request_id": "req-errata",
        "expected_generation": 1,
        "approval_ref": deepcopy(_APPROVAL_REF),
        "approver_token": "detached-approver-credential",
    }
    SeamValidator(CONTRACTS / REVISION).validate("change_apply", payload)

    literal = {key: value for key, value in payload.items() if key != "approver_token"}
    SeamValidator(CONTRACTS / REVISION).validate("change_apply", literal)
    SeamValidator(CONTRACTS / BASELINE).validate("change_apply", dict(literal))

    with pytest.raises(errors.OperationFailure) as rejected:
        SeamValidator(CONTRACTS / BASELINE).validate("change_apply", dict(payload))
    assert rejected.value.failure.code == "invalid_request"
