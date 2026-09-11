---
task: "Ship WP05 procedure admission execution protection"
slug: 20260911-085349_wp05-procedures
project: BenchWeave
phase: complete
progress: 22/22
started: 2026-09-11T00:53:49Z
updated: 2026-09-11T08:03:04Z
principal_stated_goal: "we need to work on next item"
principal_stated_goal_source: prompt
principal_stated_goal_signal: 2
principal_stated_goal_locked: 2026-09-11T00:53:49Z
context_sufficient: true
interview_invoked: false
iteration: 2
resumed_at: 2026-09-11T08:03:14.031Z
resumed_from_phase: complete
---

# BenchWeave — Ideal State Artifact

## Problem

BenchWeave has its foundations — vendored contracts with byte-verified manifest
(WP01), a live MCP/identity spike (WP02), durable run/lease/request/event state
(WP03), and a published host ABI with two faultable simulator plugins (WP04;
gate G1 closed) — but no control core. Nothing can admit a procedure, bind it to
a bench, execute its steps, enforce a safety policy, or produce a truthful run
record. The gateway cannot yet run a test, which is the product's entire reason
to exist.

## Vision

The first full procedure runs end-to-end on the simulated bench, and the
evidence tells the truth in both directions: a passing run is provably passed
(completed body, verified safe state, immutable evidence chain), and a failing
or tripping run is provably what it claims — no outcome is dressed up, no
uncertainty is erased, no protective deadline is quietly reset. The principal
reads a run record and trusts it the way he trusts a measurement instrument:
not because it agrees with him, but because it cannot lie by construction.

## Out of Scope

- REST/MCP/administration interfaces and event-recovery parity (WP07).
- Curated registry, package reuse, signing/revocation (WP06).
- Operator CLI, reports, native service packaging (WP08).
- Real hardware, DPS-150/ESP32 plugins, energised fixtures, commissioning of
  physical protection (WP10–WP12; simulation only here).
- Unattended-mode qualification and disconnect drills (WP12).
- Language extensions beyond execution 1.0.0: array analytics, free-form
  expressions, streaming loops, interactive human steps, persistent energised
  terminal conditions.
- User-authored cleanup/finally blocks — the policy safe transition is the only
  cleanup path.

## Constraints

- The vendored contracts (`contracts/execution-v1.0.0/`, byte-pinned by
  `contracts/manifest.json`) are the authority; schemas set structure and
  `docs/execution-v1.0.0/execution-contract.md` semantic rules are mandatory.
  JSON validity grants no authority.
- No arbitrary code in procedures; no raw-device bypass; no hidden plugin I/O;
  no automatic retry of uncertain physical actions; no automatic resume after
  gateway restart.
- Original-byte document handling via `benchweave.content.json_document`;
  remote `$ref` resolution is structurally impossible (local resources only).
- State through the WP03 store contract: caller-supplied timestamps, no device
  I/O inside DB transactions, request acceptance before dispatch.
- Device work only through the WP04 host ABI (`DevicePlugin.dispatch` with
  monotonic deadlines); dispatch-state-honest errors preserved.
- Python 3.13 / uv; ruff + mypy strict clean; TypeScript-family repo rules do
  not apply. One RED→GREEN slice per commit; `set -o pipefail` gates pass
  before every commit. Gortex-first repo access (reads and writes).
- Planning pack `docs/implementation-planning/00–04` remains the controlling
  spec; this ISA holds the verifiable bar, not a restatement of the plan.

## Goal

"we need to work on next item" — resolved per the delivery plan to **WP05:
procedure admission/execution/protection**. Done means: `src/benchweave/control/`
admits, binds, executes and protects bounded sequential procedures over the
WP03 store and WP04 host ABI, verified by `tests/integration/test_procedures.py`
and `tests/faults/test_protection.py` against the delivery plan's bar — eight
step kinds, lexical scope, identity/resource closure, own lease, total
qualification budget, fixed protection deadline, truthful terminal status —
with ruff and mypy strict clean and every slice RED before GREEN.

## Features

### F0 · Cross-cutting: executable fixtures and simulator class actions
Why: the contract examples are structural; the verification bar needs genuinely
executable documents and a simulator that actually speaks the invoke path the
procedure language depends on.

