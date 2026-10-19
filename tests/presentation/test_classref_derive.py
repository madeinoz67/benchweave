"""The class-reference derivation module (L4 capability a; design record
2026-10-15 §1, parent record §3 semantics).

The gateway's own derivation over (descriptor × corpus reference); the SDK
is read-not-imported (REG-4) — agreement with the SDK expander is pinned by
the committed fixture documents (B8: canonical-JSON byte equality of the
derived triples on 2/2 fixtures, F1 and F2). Fail-closed cases carry the
same typed ``classref_*:`` refusals the parent record's §3.3 table names;
an unknown class fails OPEN (B3's fail-open arm — the fallback never
invents obligations the descriptor does not create).
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
    select_references,
)
from benchweave.vendoring import corpus_root

FIXTURES = Path(__file__).parent / "classref_fixtures"


def _vendor_catalogs() -> dict[str, bytes]:
    """Every invented vendor catalog the fixtures pin, keyed by digest —
    the admission store's resolution shape (L5 adds the trio catalog)."""
    catalogs: dict[str, bytes] = {}
    for name in ("vendor-catalog.json", "vendor-catalog-trio.json"):
        raw = (FIXTURES / name).read_bytes()
        catalogs[hashlib.sha256(raw).hexdigest()] = raw
    return catalogs


def _derive(tag: str) -> DerivedAttachment:
    descriptor_raw = (FIXTURES / f"descriptor-{tag}.json").read_bytes()
    decoder_raw = (FIXTURES / "decoder-uart.json").read_bytes()
    return derive_attachment(
        descriptor_raw,
        corpus=corpus_root(),
        vendor_catalogs=_vendor_catalogs(),
        decoder_docs={hashlib.sha256(decoder_raw).hexdigest(): decoder_raw},
    )


def _serialize(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2) + "\n").encode()


