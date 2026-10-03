# Issue #231 follow-ons — 2026-10-03 reconcile of the 2026-09-26 park record

**Date:** 2026-10-03 · **Issue:** [#231](https://github.com/madeinoz67/benchweave/issues/231)
**Adopts:** `.claude/deep-review/2026-09-26-issue231-follow-ons-park-design.md` (on `main`
since `67a647c`, PR #232). That record stays the authority for the mechanism sketches
(its §2.2/§3.2/§4.1), the maintainer forks (§6) and the pre-committed reopening
acceptance rules (§7). This record reconciles its per-row dispositions against today's
tree, carries a dated errata for what moved, and returns the verdict the reconciled
evidence supports.
**Tree:** `origin/main` @ `c183db4` — 512 commits after the park record's `9ad0301`.
**Verdict: PARK stands for all three rows — no BUILD slice in this increment.**
Every reopen tripwire the record attached is unfired at `c183db4`. One of Row 1's two
independent bars (the "#203 dependency train" gate) is LIFTED — that train completed —
and is recorded as errata E1; it does not fire the caller trigger, so the disposition is
unchanged.

**Minimal increment shipped here: the reconcile itself** — one docs commit, this record.
Everything else defers per §4, each row with carrier and reopen trigger.

---

## 0. Grounding — re-derived at `c183db4`, nothing inherited

| Claim (each feeds a row disposition) | Command | Result |
|---|---|---|
| OTDP corpus byte-frozen since the park | `git diff --stat 9ad0301..origin/main -- standards/otdp/` | empty — no 0.2.3 dir; the pinned catalog schema at 0.2.2 is byte-identical, so the M06/M13 quantity substrate still does not exist |
| Publish path frozen | diff over `src/benchweave/content/dataset_services.py`, `src/benchweave/registry/otdp_contracts.py`, `tests/unit/test_dataset_services.py` | empty — the park's §2.2/§3.2 sketches and their line cites remain valid |
| Demo lattice frozen | diff over `fixtures/execution/`, `scripts/registry/build_fixtures.py`, `tests/contract/test_registry_fixtures.py` | empty — the soft-arm chain and the builder-parity posture are as recorded |
| Signing keys still absent | `git ls-tree origin/main fixtures/registry/keys/` | `README.md`, `main.pub.pem`, `originb.pub.pem` only; CI materialises the private keys from repo secrets (`ci.yml:24-32`) — the Row 7 blocker holds mechanically |
| Dataset-consumer set frozen | `git grep -l 'DatasetController\|dataset_publish'` over `src/` + `tests/`, both refs | the same 8 files at `9ad0301` and `c183db4` — no new consumer appeared |
| Guide boundary sentence current | grep for the M05 sentence | `docs/device-developer-guide.md:553` — "The remaining class-semantic checks of the corpus's full M01–M15 family stay author-side obligations. … The gateway does not verify them for you." (line moved from :394 in the guide rewrite; text intact) |
| Publishing path live, first record non-class | registry repo tree census | exactly one record: `records/submissions/madeinoz67/dps150/0.1.0/` + `records/lifecycle/madeinoz67/dps150/0.1.0/1-publish.json` — identify/read, non-class |
| #203 train complete | issue states | #203 CLOSED; slices #215–#221 all CLOSED |
| No tracker trigger | open-issue sweep (60 rows) + vocabulary sweep (`quantity\|lattice\|fixture\|catalog\|manifest`) | #92–#95 still open proposals (unadmitted); nothing asks for class-semantic M-checks, acquisition-scoped dataset ids, or a runnable class fixture |
| Pre-flight | open PRs #371/#372 (G2a/G2b UI fold rows) file lists | UI/interfaces surfaces only (one carries `docs/internal/invariants.md` rows); no overlap with the three rows' surfaces |

Read alongside: `docs/internal/review-rubric.md` (tier rules; §8 below),
`docs/internal/drift-and-obligations.md` (no obligation fires for a
`.claude/deep-review/` docs-only diff), `docs/internal/invariants.md` (§7 below), and
the #146 record remains the governing precedent set. `docs/smart-test-gateway-decisions.md`
is not re-opened: this reconcile proposes no decision change (the park record's §0
already grounded A01–A14; nothing here re-proposes one).

## 1. What moved since `9ad0301` (512 commits)

- **The gateway UI train landed**: G1e React cutover (#301, closed); G2 read-only UI
  (#303, in flight — G2b merged as #368 `13faaec`, G2c live-events bridge as #370
  `a311e92`; fold-row PRs #371/#372 open).
- **The registry publishing lane went production**: slices 1–3 (#223–#225) closed — the
  standalone registry repo exists, `standards/registry/0.1.2` is in the corpus tree
  (the `standards/` diff since `9ad0301` is 23 files / +3885−178, all registry-corpus
  and manifest rows; OTDP untouched), `scripts/registry/sign_release.py` landed;
  slices 4–6 (#226–#228) remain open.
- **The #203 standards-dependency train completed** (all seven slices #215–#221 closed):
  multi-version serving, resolver surface, per-pin gateway admission, dev-head pinning,
  soft roll-forward, execution per-document pin, zero-literal end state.
- **The device-developer guide was rewritten** (+380 lines; the M-boundary paragraph
  survives at `:553`).
- **`plugins/esp32_controller/` appeared — as a `.gitkeep` placeholder only** (the
  ADC-class plugin named by #203/#223 has tree presence, no code, no descriptor).
- **The dataset/invoke lane itself did not move**: publish path, contracts module,
  dataset tests, execution fixtures, builder, parity tests, lattice — all byte-identical
  (§0).

## 2. Per-row re-verification

### 2.1 Row 1 — class-semantic M-checks at publish (M05–M09, M12, M13): PARK stands

- **Class-data half (M06/M13).** The recorded trigger — "the first profile whose
  required-quantity or class-output validation is wanted at the gateway" — is unfired:
  the only admitted real plugin remains DPS-150 (identify/read; the registry's single
  production record is that same plugin at 0.1.0, non-class); the invoke-capable in-tree
  plugins remain the two sims; the proposals #92–#95 remain unadmitted; and the
  substrate is still absent — the OTDP corpus is byte-frozen at 0.2.2, whose closed
  catalog schema defines each profile as `{id, title, channel_roles, required_actions,
  optional_actions}` with no quantities (park §2.3, verified still true). What changed
  is the second, independent bar: the park parked this half "twice over" —
  caller-gated AND "structurally, behind #203's dependency train for any catalog
  revision". #203 is now complete (E1), so a catalog revision would ride landed
  multi-version-serving machinery under the standing standards rule, not a pending
  train. The half is single-gated now; the gate is still closed.
- **Manifest-internal subset (M05/M08/M09 internal halves).** The sharpened fire
  condition — "a dataset consumer that needs M05/M08/M09 coherence as a gateway
  guarantee rather than an author obligation," carrier "a UI/reporting surface over
  admitted manifests" — is unfired, and its nearest carrier materialized and can be
  checked: the G2b read views (`src/benchweave/interfaces/ui_read.py`, merged
  `13faaec`) render benches/devices/documents/evidence/requests/runs and contain zero
  references to dataset manifests; the single `dataset` token in the UI tree
  (`ui_presentation.py:254`) is the plugin-ui presentation page kind from the plots
  family (`kind == "dataset"` over descriptor-authored pages) — a different lane from
  the dataset-publish path. The consumer-set freeze (§0) is the structural
  corroboration: nothing outside the 8-file publish-lane set reads `DatasetController`
  or `dataset_publish`. Displaying is not verification — no consumer *needs* the
  coherence guarantee yet.

### 2.2 Row 5 — acquisition-scoped dataset identity: PARK stands

Recorded trigger: "a profile whose fetch semantics need acquisition dedup." Unfired at
`c183db4`: no acquisition-lifecycle fetch family exists in any admitted or published
profile (DPS-150 at 0.1.0 is the registry's whole census — non-class, no fetch family);
the oscilloscope-class carrier (#92) is still an open proposal; the mint remains
per-operation (`mint_dataset_id`, `dataset_services.py:169-186`, file byte-identical);
and the corpus clause that makes the posture legal (`extension-contract.md:64`,
"derived from the current operation/acquisition", repeated fetch "may return") is
byte-frozen. The park's load-bearing observation — that dedup across operations is
meaningless until a profile defines what a divergent re-fetch MEANS, and building the
id scheme ahead of that is inventing policy — is untouched by anything in the 512
commits.

### 2.3 Row 7 — demo-lattice class fixture: PARK stands

Recorded trigger: "the first registry-demo need or the first real class plugin
admission." Unfired, now with production-grade evidence: the publishing path the park
sketched as the dogfood venue (#223's shape) is LIVE, and its first real submission is
`dps150/0.1.0` — a non-class identify/read plugin. The tripwire was testable and did
not fire. The mechanism state is unchanged: builder, lattice, parity tests, catalogue
all byte-identical (§0); the committed demo lattice still cannot invoke (the soft-arm
chain of park §4.1 needs no re-derivation — `otdp_contracts.py` is byte-frozen); the
signing keys remain repo-secrets-only with CI materialisation at `ci.yml:24-32`, so
lattice regeneration remains impossible on a contributor machine — the second gate
holds mechanically. No demo or website need to RUN a class plugin appeared (the UI
train renders gateway state, not plugins from committed fixtures; the
standalone-web-UI analysis/reporting rows #282/#286 are open issues, not fired needs).

## 3. Dated errata against the 2026-09-26 record (2026-10-03)

The adopted record is committed history and is not edited (the deferral contract's own
clause); these rows annotate it. None changes a disposition.

- **E1 — Row 1 §2.4, second bar lifted.** The park text: M06/M13 are "bump-gated even
  if a caller appeared … structurally, behind #203's dependency train for any catalog
  revision." #203 closed with all seven slices landed: a catalog-schema revision would
  now ride the landed multi-version-serving + per-pin admission machinery as a normal
  bump-window event under the standing standards-involvement rule (the principal's
  word as the permission gate, 2026-09-29), not a pending train. Consequence: the
  class-data half is caller-gated only. Disposition unchanged — no caller exists.
- **E2 — guide citation drift.** The park cites `docs/device-developer-guide.md:394`
  for the author-side M-boundary. The guide was rewritten; the paragraph is now at
  `:553`, text verified intact. Citation drift only.
- **E3 — Row 7 §4.3 surroundings hardened, blocker unchanged.** "No workflow
  regenerates-and-commits the lattice" re-checked and still true. The registry lane
  ADDED `scripts/registry/sign_release.py` (release-record signing — a different key
  family from the fixture lattice); it is the closest new neighbour to the fork-3
  clearance options and changes none of them.
- **E4 — trigger-landscape churn.** The park's §0 tracker enumeration (#92–#95, #203,
  #207, #209–#210, #215–#228) is stale as a snapshot: #203 and #215–#221 closed;
  #223–#225 closed; a UI train (#282–#286, #295, #301–#305) opened and G1e/G2
  partially landed. None of the deltas fires a tripwire (§2); the enumeration is
  refreshed here rather than edited there.
- **E5 — `plugins/esp32_controller/` placeholder.** The park named "the external ADC
  plugin named in #203/#223" as a serial scalar board, not an invoke-class plugin. It
  now has tree presence as a `.gitkeep`-only directory — still no descriptor, no
  capabilities, no admission. Not a trigger event; recorded so the next reconcile does
  not mistake the directory for a plugin.
- **E6 — "no open PRs" no longer describes the tree.** #371/#372 (UI fold rows) and
  SDK #98 (I2b) are open; their file lists were checked (§0) and none touches the
  three rows' surfaces. Pre-flight recorded per the standing dispatch rule.

## 4. Deferral rows (the #99 contract vocabulary: carrier + reopen trigger)

| Row | Disposition | Carrier | Reopen trigger (observable event) | Nearest plausible carrier today |
|---|---|---|---|---|
| 1 — class-data half (M06/M13) | PARK (trigger unfired; E1 lifts the train bar) | #231 + this record + park §2.2/§2.3 | An invoke-capable class plugin's admission/publication whose conformance story requires gateway-side quantity/class-output verification, or a corpus train that adds quantity data to the catalog schema | #92/#94 maturing; a future OTDP bump touching the catalog |
| 1 — manifest-internal subset (M05/M08/M09) | PARK (trigger unfired; carrier checked, §2.1) | #231 + this record + park §2.3 | A dataset consumer that needs manifest-internal coherence as a gateway guarantee rather than an author obligation | The G2 read views (landed, verified not to consume dataset manifests); a future reporting surface over admitted manifests |
| 5 — acquisition-scoped dataset identity | PARK (trigger unfired) | #231 + this record + park §3.2 | A profile with acquisition-lifecycle fetch semantics whose procedures re-fetch one acquisition across steps | #92 admission; any published profile declaring a fetch family |
| 7 — demo-lattice class fixture | PARK (trigger unfired; key blocker holds) | #231 + this record + park §4 | A real class plugin submission through the publishing path, or a demo that must RUN a class plugin from committed fixtures | The live publishing path's next submission; a website/demo run |

## 5. Maintainer forks — carried forward, one note

The three forks of park §6 (Row 1 quantity substrate; Row 5 divergent-refetch
semantics; Row 7 key clearance) are unchanged and remain "decide when a trigger fires,
not now." E1 amends fork 1's phrasing only: "corpus revision … riding #203's train"
resolves to "a normal bump-window event on the landed multi-version-serving machinery,
gated by the principal's word under the standing standards-involvement rule."

## 6. Acceptance rules

**(a) The reopening slices stay bound by the park record's §7 rules, unchanged** —
they were pre-committed on 2026-09-26, before any implementation number existed, and a
reconcile is not a re-commit. Binding summary, not a replacement: every new M-check
ships as a RED-revertible publish-path control in the `tests/unit/test_dataset_services.py`
battery shape with the check named in the refusal message, and the class-data half
additionally pins that the quantity substrate is READ from the pinned catalog (mutate
the catalog's quantity row, the check's verdict flips); Row 5 ships both arms — two
dispatches carrying the SAME issued acquisition id publish under ONE dataset id (the
second byte-identical publish returns the admitted manifest, zero new evidence rows),
and the divergent-refetch outcome is pinned in both directions to whatever the firing
profile's text says, with the `ds:{operation_id}` pin moved in the same change, never
after; Row 7 makes the COMMITTED lattice the E2E substrate (real activation path,
`configure → fetch → sample`, no dev publish, no test-local bundle), with the
builder-emission revert reddening the run to UNSUPPORTED at I1 and the
catalogue/digest lockstep moving in the same commit. Common kill direction: a slice
that cannot express its control through the real mechanisms (the committed lattice,
the pinned catalog, the publish path) reports itself underpowered and stops — no
hand-built substitute counts.

**(b) This reconcile's own pre-committed verification rule** (mechanical; stated before
the observations were gathered — each §0 row is its execution):

- **SHIP as PARK** if, at the reconcile ref `c183db4`, ALL of: the four freeze diffs
  (OTDP corpus; publish path; demo lattice + builder + parity; consumer set) are empty;
  the registry census is exactly one non-class record; #203 and #215–#221 read closed;
  the guide paragraph greps at its new line with the boundary sentence intact.
  *All held at `c183db4` — this record ships.*
- **KILL (a row un-parks; this record is wrong)** if ANY of: the `standards/otdp/`
  diff is non-empty; the registry census contains an invoke-class record; an open
  issue asks for one of the three rows by mechanism; the consumer set grows beyond the
  8 files; the committed keys directory gains a private key.
- **UNDERPOWERED, not conclusive**: if any verification command cannot run (registry
  repo unreachable, tracker API down), the affected row's disposition is reported
  UNVERIFIED on the issue — never inherited as PARK.

**(c) Push tripwire (standing 2026-09-29 rule):** `git diff origin/main...HEAD --
standards/` is empty and no version strings are touched — reported at push; this
record's diff is one new `.md` file under `.claude/deep-review/`.

## 7. Invariant and drift impacts

None — same shape as the park record's §9. No code, corpus, fixture, contract-lock or
SDK bytes move; no invariant gains an amendment; no drift obligation fires for a
`.claude/deep-review/` docs-only addition (the guide/operator/UI surfaces named in
`drift-and-obligations.md` are untouched). CI cost: zero (no pipeline surface moves).

## 8. Review tier and the Step-1 keyword scan (#254)

- Path rule: the expected diff is one new `*.md` file under `.claude/deep-review/` →
  **Tier 1** (docs-only; no Tier-3 path matches — no `src/`, no `standards/`, no
  fixture lattice, no submodule pointer, no dependency change).
- Keyword scan over the whole expected diff text (this file): each of the eight
  Step-1 keywords named in `docs/internal/review-rubric.md` scores **0**. The counts
  are re-measured at commit time and recorded in the commit message (which is not
  diff text). This report deliberately does not spell the tokens: quoting them inside
  the record would place each token once into the diff and self-fire the very rule the
  scan reports on, making the stated counts false — the rubric's self-fire clause,
  applied in the direction that keeps the report truthful. The record names
  digest-pinned lattices and signing keys without carrying the tokens; the review
  re-derives the scan independently, and any non-zero count self-escalates the tier
  per the rubric's interplay rule.
- Standards-governor (#69): not dispatched — the diff touches no `standards/` bytes,
  no plugin contract locks, no SDK vendored tree, no standard-version strings.

## 9. Risks of standing pat (carried forward, carriers updated)

| Risk | Tripwire / mitigation |
|---|---|
| The author-side M-boundary is silently relied on by a future dataset consumer | The guide's boundary sentence (now `:553`) is the contract; §4's internal-subset trigger watches for the first consumer that needs verification, not display |
| `ds:{operation_id}` becomes load-bearing in external tooling, making the acquisition-scoped change breaking later | The corpus never promised scheme stability to adapters; the guide documents the mint as host-internal; the correlation channel is `context.dataset_id`, not the string's shape |
| The demo lattice's inability to invoke is rediscovered expensively | `otdp_contracts.py`'s module docstring still states it verbatim (file byte-frozen); park §4.1 + §2.3 here carry the full chain with citations |
| Row 7's builder change lands without regeneration (builder and lattice diverge) | The builder/lattice byte-freeze makes divergence impossible without intent; when the row reopens, §6(a)'s Row-7 rule requires the lockstep in one commit, and builder parity reddens in CI where the keys materialise |
| A reconcile ossifies into "never rechecked" | §6(b)'s kill direction is the counter: any listed observation flipping state forces the row off PARK; the registry census is one command |

---

*Provenance: grounded against `origin/main` @ `c183db4` (2026-10-03); adopts the
2026-09-26 record grounded at `9ad0301`; the OTDP corpus `standards/otdp/0.2.2` is
byte-frozen between the two refs. No client, bench, or person identifiers; plugin,
fixture and publisher names are the repository's own public in-tree names and public
repo namespace.*
