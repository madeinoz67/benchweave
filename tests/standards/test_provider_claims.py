"""The provider security-boundary claim stays exactly as wide as its machine surface.

Adversary fold for gateway #147 (LOW, owner-ratified 2026-09-22): three 0.2.1
corpus surfaces claimed more than the schema enforces — that filesystem paths,
process spawning and unrestricted network endpoints are "unrepresentable" in the
provider document, and that provider transactions categorically reject unspecified
fields and carry no host/path/credential fields. The machine surface backs neither
reading: ``security_scope`` is the only closed field, and a grammar whose
subschemas admit a path or credential key (no ``additionalProperties: false``)
validates clean against the vendored schema. These tests pin both halves so the
prose cannot outrun the mechanism again: the falsifier stays valid (no future
wording may imply the schema refuses it), and each surface states the
field-scoped claim. transport-providers.md §4 already carried the honest framing
before this fold and is pinned by nothing here.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
OTDP = ROOT / "standards" / "otdp" / "0.2.1"

SCHEMA_PATH = OTDP / "otdp-transport-provider.schema.json"
PROSE_PATH = OTDP / "transport-providers.md"
SPEC_PATH = OTDP / "otdp-specification.md"

# The adversary repro, verbatim in shape: grammar subschemas that admit a
# filesystem-path key and a credential key (deliberately no
# additionalProperties: false) plus hostile host_requirements text. Invented
# names only — no real vendor, product, bench or person.
HOSTILE_CONTRACT = {
    "contract_version": "0.1.0",
    "id": "urn:otdp:transport-provider:mock-relay:1.0.0",
    "feature_id": "otdp.transport.mock-relay/1.0.0",
    "version": "1.0.0",
    "description": "Synthetic falsifier: grammar subschemas that admit path and credential keys.",
    "transport_kind": "vendor_sdk",
    "transaction_grammar": [
        {
            "kind": "load_config",
            "request_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "config_path": {"type": "string"},
                    "api_key": {"type": "string"},
                },
            },
            "result_schema": {"type": "object"},
            "limits": {},
        }
    ],
    "security_scope": "commissioned_connection",
    "host_requirements": {
        "summary": "Reads /etc/mock-relay.conf and spawns helper binaries; needs root.",
        "native_libraries": [{"name": "libmockrelay", "version": "9.9.9"}],
        "privileges": ["root", "arbitrary filesystem paths", "process spawning"],
    },
    "approval": {
        "approved_by": "Mock Bench Review",
        "approved_at": "2026-09-22T00:00:00Z",
        "expires_at": "2027-09-22T00:00:00Z",
        "evidence": [
            {
                "category": "protocol",
                "report": {
                    "id": "mock-relay-grammar",
                    "version": "1.0.0",
                    "sha256": "0" * 64,
                },
                "tested_at": "2026-09-22T00:00:00Z",
                "scope": "Falsifier fixture only",
                "result": "passed",
                "limitations": ["No hardware evidence"],
            }
        ],
    },
}


def test_falsifier_contract_validates_clean_against_the_schema() -> None:
    """security_scope is the only closed field: the hostile document is schema-valid.

    Pins the adversary repro. If this ever fails because the schema grew teeth,
    the three prose surfaces may widen with it — change them in the same arc,
    never before.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(HOSTILE_CONTRACT))
    assert not errors, [error.message for error in errors]


def test_schema_description_scopes_the_boundary_to_security_scope() -> None:
    """The schema's own claim names the security_scope boundary, not the document.

    The pre-fold wording said such things are "unrepresentable here", reading
    document-wide; the falsifier above proves they are representable everywhere
    in the document except inside the security_scope enum.
    """
    description = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["description"]
    assert "unrepresentable here" not in description
    assert "security_scope" in description
    assert "commissioned_connection" in description


def test_provider_companion_qualifies_the_transaction_properties() -> None:
    """transport-providers.md §3 states the authored-grammar condition.

    §4's security-surface framing is untouched by this pin.
    """
    prose = PROSE_PATH.read_text(encoding="utf-8")
    assert (
        "they reject unspecified fields, carry no host/path/credential fields" not in prose
    )
    assert "when the grammar is authored that way" in prose


def test_specification_qualifies_the_transaction_properties() -> None:
    """otdp-specification.md §8.1's provider paragraph carries the same qualifier."""
    spec = SPEC_PATH.read_text(encoding="utf-8")
    assert (
        "they reject unspecified fields, carry no host/path/credential fields" not in spec
    )
    assert "when the admitted grammar is authored that way" in spec
