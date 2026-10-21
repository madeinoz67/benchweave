"""The shared class-reference mockup census (L12 of the class sweep;
design record ``.claude/deep-review/2026-10-19-classref-l12-dmm-design.md``
§6): the placement-aware hook census, the §E.1 hook tuple and the
placement contract, lifted from ``test_classref_dc_psu.py`` (L11's A3
instrument, authored in the 2026-10-18 record and folded once by its
refute — F1's placement-awareness) so every class arm of the sweep keys
on ONE instrument, never a per-class fork.

L13 extension (oscilloscope; design record
``.claude/deep-review/2026-10-19-classref-l13-oscilloscope-design.md``
§6): the capture classes render run controls, so the instrument carries
the ``bw-button`` root and the per-class parameterization — a hook
family set, a container map and an idiom-surface class set per mockup.
Defaults are byte-preserved for the readings classes (the dc_psu/dmm
arm sets keep importing ``HOOKS``/``PLACEMENT_*`` unchanged); the
capture instance passes its own families and containers. The idiom
record answers the design's third arm: a non-contract idiom surface
(trigger marker, cursor pair) must carry NO ``bw-`` hook at all —
reverse-planting one reds while the count census stays green.

Non-test helper in the suite's standing idiom (``colour_instrument.py``,
``thresholds.py``): imported by test modules, carrying no tests of its
own. The census counts the §E.1 contract hooks per ``data-theme``
section of a class mockup and records each occurrence's tag and ancestor
classes — placement is part of the spec (a count-conserving move of a
hook onto the wrong element is a structural lie, not a pass).
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

# The composition gate's seam into the real code path (issue #500): the
# gateway's own selection and merge, private symbol included — the same
# private-import posture ``tests/presentation/test_classref_derive.py``
# established for ``_satisfies_target``. The gate judges what production
# emits; a reimplementation here would drift unnoticed.
from benchweave.presentation.classref import (
    _merge_references,
    family_version,
    select_references,
)

#: The §E.1 contract hooks a class mockup carries (RC-L11-3): the
#: component roots the census keys on — never bespoke selectors.
HOOKS = ("bw-reading", "bw-alert-bubble", "bw-plot", "bw-data-table")

#: The placement contract (the refute fold's F1): each hook names its
#: §E.1 component ROOT element, and the two container-scoped hooks sit in
#: their mockup containers — `bw-reading` only inside the readings row,
#: `bw-plot` only inside the lower grid. The mockup is the spec;
#: placement is part of the spec.
PLACEMENT_TAG: dict[str, str] = {
    "bw-reading": "article",
    "bw-alert-bubble": "aside",
    "bw-plot": "section",
    "bw-data-table": "table",
    "bw-button": "button",
}
PLACEMENT_CONTAINER: dict[str, str] = {
    "bw-reading": "readings",
    "bw-plot": "lower",
}


def load_document(path: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


class HookCensus(HTMLParser):
    """The §E.1 hook count per ``data-theme`` section of a mockup, with
    each occurrence's tag and the classes of its ancestors — the census
    is PLACEMENT-AWARE (the refute fold's F1: a count-conserving move of
    a hook onto the wrong element is a structural lie, not a pass)."""

    VOID = {"meta", "br", "img", "input", "hr", "link", "line", "rect",
            "path", "pattern", "polyline"}

    def __init__(
        self,
        hooks: tuple[str, ...] = HOOKS,
        containers: dict[str, str] | None = None,
        idiom_classes: frozenset[str] = frozenset(),
    ) -> None:
        super().__init__()
        self.hooks = hooks
        self.containers = (
            dict(PLACEMENT_CONTAINER) if containers is None else dict(containers)
        )
        self.idiom_classes = idiom_classes
        self.counts: dict[str, dict[str, int]] = {}
        #: (theme, hook, tag, ancestors) per hook occurrence, where each
        #: ancestor is the (tag, class-tuple) pair from the open stack.
        self.placements: list[
            tuple[str, str, str, tuple[tuple[str, tuple[str, ...]], ...]]
        ] = []
        #: elements carrying the "control" class (the staged-output card)
        #: and any hook they carry — the cannot_derive surface.
        self.control_hooks: list[tuple[str, str, tuple[str, ...]]] = []
        #: (theme, tag, classes, bw-prefixed classes carried) per element
        #: carrying an idiom class — a non-contract idiom surface must
        #: carry NO `bw-` hook (the L13 arm).
        self.idiom_surfaces: list[
            tuple[str, str, tuple[str, ...], tuple[str, ...]]
        ] = []
        self._theme: str | None = None
        self._stack: list[tuple[str, tuple[str, ...]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = {key: value for key, value in attrs}
        classes = tuple((fields.get("class") or "").split())
        class_set = set(classes)
        theme = fields.get("data-theme")
        if "mock-theme" in class_set and theme is not None:
            self._theme = theme
            self.counts[theme] = {hook: 0 for hook in self.hooks}
            self._stack.append((tag, classes))
            return
        if self._theme is not None:
            for hook in self.hooks:
                if hook in class_set:
                    self.counts[self._theme][hook] += 1
                    self.placements.append(
                        (self._theme, hook, tag, tuple(self._stack))
                    )
            if "control" in class_set:
                self.control_hooks.append(
                    (
                        self._theme or "",
                        tag,
                        tuple(hook for hook in self.hooks if hook in class_set),
                    )
                )
            if self.idiom_classes & class_set:
                self.idiom_surfaces.append(
                    (
                        self._theme or "",
                        tag,
                        classes,
                        tuple(sorted(c for c in classes if c.startswith("bw-"))),
                    )
                )
        if tag not in self.VOID:
            self._stack.append((tag, classes))

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID:
            return
        if self._stack:
            self._stack.pop()


def hook_census(
    mockup: Path, hooks: tuple[str, ...] = HOOKS
) -> dict[str, dict[str, int]]:
    """The per-theme hook counts of one class mockup, over the hook
    family set that mockup's class carries (the default is the readings
    classes' shared set)."""
    parser = HookCensus(hooks=hooks)
    parser.feed(mockup.read_text(encoding="utf-8"))
    return parser.counts


