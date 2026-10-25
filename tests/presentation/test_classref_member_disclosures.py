"""The composed-member dispositions and the seam (issue #556 Track B,
slice B7): the residual rows the SDK gate renders on its REPORTED
channel, mirrored verbatim on the gateway's ``PresentationState``
disclosure surface, and the profile seam — the canonical validator
reading the accepted pinned documents beside the corpus set so a
composed member's target naming its declaration's vendor row validates
(B4's motion 1, gateway-side; the B4 fold's F4 shape filter).

Same corpus posture as ``test_classref_members``: the arms run against
the scratch corpus, so the wording they pin is base-independent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from classref_members_support import build_member_corpus

from benchweave.presentation.classref import (
    DerivedAttachment,
    derive_attachment,
)

FIXTURES = Path(__file__).parent / "classref_fixtures"



@pytest.fixture()
def member_corpus(tmp_path: Path) -> Path:
    """The scratch corpus carrying a member-declaration schema at the
    ACTIVE family version (see classref_members_support for the
    posture)."""
    return build_member_corpus(tmp_path)


def _disclosures(derived: DerivedAttachment) -> tuple[str, ...]:
    from benchweave.interfaces.ui_presentation import _classref_disclosures

    return _classref_disclosures(derived)


def _m400() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-m400.json").read_bytes()
    )
    return document


def _f6_smu() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-f6-smu.json").read_bytes()
    )
    return document


def _f2() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-f2.json").read_bytes()
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
    raw = (json.dumps(document, indent=2) + "\n").encode()
    descriptor["contracts"].append(
        {
            "id": f"urn:meridian:{name.removesuffix('.json')}",
            "path": name,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    return {hashlib.sha256(raw).hexdigest(): raw}


def _members_document(members: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contract_version": "0.1.0",
        "profiles": [
            {
                "id": "com.meridian.m400/1.0.0",
                "title": "Meridian M-400 vendor row",
                "channel_roles": ["analogue_input"],
                "required_actions": [
                    "com.meridian.m400.sweep/1.0.0",
                    "com.meridian.m400.profile_mode/1.0.0",
                ],
                "optional_actions": [],
            }
        ],
        "members": members,
    }


def _declare(descriptor: dict[str, Any], *urns: str) -> None:
    for urn in urns:
        descriptor["actions"][urn] = {
            "binding": {"kind": "adapter", "key": "fixture"},
            "timeout_ms": 5000,
            "side_effect": "state_change",
            "cancellable": True,
            "retry": "never",
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


def _lines(derived: DerivedAttachment) -> list[str]:
    return list(_disclosures(derived))


class TestAppliedNowhereRows:
    """The B3 fold's F2 family: a pin whose members applied nowhere, and
    the dead members inside pins that applied — the SDK gate's own
    wording, one row each, never silent and never a finding."""

    def test_a_pin_that_applied_nowhere_discloses(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.elsewhere/1.0.0"],
                    "page": "configuration",
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        assert (
            "composed member declaration members.json applied nowhere" in lines
        ), lines

    def test_a_dead_member_inside_an_applied_pin_discloses(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        _declare(
            descriptor,
            "com.meridian.m400.sweep/1.0.0",
        )
        document = _members_document(
            [
                {
                    "slot": "sweep",
                    "kind": "procedure",
                    "claims": ["com.meridian.m400.sweep/1.0.0"],
                    "page": "configuration",
                },
                {
                    "slot": "vendor-configure",
                    "kind": "configuration",
                    "claims": ["com.meridian.m400.dead/1.0.0"],
                    "page": "configuration",
                },
            ]
        )
        vendor_row = {
            "catalog_version": "1.0.0",
            "actions": {
                "com.meridian.m400.sweep/1.0.0": {
                    "input_schema": {
                        "$id": "urn:meridian:action:sweep:input",
                        "type": "object",
                        "properties": {},
                    },
                    "side_effect": "none",
                }
            },
        }
        catalogs = _vendor_catalogs()
        catalogs |= _pin(descriptor, vendor_row, name="vendor-extra.json")
        catalogs |= _pin(descriptor, document)
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        assert (
            "composed member declaration members.json member vendor-configure "
            "applied nowhere (its claims name no action this descriptor "
            "declares)" in lines
        ), lines
        assert (
            "composed member declaration members.json applied nowhere" not in lines
        )

    def test_a_dead_channels_member_names_the_role(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
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
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        assert (
            "composed member declaration members.json member trigger-lanes "
            "applied nowhere (no declared channel carries role trigger_bus)"
            in lines
        ), lines


class TestPlacementAndResidualRows:
    """The fold-assigned dispositions: the placement rows (already-hosted
    plot, page-kind limit), the no-plot-carries-its-binding row with the
    EMITTED binding as its reason, the join-overflow rows, the settings
    and dataset control rows, and the V2/V3 residual closures."""

    def test_a_plot_on_a_page_that_already_hosts_one_discloses(
        self, member_corpus: Path
    ) -> None:
        """The 2026-10-25 capacity-versus-declaration ruling: a placement
        limit the declaration cannot see is a disclosure, never a refusal
        — the page keeps the class's plot."""
        descriptor = _m400()
        _declare(descriptor, "com.meridian.m400.wave/1.0.0")
        document = _members_document(
            [
                {
                    "slot": "vendor-lanes",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.wave/1.0.0"],
                    "page": "capture",
                    "plot": {"kind": "waveform", "over_slot": "vendor-lanes"},
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        assert (
            "composed plot vendor-lanes: page capture already hosts a plot "
            "(the page keeps the class's plot)" in lines
        ), lines

    def test_a_plot_on_a_configuration_page_discloses_the_page_kind(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        _declare(descriptor, "com.meridian.m400.wave/1.0.0")
        document = _members_document(
            [
                {
                    "slot": "vendor-plot",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.wave/1.0.0"],
                    "page": "configuration",
                    "plot": {"kind": "time_series", "over_slot": "vendor-plot"},
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        assert (
            "composed plot vendor-plot: page configuration admits no plot "
            "(plots render on dataset and readings pages alone)" in lines
        ), lines

    def test_a_dataset_member_no_plot_carries_names_the_emitted_binding(
        self, member_corpus: Path
    ) -> None:
        """The B5 fold's F2: the reason names the EMITTED plot's binding
        — the daq capture page's waveform plot binds the class capture
        slot, never the member's."""
        descriptor = _m400()
        _declare(descriptor, "com.meridian.m400.wave/1.0.0")
        document = _members_document(
            [
                {
                    "slot": "vendor-capture",
                    "kind": "dataset",
                    "claims": ["com.meridian.m400.wave/1.0.0"],
                    "page": "capture",
                }
            ]
        )
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        assert (
            "composed dataset vendor-capture: no plot carries its binding "
            "(the plot on page capture binds capture)" in lines
        ), lines

    def test_the_join_overflow_discloses_one_row_per_dropped_lane(
        self, member_corpus: Path
    ) -> None:
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
        catalogs = _vendor_catalogs() | _pin(descriptor, document)
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        dropped = [line for line in lines if line.startswith("composed lane ")]
        assert len(dropped) == 8, dropped
        assert (
            "composed lane tb32 (role trigger_bus): no lane surface on page "
            "capture (the page's channels slots join to 72 lanes; the "
            "plot's y admits 64)" in lines
        ), lines

    def test_a_staged_unclaimed_action_carries_the_settings_row(
        self, member_corpus: Path
    ) -> None:
        """The classifier is the derived state: an action with a
        catalogue side derives L2 staging, and unclaimed (device-features)
        it carries the settings row — a custom action with constraints
        alone derives the L1 bare button (the dataset vocabulary's own
        row below), never this one."""
        descriptor = _m400()
        _declare(descriptor, "com.meridian.m400.staged/1.0.0")
        vendor_row = {
            "catalog_version": "1.0.0",
            "actions": {
                "com.meridian.m400.staged/1.0.0": {
                    "input_schema": {
                        "$id": "urn:meridian:action:staged:input",
                        "type": "object",
                        "properties": {
                            "dwell_ms": {"type": "integer", "minimum": 1}
                        },
                        "required": ["dwell_ms"],
                    },
                    "side_effect": "none",
                }
            },
        }
        catalogs = _vendor_catalogs() | _pin(
            descriptor, vendor_row, name="vendor-extra.json"
        )
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        assert (
            "settings member com.meridian.m400.staged/1.0.0: no settings "
            "surface declared (controls render staged on device-features)"
            in lines
        ), lines
        assert not any(
            line.startswith("dataset member com.meridian.m400.staged")
            for line in lines
        ), lines

    def test_a_class_listed_run_verb_never_carries_the_settings_row(
        self, member_corpus: Path
    ) -> None:
        """The B4 fold's F5: a claimed profile's served row listing is the
        one honest class-action signal — otdp.smu.arm stages on
        device-features and stays off this row."""
        lines = _lines(_derive_document(_f6_smu(), _vendor_catalogs(), member_corpus))
        settings_rows = [line for line in lines if line.startswith("settings member ")]
        assert not any("otdp.smu." in row for row in settings_rows), settings_rows

    def test_an_unclaimed_bare_button_carries_the_dataset_row(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        _declare(descriptor, "com.meridian.m400.ping/1.0.0")
        vendor_row = {
            "catalog_version": "1.0.0",
            "actions": {
                "com.meridian.m400.ping/1.0.0": {
                    "input_schema": {
                        "$id": "urn:meridian:action:ping:input",
                        "type": "object",
                        "properties": {},
                    },
                    "side_effect": "none",
                }
            },
        }
        catalogs = _vendor_catalogs() | _pin(descriptor, vendor_row, name="ping.json")
        lines = _lines(_derive_document(descriptor, catalogs, member_corpus))
        assert (
            "dataset member com.meridian.m400.ping/1.0.0: no dataset surface "
            "declared (the action's control renders on device-features)"
            in lines
        ), lines

    def test_an_unresolved_channel_role_reports_every_run(
        self, member_corpus: Path
    ) -> None:
        """The B1 closure: a channel whose role matches no resolved
        channels slot derives nothing and reports — never silent."""
        descriptor = _m400()
        descriptor["channels"].append(
            {
                "id": "aux1",
                "label": "Auxiliary",
                "role": "aux",
                "quantities": [],
                "parameter_names": [],
            }
        )
        lines = _lines(
            _derive_document(descriptor, _vendor_catalogs(), member_corpus)
        )
        assert "channel aux1 (role aux): resolves to no lanes surface" in lines, lines

    def test_an_unhosted_decoder_names_the_plot_kind(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        decoder_raw = (FIXTURES / "decoder-uart.json").read_bytes()
        descriptor["decoders"] = [
            {
                "id": "uart-decoder",
                "path": "decoder-uart.json",
                "sha256": hashlib.sha256(decoder_raw).hexdigest(),
            }
        ]
        lines = _lines(
            _derive_document(descriptor, _vendor_catalogs(), member_corpus)
        )
        assert (
            "custom decoder uart-decoder: no lane host (this class's plot "
            "is waveform; lanes host in digital_lanes plots alone)" in lines
        ), lines

    def test_a_computed_variable_states_its_composed_surface(
        self, member_corpus: Path
    ) -> None:
        descriptor = _m400()
        descriptor["derived_variables"] = [
            {
                "id": "rms_v",
                "quantity": "voltage",
                "unit": "V",
                "expression": "rms(ch1)",
            }
        ]
        lines = _lines(
            _derive_document(descriptor, _vendor_catalogs(), member_corpus)
        )
        assert (
            "observation variable rms_v: computed variable derives into "
            "dataset variables (no tile; no parameter to read)" in lines
        ), lines


class TestTheSeam:
    """The profile seam (B4's motion 1, gateway-side): the canonical
    validator reads the accepted pinned documents beside the corpus set
    through the shared guard, so a composed member's target naming its
    declaration's vendor row validates — the negative control proves the
    pinned rows load-bearing, not decorative."""

    def _composed_settings_derivation(
        self, member_corpus: Path
    ) -> tuple[DerivedAttachment, dict[str, Any], dict[str, bytes]]:
        descriptor = _m400()
        _declare(descriptor, "com.meridian.m400.profile_mode/1.0.0")
        # The claim (record §0.2): the descriptor lists the vendor profile
        # id in its namespace-open profiles[], making the row claimable.
        descriptor["profiles"].append("com.meridian.m400/1.0.0")
        document = _members_document(
            [
                {
                    "slot": "vendor-configure",
                    "kind": "configuration",
                    "claims": ["com.meridian.m400.profile_mode/1.0.0"],
                    "schema_source": "input_schema",
                    "page": "configuration",
                }
            ]
        )
        vendor_row = {
            "catalog_version": "1.0.0",
            "actions": {
                "com.meridian.m400.profile_mode/1.0.0": {
                    "input_schema": {
                        "$id": "urn:meridian:action:profile_mode:input",
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string", "enum": ["fast", "precise"]}
                        },
                    },
                    "side_effect": "none",
                }
            },
        }
        catalogs = _vendor_catalogs()
        catalogs |= _pin(descriptor, vendor_row, name="vendor-extra.json")
        catalogs |= _pin(descriptor, document)
        derived = _derive_document(descriptor, catalogs, member_corpus)
        return derived, descriptor, catalogs

    def test_a_composed_target_validates_through_the_merged_documents(
        self, member_corpus: Path
    ) -> None:
        from benchweave.interfaces.ui_presentation import _pin_scoped_documents
        from benchweave.presentation.admission import validate_attachment
        from benchweave.presentation.classref import pinned_contract_documents
        from benchweave.presentation.contracts import merge_pinned_documents

        derived, descriptor, admitted = self._composed_settings_derivation(
            member_corpus
        )
        documents = merge_pinned_documents(
            _pin_scoped_documents(descriptor),
            pinned_contract_documents(descriptor, admitted),
        )
        report = validate_attachment(
            derived.envelope_raw,
            descriptor_raw=(json.dumps(descriptor, indent=2) + "\n").encode(),
            verified_resources=dict(derived.resources),
            binding_catalogue=derived.catalogue,
            schema_documents=documents,
            supported_features=frozenset(),
            supported_panels=frozenset(),
            firmware=None,
        )
        assert report.valid, [str(f) for f in report.findings]

    def test_the_pinned_rows_are_load_bearing(
        self, member_corpus: Path
    ) -> None:
        """The negative control (the B3 first-commit arm's shape): without
        the merge the same derivation fails validation on the vendor
        target — the composed profile row is what admits it."""
        from benchweave.interfaces.ui_presentation import _pin_scoped_documents
        from benchweave.presentation.admission import validate_attachment

        derived, descriptor, _admitted = self._composed_settings_derivation(
            member_corpus
        )
        report = validate_attachment(
            derived.envelope_raw,
            descriptor_raw=(json.dumps(descriptor, indent=2) + "\n").encode(),
            verified_resources=dict(derived.resources),
            binding_catalogue=derived.catalogue,
            schema_documents=_pin_scoped_documents(descriptor),
            supported_features=frozenset(),
            supported_panels=frozenset(),
            firmware=None,
        )
        assert not report.valid
        assert any(
            finding.code in ("capability_mismatch", "unresolved_reference")
            for finding in report.findings
        ), [str(f) for f in report.findings]
