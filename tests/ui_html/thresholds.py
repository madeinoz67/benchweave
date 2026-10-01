"""The threshold ledger (G1c design record §2) as named constants, verbatim,
each citing its ledger row.

Thresholds are never tuned to make a row green: a red row means the port is
wrong or the tokens moved, and either way it ships nothing. The verbatim arms
in ``test_threshold_verbatim.py`` are the load-bearing guard — they parse the
frozen records and the TS source and refuse any drift between those bytes and
these constants, in both directions.

Denominator convention (record §2, claim discipline): "values" in the #242
record counts pair-cells; every ΔE00 cell here is asserted under BOTH model
arms, so assertion counts are double the pair counts. The colour census
totals 1,312 ΔE00 arm-values over 656 pair-cells plus 20 contrast ratios =
1,332 assertions (640 S3-A2 + 448 S3-D2 + 112 S3-A3 + 112 S1-A3 arm-values;
16 + 4 ratios).
"""

from __future__ import annotations

from typing import Final

# --- Group i — record-backed hard thresholds (#242 §6; TS assertions agree) ---

# Row T1: contrast >= 3.0:1 (WCAG 2.2 non-text) vs --bw-surface-recessed;
# 16 ratios (8 tokens x 2 themes; single-arm).
# Citation: #242 §6 S3-A1 + the threshold sentence; series-colors.test.ts:440.
T1_CONTRAST: Final = 3.0

# Row T2: dE00 >= 10.0 per pair per condition; 320 pairs / 640 arm-values
# (8 tokens x 5 severity hues x 4 conditions x 2 themes).
# Citation: #242 §6 S3-A2 + the threshold sentence; series-colors.test.ts:453-454.
T2_SEVERITY: Final = 10.0

# Row T3: dE00 >= 8.0, ADJACENT slots; 56 pairs / 112 arm-values
# (7 adjacent pairs x 4 conditions x 2 themes).
# Citation: #242 §6 S3-A3 + the threshold sentence; series-colors.test.ts:600-601.
T3_ADJACENT: Final = 8.0

# Row CVD (model identity, carried by the instrument's structure, not a
# scalar): Machado 2009 sev-1.0 primary; Viénot 1999 prot/deut + Brettel 1997
# trit secondary; both arms asserted every pair; disagreement = inconclusive,
# escalate, never pass. Citation: #242 §6 threshold sentence; TS :63-71,380-430.
#
# Row DIST (metric identity): CIEDE2000 on CIELAB (D65). Citation: #242 §6
# threshold sentence; TS :56-152. Carried by colour_instrument.ciede2000.

# Row COND: the four viewing conditions. Citation: #242 §6 threshold
# sentence; TS :216.
CONDITIONS: Final[tuple[str, ...]] = ("normal", "deuteranopia", "protanopia", "tritanopia")

# --- Group ii — TS-embedded, ABSENT from #242 §6 (each FLAGGED, never
#     silently reconciled; frozen records are never retrofitted) ---

# Row T2-ENG: >= 11.0 (= threshold + 1.0) engineering floor, per-theme
# dual-arm min; 2 (one per theme). Citation: TS :477; #243 §11a ("the search
# screens (T1 >= 3.3, T2 >= 11.0) are STANDING pre-commit doctrine").
# FLAG: absent from #242 §6's threshold sentence — carried, flagged.
T2_ENG_FLOOR: Final = 11.0

# Row CENSUS-HARD: ALL 28 same-dash pairs dE00 >= 8.0 (the waveform
# monochrome arm); 224 pairs / 448 arm-values (C(8,2) x 4 conditions x
# 2 themes). Citation: TS :482-507, label "S3-D2".
# FLAG: NO row of that id exists in #242 §6 (which enumerates S3-A1..A7);
# provenance is the slice-3 review fold (PR #263 owner row) — carried,
# flagged; this ledger row is its durable citation home after G1e.
CENSUS_HARD: Final = 8.0

# Row CENSUS-ENG-DARK: dark census engineering floor >= 9.0; 1.
# Citation: TS :506. FLAG: TS-only — carried, flagged.
CENSUS_DARK_ENG_FLOOR: Final = 9.0

# Row CENSUS-LIGHT: light census hard floor 8.0 ONLY; the measured min 8.19
# is BELOW the +1.0 engineering floor. Citation: TS comment :486-489; PR #263
# owner row (accept-recommended). FLAG: the dark/light asymmetry is
# DELIBERATE — porting a symmetric >= 9.0 would red at 8.19 and invite
# forbidden threshold relaxation. There is deliberately NO light
# engineering-floor constant here (pinned by test_threshold_verbatim).

# Row LIM-T1: contrast >= 3.0:1 vs BOTH --bw-surface AND
# --bw-surface-recessed; 4 ratios (1 token x 2 surfaces x 2 themes).
# Citation: #243 §6 S1-A3 row (record-backed); TS :544-545 agrees.
LIM_T1_CONTRAST: Final = 3.0

# Row LIM-T2: dE00 >= 10.0 vs the comparator set; 7 comparators = 56 pairs /
# 112 arm-values (7 x 4 conditions x 2 themes). Citation: #243 §6 S1-A3 row +
# TS :551-552. FLAG: THREE counts disagree — the record says "6 severity
# keys / 48 values", the TS it()-name says "24 pairs", and the TS CODE loops
# severityAll = 5 hues + --bw-text-muted + --bw-border = 7 comparators
# (:525-539). The border comparator was fold-added ("measured safe, pinned
# anyway") without updating either count. The port carries the CODE's
# 7-comparator superset and asserts the set exactly (verbatim arm (b)); the
# stale counts are documented here and the frozen record is never retrofitted.
LIM_T2_SEVERITY: Final = 10.0

# Row LIM-T2-ENG: >= 11.0; 2. Citation: TS :559. FLAG: TS-only, consistent
# with #243 §11a doctrine — carried, flagged.
LIM_T2_ENG_FLOOR: Final = 11.0

# Row (search screens): T1 >= 3.3, T2 >= 11.0 — search-time doctrine for
# FUTURE slots, asserted NOWHERE. Citation: #243 §11a. Do NOT port 3.3 as an
# assertion; the TS does not. Documented here so the row is not lost;
# deliberately no constant.

#: The exact 7-comparator token set (rows LIM-T2 + the #243 fold): the
#: five severity hues, the neutral severity's actual rendering, and the
#: border. The verbatim arm (b) regenerates this set from the TS source and
#: refuses any silent drop (e.g. the fold-added border comparator).
COMPARATOR_TOKENS: Final[tuple[str, ...]] = (
    "--bw-advisory",
    "--bw-warning",
    "--bw-critical",
    "--bw-trip",
    "--bw-success",
    "--bw-text-muted",
    "--bw-border",
)

#: The 22-row ledger census (acceptance A: groups i-iii exactly). Group ii's
#: eight rows include the documented search-screens non-port; group iii's
#: pins live in test_series_colour_proofs.py (I1..I8); group iv's lane
#: constants (L1..L6) live in test_lane_reduction.py — outside this census's
#: jurisdiction per the record's §7 row A.
LEDGER_ROWS: Final[tuple[tuple[str, str], ...]] = (
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