- [x] ISC-1: sim_psu implements the three OTDP dc_psu class actions
  (`configure`, `output`, `measure`) as INVOKE verbs with typed results;
  `measure` returns an admitted `scalar_set` (voltage/current/power in V/A/W,
  one finite value each, explicit uncertainty) honouring the configuration ID.
- [x] ISC-2: Anti: simulator invoke actions fail dispatch-state-honest like
  core verbs — unknown action, bad input and post-dispatch timeout produce
  typed errors with truthful `dispatch_state`, never silent retries.

### F1 · Document admission and budgets
Why: admission is where the contract says "no" — a document that cannot prove
its own closure and budget never creates a run.

- [x] ISC-3: `control.documents` loads procedure, safety-policy, bench,
  run-binding and commissioning documents through the exact-byte decoder and
  validates each strictly against its vendored execution 1.0.0 schema; unknown
  fields, duplicate keys and nonfinite values are rejected.
- [x] ISC-4: Semantic admission rejects duplicate step IDs (including nested
  bodies), references to future steps, sibling branches or outer-scope leakage
  of repeat/branch internals, and misplaced `$stg_issue` uses — at admission,
  before any dispatch.
- [x] ISC-5: Admission computes the worst-case static body bound (sum of
  timeouts and delays multiplied through repeat counts, taking the larger
  branch, plus commissioned scheduling overhead) and rejects procedures whose
  bound exceeds `max_body_ms`.
- [x] ISC-6: The total qualification budget holds: `max_body_ms` plus the
  protective budget fits every relevant domain's `max_energised_ms`, the
  commissioning record pins the exact bench/policy/procedure digests in use,
  and the run window fits inside commissioning validity or is rejected.

### F2 · Binding, identity and resource closure
Why: a run owns its bench exclusively or it owns nothing — partial reservations
and shared devices are how benches break.

- [x] ISC-7: Every procedure role binds to exactly one commissioned device;
  required profiles are present in the pinned descriptor; role channel aliases
  resolve to channels that device actually declares; every invoked action and
  read/write parameter is declared.
- [x] ISC-8: Admission reserves the transitive closure of resources serving the
  bound roles (including protection mechanisms and monitored signals); cycles
  and conflicting identities are rejected; failed admission releases every
  partial reservation.
- [x] ISC-9: Anti: a second run cannot start on a bench whose lease is live —
  competing starts are rejected while the controlling run holds its own lease
  from the WP03 store.

### F3 · Execution engine
Why: the eight-kind interpreter is the product; its honesty rules (occurrence
identity, three-valued predicates, no retry) are what make results evidence.

- [x] ISC-10: All eight step kinds (invoke, read, write, delay, sample, assert,
  if, repeat) execute per the contract on the sim bench; the normal path
  terminates `passed` only after the verified safe transition.
- [x] ISC-11: Occurrence identity `(run_id, step_id, loop-index-path)` is
  stable: re-entering an occurrence returns its existing result and never
  repeats physical work; repeat iterations create fresh occurrences.
- [x] ISC-12: Runtime reference resolution honours lexical scope —
  `$stg_ref` reaches only earlier siblings/enclosing earlier steps, repeat
  iterations see only their own results, and any unresolvable, missing or
  wrong-typed reference terminates the body before dispatch.
- [x] ISC-13: `$stg_issue` issues fresh scoped IDs only at the corresponding
  required input field of configuring/arming actions; a failed configuration
  invalidates its issued ID.
- [x] ISC-14: Predicates are three-valued: invalid/stale/wrong-unit/unknown-
  required-uncertainty evidence yields `execution_error` (never a false branch
  or passing assertion); a false assert yields `assertion_failed`; a false `if`
  selects `else`.
- [x] ISC-15: Samples are trustworthy by construction: exact unit equality, one
  finite inline value, freshness measured from acquisition, and conservative
  interval comparison when uncertainty is known — no implicit conversion.
- [x] ISC-16: The body deadline is monotonic and starts at acceptance; the
  scheduler may shorten a step timeout to the remaining budget and never
  extends it; expiry yields `timed_out`; a timeout after dispatch preserves the
  operation's uncertain dispatch state.
