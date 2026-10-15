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
    raw = (FIXTURES / "vendor-catalog.json").read_bytes()
    return {hashlib.sha256(raw).hexdigest(): raw}


def _derive(tag: str) -> DerivedAttachment:
    descriptor_raw = (FIXTURES / f"descriptor-{tag}.json").read_bytes()
    return derive_attachment(
        descriptor_raw,
        corpus=corpus_root(),
        vendor_catalogs=_vendor_catalogs(),
    )


def _serialize(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2) + "\n").encode()


class TestParityB8:
    def test_f1_f2_triples_byte_equal_committed_sdk_fixtures(self) -> None:
        """B8 (2/2): the gateway derivation's canonical-JSON triples equal
        the committed SDK-expansion fixtures byte for byte — the two
        derivations agree over the same corpus reference bytes."""
        for tag in ("f1", "f2"):
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

    def test_derived_resources_carry_every_asset_and_the_manifest(self) -> None:
        """The resources map the composition hands the validator carries
        the manifest bytes plus every declared asset's exact bytes —
        ``_resource``'s digest gate (validator side) must find each."""
        for tag in ("f1", "f2"):
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
        derivation the validator rejects."""
        from benchweave.interfaces.ui_presentation import _pin_scoped_documents
        from benchweave.presentation.admission import validate_attachment

        for tag in ("f1", "f2"):
            derived = _derive(tag)
            descriptor_raw = (FIXTURES / f"descriptor-{tag}.json").read_bytes()
            report = validate_attachment(
                derived.envelope_raw,
                descriptor_raw=descriptor_raw,
                verified_resources=derived.resources,
                binding_catalogue=derived.catalogue,
                schema_documents=_pin_scoped_documents(json.loads(descriptor_raw)),
                supported_features=frozenset(),
                supported_panels=frozenset({"benchweave/classref-logic-analyser/0.1.0"}),
                firmware="1.0",
            )
            assert report.valid, report.findings


class TestSelection:
    def test_unknown_class_selects_no_reference(self) -> None:
        """The fail-open signal: a descriptor whose profiles name no class
        with a corpus reference selects NOTHING (the composition then
        renders today's no-attachment absence — B3)."""
        descriptor = {
            "otdp_version": "0.2.3",
            "id": "dev.example.scalar",
            "profiles": ["otdp.dc_psu/1.0.0"],
        }
        assert select_references(corpus_root(), descriptor) is None

    def test_selection_is_bytewise_sorted_first_with_a_reference(self) -> None:
        """Reference selection: profiles sorted bytewise; the first profile
        WITH a reference applies; profiles without one are skipped."""
        descriptor = {
            "otdp_version": "0.2.3",
            "id": "dev.example.multi",
            "profiles": ["otdp.logic_analyser/1.0.0", "otdp.dc_psu/1.0.0"],
        }
        selected = select_references(corpus_root(), descriptor)
        assert selected is not None and len(selected) == 1
        assert selected[0]["profile_id"] == "otdp.logic_analyser/1.0.0"


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
            (corpus_root() / "plugin-ui-class-reference/0.1.0/class-logic_analyser.json")
            .read_bytes()
        )
        reference["pages"][0]["binding_slots"].append("ghost-slot")
        with pytest.raises(ClassRefusal, match="^classref_unknown_slot:"):
            _derive_from_document(
                json.loads((FIXTURES / "descriptor-f1.json").read_bytes()),
                references_override=[reference],
            )


def _derive_from_document(
    document: dict[str, Any],
    *,
    references_override: list[dict[str, Any]] | None = None,
) -> DerivedAttachment:
    """A raw-bytes derivation with the vendor catalog admitted, for the
    refusal arms that mutate the descriptor document."""
    descriptor_raw = json.dumps(document).encode()
    return derive_attachment(
        descriptor_raw,
        corpus=corpus_root(),
        vendor_catalogs=_vendor_catalogs(),
        references_override=references_override,
    )
