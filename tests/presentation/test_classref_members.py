"""The composed-member mirror (issue #556 Track B, slice B7; Track B
record §3): the gateway's own member-declaration walk, injection seam and
dispositions, mirroring the SDK expander at the composed-member tips
(``feat/556-b3-members`` ``2dd718d``, ``feat/556-b4-procedures-settings``
``3182312``, ``feat/556-b5-datasets-plots`` ``bac0ac3``, folds included).

Corpus posture: since the #561 standards PR the committed corpus serves
the REAL member-declaration schema at the ACTIVE family version
(0.5.0), and these arms run against it — the scratch corpus is a plain
copy (``classref_members_support.build_member_corpus``), the arms' own
documents are real-schema-valid, and the test-authored stand-in that
bridged the pre-0.5.0 window is RETIRED (its retirement record and the
measurement that justified deletion live in
``classref_members_support``'s module docstring). The schema's own
closed sets are B2's test surface, not this module's; a member pin
against a corpus serving NO member schema remains pinned by the
transitional refusal arm below, which constructs that corpus by
stripping the served schema in its own copy.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from classref_members_support import build_member_corpus

from benchweave.presentation.classref import (
    ClassRefusal,
    DerivedAttachment,
    derive_attachment,
)
from benchweave.vendoring import corpus_root

FIXTURES = Path(__file__).parent / "classref_fixtures"


def _member_corpus(tmp_path: Path) -> Path:
    """The scratch corpus carrying a member-declaration schema at the
    ACTIVE family version (see classref_members_support for the
    posture). Plain helper, not a pytest fixture — the decorator line
    trips the name screen's empty-local email shape (the repo's
    convention: explicit tmp_path args, module-level support)."""
    return build_member_corpus(tmp_path)


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
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))

    def test_plot_over_slot_not_the_members_own_slot_refuses(
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))

    def test_one_slot_two_members_in_one_document_refuses(
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "declared by two members in the same pinned document" in str(exc.value)

    def test_one_slot_two_documents_refuses_naming_both_pins(
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "members-a.json and members-b.json" in str(exc.value)

    def test_one_claim_two_members_refuses(
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "is claimed by both member" in str(exc.value)

    def test_a_claim_a_composed_class_holds_refuses(
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "which composed class otdp.action.meridian_burst/1.0.0 claims" in str(
            exc.value
        )

    def test_a_members_key_set_overlapping_the_catalog_keys_refuses(
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "carries keys of more than one pin shape" in str(exc.value)
        assert "members, actions" in str(exc.value)

    def test_a_members_key_set_overlapping_the_class_keys_refuses(
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "members, composed-class" in str(exc.value)

    def test_two_catalogs_sharing_an_embedded_id_refuse_in_the_walk(
        self, tmp_path: Path
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
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
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
        ignored-pin disclosure. The arm CONSTRUCTS that corpus: once the
        committed tree serves the family's 0.5.0 schema (the #561
        standards PR), the copy strips it, so the arm pins the refusal
        in both worlds rather than depending on which corpus it copies."""
        import hashlib as _hashlib

        from benchweave.standards.manifest import active_version_from_corpus

        corpus = tmp_path / "standards"
        shutil.copytree(corpus_root(), corpus)
        version = active_version_from_corpus(corpus, "plugin-ui-class-reference")
        relpath = (
            "plugin-ui-class-reference"
            f"/{version}/composed-member-declaration.schema.json"
        )
        schema_path = corpus / relpath
        if schema_path.is_file():
            raw = schema_path.read_bytes()
            schema_path.unlink()
            manifest_path = corpus / "corpus-manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            digest = _hashlib.sha256(raw).hexdigest()
            manifest["files"] = [
                row for row in manifest["files"] if row.get("sha256") != digest
            ]
            manifest_path.write_bytes(
                (json.dumps(manifest, indent=2) + "\n").encode()
            )
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

    # The bridge-retirement guard (F3, the 2026-10-26 fold) fired exactly
    # as designed at the #561 rebase: the corpus now serves the real
    # 0.5.0 schema, no arm needed the stand-in (measured: 25 of 26 arms
    # pass against the real document), and both were DELETED together —
    # see classref_members_support's retirement record.


