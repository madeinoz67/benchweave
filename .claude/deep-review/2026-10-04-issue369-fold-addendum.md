# Issue #369 fold addendum — refute lane 1 (2 MEDIUM + 1 LOW), 2026-10-04

The design record (`2026-10-03-issue369-reading-tiles-design.md`) stays frozen;
this dated addendum records the refute lane's findings and their dispositions
on the branch. NITs went to the owner, not this lane.

## F1 MEDIUM — cross-device misattribution: DISCLOSED, NOT GUARDED (path b)

The repro: a sibling commissioned declaring only `current`, one run binding
both devices, the sibling's plugin streaming parameter `voltage` (its
subscription id) — the victim device's tile renders the sibling's value. Every
verification passes because attribution is parameter-name match + run-binds-
device + census owners==1, and nothing ties the reading to the streaming
device.

**Path taken: no stored resolution exists, so the guard is not buildable in
this slice.** The evidence, read at `origin/main 7342bb7`:

- `OTDPBridge._subscribe_gate` (`host/otdp_bridge.py:808-901`) validates
  subscription parameters against the corpus pattern `^[a-z][a-z0-9_]*$` only —
  never against the descriptor's declared `parameters` — so a plugin may
  stream any pattern-valid name, declared or not.
- `build_run` (`interfaces/app.py:696-902`) constructs one `StreamController`
  per bound adapter device but gives EVERY controller the same
  `context_key = f"run:{run_id}"` — landed evidence from all devices shares
  one context key.
- The evidence reference carries `subscription_id` (a host-minted uuid4
  opaque) and no device identity (`content/stream_services.py::land_events`);
  the subscription registry is an in-memory dict, persisted nowhere; the
  device→controller mapping lives only on the in-memory `RunStreamHost`.

**Disposition:** the census's does-not-catch clause in `ui_read.device_page`
names the live-undeclared-stream case; the join's docstring carries the same
clause; the A7 discriminator arm is reframed to pin TODAY's parameter-name-only
attribution as a disclosed behavior (not a correctness proof). A RED arm
shaped like the repro asserting the guarded outcome would RED forever in this
slice — the arm pins the actual behavior instead, so a future guard landing
FLIPS it visibly.

**Carrier (reopen trigger):** an interface/host slice that persists the
subscription→device resolution at landing — the evidence reference (or the
landing lane's context keying) gaining a device identity, or the run host
recording its `stream_host.register` map durably. That is an interface
capability change in D1's class (filed by the owner, not this lane); when it
lands, the attribution guard is "a reading renders only when its subscription
resolves to THIS device" and the A7 discriminator arm flips.

## F2 MEDIUM — the scan budget did not bound the work: FIXED

Both halves, RED-first (`test_f2_artifact_opens_are_bounded_across_runs`,
`test_f2_walk_stops_when_budget_fills` — counting wrappers over
`ContentStore.artifact_chunk`, `ContentStore.evidence_rows_by_context` and
`Store.get_run`, asserted across MULTIPLE runs; A10's single-run fixture is
exactly why this escaped the design's own arms):

- (i) `scan_rows` now bounds TOTAL artifact opens (every attempted read,
  verified or not — pre-fold only successful decodes counted, so tampered
  rows were free: measured 10 opens at scan_rows=2, five runs × four
  tampered rows, the per-run SQL LIMIT clamping rows but nothing bounding
  the walk).
- (ii) the run walk breaks the moment the budget fills — pre-fold
  `evidence_rows_by_context` AND `Store.get_run` fired for every bench run
  after the budget filled (measured 4 queries + 4 get_run at scan_rows=2
  across four runs).

## F3 LOW — a corrupt reference aborted the join: FIXED

`evidence_rows_by_context` parsed `content_ref_json` inside the row
comprehension; one corrupt column raised `ValueError` through the whole read,
aborting the join's data for every parameter (the page survived on the
conservative floor, but the module docstring's "one bad row never aborts the
join" was false at the row-reader level). The reader is now per-row tolerant:
a corrupt reference is warned and omitted, exactly its own row. RED arm:
`test_f3_corrupt_reference_row_is_skipped_per_row` (corrupt newest row via
direct SQL → the older valid row still populates; pre-fold the join aborted
to all-`Unavailable`).

## LOW-2 (lane 2) — the "newest" claim overstated: CORRECTED (wording)

`latest_retained_readings`' docstring opened "The newest digest-verified
reading per parameter this device's tiles may render" — false under budget
starvation (lane 2's repro): with scan_rows=2, two older-but-valid
observations in a NEWER run consume the budget and starve the actual newest
observation in an older run; the tile renders the older value and no
truncation mark exists. The walk's newest-RUN-first order guarantees nothing
about `observed_at` reachability. The docstring is reworded in the same
commit as this row to what holds — newest AMONG THE ROWS REACHED within the
scan budget. No mechanism change: the budget is the bound, not completeness,
and A10 already pins the disclosed-absence half.

## LOW-5 (lane 2) — the record's §4 step-7 census claim: CORRECTED here

The design record says the ownership count comes from "ONE seam call,
`device_list`, whose CON-10 projections carry parameter names". The
implementation's census is `device_list` plus one `document_get` per bench
device, because the wire device projection is contract-frozen to five fields
(`device_id`, `generation`, `profiles`, the descriptor ref, `identity_state` —
`operations.py::_device_projection`) and carries NO parameter names; the
parameter-name list exists only in each device's admitted descriptor
document, which the seam serves by digest. This deviation was disclosed in
the implementation commit (87fd80e) but the addendum — the designated
correction surface — owed this row. All census calls stay seam-mediated on
the session identity; the semantics are the record's own (a parameter
renders only when exactly one bench device declares it).
