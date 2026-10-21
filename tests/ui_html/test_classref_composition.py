"""The cross-class composition gate (gateway issue #500; design record
``.claude/deep-review/2026-10-20-classref-composition-gate-design.md``).

A device may claim several class profiles — the descriptor's
``profiles`` array has no maximum — and the gateway merges the selected
references per parent §3.8 (first profile bare, later ones
``{slug}-`` prefixed). Every class reference is authored in isolation,
and until this gate no instrument composed two classes: a class whose
identifiers collide with another class's prefixed identifiers landed
clean — the family schema admits the colliding literal, the per-class
gates never merge, and the merge itself overwrites silently. The defect
appears only when a device claims two classes.

The gate runs every unordered pair of the ACTIVE family's classes
through the REAL selection and merge (``select_references`` +
``_merge_references``, via the census instrument's seam) and refuses
any identifier the composed document would carry twice: slot keys, page
template ids, authored layout page ids, and ``expect.controls`` action
URNs — with attribution naming the colliding profiles. The pair set
derives from the current family (``family_profile_ids``), never a
frozen list.

The RED demonstration (design record §3) proves the gate can refuse:
the deliberately colliding class passes every existing gate first (the
issue's premise — the schema is collision-blind), then the gate refuses
it from both directions — a NEW class colliding with an existing one,
and an EXISTING class edited so a new one collides — and under either
sort order. A clean synthetic class composes with every existing class
with zero findings: the gate refuses collisions, not new classes.

Instrument: ``tests/ui_html/classref_census.py`` (extended — the
family's shared instrument since L12; no second census).
"""

from __future__ import annotations

import copy
from itertools import combinations
from typing import Any

from classref_census import (
    compose_pair,
    composition_findings,
    family_profile_ids,
    merge_selected,
)

from benchweave.presentation.classref import validate_reference_document
from benchweave.vendoring import corpus_root

CORPUS = corpus_root()

#: Synthetic profile ids for the refusal arms. The first sorts before
#: and the last after the ``otdp.d*`` targets — the sort geometry is
#: ASSERTED in the arms, not assumed (the flip-target rotation rule: an
#: arm whose geometry is stale goes dead silently).
_SYNTHETIC_FIRST = "otdp.composed_probe/1.0.0"
_SYNTHETIC_LAST = "otdp.probe_marker/1.0.0"


def _family_references() -> dict[str, dict[str, Any]]:
    """Every family class's reference, selected through the REAL path
    (a one-profile synthetic descriptor per class)."""
    return {
        profile: compose_pair(CORPUS, (profile,))[0][0]
        for profile in family_profile_ids(CORPUS)
    }


