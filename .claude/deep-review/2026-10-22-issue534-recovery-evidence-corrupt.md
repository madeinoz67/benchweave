# Recovery evidence: corrupt retained bytes are never silently absent

Tracker: madeinoz67/benchweave#534 (single issue stream; gateway-only diff).

## Verified finding (designer, base aa8cd5ca)

`coordinator.py`'s blanket `except Exception` over the retained-bytes probe
(`_versioned_schema_path`, `documents.py::_versioned_schema_path`) collapses
three typed refusals — `version_unknown:` (genuinely absent),
`corpus_file_unpinned:` (retained bytes with no corpus row) and
`corpus_pin_mismatch:` (retained bytes that fail their digest pin) — into the
composition decision. For the two CORRUPT refusals that is the A06 laundering
shape: a durable composition terminal record is stamped over retained bytes
the corpus itself refuses to vouch for, and the corruption is silently absent
from every operator surface.

Corruption of a CARRIED dialect is already contained at terminalization
(`_record_validator_for_version` refusing inside the per-run try, fold row 7;
pinned by `test_unrowed_run_record_schema_is_contained_per_run`). The hole is
exactly the retired-echo + retained-bytes branch of
`_recovery_record_version` (the three-way disposition's third leg): a
retired-but-retained echo whose bytes are tampered, unrowed, or unverifiable
composed instead of containing.

## Mechanism (one production file, coordinator.py only)

In the retained-bytes branch, catch `AdmissionRejected`
(`documents.py::AdmissionRejected`) and split on the machine-matchable
prefix:

- `version_unknown:` → the composition decision unchanged (honest absence —
  no retained bytes, caller data);
- any other `AdmissionRejected` (including `corpus_file_unpinned:`,
  `corpus_pin_mismatch:`, and any prefix the split does not name) →
  decision-level containment with the reason quoting the refusal verbatim —
  fail-closed, so refusal-wording drift degrades to visible containment,
  never a wrong record;
- any non-refusal exception (unreadable corpus manifest, IO, JSON errors) →
  containment naming the unreadable corpus state.

The function stays TOTAL — `recover_interrupted` calls it OUTSIDE the per-run
try (both sweep legs), so raising would kill gateway startup. Prefix matching
is the documented machine-matchable vocabulary of the corpus refusal family.
No typed exception subclasses are added to `documents.py`: that is a
persisted-format surface and this slice does not touch it.

## Operator visibility (absent vs corrupt)

- absent → the durable interrupted record with the composition stamp, as
  before the fold (the honest-ref class; the integration harnesses keep
  recovering);
- corrupt → an error log naming the run, the path and both digests (the
  verbatim refusal carries all three), the run on `contained`, the
  projection closing terminal with `outcome_unknown` through the #507 loop,
  the lease released, and the bench bookable.

Repair does NOT retro-terminalize — that is #507's row-c door, disclosed,
not widened here.

## Files

- `src/benchweave/control/coordinator.py` — the split (branch, import,
  docstring);
- `tests/faults/test_recovery_sweep_faults.py` — the corruption cohort;
- `docs/internal/invariants.md` — CON-1 fold-clarification amendment;
- `docs/operator-guide.md` — the three-way sentence gains the split (drift
  obligation 4; README carries no recovery sentence, verified).

No schema, no SDK pointer, no CI workflow, no other doc.

## CON-1 amendment text (invariants.md)

> the third leg splits — version_unknown (no retained bytes) stays the
> composition record; retained-but-untrustworthy bytes (corpus_file_unpinned
> / corpus_pin_mismatch / unreadable corpus) is decision-level containment
> under recovery_execution_version_unresolved: — no record, the #507
> projection close; corrupt is never silently absent.

## Pre-committed acceptance

Pre-committed by the design brief (team-lead dispatch, 2026-10-22) before the
implementation lane ran; carried here verbatim in substance. The arms' RED and
GREEN evidence rides the implementation commit's message.

Substrate: `tests/faults/test_recovery_sweep_faults.py`, decision arms on the
retired-echo staging (copytree standards into tmp plus a dependency-policy
retirement — the existing
`test_era_echo_retired_by_a_later_policy…` shape, factored into
`_retired_era_corpus`) plus one sweep arm through
`_recover_interrupted_runs(contracts=…)`. Deterministic fixtures, N=1 each,
idempotency pinned.

- **D1** tamper the schema bytes with the corpus row intact → containment,
  reason carries `corpus_pin_mismatch` (quoted verbatim, prefix and path
  intact).
- **D2** remove the corpus row (the unrowed staging plus the retirement edit)
  → containment, reason carries `corpus_file_unpinned`.
- **D4** corrupt the corpus manifest to invalid JSON → containment naming the
  unreadable corpus state.
- **D3** delete the schema file (ABSENT control) → the composition decision
  exactly as the existing caller-data pin asserts, and it must NOT move.
- **S1** a sweep over D1's corpus at the app-level entrypoint → the run is
  NOT in `recovered`, no durable record, the unresolved log names run plus
  mismatch, projection terminal with `outcome_unknown` and no record, bench
  not busy, second sweep idempotent.
- All existing era arms stay green, especially the retained-bytes SUCCESS
  arm.

SHIP iff every arm holds post-fix. KILL if any corrupt arm still yields a
composition decision; if D3 moves (over-broad containment, the #260 lesson);
or if S1 writes a durable record (laundering — worse than the bug).
UNDERPOWERED if, with the fix reverted, any of D1/D2/D4 stays green, or S1
cannot redden under the revert — a green-under-revert arm measures nothing,
replace it, do not ship around it.

RED CONTROL: restore only the blanket `except Exception` over the probe →
D1, D2, D4 and S1 must go RED while D3 STAYS GREEN. FLUFF CONTROL the other
way: treat `version_unknown` as containment too → D3 must REDDEN.

NOT MEASURABLE on this substrate: operator repair behaviour in the field,
and a tamper that re-pins every digest (the repin authority boundary, out of
scope).

## Deferrals

| # | Deferral | Home | Reopen trigger |
|---|----------|------|----------------|
| 1 | `_is_carried_execution_dialect` returning bool \| None (three-valued judgment) | this record | a refute lane finding a wrong-record path through the call sites |
| 2 | Typed exception subclasses for the corpus refusal family | this record | a second prefix-matching consumer appearing |
| 3 | The re-judgment door after repair | #507 row c, unchanged | #507's own process |
| 4 | Durable containment surfacing beyond the log and `run_changed` | #507 row d, unchanged | #507's own process |

## Review tier

TIER 3 by the keyword rule: the diff text contains `recovery`, `sha256`,
`hashlib` (the designer's scan over the expected diff: recovery 24, sha256 2,
hashlib 2, all other tier-3 keywords 0). The actual diff's counts are
recorded in the implementation commit's message. Expect the deep refute
slate.

## Ordering disclosure

The brief required this record as the first commit, alone, before any
measurement. The tracker number (#534) arrived after the lane had already
taken a first measurement pass on the working tree, so this record's commit
postdates that pass; the acceptance above is the designer's dispatch text
carried unmodified, never derived from any run. Per the coordinator's
correction, every number shipped in the implementation commit's message and
the lane report comes from the post-commit re-run taken on the tree exactly
as it stands after this commit — the first pass's numbers are not evidence
for this increment.