- [x] ISC-17: Anti: no state-changing operation is ever automatically retried
  — a failed or unknown operation ends the body per the contract mapping.

### F4 · Protection and truthful terminal status
Why: the run record is the trust object; everything protection does exists to
make its final claim unfakeable.

- [x] ISC-18: Every state-changing action is denied at dispatch unless a
  policy allow rule matches the actual device and exact action/parameter, with
  input/value constraints applied conjunctively.
- [x] ISC-19: Continuous conditions apply from acceptance until the safe
  condition is verified; numeric bounds contain the full error interval, the
  V×A product uses the conservative upper bound with skew accounting, and
  missing/stale/unknown signals trigger the protective response.
- [x] ISC-20: The first entry to protecting fixes its deadline; later faults
  escalate reasons without restarting or extending it; ordered safe actions run
  within the remaining budget and final verification is a conjunction held
  continuously for `stable_for_ms`.
- [x] ISC-21: Terminal status is truthful per the run-record state machine:
  `passed` requires a completed body and verified safe state; unverified safety
  forces `outcome_unknown`; trip yields `tripped`; the finalised record
  validates against `run-record.schema.json`.
- [x] ISC-22: After a simulated gateway restart, durable runs that were not
  terminal are recovered as `interrupted` with unknown physical assurance, body
  execution never resumes automatically, and retained occurrence identities
  suppress replay.

## Test Strategy

| isc | type | check | threshold | tool | anchors_to |
|---|---|---|---|---|---|
| ISC-1 | contract | invoke vectors for configure/output/measure pass against sim_psu | 3/3 actions | `uv run pytest tests/contract/test_sim_plugins.py` | PRD-04, OTDP dc_psu |
| ISC-2 | contract | invoke fault vectors return typed errors with truthful dispatch_state | 3/3 cases | `uv run pytest tests/contract/test_fault_matrix.py` | PRD-04, P-qual |
| ISC-3 | unit | five fixtures validate; mutated docs (unknown field, dup key) rejected | 5 pass / ≥2 reject | `uv run pytest tests/integration/test_procedures.py` | PRD-06, P-checks |
| ISC-4 | unit | each malformed-scope procedure variant rejected at admission | ≥5 variants | `uv run pytest tests/integration/test_procedures.py` | execution-contract §3 |
| ISC-5 | unit | computed worst-case bound equals hand-calculated value; over-budget rejected | exact ms | `uv run pytest tests/integration/test_procedures.py` | execution-contract §5 |
| ISC-6 | unit | over-energised and expired-commissioning bindings rejected; valid one accepted | 2 reject / 1 accept | `uv run pytest tests/integration/test_procedures.py` | execution-contract §5/§8 |
| ISC-7 | unit | unbound role, missing profile, undeclared action/parameter, bad channel rejected | 4/4 | `uv run pytest tests/integration/test_procedures.py` | P01 |
| ISC-8 | unit | resource cycle rejected; failed admission leaves no reservation | 2/2 | `uv run pytest tests/integration/test_procedures.py` | P05, B03 |
| ISC-9 | integration | second start on live-leased bench rejected; after release accepted | 1 reject / 1 accept | `uv run pytest tests/integration/test_procedures.py` | PRD-05 |
| ISC-10 | integration | eight-kind procedure completes passed with verified safe state | 1/1 run | `uv run pytest tests/integration/test_procedures.py` | PRD-06 |
| ISC-11 | integration | re-dispatched occurrence returns prior result; repeat iterations distinct | 2/2 | `uv run pytest tests/integration/test_procedures.py` | PRD-07 |
| ISC-12 | integration | bad-ref/stale-scope variants terminate execution_error before dispatch | ≥3 variants | `uv run pytest tests/integration/test_procedures.py` | P03 |
| ISC-13 | integration | issued ID valid only at configure field; failed configure invalidates | 2/2 | `uv run pytest tests/integration/test_procedures.py` | P03 |
| ISC-14 | integration | invalid sample → execution_error; false assert → assertion_failed; if-else both branches | 3/3 | `uv run pytest tests/integration/test_procedures.py` | P06 |
| ISC-15 | integration | wrong-unit/stale/multi-value samples rejected; uncertainty interval honoured | 4/4 | `uv run pytest tests/integration/test_procedures.py` | PRD-09 |
| ISC-16 | faults | step timeout shortened not extended; body expiry → timed_out; post-dispatch timeout uncertain | 3/3 | `uv run pytest tests/faults/test_protection.py` | PRD-08 |
| ISC-17 | faults | injected transport fault produces exactly one dispatch occurrence | 1/1 | `uv run pytest tests/faults/test_protection.py` | PRD-07/08 |
| ISC-18 | integration | unmatched action denied; constrained input rejected; matched allowed | 3/3 | `uv run pytest tests/integration/test_procedures.py` | P07, B06 |
| ISC-19 | faults | out-of-envelope reading trips; stale signal trips; product bound enforced | 3/3 | `uv run pytest tests/faults/test_protection.py` | P07, B07 |
| ISC-20 | faults | second fault during protecting escalates without extending deadline | 1/1 | `uv run pytest tests/faults/test_protection.py` | P08 |
| ISC-21 | faults | terminal records validate per schema; unverified-safe → outcome_unknown; trip → tripped | 3/3 | `uv run pytest tests/faults/test_protection.py` | P10, PRD-09 |
| ISC-22 | faults | kill-window restart recovers run as interrupted; no resume; no replay | 3/3 | `uv run pytest tests/faults/test_protection.py` | P09, PRD-08 |