class TestParityB8:
    def test_f1_f2_triples_byte_equal_committed_sdk_fixtures(self) -> None:
        """B8 (4/4 after the L5 widening): the gateway derivation's
        canonical-JSON triples equal the committed SDK-expansion fixtures
        byte for byte — the two derivations agree over the same corpus
        reference bytes, decoder-carrying descriptors AND the F5 trio
        descriptor included. The F5 arm is the widening's parity proof:
        the SDK derives the device-features section at L2 with the
        [text, select, boolean] staging triad and the button; the mirrored
        gateway derivation emits the same bytes."""
        for tag in ("f1", "f2", "f1-da", "f5-trio"):
            derived = _derive(tag)
            for kind in ("envelope", "manifest", "catalogue"):
                committed = (FIXTURES / f"fixture-{tag}-{kind}.json").read_bytes()
                produced = _serialize(getattr(derived, kind))
                assert produced == committed, (
                    f"{tag}/{kind}: gateway derivation diverges from the "
                    f"committed SDK fixture\n--- gateway ---\n"
                    f"{produced[:800].decode()}\n--- committed ---\n"
                    f"{committed[:800].decode()}"
                )
                # The JSON loads too: bytes equal, documents equal.
                assert json.loads(produced) == json.loads(committed)
            assert derived.profile_ids == ("otdp.logic_analyser/1.0.0",)

    def test_f5_trio_derives_the_staging_section_at_l2(self) -> None:
        """The L5 widening's proof surface (B1 extends to F5): the invented
        vendor action ``com.veridian-labs.auto-band/1.0.0`` requires a free
        string, an enum and a boolean — all three expressible — so the
        device-features page derives a section whose children are the
        [text, select, boolean] staging nodes followed by the button. The
        pre-widening derivation rates the action non-numeric -> L0, emits
        NO section, and this arm reddens."""
        derived = _derive("f5-trio")
        block = derived.manifest["extensions"]["plugin-ui-class-reference:layout"]
        page = next(
            page for page in block["pages"] if page["page_id"] == "device-features"
        )
        children = page["sections"][0]["children"]
        assert [(node.get("kind"), node.get("field")) for node in children] == [
            ("text", "label"),
            ("select", "band_class"),
            ("boolean", "holdoff_enable"),
            ("button", None),
        ]

    def test_field_rows_emit_the_trio_modes_and_text_bounds(self) -> None:
        """The widened ``_field_rows`` (mirrored from the SDK expander):
        the F2 ruling's per-mode rows, and a free string's declared bounds
        ride the row's ``minLength``/``maxLength``. The F5 fixture's free
        string declares no bound, so this arm — not the parity fixture —
        pins the bounded-text branch (mirrors the SDK's trio modes test)."""
        from benchweave.presentation.classref import _field_rows

        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "bounded": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 8,
                },
                "band_class": {"enum": ["wide", "narrow"]},
                "holdoff_enable": {"type": "boolean"},
                "count": {"type": "integer", "minimum": 0},
                "fixed": {"const": 1.5},
                "patterned": {"type": "string", "pattern": "^[A-Z]{4}$"},
            },
        }
        rows = {row["field"]: row for row in _field_rows("urn:t/1.0.0", "", schema)}
        assert {name: row["mode"] for name, row in rows.items()} == {
            "label": "text",
            "bounded": "text",
            "band_class": "enum",
            "holdoff_enable": "boolean",
            "count": "numeric",
            "fixed": "const",
        }  # `patterned` — a pattern-narrowed string — emits no row
        assert rows["bounded"]["minLength"] == 1
        assert rows["bounded"]["maxLength"] == 8
        assert "minLength" not in rows["label"]
        assert "maxLength" not in rows["label"]

    def test_inexpressible_required_field_keeps_l0(self) -> None:
        """The L2 test widens from all-numeric to all-expressible: a
        required free string derives L2, a required pattern-narrowed
        string stays L0 (no row -> inexpressible; mirrors the SDK's
        ``test_pattern_narrowed_string_keeps_l0``)."""
        from benchweave.presentation.classref import _ladder_level

        free: dict[str, Any] = {
            "required": ["label"],
            "properties": {"label": {"type": "string"}},
        }
        assert _ladder_level(free, frozenset(), None) == "L2"
        patterned: dict[str, Any] = {
            "required": ["format"],
            "properties": {"format": {"type": "string", "pattern": "^[A-Z]{4}$"}},
        }
        assert _ladder_level(patterned, frozenset(), None) == "L0"
        mixed: dict[str, Any] = {
            "required": ["label", "format"],
            "properties": {
                "label": {"type": "string"},
                "format": {"type": "string", "pattern": "^[A-Z]{4}$"},
            },
        }
        assert _ladder_level(mixed, frozenset(), None) == "L0"

    def test_mode_kind_mapping_carries_the_f2_ruling(self) -> None:
        """The F2 ruling: a literal const emits a select node — the landed
        contract row and the renderer both say a const renders the
        read-only fixed display (mirrors the SDK's mapping test)."""
        from benchweave.presentation.classref import _MODE_KIND

        assert _MODE_KIND == {
            "numeric": "numeric",
            "text": "text",
            "const": "select",
            "enum": "select",
            "boolean": "boolean",
        }

    def test_derived_resources_carry_every_asset_and_the_manifest(self) -> None:
        """The resources map the composition hands the validator carries
        the manifest bytes plus every declared asset's exact bytes —
        ``_resource``'s digest gate (validator side) must find each."""
        for tag in ("f1", "f2", "f5-trio"):
            derived = _derive(tag)
            assert "manifest.json" in derived.resources
            for asset in derived.manifest["assets"]:
                path = str(asset["path"])
                assert path in derived.resources
                assert (
                    hashlib.sha256(derived.resources[path]).hexdigest()
                    == asset["sha256"]
                )

    def test_triples_validate_through_validate_attachment(self) -> None:
        """B2's module-level arm: every derived triple passes the unchanged
        ``validate_attachment`` (valid=true) — the composition never sees a
        derivation the validator rejects. The supported-panel set is the
        REGISTRY's derived value, never a fabricated id: the two-slash
        literal a test once fabricated is a string no legal manifest can
        declare (the schema's panel_id pattern admits one slash). The F5
        trio arm proves the widened node kinds (text/select/boolean)
        survive the unchanged validator — the layout block's only
        authority."""
        from benchweave.interfaces.ui_presentation import _pin_scoped_documents
        from benchweave.presentation.admission import validate_attachment
        from benchweave.presentation.panels import SUPPORTED_PANELS

        for tag in ("f1", "f2", "f1-da", "f5-trio"):
            derived = _derive(tag)
            descriptor_raw = (FIXTURES / f"descriptor-{tag}.json").read_bytes()
            report = validate_attachment(
                derived.envelope_raw,
                descriptor_raw=descriptor_raw,
                verified_resources=derived.resources,
                binding_catalogue=derived.catalogue,
                schema_documents=_pin_scoped_documents(json.loads(descriptor_raw)),
                supported_features=frozenset(),
                supported_panels=SUPPORTED_PANELS,
                firmware="1.0",
            )
            assert report.valid, report.findings