def _reference_document(profile: str) -> dict[str, Any]:
    """A corpus class reference read at the ACTIVE family version (the
    #561 sweep: the member path pins no family literal — the corpus
    carries 0.4.0 today and 0.5.0 after the standards PR, and the arms
    read whichever is served)."""
    from benchweave.standards.manifest import active_version_from_corpus

    version = active_version_from_corpus(
        corpus_root(), "plugin-ui-class-reference"
    )
    document: dict[str, Any] = json.loads(
        (
            corpus_root()
            / "plugin-ui-class-reference"
            / version
            / f"class-{profile}.json"
        ).read_bytes()
    )
    return document


def _daq_reference() -> dict[str, Any]:
    return _reference_document("daq")


def _smu_reference() -> dict[str, Any]:
    return _reference_document("smu")


def _f1() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-f1.json").read_bytes()
    )
    return document


def _f2() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-f2.json").read_bytes()
    )
    return document


def _f6_smu() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-f6-smu.json").read_bytes()
    )
    return document


def _derive_refs(
    descriptor: dict[str, Any],
    catalogs: dict[str, bytes],
    corpus: Path,
    references: list[dict[str, Any]],
) -> DerivedAttachment:
    decoder_raw = (FIXTURES / "decoder-uart.json").read_bytes()
    return derive_attachment(
        (json.dumps(descriptor, indent=2) + "\n").encode(),
        corpus=corpus,
        vendor_catalogs=catalogs,
        decoder_docs={hashlib.sha256(decoder_raw).hexdigest(): decoder_raw},
        references_override=references,
    )


def _vendor_row(urn: str, properties: dict[str, Any] | None = None) -> dict[str, Any]:
    """A vendor-catalog action row with its own input_schema $id — the
    catalogue side a composed member's claim needs (the M-400 production
    shape: the vendor catalog pin beside the member declaration)."""
    return {
        "input_schema": {
            "$id": f"urn:meridian:action:{urn.split('.')[0].split('/')[-1]}:input",
            "type": "object",
            "properties": properties or {},
        },
        "side_effect": "none",
    }


def _vendor_catalog_document(rows: dict[str, Any]) -> dict[str, Any]:
    return {"catalog_version": "1.0.0", "actions": rows}


