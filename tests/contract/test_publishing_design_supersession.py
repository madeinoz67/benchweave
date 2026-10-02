"""The parent publishing design's mirror/sync prose is superseded (fold G1).

``docs/implementation-planning/10-contributor-publishing-design.md`` still
describes the deleted catalogue architecture (the committed gateway mirror,
the two-sided drift gate, the assembly render) in §3.4 and §5 — and slices
3–6 of that lane build from this doc. The slice-2 pivot record
(``.claude/deep-review/2026-10-02-issue224-s2-pivot-registry-hosted-catalogue.md``)
is the authority for what was built instead: the catalogue is registry-hosted
and deploy-time generated; the gateway website carries a static teaser with
zero catalogue-derived bytes. The doc is class-6 living-until-close-out, so
the stale sections carry a dated in-place supersession note at their top —
a reader cannot reach the mirror prose without passing the note. This test
mechanizes that: the note, its date, and the pivot-record path must be the
first paragraph of each affected section. What this does not catch: stale
architecture prose elsewhere in the doc that no note names — §2's
single mirror clause and §4's slice-2 subsection are covered by the same
pivot record but are not separately asserted here.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "implementation-planning" / "10-contributor-publishing-design.md"

PIVOT_RECORD = ".claude/deep-review/2026-10-02-issue224-s2-pivot-registry-hosted-catalogue.md"
PIVOT_DATE = "2026-10-02"

#: The sections whose bodies still describe the deleted mirror/sync
#: architecture (fold G1's scope: §3.4 the mechanism, §5 the governance
#: appendix that drafted the CON-13 amendment and the class-11 taxonomy
#: entry for the mirror).
SUPERSEDED_SECTIONS = (
    "### 3.4 Catalogue and search on the public website",
    "## 5. Invariant and governance impacts",
)


def _section_body(heading: str) -> str:
    """The section's own body: after the heading line, up to the next
    heading of any level. Fails loudly when the heading moves or vanishes —
    a scanner over an absent section is blind, not green."""
    text = DOC.read_text(encoding="utf-8")
    start = text.index(heading)
    line_end = text.find("\n", start)
    rest = text[line_end + 1 :]
    nxt = rest.find("\n#")
    return rest[: nxt if nxt != -1 else len(rest)]


def test_mirror_sections_lead_with_the_pivot_supersession() -> None:
    """Each affected section's FIRST paragraph is the dated supersession
    note naming the pivot record — the note cannot be buried below the
    stale prose it supersedes."""
    for heading in SUPERSEDED_SECTIONS:
        body = _section_body(heading)
        first_paragraph = body.lstrip("\n").split("\n\n", 1)[0]
        assert first_paragraph.startswith("**Superseded"), (
            f"{heading!r}: no supersession note at the top of the section"
        )
        assert PIVOT_DATE in first_paragraph, (
            f"{heading!r}: the supersession note is not dated"
        )
        assert PIVOT_RECORD in first_paragraph, (
            f"{heading!r}: the supersession note does not name the pivot record"
        )


def test_superseded_prose_still_names_the_deleted_mechanism() -> None:
    """The note supersedes real prose, not a ghost: each section's body
    still contains the mirror prose being superseded (the frozen history
    the note points past). If a later slice legitimately rewrites these
    sections, this test and the note retire together."""
    for heading in SUPERSEDED_SECTIONS:
        body = _section_body(heading)
        assert "mirror" in body, f"{heading!r}: the mirror prose is gone — retire this suite"
