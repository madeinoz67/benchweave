"""The composed-member mirror (issue #556 Track B, slice B7; Track B
record §3): the gateway's own member-declaration walk, injection seam and
dispositions, mirroring the SDK expander at the composed-member tips
(``feat/556-b3-members`` ``2dd718d``, ``feat/556-b4-procedures-settings``
``3182312``, ``feat/556-b5-datasets-plots`` ``bac0ac3``, folds included).

Corpus posture: the member-declaration schema joins the family at 0.5.0
(the B2 standards motion, a sibling slice). This module's arms run against
a SCRATCH corpus — the committed corpus copied into tmp with a
test-authored member schema written at the ACTIVE family version and
re-pinned into the copied manifest — so the walk's semantics
(discrimination, conflicts, injection, dispositions) are pinned on every
base, with or without the 0.5.0 bump merged. The schema's own closed sets
(lifted verbatim from their owners) are B2's test surface, not this
module's; a member pin against a corpus serving NO member schema is the
transitional refusal arm below. When the corpus serves the real 0.5.0
schema the same arms run unchanged — the walk reads whatever schema the
active family serves, exactly as the SDK's lazy loader does.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from benchweave.presentation.classref import (
    ClassRefusal,
    DerivedAttachment,
    derive_attachment,
)
from benchweave.standards.manifest import active_version_from_corpus
from benchweave.vendoring import corpus_root

FIXTURES = Path(__file__).parent / "classref_fixtures"

#: A test-authored stand-in for the family's composed-member-declaration
#: schema: the same required keys and closed sets the arms pin, compact.
#: The real schema (family 0.5.0) is B2's surface; this stand-in keeps the
#: walk's arms running on every corpus base. Its acceptance envelope is
#: deliberately the real schema's: action members carry claims and a page,
#: dataset members alone may carry a plot block, channels members carry
#: where_role, and one optional vendor profile row rides under ``profiles``.
_MEMBER_SCHEMA_STAND_IN: dict[str, Any] = {
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


@pytest.fixture()
def member_corpus(tmp_path: Path) -> Path:
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
    raw = (json.dumps(_MEMBER_SCHEMA_STAND_IN, indent=2) + "\n").encode()
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


def _m400() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-m400.json").read_bytes()
    )
    return document


def _vendor_catalogs() -> dict[str, bytes]:
    catalogs: dict[str, bytes] = {}
    for name in (
        "vendor-catalog.json",
        "vendor-catalog-trio.json",
        "composed-burst.json",
    ):
        raw = (FIXTURES / name).read_bytes()
        catalogs[hashlib.sha256(raw).hexdigest()] = raw
    return catalogs


def _pin(
    descriptor: dict[str, Any],
    document: dict[str, Any],
    *,
    name: str = "members.json",
) -> dict[str, bytes]:
    """Admit one pinned document beside the descriptor and return the
    admission map (digest-keyed) carrying it."""
    raw = (json.dumps(document, indent=2) + "\n").encode()
    descriptor["contracts"].append(
        {
            "id": f"urn:meridian:{name.removesuffix('.json')}",
            "path": name,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    return {hashlib.sha256(raw).hexdigest(): raw}


def _declare(descriptor: dict[str, Any], *urns: str) -> None:
    """Declare vendor actions the members claim (the custom-resolution
    shape: descriptor-declared, no served catalog row)."""
    for urn in urns:
        descriptor["actions"][urn] = {
            "binding": {"kind": "adapter", "key": "fixture"},
            "timeout_ms": 5000,
            "side_effect": "state_change",
            "cancellable": True,
            "retry": "never",
        }


def _members_document(members: list[dict[str, Any]]) -> dict[str, Any]:
    """One valid member declaration over the given member rows."""
    return {
        "contract_version": "0.1.0",
        "profiles": [
            {
                "id": "com.meridian.m400/1.0.0",
                "title": "Meridian M-400 vendor row",
                "channel_roles": ["analogue_input"],
                "required_actions": ["com.meridian.m400.sweep/1.0.0"],
                "optional_actions": [],
            }
        ],
        "members": members,
    }


def _derive_document(
    descriptor: dict[str, Any],
    catalogs: dict[str, bytes],
    corpus: Path,
) -> DerivedAttachment:
    decoder_raw = (FIXTURES / "decoder-uart.json").read_bytes()
    return derive_attachment(
        (json.dumps(descriptor, indent=2) + "\n").encode(),
        corpus=corpus,
        vendor_catalogs=catalogs,
        decoder_docs={hashlib.sha256(decoder_raw).hexdigest(): decoder_raw},
    )


class TestMemberWalk:
    """The pinned-document walk's member half: shape discrimination
    (one definition, three disjoint key vocabularies), schema validation,
    the over-slot self-reference refusal, and the member conflict family —
    the mirror of the SDK walk at ``bac0ac3``."""

    def test_a_schema_invalid_member_document_refuses_typed(
        self, member_corpus: Path
    ) -> None:
        """A ``members`` pin that fails the served member schema refuses
        ``classref_invalid_member_declaration`` (the
        ``_invalid_composed_class`` posture): pre-B7 the same bytes matched
        neither shape discriminator and were silently disclosed as an
        ignored pin."""
        descriptor = _m400()
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "not-a-kind",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "capture",
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(
            ClassRefusal, match="^classref_invalid_member_declaration:"
        ):
            _derive_document(descriptor, catalogs, member_corpus)

    def test_plot_over_slot_not_the_members_own_slot_refuses(
        self, member_corpus: Path
    ) -> None:
        """The self-reference rule (the README's named cannot-catch: the
        schema cannot compare two instance values): ``plot.over_slot``
        names the member's own slot or the document contradicts itself —
        ``classref_composed_plot_slot_mismatch``, before any member
        injects."""
        descriptor = _m400()
        _declare(descriptor, "com.meridian.m400.wave/1.0.0")
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.wave/1.0.0"],
                    "page": "capture",
                    "plot": {
                        "kind": "waveform",
                        "over_slot": "capture",
                        "series": "numeric_variables",
                    },
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(
            ClassRefusal, match="^classref_composed_plot_slot_mismatch:"
        ):
            _derive_document(descriptor, catalogs, member_corpus)

    def test_one_slot_two_members_in_one_document_refuses(
        self, member_corpus: Path
    ) -> None:
        """The same-document duplicate names the document once and says
        the pair is internal (the B3 fold's NIT wording)."""
        descriptor = _m400()
        _declare(
            descriptor,
            "com.meridian.m400.sweep/1.0.0",
            "com.meridian.m400.profile_mode/1.0.0",
        )
        member = {
            "slot": "sweep",
            "kind": "procedure",
            "claims": ["com.meridian.m400.sweep/1.0.0"],
            "page": "capture",
        }
        other = {
            "slot": "sweep",
            "kind": "configuration",
            "claims": ["com.meridian.m400.profile_mode/1.0.0"],
            "page": "output",
        }
        document = _members_document([member, other])
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(ClassRefusal, match="^classref_composed_slot_conflict:") as exc:
            _derive_document(descriptor, catalogs, member_corpus)
        assert "declared by two members in the same pinned document" in str(exc.value)

    def test_one_slot_two_documents_refuses_naming_both_pins(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        _declare(
            descriptor,
            "com.meridian.m400.sweep/1.0.0",
            "com.meridian.m400.profile_mode/1.0.0",
        )
        first = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "capture",
                }
            ]
        )
        second = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "configuration",
                    "claims": ["com.meridian.m400.profile_mode/1.0.0"],
                    "page": "output",
                }
            ]
        )
        catalogs = _vendor_catalogs()
        catalogs |= _pin(descriptor, first, name="members-a.json")
        catalogs |= _pin(descriptor, second, name="members-b.json")
        with pytest.raises(ClassRefusal, match="^classref_composed_slot_conflict:") as exc:
            _derive_document(descriptor, catalogs, member_corpus)
        assert "members-a.json and members-b.json" in str(exc.value)

    def test_one_claim_two_members_refuses(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        _declare(descriptor, "com.meridian.m400.sweep/1.0.0")
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "capture",
                },
                {
                    "slot": "vendor-configure",
                    "kind": "configuration",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "output",
                },
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(ClassRefusal, match="^classref_composed_slot_conflict:") as exc:
            _derive_document(descriptor, catalogs, member_corpus)
        assert "is claimed by both member" in str(exc.value)

    def test_a_claim_a_composed_class_holds_refuses(
        self, member_corpus: Path
    ) -> None:
        """One claim, one owner: the class owns the catalogue side, the
        member the placement — a member claiming the class's URN refuses
        under the shared conflict code."""
        descriptor = _m400()
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.burst_mode/1.0.0"],
                    "page": "capture",
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(ClassRefusal, match="^classref_composed_slot_conflict:") as exc:
            _derive_document(descriptor, catalogs, member_corpus)
        assert "which composed class otdp.action.meridian_burst/1.0.0 claims" in str(
            exc.value
        )

    def test_a_members_key_set_overlapping_the_catalog_keys_refuses(
        self, member_corpus: Path
    ) -> None:
        """The R2 question generalized to three key vocabularies: a pin
        carrying ``members`` AND ``actions`` is ambiguous — one key set is
        not a shape claim — and refuses naming the carried shape groups
        (pre-B7 this pin rode the catalog arm down and contributed its
        actions silently)."""
        descriptor = _m400()
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "capture",
                }
            ]
        )
        document["actions"] = {}
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(
            ClassRefusal, match="^classref_invalid_composed_class:"
        ) as exc:
            _derive_document(descriptor, catalogs, member_corpus)
        assert "carries keys of more than one pin shape" in str(exc.value)
        assert "members, actions" in str(exc.value)

    def test_a_members_key_set_overlapping_the_class_keys_refuses(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "capture",
                }
            ]
        )
        document["urn"] = "otdp.action.meridian_members/1.0.0"
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(
            ClassRefusal, match="^classref_invalid_composed_class:"
        ) as exc:
            _derive_document(descriptor, catalogs, member_corpus)
        assert "members, composed-class" in str(exc.value)

    def test_two_catalogs_sharing_an_embedded_id_refuse_in_the_walk(
        self, member_corpus: Path
    ) -> None:
        """The walk-side half of the shared ``pinned_id_shadow`` guard
        (the B4 fold's F3): the derive and the canonical validation refuse
        the same shape under the same code — two pinned catalogs sharing
        an input-schema ``$id`` never derive green."""
        descriptor = _m400()
        schema_id = "urn:meridian:action:shared-input"
        row = {
            "input_schema": {
                "$id": schema_id,
                "type": "object",
                "properties": {},
            },
            "side_effect": "none",
        }
        first = {"catalog_version": "1.0.0", "actions": {"com.meridian.a/1.0.0": dict(row)}}
        second = {"catalog_version": "1.0.0", "actions": {"com.meridian.b/1.0.0": dict(row)}}
        catalogs = _vendor_catalogs()
        catalogs |= _pin(descriptor, first, name="catalog-a.json")
        catalogs |= _pin(descriptor, second, name="catalog-b.json")
        with pytest.raises(ClassRefusal, match="^pinned_id_shadow:") as exc:
            _derive_document(descriptor, catalogs, member_corpus)
        assert "shadows a served schema $id" in str(exc.value)

    def test_a_tampered_member_pin_refuses_under_the_neutral_wording(
        self, tmp_path: Path
    ) -> None:
        """The B5 fold's NIT: the digest-mismatch detail names the pin
        neutrally — the walk verifies member declarations and vendor
        catalogs through one seam, and a members document is not a vendor
        catalog (the code keeps its historical name; the prose does not).
        The real corpus (no member schema) is fine here: integrity fires
        before any discrimination."""
        corpus = tmp_path / "standards"
        shutil.copytree(corpus_root(), corpus)
        descriptor = _m400()
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "capture",
                }
            ]
        )
        raw = (json.dumps(document, indent=2) + "\n").encode()
        claimed = hashlib.sha256(raw + b"x").hexdigest()
        descriptor["contracts"].append(
            {
                "id": "urn:meridian:members",
                "path": "members.json",
                "sha256": claimed,
            }
        )
        with pytest.raises(
            ClassRefusal, match="^classref_vendor_catalog_digest_mismatch:"
        ) as exc:
            # The admission store serves the tampered BYTES under the
            # claimed digest — the lookup succeeds and the digest gate
            # fires (the tampering arm, not the unreadable one).
            _derive_document(
                descriptor, _vendor_catalogs() | {claimed: raw},
                corpus,
            )
        assert "pinned document members.json digest mismatch" in str(exc.value)

    def test_a_member_pin_against_a_corpus_serving_no_member_schema_refuses(
        self, tmp_path: Path
    ) -> None:
        """The transitional posture (the SDK's lazy-loader rule, in the
        gateway's typed face): a member pin on a corpus whose active
        family serves no member-declaration schema is a platform fault
        that refuses LOUDLY — never a silently-empty read, never the
        ignored-pin disclosure. Once the corpus serves the family's 0.5.0
        tree the arm is unreachable by construction."""
        corpus = tmp_path / "standards"
        shutil.copytree(corpus_root(), corpus)
        descriptor = _m400()
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "capture",
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(
            ClassRefusal, match="^classref_invalid_member_declaration:"
        ) as exc:
            _derive_document(descriptor, catalogs, corpus)
        assert "serves no composed-member-declaration schema" in str(exc.value)
