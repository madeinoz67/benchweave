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
from benchweave.standards.manifest import active_version_from_corpus
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
        """B8 (5/5 after the plot-kind mirror): the gateway derivation's
        canonical-JSON triples equal the committed SDK-expansion fixtures
        byte for byte — the two derivations agree over the same corpus
        reference bytes, decoder-carrying descriptors, the F5 trio
        descriptor AND the numeric smu pair included. The F5 arm is the
        L5 widening's parity proof: the SDK derives the device-features
        section at L2 with the [text, select, boolean] staging triad and
        the button; the mirrored gateway derivation emits the same bytes.
        The f6-smu arm is the plot-kind mirror's: the readings expansion
        (observation bindings and tiles), the slot-aware measure target
        and the time_series plot bound to the page's first observation —
        generated from the widened SDK expander at the v0.18.0 pin (the
        convention's oracle, design record §5.2)."""
        for tag in ("f1", "f2", "f1-da", "f5-trio", "f6-smu"):
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
            # The founding tags derive the analyser; the numeric tag the
            # smu pair (the mirror's own class).
            expected_profile = (
                "otdp.smu/1.0.0"
                if tag == "f6-smu"
                else "otdp.logic_analyser/1.0.0"
            )
            assert derived.profile_ids == (expected_profile,)

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

        for tag in ("f1", "f2", "f1-da", "f5-trio", "f6-smu"):
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


# --- the plot-kind mirror (issue #521; design record §5.3) -----------------------


def _active_family() -> dict[str, tuple[str, dict[str, Any]]]:
    """The ACTIVE family's classes, discovered by walking the corpus's
    ``class-*.json`` (the census instrument's family_profile_ids pattern):
    profile id -> (slug, reference document). The family's schema files
    also match the glob and are skipped; membership is never a literal
    list, so a ninth class widens the plot-kind arms by itself."""
    family_dir = (
        corpus_root()
        / "plugin-ui-class-reference"
        / active_version_from_corpus(corpus_root(), "plugin-ui-class-reference")
    )
    family: dict[str, tuple[str, dict[str, Any]]] = {}
    for path in sorted(family_dir.glob("class-*.json")):
        document = json.loads(path.read_bytes())
        if not isinstance(document, dict) or "profile_id" not in document:
            continue  # the family schema files also match the glob
        family[str(document["profile_id"])] = (
            path.stem.removeprefix("class-"),
            document,
        )
    return family


def _plot_classes(kind: str) -> dict[str, tuple[str, dict[str, Any]]]:
    """The family members whose page template authors a plot of ``kind`` —
    the reference's own declaration, never a class list."""
    return {
        profile_id: pair
        for profile_id, pair in _active_family().items()
        if any(
            str((page.get("plot") or {}).get("kind")) == kind
            for page in pair[1].get("pages", [])
        )
    }


def _committed_example(slug: str) -> Path:
    """The committed OTDP class example paired with a reference — the
    corpus's own descriptor for the class, at the ACTIVE otdp version."""
    return (
        corpus_root()
        / "otdp"
        / active_version_from_corpus(corpus_root(), "otdp")
        / "examples"
        / f"class-{slug}.json"
    )


