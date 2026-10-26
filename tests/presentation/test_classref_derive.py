"""The class-reference derivation module (L4 capability a; design record
2026-10-15 §1, parent record §3 semantics).

The gateway's own derivation over (descriptor × corpus reference); the SDK
is read-not-imported (REG-4) — agreement with the SDK expander is pinned by
the committed fixture documents (B8: canonical-JSON byte equality of the
derived triples — six tags from f1 through m400, seven with the dmm
fallback tag; the founding "2/2 fixtures" wording predates the L5, smu,
acceptance and fallback tags). Fail-closed cases carry the
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
    the admission store's resolution shape (L5 adds the trio catalog;
    the m400 tag adds its composed-class pin)."""
    catalogs: dict[str, bytes] = {}
    for name in (
        "vendor-catalog.json",
        "vendor-catalog-trio.json",
        "composed-burst.json",
    ):
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
        convention's oracle, design record §5.2). The m400 arm is the
        three-layer acceptance tag (issue #556 Track A): one descriptor
        carrying catalog, composed and custom resolutions at once,
        generated from the pinned v0.21.0 expander beside its
        composed-class pin. The dmm arm is the empty-page fallback's
        (issue #556, the B7 refute fold F2): a plain two-action DMM whose
        device-features page derives nothing — the SDK expander emits the
        fallback panel ("No additional device features."), and this tag
        pins those bytes on the gateway derivation too."""
        for tag in ("f1", "f2", "f1-da", "f5-trio", "f6-smu", "m400", "dmm"):
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
            # smu pair (the mirror's own class); the acceptance tag the
            # daq class.
            expected_profile = {
                "f6-smu": "otdp.smu/1.0.0",
                "m400": "otdp.daq/1.0.0",
                "dmm": "otdp.dmm/1.0.0",
            }.get(tag, "otdp.logic_analyser/1.0.0")
            assert derived.profile_ids == (expected_profile,)

    def test_w8_one_field_one_control_on_derived_pages(self) -> None:
        """W8 (issue #556 Track A; the SDK expander's fold, mirrored): a
        numeric staging node the section already carries is never
        re-emitted — the pair used to render twice on every derived page,
        catalogued pairs included (the pre-fold committed fixtures pinned
        the doubling; the regeneration at the v0.21.0 expander collapsed
        it, and this arm holds the mechanism on the derivation's own
        output, fixture-independent)."""
        for tag, binding, field in (
            ("f1", "auto-threshold", "margin_ppm"),
            ("f1", "auto-threshold", "hysteresis_mv"),
            ("f6-smu", "arm", "max_duration_ms"),
            ("f6-smu", "fetch", "max_bytes"),
        ):
            derived = _derive(tag)
            block = derived.manifest["extensions"][
                "plugin-ui-class-reference:layout"
            ]
            pairs = [
                (node.get("binding_id"), node.get("field"))
                for page in block["pages"]
                for section in page["sections"]
                for node in section.get("children", [])
                if node.get("kind") == "numeric"
            ]
            assert pairs.count((binding, field)) == 1, (tag, binding, field, pairs)

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

    def test_a_page_every_section_of_which_derives_empty_keeps_its_panel(
        self,
    ) -> None:
        """The empty-page fallback, mirrored from the SDK expander (the
        pinned v0.21.0 ``_build_layout``; issue #556, the B7 refute fold
        F2): every declared page renders as a panel — a page whose surface
        is fully placed (the dmm's device-features page: both actions sit
        on named slots, the vendor-actions slot owns nothing) derives the
        honest disclosure body, never an omitted page. The body is the
        template's ``vendor_features`` branch ("No additional device
        features."), the SDK's own wording; a page without that template
        flag would carry "No additional surfaces for this page." (the
        same branch, not exercised by a committed tag — the dmm tag is)."""
        derived = _derive("dmm")
        block = derived.manifest["extensions"]["plugin-ui-class-reference:layout"]
        pages = {page["page_id"]: page for page in block["pages"]}
        assert set(pages) == {"readings", "configuration", "device-features"}, pages
        section = pages["device-features"]["sections"][0]
        assert section["id"] == "device-features-section"
        assert section["children"] == [{"body": "No additional device features."}]


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

        for tag in ("f1", "f2", "f1-da", "f5-trio", "f6-smu", "m400"):
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
) -> None:
    """Acceptance 3's validation half: the derived triple passes the
    unchanged ``validate_attachment`` (valid=true) for EVERY pair the
    census walks, readings-page and dataset-page alike. The
    zero-parameter recorded state is closed (issue #525, the corpus fix
    the recorded state's own ruling assigned — "the fix belongs
    there"): the committed OTDP examples now declare their readable
    parameters, a readings page carries its observation bindings, and
    the finding's disappearance is the assertion — this strictens the
    recorded-state pin it replaces (`6d041a7b`): a finding now fails
    the arm; before, its absence did. The parameters-carrying readings
    pair validates clean (f6-smu, TestParityB8's validator arm): the
    readings path itself is sound once the descriptor owes what the
    reference authors."""
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
        plot, ``time_series``, with NO ``lane_groups`` and NO
        ``decoder_lanes`` (the manifest schema's analog branch bans both)
        and the bound target's x variable the receipt-time scalar in
        seconds (the canonical validator's own rule). The bound target
        is page-kind-aware, derived from the reference's own plot page
        (never a class list): a DATASET page binds its dataset slot with
        ``y`` exactly the (channel, quantity) variable ids; a READINGS
        page (the #525-fixed examples) binds the page's FIRST
        observation with ``y`` that observation's single value id — the
        f6-smu convention the parity fixture pins byte for byte."""
        slug, reference = _active_family()[profile_id]
        descriptor_path = _committed_example(slug)
        descriptor_raw = descriptor_path.read_bytes()
        descriptor = json.loads(descriptor_raw)
        derived = derive_attachment(descriptor_raw, corpus=corpus_root())
        _, plot = _the_plot(derived)
        assert plot["kind"] == "time_series", plot
        assert "lane_groups" not in plot, plot
        assert "decoder_lanes" not in plot, plot
        assert plot["x"] == "time", plot
        if _plot_page_kind(reference) == "readings":
            template = next(p for p in reference["pages"] if p.get("plot"))
            over = str(template["plot"]["over_slot"])
            lane = _numeric_channels(reference, descriptor)[0]
            quantity = str((lane.get("quantities") or [])[0])
            assert plot["binding_id"] == f"{over}-{lane['id']}-{quantity}", plot
            assert plot["y"] == [f"{lane['id']}-{quantity}"], plot
        else:
            assert plot["y"] == _variable_ids(reference, descriptor), plot
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
        _assert_pair_validates(derived, descriptor_raw)

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
        the 16 ceiling, computed from the mutation, never a literal) and
        strips ``parameters``/``parameter_names`` (the tolerance shape
        the zero-parameter arm pins): post-#525 the readings pair's plot
        binds its first observation's single value id, so the DATASET
        fallback with every variable id is the only route by which an
        over-ceiling readings descriptor reaches the y check at all —
        with parameters declared, the same mutation refuses
        ``classref_parameter_map`` first (measured on the bumped tree)."""
        profile_id = sorted(_plot_classes("time_series"))[0]
        slug, reference = _active_family()[profile_id]
        slot = next(
            row
            for row in reference["slots"].values()
            if row.get("kind") == "channels"
        )
        role = str(slot.get("where_role", ""))
        descriptor = json.loads(_committed_example(slug).read_bytes())
        descriptor.pop("parameters", None)
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

    def test_a_zero_parameter_readings_descriptor_derives_the_tolerated_shape(
        self,
    ) -> None:
        """The disclosed gateway-SDK divergence, pinned as a BEHAVIOR now
        the committed corpus no longer carries the shape (issue #525's
        fix completes the examples): a readings-class descriptor stripped
        of ``parameters`` and ``parameter_names`` IN MEMORY (no corpus
        byte touched) derives WITHOUT refusing — the SDK expander meets
        the same descriptor at authoring time and refuses
        ``classref_parameter_map``; the gateway tolerates, which is what
        kept the pre-#525 examples derivable — so the readings page
        carries no observation bindings, the plot falls back to the
        dataset binding with every (channel, quantity) variable id, and
        validation reports exactly ONE ``invalid_plot`` finding at the
        plot page: the ``6d041a7b`` recorded state, pinned here on the
        mechanism's behavior instead of the committed corpus."""
        from benchweave.interfaces.ui_presentation import _pin_scoped_documents
        from benchweave.presentation.admission import validate_attachment
        from benchweave.presentation.panels import SUPPORTED_PANELS

        readings = sorted(
            profile_id
            for profile_id, (_, reference) in _plot_classes("time_series").items()
            if _plot_page_kind(reference) == "readings"
        )
        assert readings, sorted(_plot_classes("time_series"))
        slug, reference = _active_family()[readings[0]]
        template = next(p for p in reference["pages"] if p.get("plot"))
        descriptor = json.loads(_committed_example(slug).read_bytes())
        descriptor.pop("parameters", None)
        for channel in descriptor["channels"]:
            channel.pop("parameter_names", None)
        descriptor_raw = (json.dumps(descriptor) + "\n").encode()
        derived = derive_attachment(descriptor_raw, corpus=corpus_root())
        page, plot = _the_plot(derived)
        assert str(page["id"]) == str(template["id"]), page
        assert plot["binding_id"] == str(template["plot"]["over_slot"]), plot
        assert plot["y"] == _variable_ids(reference, descriptor), plot
        firmware = (descriptor.get("identity", {}).get("supported_firmware") or ["0"])[
            0
        ]
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
        assert [(row.code, row.path) for row in report.findings] == [
            ("invalid_plot", f"pages.{template['id']}.plots")
        ], report.findings

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
        _, plot = _the_plot(derived)
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
        _assert_pair_validates(derived, descriptor_raw)


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
            (corpus_root() / "plugin-ui-class-reference/0.6.0/class-logic_analyser.json")
            .read_bytes()
        )
        reference["pages"][0]["binding_slots"].append("ghost-slot")
        with pytest.raises(ClassRefusal, match="^classref_unknown_slot:"):
            _derive_from_document(
                json.loads((FIXTURES / "descriptor-f1.json").read_bytes()),
                references_override=[reference],
            )


def _effective_sample_count(field: dict[str, Any]) -> dict[str, Any]:
    """The configured action's emitted settings schema with ``sample_count``
    narrowed by ``field`` — the catalogued intersection's output, read where
    a dispatch value is judged."""
    raw = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
    raw["actions"]["otdp.logic_analyser.configure/1.0.0"]["input_constraints"] = {
        "properties": {"sample_count": field}
    }
    derived = _derive_from_document(raw)
    settings = next(
        blob
        for name, blob in derived.resources.items()
        if name.startswith("settings/")
    )
    schema: dict[str, Any] = json.loads(settings)
    return {"schema": schema, "field": schema["properties"]["sample_count"]}


def _configured_candidate(sample_count: int) -> dict[str, Any]:
    """The configured action's required fields, so a validator's verdict
    turns on ``sample_count`` alone."""
    return {
        "configuration_id": "cfg-1",
        "channels": [{"channel": "a", "threshold_v": 1.0}],
        "sample_rate_hz": 1000.0,
        "trigger": {"kind": "immediate"},
        "sample_count": sample_count,
    }


class TestResidualResolution:
    """The residual layer (issue #556 Track A, design §3.3): a declared
    action no served catalog describes derives from the descriptor's own
    input_constraints — resolution "custom", a visible custom section —
    never the recoverable ``classref_unknown_action`` refusal. The fold
    hardening on the shared paths (W5/M6/W9/W3/G4, the released
    semantics) rides along."""

    _CUSTOM_URN = "com.veridian-labs.self_test/1.0.0"

    def _descriptor_with_custom_action(
        self, constraints: dict[str, Any] | None
    ) -> dict[str, Any]:
        raw: dict[str, Any] = json.loads(
            (FIXTURES / "descriptor-f1.json").read_bytes()
        )
        action: dict[str, Any] = {
            "binding": {"kind": "adapter", "key": "fixture"},
            "timeout_ms": 5000,
            "side_effect": "state_change",
            "cancellable": True,
            "retry": "never",
        }
        if constraints is not None:
            action["input_constraints"] = constraints
        raw["actions"][self._CUSTOM_URN] = action
        return raw

    def test_residual_action_derives_labelled_custom(self) -> None:
        """The recoverable refusal is GONE: a declared action absent from
        every served catalog derives with resolution "custom", its
        controls from the descriptor's own input_constraints, rendered in
        the page's custom section (resolution partitions, never mixes)."""
        raw = self._descriptor_with_custom_action(
            {
                "properties": {
                    "duration_s": {"type": "number", "minimum": 0.0, "maximum": 60.0}
                },
                "required": ["duration_s"],
            }
        )
        derived = _derive_from_document(raw)
        # The denominator is the descriptor's own declared action set —
        # every declared URN resolves exactly once, non-null (G-M1's
        # shape at this layer), and the custom member names no class.
        assert sorted(urn for urn, _resolution, _class_urn in derived.resolutions) == (
            sorted(raw["actions"])
        )
        assert all(
            resolution in ("catalog", "composed", "custom")
            for _urn, resolution, class_urn in derived.resolutions
        )
        by_urn = {
            urn: (resolution, class_urn)
            for urn, resolution, class_urn in derived.resolutions
        }
        assert by_urn[self._CUSTOM_URN] == ("custom", None)
        assert by_urn["com.veridian-labs.auto-threshold/1.0.0"] == ("catalog", None)
        block = derived.manifest["extensions"][
            "plugin-ui-class-reference:layout"
        ]
        features = next(
            page
            for page in block["pages"]
            if page["page_id"] == "device-features"
        )
        section_ids = [section["id"] for section in features["sections"]]
        assert "device-features-custom" in section_ids, section_ids
        custom = next(
            section
            for section in features["sections"]
            if section["id"] == "device-features-custom"
        )
        assert custom["title"] == "Custom device actions"
        assert [(node.get("kind"), node.get("field")) for node in custom["children"]] == [
            ("numeric", "duration_s"),
            ("button", None),
        ]
        main = next(
            section
            for section in features["sections"]
            if section["id"] == "device-features-section"
        )
        assert all(
            node.get("binding_id") != "self_test" for node in main["children"]
        )

    def test_residual_undeclared_input_derives_l0_with_the_marker(self) -> None:
        """W7: "declares nothing" is not "declares no inputs" — a residual
        action whose input_constraints carries no properties key at all
        derives L0 with input_undeclared, and silence never becomes a
        one-click dispatch (no button, no control node)."""
        raw = self._descriptor_with_custom_action({"required": ["channel"]})
        derived = _derive_from_document(raw)
        resolutions = {
            urn: (resolution, class_urn)
            for urn, resolution, class_urn in derived.resolutions
        }
        assert resolutions[self._CUSTOM_URN] == ("custom", None)
        from benchweave.presentation.classref import _derive_controls

        plan, _divergences = _derive_controls(
            {self._CUSTOM_URN: {}}, {}, {}, {}, {}
        )
        row = plan[self._CUSTOM_URN]
        assert row["resolution"] == "custom"
        assert row["level"] == "L0"
        assert row["input_undeclared"] is True
        block = derived.manifest["extensions"][
            "plugin-ui-class-reference:layout"
        ]
        for page in block["pages"]:
            for section in page["sections"]:
                for node in section.get("children", []):
                    assert node.get("binding_id") != "self_test", node

    def test_non_object_catalog_row_refuses_classref_catalog_row_invalid(
        self,
    ) -> None:
        """A served catalog row that is not an object refuses typed —
        reading it as "no catalog" would mint a false custom provenance
        (the pre-split code crashed on it downstream)."""
        catalog = json.loads((FIXTURES / "vendor-catalog.json").read_bytes())
        catalog["actions"]["com.veridian-labs.ghost/1.0.0"] = 5
        raw_bytes = (json.dumps(catalog, indent=2) + "\n").encode()
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        descriptor["actions"]["com.veridian-labs.ghost/1.0.0"] = descriptor[
            "actions"
        ]["com.veridian-labs.auto-threshold/1.0.0"]
        descriptor["contracts"][-1]["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        with pytest.raises(ClassRefusal, match="^classref_catalog_row_invalid:"):
            derive_attachment(
                json.dumps(descriptor).encode(),
                corpus=corpus_root(),
                vendor_catalogs={hashlib.sha256(raw_bytes).hexdigest(): raw_bytes},
            )

    def test_residual_closed_vocabulary_refuses_at_every_depth(self) -> None:
        """The residual fragment passes the same closed-vocabulary gate
        the catalogued intersection passes — at every depth (W2)."""
        raw = self._descriptor_with_custom_action(
            {
                "properties": {
                    "payload": {
                        "type": "object",
                        "properties": {
                            "token": {"type": "string", "format": "uri"}
                        },
                    }
                }
            }
        )
        with pytest.raises(ClassRefusal, match="^classref_constraint_unsupported:"):
            _derive_from_document(raw)

    def test_residual_empty_admittance_shapes_refuse(self) -> None:
        """W5/M6: an empty declared enum and inverted string length
        bounds admit nothing — residual and catalogued alike."""
        raw = self._descriptor_with_custom_action(
            {"properties": {"mode": {"enum": []}}}
        )
        with pytest.raises(
            ClassRefusal, match="enum admits no value"
        ):
            _derive_from_document(raw)
        raw = self._descriptor_with_custom_action(
            {
                "properties": {
                    "label": {"type": "string", "minLength": 5, "maxLength": 2}
                }
            }
        )
        with pytest.raises(
            ClassRefusal,
            match="string length bounds admit no value",
        ):
            _derive_from_document(raw)

    def test_residual_declared_values_narrow_under_bounds(self) -> None:
        """W3: a declared value set under declared bounds renders exactly
        the values both admit — narrowed, refused when emptied, conflicted
        when a const sits outside (kill (d)'s shape at the residual
        layer). The narrowed set rides the FIELD ROW (the layout node
        vocabulary carries kind/field only), read here through the
        derivation's own helpers over the same fragment the plan
        consumed."""
        from benchweave.presentation.classref import (
            _effective_action_schema,
            _field_rows,
        )

        fragment = {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
            "enum": [5, 50],
        }
        effective = _effective_action_schema(
            self._CUSTOM_URN, None, {"properties": {"level": fragment}}
        )
        rows = _field_rows(self._CUSTOM_URN, "", effective)
        assert rows[0]["enum"] == [5]
        raw = self._descriptor_with_custom_action(
            {
                "properties": {
                    "level": {"type": "integer", "maximum": 10, "enum": [50]}
                }
            }
        )
        with pytest.raises(
            ClassRefusal, match="every declared enum value falls outside"
        ):
            _derive_from_document(raw)
        raw = self._descriptor_with_custom_action(
            {
                "properties": {
                    "level": {"type": "integer", "maximum": 10, "const": 50}
                }
            }
        )
        with pytest.raises(
            ClassRefusal, match="const"
        ):
            _derive_from_document(raw)

    def test_ill_typed_control_values_refuse_g4(self) -> None:
        """G4: a control keyword whose value is ill-typed refuses typed
        on the residual path (the W9 admission without value typing used
        to crash the narrowing)."""
        raw = self._descriptor_with_custom_action(
            {"properties": {"count": {"type": "integer", "minimum": "0"}}}
        )
        with pytest.raises(ClassRefusal, match="^classref_constraint_unsupported:"):
            _derive_from_document(raw)

    def test_w9_string_length_bounds_join_the_vocabulary(self) -> None:
        """W9: minLength/maxLength are inside the closed vocabulary — a
        bounded string on the CONSTRAINT side used to refuse
        classref_constraint_unsupported; it now derives a bounded text
        row. A length bound meeting a NON-string catalogue type is the
        same conflict the numeric bounds raise (the catalog's
        margin_ppm is an integer)."""
        raw = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        raw["actions"]["com.veridian-labs.auto-threshold/1.0.0"][
            "input_constraints"
        ] = {"properties": {"margin_ppm": {"maxLength": 8}}}
        with pytest.raises(ClassRefusal, match="length bound applied to catalogue"):
            _derive_from_document(raw)
        raw = self._descriptor_with_custom_action(
            {
                "properties": {
                    "label": {"type": "string", "minLength": 2, "maxLength": 8}
                },
                "required": ["label"],
            }
        )
        derived = _derive_from_document(raw)
        block = derived.manifest["extensions"][
            "plugin-ui-class-reference:layout"
        ]
        node = next(
            node
            for page in block["pages"]
            for section in page["sections"]
            for node in section.get("children", [])
            if node.get("field") == "label"
        )
        assert node["kind"] == "text"

    def test_constraint_only_maximum_survives_the_intersection(self) -> None:
        """The high-bound selection the gateway transposed (its copy read
        ``low_constraint`` where the SDK reads ``high_constraint``): a
        constraint declaring ONLY a maximum against a catalogue row with
        no upper bound (sample_rate_hz is exclusiveMinimum-only) used to
        drop the bound silently — an admittance WIDENING. The mirror
        keeps the declared maximum."""
        raw = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        raw["actions"]["otdp.logic_analyser.configure/1.0.0"][
            "input_constraints"
        ] = {"properties": {"sample_rate_hz": {"maximum": 48000000}}}
        derived = _derive_from_document(raw)
        settings = next(
            blob
            for name, blob in derived.resources.items()
            if name.startswith("settings/")
        )
        schema = json.loads(settings)
        assert schema["properties"]["sample_rate_hz"]["maximum"] == 48000000

    def test_high_bound_tie_prefers_the_exclusive_end(self) -> None:
        """The tighter end of an EQUAL-value HIGH bound is the exclusive
        one. A catalogue ``maximum: 1000000`` meeting a constraint
        ``exclusiveMaximum: 1000000`` must derive the exclusive bound: the
        constraint is the tighter end, and an effective schema keeping the
        inclusive catalogue end admits the very value the plugin's own
        declaration refuses — the one direction this project does not
        tolerate. The selection compared ``(value, exclusive)`` tuples with
        ``min()``, which returns the INCLUSIVE pair on an equal value.
        """
        from jsonschema import Draft202012Validator

        high = _effective_sample_count({"exclusiveMaximum": 1000000})
        assert high["field"]["exclusiveMaximum"] == 1000000
        assert "maximum" not in high["field"]
        validator = Draft202012Validator(high["schema"])
        assert not validator.is_valid(_configured_candidate(1000000))
        assert validator.is_valid(_configured_candidate(999999))

    def test_low_bound_tie_prefers_the_exclusive_end(self) -> None:
        """The mirror arm: the tighter end of an EQUAL-value LOW bound is
        the exclusive one too. The side's ``max()`` already returned the
        exclusive pair before the fix, so this arm passes pre-fix; it is
        pinned here because both sides now read through one comparator,
        and the comparator neutralization reds it — that neutralization,
        not the pre-fix run, is what proves it load-bearing."""
        from jsonschema import Draft202012Validator

        low = _effective_sample_count({"exclusiveMinimum": 1})
        assert low["field"]["exclusiveMinimum"] == 1
        assert "minimum" not in low["field"]
        validator = Draft202012Validator(low["schema"])
        assert not validator.is_valid(_configured_candidate(1))
        assert validator.is_valid(_configured_candidate(2))

    def test_qualified_field_collision_refuses_classref_duplicate_field(self) -> None:
        """Dotted flattening gives a nested a→b and a literal "a.b" the
        same qualified name — two rows under one name render two controls
        for one declared field; the collision refuses typed."""
        raw = self._descriptor_with_custom_action(
            {
                "properties": {
                    "a.b": {"type": "integer"},
                    "a": {"type": "object", "properties": {"b": {"type": "integer"}}},
                }
            }
        )
        with pytest.raises(ClassRefusal, match="^classref_duplicate_field:"):
            _derive_from_document(raw)

    def test_custom_action_never_welds_into_an_authored_section(self) -> None:
        """The completion scoping (W1 fold): a residual member never
        welds its button into the reference's authored sections — the
        authored page stands as authored and the member surfaces through
        the plan and the custom channel instead."""
        reference = json.loads(
            (
                corpus_root()
                / "plugin-ui-class-reference/0.6.0/class-logic_analyser.json"
            ).read_bytes()
        )
        reference["layouts"].append(
            {
                "page_id": "device-features",
                "sections": [
                    {
                        "id": "features",
                        "title": "Device features",
                        "surface": "raised",
                        "span": 12,
                        "children": [{"body": "Vendor features."}],
                    }
                ],
            }
        )
        raw = self._descriptor_with_custom_action(
            {
                "properties": {"duration_s": {"type": "number"}},
                "required": ["duration_s"],
            }
        )
        derived = _derive_from_document(raw, references_override=[reference])
        features = next(
            page
            for page in derived.manifest["extensions"][
                "plugin-ui-class-reference:layout"
            ]["pages"]
            if page["page_id"] == "device-features"
        )
        assert [section["id"] for section in features["sections"]] == ["features"]
        assert all(
            node.get("binding_id") != "self_test"
            for section in features["sections"]
            for node in section.get("children", [])
        )


class TestComposedResolution:
    """The composed layer (issue #556 Track A, design §3.2): a pinned,
    digest-verified composed action-class document supplies the catalogue
    side for the URNs it claims — layer 2 between the served catalog and
    the residual derivation. Conflicts refuse, never merge."""

    _BURST_URN = "com.veridian-labs.burst/1.0.0"
    _CLASS_URN = "otdp.action.veridian_burst/1.0.0"

    @staticmethod
    def _composed_document(
        *,
        urn: str = "otdp.action.veridian_burst/1.0.0",
        claims: tuple[str, ...] = ("com.veridian-labs.burst/1.0.0",),
        side_effect: str = "state_change",
        title: str | None = "Veridian burst mode",
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "contract_version": "0.1.0",
            "urn": urn,
            "claims": list(claims),
            "input_schema": {
                "type": "object",
                "properties": {
                    "burst_count": {"type": "integer", "minimum": 1, "maximum": 1024}
                },
                "required": ["burst_count"],
                "additionalProperties": False,
            },
            "side_effect": side_effect,
        }
        if title is not None:
            document["title"] = title
        return document

    def _descriptor_with_composed_pin(
        self,
        *documents: dict[str, Any],
        declare_burst: bool = True,
        burst_side_effect: str = "state_change",
    ) -> tuple[bytes, dict[str, bytes]]:
        """The f1 descriptor with its vendor-catalog pin replaced by one
        composed-class pin per document (the admission resolution keyed
        by digest), plus the burst action declared."""
        descriptor: dict[str, Any] = json.loads(
            (FIXTURES / "descriptor-f1.json").read_bytes()
        )
        catalogs: dict[str, bytes] = {}
        pins: list[dict[str, Any]] = []
        for document in documents:
            raw = (json.dumps(document, indent=2) + "\n").encode()
            digest = hashlib.sha256(raw).hexdigest()
            catalogs[digest] = raw
            pins.append(
                {
                    "id": f"urn:veridian:composed:{len(pins) + 1}",
                    "path": f"composed-{len(pins)}.json",
                    "sha256": digest,
                }
            )
        descriptor["contracts"] = [
            row for row in descriptor["contracts"]
            if str(row["id"]).startswith("urn:otdp:")
        ] + pins
        if declare_burst:
            descriptor["actions"][self._BURST_URN] = {
                "binding": {"kind": "adapter", "key": "fixture"},
                "input_constraints": {},
                "timeout_ms": 5000,
                "side_effect": burst_side_effect,
                "cancellable": True,
                "retry": "never",
            }
        # The vendor action the un-pinned catalog used to describe is
        # gone with the pin: drop it from the declared set too.
        descriptor["actions"].pop("com.veridian-labs.auto-threshold/1.0.0", None)
        return json.dumps(descriptor).encode(), catalogs

    def test_composed_class_supplies_the_catalogue_side(self) -> None:
        """A composed pin supplies the catalogue side for its claimed
        URNs: resolution "composed" naming the class, the controls from
        the class's input_schema, D13 narrowing unchanged on them, and
        the member renders in the MAIN section (composed is not
        custom)."""
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(
            self._composed_document()
        )
        derived = derive_attachment(
            descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
        )
        resolutions = {
            urn: (resolution, class_urn)
            for urn, resolution, class_urn in derived.resolutions
        }
        assert resolutions[self._BURST_URN] == ("composed", self._CLASS_URN)
        block = derived.manifest["extensions"][
            "plugin-ui-class-reference:layout"
        ]
        features = next(
            page
            for page in block["pages"]
            if page["page_id"] == "device-features"
        )
        section_ids = [section["id"] for section in features["sections"]]
        assert "device-features-custom" not in section_ids, section_ids
        main = next(
            section
            for section in features["sections"]
            if section["id"] == "device-features-section"
        )
        kinds = [
            (node.get("kind"), node.get("field")) for node in main["children"]
        ]
        assert ("numeric", "burst_count") in kinds
        assert ("button", None) in kinds

    def test_ds3_a_claim_the_descriptor_does_not_declare_joins_the_map(self) -> None:
        """DS3: a claim the descriptor does not declare simply does not
        apply — it joins the catalogue side (so a named reference slot
        may bind a composed-claimed URN; the family schema's slot action
        pattern is the otdp three-segment shape, so the claim uses it),
        and the class rides back as UNAPPLIED when none of its claims
        applied."""
        unclaimed = "otdp.logic_analyser.burst/1.0.0"
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(
            self._composed_document(claims=(unclaimed,)),
            declare_burst=False,
        )
        derived = derive_attachment(
            descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
        )
        assert derived.unapplied_classes == (
            (self._CLASS_URN, "composed-0.json"),
        )
        # The slot check runs against the MERGED map: a procedure slot
        # naming the composed-claimed URN passes (pre-walk this exact
        # input refused classref_unknown_action) — the slot is
        # when-declared and the descriptor does not declare the action,
        # so it contributes no target, exactly the SDK's shape.
        reference = json.loads(
            (
                corpus_root()
                / "plugin-ui-class-reference/0.6.0/class-logic_analyser.json"
            ).read_bytes()
        )
        arm_action = str(reference["slots"]["arm"]["action"])
        reference["slots"]["arm"]["action"] = unclaimed
        descriptor = json.loads(descriptor_raw)
        _derive_from_document(
            descriptor,
            references_override=[reference],
            extra_vendor_catalogs=catalogs,
        )
        # The declared half — the §3.5 composed tolerance: a DECLARED
        # composed-claimed action in the configuration slot derives its
        # settings schema from the class's input_schema alone, the $id
        # falling back to the derived action-input urn.
        descriptor["actions"][unclaimed] = {
            "binding": {"kind": "adapter", "key": "fixture"},
            "input_constraints": {},
            "timeout_ms": 5000,
            "side_effect": "state_change",
            "cancellable": True,
            "retry": "never",
        }
        reference["slots"]["arm"]["action"] = arm_action
        reference["slots"]["configure"]["action"] = unclaimed
        derived = _derive_from_document(
            descriptor,
            references_override=[reference],
            extra_vendor_catalogs=catalogs,
        )
        settings = next(
            blob
            for name, blob in derived.resources.items()
            if name.startswith("settings/")
        )
        schema = json.loads(settings)
        assert schema["$id"] == f"urn:otdp:action:{unclaimed}:input"
        assert "burst_count" in schema["properties"]
        assert derived.unapplied_classes == ()

    def test_schema_invalid_composed_doc_refuses(self) -> None:
        document = self._composed_document(title=None)  # title is required
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(document)
        with pytest.raises(
            ClassRefusal, match="^classref_invalid_composed_class:"
        ):
            derive_attachment(
                descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
            )

    def test_ambiguous_pin_refuses_naming_the_carried_keys(self) -> None:
        document = self._composed_document()
        document["actions"] = {}
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(document)
        with pytest.raises(
            ClassRefusal, match="ambiguous pin"
        ) as caught:
            derive_attachment(
                descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
            )
        assert "actions" in str(caught.value)
        assert "urn" in str(caught.value)
        assert "claims" in str(caught.value)

    def test_claim_against_the_served_catalog_refuses(self) -> None:
        document = self._composed_document(
            claims=("otdp.logic_analyser.arm/1.0.0",)
        )
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(document)
        with pytest.raises(
            ClassRefusal, match="^classref_composed_claim_conflict:"
        ) as caught:
            derive_attachment(
                descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
            )
        assert "served OTDP catalog" in str(caught.value)

    def test_claim_against_a_pinned_row_refuses(self) -> None:
        """Two pins: one vendor catalog describing auto-threshold, one
        class claiming the same URN — the claim collides with the pinned
        row and refuses naming the pinned document."""
        catalog = json.loads((FIXTURES / "vendor-catalog.json").read_bytes())
        composed = self._composed_document(
            claims=("com.veridian-labs.auto-threshold/1.0.0",)
        )
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(
            composed, catalog
        )
        with pytest.raises(
            ClassRefusal, match="^classref_composed_claim_conflict:"
        ) as caught:
            derive_attachment(
                descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
            )
        assert "pinned document" in str(caught.value)

    def test_two_classes_one_claim_refuses(self) -> None:
        first = self._composed_document()
        second = self._composed_document(urn="otdp.action.veridian_alt/1.0.0")
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(
            first, second
        )
        with pytest.raises(
            ClassRefusal, match="^classref_composed_claim_conflict:"
        ) as caught:
            derive_attachment(
                descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
            )
        assert "both class" in str(caught.value)

    def test_one_class_urn_in_two_pins_refuses(self) -> None:
        first = self._composed_document()
        second = self._composed_document()
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(
            first, second
        )
        with pytest.raises(
            ClassRefusal, match="^classref_composed_claim_conflict:"
        ) as caught:
            derive_attachment(
                descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
            )
        assert "two pinned documents" in str(caught.value)

    def test_side_effect_under_refuses(self) -> None:
        """The S20 direction at the class layer: a class declaring
        side_effect none under a descriptor action declaring
        state_change under-classifies and refuses (over-classification
        stays legal)."""
        document = self._composed_document(side_effect="none")
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(document)
        with pytest.raises(
            ClassRefusal, match="^classref_composed_side_effect_under:"
        ):
            derive_attachment(
                descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
            )

    def test_shapeless_pin_is_disclosed_as_ignored(self) -> None:
        """A digest-valid pin matching neither shape discriminator
        contributes nothing and is DISCLOSED (never silently dropped)."""
        document = {"catalog_version": "1.0.0", "vendor": "com.veridian-labs"}
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(document)
        derived = derive_attachment(
            descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
        )
        assert derived.ignored_pins == ("composed-0.json",)

    def test_empty_actions_pin_is_disclosed(self) -> None:
        document: dict[str, Any] = {"actions": {}}
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(document)
        derived = derive_attachment(
            descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
        )
        assert derived.empty_action_pins == ("composed-0.json",)

    def test_stray_composed_class_key_is_stripped_not_laundered(self) -> None:
        """N2: composed provenance has exactly one writer — the composed
        walk. A vendor-catalog action row carrying a stray
        ``composed_class`` key is stripped and resolves CATALOG, never a
        laundered composed label."""
        catalog = json.loads((FIXTURES / "vendor-catalog.json").read_bytes())
        catalog["actions"]["com.veridian-labs.auto-threshold/1.0.0"][
            "composed_class"
        ] = "otdp.action.veridian_fake/1.0.0"
        descriptor_raw, catalogs = self._descriptor_with_composed_pin(catalog)
        # The helper drops the un-pinned vendor action from the declared
        # set; this arm is exactly about that row — re-declare it.
        descriptor = json.loads(descriptor_raw)
        descriptor["actions"]["com.veridian-labs.auto-threshold/1.0.0"] = {
            "binding": {"kind": "adapter", "key": "fixture"},
            "input_constraints": {},
            "timeout_ms": 5000,
            "side_effect": "state_change",
            "cancellable": True,
            "retry": "never",
        }
        descriptor_raw = json.dumps(descriptor).encode()
        derived = derive_attachment(
            descriptor_raw, corpus=corpus_root(), vendor_catalogs=catalogs
        )
        resolutions = {
            urn: (resolution, class_urn)
            for urn, resolution, class_urn in derived.resolutions
        }
        assert resolutions["com.veridian-labs.auto-threshold/1.0.0"] == (
            "catalog",
            None,
        )


class TestAcceptanceM400:
    """The three-layer acceptance tag (issue #556 Track A, design §7):
    the m400-shaped fixture — a mostly-DAQ device with one composed and
    one residual action, its triple generated from the pinned v0.21.0
    expander beside its composed-class pin — derives with zero
    refusals, every declared action resolved, and the three layers
    distinguishable on the real path."""

    _BURST = "com.meridian.m400.burst_mode/1.0.0"
    _CLASS = "otdp.action.meridian_burst/1.0.0"
    _SELF_CAL = "com.meridian.m400.self_cal/1.0.0"

    def test_gm1_every_declared_action_resolves(self) -> None:
        """G-M1: the acceptance fixture derives with zero refusals AND
        100% of its declared actions carry a non-null resolution — the
        denominator derived from the descriptor document, never a
        literal count."""
        derived = _derive("m400")
        descriptor = json.loads((FIXTURES / "descriptor-m400.json").read_bytes())
        declared = set(descriptor["actions"])
        assert declared, "the fixture declares actions"
        assert {urn for urn, _r, _c in derived.resolutions} == declared
        assert all(
            resolution in ("catalog", "composed", "custom")
            for _urn, resolution, _class in derived.resolutions
        )
        assert derived.ignored_pins == ()
        assert derived.unapplied_classes == ()
        assert derived.empty_action_pins == ()

    def test_gm3_the_layers_are_distinguishable(self) -> None:
        """G-M3: one burst_mode-shaped URN derives ``custom`` with no
        pin, ``composed`` with the pin, and a served-namespaced sibling
        derives ``catalog`` — three derivations over the real path,
        three asserted resolutions, the composed leg naming its class."""
        descriptor = json.loads((FIXTURES / "descriptor-m400.json").read_bytes())
        composed_pin = next(
            row
            for row in descriptor["contracts"]
            if str(row["id"]) == "urn:meridian:composed-burst:1.0.0"
        )
        descriptor["contracts"].remove(composed_pin)
        derived = _derive_from_document(descriptor)
        assert dict(
            (urn, (resolution, class_urn))
            for urn, resolution, class_urn in derived.resolutions
        )[self._BURST] == ("custom", None)
        derived = _derive("m400")
        resolutions = {
            urn: (resolution, class_urn)
            for urn, resolution, class_urn in derived.resolutions
        }
        assert resolutions[self._BURST] == ("composed", self._CLASS)
        assert resolutions[self._SELF_CAL] == ("custom", None)
        assert resolutions["otdp.daq.arm/1.0.0"] == ("catalog", None)

    def test_the_custom_section_renders_beside_the_main_section(self) -> None:
        """The device-features page partitions: the catalogued and
        composed actions in the main section, the residual member in the
        custom section — each action's controls carry its own field
        rows."""
        derived = _derive("m400")
        block = derived.manifest["extensions"][
            "plugin-ui-class-reference:layout"
        ]
        features = next(
            page
            for page in block["pages"]
            if page["page_id"] == "device-features"
        )
        sections = {section["id"]: section for section in features["sections"]}
        assert set(sections) == {
            "device-features-section",
            "device-features-custom",
        }
        main_fields = [
            node.get("field")
            for node in sections["device-features-section"]["children"]
        ]
        assert "burst_count" in main_fields
        custom_children = sections["device-features-custom"]["children"]
        assert [
            (node.get("kind"), node.get("field")) for node in custom_children
        ] == [("text", "channel"), ("button", None)]


class TestRefusalSplit:
    """The refusal split (issue #556 Track A, design §3.1): every integrity
    arm fires with its own code, mirroring the SDK expander at the v0.21.0
    pin. The pre-split code wore ``classref_unknown_action`` for all of
    these; the split keeps that code for exactly ONE condition (the D4
    reference-slot arm below) and nothing else."""

    def test_not_admitted_pin_refuses_classref_vendor_catalog_unreadable(
        self,
    ) -> None:
        """The gateway-specific resolution fault keeps its own detail
        sentence under the SDK's ``classref_vendor_catalog_unreadable``
        code — the admission store is the gateway's equivalent of the
        SDK's unreadable pinned file (the module docstring's disclosed
        divergence)."""
        descriptor_raw = (FIXTURES / "descriptor-f1.json").read_bytes()
        with pytest.raises(
            ClassRefusal, match="^classref_vendor_catalog_unreadable:"
        ) as caught:
            derive_attachment(descriptor_raw, corpus=corpus_root(), vendor_catalogs={})
        assert "is not admitted" in str(caught.value)

    def test_tampered_pin_bytes_refuse_classref_vendor_catalog_digest_mismatch(
        self,
    ) -> None:
        """Pinned bytes that fail their digest are an integrity fault —
        its own code since the split, never the recoverable gap's. The
        map is keyed by the descriptor's PIN (the resolution lookup's
        own key) with tampered bytes as the value, so the arm exercises
        the digest check itself — keying by the tampered bytes' own
        digest would miss the lookup and fire the not-admitted arm
        instead (the pre-split arm passed that way, asserting its code
        for the wrong reason)."""
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        pin = str(
            next(
                row["sha256"]
                for row in descriptor["contracts"]
                if not str(row["id"]).startswith("urn:otdp:")
            )
        )
        raw = (FIXTURES / "vendor-catalog.json").read_bytes() + b" "
        with pytest.raises(
            ClassRefusal, match="^classref_vendor_catalog_digest_mismatch:"
        ):
            derive_attachment(
                (FIXTURES / "descriptor-f1.json").read_bytes(),
                corpus=corpus_root(),
                vendor_catalogs={pin: raw},
            )

    def test_non_object_pin_refuses_classref_vendor_catalog_invalid(self) -> None:
        """A digest-valid pin whose document is not a JSON object refuses
        typed (the SDK's B7 row: the pre-split walk crashed on a bare
        AttributeError — never an SDK error face, never a 500)."""
        raw = b"[1, 2, 3]\n"
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        row = next(
            item
            for item in descriptor["contracts"]
            if not str(item["id"]).startswith("urn:otdp:")
        )
        row["sha256"] = hashlib.sha256(raw).hexdigest()
        with pytest.raises(ClassRefusal, match="^classref_vendor_catalog_invalid:"):
            derive_attachment(
                json.dumps(descriptor).encode(),
                corpus=corpus_root(),
                vendor_catalogs={row["sha256"]: raw},
            )

    def test_non_object_actions_map_refuses_classref_vendor_catalog_invalid(
        self,
    ) -> None:
        """A digest-valid object pin whose ``actions`` is not an object
        refuses typed (the SDK's R4 row: ``{"actions": 5}`` used to crash
        the walk at ``.items()``)."""
        raw = b'{"actions": 5}\n'
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        row = next(
            item
            for item in descriptor["contracts"]
            if not str(item["id"]).startswith("urn:otdp:")
        )
        row["sha256"] = hashlib.sha256(raw).hexdigest()
        with pytest.raises(ClassRefusal, match="^classref_vendor_catalog_invalid:"):
            derive_attachment(
                json.dumps(descriptor).encode(),
                corpus=corpus_root(),
                vendor_catalogs={row["sha256"]: raw},
            )

    def test_unserved_profile_catalog_refuses_its_own_code(
        self, tmp_path: Path
    ) -> None:
        """A descriptor pinning a version whose profile catalog the corpus
        does not carry is a platform fault (the SDK's own split code
        ``classref_profile_catalog_unserved``) — never the recoverable
        gap's code."""
        import shutil

        corpus = tmp_path / "standards"
        shutil.copytree(corpus_root(), corpus)
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        catalog = corpus / "otdp" / str(descriptor["otdp_version"])
        catalog.joinpath("device-profile-catalog.json").unlink()
        with pytest.raises(ClassRefusal, match="^classref_profile_catalog_unserved:"):
            derive_attachment(
                (FIXTURES / "descriptor-f1.json").read_bytes(), corpus=corpus
            )

    def test_absent_profile_refuses_classref_profile_absent(self) -> None:
        """A reference whose profile the served catalog does not carry is
        a platform fault — re-coded ``classref_profile_absent`` (the
        SDK's own code), still refusing."""
        reference = json.loads(
            (
                corpus_root()
                / "plugin-ui-class-reference/0.6.0/class-logic_analyser.json"
            ).read_bytes()
        )
        reference["profile_id"] = "otdp.meridian_ghost/1.0.0"
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        descriptor["profiles"].append("otdp.meridian_ghost/1.0.0")
        with pytest.raises(ClassRefusal, match="^classref_profile_absent:"):
            _derive_from_document(descriptor, references_override=[reference])

    def test_slot_naming_an_unserved_urn_keeps_classref_unknown_action(self) -> None:
        """The D4 corpus fault SURVIVES the retirement of its own code:
        a reference slot naming an URN absent from every served catalog
        is the ONE condition that still refuses
        ``classref_unknown_action`` gateway-side."""
        reference = json.loads(
            (
                corpus_root()
                / "plugin-ui-class-reference/0.6.0/class-logic_analyser.json"
            ).read_bytes()
        )
        reference["slots"]["abort"]["action"] = "otdp.logic_analyser.ghost/1.0.0"
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        with pytest.raises(ClassRefusal, match="^classref_unknown_action:"):
            _derive_from_document(descriptor, references_override=[reference])

    def test_slot_conflicts_fire_before_the_profile_claims_check(self) -> None:
        """The SDK's position (``derive_ui`` runs ``_check_slot_conflicts``
        immediately after reference resolution): a multi-fault descriptor —
        a URN claimed by named slots in two references AND a profile the
        descriptor does not claim — raises the slot-conflict code both
        sides, never the later check's."""
        first = json.loads(
            (
                corpus_root()
                / "plugin-ui-class-reference/0.6.0/class-logic_analyser.json"
            ).read_bytes()
        )
        second = json.loads(json.dumps(first))
        second["profile_id"] = "otdp.meridian_ghost/1.0.0"
        for key, slot in second["slots"].items():
            if slot.get("action") == "otdp.logic_analyser.abort/1.0.0":
                second["slots"][f"ghost-{key}"] = slot
                del second["slots"][key]
                break
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        with pytest.raises(ClassRefusal, match="^classref_profile_slot_conflict:"):
            _derive_from_document(
                descriptor, references_override=[first, second]
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
        relpath = "plugin-ui-class-reference/0.6.0/class-logic_analyser.json"
        tampered = (corpus / relpath).read_bytes() + b"\n"
        (corpus / relpath).write_bytes(tampered)
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        with pytest.raises(ClassRefusal, match="^corpus_pin_mismatch:"):
            select_references(corpus, descriptor)

    def test_malformed_reference_bytes_refuse_typed_never_silence(
        self, tmp_path: Path
    ) -> None:
        corpus = self._tampered_corpus(tmp_path)
        relpath = "plugin-ui-class-reference/0.6.0/class-logic_analyser.json"
        (corpus / relpath).write_bytes(b"{not json")
        self._re_pin(corpus, relpath, b"{not json")
        descriptor = json.loads((FIXTURES / "descriptor-f1.json").read_bytes())
        with pytest.raises(ClassRefusal, match="^classref_invalid_reference:"):
            select_references(corpus, descriptor)


def _derive_from_document(
    document: dict[str, Any],
    *,
    references_override: list[dict[str, Any]] | None = None,
    extra_vendor_catalogs: dict[str, bytes] | None = None,
) -> DerivedAttachment:
    """A raw-bytes derivation with the vendor catalog admitted, for the
    refusal arms that mutate the descriptor document. Composed-class
    arms admit their pinned documents through
    ``extra_vendor_catalogs`` (the admission resolution keyed by
    digest)."""
    descriptor_raw = json.dumps(document).encode()
    decoder_raw = (FIXTURES / "decoder-uart.json").read_bytes()
    catalogs = _vendor_catalogs()
    if extra_vendor_catalogs is not None:
        catalogs.update(extra_vendor_catalogs)
    return derive_attachment(
        descriptor_raw,
        corpus=corpus_root(),
        vendor_catalogs=catalogs,
        decoder_docs={hashlib.sha256(decoder_raw).hexdigest(): decoder_raw},
        references_override=references_override,
    )


class TestVendorFeaturesCeilingRemoval:
    """Issue #560: a device with many real vendor actions derives a
    device-features section whose children grow with the action count —
    staging nodes per expressible field plus the button — so the 0.5.0
    per-section children ceiling (16) refused real devices. The measured
    evidence: 8 vendor actions with 2 fields each emit 24 children in one
    section and were refused ``classref_layout_invalid``; the 0.6.0 family
    removes the ceiling (density is a renderer concern, never a
    validation one). Invented vendor throughout — fixture vocabulary
    only, never a real product."""

    _VENDOR = "com.lodestar.vx480"
    _ACTION_COUNT = 8
    _FIELDS_PER_ACTION = 2

    def _descriptor_and_catalog(self) -> tuple[bytes, dict[str, bytes]]:
        """The evidence-shaped device (invented vendor): the m400 daq-class
        descriptor minus its vendor actions, plus eight catalogued vendor
        actions each declaring two expressible required fields (a numeric
        and a free text) — 8 x (2 staging nodes + 1 button) = 24 children
        in the device-features section, one page, no custom members."""
        descriptor = json.loads(
            (FIXTURES / "descriptor-m400.json").read_bytes()
        )
        descriptor["id"] = "dev.lodestar.vx480"
        descriptor["display_name"] = "Lodestar VX-480 (fixture)"
        descriptor["description"] = (
            "Fixture vocabulary only; the issue #560 evidence shape — a "
            "daq-class device with eight catalogued vendor actions of two "
            "fields each. Not a verified real device or implemented adapter."
        )
        descriptor["identity"]["manufacturer"] = "Lodestar Instruments"
        descriptor["identity"]["model"] = "VX-480"
        descriptor["integration"]["adapter"]["entry_point"] = (
            "lodestar_vx480_plugin:create_plugin"
        )
        for urn in (
            "com.meridian.m400.burst_mode/1.0.0",
            "com.meridian.m400.self_cal/1.0.0",
        ):
            del descriptor["actions"][urn]
        del descriptor["contracts"][2]  # the composed-burst pin
        actions: dict[str, Any] = {}
        for index in range(self._ACTION_COUNT):
            urn = f"{self._VENDOR}.feature_{index}/1.0.0"
            descriptor["actions"][urn] = {
                "binding": {"kind": "adapter", "key": f"feature_{index}"},
                "input_constraints": {},
                "timeout_ms": 5000,
                "side_effect": "state_change",
                "cancellable": True,
                "retry": "never",
            }
            actions[urn] = {
                "input_schema": {
                    "type": "object",
                    "properties": {
                        f"level_{index}_v": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 12.0,
                        },
                        f"tag_{index}": {"type": "string"},
                    },
                    "required": [f"level_{index}_v", f"tag_{index}"],
                    "additionalProperties": False,
                },
                "side_effect": "state_change",
            }
        catalog = {
            "catalog_version": "1.0.0",
            "vendor": self._VENDOR,
            "actions": actions,
        }
        catalog_raw = json.dumps(catalog).encode()
        descriptor["contracts"].append(
            {
                "id": "urn:lodestar:vendor-catalog:1.0.0",
                "path": "vendor-catalog.json",
                "sha256": hashlib.sha256(catalog_raw).hexdigest(),
            }
        )
        return (
            json.dumps(descriptor).encode(),
            {hashlib.sha256(catalog_raw).hexdigest(): catalog_raw},
        )

    def test_evidence_device_derives_and_validates_end_to_end(self) -> None:
        """The expander path that 0.5.0 refused succeeds end to end: the
        derivation emits the 24-child device-features section and the
        block validates against the ACTIVE corpus schema (the serve
        path's ``classref_layout_invalid`` gate reads the same function).
        RED under 0.5.0 — the block fails the children maxItems — and the
        children arithmetic is pinned beside the verdict so the count
        cannot silently change shape: 8 actions x 3 nodes each; the daq
        class's own actions ride their slot pages (capture,
        configuration), never this section."""
        descriptor_raw, catalogs = self._descriptor_and_catalog()
        decoder_raw = (FIXTURES / "decoder-uart.json").read_bytes()
        derived = derive_attachment(
            descriptor_raw,
            corpus=corpus_root(),
            vendor_catalogs=catalogs,
            decoder_docs={
                hashlib.sha256(decoder_raw).hexdigest(): decoder_raw
            },
        )
        from benchweave.presentation.classref import validate_layout_block

        block = derived.manifest["extensions"][
            "plugin-ui-class-reference:layout"
        ]
        features = next(
            page
            for page in block["pages"]
            if page["page_id"] == "device-features"
        )
        main = next(
            section
            for section in features["sections"]
            if section["id"] == "device-features-section"
        )
        children = main["children"]
        expected = self._ACTION_COUNT * (self._FIELDS_PER_ACTION + 1)
        assert len(children) == expected, (
            f"{len(children)} children in the device-features section; "
            f"the evidence shape derives {expected} "
            f"({self._ACTION_COUNT} actions x "
            f"({self._FIELDS_PER_ACTION} staging + 1 button))"
        )
        assert len(children) > 16, "the evidence shape no longer crosses 16"
        error = validate_layout_block(block, corpus=corpus_root())
        assert error is None, (
            "the derived layout block fails the active family schema: "
            f"{error} — the vendor-features children ceiling (issue #560) "
            "is still refusing real device surfaces"
        )
