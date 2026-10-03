# Issue #316 — Endurance-class runs: gateway-owned authorization — design record

**Date:** 2026-10-03
**Verdict:** BUILD (one Tier-3 slice), with three OWNER_FORKS on the authorization model.
**Base:** `origin/main` @ `c183db4` (worktree `.wt/i316-6104`, branch `feat/issue316-endurance-authz`).

---

## 0. Summary

The issue's premise — "the authorization mechanism has zero corpus presence" — is **half
wrong, and the half that is wrong is the important half**. The corpus presence exists and
is complete: the commissioning schema carries the grant (`modes[]` with `"unattended"`,
an `"unattended"` evidence category, `approved_by/approved_at`, `expires_at`), the
procedure schema carries `mode: manual | gateway_owned`, the execution contract states
the run-time rule in so many words (execution-contract.md 0.2.0 lines 72, 131, 133, 145),
and the offline census already enforces grant-consistency over the vendored examples
(`scripts/architecture/check_execution.py::commissioning_errors`, line 454:
`if p["mode"] == "gateway_owned" and "unattended" not in c["modes"]`).

What has zero presence is **gateway enforcement**. Verified on this tree:

- `src/benchweave/` contains **zero** occurrences of `unattended` and zero reads of the
  procedure's `mode` field (gortex text search, path-scoped, 2026-10-03).
- `Operations.run_start` (`src/benchweave/interfaces/operations.py:594-728`) sets
  `runs.authority = "lease" if lease_id is not None else "gateway"` — the attended,
  lease-backed path is fully validated (resolution, bench identity, expiry, holder
  identity, single-shot consumption — D12), while the **unattended** path
  (`lease_id=None`) requires nothing. The gateway-owned mode is the unchecked default.
- `admit_documents` (`src/benchweave/control/documents.py:1768+`) checks the
  commissioning document's structural pins (bench id, policy, package_lock,
  procedure_refs) and never reads `modes`, `expires_at`, or evidence categories.