class TestDecoderDerivation:
    """The decoder behaviors the derivation mirrors from the SDK expander
    (v0.15.0 after the L5 pointer leg; the fixtures on this branch were
    regenerated from v0.14.0's derivation against the 0.2.0 corpus and
    stamp-only re-derived against the 0.3.0 corpus at L11 — REG-4):
    pinned-decoder lane rows, the
    annotation form's capture rebinding, and the decode binding's page
    append on the plot page."""

    def test_decoder_lanes_derive_from_admitted_decoder_documents(self) -> None:
        derived = _derive("f1-da")
        plot_page = next(page for page in derived.manifest["pages"] if page.get("plots"))
        plot = plot_page["plots"][0]
        lanes = plot["decoder_lanes"]
        assert len(lanes) == 1, lanes
        row = lanes[0]
        assert row["id"] == "decode-uart"
        assert row["label"] == "UART"
        assert row["decoder"] == "uart"
        assert row["settings"] == {"rx": "d0", "tx": "d1"}
        assert row["source_channel_ids"] == ["d0", "d1"]
        # decode is DECLARED on f1-da: the lanes name the decode binding.
        assert row["binding_id"] == "decode"
        # The plot page carries the decode binding (the page append).
        assert plot_page["bindings"] == ["capture", "decode"]

    def test_annotation_only_descriptor_rebinds_lanes_to_capture(self) -> None:
        """The annotation form (decode_annotated declared, the plain decode
        action absent) binds the lanes to the CAPTURE dataset binding — no
        decode target exists to carry them — while the page append still
        lists the decode slot key (the SDK's own emission, mirrored)."""
        raw = json.loads((FIXTURES / "descriptor-f1-da.json").read_bytes())
        del raw["actions"]["otdp.logic_analyser.decode/1.0.0"]
        derived = _derive_from_document(raw)
        plot_page = next(page for page in derived.manifest["pages"] if page.get("plots"))
        lanes = plot_page["plots"][0]["decoder_lanes"]
        assert [row["binding_id"] for row in lanes] == ["capture"]
        binding_ids = {row["id"] for row in derived.manifest["bindings"]}
        assert "decode" not in binding_ids
        assert plot_page["bindings"] == ["capture", "decode"]

    def test_unresolvable_decoder_pin_skips_the_decoder(self) -> None:
        """A pin the resolution source cannot serve skips that decoder (the
        SDK's unreadable-document arm), never a partial lane."""
        descriptor_raw = (FIXTURES / "descriptor-f1-da.json").read_bytes()
        derived = derive_attachment(
            descriptor_raw,
            corpus=corpus_root(),
            vendor_catalogs=_vendor_catalogs(),
            decoder_docs={},
        )
        plot_page = next(page for page in derived.manifest["pages"] if page.get("plots"))
        assert plot_page["plots"][0]["decoder_lanes"] == []


