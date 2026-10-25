"""Plugin-authored profile documents: the profile-shadow rule and the pinned-$id merge guard.

Issue #446 slice 2 (design:
.claude/deep-review/2026-10-12-issue446-invoke-profile-map-design.md §3.2):
a digest-pinned plugin-authored contract document may re-declare a corpus
profile id — divergent rows refuse (`profile_shadow`); identical rows stay
benign dedup. A pinned document may not embed a `$id` that shadows a served
schema `$id` (`merge_pinned_documents` refuses `pinned_id_shadow`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from benchweave.presentation.contracts import (
    SCHEMA_ROOT,
    DocumentError,
    Finding,
    ValidationReport,
    merge_pinned_documents,
    validate_presentation,
)

type JsonObject = dict[str, Any]

ROOT = Path(__file__).resolve().parents[2]

VENDOR_PROFILE_ID = "vendor.la34/1.0.0"
CORPUS_PROFILE_ID = "otdp.dc_psu/1.0.0"
CORPUS_ACTION = "otdp.dc_psu.configure/1.0.0"


def encode(value: object) -> bytes:
    return json.dumps(value).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load(path: str) -> JsonObject:
    document: JsonObject = json.loads((ROOT / path).read_bytes())
    return document


DOCUMENTS: JsonObject | None = None
CATALOG: JsonObject | None = None
DESCRIPTOR: JsonObject | None = None


def documents() -> JsonObject:
    """The trusted-host corpus document set: plugin-ui 0.3.1 schemas + OTDP 0.2.2 catalog."""
    global DOCUMENTS, CATALOG
    if DOCUMENTS is None:
        set_: JsonObject = {}
        for path in (ROOT / "standards/plugin-ui/0.4.0").glob("*.schema.json"):
            document = json.loads(path.read_bytes())
            set_[document["$id"]] = document
        CATALOG = load("standards/otdp/0.2.2/device-profile-catalog.json")
        set_["catalog"] = CATALOG
        DOCUMENTS = set_
    return DOCUMENTS


def corpus_catalog() -> JsonObject:
    documents()
    assert CATALOG is not None
    return CATALOG


def base_descriptor() -> JsonObject:
    global DESCRIPTOR
    if DESCRIPTOR is None:
        DESCRIPTOR = load("standards/otdp/0.2.2/examples/class-dc_psu.json")
    return DESCRIPTOR


def corpus_profile_row() -> JsonObject:
    row = [p for p in corpus_catalog()["profiles"] if p["id"] == CORPUS_PROFILE_ID][0]
    copy: JsonObject = json.loads(json.dumps(row))  # deep copy
    return copy


def pinned_catalog(
    profile_rows: list[JsonObject],
    *,
    id_: str = "urn:vendor-la34:profile-catalog:1.0.0",
    actions: JsonObject | None = None,
) -> JsonObject:
    document: JsonObject = {
        "$id": id_,
        "contract_version": "0.4.0",
        "catalog_version": "0.2.2",
        "otdp_version": "0.2.2",
        "profiles": profile_rows,
        "actions": actions if actions is not None else {},
    }
    return document


def validate_with(
    documents: JsonObject,
    *,
    descriptor: JsonObject | None = None,
    target: JsonObject | None = None,
    schema_asset: JsonObject | None = None,
) -> ValidationReport:
    """Validate a configuration-target specimen over the given document set.

    ``schema_asset`` overrides the bytes the manifest's ``settings`` asset
    carries (default: the corpus action's input schema) — a vendor target
    supplies its own action schema the same way the corpus specimen does.
    """
    descriptor = descriptor if descriptor is not None else base_descriptor()
    if target is None:
        action_schema = corpus_catalog()["actions"][CORPUS_ACTION]["input_schema"]
        target = {
            "id": "configure",
            "kind": "configuration",
            "action_id": CORPUS_ACTION,
            "profile_ids": [CORPUS_PROFILE_ID],
            "input_schema_id": action_schema["$id"],
            "schema_asset_id": "settings",
            "preset_asset_ids": [],
        }
    descriptor_raw = encode(descriptor)
    manifest = {
        "contract_version": "0.4.0",
        "plugin_id": descriptor["id"],
        "descriptor_sha256": digest(descriptor_raw),
        "bindings": [
            {"id": "configuration", "kind": "configuration", "target_id": "configure"}
        ],
        "pages": [
            {
                "id": "settings",
                "kind": "configuration",
                "title": "Settings",
                "bindings": ["configuration"],
                "required": True,
            }
        ],
    }
    if schema_asset is None:
        schema_asset = corpus_catalog()["actions"][CORPUS_ACTION]["input_schema"]
    action_schema_raw = encode(schema_asset)
    assets = {"settings": action_schema_raw}
    manifest["assets"] = [
        {"id": name, "path": name + ".json", "sha256": digest(raw)} for name, raw in assets.items()
    ]
    manifest_raw = encode(manifest)
    catalogue = {
        "contract_version": "0.4.0",
        "descriptor_sha256": digest(descriptor_raw),
        "targets": [target],
    }
    envelope = {
        "contract_version": "0.4.0",
        "descriptor_sha256": digest(descriptor_raw),
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": digest(manifest_raw)},
    }
    resources = {name + ".json": raw for name, raw in assets.items()}
    resources["manifest.json"] = manifest_raw
    return validate_presentation(
        encode(envelope),
        descriptor_raw=descriptor_raw,
        resources=resources,
        binding_catalogue=catalogue,
        schema_documents=documents,
        supported_features=frozenset(),
        supported_panels=frozenset(),
        firmware="1.0",
    )


def test_corpus_specimen_is_valid_without_pinned_documents() -> None:
    """Baseline: the corpus-only set validates (0.3.0 behavior unchanged)."""
    report = validate_with(documents())
    assert report.valid, report.findings


def test_pinned_duplicate_identical_rows_admits() -> None:
    """Identical duplicate = benign dedup: the target binds the same rows either way."""
    set_ = dict(documents())
    set_["pinned:vendor-cat"] = pinned_catalog([corpus_profile_row()])
    report = validate_with(set_)
    assert report.valid, report.findings


def test_pinned_duplicate_divergent_rows_refuses() -> None:
    """Divergent duplicate + target binds the shadowed id → `profile_shadow`."""
    divergent = corpus_profile_row()
    divergent["optional_actions"] = ["otdp.dc_psu.measure/1.0.0"]
    set_ = dict(documents())
    set_["pinned:vendor-cat"] = pinned_catalog([divergent])
    report = validate_with(set_)
    assert not report.valid
    assert Finding(
        "profile_shadow",
        "targets.configure",
        'Profile id "otdp.dc_psu/1.0.0" is declared with divergent rows by multiple documents',
    ) in report.findings


def test_merge_guard_refuses_planted_corpus_id() -> None:
    """A pinned document may not embed a served schema `$id` (the poisoning vector)."""

    planted = pinned_catalog([corpus_profile_row()], id_=SCHEMA_ROOT + "ui-manifest.schema.json")
    with pytest.raises(DocumentError) as excinfo:
        merge_pinned_documents(documents(), {"vendor-cat": planted})
    assert excinfo.value.code == "pinned_id_shadow"
    assert "vendor-cat" in str(excinfo.value)
    assert "ui-manifest" in str(excinfo.value)


def test_merge_guard_refuses_action_schema_id_collision() -> None:
    """The guard also scans a pinned document's action-schema `$id`s."""

    action_schema_id = corpus_catalog()["actions"][CORPUS_ACTION]["input_schema"]["$id"]
    planted = pinned_catalog(
        [corpus_profile_row()],
        actions={CORPUS_ACTION: {"input_schema": {"$id": action_schema_id}}},
    )
    with pytest.raises(DocumentError) as excinfo:
        merge_pinned_documents(documents(), {"vendor-cat": planted})
    assert excinfo.value.code == "pinned_id_shadow"
    assert action_schema_id in str(excinfo.value)


def test_merge_guard_refuses_pinned_pairwise_collision() -> None:
    """Two pinned documents aliasing one `$id` refuse (the within-set residual)."""
    from benchweave.presentation.contracts import merge_pinned_documents

    vendor = pinned_catalog([corpus_profile_row()])
    with pytest.raises(DocumentError) as excinfo:
        merge_pinned_documents(
            documents(),
            {"vendor-cat": vendor, "vendor-cat-2": pinned_catalog([], id_=vendor["$id"])},
        )
    assert excinfo.value.code == "pinned_id_shadow"


def test_merge_guard_admits_unique_vendor_ids() -> None:
    """A pinned document with unique vendor `$id`s merges under its pinned: key."""

    vendor = pinned_catalog([corpus_profile_row()])
    merged = merge_pinned_documents(documents(), {"vendor-cat": vendor})
    assert merged["pinned:vendor-cat"] is vendor
    assert merged["catalog"] is corpus_catalog()
    # The merged set validates the corpus specimen unchanged.
    report = validate_with(merged)
    assert report.valid, report.findings


# --- the #556 track B composed-member seam (B2 fold, F1) -------------------------
#
# The composed-member declaration's vendor profile row must ride the PLURAL
# ``profiles`` key — the one ``_target_findings`` reads. The first draft of
# the family schema published it under a singular ``profile`` object, which
# the canonical validator never reads (and ``additionalProperties: false``
# refuses on the validator's spelling), so nothing could be both
# schema-valid and validator-readable. The arm below proves the
# intersection is non-empty: schema-valid AND resolved, zero findings.

VENDOR_PROFILE_ID_556 = "com.meridian.m400/1.0.0"
VENDOR_ACTION_556 = "com.meridian.m400.arm/1.0.0"
VENDOR_INPUT_SCHEMA_ID = "urn:vendor:m400:arm-input:1.0.0"


def member_declaration_556() -> JsonObject:
    return {
        "contract_version": "0.1.0",
        "profiles": [
            {
                "id": VENDOR_PROFILE_ID_556,
                "title": "Meridian M-400",
                "channel_roles": ["digital_input"],
                "required_actions": [VENDOR_ACTION_556],
                "optional_actions": [],
            }
        ],
        "members": [
            {
                "slot": "arm",
                "kind": "procedure",
                "claims": [VENDOR_ACTION_556],
                "page": "capture",
            }
        ],
    }


def vendor_action_catalog_556() -> JsonObject:
    """The sibling pinned document a vendor target's action schema rides
    (the vendor-catalog shape of the pin-seam discrimination): the action
    and its input schema, no profile row — the profile row belongs to the
    declaration alone."""
    return {
        "$id": "urn:vendor:m400:actions:1.0.0",
        "actions": {
            VENDOR_ACTION_556: {
                "input_schema": {
                    "$id": VENDOR_INPUT_SCHEMA_ID,
                    "type": "object",
                    "properties": {
                        "hold_s": {"type": "number", "minimum": 0}
                    },
                    "required": ["hold_s"],
                    "additionalProperties": False,
                }
            }
        },
    }


def vendor_claiming_descriptor_556() -> JsonObject:
    descriptor: JsonObject = json.loads(json.dumps(base_descriptor()))
    descriptor["profiles"] = sorted(
        set(descriptor.get("profiles", [])) | {VENDOR_PROFILE_ID_556}
    )
    descriptor["actions"][VENDOR_ACTION_556] = json.loads(
        json.dumps(descriptor["actions"][CORPUS_ACTION])
    )
    return descriptor


def test_schema_valid_member_declaration_resolves_a_vendor_target() -> None:
    """The F1 seam, driven end to end: a composed-member declaration that
    validates against the family's 0.5.0 schema, merged into the document
    set through the real ``merge_pinned_documents`` guard, resolves a
    vendor profile target through the real ``validate_presentation`` with
    ZERO target findings — the descriptor claims the vendor profile id, the
    declaration's ``profiles[0]`` row is what the validator's profile map
    reads, and the vendor action's schema arrives pinned beside it. Under
    the singular ``profile`` spelling this intersection was empty: the
    schema admitted a key no reader owns."""
    schema = json.loads(
        (
            ROOT
            / "standards/plugin-ui-class-reference/0.5.0"
            / "composed-member-declaration.schema.json"
        ).read_bytes()
    )
    declaration = member_declaration_556()
    assert Draft202012Validator(schema).is_valid(declaration), (
        "the declaration must be schema-valid for the seam to be proven"
    )
    merged = merge_pinned_documents(
        documents(),
        {
            "m400-declaration": declaration,
            "m400-catalog": vendor_action_catalog_556(),
        },
    )
    vendor_schema = vendor_action_catalog_556()["actions"][VENDOR_ACTION_556][
        "input_schema"
    ]
    report = validate_with(
        merged,
        descriptor=vendor_claiming_descriptor_556(),
        target={
            "id": "configure",
            "kind": "configuration",
            "action_id": VENDOR_ACTION_556,
            "profile_ids": [VENDOR_PROFILE_ID_556],
            "input_schema_id": VENDOR_INPUT_SCHEMA_ID,
            "schema_asset_id": "settings",
            "preset_asset_ids": [],
        },
        schema_asset=vendor_schema,
    )
    assert report.valid, report.findings
    assert not [
        finding
        for finding in report.findings
        if finding.code in ("capability_mismatch", "unresolved_reference", "profile_shadow")
    ]
