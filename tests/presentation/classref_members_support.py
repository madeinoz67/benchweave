"""Shared support for the composed-member arms (#556 Track B, slice B7):
the test-authored member-declaration schema stand-in and the scratch
corpus builder, imported by the member test modules as a sibling (the
``ui_gateway_support`` pattern — no package structure under ``tests/``).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from benchweave.standards.manifest import active_version_from_corpus
from benchweave.vendoring import corpus_root

#: A test-authored stand-in for the family's composed-member-declaration
#: schema: the same required keys and closed sets the arms pin, compact.
#: The real schema (family 0.5.0, the B2 standards motion) is B2's own
#: test surface; this stand-in keeps the walk's arms running on every
#: corpus base, with or without the bump merged. Its acceptance envelope
#: is deliberately the real schema's: action members carry claims and a
#: page, dataset members alone may carry a plot block, channels members
#: carry where_role, and one optional vendor profile row rides under
#: ``profiles`` (the plural key the canonical validator's map reads).
MEMBER_SCHEMA_STAND_IN: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:benchweave:test:composed-member-declaration",
    "title": "composed member declaration (test stand-in)",
    "type": "object",
    "additionalProperties": False,
    "required": ["contract_version", "members"],
    "properties": {
        "contract_version": {"const": "0.1.0"},
        "profiles": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {"$ref": "#/$defs/vendor_profile"},
        },
        "members": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/member"},
        },
    },
    "$defs": {
        "member": {
            "type": "object",
            "required": ["slot", "kind", "page"],
            "properties": {
                "slot": {"type": "string", "minLength": 1},
                "kind": {
                    "enum": ["channels", "dataset", "configuration", "procedure"]
                },
                "claims": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "string",
                        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*/[0-9]+\\.[0-9]+\\.[0-9]+$",
                    },
                },
                "where_role": {"type": "string", "minLength": 1},
                "when_declared": {"type": "boolean"},
                "schema_source": {"enum": ["input_schema", "output_measurement"]},
                "host_supplied": {"type": "array", "items": {"type": "string"}},
                "page": {"type": "string", "minLength": 1},
                "plot": {"$ref": "#/$defs/plot"},
            },
            "allOf": [
                {
                    "if": {
                        "properties": {"kind": {"const": "dataset"}},
                        "required": ["kind"],
                    },
                    "else": {"not": {"required": ["plot"]}},
                }
            ],
        },
        "plot": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "over_slot"],
            "properties": {
                "kind": {"enum": ["digital_lanes", "time_series", "waveform"]},
                "over_slot": {"type": "string", "minLength": 1},
                "series": {"const": "numeric_variables"},
            },
        },
        "vendor_profile": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "id",
                "title",
                "channel_roles",
                "required_actions",
                "optional_actions",
            ],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1},
                "channel_roles": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "required_actions": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "optional_actions": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}


def build_member_corpus(tmp_path: Path) -> Path:
    """The committed corpus copied into tmp with a member-declaration
    schema served at the ACTIVE family version, manifest-pinned — the
    posture a 0.5.0-serving corpus carries natively once B2 merges."""
    corpus = tmp_path / "standards"
    shutil.copytree(corpus_root(), corpus)
    version = active_version_from_corpus(corpus, "plugin-ui-class-reference")
    relpath = (
        "plugin-ui-class-reference"
        f"/{version}/composed-member-declaration.schema.json"
    )
    raw = (json.dumps(MEMBER_SCHEMA_STAND_IN, indent=2) + "\n").encode()
    (corpus / relpath).write_bytes(raw)
    manifest_path = corpus / "corpus-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"].append(
        {
            "path": relpath,
            "source": "test stand-in (B7 arms)",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
    return corpus