def resolve_count(expression: str, counters: dict[str, int]) -> int:
    """The closed count grammar the expect block authors: a pure-numeric
    literal or a ``{name}`` expression over the structural counters. An
    expression outside the closure refuses — an unknown name cannot
    launder a divergence."""
    if re.fullmatch(r"[0-9]+", expression):
        return int(expression)
    match = re.fullmatch(r"\{([a-z_]+)\}", expression)
    if match is not None and match.group(1) in counters:
        return counters[match.group(1)]
    raise AssertionError(f"unknown count expression: {expression!r}")


# --- the cross-class composition gate (issue #500; design record ----------------
# --- .claude/deep-review/2026-10-20-classref-composition-gate-design.md) -------


def family_profile_ids(corpus: Path) -> list[str]:
    """The ACTIVE family's class profile ids, discovered the way the
    production selection walk discovers references: the same
    ``class-*.json`` glob ``_find_reference`` walks under the served
    version, the same ``profile_id`` acceptance it applies. The gate's
    pair set derives from the CURRENT family, never a frozen list — a
    ninth class widens the gate automatically (the flip-target rotation
    rule; an arm banked against yesterday's family goes dead silently
    otherwise)."""
    version = family_version(corpus)
    root = corpus / "plugin-ui-class-reference" / version
    profile_ids: list[str] = []
    for path in sorted(root.glob("class-*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and str(
            document.get("profile_id", "")
        ).startswith("otdp."):
            profile_ids.append(str(document["profile_id"]))
    return profile_ids


def merge_selected(
    references: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The merge the real code path runs: sort bytewise by profile id
    (the order ``select_references`` returns and ``derive_attachment``
    re-establishes for override inputs), then the gateway's own
    ``_merge_references`` — first reference bare, every later one
    ``{slug}-`` prefixed. The seam both the pair gate and the refusal
    arms compose through: selection for corpus classes, direct sorted
    documents for synthetic ones (the corpus cannot carry a colliding
    class without a standards bump)."""
    ordered = sorted(references, key=lambda item: str(item["profile_id"]))
    return ordered, _merge_references(ordered)


def compose_pair(
    corpus: Path, profile_ids: tuple[str, ...]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One synthetic two-profile descriptor run through the REAL
    selection and merge: ``select_references`` over ``{"profiles":
    [...]}`` (digest-verified corpus reads, bytewise ordering, skip of
    profile ids without a reference), asserting every claimed class was
    selected, then ``merge_selected``. Raises ``AssertionError`` when
    selection drops a claimed class — the pair gate never composes a
    half-selected device."""
    descriptor = {"profiles": [str(profile) for profile in profile_ids]}
    references = select_references(corpus, descriptor)
    if references is None or len(references) != len(set(descriptor["profiles"])):
        found = [] if references is None else [str(r["profile_id"]) for r in references]
        raise AssertionError(
            f"selection dropped a claimed class: claimed "
            f"{sorted(set(descriptor['profiles']))}, selected {sorted(found)}"
        )
    return merge_selected(references)


def _emitted_identifier_owners(
    references: list[dict[str, Any]],
) -> dict[tuple[str, str], list[str]]:
    """Per (identifier kind, identifier), the profiles whose merge
    emission produces it — the merge's own transform re-derived (bare
    for the first reference, ``{slug}-`` prefixed slot keys, page ids
    and layout page ids for later ones; ``expect.controls`` URNs ride
    unprefixed, a control's identity being its URN). Re-derived from the
    merge's current shape at every call, never copied from a design
    record."""
    owners: dict[tuple[str, str], list[str]] = {}
    for index, item in enumerate(references):
        profile = str(item["profile_id"])
        slug = "" if index == 0 else profile.split("/")[0].replace(".", "-")

        def emit(kind: str, identifier: str, *, who: str = profile) -> None:
            owners.setdefault((kind, identifier), []).append(who)

        for key in item.get("slots", {}):
            emit("slot", f"{slug}-{key}" if slug else str(key))
        for page in item.get("pages", []):
            emit("page", f"{slug}-{page['id']}" if slug else str(page["id"]))
        for layout_page in item.get("layouts", []):
            emit(
                "layout-page",
                f"{slug}-{layout_page['page_id']}"
                if slug
                else str(layout_page["page_id"]),
            )
        for urn in item.get("expect", {}).get("controls", {}):
            emit("control-urn", str(urn))
    return owners


def composition_findings(references: list[dict[str, Any]]) -> list[str]:
    """The composition gate's refusals: every identifier the composed
    document would carry twice, WITH attribution — the two profiles whose
    emissions collide under the merge prefixing. Four kinds: slot keys
    (the composed binding namespace — the control handles the manifest's
    pages bind), page template ids, authored layout page ids, and
    ``expect.controls`` action URNs (two classes claiming one URN is a
    duplicate control identifier no prefixing can separate). Sorted, so
    a refusal is byte-stable across runs."""
    findings: list[str] = []
    for (kind, identifier), emitters in sorted(
        _emitted_identifier_owners(references).items()
    ):
        if len(emitters) > 1:
            findings.append(
                f"{kind} {identifier!r} is emitted by both "
                f"{' and '.join(emitters)} under the merge prefixing"
            )
    return findings
