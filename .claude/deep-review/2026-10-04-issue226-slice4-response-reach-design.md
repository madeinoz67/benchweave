# Issue #226 — registry train slice 4: response reach (design record)

**Status:** Design (builder-ready) · **Tracking issue:** madeinoz67/benchweave#226
(#209 slice 4 of 6) · **Parent design:**
`docs/implementation-planning/10-contributor-publishing-design.md` §3.6 + §4 Slice 4
(acceptance rule D) — this record makes §3.6 concrete and executable; where the two
disagree the parent record wins and this record is defective.
**Requirements:** `docs/implementation-planning/07-contributor-publishing-prd.md`
(Draft v0.3, §9 rulings FIXED — Q14, Q19, NFR-S2, NFR-S3, CR-42, CR-53 bind here).
**Evidence baseline:** gateway `main` at `b67863b` (2026-10-04); registry repository
`main` at `6697504`; SDK at the pinned gitlink (not read — no SDK bytes move).
Every code claim below was read at this baseline; every number carries its denominator.

**Scope in one line:** the ONE gateway change of the registry train —
`commissioned_device_closure` gains a cached, signature-verified status consult with a
committed staleness bound, so a published revocation, yank or advisory reaches the next
run-build of an already-commissioned closure (M6 closed). Registry repo: nothing
(slice 3's advisory records already exist). SDK repo: nothing.

---

## 1. Root cause, traced to the line

M6 ("response failure", PRD §5(l).1) is real at the baseline and its mechanism is exact:

- `src/benchweave/interfaces/device_closures.py:132` `commissioned_device_closure`
  re-reads every closure release's **manifest** through the origin sources and
  digest-verifies it against the admitted lock row (`closure_manifest_drift`), then
  serves the bridge construction inputs. It reads **no status document anywhere** —
  verified by reading the whole module (11904 bytes, one file): the words `status`
  appear only in the docstring's explanation of why the *resolver* cannot be reused.
- The resolver path (`src/benchweave/registry/resolver.py::_resolve_release`) does read,
  schema-load, signature-verify, release-bind and gate every status — but it advances the
  strictly-increasing high-water (`check_status` refuses `sequence <= high_water[key]`,
  `src/benchweave/registry/authenticity.py:65`), so a second resolve of an
  already-admitted release is structurally impossible. That is why the consult cannot
  reuse `resolve` and must exist as its own read-only path.
- Admission (`src/benchweave/registry/admission.py:147` `_gate_lifecycle`) refuses
  `revoked`/`yanked` — but only **at admit time**. A closure admitted before the
  revocation was published keeps executing forever: nothing between admission and
  run-build ever looks at lifecycle again. Both refute lanes of the PRD audit confirmed
  this (PRD §5(l) M6 row; the lane design record §1 line 22).

So the defect is not a missing check — the checks all exist (signature verify, release
binding, expiry/future/sequence gates, lifecycle refusal) — it is that they run at two
moments only (resolve, admit) and never at the third moment that matters (run-build of an
already-commissioned closure). The consult wires the EXISTING checks into the third
moment. No new verification logic is invented; that is the whole design.

**Verified facts the mechanism stands on** (all read at the baseline):

| Fact | Site |
|---|---|
| `PackageSource` already exposes `status_bytes` + `status_signature` | `resolver.py:63` (Protocol), `LocalDirectorySource` at :93 |
| Status schema carries `lifecycle` enum {published, deprecated, yanked, revoked}, `advisories[]` items {id, severity, summary, url}, `sequence >= 1`, `expires_at`, `updated_at` | `standards/registry/0.1.2/release-status.schema.json` (0.1.1-identical; `status_version` const stays "0.1.1" in both) |
| The release binding a status must satisfy: its `release` block names the key AND pins the served manifest digest | `resolver.py` (`status_release_mismatch`), re-run by `admission.py` `_gate_lifecycle` |
| Admission's own **persisted-layer** sequence rule already allows same-sequence replay and refuses only a lower sequence | `admission.py::_gate_lifecycle` (`if sequence < water.get(key, 0): raise`) with its docstring naming idempotent re-admission |
| The persisted floor lives at `<cache_root>/high-water.json` and its loader is reusable read-only | `admission.py::_load_persisted_high_water` (absent file = empty map; malformed = `high_water_invalid`) |
| `RegistrySession` already carries `roots`, `cache_root`, `now_ns`, `resolver` | `src/benchweave/interfaces/bootstrap.py` (`RegistrySession`, `build_registry_session` — one signed `origin-main`, fail-closed `required` posture) |
| The registry specification itself names the client duty the consult implements | `standards/registry/0.1.2/registry-specification.md`: "Clients persist the highest authenticated sequence per release and reject older status" |
| The consult's exact shape already exists twice as a proven pattern | `admission.py::_gate_lifecycle` (gates + binding + lifecycle refusal) and `benchweave-registry/scripts/replay_admission.py::_replay_real_tree` (served bytes → schema → signature → binding → gates → lifecycle reading, on gateway machinery) |
| Lifecycle rewrite discipline: every status change rides sequence+1 | SDK `registry_ops.py` (`yank_release` "sequence+1 lifecycle yanked", `advise_release` appends under sequence+1); REG-5a's per-op ordering clauses |

**A discovery that reshapes one clause of the parent record.** The parent design §3.6
says "verify it against the session's trust root" for every served status. The gateway's
routed origin (`fixtures/registry/origin-main`) does serve `status.sig` for every release
(verified: `sim-psu-descriptor/1.0.0/` carries `manifest.json`, `manifest.sig`,
`status.json`, `status.sig`, `payload.zip`), so the consult's signature verification is
provable on the only origin any stock session routes. But the **registry repository's
real releases** (`releases/benchweave-registry/madeinoz67/dps150/0.1.0/`) carry NO
`status.sig` and no committed origin root — the slice-3 R1 owner ruling made the registry
"VALIDATE + PUBLISH + LABEL, never signs", and the lane-posture replay
(`replay_admission.py`) refuses the dogfooded release today with
`status_signature_absent`/`origin_root_absent` (issue #225 F2/F3 residuals). This is not
a slice-4 defect and slice 4 does not touch it: no stock gateway session routes the real
origin (the lane's D2 deferral owns third-party origin consumption). The design states
it because an adversary will: **the consult's reach guarantee is only as good as the
status channel the origin serves**; until the registry repository's F2/F3 follow-up
lands (committed origin root + held-maintainer status signatures), a gateway consuming
that origin could not consult at all — it would refuse `closure_status_signature`
fail-closed rather than silently skipping verification. Degrade loudly, not silently.

## 2. The mechanism

### 2.1 The consult (inside `commissioned_device_closure`)

After the manifest re-read loop has digest-verified each closure release's manifest
against the lock row (the loop at the `closure_manifest_drift` check), the same
iteration consults that release's status, per release key
`(registry_id, package_id, version)`:

1. **Cache.** A per-session view cache (see 2.3) is checked first. A view consulted at
   `consulted_at_ns` is fresh while `now_ns() - consulted_at_ns <=
   _STATUS_CONSULT_BOUND_NS`. Fresh → the cached verified view is used and **zero
   status reads are performed**.
2. **Read + schema.** `source.status_bytes(package_id, version)` (the source the
   manifest re-read already used), loaded through `load_status_document` with the
   resolver's own budget (`_STATUS_MAX_BYTES = 100_000`). A missing/unreadable status
   is a typed refusal (`closure_status_absent`), never a raw OS error.
3. **Authenticity.** `source.status_signature(...)` +
   `verify_document(status_doc, status_sig, session.roots[registry_id])` — the
   fail-closed `required` posture the session already enforces everywhere. A root
   absent from `session.roots` for a routed origin refuses
   `closure_status_root_absent` (mirrors `admit`'s own "roots must cover every
   registry id" contract). No dev-unsigned consult posture is built (§6 S4-D1).
4. **Release binding** (the resolver's anti-swap check, restated): the status's
   `release` block must name exactly this key and pin the manifest digest the loop
   ALREADY verified against the lock — else `closure_status_release_mismatch`. A
   validly-signed foreign "published" status cannot mask this release's revocation.
5. **Gates, consult semantics** — new `consult_status(status, *, now_ns, floor)` in
   `src/benchweave/registry/authenticity.py`, beside `check_status`, sharing its
   private clock helpers and `_FUTURE_TOLERANCE_NS`:
   - expiry: `expires_at <= now` → `expired_status` (an unattested lifecycle is
     UNKNOWN, not published — fail closed);
   - future: `updated_at > now + tolerance` → `future_updated_at`;
   - **floor instead of fence**: `sequence < floor` → `sequence_rollback` (a NEW
     reason name, deliberately distinct from `stale_sequence` — consult semantics,
     where replaying the same sequence is the healthy case). `floor` is the persisted
     high-water value for the key. This is exactly `admission.py::_gate_lifecycle`'s
     persisted-layer rule ("replaying the SAME authenticated sequence … is allowed
     and only a lower one is rollback"), lifted verbatim; the resolver's strict
     fence is NOT used, for the reason the module docstring already gives. The
     consult writes nothing back — no high-water advance, no lock change, no cache
     write outside its own view cache. It is a consult, not an admission.
   Authenticity rejections map to `ClosureResolutionError` with `closure_status_*`
   prefixes (the module's existing machine-prefix discipline; `device_closures.py`
   does the mapping the way `admission.py` maps with `_WRAPPED_STATUS_REASONS`, so
   the owning layer stays visible).
6. **Lifecycle.** `lifecycle == "revoked"` → raise `closure_status_revoked`;
   `lifecycle == "yanked"` → raise `closure_status_yanked`; `published` and
   `deprecated` proceed (the same classes `_gate_lifecycle` refuses/admits — an
   advisory-carrying deprecated release is honest degradation, not revocation).
7. **Advisory delivery (Q14's recorded operator half).** `advisories` non-empty →
   the run PROCEEDS and the advisory is DELIVERED: one append-once record under the
   session's advisory directory (2.3) per (release key, advisory id) —
   `advisory-<sha256-of-record-bytes[:16]>.json`, canonical JSON, carrying release
   coordinates, the advisory verbatim, the consulted status digest, `consulted_at`,
   and `kind: "operator_advisory"` — plus a `_LOG.warning("closure_status_advisory:
   …")` line. Re-consults of the same advisory are idempotent (no second record). An
   advisory does not refuse the run: CR-29 fixes advisory semantics as
   informational (admission's gates refuse revoked/yanked only), and the consult
   mirrors admission's classes rather than inventing stricter ones.
8. **Cache write.** The verified view (status content, served digest, consulted_at_ns)
   enters the session's view cache.

### 2.2 Approval-drift surfacing (D4, CR-42) — beside the consult, on the manifest already read

For each closure release whose digest-verified manifest carries a `review` block
(registry 0.1.2; optional, so every 0.1.1 manifest is simply out of scope): if
`review.outcome != "accepted"`, the consult SURFACES drift — an operator-advisory
record (`kind: "approval_drift"`) plus a `_LOG.warning("closure_status_approval_drift:
…")` line — and the run continues. CR-42's kill direction is *silent acceptance*, not
the run: a commissioned release whose published review block records a non-acceptance
(the local lock `approval` block asserts an approval-for-commissioning; a published
`changes_requested`/`unreviewed` outcome contradicts it) must never ride silently.

What D4 deliberately does NOT do, stated so no later slice mistakes it for an accident:

- **No identity-equivalence check** (`lock.approval.principal_id` vs
  `manifest.review.reviewer_id`). The two fields name different roles — the local
  principal who approved commissioning versus the registry-side reviewer — so equality
  is not a drift signal and its absence is not an agreement. CR-42's *signed* approval
  binding (approval signature over the release digest, carried in the index) is what
  makes identity-level cross-checks honest, and it does not exist yet (§6 S4-D2).
- **No refusal.** The drift is surfaced, never enforced — REG-5's "the gateway never
  consults it" holds for ADMISSION byte-for-byte; the run-build consult reads `review`
  for surfacing only, never as provenance, never for gating. The REG-5 amendment (§4)
  states this seam precisely.

### 2.3 Wiring (the only shape changes outside the consult body)

`RegistrySession` (bootstrap.py) gains two explicit fields, both set in
`build_registry_session` — explicit configuration, never derived by convention:

- `advisories_dir: Path` — `work_root / "advisories"` (the operator-delivery records;
  a sibling of `activations/`, per-release rather than per-bench);
- `status_cache: dict[Key, _StatusView]` — the per-session view cache (the session is
  constructed once and attached to the Operations seam; a fresh session starts cold,
  which is the honest freshness floor: a process restart forces re-reads).

The staleness bound is a named module constant in `device_closures.py`:

- `_STATUS_CONSULT_BOUND_NS = 300 * 1_000_000_000` (5 minutes), with its NFR-S2
  denominator statement in the docstring (§4 carries the amendment text). Rationale,
  pre-committed: run-builds on a local bench are operator-initiated and sparse, so the
  cache is a cost bounder for dense run patterns and future remote origins, not a
  reach-killer; 5 minutes bounds the blind window tightly enough that a published
  revocation reaches the next run-build inside any realistic operator response loop.
  Per-bench commissioning of the bound is deferred (§6 S4-D3).

No other surface moves: no MCP tool, no REST route, no CLI, no schema, no standards
byte. The refusal surfaces exactly where `closure_*` refusals already surface — run
start (`_device_plans` → `build_run`), poison-guard greppable, and the recorded
advisories are operator-visible records + log lines (the console that might render them
is issue #210's surface, per PRD (l.3)).

## 3. Minimal first increment and its deferrals

**The increment is:** `consult_status` (authenticity.py) + the consult body, cache,
advisory delivery and drift surfacing (device_closures.py) + the two session fields
(bootstrap.py) + the test family (tests/integration/test_run_activation.py extension —
the #167 lane's own file, where the commissioned-closure run path is already pinned) +
the four doc surfaces (§4). One repo, one branch, one PR.

**Explicitly NOT built** (each with identifier / deferred / home / reopen trigger — §6):

- anything in the registry repository or SDK (the issue's own scope line: the advisory
  record shape already exists from slice 3);
- the multi-origin config surface (the lane's D2, restated);
- CR-42's signed-approval channel and identity binding (S4-D2);
- dev-unsigned consult posture (S4-D1); remote-origin transport semantics (S4-D4);
- per-bench commissioning of the bound (S4-D3);
- any console/MCP rendering of advisory records (#210);
- **anything slice 5 needs** (kind tags, community-shared records, unverified markers —
  the consult is lifecycle-only and must not grow a `kind` read);
- **anything slice 6 needs** (loader parity, sim-lane guard, trust-root fingerprints,
  dev-origin refusal — the consult consumes the session's roots as they are and must
  not grow fingerprint verification, which is CR-40's lane).

## 4. Invariant, drift and cross-surface impacts

- **REG-5 amendment (this slice's PR, dated, append-with-evidence):** the reach clause
  becomes true — "yank/advisory reach commissioned gateways through the run-build
  status consult with a stated, testable bound (NFR-S2's denominator) and cached cost
  (NFR-S3)". The amendment text also carries the two precision notes: (a) admission
  still never consults `review` — the run-build consult reads it for drift surfacing
  only; (b) the consult's verification posture is the session's fail-closed `required`
  policy over the status channel the origin actually serves.
- **CTL/STO: unamended.** The consult is pre-run resolution refusing loudly, inside the
  existing `closure_*`/`ClosureResolutionError` family — the same failure surface and
  the same run-start refusal `_device_plans` already produces for
  `closure_manifest_drift`. No control-path, store or migration byte moves.
- **The #167 design record**
  (`.claude/deep-review/2026-09-23-issue167-run-engine-activation-design.md`): a dated
  amendment note on Decision 1's authority chain — the commissioned closure's run-build
  preconditions now include the status consult beside the manifest re-read (the parent
  record §4 Slice 4 names this edit).
- **Obligation 27** (`docs/internal/drift-and-obligations.md`, the publishing-lane
  surfaces row): gains the consult + the advisory-record surface + the bound-statement
  locations (module constant, REG-5, publishing guide).
- **`docs/publishing-guide.md`:** a short "Response reach" statement under Honest
  boundaries — the bound (5 min), its denominator (reachable-at-next-run-build covered
  by the consult; offline-since-publication and no-build gateways covered by recorded
  operator delivery at their next consult), and that a yanked/revoked release refuses
  the next run-build of a commissioned closure. (The guide is in the ASD-STE100
  documentation register — the document-writer agent authors this paragraph.)
- **On-disk format:** one new lane-local record (the operator-advisory delivery record,
  canonical JSON, no standard schema — the activation-record precedent). It joins the
  parent record's §5 format inventory by this record naming it; it is NOT a standards
  byte and carries no version string.
- **Standards bytes: none. No version strings.** No governor dispatch (the
  standards-governor mandate fires on `standards/` touches; this slice has none —
  `git diff origin/main...HEAD -- standards/` stays empty, tripwire-checked at push).
- **CI cost:** one fault-style test family on local-dir origins (no live services, no
  network), plus the existing battery. Measured at merge with the cost figure (D2).

**Cross-repo:** no registry-repo or SDK-repo PRs. The registry repo's slice-3 F2/F3
residual (origin root + status signatures for real releases) is a named dependency for
REAL-origin reach, not a slice-4 gate (§1's discovery paragraph).

## 5. Pre-committed acceptance rule (rule D, executable)

All arms run on a runtime-keyed local origin built the `tests/integration/test_registry_reuse.py`
way (fresh Ed25519 keypair, served tree in a tmp dir) — the committed
`fixtures/registry` statuses are signed by CI-materialised keys and cannot be re-signed
in tests; the harness signs its own statuses, which is exactly what D1's
publish-a-revocation step needs. Deterministic arms; no sampling variance — the
pre-commitment is on exact behaviors. Baselines are committed BEFORE the mechanism.

**D1 — reach (CR-53; closes M6).**
Fixture: one implementation release serving a descriptor, resolved → admitted →
activated for one bench device (the `test_run_activation.py` construction), then the
served status is rewritten by the test the way the SDK's lifecycle ops do it
(`registry_ops.yank_release` discipline): lifecycle flip, `sequence + 1`, `updated_at`
bumped, re-signed by the origin key, `expires_at` renewed.
- **RED baseline (committed first):** on `main`, the same run-build SUCCEEDS with the
  revoked status served — the test asserts today's behavior and names M6 in a comment;
  the recorded run output is the M6 reproduction the parent record requires.
- **SHIP:** with the mechanism, the next run-build raises `closure_status_revoked`.
  Arms: revoked → `closure_status_revoked`; yanked → `closure_status_yanked`; advisory
  (lifecycle `published`, `advisories: [{id, severity, summary, url}]`, sequence+1) →
  run PROCEEDS + exactly one advisory record + one warning line + a re-consult writes
  no duplicate; rollback (served sequence below the persisted floor, re-signed) →
  `closure_status_rollback`; expired (expires_at in the past, sequence+1, re-signed) →
  `closure_status_expired`; swapped status (validly signed, names another release's
  manifest digest) → `closure_status_release_mismatch`; absent status file →
  `closure_status_absent`.
- **Controls (each must PASS for the arm to count):** the untouched closure (published,
  sequence unchanged — the same-sequence replay case) run-build stays green; and the
  healthy-control arm run under a COLD cache after process-fresh session construction
  (the restart-freshness floor).
- **KILL:** the revocation not reaching the next run-build (run-build green with a
  revoked status served — the M6 behavior surviving); any control failing; any
  refusal without its `closure_status_` prefix.

**D2 — staleness and cost (NFR-S3).**
Injected clock (`session.now_ns`) + an instrumented `PackageSource` wrapper counting
`status_bytes` calls (the "monkeypatched-clock/socket" control adapted to local-dir
origins — there is no socket to patch; the counting wrapper is the honest equivalent
and is stronger: it counts the reads themselves).
- **SHIP:** consult #1 cold → count == 1 per release; consult #2 within the bound →
  count == 0 (zero reads — exact); clock advanced past `_STATUS_CONSULT_BOUND_NS` →
  count >= 1 again. Measured cost figure committed with the merge: run-build cost,
  consult cold vs consult disabled, N = 20 iterations, median and p95 reported,
  conditions stated (local-dir origin, 1-release closure, Python 3.13, the CI runner
  class). No number is pre-assumed here; the pre-commitment is that the mechanism
  ships WITH its measured figure or does not ship.
- **KILL:** unbounded cost (every run-build re-reading with no bound honored — count ==
  builds) or the bound unenforced (a beyond-bound consult served the stale view).

**D3 — denominator (NFR-S2).**
The bound's statement (module docstring + REG-5 amendment + publishing guide, all three
committed) names both halves: gateways REACHABLE at next run-build after publication
are covered by the consult with delay ≤ the bound; gateways OFFLINE since publication
or running no builds are covered by the recorded operator-delivery half — their
refusal/advisory lands at their next consult whenever that happens, and until then the
bound makes no claim. The exercise: D1's revocation arm demonstrates the reachable
half end-to-end; the absent-status arm (`closure_status_absent`, cold cache, origin
dir emptied) demonstrates the offline half's honest behavior — refuse loudly, never
assert published.
- **KILL:** a denominator-less statement (any of the three surfaces stating a bound
  without naming which gateway states it covers).

**D4 — approval drift (CR-42).**
Fixture: a 0.1.2 manifest whose `review` block carries `outcome: "changes_requested"`
(admission is review-indifferent by CR-13, so it admits and commissions — the fixture
proves that). **SHIP:** the consult surfaces drift — one `approval_drift` advisory
record + warning line — and the run continues; control: `outcome: "accepted"` → no
drift record. **KILL:** silent acceptance (a non-accepting review block riding a
commissioned run with zero surfaced signal).

**RED ordering:** D1's refusal test is written first and shown RED on `main` (it fails
by the run-build succeeding — that failure output IS the M6 reproduction); then the
mechanism lands and every arm goes GREEN. Per the repo's G3, `no tests ran` is a failed
RED check; the collected count is read from `--junitxml` attributes, never an
output-filter summary line.

**Underpowered reading (pre-committed):** if D2's measured figure cannot be produced
with its conditions stated (harness cannot measure repeatably — e.g. CI runner variance
swamping the delta), the slice does NOT ship on an unmeasured claim; the measurement
harness is fixed and re-run, or the slice parks with D2 open. A green suite with no
committed figure is the same failure, not a pass.

## 6. Deferrals (identifier / deferred / home / reopen trigger)

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| S4-D1 | Dev-unsigned consult posture (skip-signature consult for dev origins) | The consult's fail-closed root requirement; no production session routes a dev origin (`build_registry_session` wires exactly one signed origin; the PRD's "operator config accepts a dev origin" arm is refuted) | The first dev-origin routing surface — the lane's D2 multi-origin config, or a #167 dev-loop lane that wants run-build over dev closures |
| S4-D2 | CR-42's signed-approval cross-check (verifiable approval signature over the release digest, carried in the index; identity-level principal↔reviewer binding) | This record §2.2; REG-5 | Slice 6's CR-40/41 channel landing, or the registry index carrying verifiable approval signatures |
| S4-D3 | Per-bench commissioning of the staleness bound (A02 lens: a response-time bound is a commissioned parameter the moment a bench's reach requirement differs from the lane default) | The module constant + its docstring | The first bench with a commissioned reach requirement ≠ 300 s, or the operator deploy-config surface that owns such knobs |
| S4-D4 | Remote-origin consult transport (HTTP origins, timeouts, partial-failure semantics) | The consult's local-dir reality (`LocalDirectorySource` only) | The lane's D2 multi-origin surface, or the first HTTP origin |
| S4-D5 | Wrapping the manifest arm's raw read errors (a vanished origin today propagates a bare `FileNotFoundError` from `source.manifest_bytes`) | Disclosed here; pre-existing, untouched | Any slice editing the manifest re-read loop |
| lane D2 | Gateway multi-origin config surface | The lane record §6 | As ruled there |
| **D8/Q19** | **The truncated threat-catalogue entry's re-issue and verdict — BLOCKING on this slice's acceptance FINALITY, not on its build** | The lane record §6 D8 + §7; PRD §9 Q19 | The owner re-issues and verdicts the entry (see §7 risk 7) |

## 7. Top risks — each with what falsifies this design

1. **Availability regression (the posture call).** The consult makes origin status
   availability and status expiry run-relevant for the first time: a registry that
   lets statuses expire, or an origin that vanishes, refuses commissioned benches —
   loudly, by design (an unattested lifecycle is unknown, not published; A06). The
   fixture statuses expire 2027-09-11 and the committed lattice already lives under
   this clock at commissioning time (admission's own `expired_status` gate) — the
   consult extends the same clock to run-build, it does not invent a new duty class.
   **Falsifier:** the expired arm refusing; the healthy controls staying green. If the
   owner judges availability-over-containment here, the whole fail-closed posture
   inverts and this design is wrong — that is an owner fork, surfaced in §8.
2. **Cache staleness laundering a revocation published inside the bound.** True and
   accepted: the bound IS the reach delay, stated with its denominator (D3). What
   would falsify the design: a beyond-bound consult serving a stale view (D2's third
   arm), or the same-sequence-replay rule accepting a REPLACED status — prevented
   structurally only by the registry's sequence discipline (every lifecycle change
   rides sequence+1; REG-5a's ordering clauses + the SDK lifecycle ops), which is why
   the design consumes that discipline rather than re-verifying it, and says so.
3. **The REG-5 seam ("the gateway never consults review").** D4 makes the RUN-BUILD
   consult read `review` for surfacing. An adversary will read REG-5 as violated. The
   defense is the amendment's precision (admission never consults it — byte-true,
   pinned by `tests/contract/test_registry_review_block.py`'s admission-indifference
   arms; the consult reads it for drift surfacing only, never as provenance, never for
   gating). **Falsifier:** any consult behavior that lets `review` content gate or
   authenticate anything.
4. **M3 inheritance.** The floor comes from local `high-water.json`; a well-formed
   lowered floor disarms the consult's rollback gate exactly as it disarms admission's
   (documented M3 class; CR-55 owns the posture; slice 6 hardens). Not widened here:
   the consult adds no new local-state authority — the cache is in-memory only, so a
   forged on-disk view is unrepresentable across restarts by construction.
5. **Test-fixture divergence.** D1 needs re-signable statuses; the committed fixtures
   cannot provide them (CI-materialised keys). The harness keys its own origin
   (test_registry_reuse / `replay_admission --fixture` precedent). **Falsifier:** any
   arm passing because the harness skipped signature verification rather than because
   the consult performed it — the counting wrapper and the swapped-status arm close
   this.
6. **Advisory-record spam or loss.** Append-once per (release, advisory id) is the
   dedup rule; a missing dedup falsifies D1's advisory arm (re-consult writes a
   duplicate). The records are operator-visible only via files and logs this slice —
   a rendering gap is #210's, disclosed.
7. **The Q19 blocker interacts with THIS machinery.** The one truncated, never-verdicted
   threat-catalogue entry referenced the three status gates (expiry, future-time
   tolerance, sequence high-water — PRD §7.19 confirms the machinery is real; the
   entry's content is not recoverable from the tree and the vault holds no trace of
   it — searched). Slice 4 makes those three gates load-bearing at a NEW moment
   (run-build of commissioned closures), which raises the stakes of the owed verdict:
   the entry may name a threat against exactly this consult shape. Per the ruling
   (PRD §9 Q19; the lane record §6 D8), the re-issue+verdict BLOCKS treating this
   slice's acceptance as final. The recommendation: the owner re-issues it on #209
   BEFORE this slice's acceptance is claimed final; the build may proceed and land
   behind that gate. **Falsifier for this design:** the verdicted entry describing a
   threat the consult's posture fails to handle — that finding reopens this record,
   and the slice's merge holds until it is folded.

## 8. Forks for the maintainer

- **F1 — offline consult posture.** RECOMMENDED: fail closed (`closure_status_absent`
  on a cold-cache unreachable origin; refuse, never assert published). Alternative:
  serve the last cached view with a loud disclosure — rejected because a stale view is
  exactly the "ambiguous outcome laundered as success" A06 forbids; note this
  alternative is what D3's offline half would need if the owner weighs availability
  higher (risk 1's inversion).
- **F2 — the bound's value.** RECOMMENDED: 300 s committed constant (rationale §2.3).
  Alternatives: 60 s (nearer-real-time reach, more re-reads — moot while origins are
  local dirs), or per-bench config now (S4-D3 instead — more surface than the evidence
  demands).
- **F3 — who re-issues Q19 and when.** RECOMMENDED: the owner, on #209, before this
  slice's acceptance is claimed final (the build proceeds meanwhile). This is the
  ruling's own reading; recorded as a fork because the timing is genuinely the
  owner's.

## 9. Review tier and the Step-1 keyword scan (per #254)

**TIER 3.** Rules firing, first-match-wins: (a) path rule — the diff touches
`src/benchweave/registry/authenticity.py`, registry policy behavior (the status-gate
home gains a gate); (b) independently, the keyword rule — the diff text carries
`sha256` and `hashlib`. Tier 3 ⇒ full cold suite + the mandatory second adversarial
reviewer; per the standing two-lane rule (2026-09-24 R3), the refute runs TWO
independent adversary lanes. **No standards-governor dispatch: no `standards/` byte,
no version string, no contract lock moves** (tripwire-checked at push).

**Keyword scan over the expected diff** — measured, not estimated: the counts below
were taken by scanning the committed record text (`grep -o <kw> | wc -l`, output in
the run record) plus the stated expectation for the code/test/docs edits. The whole
expected diff, docs and code alike:

| Keyword | Record (measured) | Code/tests/docs (expected) | Where the content-bearing hits live |
|---|---|---|---|
| `sha256` | 7 | +6..10 | advisory-record digest naming (`advisory-<sha256[…]>.json`), the `manifest_sha256` binding comparisons in the consult and their test assertions |
| `hashlib` | 3 | +2..4 | `hashlib.sha256` uses in `device_closures.py` (already imported) and the test family |
| `protection` | 2 | +0 | both hits are this table naming the word; zero content-bearing |
| `threading` | 2 | +0 | same — self-references only |
| `asyncio` | 2 | +0 | same |
| `subprocess` | 2 | +0 | same |
| `migrate` | 2 | +0 | same |
| `recovery` | 3 | +0 | table cell + this row + one true prose use ("the consult does not touch the run-recovery path") — that single content use is a negative claim about scope, not a touched path |

Self-reference disclosure: this table and its parenthetical name every keyword, so
most rows above are inflated by their own naming (each zero-row word appears exactly
in its table cell plus once here). The two rules that fire, fire on real content: the
PATH rule (`src/benchweave/registry/authenticity.py` — actual gate code) and the
`sha256`/`hashlib` keyword rule on the consult's digest comparisons in code. Tier 3
stands on the path rule alone even if every keyword hit were stripped.

## 10. Disclosed unverified

- SDK tree at the pinned gitlink was not read this session (no SDK byte moves; the
  lifecycle-op discipline claims cite slice-3's landed `registry_ops.py` through the
  gateway-side search index at the baseline).
- The measured cost figure (D2) does not exist yet by design — the pre-commitment is
  that the slice ships with it or not at all.
- The Q19 entry's content is unrecoverable from the tree and the project vault
  (searched this session); §7 risk 7 proceeds on the lane record's own disclosure.
- Registry-repo claims (dogfooded release files, replay behavior) were read at
  `6697504`; that repository can move during the build — the consult does not depend
  on it (no stock session routes that origin), and the F2/F3 residual note is
  informational for reach, not a build dependency.