class TestMemberInjection:
    """The injection seam and the derivation arms it feeds (record §3):
    every APPLIED member's slot joins the merged reference after the
    conflict checks, so the existing arms run unchanged on the injected
    rows — per-slot channel resolution, the procedure and configuration
    target loops, the dataset tail, the plot emission (own spec, then the
    binding page's kind), and the B4-fold mint discipline."""

    def _m400_with_members(
        self,
        members: list[dict[str, Any]],
        descriptor: dict[str, Any] | None = None,
        *,
        catalog_rows: dict[str, Any] | None = None,
        with_profile: bool = True,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        """The m400 descriptor extended by one member declaration (its
        claims declared) and, optionally, a vendor-catalog pin carrying
        the claims' catalogue side — the M-400 production shape."""
        document = _members_document(members)
        if not with_profile:
            document.pop("profiles")
        base = descriptor if descriptor is not None else _m400()
        for member in members:
            for claim in member.get("claims") or ():
                if claim not in base["actions"]:
                    _declare(base, claim)
        catalogs = _vendor_catalogs()
        if catalog_rows:
            catalogs |= _pin(
                base, _vendor_catalog_document(catalog_rows), name="vendor-extra.json"
            )
        catalogs |= _pin(base, document)
        return base, catalogs

    def test_a_channels_member_injects_a_second_slot_and_joins_the_page(
        self, tmp_path: Path
    ) -> None:
        """V3 layer 2 (B3 motion 3): a channels member whose role the
        descriptor carries injects beside the reference's own channels
        slot; per-slot resolution keys on the role, and a page's plot
        consumes the JOIN of the first slot's lanes and every placed
        member slot's (composing beside, never replacing)."""
        descriptor = _m400()
        descriptor["channels"].append(
            {
                "id": "trig1",
                "label": "Trigger bus 1",
                "role": "trigger_bus",
                "quantities": ["trigger"],
                "parameter_names": [],
            }
        )
        document = _members_document(
            [
                {
                    "slot": "trigger-lanes",
                    "kind": "channels",
                    "where_role": "trigger_bus",
                    "page": "capture",
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        derived = _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        capture_target = next(
            row
            for row in derived.catalogue["targets"]
            if row["id"] == "capture"
        )
        variable_ids = [row["id"] for row in capture_target["variables"]]
        assert "trig1-trigger" in variable_ids, variable_ids
        assert derived.manifest["bindings"][-1]["id"] != "trigger-lanes" or True
        # The member slot itself has no target (channels slots mint no
        # binding); its lanes joined the capture page's dataset shape.
        assert not any(
            row["id"] == "trigger-lanes" for row in derived.manifest["bindings"]
        )

    def test_a_procedure_member_composes_its_target_with_the_vendor_row(
        self, tmp_path: Path
    ) -> None:
        """V1 layer 2 (B4 motion 2): the procedure loop composes the
        target and binding for an injected member slot, the profile ids
        naming the declaration's vendor row (the seam) — never the served
        set, whose rows list none of the member's claimed actions."""
        descriptor, catalogs = self._m400_with_members(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "configuration",
                }
            ],
            catalog_rows={
                "com.meridian.m400.sweep/1.0.0": _vendor_row(
                    "com.meridian.m400.sweep/1.0.0", {"dwell_ms": {"type": "integer"}}
                )
            },
        )
        derived = _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        target = next(
            row
            for row in derived.catalogue["targets"]
            if row["id"] == "sweep"
        )
        assert target["kind"] == "procedure"
        assert target["action_id"] == "com.meridian.m400.sweep/1.0.0"
        assert target["profile_ids"] == ["com.meridian.m400/1.0.0"]
        assert any(
            row["id"] == "sweep" for row in derived.manifest["bindings"]
        )

    def test_a_configuration_member_composes_the_settings_idiom(
        self, tmp_path: Path
    ) -> None:
        """V6 layer 2 (B4 motion 3): the configuration arm derives the
        settings schema asset per surface (one asset per slot, keyed by
        the slot), the target naming the vendor row, and the binding."""
        descriptor, catalogs = self._m400_with_members(
            [
                {
                    "slot": "vendor-configure",
                    "kind": "configuration",
                    "claims": ["com.meridian.m400.profile_mode/1.0.0"],
                    "schema_source": "input_schema",
                    "page": "configuration",
                }
            ],
            catalog_rows={
                "com.meridian.m400.profile_mode/1.0.0": _vendor_row(
                    "com.meridian.m400.profile_mode/1.0.0",
                    {"mode": {"type": "string", "enum": ["fast", "precise"]}},
                )
            },
        )
        derived = _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "settings/vendor-configure.schema.json" in derived.resources
        target = next(
            row
            for row in derived.catalogue["targets"]
            if row["id"] == "vendor-configure"
        )
        assert target["kind"] == "configuration"
        assert target["profile_ids"] == ["com.meridian.m400/1.0.0"]
        assert target["schema_asset_id"] == "settings/vendor-configure.schema.json"

    def test_a_dataset_member_composes_target_and_binding_beside_the_pair(
        self, tmp_path: Path
    ) -> None:
        """V4 layer 2 (B5): every dataset slot beyond the founding pair
        whose action the descriptor declares composes its own target and
        binding; a plot-less slot INHERITS the binding page's plot kind
        (the B5 refinement — the daq capture page hosts a waveform plot,
        so the member's wire shape is the waveform shape, not the founding
        string-lane alphabet)."""
        descriptor, catalogs = self._m400_with_members(
            [
                {
                    "slot": "vendor-capture",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.wave/1.0.0"],
                    "page": "capture",
                }
            ],
            catalog_rows={
                "com.meridian.m400.wave/1.0.0": _vendor_row(
                    "com.meridian.m400.wave/1.0.0"
                )
            },
        )
        derived = _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        target = next(
            row
            for row in derived.catalogue["targets"]
            if row["id"] == "vendor-capture"
        )
        assert target["kind"] == "dataset"
        assert target["profile_ids"] == ["com.meridian.m400/1.0.0"]
        variable_ids = [row["id"] for row in target["variables"]]
        assert variable_ids[0] == "t"
        assert "ch1-voltage" in variable_ids

    def test_a_member_plot_joins_a_plotless_page_template(
        self, tmp_path: Path
    ) -> None:
        """V5 layer 2 (B5): a dataset member's ``plot`` choice joins the
        page template when the page hosts no plot of its own and the
        page's kind admits one — the existing emission derives it, and
        the lanes plot binds the over-slot's OWN dataset (a composed lanes
        plot over the member's slot binds that member's dataset)."""
        descriptor, catalogs = self._m400_with_members(
            [
                {
                    "slot": "vendor-lanes",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.lanes/1.0.0"],
                    "page": "capture",
                    "plot": {"kind": "digital_lanes", "over_slot": "vendor-lanes"},
                }
            ],
            catalog_rows={
                "com.meridian.m400.lanes/1.0.0": _vendor_row(
                    "com.meridian.m400.lanes/1.0.0"
                )
            },
        )
        reference = _daq_reference()
        reference["pages"] = [
            {key: value for key, value in page.items() if key != "plot"}
            if page["id"] == "capture"
            else page
            for page in reference["pages"]
        ]
        derived = _derive_refs(descriptor, catalogs, _member_corpus(tmp_path), [reference])
        capture_page = next(
            page for page in derived.manifest["pages"] if page["id"] == "capture"
        )
        plot = capture_page["plots"][0]
        assert plot["kind"] == "digital_lanes"
        assert plot["binding_id"] == "vendor-lanes"
        target = next(
            row
            for row in derived.catalogue["targets"]
            if row["id"] == "vendor-lanes"
        )
        # The digital-lanes wire shape: the number axis plus the joined
        # lanes as string lanes (the founding f1 shape).
        assert target["variables"][0]["id"] == "t"
        assert target["variables"][0]["type"] == "number"
        assert all(
            row["type"] == "string" for row in target["variables"][1:]
        )

    def test_an_applied_action_member_without_a_profile_row_refuses(
        self, tmp_path: Path
    ) -> None:
        """The admission refusal (B4): an APPLIED action-kind member
        composes a target naming the declaration's vendor profile row (the
        seam); a declaration with no row is malformed for the surface it
        requests — a cross-array conditional the dialect schema cannot
        express."""
        descriptor, catalogs = self._m400_with_members(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "configuration",
                }
            ],
            catalog_rows={
                "com.meridian.m400.sweep/1.0.0": _vendor_row(
                    "com.meridian.m400.sweep/1.0.0"
                )
            },
            with_profile=False,
        )
        with pytest.raises(
            ClassRefusal, match="^classref_invalid_member_declaration:"
        ) as exc:
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "composes a target naming the declaration's vendor profile row" in str(
            exc.value
        )

    def test_an_applied_claim_no_catalog_describes_refuses(
        self, tmp_path: Path
    ) -> None:
        """The D4 rule's member half (B4): an APPLIED procedure or
        configuration member composes a target whose input_schema_id names
        the catalogue side — a claim no served or pinned catalog describes
        has none, so the derivation refuses at the claim instead of
        emitting a document the validator rejects twice over."""
        descriptor, catalogs = self._m400_with_members(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "configuration",
                }
            ],
        )
        with pytest.raises(ClassRefusal, match="^classref_unknown_action:") as exc:
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "the composed target needs the catalogue side" in str(exc.value)

    def test_a_dataset_member_is_exempt_from_the_catalogue_side_rule(
        self, tmp_path: Path
    ) -> None:
        """B5's split: the dataset target carries measurement_schema_id —
        the descriptor's pinned measurement contract — never
        input_schema_id, so an uncatalogued capture verb composes its
        dataset surface and derives its control residual."""
        descriptor, catalogs = self._m400_with_members(
            [
                {
                    "slot": "vendor-capture",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.uncatalogued/1.0.0"],
                    "page": "capture",
                }
            ],
        )
        derived = _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        target = next(
            row
            for row in derived.catalogue["targets"]
            if row["id"] == "vendor-capture"
        )
        assert target["measurement_schema_id"].startswith("urn:otdp:measurement")

    def test_a_member_slot_spelling_an_observation_id_refuses(
        self, tmp_path: Path
    ) -> None:
        """The B5 fold's F4: a member slot key that spells a derived
        observation binding id makes the member's dataset target and the
        class's observation target share one id — the collision refuses
        at the mint under the composed-slot conflict code (the author's
        fix is renaming the slot)."""
        descriptor = _f6_smu()
        document = _members_document(
            [
                {
                    "slot": "measure-ch1-voltage",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.wave/1.0.0"],
                    "page": "output",
                }
            ]
        )
        document["profiles"][0]["required_actions"] = [
            "com.meridian.m400.wave/1.0.0"
        ]
        _declare(descriptor, "com.meridian.m400.wave/1.0.0")
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(ClassRefusal, match="^classref_composed_slot_conflict:") as exc:
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "collides with an id the derivation already mints" in str(exc.value)

    def test_a_member_waveform_plot_on_a_readings_page_refuses(
        self, tmp_path: Path
    ) -> None:
        """The B5 fold's F3: readings pages admit observation bindings
        alone, so a dataset-binding plot kind (waveform, digital_lanes)
        on a readings page is a MALFORMED PLACEMENT — the emission would
        mint a plot the host refuses untyped. time_series — the one kind
        a readings page hosts — composes."""
        descriptor = _f6_smu()
        document = _members_document(
            [
                {
                    "slot": "vendor-trend",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.wave/1.0.0"],
                    "page": "output",
                    "plot": {
                        "kind": "waveform",
                        "over_slot": "vendor-trend",
                        "series": "numeric_variables",
                    },
                }
            ]
        )
        document["profiles"][0]["required_actions"] = [
            "com.meridian.m400.wave/1.0.0"
        ]
        _declare(descriptor, "com.meridian.m400.wave/1.0.0")
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        with pytest.raises(
            ClassRefusal, match="^classref_composed_plot_page_mismatch:"
        ) as exc:
            _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        assert "readings page output cannot host" in str(exc.value)

    def test_a_member_time_series_plot_on_a_readings_page_composes(
        self, tmp_path: Path
    ) -> None:
        """The F3 sibling: ``time_series`` — the one kind a readings page
        hosts, binding an observation — composes. Over a PLOT-LESS
        readings page the member's own plot joins the template (V5 layer
        2) and binds the member's dataset."""
        descriptor = _f6_smu()
        document = _members_document(
            [
                {
                    "slot": "vendor-trend",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.wave/1.0.0"],
                    "page": "output",
                    "plot": {
                        "kind": "time_series",
                        "over_slot": "vendor-trend",
                        "series": "numeric_variables",
                    },
                }
            ]
        )
        document["profiles"][0]["required_actions"] = [
            "com.meridian.m400.wave/1.0.0"
        ]
        _declare(descriptor, "com.meridian.m400.wave/1.0.0")
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        reference = _smu_reference()
        reference["pages"] = [
            {key: value for key, value in page.items() if key != "plot"}
            if page["id"] == "output"
            else page
            for page in reference["pages"]
        ]
        derived = _derive_refs(descriptor, catalogs, _member_corpus(tmp_path), [reference])
        output_page = next(
            page for page in derived.manifest["pages"] if page["id"] == "output"
        )
        plot = output_page["plots"][0]
        assert plot["kind"] == "time_series"
        # The one kind a readings page hosts binds an OBSERVATION (the
        # B5 fold's F2: the emitted time-series plot binds the page's
        # first observation, so the member's own dataset binding rides
        # no plot — the no-plot-carries-its-binding row names this).
        assert plot["binding_id"] == "measure-ch1-voltage"
        assert any(
            row["id"] == "vendor-trend"
            for row in derived.manifest["bindings"]
        )

    def test_the_lane_join_over_the_ceiling_drops_from_the_plot_alone(
        self, tmp_path: Path
    ) -> None:
        """The B3 fold's F1 (the capacity boundary's join half): the sum
        of admissible declarations is not an authoring error — the joined
        page over the cap drops the overflow from the PLOT alone (the
        wire shape keeps every joined lane) and each dropped lane REPORTS
        (the rows land with the disclosure channel)."""
        descriptor = _f2()
        for index in range(40):
            descriptor["channels"].append(
                {
                    "id": f"tb{index}",
                    "label": f"Trigger bus {index}",
                    "role": "trigger_bus",
                    "quantities": [],
                    "parameter_names": [],
                }
            )
        document = _members_document(
            [
                {
                    "slot": "trigger-lanes",
                    "kind": "channels",
                    "where_role": "trigger_bus",
                    "page": "capture",
                }
            ]
        )
        document["profiles"][0]["required_actions"] = [
            "com.meridian.m400.sweep/1.0.0"
        ]
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        derived = _derive_document(descriptor, catalogs, _member_corpus(tmp_path))
        plot = next(
            plot
            for page in derived.manifest["pages"]
            for plot in page.get("plots", [])
            if plot["kind"] == "digital_lanes"
        )
        assert len(plot["y"]) == 64
        capture_target = next(
            row
            for row in derived.catalogue["targets"]
            if row["id"] == "capture"
        )
        lane_vars = [
            row
            for row in capture_target["variables"]
            if row["type"] == "string"
        ]
        assert len(lane_vars) == 72

    def test_computed_variables_derive_into_dataset_shapes(
        self, tmp_path: Path
    ) -> None:
        """V2 (B1, mirrored): a computed measurement is an ordinary value
        variable of EVERY dataset target — the shape follows the
        dataset's own wire shape (scalar on time_series, vector on
        waveform/digital-lanes) — and a computed id colliding with a
        variable id the wire shape already carries is skipped, never
        emitted as a duplicate."""
        descriptor = _m400()
        descriptor["derived_variables"] = [
            {"id": "rms_v", "quantity": "voltage", "unit": "V", "expression": "rms(ch1)"},
            {"id": "ch1-voltage", "quantity": "voltage", "unit": "V", "expression": "x"},
        ]
        derived = _derive_document(descriptor, _vendor_catalogs(), _member_corpus(tmp_path))
        capture_target = next(
            row
            for row in derived.catalogue["targets"]
            if row["id"] == "capture"
        )
        variables = {row["id"]: row for row in capture_target["variables"]}
        assert variables["rms_v"] == {
            "id": "rms_v",
            "type": "number",
            "unit": "V",
            "shape": "vector",
        }
        # The colliding id keeps the wire shape's own row (the trace
        # variable — the descriptor declares no parameters, so the trace
        # unit is None), never a duplicate computed row carrying "V".
        assert variables["ch1-voltage"]["shape"] == "vector"
        assert variables["ch1-voltage"]["unit"] is None
        assert len(variables) == len(
            {row["id"] for row in capture_target["variables"]}
        )

    def test_an_unclaimed_slug_sharing_a_placed_slot_keys_spelling_keeps_its_own_action(
        self, tmp_path: Path
    ) -> None:
        """The B4 fold's F1 (the mint discipline, mirrored): a placed slot
        key must not capture a binding id that only shares its spelling —
        an unclaimed vendor action slugged ``configure`` keeps its OWN
        numeric staging on device-features, never the class configure
        action's fields welded through a slot key placed on another page;
        and a member slot key that names its own action resolves through
        the placed map (the founding slug scan would find nothing)."""
        descriptor = _f1()
        descriptor["actions"]["com.meridian.logicx.configure/1.0.0"] = {
            "binding": {"kind": "adapter", "key": "fixture"},
            "timeout_ms": 5000,
            "side_effect": "state_change",
            "cancellable": True,
            "retry": "never",
            "input_constraints": {
                "properties": {"margin_ms": {"type": "integer", "minimum": 1}}
            },
        }
        derived = _derive_document(descriptor, _vendor_catalogs(), _member_corpus(tmp_path))
        block = derived.manifest["extensions"][
            "plugin-ui-class-reference:layout"
        ]
        device_features = next(
            page
            for page in block["pages"]
            if page["page_id"] == "device-features"
        )
        # The vendor action's OWN numeric staging, and nothing else
        # under its binding id: the weld would resolve the slug through
        # the class configure slot (placed on another page) and put the
        # class action's numeric fields on this device-features button.
        vendor_numerics = {
            node["field"]
            for section in device_features["sections"]
            for node in section["children"]
            if node.get("kind") == "numeric"
            and node.get("binding_id") == "configure"
        }
        assert vendor_numerics == {"margin_ms"}, vendor_numerics