class TestSelection:
    def test_unknown_class_selects_no_reference(self) -> None:
        """The fail-open signal: a descriptor whose profiles name no class
        with a corpus reference selects NOTHING (the composition then
        renders today's no-attachment absence — B3). The exemplar
        ROTATES with the sweep: dc_psu carried this arm until L11 gave it
        a reference, dmm until L12, oscilloscope until L13;
        function_generator (the L14 slot, unwritten) carries it now —
        when L14 lands its reference, the exemplar advances again."""
        descriptor = {
            "otdp_version": "0.2.3",
            "id": "dev.example.scalar",
            "profiles": ["otdp.function_generator/1.0.0"],
        }
        assert select_references(corpus_root(), descriptor) is None

    def test_selection_is_bytewise_sorted_first_with_a_reference(self) -> None:
        """Reference selection: profiles sorted bytewise; a profile
        without a corpus reference is skipped and the next one applies.
        The skipped profile ROTATES with the sweep: dc_psu until L11,
        dmm until L12, oscilloscope until L13; function_generator (the
        L14 slot, unwritten — sorted after the analyser bytewise) carries
        the skip arm now — and the corpus pairs add their own
        multi-profile arms below."""
        descriptor = {
            "otdp_version": "0.2.3",
            "id": "dev.example.multi",
            "profiles": ["otdp.logic_analyser/1.0.0", "otdp.function_generator/1.0.0"],
        }
        selected = select_references(corpus_root(), descriptor)
        assert selected is not None and len(selected) == 1
        assert selected[0]["profile_id"] == "otdp.logic_analyser/1.0.0"

    def test_a_two_reference_descriptor_selects_both_sorted_dmm(self) -> None:
        """L12: with the dmm reference in the corpus, a descriptor
        declaring it beside the analyser selects BOTH — sorted bytewise
        (dmm before logic_analyser)."""
        descriptor = {
            "otdp_version": "0.2.3",
            "id": "dev.example.multi",
            "profiles": ["otdp.logic_analyser/1.0.0", "otdp.dmm/1.0.0"],
        }
        selected = select_references(corpus_root(), descriptor)
        assert selected is not None and len(selected) == 2
        assert [r["profile_id"] for r in selected] == [
            "otdp.dmm/1.0.0",
            "otdp.logic_analyser/1.0.0",
        ]

    def test_a_two_reference_descriptor_selects_both_sorted(self) -> None:
        """L11: with the dc_psu reference in the corpus, a descriptor
        declaring both classes selects BOTH — sorted bytewise (dc_psu
        before logic_analyser) — the multi-profile merge input (parent
        §3.8)."""
        descriptor = {
            "otdp_version": "0.2.3",
            "id": "dev.example.multi",
            "profiles": ["otdp.logic_analyser/1.0.0", "otdp.dc_psu/1.0.0"],
        }
        selected = select_references(corpus_root(), descriptor)
        assert selected is not None and len(selected) == 2
        assert [r["profile_id"] for r in selected] == [
            "otdp.dc_psu/1.0.0",
            "otdp.logic_analyser/1.0.0",
        ]


class TestRefusals:
    """The fail-closed table (parent record §3.3), gateway-side."""

    def _descriptor(self, **overrides: Any) -> dict[str, Any]:
        raw: dict[str, Any] = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        raw.update(overrides)
        return raw

    def test_zero_digital_input_channels_refuses_classref_no_lanes(self) -> None:
        raw = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        raw["channels"] = [
            {"id": "a1", "label": "Analog one", "role": "source", "quantities": []}
        ]
        with pytest.raises(ClassRefusal, match="^classref_no_lanes:"):
            _derive_from_document(raw)

    def test_lane_ceiling_refuses_at_65(self) -> None:
        raw = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        raw["channels"] = [
            {
                "id": f"d{index}",
                "label": f"Data line {index}",
                "role": "digital_input",
                "quantities": ["digital_level"],
            }
            for index in range(65)
        ]
        with pytest.raises(ClassRefusal, match="^classref_lane_ceiling:"):
            _derive_from_document(raw)

    def test_missing_required_action_refuses_classref_required_action_absent(
        self,
    ) -> None:
        raw = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        del raw["actions"]["otdp.logic_analyser.abort/1.0.0"]
        with pytest.raises(ClassRefusal, match="^classref_required_action_absent:"):
            _derive_from_document(raw)

    def test_unadmitted_vendor_catalog_refuses_classref_unknown_action(
        self,
    ) -> None:
        """The gateway resolution source is the ADMISSION store (design
        §1: read-time composition over admitted bytes); a pinned vendor
        catalog that is not admitted refuses typed, never silent."""
        descriptor_raw = (FIXTURES / "descriptor-f1.json").read_bytes()
        with pytest.raises(ClassRefusal, match="^classref_unknown_action:"):
            derive_attachment(
                descriptor_raw,
                corpus=corpus_root(),
                vendor_catalogs={},
            )

    def test_tampered_vendor_catalog_bytes_refuse(self) -> None:
        raw = (FIXTURES / "vendor-catalog.json").read_bytes() + b" "
        descriptor_raw = (FIXTURES / "descriptor-f1.json").read_bytes()
        with pytest.raises(ClassRefusal, match="classref_unknown_action:"):
            derive_attachment(
                descriptor_raw,
                corpus=corpus_root(),
                vendor_catalogs={hashlib.sha256(raw).hexdigest(): raw},
            )

    def test_satisfies_target_compares_per_parsed_operator(self) -> None:
        """The target grammar's four operators (parent record §2.2
        admission-fold note), tested at the comparator."""
        from benchweave.presentation.classref import _satisfies_target

        assert _satisfies_target("0.3.1", ">=0.3.1") is True
        assert _satisfies_target("0.3.0", ">=0.3.1") is False
        assert _satisfies_target("0.3.2", ">0.3.1") is True
        assert _satisfies_target("0.3.1", ">0.3.1") is False
        assert _satisfies_target("0.3.0", "<0.3.1") is True
        assert _satisfies_target("0.3.1", "<0.3.1") is False
        assert _satisfies_target("0.3.1", "<=0.3.1") is True
        assert _satisfies_target("0.4.0", "<=0.3.1") is False

    def test_invalid_reference_document_refuses_classref_invalid_reference(
        self,
    ) -> None:
        from benchweave.presentation.classref import validate_reference_document

        with pytest.raises(ClassRefusal, match="^classref_invalid_reference:"):
            validate_reference_document(
                {"profile_id": "otdp.logic_analyser/1.0.0"},
                corpus=corpus_root(),
            )

    def test_unknown_slot_cross_object_check_refuses(self) -> None:
        """The cross-object key check the schema cannot express (parent
        §3.3's ``classref_unknown_slot``): a page binding a slot key absent
        from the reference's slots refuses."""
        reference = json.loads(
            (corpus_root() / "plugin-ui-class-reference/0.3.0/class-logic_analyser.json")
            .read_bytes()
        )
        reference["pages"][0]["binding_slots"].append("ghost-slot")
        with pytest.raises(ClassRefusal, match="^classref_unknown_slot:"):
            _derive_from_document(
                json.loads((FIXTURES / "descriptor-f1.json").read_bytes()),
                references_override=[reference],
            )