## Decisions

- 2026-09-11 08:53: "next item" resolved to WP05 (not the parallel WP06) —
  the delivery plan's dependency graph names WP05 next on the core-engineer
  path (WP03/04 done), and the session handoff memory records it as planned
  next; WP06 remains parallel-eligible later.
- 2026-09-11 08:53: Project ISA created at WP05 start. WP01–WP04 outcomes and
  gate G1 closure are history in git (47d0150…d62deeb), not open claims; this
  ISA tracks the WP05 bar and, after close, the project's living state.
- 2026-09-11 08:53: sim_psu gains the three dc_psu class actions inside WP05
  — the plugins shipped with core verbs only, but the procedure language's
  invoke/sample path requires them; this is the "genuinely executable
  simulator descriptors" global constraint landing.
- 2026-09-11 08:53: device descriptors for admission are local pinned documents
  in `fixtures/execution/` checked structurally by the control layer (profiles,
  actions, parameters); full OTDP descriptor-schema admission stays OTDP-layer
  work and is not re-litigated here.
- 2026-09-11 08:53: boolean continuous conditions requiring host-input
  contracts are out of this slice (no host-input source exists yet); the
  fixture policy uses numeric and product conditions only.
- 2026-09-11 (close): Ratified — a completed body plus a post-body pre-verification continuous-condition violation records outcome=passed with the violation retained in reasons (schema-consistent: completed ⇒ {passed, outcome_unknown}, safe verified decides; the violation is not hidden and protection was entered with it). Boundary: reclassification to tripped/cancelled fires only for causes that actually blocked a dispatch.
- 2026-09-11 08:03 (close): fog killed — the single-threaded monitor tick model is the deliberate PoC posture; multi-signal scheduling policy is WP07/09 evidence scope, not unresolved design.
- 2026-09-11 08:03 (close): Cross-vendor Forge audit + strongest-model whole-branch review ran on the full branch (claim 11 second look; plan review boundary). Forge: no critical — headline guarantees attacked and confirmed clean. Fable: "With fixes"; trust core verified end-to-end, fixture lattice independently re-hashed. Findings dispositioned: adopted (final fix wave — read/write ref targets + verb discrimination, interrupted outcome emission, product factor units, freshness negative-age + device age_ms, reset token clearing, poll-cadence/interval consolidation, safe-action continue exercise); carried as follow-up (see Remaining Work); dropped per triage (M3/M6/M11/M16/M19/M20/M27/M30/M32/M33/M36/M37).
- 2026-09-11 08:03 (close): WP05 declared complete — 15 commits on local `main` ending at 11501fd (not pushed, per convention), 225 tests / ruff / mypy strict clean at HEAD, all 22 claims closed on tool evidence, both final reviews passed, final fix wave Approved (11501fd).
- D-auto-2026-09-11T08:03:14.031Z: Auto-resumed from complete to learn at 2026-09-11T08:03:14.031Z — iteration 2 (resume hook fired on the close write; restructured the tail into locked section order and re-closed)