- The worker (`build_run`, `src/benchweave/interfaces/app.py:718-742`) admits documents
  and applies the implemented-dialect floor (`_check_run_floor`, issue #260) — no mode
  or qualification-window check.
- **The in-tree demo lattice is itself the live counterexample:**
  `fixtures/execution/commissioning.json` has `modes: ["supervised"]` and evidence
  categories `["envelope"]` only, while its procedure
  (`fixtures/execution/procedure-voltage-check.json`) declares `mode: "gateway_owned"`.
  The demo gateway starts gateway-owned runs on a bench whose commissioning grants
  supervised only. Nothing catches it, because the census checks the vendored
  `standards/execution/*/examples/` (which are self-consistent), not the fixture
  lattice the gateway actually admits.

So the design is not "invent an authorization mechanism"; it is **wire the corpus's
existing grant rule into the two layers where the corpus says it is checked** — the
run-start seam and the worker's authoritative admission — by extending the exact
mechanism issue #260 landed for the execution-version floor. Zero standards bytes move.

This inverts the current posture, which is backwards on its own terms: the *manual,
attended* start must prove a validated lease, while the *autonomous, hours-long* start
proves nothing. A04's "a client cannot silently promote an ordinary operation to
autonomous execution" is today enforced by no code path.

---

## 1. What the corpus already specifies (the rule being enforced)

All citations from `standards/execution/0.2.0/` unless noted; the 0.1.0 dialect carries
the identical `mode`/`modes`/evidence-category/`expires_at` vocabulary (verified by
schema comparison — the check is dialect-stable across both served versions).

- `procedure.schema.json` — `mode: "manual" | "gateway_owned"` (required);
  `max_body_ms` capped at 86 400 000 ms (24 h) in 0.2.0.
- `commissioning.schema.json` — `modes[] ⊆ {observation, supervised, unattended}`;
  `evidence[].category` enum includes `"unattended"`; `approved_by`, `approved_at`,
  `expires_at` required.
- `execution-contract.md:72` — "Manual mode requires an active client lease; lease loss
  ends the body and invokes protection. Gateway-owned mode may continue through client
  disconnect only within the approved unattended record and body deadline."
- `execution-contract.md:131` — "Admission checks expiration before each run; the full
  body plus protective budget cannot exceed the valid qualification interval without a
  separately defined policy (not provided here)."
- `execution-contract.md:133` — "Observation, supervised and unattended modes are
  distinct grants. Unattended requires a gateway-owned bounded procedure and its own
  evidence."
- `execution-contract.md:145` (bench checks B01–B10) — names "exact commissioning
  approvals/expiry/invalidation; offline/mains/unattended mode gates."
- `scripts/architecture/check_execution.py::commissioning_errors` (offline census) —
  gateway_owned procedure on a commissioning without `"unattended"` in `modes` is
  "missing unattended grant"; `"unattended"` in `modes` requires a **passing**
  (`result == "passed"`) evidence row of category `"unattended"`.

**GW-56** (PRD 12, `docs/implementation-planning/12-gateway-web-ui-prd.md:210`) reads
the grant off "the binding" — but the binding is a closed wiring document
(`run-binding.schema.json`: procedure/bench/policy/package_lock/commissioning pins +
role bindings, `additionalProperties: false`). The binding "has" the grant transitively
through its **commissioning pin** (id/version/sha256). That reading is forced, not
chosen: the binding is client-authored at request time, and a grant field there would
let the requester author its own authorization — the exact inversion A04 and REG-3's
"publication and installation never authorize control" logic exist to prevent.

---

## 2. The mechanism

One helper, two call sites, typed refusals — the #260 two-layer shape verbatim.

### 2.1 The helper

New function in `src/benchweave/control/documents.py`, beside `_check_run_floor`:

```
_check_unattended_grant(procedure, commissioning, *, now_wall, lease_present) -> None
```

Raises `DocumentAdmissionRejected` (the existing typed refusal; its message carries a
machine-matchable prefix, matching the family's convention) for, in evaluation order:

1. `unattended_grant_absent:` — `procedure["mode"] == "gateway_owned"` and
   `"unattended"` not in `commissioning["modes"]`. (Census-parity: the offline wording
   is "missing unattended grant".)
2. `unattended_evidence_failed:` — `"unattended"` in `commissioning["modes"]` and no
   evidence row with `category == "unattended"` and `result == "passed"` (covers absent
   and non-passing; the contract's "a syntactically complete record with failed
   evidence grants nothing").
3. `qualification_expired:` — `now_wall >= commissioning["expires_at"]`.
4. `qualification_window_exceeded:` — `now_wall + max_body_ms + max_protection_ms >
   commissioning["expires_at"]` (contract line 131 verbatim: full body plus protective
   budget within the valid qualification interval). Applies to **both** modes.
5. `manual_lease_required:` — `procedure["mode"] == "manual"` and not `lease_present`
   (contract line 72: manual mode requires an active client lease).

Signature discipline follows the provider-approval precedent
(`documents.py:1290`): `now_wall` is caller-supplied and the check is pure arithmetic
on declared values — A04's bounded-continuity rule, never an ambient clock read. The
helper never mutates, never re-dispatches, never reads the store.

### 2.2 The two layers

- **Seam (wire-visible early refusal, best-effort):** extend
  `Operations._assert_run_runnable` (`operations.py:1712-1785`), which
  `_assert_bench_acceptable` already calls over the resolved binding document
  (`operations.py:1903`). The binding document's content pins the procedure and
  commissioning by sha256; resolve both from the content store exactly as the bench
  and descriptor documents are resolved today (digest-addressed, no TOCTOU — same
  digests the worker will admit). The **inverted-guard doctrine carries over
  verbatim**: an unstored procedure/commissioning document is NOT decided at the seam;
  that run stays asynchronous under the worker's authority. `lease_present` is the
  seam's own `lease_id is not None` (the lease itself is validated independently by
  the D12 block; the helper only needs presence). The refusal rides the existing
  `except DocumentAdmissionRejected → policy_denied` handler — `policy_denied` is
  already in the catalog's 14-code set, so **no wire-schema bytes move**.
- **Worker (authoritative):** call the same helper in `build_run`
  (`app.py:742`, immediately beside `_check_run_floor`, after `admit_documents`
  produces `docs.procedure` / `docs.commissioning`, before any device plan or bridge is
  constructed) with `now_wall=now_iso()` and `lease_present` threaded from the run row's
  `authority` (the worker knows it from the accepted request). One rule, one
  vocabulary, two enforcement points — the #260 sentence, re-applied.

### 2.3 Ordering inside the seam (preserved, not invented)

`_assert_bench_acceptable` runs inside `run_start` after the §9 replay peek (replay
still returns an accepted run without re-checking — idempotency untouched) and its
lease consumption is LAST (`operations.py:1907+`, D12's consume-last doctrine). The
new gate sits with the other §5 pre-checks, so **every refusal leaves a presented
lease untouched** — no start is refused after having consumed the operator's lease.

### 2.4 What the gate does NOT do (stated, per claim discipline)

- It does not check the seven base evidence categories (identity/protocol/envelope/
  protection/timing/safe_transition/audit_failure) — that is commissioning-time
  completeness, the offline census's job. The run gate checks the grant it is
  exercising: the `unattended` grant and the qualification window. Residual disclosed.
- It does not detect "relevant changes" invalidating qualification before expiry
  (contract line 131's invalidation clause) — no mechanism exists; deferral D3.
- It does not add a mid-run expiry timer. The acceptance-time window check makes
  "commissioning expires mid-run" unrepresentable for a compliant start (the run's
  own bench lease, `acceptance + max_body + max_protection` — STO-4 — is inside the
  qualification interval by construction). No new timer, no judgement, arithmetic.
- It does not touch recovery: era runs terminalize as `interrupted` under CTL-9 and
  are never resumed — A04's "restarts do not automatically resume or re-arm".
- It does not change `runs.authority` recording (migration v3, `authority_changed`)
  or the terminal record (which already pins commissioning
  `{id, version, sha256}` — `coordinator.py:1268-1270` — so run evidence derives the
  grant from the pinned digest; no record change, evidence-exactness preserved).

### 2.5 The endurance body-shape doctrine (issue direction 3 — no mechanism this slice)

`max_body_ms` caps at 24 h in 0.2.0 and monitor ticks already slice waits at the poll
cadence (CTL-8), so endurance tests author as segmented bodies (`repeat` of short
capture · sample · assert) and multi-day studies compose as schedules of bodies. The
step kinds (capture/sample/assert/repeat/delay) already support this; nothing in the
gateway blocks it. This is authoring doctrine and lands as documentation with the
first real endurance procedure — deferral D2, not code.

---

## 3. Minimal first slice

**Slice 1 — the unattended-grant gate (Tier 3).** Files in the expected diff:

1. `src/benchweave/control/documents.py` — `_check_unattended_grant` (~60-90 lines)
   + export.
2. `src/benchweave/interfaces/operations.py` — seam wiring in
   `_assert_run_runnable` (~25 lines).
3. `src/benchweave/interfaces/app.py` — worker wiring beside `_check_run_floor`
   (~10 lines; `lease_present` threaded from the run row).
4. `fixtures/execution/commissioning.json` — gains `"unattended"` in `modes` and one
   passing `unattended`-category evidence entry (synthetic report id, invented name).
   The owners block is untouched. This keeps the demo lattice runnable under the gate;
   without it every demo/e2e run refuses (that refusal is the demonstrated defect).
5. `tests/control/test_unattended_grant.py` (new) — the refusal matrix + parity +
   control arms (§5). Seam arms land with the existing seam/integration files.
6. `docs/internal/invariants.md` — new **CTL-10** row (§6).
7. `docs/operator-guide.md` — the run-start refusal family row (obligation 4).
8. This design record.

**Explicit deferrals** (each: carrier + reopen trigger):

- **D1 — UI surfacing (GW-56's gateway-owned hint, grant status in the run views).**
  Carrier: PRD 12 §G3 (GW-56) and the G2/G3 UI lanes (#295/#303, PRs #371/#372 in
  flight). Reopen: the UI slice implementing GW-56 — it consumes this gate's refusal
  and the grant fact; it needed the gateway check to exist first.
- **D2 — endurance authoring doctrine** (segmented bodies, schedules-of-bodies,
  capture-window monitoring disclosure). Carrier: the execution contract's bounded-body
  clauses + the device-developer-guide's procedure-authoring sections. Reopen: the
  first endurance-class procedure author, or the landing of #307's lease-duration
  ruling (which fixes the manual-mode numbers this doctrine contrasts against).
- **D3 — mid-run qualification invalidation** ("relevant changes" before expiry).
  Carrier: this record. Reopen: a dedicated issue + design (needs a definition of
  "relevant change" — e.g. descriptor re-admission at a newer version — that no current
  mechanism provides).
- **D4 — endurance hazard accounting** (cumulative energised-time vs
  `domains[].max_energised_ms`, discharge-class stored-energy accounting vs
  `max_stored_energy_j` across a 24 h body). Carrier: this record. Reopen: the first
  burn-in/discharge-class procedure; per-action allow-rule constraints and CTL-8
  monitoring bound the per-dispatch hazards today, cumulative budgets do not exist.
- **D5 — schedules-of-bodies composition** (multi-day studies as one operator
  artifact). Carrier: this record. Reopen: owner call for multi-day study support —
  needs its own corpus concept and standards design.
- **D6 — mid-run commissioning-expiry enforcement.** Structurally unnecessary under
  the acceptance-time window check (§2.4); listed so the non-decision is on record,
  not silent. Reopen: only if a future policy wants runs curtailed at qualification
  expiry rather than refused at start.

---

## 4. Precedent (why this shape and not another)

1. **The #260 two-layer run floor** — `_check_run_floor`
   (`documents.py:1423`) called at the seam (`operations.py:1778`, inside
   `_assert_run_runnable`) and at the worker (`app.py:742`), one helper, one refusal
   vocabulary, inverted-guard at the seam / authoritative at the worker. This design is
   that mechanism with a different rule inside the helper. No new architecture.
2. **D12 lease takeover** (`operations.py:1787-1920`) — validated-then-consumed, and
   consume-LAST so every refusal leaves the lease untouched. The new gate inherits the
   ordering for free by living in the same §5 block.
3. **The provider-approval expiry check** (`documents.py:1290`) — caller-supplied
   `now_wall`, refusal when absent, pure arithmetic. The expiry clauses' signature.
4. **The offline census** (`check_execution.py::commissioning_errors`) — the rule and
   its vocabulary ("missing unattended grant", passing-evidence requirement) already
   exist; the gateway mirrors rather than invents.
5. **`runs.authority` + `authority_changed`** (migration v3) — authority is recorded,
  not re-derived; no schema motion needed for the grant because the terminal record
  already pins the commissioning digest.

A new "grant document" or a new admin operation would need all of: a new schema, a new
mint/revoke lifecycle, drift surfaces, and a reason the commissioning document's
existing grant fields cannot carry it. No such reason exists (Fork F1 puts the
question to the owner anyway, because it sets who can self-serve unattended runs).

---

## 5. Pre-committed acceptance rule

**Metric: refusal-matrix coverage** — committed before any result is read. The test
file enumerates a matrix over the demo lattice with controlled mutations:

- Illegal cells (the gate must refuse at the SEAM, typed `policy_denied`, message
  carrying the named prefix):
  1. `gateway_owned` + no `"unattended"` in modes × {lease absent, lease present} — 2
     cells → `unattended_grant_absent:` (the lease-present cell also pins that the
     refusal fires BEFORE lease consumption: the lease must survive unconsumed).
  2. `gateway_owned` + `"unattended"` in modes + evidence row absent — 1 cell →
     `unattended_evidence_failed:`.
  3. same + evidence row present with `result != "passed"` — 1 cell →
     `unattended_evidence_failed:`.
  4. `gateway_owned` + grant ok + `expires_at` < now + max_body + max_protection ×
     {marginally (1 ms), badly (days)} — 2 cells → `qualification_window_exceeded:`.
  5. `gateway_owned` + grant ok + `expires_at` in the past — 1 cell →
     `qualification_expired:`.
  6. `manual` + lease absent + window ok — 1 cell → `manual_lease_required:`.

  **N = 8 illegal cells** as designed. If a cell proves infeasible to author, the
  record is amended with the reason BEFORE results are read, or the measurement is
  void — never silently dropped.

- Legal cells (must admit and reach a terminal record): `gateway_owned` + grant ok +
  covering window × {lease absent, lease present}; `manual` + lease present + covering
  window; `manual` + lease present + no unattended grant (a manual run needs no
  unattended grant — only the window). **4 legal cells.**

- Parity arms: for each of the 5 refusal classes, ≥1 arm asserting the worker layer's
  refusal string is **byte-identical** to the seam's for the same lattice (the #260
  Risk-4 machine-check pattern).

**SHIP iff all of:**
- (a) 8/8 illegal cells refuse at the seam with the named prefix (100%; one miss is
  needs-work, not a partial ship);
- (b) 5/5 refusal classes have a passing parity arm;
- (c) 4/4 legal cells admit and complete;
- (d) **RED control**: with the helper neutralized (reverted in place), 0/8 illegal
  cells refuse at the seam, AND the pre-change counterexample
  (`fixtures/execution` as it stands on `origin/main`: `gateway_owned` procedure,
  supervised-only commissioning) admits a run start — the defect, demonstrated.

**KILL the increment if:** any illegal cell admits with the gate in place (gate
incomplete); or any legal cell refuses (over-tight — including any breakage of the
existing demo/e2e suites, which are the legal-cell controls at full-battery scale).

**KILL the measurement (underpowered/polluted) if:** the RED control shows any illegal
cell refusing *without* the gate (the matrix is measuring a pre-existing refusal, not
this gate — re-author the cell, re-run; no verdict is taken); or fewer than 6 illegal
cells survive authoring; or any refusal class ends with no parity arm.

**Sample size** is the matrix itself: 8 illegal + 4 legal + 5 parity + 2 control arms
≈ 19 test arms. Small on purpose: the population is enumerated (a closed mutation
product), not sampled — coverage, not statistics.

**RED-sanity:** the gate's tests must be shown RED on `origin/main` before the fix
(rubric G3; `no tests ran` is a failed check — read the collected count).

---

## 6. Invariant and drift impacts

- **New invariant CTL-10** (append to `docs/internal/invariants.md`, Control &
  execution): *A run start over a `gateway_owned` procedure requires the commissioned
  unattended grant — `commissioning.modes` contains `"unattended"` with a passing
  `unattended`-category evidence row — and every run's window
  (`acceptance + max_body_ms + max_protection_ms`, caller-supplied `now_wall`) must fit
  inside `commissioning.expires_at`; a `manual`-mode start requires a presented lease.
  Refusals are typed (`unattended_grant_absent:`, `unattended_evidence_failed:`,
  `qualification_expired:`, `qualification_window_exceeded:`,
  `manual_lease_required:`) and are raised at the seam (best-effort, inverted-guard,
  before lease consumption) and authoritatively at the worker — one helper, both
  layers. A02 (the grant is commissioned qualification, never inferred), A04 (pure
  arithmetic on declared values; no client can silently promote to autonomous
  execution), A12 (the procedure cannot rewrite its operating envelope — the grant
  lives outside it).*
- **STO-4** unchanged (its arithmetic is untouched); CTL-10 cross-references it — the
  run lease's horizon is the quantity now also bounded by the qualification interval
  at admission.
- **CON-1..CON-15**: no amendments — exact-byte decode, digest pins, the 14-code
  failure envelope, and the fixture digest lattice are all reused as-is.
- **Drift obligations** (from `docs/internal/drift-and-obligations.md`):
  - Obligation 4 (operator-visible behavior): operator-guide + README refusal-family
    row — lands in the slice.
  - Obligation 5 (fixture lattice): **not triggered for the catalogue lattice** —
    `scripts/registry/build_fixtures.py:206-227` reads only the two descriptor files
    from `fixtures/execution/`; the commissioning fixture is outside it. The
    commissioning change's real consumers are the bootstrap/demo tests
    (`tests/unit/test_bootstrap_admission.py`, `tests/integration/test_clean_install.py`,
    `tests/faults/test_recovery_sweep_faults.py`, `tests/control/test_execution_pin.py`,
    `tests/unit/test_seam_control.py`) — re-run, expect green (the change is
    schema-additive within existing enums).
  - Obligation 13 (validation-report family): census unchanged; no report bytes move.
  - Obligation 3 (device-developer-guide): not triggered — no plugin-ABI or
    packaging change; procedure authoring is operator-guide territory.
- **Surfaces that do NOT move**: MCP tools, REST/openapi, operation-catalog, run-record
  schema, store migrations (no new column — `runs.authority` exists since v3), the SDK
  repo (the check is gateway-only, like `provider_not_admitted:` — the SDK cannot see
  commissioned state), the vendored standards tree. **On-disk formats: none.**
- **CI cost:** ~15-25 new focused tests; no new jobs; the full battery + faults run
  once pre-push as usual. Tier 3 → two independent adversary lanes (standing rule,
  2026-09-24 R3) + cold full suite.

**Standards involvement: NONE.** No `standards/` bytes and no version strings move.
One disclosed standards-side hazard, not touched by this slice: the vendored example
commissioning (`standards/execution/0.2.0/examples/commissioning.json`) carries
`expires_at: 2026-10-09T00:00:00Z` — six days out. The gateway never runs the example
lattice (only `fixtures/execution/` is admitted), but any future test that runs this
gate over the vendored examples will start refusing that date; the example will need a
synthetic far-future date in whatever bump next touches it. Tests in this slice use
their own timestamps.

---

## 7. Review tier and the Step-1 keyword scan (#254)

**Tier 3**, by two independent rules:

- Path rule: touches `src/benchweave/control/documents.py` (persisted-format
  surfaces family) and `fixtures/execution/`.
- Keyword rule: the expected diff text carries Tier-3 keywords.

Keyword scan over the expected slice-1 diff text (all eight files, docs and code
alike) — estimated counts from the designed content, to be re-stated with exact counts
in the review:

- `protection` — est. 10-18 (the helper's `max_protection_ms` arithmetic, the
  invariants row, test assertions, this record's deferrals).
- `sha256` — est. 6-10 (digest-addressed resolution code, fixture pins in tests).
- `recovery` — est. 1-3 (invariant/doc prose citing recovery doctrine).
- `hashlib` — 0 (no new hashing; digest resolution reuses the content store).
- `migrate` — 0 (no store migration).
- `threading` / `asyncio` / `subprocess` — 0.

First-match-wins lands Tier 3 regardless of order; the G6 adversarial second lane is
mandatory and, per the standing two-lane rule, runs as two independent adversary
lanes. The standards-governor pass is not mandated by the letter (zero standards
bytes) — the record states `standards_touch: false`; a reviewer may still dispatch it
as a courtesy pass since the slice enforces corpus semantics.

---

## 8. Owner forks (the authorization model is the owner's call)

**F1 — who grants unattended, and where does the grant live?**
- (a) **Recommended — the commissioning document, as the corpus already sketches**:
  `modes` + `unattended`-category evidence + `approved_by/at` + `expires_at`, scoped
  to the commissioned procedure set (`procedure_refs`). Zero standards motion; the
  bench owner and test-safety owner approve it at commissioning (A02: qualification
  per bench); GW-56 reads it through the binding's commissioning pin. Consequence:
  granting unattended is a commissioning act (re-commission to add it), and the grant
  covers the whole commissioned procedure set, not per-procedure classes.
- (b) A separate unattended-grant document with its own lifecycle: finer-grained
  (per procedure class, independent expiry), but needs a new schema, admission
  wiring, drift surfaces, and a reason the commissioning fields cannot carry it.
- (c) A binding field: rejected on evidence — the binding is client-authored at
  request time; a grant field there is the requester authorizing itself. (Listed for
  completeness; not recommended.)
- The fork exists because (a) makes unattended a *commissioning-time* owner decision
  with re-commissioning friction, and only the owner can rule that friction correct
  for multi-developer benches.

**F2 — what bounds an in-flight endurance run when qualification approaches expiry?**
- (a) **Recommended — acceptance-time window arithmetic only**: a start whose
  `acceptance + max_body + max_protection` exceeds `expires_at` is refused; a
  compliant run can never straddle expiry, so no mid-run timer exists. Pure A04
  arithmetic; the run lease (STO-4) remains the binding budget.
- (b) Mid-run expiry enforcement (curtail + protective transition at
  `expires_at`): a new timer, a new protective reason, and a run killed mid-body that
  arithmetic could have refused at the door. Only worth it if the owner wants
  qualification intervals shorter than bodies (impossible under (a)) — i.e. only if
  D5's schedules-of-bodies lands and per-body windows must shrink dynamically.

**F3 — does the manual-mode lease guard land here or with #307's lease ruling?**
- (a) **Recommended — land it here**: it is structural (`manual ⇒ lease present`),
  needs none of #307's pending numeric rulings, is vacuous in-tree today (every
  in-tree procedure is `gateway_owned`), and completes the mode-consistency rule the
  contract states. Two tests, one refusal branch.
- (b) Defer to #307: keeps lease semantics in one lane, but leaves
  `manual`-without-lease startable gateway-style until that ruling lands — the same
  silent-promotion hole this issue closes, one mode over.

The recommendation set is (a)/(a)/(a); the design is buildable as-specified under it,
and forks (b) variants would each need a record amendment, not a redesign.

---

## 9. Top risks, each with its falsifier

1. **False refusals break the demo/e2e paths** (the fixture change misses a consumer).
   Falsified by: the 4 legal cells + the full cold battery (the demo lattice IS the
   legal-cell control at suite scale). If any existing suite reds with the gate on,
   the gate or the fixture update is wrong — needs-work.
2. **Seam/worker TOCTOU** (documents swapped between seam check and worker
   admission). Falsified by: digest-addressed resolution (both layers read the same
   digests; a changed document is a different digest, and the admission pin lattice
   refuses the mismatch). Adversary arm: mutate the commissioning between POST and
   worker run; expect the worker's authoritative refusal, never a silent pass.
3. **Time-bomb timestamps** (the §6 disclosed example; tests pinning near-term
   dates). Falsified by: this slice's tests using parametric/far-future timestamps
   only; a grep of the new test file for literal near-term dates at review.
4. **Replay/idempotency regression** (a §9 replay of an accepted request re-checked
   and refused). Falsified by: the replay-precedence arm — the peek precedes the
   gate in `run_start`'s order; pinned explicitly.
5. **Lease consumed on a refused start** (ordering bug). Falsified by: illegal-cell
   1's lease-present arm asserting the lease survives unconsumed.
6. **The gateway-owned-with-lease corner** (an operator's manual lease consumed by an
   unattended run that then outlives their attention). Disclosed residual, legal per
   the contract (D12 takeover is a deliberate handoff; `authority_changed` records
   it); flagged for the adversary lanes to attack the disclosure, not the code.
7. **The issue's own stated mechanism is corrected, not implemented** ("zero corpus
   presence" is false; the gap is enforcement). If the owner disagrees and wants a
   *new* grant mechanism (F1b), this design's slice 1 is still the right first move —
   any grant document would gate through the same two-layer helper.

---

## 10. Post-landing obligations

- Post the design outcome to issue #316 (per-row verdicts, fork options + recommendation,
  record path) — the main session posts; this lane does not write to GitHub.
- Memory proposals: the defect pattern (the attended path validated while the
   autonomous path is the unchecked default) and the fixture-lattice counterexample
   finding go to the proposal ledger from this lane.