class TestReferenceIntegrity:
    """Corpus-integrity arms of the selection walk: a reference file the
    corpus pins but whose bytes (or parse) fail is a LOUD typed refusal —
    the same corpus-pin gate loudness every other family read carries —
    never a silent skip that renders the plain no-attachment absence
    (the fail-closed table's posture; the design record §1 table's
    ``fail-closed`` row)."""

    def _tampered_corpus(self, tmp_path: Path) -> Path:
        copy = tmp_path / "standards"
        shutil.copytree(corpus_root(), copy)
        return copy

    def _re_pin(self, corpus: Path, relpath: str, raw: bytes) -> None:
        """Point the copied corpus manifest's pin at the new bytes, so the
        arm exercises the DOCUMENT's corruption, not the pin's."""
        manifest_path = corpus / "corpus-manifest.json"
        document = json.loads(manifest_path.read_bytes())
        for row in document["files"]:
            if str(row["path"]) == relpath:
                row["sha256"] = hashlib.sha256(raw).hexdigest()
        manifest_path.write_bytes((json.dumps(document, indent=2) + "\n").encode())

    def test_pin_mismatched_reference_refuses_typed_never_silence(
        self, tmp_path: Path
    ) -> None:
        corpus = self._tampered_corpus(tmp_path)
        relpath = "plugin-ui-class-reference/0.3.0/class-logic_analyser.json"
        tampered = (corpus / relpath).read_bytes() + b"\n"
        (corpus / relpath).write_bytes(tampered)
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        with pytest.raises(ClassRefusal, match="^corpus_pin_mismatch:"):
            select_references(corpus, descriptor)

    def test_malformed_reference_bytes_refuse_typed_never_silence(
        self, tmp_path: Path
    ) -> None:
        corpus = self._tampered_corpus(tmp_path)
        relpath = "plugin-ui-class-reference/0.3.0/class-logic_analyser.json"
        (corpus / relpath).write_bytes(b"{not json")
        self._re_pin(corpus, relpath, b"{not json")
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        with pytest.raises(ClassRefusal, match="^classref_invalid_reference:"):
            select_references(corpus, descriptor)


def _derive_from_document(
    document: dict[str, Any],
    *,
    references_override: list[dict[str, Any]] | None = None,
) -> DerivedAttachment:
    """A raw-bytes derivation with the vendor catalog admitted, for the
    refusal arms that mutate the descriptor document."""
    descriptor_raw = json.dumps(document).encode()
    decoder_raw = (FIXTURES / "decoder-uart.json").read_bytes()
    return derive_attachment(
        descriptor_raw,
        corpus=corpus_root(),
        vendor_catalogs=_vendor_catalogs(),
        decoder_docs={hashlib.sha256(decoder_raw).hexdigest(): decoder_raw},
        references_override=references_override,
    )