## Learning

- conjectured: the plan's walker kernel (`frozenset(visible)`) encoded lexical scope correctly. refuted by: Task 3's implementer — under the literal kernel every required acceptance test fails (earlier siblings invisible). learned: a plan's illustrative code is a sketch, not the spec; prose contracts govern. criterion now: kernel code in briefs is verified against its own prose before dispatch (and the deviation-adjudication pattern caught it again at the §4 freshness recheck).
- conjectured: two clean endpoint samples prove a stability window. refuted by: the whole-family review chain — Task 8's first review showed endpoint sampling claims `verified` over an unobserved transient. learned: held-continuously conditions need cadence polling with reset-on-dirty, closed by a verified-vs-unknown discriminator test. criterion now: any continuity claim ships with a test that flips the outcome under the old implementation.
- conjectured: conservative error intervals only ever tighten assertions. refuted by: Task 7's fixture finding — at nominal zero, the interval dips below a zero floor and the pristine fixture's own check became honestly unsatisfiable. learned: interval semantics interact with physical floors; the fix belongs in fixture bounds, never the evaluator. criterion now: fixture assertion bounds are audited against signal-at-zero intervals.

## Verification

- ISC-1: commit ac90e04 — tests/contract/test_sim_plugins.py invoke suite (incl. vendored OTDP schema probe)
- ISC-2: commit e7321d6 — dispatch-state-pinned trip/bounds tests + sim_psu_vectors.json trip vector; task review Approved
- ISC-3: commit ae3d741 — tests/integration/test_procedures.py admission suite; review-verified: all committed digests = committed bytes; runtime dep promoted 7cc6f6e
- ISC-4/5/6: commit cb00dff — semantics.py rejection suite (hand-computed 3500ms bound asserted; isolation properties traced by reviewer); task review Approved
- ISC-7/8/9: commit 2a981d6 — binding.py closure/lease suite (expired-vs-live clock comparison, unwind-by-construction reviewer-verified); task review Approved
- ISC-18: commits 1f117d5+aa68960 — policy.py allow-rule/condition suite (escaping-edge, conjunctive, boolean both directions, schema-confirmed); task review Approved
- ISC-11/16/17: commit 4dd2031 — executor.py replay/deadline/error-mapping suite (reviewer-traced choke points); task review Approved
- ISC-12/13/14/15: commits c55683a+c4b0c98 — resolver/predicate/sample suite incl. conservative-interval headline + predicate-time freshness recheck (RED-first); task review Approved
- ISC-10/19/20/21/22: commits ca1abca+ccff8d1 (+fixture lattice) — protection/coordinator fault suite (vendored-schema record validation, exact-timestamp deadline fixity, poll-sliced stability discriminators, restart recovery); task review Approved
- Final wave: commit 11501fd — read/write ref projections, interrupted outcome, product factor units, freshness honesty (RED 9-failed → 225 passed); fix-wave review Approved; closing gates re-run by controller: 225 passed / ruff [] / mypy strict 0 issues

## Remaining Work

Carried follow-ups (whole-branch + Forge triage; full detail in the run's SDD ledger and Decisions):
- [ ] WP06 intake batch: vacuous-constraint admission warning, types-jsonschema + drop import ignores, explicit package_lock_path param, single-writer store contract docs — each one line in the next dependency/config touch
- [ ] Alignment commit: raw WRITE trip reports NOT_DISPATCHED vs invoke-path DISPATCHED (WP04 code; needs deliberate fault-matrix pin updates)
- [ ] Test-posture batch: untested admission rejection branches, then→else pin, product-at-maximum, safe-action clamp assertion, nested if-in-repeat replay, if-side interval end-to-end
- [ ] Input-validation polish: eager expires_at/now_wall parse, narrow release ValueError, ValueError on unexpected policy kinds
- [ ] Monitor evidence retention (raw signal readings behind trip reasons) — WP07 evidence surface
- [ ] Later-gateway items outside WP05: §9 request_id principal scoping, local-takeover semantics, §144 conformance scenarios (disconnect/evidence-failure/revocation)
