# Deferral-term definitions and the deferral-row contract (issue #99)

**Date:** 2026-09-26 · **Issue:** [#99](https://github.com/madeinoz67/benchweave/issues/99)
**Tree:** `main` @ `67a647c` (origin/main one ahead: `97024b4`, a changelog regen only —
no rival work; open PRs gateway #234 / SDK #58, both `feat/issue215-multi-version-serving`,
surfaces disjoint from this slice).
**Verdict: BUILD — define-only first slice.** Two defined terms + a column contract in the
deep-review README, a one-line reference replacing the inline parentheticals in both
copies of the increment skill, SDK re-sync, and no mechanical gate (a named deferral, §8
row 1). No corpus, contract, fixture, or version bytes move — the no-standards-bump
directive is honored trivially.

This record is committed before any review applies the contract, so the acceptance rule
in §7 is provably pre-committed.

---

## 0. Grounding — what was read, not assumed

- `.claude/skills/increment/SKILL.md` (main) — full text, gortex-served then
  line-verified by targeted read; step 7 is lines 92–107, the clause under repair is
  lines 94–100.
- `~/Documents/src/benchweave-sdk/.claude/skills/increment/SKILL.md` (SDK standalone
  checkout; the main repo's `packages/sdk` submodule stays deinitialized per the standing
  directive) — full text; its step 7 carries the same clause at lines 88–91.
- `.claude/deep-review/README.md` (main, 2165 bytes) and the SDK repo's own
  `.claude/deep-review/README.md` (2.0K, an SDK-adapted mirror of the same shape:
  triage rule + measuring section).
- A census of every committed usage of "reopen trigger" tree-wide (git grep — see the
  tooling note below): **16 design records + the skill + `docs/internal/drift-and-obligations.md`
  (line 163) + two implementation-planning docs.** The deferral-table column shapes found:

  | Record | Shape | Verdict under the draft contract (§2) |
  |---|---|---|
  | #146 (09-25) §6 | `\| # \| Deferred \| Carrier \| Reopen trigger \|`, 10 rows | Conforms (canonical) |
  | #79, #102, #43, #159, #194, #199 | same 4-col shape | Conform |
  | #147-inc3, #167, #176 | `\| # \| Deferred \| Home \| Reopen trigger \|` | Conform (label variant) |
  | #133 (09-21) §9 | 3-col: `\| # \| Deferred \| Reopen trigger \|` | Conforms **via preamble** — its intro sentence carries "their reopen triggers in-row (documentation deferrals; no scheduled carrier)" |
  | #156 (09-23) | `\| # \| Deferred \| Why \| Reopen trigger \|` | **Non-conforming on home** — ids D1–D3, exemplary triggers ("Repeated `run_worker completion close failed` lines in an operator's gateway log"), a rationale column, and no home stated anywhere in the record (verified by grep) |
  | #67 (09-21) | 2-col: `\| Deferral \| Reopen trigger \|` | **Non-conforming on identifier and home** |
  | devstage (09-23), website-stamps (09-24) | prose lists with bold inline "Reopen trigger:" | Acceptable renderings when each item carries the four semantics (devstage's do) |

- `docs/internal/invariants.md` (full), `docs/internal/drift-and-obligations.md` (full),
  `docs/smart-test-gateway-decisions.md` (targeted: zero occurrences of "deferral" — no
  A-numbered decision governs this surface; A04/A06/A07 content absorbed via
  invariants.md and CLAUDE.md).
- `.claude/deep-review/2026-09-25-issue146-invoke-dataset-design.md` §6 (lines 551–564)
  and `2026-09-26-issue231-follow-ons-park-design.md` in full — the two grounding tables
  the issue names. **Premise correction to the dispatch brief:** the #231 record is no
  longer untracked — it landed at `67a647c` via PR #232; it was read from the tree either
  way.
- The rule's own precedent chain: `2026-09-19-issue71-skill-role-design.md` §9
  (lines 382–416 — the original "amended rule 3 (merge commit `a6d4b76`)" text, which
  already used both terms informally), and the vault's 2026-09-20 council decision that
  amended the rule (deferrals live in design-record tables, not tracker rows).

**Tooling note (durable):** gortex's text search does not index `.claude/` paths — a
search for "reopen trigger" returned exactly one hit (`drift-and-obligations.md:163`)
against 40+ real occurrences. The census therefore ran via `git grep` (the git-family
evidence path the skill itself sanctions for unindexed paths). Recorded in the session's
memory proposal.

---

## 1. Root cause — the defect, precisely

The clause under repair, main copy, `.claude/skills/increment/SKILL.md` lines 94–100
(SDK copy: same words at lines 88–91, attributing "(main #69, amended 2026-09-20 by the
backlog triage council)"):

> **every deferral must cite its home (reviewer-enforced; no mechanical gate yet)**
> (#69, amended 2026-09-20 by the backlog triage council): either (a) an open issue,
> created at PR-open time if absent, whose body names its carrier increment and its
> reopen trigger (the condition that justifies reopening), or (b) a row in the design
> record's deferral table that records that same reopen trigger. …

Two terms carry the gate's entire weight and neither is defined:

1. **"reopen trigger"** — the parenthetical "(the condition that justifies reopening)"
   restates the word "condition"; it does not say what makes a trigger well-formed. The
   in-tree range is consequently wide: exemplary observable triggers (#156 D3's repeated
   log line; #146 row 10's "a measured manifest-bloat trace the routed bytes cannot
   refuse"; #133 D1's "a second retrospective run where hand-harvesting proves
   error-prone, or any acceptance-check-2 mismatch attributable to transcription") sit
   next to judgement-shaped ones (#146 row 5 as written: "a profile whose fetch semantics
   need acquisition-dedup" — "need" is the deferrer's assessment, not an inspectable
   event; the #231 record §3.3 later sharpened exactly this row into a decidable
   procedure shape).
2. **"deferral table row"** — the row has no required shape. The census found six header
   variants, two prose-list forms, one table missing the home entirely (#156) and one
   missing identifier and home (#67). A reviewer enforcing the gate today applies a
   private notion of the row's requirements — which is precisely the
   continued-judgement-dependence the project's own doctrine refuses for every other
   gate (the reviewer-enforced marker is accepted for now, but the *terms* the reviewer
   applies must not be undefined).

**A third defect the definitions must untangle:** "carrier" is used for two different
concepts in-tree. The skill's "its **carrier increment**" means the *future* increment
that would carry the deferred work; seven records' "Carrier" *column* holds the
deferral's *home* (follow-on issue vs documentation here). The #231 §5 table's "Nearest
plausible carrier" uses the skill's sense (the future train). The contract fixes the
vocabulary going forward without renaming any committed bytes.

---

## 2. The mechanism — drafted text, ready to lift

### 2.1 New section for `.claude/deep-review/README.md` (main; authoritative)

Insert after the triage-rule section, before "Measuring on a real bench":

```markdown
## The deferral-row contract (issue #99)

The `increment` skill's Land step requires every deferral to cite its home and carry a
reopen trigger. Both terms are defined here; the skill references this section and does
not restate it.

**Reopen trigger — well-formed when:** it names an observable event (or a decidable
state) on a surface a third party can inspect, so a GO/CLOSE pass can answer "has it
fired?" by looking at that surface, not by asking the deferrer what they meant.
Observable: an admission or publication arriving; a corpus train opening; a measured
trace or repeated log line; a harness or corpus convention changing; a second run
exhibiting a named failure; the owner's explicit call on a named channel — an
owner-fired trigger is legitimate and must be disclosed as such (the #199 precedent:
"the reopen trigger fired by the owner's explicit call, not by operator demand").
Not observable, refused: "when it becomes important", "if needed", "when we have time".

Weak → strong, from the records: "a profile whose fetch semantics need acquisition
dedup" (#146 §6 row 5 as written — "need" is judgement, no inspection procedure)
sharpens to "an admitted or dogfood-published profile declaring an acquisition-lifecycle
fetch family whose procedure shape re-fetches the same acquisition across steps — a
real procedure that today would double-publish under two `ds:` ids" (#231 §3.3). The
strong form is the maturity the contract points at: it additionally names its **nearest
plausible carrier** — the arriving work or train most likely to carry the reopen (#231
§5's table shape). Naming the carrier is recommended, not required.

**Deferral table row — required semantics (four):**

1. **identifier** — a stable row id; later GO/CLOSE passes and follow-on records cite
   rows by it (#231's lineage cites "#146 rows 1, 5 and 7" — a table without ids cannot
   be cited).
2. **deferred** — the bounded thing deferred.
3. **home** — where this deferral lives under the skill's rule: "follow-on issue #N" or
   "documentation here". The column may be labelled Home or Carrier (both in active
   use); a rationale column ("Why") does not satisfy it. A home uniform across all rows
   may be carried once in a sentence above the table instead of a column (#133's
   preamble does this).
4. **reopen trigger** — well-formed per the definition above.

Extra columns are free. A prose list is an acceptable rendering when every item carries
all four semantics. The contract governs records written after it lands; committed
records are frozen history and are never retrofitted.
```

### 2.2 The skill edit (main copy, step 7, lines 94–100)

Replace the two inline parentheticals with the reference — the skill's own pointer style
(principle 5 already does "see its README for the public/private triage rule"):

- `whose body names its carrier increment and its reopen trigger (the condition that
  justifies reopening), or (b) a row in the design record's deferral table that records
  that same reopen trigger`
  → `whose body names its carrier increment and its reopen trigger, or (b) a row in the
  design record's deferral table — both terms and the row's required columns are defined
  in `.claude/deep-review/README.md` (the deferral-row contract)`

Nothing else in step 7 moves. "(reviewer-enforced; no mechanical gate yet)" stays —
it remains true this slice.

### 2.3 The SDK edits (standalone checkout)

- `.claude/skills/increment/SKILL.md` lines 88–91: the same replacement, with the
  pointer naming the authority explicitly:
  `— both terms and the row's required columns are defined in the main gateway repo's
  `.claude/deep-review/README.md` (authoritative main-side, as GOVERNANCE.md is)`.
  Precedent: the SDK copy's own "Surface-aware parallelism (main #69)" section already
  declares loop prose "live main-side only … the authoritative text is the main repo's".
- `.claude/deep-review/README.md` (SDK): a three-line pointer section after its triage
  rule — deferral rows and reopen triggers follow the main gateway repo's contract;
  authoritative main-side; no local mirror (a mirror would reintroduce the two-copies
  drift this issue exists to remove). Droppable at review without hurting the mechanism.

### 2.4 Why the definitions live in the README, not in step 7

The issue's letter says "step 7 defines both terms". Placing the definitions in the skill
and the column contract in the README would split one authority across two files that
sync imperfectly — the fourth column of the contract IS the trigger definition. One
authoritative text (README), one reference (skill), is the single-source shape the repo
already uses for the triage rule. Step 7 keeps the gate sentence; the README keeps the
semantics.

---

## 3. Placement map — which bytes move, in which repo and commit

**SDK repo first (two-repo discipline: SDK commit → push → SDK PR now):**

| File | Change |
|---|---|
| `benchweave-sdk/.claude/skills/increment/SKILL.md` | §2.3 clause replacement (lines ~88–91) |
| `benchweave-sdk/.claude/deep-review/README.md` | §2.3 pointer section (optional, droppable) |

Branch `docs/issue99-deferral-terms`, base `main` — **not** stacked on open SDK #58:
surfaces are disjoint (#58 is multi-version serving code under `src/`; this is
`.claude/`). PR body links gateway issue #99 and notes no SDK-side issue exists by
design (single issue stream).

**Main repo (one branch, `docs/issue99-deferral-terms`):**

| File | Change |
|---|---|
| `.claude/skills/increment/SKILL.md` | §2.2 clause replacement (lines 94–100) |
| `.claude/deep-review/README.md` | §2.1 contract section |
| `.claude/deep-review/2026-09-26-issue99-deferral-terms-design.md` | this record |
| `docs/internal/drift-and-obligations.md` | optional obligation row (§6; maintainer fork) |
| `packages/sdk` gitlink | pointer commit advancing to the merged SDK SHA — added only after the SDK PR merges |

**Serialization risk, named:** gateway #234 (open) will carry a pointer advance to SDK
#58's SHA; this slice's main PR also moves the gitlink — a shared surface. If #234
merges first: rebase once onto the new main and regenerate the pointer commit on top
(pointer commits never textually conflict; the rebase is the whole repair). **Local
trap:** the main checkout currently shows `M packages/sdk` (a dirty submodule working
tree that is not ours). The pointer commit must contain only the intended gitlink
advance — verify with `git diff --submodule` before committing, and never `git add -A`.

Gates after every commit, docs-only commits included (retro 2026-09-25 R2): `uv run
ruff check .`, bare `uv run mypy`, focused `uv run pytest` (nothing should move; run
the lanes anyway). Merge on the full rollup, never a filtered view.

---

## 4. Precedent — proven in-tree mechanisms extended

1. **README-section-as-authority + skill pointer**: the deep-review README's triage rule
   referenced by the skill's principle 5 — the exact shape being extended.
2. **Main-side-only authoritative text for shared prose**: the SDK skill's own
   GOVERNANCE.md declaration (§2.3) — the pattern for where the contract's authority
   lives SDK-side.
3. **The rule's own amendment chain**: #71's original in-row-trigger text → the
   2026-09-20 council amendment → this definitional tightening. Each step cited its
   predecessor; this is the third link, not new architecture.
4. **Maturity-model pointing**: #231 §5's sharpened tripwire table is the form the
   contract points at rather than mandates — the same floor-plus-aspiration shape the
   rubric uses for claim discipline.

---

## 5. Scope fork ruled: define-only, mechanical gate deferred

Ruling: **define-only first slice.** The validator is deferral row 1 (§8), with an
evidence-based trigger. The evidence:

- A retroactive validator faces 16 committed records in six header variants plus two
  prose-list forms — it would either mass false-red (and retrofitting frozen history is
  the record-laundering this repo refuses) or accept so many variants it checks nothing.
- A forward-only validator must date-gate records (filename-date parsing — brittle) and
  parse markdown tables whose legitimate variance the contract deliberately tolerates.
  The repo's own CON-12 lesson names the failure mode: a gate that reds on correct
  content "teaches its readers to ignore it".
- The contract must bake before a validator has a stable input set: converge new tables
  on the canonical form first, then codify the checker.

Both kill-directions for the validator idea are recorded in its trigger (§8 row 1).

---

## 6. Invariant and drift impacts

- **CTL/STO/CON/REG:** none touched — no code, corpus, fixture, schema, or version
  bytes. CON-13's closing clause ("a new version-bearing literal anywhere is a defect")
  is unaffected; this record introduces none.
- **Review rubric:** G4 binds the contract text itself — it states what it does not
  catch (no mechanical enforcement this slice; new records only; prose lists pass only
  when each item carries the four semantics). G5: the obligations walk adds one row if
  the maintainer takes the fork below.
- **New obligation row (the one scope extension beyond the issue's letter):**
  `.claude/skills/` copies shared with the SDK repo (`increment/`, `panel/`) currently
  have NO sync obligation — the duty lived in this issue's text alone. Draft row 19:
  *"A change to a skill shared with the SDK repo (`.claude/skills/increment/`,
  `panel/`) → re-sync the SDK copy's shared clauses in the same work (two-commit shape
  per AGENTS.md; loop prose that is deliberately gateway-specific does not sync)."*
  Grounded in the file's own principle (obligation 14 landed the same way on its second
  arrival); the two skills dirs are `increment, panel, retrospective` (main) vs
  `increment, panel, release-review` (SDK) — the shared set is exactly `increment/` +
  `panel/`. **Maintainer fork: register now, or rely on AGENTS.md's two-repo discipline
  section** (which covers the submodule, not skill copies).
- **CI cost:** zero new jobs; existing gates re-run per commit.

---

## 7. Pre-committed acceptance rule

Written before any review applies the contract. A docs increment still gets a control
that fluff cannot pass.

**SHIP when all three hold:**

1. **RED-able string control:** `git grep -F "(the condition that justifies reopening)"`
   returns exactly **2** hits on the pre-change tree (main SKILL.md:97; SDK SKILL.md:89)
   and **0** after; reverting only the two skill commits restores 2. (Disable the
   mechanism → the undefined-term artifact reappears.)
2. **Pre-committed conformance verdicts** — the contract text, applied by a reviewer
   who did not write it, must reproduce all four: (i) #146 §6 conforms (all 10 rows,
   "Carrier" accepted as the home label); (ii) #133 §9 conforms via its
   preamble-carried home; (iii) #156's table is NON-conforming on the home semantic;
   (iv) #67's table is non-conforming on identifier and home. Any verdict that flips
   means the contract text is ambiguous and the slice fails review.
3. **Dogfood:** every row of this record's own §8 table conforms to the contract as
   written.

**KILL if:** the contract cannot refuse "when it becomes important" without appeal to
taste, or cannot produce verdict set 2 unambiguously — then a prose contract is the
wrong instrument and the issue needs the validator-first shape instead.

**UNDERPOWERED, not conclusive, if:** disputes arise on rows outside the pre-committed
set — those extend the contract's example set (an amendment), they do not kill it.

---

## 8. Deferrals — every row carries home and reopen trigger

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| 1 | Mechanical validator for deferral-row conformance (forward-only record gate) | Documentation here | A reviewer dispute over a NEW record's row conformance (evidence the prose contract is ambiguous in practice), or five new records all carrying the canonical header (a stable input set for a header-tolerant checker) |
| 2 | Backport of the 2026-09-24/25 loop content the SDK skill copy lacks (step 3's gates-after-docs-commits line; step 8's entry-shape fields) — observed drift, out of #99's scope | Documentation here | The next edit to either copy's loop steps 3–8 (it forces the full diff anyway), or the owner's explicit call |
| 3 | Terminology sweep renaming committed records' "Carrier" home columns to "Home" — refused, not merely deferred: committed records are frozen history | Documentation here (this row exists to close the question) | None exists — a reviewer proposing the sweep is directed to this row |

---

## 9. Top risks, each with its falsifier

1. **Over-specified triggers force dishonest tables.** Falsifier: a future deferrer
   unable to state any inspectable event for a genuinely deferrable item. Mitigated in
   the text: owner-call events are first-class (#199 grounding); the carrier-naming
   maturity is recommended, not required; the refused list is three phrases long, not a
   rubric.
2. **Definition drift between the main and SDK copies reintroduced.** Falsifier: the
   two step-7 clauses diverging again. Mitigated: single authoritative text main-side,
   pointer-not-mirror SDK-side, and (if taken) the obligation-19 row.
3. **Contract ossifies the four-column form.** Falsifier: a future record whose
   legitimate shape the contract refuses. Mitigated: semantics-not-labels, extra
   columns free, preamble-carried homes, prose-list rendering allowed.
4. **Reviewer variance persists with no mechanical gate.** True and named — the
   residual the issue itself acknowledges ("no mechanical gate yet"); deferral row 1
   carries the fix and its trigger.
5. **The pointer commit folds local submodule dirt.** Falsifier: `git diff --submodule`
   on the pointer commit showing anything but the intended advance. Named in §3.

---

## 10. What the maintainer must decide

1. **Obligation row 19** (§6): register the skill-sync duty in
   `docs/internal/drift-and-obligations.md` now, or leave it to AGENTS.md's discipline.
   Design position: register — the duty has no home today, and this increment is
   performing the sync manually.
2. **The SDK README pointer section** (§2.3): include or drop. Design position: include;
   three lines, and it prevents an SDK-side record author hitting a dead end at the
   SDK README.

---

*Provenance: grounded against main @ `67a647c` and the SDK standalone checkout on
2026-09-26; the census and verdicts cite committed records only; no client, bench, or
person identifiers.*
