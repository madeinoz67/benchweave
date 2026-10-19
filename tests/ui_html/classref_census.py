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
