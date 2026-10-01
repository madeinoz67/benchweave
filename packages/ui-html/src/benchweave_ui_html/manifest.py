"""The committed 28-table manifest — the corrected enumeration (design record §5).

This is the second, independent count (the contract's own ``Schema: … — N
rows`` lines are the first): the harness pins these headings, header cells and
row counts regardless of what the contract text claims, so a coordinated edit
of a table plus its Schema line still reds the pin layer.

Counts are the build-time-corrected values (168 rows / 28 tables). Three
entries were corrected against the contract at build time — §E.4.2 State
rendering 3→4 (the +1 that made the design's original total 167), and a
net-zero adjacent swap §E.2.4 Reference lines 3→4 / §E.2.5 Acquisition
disclosure 4→3 — see the design record's Build-time correction.

Kinds map each table to the artifact kind its rows require (design record §2).
The design's kind list left two tables unmapped; §B.4 Staleness joins the
Rule-id|Requirement tables under ``rule_proof``, and §E.2.2 Sequences (the
§F.1 shape: key | shape description | reference binding, minus the class
column) gets its own ``sequence_partial`` kind — disclosed in the build
report as a design gap closed on contact with the contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from benchweave_ui_html.grammar import slug_for_heading


@dataclass(frozen=True)
class ManifestTable:
    heading: str
    header_cells: tuple[str, ...]
    row_count: int
    kind: str
    slug: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "slug", slug_for_heading(self.heading))


MANIFEST: tuple[ManifestTable, ...] = (
    ManifestTable("### §A.1 Colour palette", ("Token", "Light", "Dark", "Use"), 25, "token_pair"),
    ManifestTable(
        "### §A.2 Spacing and layout", ("Token", "Value", "Typical use"), 6, "token_value"
    ),
    ManifestTable("### §A.3 Radius", ("Token", "Value", "Use"), 2, "token_value"),
    ManifestTable("### §A.4 Typography fonts", ("Token", "Value", "Use"), 2, "token_value"),
    ManifestTable(
        "### §B.1 Severities",
        ("Severity key", "Meaning", "Dismissal class", "Live region"),
        6,
        "severity_row",
    ),
    ManifestTable("### §B.2 State rules", ("Rule id", "Requirement"), 3, "rule_proof"),
    ManifestTable(
        "### §B.3 Reading states",
        ("State key", "Meaning", "Rendering", "Announcement"),
        1,
        "state_row",
    ),
    ManifestTable("### §B.4 Staleness", ("Rule id", "Requirement"), 4, "rule_proof"),
    ManifestTable("### §C.1 Safety rules", ("Rule id", "Requirement"), 3, "rule_proof"),
    ManifestTable(
        "### §C.2 Disabled-reason enum",
        ("Key", "Required label text", "Parameter"),
        5,
        "label_render",
    ),
    ManifestTable(
        "### §C.3 Refusal mapping",
        ("Code", "Severity", "What happened", "Sent status", "Operator action"),
        15,
        "refusal_render",
    ),
    ManifestTable("### §D.1 Modes", ("Mode", "Fixed wording", "Fires when"), 4, "mode_row"),
    ManifestTable(
        "### §E.1 Components",
        (
            "Component",
            "Root element",
            "Required attributes",
            "Required roles",
            "Required class hooks",
            "Required text",
            "Notes",
        ),
        11,
        "component_render",
    ),
    ManifestTable(
        "#### §E.2.0 Pass-2 composition (channel_hints)", ("Hint", "Effect"), 4, "hint_row"
    ),
    ManifestTable(
        "#### §E.2.1 Slot mapping",
        ("Slot i", "Colour", "Dash", "Symbol"),
        16,
        "slot_value",
    ),
    ManifestTable(
        "#### §E.2.2 Sequences",
        ("Key", "Shape description", "Reference binding"),
        10,
        "sequence_partial",
    ),
    ManifestTable("#### §E.2.3 Y-axis assignment", ("Condition", "Rendering"), 4, "rule_proof"),
    ManifestTable("#### §E.2.4 Reference lines", ("Property", "Requirement"), 4, "rule_proof"),
    ManifestTable(
        "#### §E.2.5 Acquisition disclosure", ("Property", "Requirement"), 3, "rule_proof"
    ),
    ManifestTable(
        "#### §E.2.6 Trace provenance",
        ("Provenance", "Required marker", "Disclosure", "Constraint"),
        4,
        "rule_proof",
    ),
    ManifestTable(
        "### §E.3 Setpoint presentation (reading-tile sub-rows)",
        ("Role", "Placement", "Required labelling", "Never"),
        3,
        "triad_row",
    ),
    ManifestTable("#### §E.4.1 Lane layout", ("Property", "Requirement"), 4, "rule_proof"),
    ManifestTable("#### §E.4.2 State rendering", ("Property", "Requirement"), 4, "rule_proof"),
    ManifestTable("#### §E.4.3 Groups and buses", ("Property", "Requirement"), 4, "rule_proof"),
    ManifestTable(
        "#### §E.4.4 Edge-preserving decimation (NORMATIVE)",
        ("Property", "Requirement"),
        3,
        "rule_proof",
    ),
    ManifestTable("#### §E.4.5 Time axis", ("Property", "Requirement"), 4, "rule_proof"),
    ManifestTable("#### §E.4.6 Decoder lanes", ("Property", "Requirement"), 4, "rule_proof"),
    ManifestTable(
        "### §F.1 Icons",
        ("Icon key", "Class", "Shape description", "Reference binding"),
        10,
        "icon_partial",
    ),
)

TOTAL_TABLES = len(MANIFEST)
TOTAL_ROWS = sum(table.row_count for table in MANIFEST)

KIND_BY_SLUG: dict[str, str] = {table.slug: table.kind for table in MANIFEST}
