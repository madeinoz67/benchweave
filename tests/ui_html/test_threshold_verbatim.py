"""The threshold-verbatim check (G1c design record §1.5): the UR-02
fail-closed-parsing mechanism applied to the frozen records and the TS
source. Three arms:

- (a) durable: the #242 record's §6 threshold sentence + S3-A1/A2/A3 rows
  equal ``thresholds.py``;
- (b) durable: the #243 record's S1-A3 limiting VALUES (never its stale
  "48 values" count — asserting it would assert a known defect), plus the
  comparator SET regenerated from the TS source and asserted exactly;
- (c) port-time: the TS file's ``toBeGreaterThanOrEqual`` threshold literals
  equal the carried constants — the machine proof that "unchanged" means
  unchanged. Retires in G1e's deletion change, its evidence transcribed into
  the design record's §2 ledger with line citations.

Every parse miss REDS (fail-closed), never skips. A relaxed constant (8.0
copied as 0.8) passes the value census silently — these arms are the
load-bearing guard against exactly that (record §8 risk 1).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import thresholds
from colour_instrument import CONDITIONS as INSTRUMENT_CONDITIONS
from colour_instrument import SEVERITY_HUE_TOKENS
from thresholds import COMPARATOR_TOKENS, LEDGER_ROWS

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RECORD_242: Final[Path] = (
    _REPO_ROOT / ".claude" / "deep-review" / "2026-09-28-issue242-ui-contract-design.md"
)
RECORD_243: Final[Path] = (
    _REPO_ROOT / ".claude" / "deep-review" / "2026-09-29-issue243-ui-followon-design.md"
)
SERIES_COLORS_TS: Final[Path] = _REPO_ROOT / "ui" / "src" / "series-colors.test.ts"


def test_ledger_census_is_exactly_22_rows() -> None:
    """Acceptance A's denominator: the §2 ledger enumerates exactly 22 rows
    across groups i-iii — 6 record-backed, 8 TS-embedded (including the
    documented search-screens non-port), 8 instrument pins."""
    assert LEDGER_ROWS == (
        ("T1", "i"),
        ("T2", "i"),
        ("T3", "i"),
        ("CVD", "i"),
        ("DIST", "i"),
        ("COND", "i"),
        ("T2-ENG", "ii"),
        ("CENSUS-HARD", "ii"),
        ("CENSUS-ENG-DARK", "ii"),
        ("CENSUS-LIGHT", "ii"),
        ("LIM-T1", "ii"),
        ("LIM-T2", "ii"),
        ("LIM-T2-ENG", "ii"),
        ("SEARCH-SCREENS", "ii"),
        ("I1", "iii"),
        ("I2", "iii"),
        ("I3", "iii"),
        ("I4", "iii"),
        ("I5", "iii"),
        ("I6", "iii"),
        ("I7", "iii"),
        ("I8", "iii"),
    )
    # The light-census asymmetry is structural: there is deliberately NO
    # light engineering-floor constant (row CENSUS-LIGHT; the measured light
    # min 8.19 is below +1.0 — a symmetric constant would invite forbidden
    # threshold relaxation).
    assert not hasattr(thresholds, "CENSUS_LIGHT_ENG_FLOOR")


def test_arm_a_record_242_thresholds_match_the_ledger() -> None:
    """Arm (a): parse the #242 record's §6 threshold sentence and S3-A1/A2/A3
    rows; assert equality with thresholds.py (equality, never >= — a raised
    OR lowered constant reds)."""
    text = RECORD_242.read_text(encoding="utf-8")
    sentence = re.search(
        r"Pre-committed thresholds .*?"
        r"T1 ≥ ([0-9.]+):1 .*?"
        r"T2 CIEDE2000 ≥ ([0-9.]+) per pair per\s+viewing condition \{([a-z, ]+)\}.*?"
        r"T3 CIEDE2000 ≥ ([0-9.]+) for\s+adjacent slots",
        text,
        re.DOTALL,
    )
    assert sentence is not None, "the #242 §6 threshold sentence did not parse (fail-closed)"
    t1, conditions_raw, t3 = sentence.group(1), sentence.group(3), sentence.group(4)
    t2 = sentence.group(2)
    assert float(t1) == thresholds.T1_CONTRAST, "T1 drifted from the frozen record"
    assert float(t2) == thresholds.T2_SEVERITY, "T2 drifted from the frozen record"
    assert float(t3) == thresholds.T3_ADJACENT, "T3 drifted from the frozen record"
    conditions = tuple(c.strip() for c in conditions_raw.split(","))
    assert conditions == thresholds.CONDITIONS, "the four-condition set drifted"
    assert conditions == INSTRUMENT_CONDITIONS, "the instrument's condition set drifted"
    # The S3-A1/A2/A3 rows agree with the sentence (both directions).
    for row_id, floor in (("S3-A1", float(t1)), ("S3-A2", float(t2)), ("S3-A3", float(t3))):
        row = re.search(rf"^\| {row_id} \|.*$", text, re.MULTILINE)
        assert row is not None, f"the {row_id} row is missing from #242 §6 (fail-closed)"
        assert f"≥ {floor}" in row.group(0), f"{row_id}'s floor disagrees with the sentence"


def test_arm_b_record_243_limiting_values_and_comparator_set() -> None:
    """Arm (b): parse the #243 record's S1-A3 row for the limiting VALUES
    only; separately assert the comparator SET equals the code's exact
    7 comparators — the pinned-set guard against silently dropping the
    fold-added border comparator (record §8 risk 4)."""
    text = RECORD_243.read_text(encoding="utf-8")
    row = re.search(r"^\| S1-A3 \|.*$", text, re.MULTILINE)
    assert row is not None, "the #243 S1-A3 row did not parse (fail-closed)"
    line = row.group(0)
    t1 = re.search(r"T1 contrast ≥ ([0-9.]+):1", line)
    t2 = re.search(r"T2-limiting ΔE00 ≥ ([0-9.]+)", line)
    assert t1 is not None, "the S1-A3 T1 value did not parse (fail-closed)"
    assert t2 is not None, "the S1-A3 T2-limiting value did not parse (fail-closed)"
    assert float(t1.group(1)) == thresholds.LIM_T1_CONTRAST
    assert float(t2.group(1)) == thresholds.LIM_T2_SEVERITY
    # The comparator set, regenerated from the TS source's severityAll loop:
    # the five severity hues + --bw-text-muted + --bw-border, exactly.
    ts = SERIES_COLORS_TS.read_text(encoding="utf-8")
    start = ts.index("const severityAll")
    end = ts.index("for (const [name, tokens] of THEMES)", start)
    parsed = set(re.findall(r'"(--bw-[\w-]+)"', ts[start:end]))
    assert len(parsed) == 7, f"the TS comparator loop parsed {len(parsed)} tokens, expected 7"
    assert parsed == set(COMPARATOR_TOKENS), "the TS comparator set drifted from the ledger"
    assert set(SEVERITY_HUE_TOKENS) | {"--bw-text-muted", "--bw-border"} == set(COMPARATOR_TOKENS)


def test_arm_c_ts_threshold_literals_match_carried_constants() -> None:
    """Arm (c): the TS file's toBeGreaterThanOrEqual threshold literals equal
    the carried constants as a SET, both directions — the machine proof that
    "unchanged" means unchanged. This set covers every carried group-ii
    numeric constant (11.0 = T2-ENG = LIM-T2-ENG; 8.0 = CENSUS-HARD = T3;
    9.0 = CENSUS-ENG-DARK; 3.0 = LIM-T1 = T1; 10.0 = LIM-T2 = T2)."""
    ts = SERIES_COLORS_TS.read_text(encoding="utf-8")
    literals = {float(m) for m in re.findall(r"toBeGreaterThanOrEqual\(([0-9.]+)\)", ts)}
    carried = {
        thresholds.T1_CONTRAST,
        thresholds.T2_SEVERITY,
        thresholds.T3_ADJACENT,
        thresholds.T2_ENG_FLOOR,
        thresholds.CENSUS_HARD,
        thresholds.CENSUS_DARK_ENG_FLOOR,
    }
    assert literals == carried, (
        "the TS threshold literals and the carried constants disagree — "
        "one side of the two-home window has drifted"
    )
