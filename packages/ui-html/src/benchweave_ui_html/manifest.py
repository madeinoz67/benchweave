"""The committed 28-table manifest — the corrected enumeration (design record §5).

This is the second, independent count (the contract's own ``Schema: … — N
rows`` lines are the first): the harness pins these headings, header cells and
row counts regardless of what the contract text claims, so a coordinated edit
of a table plus its Schema line still reds the pin layer.

F1 fold (2026-10-01): every entry also pins its exact ORDERED key list — the
identity pin, the same coupling as the TS fold-P5 key arrays. A row swap
between same-schema tables, a delete-and-pad, a duplicated key or a reorder
keeps counts and header cells green; the key list is what reds it, naming the
first divergence. The 168 literal keys ARE the pin.

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
    keys: tuple[str, ...]
    slug: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "slug", slug_for_heading(self.heading))


MANIFEST: tuple[ManifestTable, ...] = (
    ManifestTable(
        "### §A.1 Colour palette",
        ("Token", "Light", "Dark", "Use"),
        25,
        "token_pair",
        (
            "--bw-canvas",
            "--bw-surface",
            "--bw-surface-recessed",
            "--bw-text",
            "--bw-text-muted",
            "--bw-border",
            "--bw-accent",
            "--bw-accent-contrast",
            "--bw-focus",
            "--bw-advisory",
            "--bw-warning",
            "--bw-critical",
            "--bw-trip",
            "--bw-success",
            "--bw-limiting",
            "--bw-series-1",
            "--bw-series-2",
            "--bw-series-3",
            "--bw-series-4",
            "--bw-series-5",
            "--bw-series-6",
            "--bw-series-7",
            "--bw-series-8",
            "--bw-shadow-dark",
            "--bw-shadow-light",
        ),
    ),
    ManifestTable(
        "### §A.2 Spacing and layout",
        ("Token", "Value", "Typical use"),
        6,
        "token_value",
        (
            "--bw-space-1",
            "--bw-space-2",
            "--bw-space-3",
            "--bw-space-4",
            "--bw-space-5",
            "--bw-space-6",
        ),
    ),
    ManifestTable(
        "### §A.3 Radius",
        ("Token", "Value", "Use"),
        2,
        "token_value",
        ("--bw-radius-control", "--bw-radius-panel"),
    ),
    ManifestTable(
        "### §A.4 Typography fonts",
        ("Token", "Value", "Use"),
        2,
        "token_value",
        ("--bw-font-ui", "--bw-font-data"),
    ),
    ManifestTable(
        "### §B.1 Severities",
        ("Severity key", "Meaning", "Dismissal class", "Live region"),
        6,
        "severity_row",
        ("neutral", "success", "advisory", "warning", "critical", "trip"),
    ),
    ManifestTable(
        "### §B.2 State rules",
        ("Rule id", "Requirement"),
        3,
        "rule_proof",
        ("SR-B1", "SR-B2", "SR-B3"),
    ),
    ManifestTable(
        "### §B.3 Reading states",
        ("State key", "Meaning", "Rendering", "Announcement"),
        1,
        "state_row",
        ("limiting",),
    ),
    ManifestTable(
        "### §B.4 Staleness",
        ("Rule id", "Requirement"),
        4,
        "rule_proof",
        ("ST-1", "ST-2", "ST-3", "ST-4"),
    ),
    ManifestTable(
        "### §C.1 Safety rules",
        ("Rule id", "Requirement"),
        3,
        "rule_proof",
        ("R-ENERGISE-1", "R-DEENERGISE-1", "R-PROTECT-1"),
    ),
    ManifestTable(
        "### §C.2 Disabled-reason enum",
        ("Key", "Required label text", "Parameter"),
        5,
        "label_render",
        (
            "capability-absent",
            "device-state",
            "protection-active",
            "invalid-staged-input",
            "no-authority",
        ),
    ),
    ManifestTable(
        "### §C.3 Refusal mapping",
        ("Code", "Severity", "What happened", "Sent status", "Operator action"),
        15,
        "refusal_render",
        (
            "invalid_request",
            "unauthenticated",
            "forbidden",
            "not_found",
            "conflict",
            "policy_denied",
            "not_ready",
            "gone",
            "cursor_expired",
            "event_gap",
            "payload_too_large",
            "rate_limited",
            "unavailable",
            "internal_error",
            "no-response",
        ),
    ),
    ManifestTable(
        "### §D.1 Modes",
        ("Mode", "Fixed wording", "Fires when"),
        4,
        "mode_row",
        ("simulated", "no-gateway", "no-lease", "no-policy"),
    ),
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
        (
            "button",
            "numeric-input",
            "rotary-control",
            "reading-tile",
            "alert-bubble",
            "engineering-plot",
            "digital-lanes",
            "data-table",
            "panel",
            "mode-banner",
            "confirm-action",
        ),
    ),
    ManifestTable(
        "#### §E.2.0 Pass-2 composition (channel_hints)",
        ("Hint", "Effect"),
        4,
        "hint_row",
        ('color_role: "accent"', 'color_role: "muted"', "visible: false", "(no hint)"),
    ),
    ManifestTable(
        "#### §E.2.1 Slot mapping",
        ("Slot i", "Colour", "Dash", "Symbol"),
        16,
        "slot_value",
        ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"),
    ),
    ManifestTable(
        "#### §E.2.2 Sequences",
        ("Key", "Shape description", "Reference binding"),
        10,
        "sequence_partial",
        (
            "dash-1",
            "dash-2",
            "symbol-1",
            "symbol-2",
            "symbol-3",
            "symbol-4",
            "symbol-5",
            "symbol-6",
            "symbol-7",
            "symbol-8",
        ),
    ),
    ManifestTable(
        "#### §E.2.3 Y-axis assignment",
        ("Condition", "Rendering"),
        4,
        "rule_proof",
        (
            "One distinct unit among the declared traces",
            "Two distinct units among the declared traces",
            "More than two distinct units among the declared traces",
            "Every trace bound to an axis is presentation-hidden",
        ),
    ),
    ManifestTable(
        "#### §E.2.4 Reference lines",
        ("Property", "Requirement"),
        4,
        "rule_proof",
        ("Labelling", "Neutrality", "Distinctness", "Carrier"),
    ),
    ManifestTable(
        "#### §E.2.5 Acquisition disclosure",
        ("Property", "Requirement"),
        3,
        "rule_proof",
        ("When required", "Placement", "Wording"),
    ),
    ManifestTable(
        "#### §E.2.6 Trace provenance",
        ("Provenance", "Required marker", "Disclosure", "Constraint"),
        4,
        "rule_proof",
        ("measured", "derived", "device-averaged", "display-processed"),
    ),
    ManifestTable(
        "### §E.3 Setpoint presentation (reading-tile sub-rows)",
        ("Role", "Placement", "Required labelling", "Never"),
        3,
        "triad_row",
        ("measured", "set", "staged"),
    ),
    ManifestTable(
        "#### §E.4.1 Lane layout",
        ("Property", "Requirement"),
        4,
        "rule_proof",
        ("Uniform bands", "Pinned labels", "Hidden lanes", "Hiding is disclosure"),
    ),
    ManifestTable(
        "#### §E.4.2 State rendering",
        ("Property", "Requirement"),
        4,
        "rule_proof",
        ("1", "0", "x` and `z", "Monochrome discriminability"),
    ),
    ManifestTable(
        "#### §E.4.3 Groups and buses",
        ("Property", "Requirement"),
        4,
        "rule_proof",
        ("Bus lane", "Radix", "Member order", "Unknown bus"),
    ),
    ManifestTable(
        "#### §E.4.4 Edge-preserving decimation (NORMATIVE)",
        ("Property", "Requirement"),
        3,
        "rule_proof",
        ("Every transition survives", "Glitch mark", "No sample dropping"),
    ),
    ManifestTable(
        "#### §E.4.5 Time axis",
        ("Property", "Requirement"),
        4,
        "rule_proof",
        ("Axis label", "Sample rate", "Trigger", "Cursors"),
    ),
    ManifestTable(
        "#### §E.4.6 Decoder lanes",
        ("Property", "Requirement"),
        4,
        "rule_proof",
        ("Span rendering", "Payload", "Disclosure", "Never orphan"),
    ),
    ManifestTable(
        "### §F.1 Icons",
        ("Icon key", "Class", "Shape description", "Reference binding"),
        10,
        "icon_partial",
        (
            "neutral",
            "success",
            "advisory",
            "warning",
            "critical",
            "trip",
            "busy",
            "hidden",
            "staged",
            "limiting",
        ),
    ),
)

TOTAL_TABLES = len(MANIFEST)
TOTAL_ROWS = sum(table.row_count for table in MANIFEST)

KIND_BY_SLUG: dict[str, str] = {table.slug: table.kind for table in MANIFEST}