def _target_class(
    references: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    """The refusal arms' target, re-derived from the CURRENT family (the
    first class carrying a ``capture`` slot — ``otdp.daq`` today), never
    named from a design record."""
    for profile_id in sorted(references):
        if "capture" in references[profile_id].get("slots", {}):
            return profile_id, references[profile_id]
    raise AssertionError("no family class carries a capture slot")


def _rename_slot(document: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    """Rename one slot key through the document's own slot and binding
    references, leaving the document schema-valid."""
    slots = document["slots"]
    slots[new] = slots.pop(old)
    for page in document.get("pages", []):
        page["binding_slots"] = [
            new if key == old else key for key in page.get("binding_slots", [])
        ]
    return document


def _rename_into_namespace(
    document: dict[str, Any], namespace_profile_id: str
) -> dict[str, Any]:
    """Rename one slot, one page id and one layout page id into another
    class's prefixed namespace — the ``{slug}-`` shape the merge gives a
    later profile. This is the authoring assumption the gate refuses: a
    class writing into a namespace only the MERGE creates."""
    prefix = f"{namespace_profile_id.split('/')[0].replace('.', '-')}-"
    _rename_slot(document, "capture", f"{prefix}capture")
    for page in document.get("pages", []):
        if str(page["id"]) == "capture":
            page["id"] = f"{prefix}capture"
    for layout_page in document.get("layouts", []):
        if str(layout_page.get("page_id")) == "capture":
            layout_page["page_id"] = f"{prefix}capture"
    return document


def _synthetic_class(
    reference: dict[str, Any],
    profile_id: str,
    *,
    into_namespace: str | None = None,
    controls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """A synthetic class reference built from a real one: retitled
    profile, optionally renamed into another class's prefixed namespace
    (the collision arms) and with ``expect.controls`` replaced (empty
    for the identifier arms, copied for the URN arm)."""
    document = copy.deepcopy(reference)
    document["profile_id"] = profile_id
    document["title"] = "Invented composition probe (fixture vocabulary)"
    if controls is not None:
        document.setdefault("expect", {})["controls"] = dict(controls)
    if into_namespace is not None:
        _rename_into_namespace(document, into_namespace)
    return document


def _collides_verbatim(findings: list[str]) -> bool:
    """The three identifier findings a ``capture``-slot class renamed
    into another class's namespace must produce, verbatim checks."""
    return len(findings) == 3 and {
        finding.split(" ", 1)[0] for finding in findings
    } == {"slot", "page", "layout-page"}


class TestFamilyComposition:
    """The gate itself: every pair of the active family composes through
    the real code path with zero identifier findings."""

    def test_every_pair_composes_without_identifier_collisions(self) -> None:
        """C(n,2) synthetic two-profile descriptors over the active
        family — each through the REAL ``select_references`` and the
        REAL ``_merge_references`` — carry no duplicate identifier."""
        profiles = sorted(family_profile_ids(CORPUS))
        assert len(profiles) >= 8, (
            f"family discovery shrank: {len(profiles)} classes "
            f"({profiles}) — the gate must cover the whole family"
        )
        for first, second in combinations(profiles, 2):
            references, merged = compose_pair(CORPUS, (first, second))
            findings = composition_findings(references)
            assert findings == [], (
                f"{first} + {second} collides under the merge: {findings}"
            )
            # The re-derived prediction and the real merge output agree:
            # a collision the merge would overwrite silently must not
            # pass through either surface.
            emitted = sum(len(item.get("slots", {})) for item in references)
            assert len(merged["slots"]) == emitted, (
                f"{first} + {second}: merge dropped a slot "
                f"({emitted} emitted -> {len(merged['slots'])} carried)"
            )
            page_ids = [str(page["id"]) for page in merged["pages"]]
            assert len(set(page_ids)) == len(page_ids), (
                f"{first} + {second}: duplicate page id {page_ids}"
            )

    def test_pair_coverage_spans_the_whole_family(self) -> None:
        """The pair set is exactly C(n,2) over the discovered family and
        every class is paired at least once — the gate cannot silently
        skip a class (the flip-target rotation rule's mechanical form)."""
        profiles = sorted(family_profile_ids(CORPUS))
        pairs = list(combinations(profiles, 2))
        assert len(pairs) == len(profiles) * (len(profiles) - 1) // 2
        seen: set[str] = set()
        for first, second in pairs:
            seen.update((first, second))
        assert seen == set(profiles), (
            f"unpaired classes: {sorted(set(profiles) - seen)}"
        )


class TestGateRefuses:
    """The RED demonstration (design record §3): the gate refuses a
    deliberately colliding class in both directions, under either sort
    order — and a clean class composes untouched.

    The synthetic documents are built from a real family reference
    (retitled, identifiers renamed into another class's prefixed
    namespace) so they stay schema-valid by construction. The corpus
    cannot carry a colliding class without a standards bump, so these
    arms compose through ``merge_selected`` — the same sorted merge the
    real path runs after selection (the census seam's documented
    posture)."""

    def test_new_class_colliding_with_existing_refuses(self) -> None:
        """Direction 1 — a NEW class collides with an existing one. The
        premise rides the same document: it is schema-valid and the bare
        merge accepts it SILENTLY (the overwrite the issue exists to
        refuse), then the gate refuses all three identifier kinds with
        attribution."""
        references = _family_references()
        target_profile, target_reference = _target_class(references)
        assert target_profile > _SYNTHETIC_FIRST, "sort geometry drifted"
        colliding = _synthetic_class(
            target_reference,
            _SYNTHETIC_FIRST,
            into_namespace=target_profile,
            controls={},
        )
        # Premise: every existing gate is blind to the collision — the
        # schema validates the colliding literal, and the bare merge
        # overwrites it silently (one slot fewer than emitted).
        validate_reference_document(colliding, corpus=CORPUS)
        ordered, merged = merge_selected([colliding, target_reference])
        assert ordered[0]["profile_id"] == _SYNTHETIC_FIRST
        emitted = sum(len(item.get("slots", {})) for item in ordered)
        assert len(merged["slots"]) < emitted, (
            "the bare merge no longer overwrites silently — the premise "
            "this gate exists to close has closed; re-derive the arms"
        )
        findings = composition_findings(ordered)
        assert _collides_verbatim(findings), findings
        assert all(
            _SYNTHETIC_FIRST in finding and target_profile in finding
            for finding in findings
        ), findings

    def test_existing_class_edit_collides_with_new_class(self) -> None:
        """Direction 2 — an EXISTING class changes in a way that collides
        with a NEW one. The edited class is the real family member; the
        new class's own identifiers are plain. The gate refuses, and the
        silent overwrite rides the same composition."""
        references = _family_references()
        target_profile, target_reference = _target_class(references)
        assert target_profile < _SYNTHETIC_LAST, "sort geometry drifted"
        edited = _rename_into_namespace(
            copy.deepcopy(target_reference), _SYNTHETIC_LAST
        )
        newcomer = _synthetic_class(target_reference, _SYNTHETIC_LAST, controls={})
        validate_reference_document(edited, corpus=CORPUS)
        validate_reference_document(newcomer, corpus=CORPUS)
        ordered, merged = merge_selected([edited, newcomer])
        assert ordered[0]["profile_id"] == target_profile
        findings = composition_findings(ordered)
        assert _collides_verbatim(findings), findings
        emitted = sum(len(item.get("slots", {})) for item in ordered)
        assert len(merged["slots"]) < emitted

    def test_sort_order_never_decides_the_refusal(self) -> None:
        """The M7 principle at the identifier level: the same collision
        shape refuses identically whichever side sorts first — the merge
        order must not decide what the gate checks."""
        references = _family_references()
        target_profile, target_reference = _target_class(references)
        on_first = _synthetic_class(
            target_reference,
            _SYNTHETIC_FIRST,
            into_namespace=target_profile,
            controls={},
        )
        findings_first = composition_findings(
            merge_selected([on_first, target_reference])[0]
        )
        on_second = _rename_into_namespace(
            copy.deepcopy(target_reference), _SYNTHETIC_LAST
        )
        newcomer = _synthetic_class(target_reference, _SYNTHETIC_LAST, controls={})
        findings_second = composition_findings(
            merge_selected([on_second, newcomer])[0]
        )
        assert _collides_verbatim(findings_first), findings_first
        assert _collides_verbatim(findings_second), findings_second
        kinds_first = sorted(f.split(" ", 1)[0] for f in findings_first)
        kinds_second = sorted(f.split(" ", 1)[0] for f in findings_second)
        assert kinds_first == kinds_second, (findings_first, findings_second)

    def test_two_classes_claiming_one_action_urn_refuse(self) -> None:
        """A control's identity is its action URN: two classes claiming
        one URN in ``expect.controls`` is a duplicate control identifier
        no prefixing can separate."""
        references = _family_references()
        target_profile, target_reference = _target_class(references)
        urns = sorted(
            str(urn)
            for urn in target_reference.get("expect", {}).get("controls", {})
        )
        assert urns, "the target class claims no controls"
        probe = _synthetic_class(
            target_reference,
            _SYNTHETIC_LAST,
            controls=dict(
                target_reference.get("expect", {}).get("controls", {})
            ),
        )
        validate_reference_document(probe, corpus=CORPUS)
        ordered, _merged = merge_selected([probe, target_reference])
        findings = composition_findings(ordered)
        for urn in urns:
            assert any(
                finding.startswith(f"control-urn '{urn}'")
                and target_profile in finding
                and _SYNTHETIC_LAST in finding
                for finding in findings
            ), (urn, findings)

    def test_clean_new_class_composes_with_every_existing_class(self) -> None:
        """Specificity: a clean synthetic class (plain ids, empty
        controls) composes with every family class with ZERO findings —
        the gate refuses collisions, not new classes."""
        references = _family_references()
        target_profile, target_reference = _target_class(references)
        clean = _synthetic_class(target_reference, _SYNTHETIC_LAST, controls={})
        validate_reference_document(clean, corpus=CORPUS)
        for profile in sorted(references):
            ordered, merged = merge_selected(
                [clean, copy.deepcopy(references[profile])]
            )
            findings = composition_findings(ordered)
            assert findings == [], (profile, findings)
            emitted = sum(len(item.get("slots", {})) for item in ordered)
            assert len(merged["slots"]) == emitted, profile
