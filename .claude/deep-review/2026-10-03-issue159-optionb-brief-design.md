# Option B, native async host — the owner decision brief (issue #159, row 1)

**Date:** 2026-10-03 · **Issue:** [#159](https://github.com/madeinoz67/benchweave/issues/159) (deferral row 1 of the
#43 design of record). **Base:** `origin/main` tip `c183db4`.
**Authority chain:** this brief DISTILLS two merged records and adds only what changed in the tree
since they landed — it re-derives nothing. The frozen authority is
`.claude/deep-review/2026-09-23-issue159-optionb-native-async-host-design.md` (the activation review;
commits `b28b212` + sequencing refresh `5d7bce9`, 2026-09-23 — verdict **DON'T-BUILD, now**, with the
pre-committed FIRE/KILL/UNDERPOWERED/INCONCLUSIVE rule in its §6) and
`.claude/deep-review/2026-09-26-issue172-continuity-instrument-design.md` (the decision instrument;
merged as PR #236 `a6d8c54`, 2026-09-27 — the rule is now executable). Where this brief and a frozen
record disagree, the frozen record wins and the disagreement is a defect in this brief.
**Corpus:** no standards bytes move; no version strings; no SDK touch; no `src/` or `tests/` change of
any kind. `make check-sdk-standards` green trivially.
**Triage:** public — same content class as the two frozen records (synthetic-rig numbers and named
records only; no real bench, person, client, serial, or commercial term).
**Verdict: OWNER_FORK.** The row is assigned to the owner and awaiting his call; §3 is the fork table
and §4 the recommendation. This brief is the decision instrument, not a build plan.

## 0. The decision in one paragraph

The serial model's measured costs are real, priced, and — three of the four headline quantities —
immovable by ANY host model (A03 one-active-run; spec §8 per-instance serialization; SQLite
busy-retry). The one family a host moves (cross-instance freshness, telemetry continuity, and
protective latency to NON-capturing devices during another device's long dispatch) is now
instrumented, and the one simulated data point says the mechanism works (freshness gap 221 ms → 18 ms
with the blackout intact). But the decision rule is deliberately un-runnable until a bench
commissions its four bounds (`G1`/`G2`/`P`/`TB`, from qualification evidence — A02); without them
every trial reads UNDERPOWERED and a build ships on taste. The tree also moved under the review since
it merged: the exposure class is now FULLY live (capture steps and slow read/write steps are both
corpus-expressible and run-path-active), and the instrument's D2 re-measurement trigger has FIRED
(execution corpus promoted 0.1.0 → 0.2.0 on 2026-09-25) and is not discharged. The owner's call is
therefore: hold, build, close, or commission — §3.

## 1. The measured ledger — serial vs async, every number with its denominator

All serial-side numbers are from the committed synthetic rigs (`test_capture_sequential_model.py`,
`test_cross_instance_continuity.py`) or the named records — never a real bench. The async side has
ONE measured (simulated) data point; everything else about the host is prediction. Provenance codes:
[R1] #159 issue body + record §0 (re-run 2026-09-23); [R2] #161 slice-2 table via #159 record §0;
[R3] #167 record / M-B comment on #159 (2026-09-23); [R4] M-B′ comment on #159 (2026-09-25, row-B
train `3b1702f`); [R5] PR #236 body (instrument acceptance, re-measured post-fix).

| Axis | Serial model (measured) | Host prediction (evidence class) | Lever? |
|---|---|---|---|
| Monitor tick gap during a long dispatch | 50.9–51.0 ms on a 10.0 ms default poll floor (5.1×; 1.02× at a declared `poll_ms: 50` — ratios illustrative, absolute ms is the axis) [R1] | non-capturing instances keep ticking under a skip-busy-instance semantic; the capturing instance's gap stays §8-bound | **partial** — needs the skip-busy tick semantic + the aged-reading representation (a `SignalValue`/evaluator change, not a scheduling swap) |
| Queued-run delay | 56.1 ms (re-run 57.7 ms) behind a 50 ms capture — `RunWorker` FIFO, `interfaces/worker.py:43` | unchanged | **no** (A03: one active run per bench, every host model) |
| Second-dispatch lock-block | 50.6 ms (re-run 50.2 ms) — same-instance lock, `host/otdp_bridge.py` per-instance Runner/lock discipline | unchanged on the same instance | **no** (spec §8) |
| Store-contention stretch | 10.73 s class at 2× `busy_timeout` (5 s default) [R1]; M-B: median 5.199 s over 5 trials (spread 1.4% of the 10.73 s anchor) [R3]; M-B′: 3574–3612 ms under the commissioned 2000 ms clamp, 5 trials × 2 independent runs; control 5323–5399 ms [R4] | unchanged or WORSE (two-connection seam) until store ownership is decided — a census gate is named for the build | **no** (clamp shipped; contention is single-writer physics) |
| X2 — non-capturing signal freshness at dispatch end (buffered class) | 219 ms long-arm vs 42 ms matched control (dispatch ≈ 200 ms; unbuffered class collapses to 1.0 ms) [R5] | **18 ms — SIMULATED multiplexer on the rig, one axis only**; the simulation's own before-value read 221 ms — a different trial of the same rig class as the 219 ms acceptance arm [R5] | **yes** (the one measured collapse) |
| X3 — events emitted vs landed, non-capturing subscription | 202 ms long-arm vs 32 ms control [R5] | predicted to collapse; **not simulated** | yes (predicted) |
| X4 — protective-action latency to a non-capturing device | 209 ms long-arm vs 70 ms control [R5] | predicted to collapse; **not simulated** | yes (predicted) |
| Saturated polling (different regime, #161) | tick-gap max 26.0 ms worst-of-8, p95 ≈ 12.5 ms (same 8 observations), delivery median 152.5 events/s [R2] | n/a | — |

**What no host moves, ever, under the issue's own definition:** the capturing device's own signal
freshness and protective latency to it (§8), queued-run delay (A03), and the store contention axis.
The A04 gain is real but scoped: non-capturing devices stop waiting out a foreign capture; the
capturing device's residual is priced and stays.

**Missing denominators (the decision blocker):** `G1` (monitoring gap), `G2` (non-capturing
freshness), `P` (protective response), `TB` (telemetry continuity) — none commissioned on any bench.
Under the frozen §6 rule every axis without its bound reads UNDERPOWERED; a missing bound never
defaults. This is A02 territory and cannot be closed by code.

## 2. What changed in the tree since the activation review merged (verified 2026-10-03)

The review's verdict had three grounds. Ground 1's instrumentation half and ground 3's facts have
both moved; ground 2 (the mispriced buy-ledger) has not.

1. **The instrument landed** (PR #236, `a6d8c54`, 2026-09-27). X1–X4 with the mandatory non-capture
   arm, the §8-bound/movable separation as a machine check
   (`test_eight_separation_bound_share_vs_movable_share`), and the §6 classifier — verbatim, with
   per-clause citations — are on main. Numerators are producible today. (Ground 1's other half — the
   denominators — is still empty.)
2. **Run-path callers exist** (#167 Decision 1, merge `1211ab3`, 2026-09-24: run-path bridge
   construction; `tests/integration/test_run_activation.py` on main). The review's "no run-path
   caller" enumeration is stale as of that merge.
3. **Capture is ACTIVE-corpus-expressible.** Corpus-manifest `identity.execution` went 0.1.0 → 0.2.0
   at `54a59fa` (2026-09-25 07:08 +0800; SDK pointer `0de20c4`; test reconciliation `82fed0f`); the
   live `standards/execution/0.2.0/procedure.schema.json` closes `step` at NINE kinds including
   `capture`. The review's "capture verbs inexpressible" fact is stale as of that promotion. The
   exposure class (long dispatches of any verb) is therefore fully live in the tree today.
4. **The clamp and M-B′ landed** (`3b1702f`, 2026-09-25): the contention axis is measured under a
   commissioned clamp and the serial model held — arm 3's underlying quantity is priced, not open.
5. **Consequence — the instrument's D2 trigger has FIRED and is not discharged.** D2's own trigger
   text names the observable: "the capture family's promotion to the ACTIVE execution corpus
   (observable: corpus-manifest active execution version bump)". That bump is item 3. D2 (composed-path
   re-measurement — both arms through the real run path/worker) is due now; no record, tracker
   comment, or test names it as run (checked 2026-10-03).

*Footnote for future readers:* the #172 record §1 sentence "the ACTIVE execution corpus
(`execution/0.2.0`) still closes `step` at eight kinds" predates the promotion and reads stale
against main's manifest history (pre-promotion the ACTIVE corpus was 0.1.0; the 0.2.0 directory is
the promoted dev head). Frozen records are not retrofitted; the manifest is the authority.

## 3. THE FORK — the owner's options

| Option | What it is | Measured cost / benefit | Risk | What falsifies it |
|---|---|---|---|---|
| **A. HOLD** (keep the parked posture; fund only D2) | Row 1 stays the record's deferral row; the live end stays D5. Discharge the fired D2 as rig-side work (extend the landed instrument to the composed path). | Cost: one tests-only slice (the #172 rig is the size precedent — one integration module, single PR). Benefit: D5's numerators become composed-path numbers before any bench commissions bounds; zero invariant exposure. | The exposure class is fully live NOW: during any long dispatch the monitor is blacked out engine-wide (disclosed serial cost; interim bound = step `timeout_ms` under the capture-deadline arithmetic). HOLD accepts this until D5. | D5 reading FIRE on a commissioned bench. |
| **B. BUILD NOW** (owner override of the frozen rule) | Start the host train: (1) wait-primitive change + the CTL-8 bit-identity gate; (2) host loop + per-instance queues + the store-ownership census; (3) skip-busy tick semantic + the aged-reading representation (D1 — changes trip semantics for aged readings on every run); (4) the RED multiplexing control + re-measurement. | Benefit: the one measured collapse (X2 221→18 ms) plus predicted X3/X4 collapses. Cost: four slices, every one Tier-3 (concurrency keywords by construction), across `control/`, `host/`, clocking, and the fault suite's determinism gate. | **No acceptance rule can exist** until Option D supplies bounds — the frozen rule reads UNDERPOWERED on every trial, so the build ships unmeasurable against its own purpose (the exact failure the pre-commitment discipline exists to prevent). Three of four headline disclosure numbers cannot improve. If D5 later reads KILL, the train was wasted. | D5 reading KILL on a commissioned bench. |
| **C. CLOSE** (owner KILL-by-call, no rule evidence) | Close row 1 on the owner's call alone. | Cost: zero bytes. | Converts an evidence-held negative into a patience negative the month the row became decidable: the executable classifier, the simulated-mechanism result, and the fired D2 obligation would all be discarded by fiat. The frozen rule reserves closure for its KILL arm (≥2 device classes × ≥5 dispatches incl. one un-splittable class, all fitting after tightening/splitting, on commissioned bounds). | A later commissioned run reading FIRE after the row was closed. |
| **D. COMMISSION** (supply the denominators) | The owner supplies, from a real bench's qualification evidence: `G1`, `G2`, `P`, `TB`, the device-class labels, and the `T_acq_min` facts (A02/A09 — bench-side documents through the normal admission path, not repo code). Then D5 runs: the landed classifier over the rig's numerators vs the commissioned bounds — FIRE / KILL / UNDERPOWERED / INCONCLUSIVE, mechanically. | Cost: owner/bench time, no repo bytes. Benefit: the ONLY action that collapses the decision — every other option defers to this one eventually. | Commissioning a bench is itself a qualification exercise; doing it merely to decide row 1 inverts the priority (the bench commissions because it will run procedures, and then row 1 decides itself as a side effect). | Nothing — this is the prerequisite, not a bet. |

**Riders the same call can dispose of (their triggers name "the owner calling the row"):**

- **D7 (retry-class widening to TIMEOUT-flavor poll poison)** and **D8 (fractional-age truncation
  pin)**, parked on the #172 record §4. Both carry "the owner calling the row (fold it)" as their
  first trigger arm. Recommendation: **KEEP both parked** — D7's residual was demonstrated live (a
  starved host can flake a drain assert into a retry) and its second trigger arm (first
  commissioned-bench run exhibiting it) is the operative one; D8 is a cheap pin whose second arm is
  first evidence the retry classification hinges on fractional ages. Folding either now accepts the
  residual without the fix.
- **D1-early (the aged-reading representation as a standalone serial-model fix)?** The one piece of
  the host package with standalone value: today an in-bound but aged reading evaluates as a clean
  current answer for numeric/boolean conditions (pinned by the instrument's check 2 as today's
  truth). Recommendation: **do not pull it forward** — it changes what a condition trip means for
  every existing run, its fail-safe direction interacts with buffered-device classes, and the frozen
  records scope it inside the reopen. It earns its own design pass when a bench with real bounds
  exists, not ahead of the decision.

## 4. Recommendation

**A, with D named as the owner-side action on the bench's own timeline.** Concretely: HOLD row 1;
fund the fired D2 now (rig-side, one slice, discharges a live deferral-contract obligation and makes
D5's future numerators composed-path numbers); commission the four bounds when a real bench is
qualified (D — nothing in-tree blocks it, and D5 then decides the row mechanically). Do not build
(there is no acceptance rule to build against), do not close (the honest negative is one commissioned
run away, or it is not honest), keep D7/D8 parked.

## 5. Pre-committed acceptance rule (for this brief as the decision instrument)

Written before any owner reads it. The metric is decision-sufficiency, and it is checkable:

- **SHIP (the brief is fit as the instrument) iff all of:**
  1. Every numeric row in §1 carries value + denominator + provenance code, and a full cross-check
     against the cited record/PR body finds **zero mismatches** (sample = all ~20 figures, one pass).
  2. Every option in §3 and both riders carry cost, risk, and a falsifier.
  3. Both post-review deltas (§2 items 3 and 5) state their observables (merge SHAs; the manifest
     field and its before/after values) so the owner can verify them without this brief.
- **KILL (the brief is not the instrument; the owner reads the frozen records instead) if:** any
  cross-check mismatches; or the owner's call requires a fact not in §1/§3 (record the missing fact
  as this brief's defect — it is a real result about what the decision needed).
- **Underpowered reading:** none applies — this rule measures document fitness, not an effect size;
  the sample is the document's own figure set.

Self-check result (run before commit): cross-check pass over all figures — 0 mismatches; options and
riders complete; both deltas carry observables. SHIP.

## 6. Invariant, drift, and tier impacts

- **Invariants:** none changed (docs-only). CTL-8, STO-1/STO-3, REG-2/§8, and A02/A04/A06/A09 are
  DISCUSSED (§1, §3), not amended — the frozen records remain their working home.
- **Obligations (`docs/internal/drift-and-obligations.md`):** not triggered — no MCP/REST/CLI
  surface, no operator or device-developer guide, no vendored byte, no fixture lattice, no SDK
  pointer. CI cost: zero (no code; the diff is one markdown file).
- **Deferral rows (the #99 contract — every row carried, none new except the D2 status):**

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| 1 | The native async host build itself (the frozen record §2 mechanism) | #159 record §2 + this brief | The frozen §6 FIRE arm; or the three original arms restated in the record's §3 row 1 |
| 2 | D2 — composed-path re-measurement, both arms through the real run path | This brief + the row-1 trail (nearest carrier: the next execution-train slice or a dedicated rig slice under Option A) | **FIRED 2026-09-25** at `54a59fa` (observable: corpus-manifest `identity.execution` 0.1.0 → 0.2.0) — due now, not parked |
| 3 | D5 — the decision evaluation (`classify` vs commissioned `G1`/`G2`/`P`/`TB`) | #159 record §6 + the #172 record §4 | First commissioned bench supplying the bounds (Option D) |
| 4 | D7 / D8 (retry-class widening; fractional-age pin) | #172 record §4 | The owner calling the row (this brief's fork), or their second arms as written there |
| 5 | D1 early-pull (aged-reading representation ahead of the reopen) | This brief §3 (rider) — refused by recommendation, not built | The owner overruling §4, or the reopen itself |

- **Tier call (#254):** docs-only diff (one new `*.md` under `.claude/deep-review/`, nothing else).
  Step-1 keyword scan over the expected diff text, all eight tokens, both case readings
  (case-insensitive = the conservative one):
  - **Substantive text (every line except the enumeration in this scan statement itself):**
    `threading` 0 · `asyncio` 0 · `subprocess` 0 · `sha256` 0 · `hashlib` 0 · `migrate` 0 ·
    `recovery` 0 · `protection` 0 — case-insensitive and case-sensitive alike, 0/8.
  - **Whole file, as the rubric words it ("the whole expected diff"):** each token 1× — the
    enumeration in this very statement, which #254 requires ("keywords and counts, not a bare 'was
    run'"). The rubric's self-fire clause ("editing the keyword list or this Step-1 text itself …
    intended") governs diffs that EDIT the rubric, not records that state the scan; on that reading
    the enumeration is the measurement instrument, not carried content — a strict-literal reading
    that counted it would make every #254-compliant record Tier 3 and the docs-only Tier 1 rule a
    dead letter. Both readings are stated so the review's independent re-derivation is never
    surprised: on the strict reading the diff is Tier 3 by first-match-wins, and the only text that
    bought the lane is this disclosure.
  - Near-miss forms present and disclosed: `protective` (7×, the project's standard adjectival
    form — "protective-action latency", "protective transition"); `async` (6×); the per-instance
    `Runner` (1×). None contains a listed token.
  **Tier 1** — docs-only rule, zero substantive keyword hits. The review re-derives independently;
  a re-derivation that lands Tier 3 on the strict reading is a disclosed disagreement, not a
  miss — but a substantive hit this scan missed is a record defect per the rubric.
- **Standards touch:** false — no `standards/` byte, no version string.

## 7. Top risks of this brief, each with its falsifier

| Risk | Falsifier |
|---|---|
| The ledger's rig-scale numbers mislead at bench scale: real acquisition minimums may be seconds-class, making the serial blackout far larger (or irrelevant) than 50–220 ms fixtures suggest | Option D — the commissioned run; that is exactly why D is the recommendation's other half |
| The 18 ms simulated collapse is quoted as if it were a host guarantee | It is labelled one-axis/ simulated in §1 and predicted-only for X3/X4; a review finding any stronger claim in this brief is a defect |
| Ground-3 staleness (§2 items 2–3) is read as "the review was wrong" rather than "the review's now-grounds expired on schedule" | The review itself parked behind #167 with exactly this horizon ("a *now* ground, not a claim that nothing is live"); the frozen record's §1.3 wording is cited |
| The owner folds D7/D8 as housekeeping and the starvation residual bites on the first commissioned run | D7's own second trigger arm; the residual is disclosed in the rig's drain docstring and the #172 record §4 |
| A future reader takes #172 §1's stale eight-kinds sentence as present tense and re-derives a wrong exposure horizon | §2's footnote names it and points at the manifest as authority |