def _numeric_channels(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> list[dict[str, Any]]:
    """The channels the reference's channels-kind slot resolves (the slot
    found BY KIND — the key varies across classes: channels, inputs,
    outputs — with the slot's own role filter, declaration order): the
    derivation's lane input."""
    slot = next(
        (row for row in reference["slots"].values() if row.get("kind") == "channels"),
        None,
    )
    assert slot is not None, sorted(reference["slots"])
    role = str(slot.get("where_role", ""))
    return [row for row in descriptor["channels"] if str(row.get("role")) == role]


def _variable_ids(reference: dict[str, Any], descriptor: dict[str, Any]) -> list[str]:
    """The (channel, quantity) variable ids the widened SDK expander emits —
    ``{channel id}-{quantity}``, lane-major over quantity declaration order
    (the convention read from ``benchweave_sdk.classref`` at the v0.18.0
    pin; the f6-smu parity fixture pins it byte for byte)."""
    return [
        f"{row['id']}-{quantity}"
        for row in _numeric_channels(reference, descriptor)
        for quantity in (row.get("quantities") or [])
    ]


def _the_plot(derived: DerivedAttachment) -> tuple[dict[str, Any], dict[str, Any]]:
    """(page row, plot row) for the derived manifest's plot page — the
    numeric classes author exactly one plot page with one plot."""
    pages_with_plots = [page for page in derived.manifest["pages"] if page.get("plots")]
    assert len(pages_with_plots) == 1, [page["id"] for page in pages_with_plots]
    page = pages_with_plots[0]
    assert len(page["plots"]) == 1, page["plots"]
    return page, page["plots"][0]


def _bound_variables(
    derived: DerivedAttachment, plot: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """The plot's bound target's variables, by id — the axes' resolution
    (the manifest's binding row through to the catalogue's target)."""
    bindings = {row["id"]: row for row in derived.manifest["bindings"]}
    targets = {row["id"]: row for row in derived.catalogue["targets"]}
    binding = bindings.get(str(plot["binding_id"]), {})
    target = targets.get(str(binding.get("target_id", "")), {})
    return {row["id"]: row for row in target.get("variables", [])}


def _plot_page_kind(reference: dict[str, Any]) -> str:
    """The kind of the reference's plot page (a dataset page carries the
    plot beside its dataset binding; a readings page admits observation
    bindings only)."""
    page = next(page for page in reference["pages"] if page.get("plot"))
    return str(page.get("kind", "readings"))


def _assert_pair_validates(
    derived: DerivedAttachment,
    descriptor_raw: bytes,
    reference: dict[str, Any],
    page_id: str,
) -> None:
    """Acceptance 3's validation half, scoped by the pair's own plot-page
    kind (discovered from the reference, never a class list). A
    DATASET-page pair's derived triple passes the unchanged
    ``validate_attachment`` (valid=true) — the serving lie's closure
    proof: these are the pairs whose pre-mirror derivation validated AND
    served the wrong-kind plot.

    A READINGS-page pair's assertion below records a PRE-EXISTING STATE,
    not an expectation: before this slice, all four readings pairs
    (dc_psu, dmm, electronic_load, smu — measured against HEAD) derived
    valid=False with exactly ONE ``invalid_plot`` finding, because the
    committed OTDP examples declare zero readable parameters, so the
    readings page carries no observation bindings while the plot binds
    the dataset slot (issue #525 tracks the corpus gap; the fix belongs
    there, never in this slice). The assertion pins that state — it
    REDS on a second finding and on any change to the finding's shape
    (code or path) — the old state is pinned, not blessed. The
    parameters-carrying readings pair validates clean (f6-smu,
    TestParityB8's validator arm): the readings path itself is sound
    once the descriptor owes what the reference authors."""
    from benchweave.interfaces.ui_presentation import _pin_scoped_documents
    from benchweave.presentation.admission import validate_attachment
    from benchweave.presentation.panels import SUPPORTED_PANELS

    descriptor = json.loads(descriptor_raw)
    firmware = (descriptor.get("identity", {}).get("supported_firmware") or ["0"])[0]
    report = validate_attachment(
        derived.envelope_raw,
        descriptor_raw=descriptor_raw,
        verified_resources=derived.resources,
        binding_catalogue=derived.catalogue,
        schema_documents=_pin_scoped_documents(descriptor),
        supported_features=frozenset(),
        supported_panels=SUPPORTED_PANELS,
        firmware=str(firmware),
    )
    if _plot_page_kind(reference) == "readings":
        assert [(row.code, row.path) for row in report.findings] == [
            ("invalid_plot", f"pages.{page_id}.plots")
        ], report.findings
    else:
        assert report.valid, report.findings


class TestPlotKindEmission:
    """The plot-kind mirror arms (issue #521 — the serving lie; design
    record ``2026-10-21-classref-plot-kind-mirror-design.md`` §5.3): a
    numeric class's derived plot carries the reference's own plot kind —
    ``time_series``/``waveform`` over the SDK's (channel, quantity)
    variable convention — never the founding class's unconditional
    ``digital_lanes`` emission. The founding class's byte-identity is
    TestParityB8's (the four committed fixtures do not move); these arms
    pin the numeric half of the family, DISCOVERED by walking the ACTIVE
    family so a ninth class joins the arms by itself."""

    def test_the_family_carries_both_numeric_plot_kinds(self) -> None:
        """The arms' sample statement, from the corpus walk (never a
        literal): the family carries the founding lanes class, at least one
        ``time_series`` author and at least one ``waveform`` author — the
        two arms below are never vacuous."""
        family = _active_family()
        assert "otdp.logic_analyser/1.0.0" in family, sorted(family)
        assert _plot_classes("time_series"), sorted(family)
        assert _plot_classes("waveform"), sorted(family)

    @pytest.mark.parametrize("profile_id", sorted(_plot_classes("time_series")))
    def test_a_time_series_reference_derives_the_time_series_plot(
        self, profile_id: str
    ) -> None:
        """The committed pair derives the reference's own kind: exactly one
        plot, ``time_series``, over the dataset binding, with NO
        ``lane_groups`` and NO ``decoder_lanes`` (the manifest schema's
        analog branch bans both), ``y`` exactly the (channel, quantity)
        variable ids, and the bound target's x variable the receipt-time
        scalar in seconds (the canonical validator's own rule)."""
        slug, reference = _active_family()[profile_id]
        descriptor_path = _committed_example(slug)
        descriptor_raw = descriptor_path.read_bytes()
        derived = derive_attachment(descriptor_raw, corpus=corpus_root())
        page, plot = _the_plot(derived)
        assert plot["kind"] == "time_series", plot
        assert "lane_groups" not in plot, plot
        assert "decoder_lanes" not in plot, plot
        assert plot["x"] == "time", plot
        assert plot["y"] == _variable_ids(reference, json.loads(descriptor_raw))
        variables = _bound_variables(derived, plot)
        x_var = variables[plot["x"]]
        assert x_var["axis_role"] == "receipt_time", x_var
        assert (x_var["type"], x_var["unit"], x_var["shape"]) == (
            "number",
            "s",
            "scalar",
        ), x_var
        for name in plot["y"]:
            row = variables[name]
            assert (row["type"], row["shape"]) == ("number", "scalar"), row
        _assert_pair_validates(derived, descriptor_raw, reference, str(page["id"]))

    def test_a_numeric_series_ceiling_refuses_typed(self) -> None:
        """The analog y ceiling (the manifest schema's ``y maxItems 16``,
        the ``$defs.plot`` analog branch): a descriptor whose (channel,
        quantity) variable count exceeds it refuses typed
        (``classref_series_ceiling``, the lane-ceiling shape) — the
        gateway's fail-closed arm the SDK lacks at the pin (design §5.1's
        conditional: mirror an over-16 arm if the SDK ships one; it does
        not), so the schema never has to refuse diffusely. The mutated
        descriptor keeps the committed pair's class shape (nine channels
        of the slot's own role, two quantities each — 18 variables over
        the 16 ceiling, computed from the mutation, never a literal)."""
        profile_id = sorted(_plot_classes("time_series"))[0]
        slug, reference = _active_family()[profile_id]
        slot = next(
            row
            for row in reference["slots"].values()
            if row.get("kind") == "channels"
        )
        role = str(slot.get("where_role", ""))
        descriptor = json.loads(_committed_example(slug).read_bytes())
        descriptor["channels"] = [
            {
                "id": f"m{index}",
                "label": f"Numeric channel {index}",
                "role": role,
                "quantities": ["voltage", "current"],
            }
            for index in range(9)
        ]
        with pytest.raises(ClassRefusal, match="^classref_series_ceiling:"):
            derive_attachment(
                (json.dumps(descriptor) + "\n").encode(), corpus=corpus_root()
            )

    @pytest.mark.parametrize("profile_id", sorted(_plot_classes("waveform")))
    def test_a_waveform_reference_derives_the_waveform_plot(
        self, profile_id: str
    ) -> None:
        """The waveform twin: exactly one plot, ``waveform``, over the
        dataset binding, no group or decoder machinery, ``y`` the trace
        variable ids (array-valued — vector shape), the explicit time-axis
        x in seconds. The founding class's ``digital_lanes`` machinery
        never rides a numeric plot."""
        slug, reference = _active_family()[profile_id]
        descriptor_path = _committed_example(slug)
        descriptor_raw = descriptor_path.read_bytes()
        derived = derive_attachment(descriptor_raw, corpus=corpus_root())
        page, plot = _the_plot(derived)
        assert plot["kind"] == "waveform", plot
        assert "lane_groups" not in plot, plot
        assert "decoder_lanes" not in plot, plot
        assert plot["x"] == "t", plot
        assert plot["y"] == _variable_ids(reference, json.loads(descriptor_raw))
        variables = _bound_variables(derived, plot)
        x_var = variables[plot["x"]]
        assert (x_var["type"], x_var["unit"], x_var["shape"]) == (
            "number",
            "s",
            "vector",
        ), x_var
        for name in plot["y"]:
            row = variables[name]
            assert (row["type"], row["shape"]) == ("number", "vector"), row
        _assert_pair_validates(derived, descriptor_raw, reference, str(page["id"]))


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
        a reference, dmm until L12, oscilloscope until L13,
        function_generator until L14, electronic_load until L15, smu
        until L16, daq until L17; embedded_controller (the L18 slot,
        unwritten) carries it now — when L18 lands its reference, the
        exemplar advances again."""
        descriptor = {
            "otdp_version": "0.2.3",
            "id": "dev.example.scalar",
            "profiles": ["otdp.embedded_controller/1.0.0"],
        }
        assert select_references(corpus_root(), descriptor) is None

    def test_selection_is_bytewise_sorted_first_with_a_reference(self) -> None:
        """Reference selection: profiles sorted bytewise; a profile
        without a corpus reference is skipped and the next one applies.
        The skipped profile ROTATES with the sweep: dc_psu until L11,
        dmm until L12, oscilloscope until L13, function_generator until
        L14, electronic_load until L15, smu until L16, daq until L17;
        embedded_controller (the L18 slot, unwritten — sorted BEFORE
        the analyser bytewise as daq was, so the inverted shape
        carries: the unknown profile leads the sorted order and is
        skipped, the analyser second applies) carries the skip arm now
        — and the corpus pairs add their own multi-profile arms below."""
        descriptor = {
            "otdp_version": "0.2.3",
            "id": "dev.example.multi",
            "profiles": ["otdp.logic_analyser/1.0.0", "otdp.embedded_controller/1.0.0"],
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
