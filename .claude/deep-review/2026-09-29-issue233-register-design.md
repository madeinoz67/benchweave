# #233 register pass — the six dormant rows: disposition + one conditional slice

**Issue:** [#233](https://github.com/madeinoz67/benchweave/issues/233) (third register comment —
the owner's work-pass call)
**Date:** 2026-09-29 · **Base:** `origin/main` @ `03a36c2` (fetched this session; the local
checkout was 40 behind and was not used)
**Method:** reads in a detached worktree `.wt/des233-7f3a/` at `origin/main`. Gortex MCP is not
available to this lane (daemon degraded today); every read is native over the worktree — the
CLAUDE.md fallback row, disclosed. No production code, no commits, no PRs from this pass.

**What this pass is:** a per-row trigger-state ruling at current main (including the in-flight
PR #275 interaction), a buildable-vs-external-gated verdict per row, and at most one
recommended minimal slice. A DON'T-BUILD verdict on the externally-gated rows is the expected
outcome; the register's value is the honest disposition.

---

## 1. The register at current main

| Row | Deferred | State at `03a36c2` |
|---|---|---|
| D1 | Network fetch for upgrades (VR-49's fetch half) | `upgrade --precise` resolves offline from served bytes; #209 open at scoping level |
| D3 | Yank designed whole — the operator command beyond the 0.2.1 template | Machine half live end to end; no defective released version exists |
| D4 | Website range/served-set stamps (VR-50's website surface) | Token machinery live; **the trigger is firing in flight — PR #275** |
| D5 | VR-40 "why" query (constraint → locked-version explanation) | No surface; resolver ladder deterministic; rung choice computed then discarded |
| D6 | Per-version migration notes for pre-adoption releases | SM-5 self-anchors; pre-adoption releases grandfathered by mechanism |
| D7 | Interface multi-version serving | `standards/interface/` serves exactly 0.1.0; no bump motion anywhere |

## 2. Per-row disposition

### D1 — network fetch for upgrades · **STAY-DORMANT** (trigger restated)

- **Trigger:** the first externally published standards artifact (the #209 registry service
  standing up). **Un-fired.** #209 ("Registry: contributor submission process — the publishing
  path for third-party plugins") is OPEN at scoping level; nothing publishes standards bytes
  externally today, unchanged since the arc.
- The offline posture is the designed state, not a gap: NFR-1 (resolution offline, PRD:210) and
  `upgrade`'s own shape — `--precise <version>` "(served or yanked)" resolved from local bytes
  (`src/benchweave/standards/__main__.py:71-83`). Building a fetch client before an endpoint
  with digest-verified semantics exists would be speculative protocol work with nothing to
  verify against (VR-49's accept clause — "a fetched file whose digest does not match is
  refused" — cannot even be RED-tested without a publisher).
- **Verdict: DON'T-BUILD.** Trigger restated verbatim.

### D3 — yank designed whole · **STAY-DORMANT** (trigger restated; the designed-whole reading is rejected)

What is already live (all cited, all machine-enforced): the policy-block yank record with
reason and since (`standards/standards-manifest.json` `dependency_policy.standards.otdp.yanked.0.2.1`);
`classify_pin`'s named warning (VR-44's "named warning is shown"); auto-selection never picking
a yanked version (`dependency.py:1447-1455` — `max()` over `served_versions ∩ interval`, yanked
excluded by classification); a yanked version still installable via `upgrade --precise` for an
existing lock (VR-44's "still resolves for an existing lock"); the `list` render's yank rows
and the matrix's yank column. The 0.2.1 template proved the whole machine half in production.

The deferred half is the operator command (`benchweave.standards yank`). Three reasons it stays
deferred, in increasing strength:

1. **The record's own rationale.** PRD Q10 (08-standards-dependency-management-prd.md:284):
   "Yank (VR-44) gets designed whole when a genuinely defective version appears … that's how
   we'd get yank wrong under deadline pressure." No defect exists; 0.2.1's yank is a supersede
   re-roll, not a defect — it is the template, not the case.
2. **A yank record is a governance-bearing write.** PRD:300: "Range changes remain coordinator
   decisions (VR-43)" — and a yank record is the same class of artifact: it changes what every
   consumer resolves. The designed intake today is hand-authoring the policy row inside a
   reviewed standards train (exactly how 0.2.1 landed). A one-command authoring path would
   *lower* the ceremony the governance model places on this write. "Completing the designed
   whole" would here mean completing a ceremony bypass.
3. **Honest negative.** Tooling designed without a case to design against is the failure shape
   this register exists to prevent.

**Verdict: DON'T-BUILD.** Trigger restated verbatim: *the first genuinely defective released
version.* (The owner may fire it by explicit call per the deferral contract; the recommendation
is against.)

### D4 — website range/served-set stamps · **CLOSE at PR #275's landing, evidence pre-committed here**

The trigger is "the first range change after slice 1 lands." PR #275 is that range change in
flight: plugin-ui `>=0.2.0,<0.3.0` → `>=0.3.0,<0.4.0` (narrow slide) and preview
`>=0.1.0,<0.2.0` → `>=0.1.1,<0.3.0` (floor-compliant **multi-serving** — the first standard
serving two releases). The deferred work was "add range/served-set claim sites to the website."
The code says that work is **zero**, structurally:

1. **Every version claim on the website is a token derived from the manifest at assembly**
   (`scripts/assemble_docs_site.py:328-349`, CON-13): `stg-<id>` → the standard's *active*
   version. The site's claim sites are single-version badges and per-version deep links
   (`website/index.html:330-357`) — **the site claims no ranges and no served sets anywhere**.
   A range change is not an input the site consumes.
2. **Coverage is bidirectional and fail-closed** (`assemble_docs_site.py:352-379`): an unmapped
   token refuses `stamp_unmapped_token`; an unused map key refuses `stamp_unused_key` — a new
   standard cannot silently lack a card, a removed one cannot leave a dead token.
3. **The stamped deep links are verified** (`verify_tree`, `assemble_docs_site.py:530-579`):
   every `docs/…` link on the *stamped* copy must resolve in the assembled tree, plus a
   delimiter-class residue sweep — and the whole assembly runs in CI on every PR and main push
   (`.github/workflows/docs.yml`).
4. **Multi-serving stages automatically:** the docs tree globs every non-dev corpus version's
   prose and machine bytes (`standards_manifest()` at `assemble_docs_site.py:157-183`;
   `copy_standards_resources`), so preview 0.1.1 + 0.2.0 both render with no per-version work.
5. **The ranges' actual consumer is machine-rendered and CI-gated:** the compatibility matrix
   is a pure function of committed state (CON-12, invariants.md:552), rendered by
   `standards matrix` and gated by `matrix --check` (`Makefile:36`, in the `gates` lane).
   PR #275 carries the regenerated matrix — that is the whole range-change doc motion.
6. **The demonstrated control:** PR #275's file list touches **zero `website/` bytes and zero
   assembler bytes**, and its **Build Docs lane is SUCCESS** (10 pass / 0 fail; Publish Docs
   skipped — main-only, by design). The first range change has already flowed through the
   website machinery, in CI, with no website work.

VR-50's review note ("the consumer list omits the website stamps surface") is discharged
structurally: the website is a *version* consumer, not a *range* consumer, and CON-13's
coverage makes that class of drift unrepresentable.

**Verdict: CLOSE** — the closure comment lands on #233 at #275's merge, citing this section
(the D2/D8 pattern: closed at the landing, the merge as evidence). Nothing to build. If the
owner prefers, the row may close now on the PR-lane evidence (§2.6) with the merge as
confirmation — either is defensible; the landing-timed closure is the register's precedent.

### D5 — VR-40 "why" query · **OPEN-NOW, CONDITIONAL on the owner's explicit call** — the one designed slice (§3)

The trigger's two arms ("first user confusion report naming an unexpected resolution, or the
SDK docs request") are un-fired on the record. The deferral-row contract
(`.claude/deep-review/README.md`) explicitly legitimizes **owner-fired triggers**: "the owner's
explicit call (in its strong form, on a named channel) — an owner-fired trigger is legitimate
and must be disclosed as such (the #199 precedent)." The owner's "continue with #233" opens the
register pass but is *not* by itself a strong-form call for this row — so the slice below is
designed ship-ready and the fork is surfaced for the owner's design-review call. This record
recommends firing it (reasons in §3.2); the counter-case is stated there too.

### D6 — pre-adoption migration notes · **STAY-DORMANT** (trigger restated; recommended against even on owner call)

SM-5's clock **self-anchors at `migration_notes.py`'s own arrival** — "every release the tree
carried before SM-5's adoption is grandfathered by mechanism, never by a hand-maintained date
(design record D6 — SM-5 is from adoption)" (`src/benchweave/standards/migration_notes.py`,
module docstring; `_MODULE_RELATIVE` anchor with the do-not-repoint rule). Notes for
pre-adoption releases would be gate-inert prose: no refusal can reference them. The trigger's
own phrasing — "a support request pinned to a pre-adoption version **hitting a refusal**" — is
structurally un-fireable for grandfathered releases, because the gate judges nothing before the
anchor; the trigger's real form is "a human asks." No one has asked. The compatibility matrix
already renders per-version rows for every release. Writing historical notes no gate reads and
no consumer requested is busywork the honest-negative principle exists to prevent.
**Verdict: DON'T-BUILD.** Trigger restated verbatim. (Owner-call possible; recommended against.)

### D7 — interface multi-version serving · **STAY-DORMANT** (trigger restated)

`standards/interface/` serves exactly 0.1.0 (range `>=0.1.0,<0.2.0`, retired identifiers 1.1.0 /
1.1.1 held dead); the open PRs (#275, #277) are plugin-ui/preview and touch no interface
bytes; no interface bump is in flight and no live external clients are named. The carrier text
stands: VR-37 named refusals meet the API-client story until a bump with live clients exists.
**Verdict: DON'T-BUILD.** Trigger restated verbatim: *the first interface bump with live
external clients.*

---

## 3. The conditional slice — `standards why` (D5), ship-ready design

### 3.1 Root cause of the gap (established, not assumed)

`resolve_package` (`src/benchweave/standards/dependency.py:1334`) selects each standard's
locked version through a four-rung ladder, in fixed order:

| Rung | Branch | Site |
|---|---|---|
| `dev-opt-in` | content-addressed dev pin; never auto-selected | `dependency.py:1394-1408` |
| `precise-override` | `upgrade --precise` target; classified, interval-checked | `dependency.py:1409-1421` |
| `prior-retained` | prior non-dev pin that still satisfies the interval and classifies | `dependency.py:1420-1438` |
| `auto-highest-served` | `max(served ∩ interval)`; never yanked, never pre-release | `dependency.py:1439-1456` |

**Which rung fired is computed and discarded.** The lock persists only `stage` ∈
{released, dev} (`LOCK_V2_SCHEMA`, `dependency.py:173-192`) — the rung is not persisted and not
rendered anywhere. The one surface that could force the question, `pin --locked`, is a byte
comparison and refuses all-or-nothing: "`plugin_lock_drift` … (hand-edited constraint, forged
digest, stale lock, or a non-canonical serialization of identical values)"
(`dependency.py:1806-1812`) — four hypotheses, no ability to name the diverging row, because
byte equality carries no per-row story.

### 3.2 Why fire the trigger (and the counter-case)

For: (a) the project is multi-contributor since 2026-09-23 and the ladder is subtle —
prior-stickiness, yank exclusion, precise override and dev opt-in interact;
(b) `plugin_lock_drift` is a concrete in-tree feeder that today cannot name the diverging row;
(c) the mechanism is a pure re-derivation — read-only, no writes, no standards bytes, no
on-disk format; (d) the data is already implicit in the loop; the slice makes it explicit
rather than inventing architecture.

Counter-case (honest): no confusion report exists; the trigger's arms are un-fired; building
ahead of demand is what the register disciplines. If the owner weighs the counter-case higher,
D5 stays dormant with its trigger restated and this section is the scoped surface waiting for
the call. **The recommendation to fire rests on (b)** — an existing surface whose refusal is
demonstrably less informative than the tree's own data allows — not on anticipation.

### 3.3 Mechanism

**One implementation, extended — no second ladder.** The rung is recorded *where the decision
is made*: inside `resolve_package`'s existing loop, each branch that sets `resolved[standard_id]`
also sets `provenance[standard_id]` (a small frozen dataclass or enum + the inputs it judged:
interval text, prior version where relevant, candidate set for auto-selection). `Resolution`
gains a `provenance` field alongside `document`/`raw`/`warnings`. The migration-notes module's
own drift-bait lesson ("two parsers for one format would be drift bait",
`migration_notes.py` docstring) is the design rule here: an explainer implemented outside the
loop would be a second ladder that can diverge; this slice makes divergence unrepresentable by
construction.

**`why_lines(root, package) -> list[str]`** renders, reusing the existing public helpers
(`served_versions`, `classify_pin`, `load_prior_lock`) and the existing render idiom
(`list_lines`, `dependency.py:1584`; `pin_lock`'s per-row `id@version` lines):

1. per constrained standard: the authored interval, the prior locked row, the rung that fired,
   the selected version; for `auto-highest-served`, the candidate set (`served ∩ interval`)
   with exclusions named (yanked / pre-release / out-of-range);
2. the drift section: prior lock vs current resolution, **naming each diverging row** — the
   per-row story `plugin_lock_drift` cannot produce;
3. the cross-constraint pairwise verdict (the existing `_cross_violations` result, rendered).

**CLI:** `python -m benchweave.standards why [--package <dir>]` — read-only, the `pin --locked`
verify-only precedent (`dependency.py:1766-1781`). Dev rows render their label@sha and refuse
`dev_head_unresolvable:` exactly as resolution does — the why surface **reuses** refusals, it
never catches and paraphrases them (a softer refusal than the mechanism's would be a lying
surface).

### 3.4 Minimal first increment — and the deferrals

**In:** the provenance field + in-loop recording; `why_lines`; the `why` subcommand; the
discrimination and no-lie tests; one bullet in `docs/development.md`'s command-family list
(the CLI→docs drift obligation's standards-CLI home, `docs/development.md:92-105`).

**Deferred (each with home + reopen trigger, per the deferral-row contract; homes are this
record's table per amended rule 3 — no new tracker rows):**

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| S-1 | SDK-side why (the SDK resolves against its own lock; a mirror surface) | this record §3.4 | the first SDK consumer question naming a resolution |
| S-2 | Persisting selection provenance in the lock document | this record §3.4 | a consumer that must explain a lock offline at admission time (the rung stays derivable by the pure function until then) |
| S-3 | Machine-readable output shape (`--json`) | this record §3.4 | a tooling consumer asks for it |

Explicitly out: admission-side refusal explanation (not VR-40; not this row), and any change to
`plugin_lock_drift`'s own message (the why command is the explanation surface; the refusal
gains a "run `standards why`" hint only if the reviewer wants it — offered, not assumed).

### 3.5 Invariant and drift impacts

- **No CTL/STO/CON/REG invariant changes or amendments.** CON-12 (matrix) and CON-13 (website
  stamps) untouched. The lock document is **unchanged** — no persisted format, so no Tier-3
  persisted-format rule fires; provenance is render-time by design (deferral S-2 names the
  alternative and its trigger).
- **Surfaces that move:** `src/benchweave/standards/dependency.py`,
  `src/benchweave/standards/__main__.py`, `tests/standards/` (new test module or
  `test_dependency.py` additions), `docs/development.md`, this record. SDK repo: none. Website:
  none (the site stages `docs/development.md` automatically at assembly).
- **CI cost: zero new lanes.** Fast lane per commit + full battery before push (#247); no
  standards tripwires fire — the diff moves no `standards/` bytes, no lock data, no version
  strings (the surface *prints* versions; it moves none).

### 3.6 Tier call and the Step-1 keyword scan (#254)

**Tier 2** — path rule: `src/` + `tests/` + docs, matching no Tier-3 path (no `standards/`
corpus bytes, no `src/benchweave/contracts/`, no state/registry/fixtures paths, no dependency
re-pin, no SDK pointer). The standards-governor mandate does not dispatch: no diff touching
`standards/`, plugin contract locks, the SDK vendored tree, or standard-version strings.

**Keyword scan over the expected operative diff** (the code, tests and doc bullet above — the
whole expected diff minus this record, stated per the multi-part option in the rubric):
`threading` 0, `asyncio` 0, `subprocess` 0, `sha256` 0, `hashlib` 0, `migrate` 0, `recovery` 0,
`protection` 0. Design commitments that hold the zero: the render prints no digests (the lock
carries them; why explains *selection*, not integrity) and adds no process/git calls (it reuses
`resolve_package`'s own). **Disclosure:** this record's §3.6 text itself carries all eight
words once each — the by-construction shape the rubric's self-fire clause names for its own
text; if the record rides the PR, the PR-level diff text carries the words from this section
alone, and the review re-derives per #254. The builder re-runs the scan on the real operative
diff; **any nonzero operative hit flips the slice to Tier 3 first-match-wins**, disclosed at
build, not negotiated after.

### 3.7 Acceptance — pre-committed, with kill directions

Stated before any implementation output exists. Deterministic surface: no timing, no sampling
randomness; the sample sizes below are fixed fixture counts.

- **M1 — rung discrimination (the operative proof).** Planted fixtures covering each of the
  four rungs, ≥2 per rung (n=8 minimum). `standards why` must name the correct rung for
  8/8. **KILL:** any misnamed rung — an explainer that misnames the selection is a lying
  surface; the slice does not ship on a partial score.
- **M2 — no-lie equality (the control fluff cannot pass).** For every lock fixture the
  existing dependency corpus constructs (`tests/standards/test_dependency.py`, 59 tests at
  design time — the denominator), why's per-standard version map must equal
  `resolve_package`'s resolved map exactly. **KILL:** any divergence. **Underpowered rule:**
  if fewer than four distinct rung instances occur across that corpus, M2 is declared
  underpowered and M1 is the operative equality proof — recorded as such, never counted as a
  pass.
- **M3 — read-only.** `why` on a clean tree leaves `git status --porcelain` empty, before and
  after, pinned by test. **KILL:** any write.
- **RED control.** Neutralize the in-loop provenance recording (comment out the assignments)
  → M1 must FAIL (wrong rung or refusal). Watched RED before GREEN; the tests test the
  mechanism, not the fixture.
- **Design-level kill.** If making the rung explicit cannot be done inside `resolve_package`'s
  loop, and the builder finds itself re-deriving the rung from outside (a second ladder), the
  design is falsified — kill the slice rather than patch it with a parity test; a second
  implementation is the defect the migration-notes drift-bait lesson names.

### 3.8 Top risks

| Risk | Falsifier / mitigation |
|---|---|
| A second ladder sneaks in via the render | §3.7 design-level kill; reviewer checks the render only reads `provenance`, never re-derives |
| The why surface softens a mechanism refusal (dev unresolvable, cross violations) | Design rule: reuse refusals verbatim; M1's dev-rung fixtures must propagate `dev_head_unresolvable:` unchanged |
| Scope creep into admission-side explanation or drift-message edits | §3.4 names both OUT; reviewer holds the line |
| The owner does not fire the fork | Not a risk to the register: D5 stays dormant with its trigger restated and this section as the scoped surface — a no-slice outcome is acceptable per the loop |

---

## 4. Register hygiene (the pass's own output)

| Row | Disposition | Carrier |
|---|---|---|
| D1 | STAY-DORMANT, trigger restated | #233 comment citing §2 |
| D3 | STAY-DORMANT, trigger restated, designed-whole reading rejected | #233 comment citing §2 |
| D4 | **CLOSE at #275's landing** (or now on PR-lane evidence, owner's preference) | #233 comment citing §2's six-point evidence |
| D5 | OPEN-NOW conditional — owner fork; slice designed §3 | owner's design-review call |
| D6 | STAY-DORMANT, trigger restated | #233 comment citing §2 |
| D7 | STAY-DORMANT, trigger restated | #233 comment citing §2 |

One-follow-on-issue-per-PR rule: this pass opens **no new tracker issue**. If the D5 slice
ships, its deferrals (S-1..S-3) live in this record's §3.4 table — the amended rule-3 home
(deferrals live in design-record tables, not tracker rows; council 2026-09-20). The register
comment on #233 records the dispositions; the issue stays open as the home for the dormant
rows.

## 5. Owner forks surfaced at design review

1. **D5 — fire the trigger or not** (the slice ships on the owner's explicit call, disclosed
   as owner-fired per the #199 precedent). Recommendation: fire (§3.2).
2. **D4 — closure timing**: at #275's merge (register precedent) or now on the PR-lane CI
   evidence. Recommendation: at merge.
3. **D6 — historical notes on owner call**: possible, recommended against (§2).

## 6. What could not be resolved here

Nothing blocks the dispositions. The one judgement this record will not make unilaterally is
fork 1 — by the deferral contract's own rule, an owner-fired trigger must actually be the
owner's, in its strong form.
