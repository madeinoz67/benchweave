# Design — issue #133: `retrospective` skill, the standardized end-of-period report

Date: 2026-09-21. Status: DESIGN (commit 1 of the branch; design-record-first per the
`increment` skill). Issue: #133 (owner requirement recorded there verbatim). Branch:
`feat/issue133-retrospective-skill` off `origin/main` `69274a2`. Review slate per the
issue's own sizing note: adversary + code-reviewer; no standards-governor or
mechanism-critic triggers fire (no standards bytes, no mechanism code).

## 0. Verdict

**BUILD** — one new repo-local skill (`.claude/skills/retrospective/SKILL.md`) plus a
one-line pointer from `increment` step 8. No code, no tools, no standards bytes, no
schema. The proof is a dry-run: the skill's format rendering a real, closed period from
real sources, with an independent re-verification lane and a control window the
rendering agent did not live.

## 1. Root cause and premise verification

The gap is not "no retrospectives happen." They do, and the vault proves it. The gap is
that the practice is **unstandardized, sub-agent-blind, and incidentally persisted**.

### 1.1 Three periods, three shapes (verified)

- The 2026-09-19 issue-#6 run-close retrospective produced **seven numbered workflow
  rules** (vault entry "Multi-increment run workflow rules (issue #6 retrospective,
  2026-09-19)", tags `workflow,retrospective,increment-loop,standards,pr-stacks`).
- The 2026-09-21 #129 run-close retrospective produced **three row calls**, which became
  issue #130 → PR #132 (`docs(skill): increment loop amendments from the #129
  retrospective`, merged `314215e`) — a *different* output shape for the same nominal
  activity, and one that already needed a dedicated issue to land.
- The same day's session self-reflection produced the six-section list that issue #133
  now proposes as the standard — a third shape, arriving as prose outside any artifact.

Each was good work. None of them could be *found* by shape: there is no place a future
period's owner or agent can look to know "the retrospective of record for window W is
here, in this form." A standardized section set is what makes period-over-period
comparison possible at all — without it, "are the process improvements working?" is
unanswerable because the units differ every time.

### 1.2 The sub-agent dimension is owned nowhere (verified)

The repo's increment loop dispatches up to seven lanes (`increment-designer`,
`increment-builder`, `adversary`, `standards-governor`, `mechanism-critic`,
`code-reviewer`, `bench-measurer` — `.claude/skills/increment/SKILL.md` steps 1–7).
No artifact reviews their *performance*: the increment skill reviews their *output*
(findings reconciled, gates re-run), and the per-run ledger entry records what the run
did, but lane yield vs cost, gate redundancy, stall/swap frequency and brief-quality
misses are written down only when a retrospective happens to mention them. The #129
run entry in the vault does carry lane facts ("4-lane review:
adversary/standards-governor/mechanism-critic/code-reviewer; 2 fix waves; merge on
terminal-green", and what each slate decision bought) — because that session chose to.
A lane that underperforms for three periods in a row is currently invisible as a trend.

### 1.3 Persistence is incidental (the failure class this repo already measured)

Per-run retrospectives survive only if the session remembers step 8's "Ledger the
retrospective before the run reports closed." That is exactly the persistence-by-memory
failure the memory protocol documents and measured (a 4.81% declaration rate that three
interventions failed to move, before the ledger made it structural —
`.claude/memory-protocol.md` opening). The skill does for period retrospectives what
the ledger did for findings: turn a discipline that depends on remembering into a
procedure with named persistence targets.

### 1.4 What is actually harvestable (probed this session, not assumed)

| Source | Verified how | What it yields |
|---|---|---|
| `gh pr list --state merged --search "merged:A..B"` | Run against 2026-09-20..22: returned #106–#132 with merge timestamps | Section 1 verbatim: PR numbers, titles, merge times |
| `gh issue list --state closed --search "closed:A..B"` | Same window: 15 closed issues incl. #102, #130 | Section 1: issue numbers, close times, titles |
| `git log origin/main --since --until` | Run: fix-wave commits carry review-finding IDs *with dispositions in the message* (`review F3/F5/F6/LOW-1/NIT-2`, `review R-F3 + A-F4`) | Section 2: finding counts by disposition, fix-wave structure |
| Vault recall with `since`/`before` + tags | Deep-mode recall surfaced the 2026-09-21 #129 run entry and the 2026-09-19 governance-review findings record | Sections 2/3: per-run entries, review records with dispositions, lane rosters |
| `.claude/memory-drain-receipt.json` + `receipts.jsonl` | Filenames confirmed in `.claude/hooks/memory-ledger.mjs` `paths()` and `.gitignore` rows 60–63 | Section 6: drain counts, `last_run_at`, outcomes |
| `.claude/memory-proposals.jsonl` (queue) + `memory-proposals.drained.jsonl` (archive) | Named by `.claude/memory-protocol.md` §"How it drains"; one-ledger-per-repo resolves worktree appends to the main checkout | Section 6: queued-but-undrained findings (a real disclosure row) |

**What is NOT harvestable, and must not be faked:** per-lane dispatch counts, stall
durations, swap events, and brief-quality misses. There is no dispatch log in the repo;
those facts live in the session that ran the period and in maintainer-side run ledgers
outside this repository. The vault sometimes carries them incidentally (the #129 entry
names its four lanes; the stall protocol requires swaps recorded in the run ledger) but
not reliably, and not in a fixed shape. The design's answer is the honest split in §2.4:
these fields are **narrated, labeled as narrated, or marked `not recorded`** — never
invented, never laundered into numbers that look sourced.

This split mirrors the product's own evidence doctrine (decision A06: the system records
evidence; the caller concludes — ambiguity is preserved, not collapsed). A period report
that prints "adversary lane: 6 findings, 2 stalls" over an invented count is the same lie
class as a transport success reported as completed physical work.

## 2. Mechanism — the skill

### 2.1 File and frontmatter

`.claude/skills/retrospective/SKILL.md`, following the two existing skills' shape
(frontmatter `name` + `description`; body = when/when-not, procedure, honesty rules):

```yaml
---
name: retrospective
description: >-
  The standardized end-of-period report: landed work, process findings, a per-lane
  sub-agent review with keep/adjust/scale/retire calls, deviations, a numbered
  row-call table for the owner, and where everything was persisted. Use when a period
  of work closes and the owner asks for a retrospective, a period report, or a
  run/week/session wrap-up covering multiple increments. NOT-FOR: the per-run ledger
  entry at a single run's close — that is increment step 8's job; this skill harvests
  those entries later.
---
```

The skills-format boundary stays where #71-D2 left it: lowest-common-denominator
frontmatter, no format standardization, no schema.

### 2.2 Period parameterization

The period is **(from, to) UTC timestamps stated in the report header**, chosen by the
owner or defaulting to the span since the last ledgered retrospective. The window is
load-bearing and auditable: every harvest command in the report carries the same window
strings, and a verifier re-running them must get the same counts. Default when no owner
window is given: the running session's span, stated explicitly.

### 2.3 Who runs it

The main session, not a sub-agent. It needs the tracker CLI, the repo filesystem, the
project memory MCP server, and owner interaction for the row-call rulings — the same
position `increment` and `panel` occupy. (A sub-agent could be dispatched to pre-harvest
sections 1 and 6 mechanically; that is an optimization, not the design, and the skill
may suggest it without requiring it.)

### 2.4 The six sections, each with a named source class

Every section, and every numbered row inside it, carries a **source tag**: `[harvested:
<exact command or vault query>]` or `[narrated: session recollection — unverified]` or
`not recorded`. This is the mechanism's core honesty rule, and it is checkable by the
reviewer without trusting the author.

1. **Landed** — `[harvested]` `gh pr list --state merged` + `gh issue list --state
   closed` for the window + `git log origin/main --since --until`. One row per merged
   PR (number, title, issue link); closed-issue roll; commit count.
2. **Process findings — worked/didn't, with evidence** — `[harvested]` vault recall
   (`since`/`before` = the window, tags `retrospective`, `workflow`, `review-tail`)
   plus the review-finding dispositions carried in fix-wave commit messages (verified
   present: the #129 waves name every finding ID they fold). Narrated additions are
   permitted, tagged narrated.
3. **Sub-agent review** — the section nothing else owns. Per lane dispatched in the
   period: verdict and findings yield `[harvested]` from the period's review records
   and per-run retrospective entries (each review lane already ledger's its findings
   record with dispositions — the 2026-09-14 review-findings exemption — so the
   retrospective *cites* them, it never re-ledgers them); dispatch count, stalls/swaps,
   brief-quality misses `[narrated]` or `not recorded` where no entry carries them.
   Gate-redundancy observations (e.g. #129's three lanes redundantly re-running full
   gates) come from the per-run entries when present. **Each lane gets exactly one
   call: keep / adjust-brief / scale / retire**, with the evidence that drove it. A
   lane with no period data gets `not recorded` fields and **no call** — a call without
   evidence is the over-claim this design exists to prevent.
4. **Deviations & disclosures** — judgment calls made without explicit owner sign-off.
   Seed `[harvested]`: PR bodies' deferral sections and design-record deferral tables
   (both mandated by `increment` step 7). The narrated residue is the point of the
   section: it is the formal slot for "did X without asking."
5. **Numbered row-call table** — every process recommendation that needs the owner's
   call, numbered (R1, R2, …), each row: the recommendation, its evidence citation
   (issue/PR/vault entry), what it would cost to adopt, and **the falsifier** — what
   evidence would say the recommendation is wrong (the `panel` skill's
   losing-arguments discipline). Rows the evidence does not support are not offered.
   **Zero rows is a legal outcome** and must be accompanied by the
   considered-and-declined list with reasons — an empty table with no negation proof
   is report theater, and so is a table padded to look thorough.
6. **Where everything went** — `[harvested]` drain receipts (counts, `last_run_at`,
   outcomes), ledger queue state (undrained proposals are a *disclosure*, not a
   failure), the vault entries minted this period (ids), and the skill/agent/doc
   amendments landed in-window (`git log --since --until -- .claude/ docs/`).

### 2.5 The per-run entry-shape note (the harvestable-substrate coupling)

Section 3 is only as harvestable as the per-run entries increment step 8 already
mandates. The skill therefore carries a short **entry-shape note**: a run-close
retrospective entry should, when the facts exist, name the lanes dispatched, each
lane's verdict and finding count by severity, the disposition summary, any stall/swap,
and any brief-quality miss — tagged `retrospective`. The skill does not add tooling to
enforce this (that is D2, §9); it makes the contract explicit so future entries can be
harvested rather than excavated.

### 2.6 Persistence targets (in order)

1. The report is **presented to the owner** in-session (and posted where the owner
   directs — e.g. a tracker comment when the owner asks for it there).
2. **One** ledger proposal per period retrospective (verdict + the row calls; the
   owner's rulings appended when they come) — one concept per memory, per the noise
   bar; review findings are cited, never re-proposed.
3. Accepted row calls become their natural durable artifacts — issues, PRs, skill
   amendments — which is where they live forever; the report itself is **not committed
   to the repo by default** (a period report is operational narration, not a
   pre-commitment proof; committing every one would bloat the tree — D3 holds the
   published-retrospective option with its trigger).

### 2.7 The one-line `increment` step-8 pointer (in scope, included)

Current text ends step 8: "Ledger the retrospective before the run reports closed."
Proposed amendment, one sentence: "Ledger the retrospective — carrying the facts the
`retrospective` skill's entry-shape note names — before the run reports closed; at
period close, the `retrospective` skill harvests these entries."

Rationale for including rather than deferring: without the entry-shape coupling, the new
skill's data supply is unspecified and section 3 degrades to pure narration on every
future period — the design's central honesty claim would be true exactly once (for the
2026-09-21 substrate, which predates the skill) and false thereafter. The edit is one
sentence in a prose skill; the drift risk (a dangling pointer if the skill is renamed)
is a prose cross-reference of the same class the reviewer's G5 walk already covers, and
does not merit a new obligations row.

## 3. The exact increment (slice 1)

| File | Change |
|---|---|
| `.claude/skills/retrospective/SKILL.md` | New — §2.1–2.6 rendered as skill prose in the house voice (the `increment`/`panel` register: imperatives, failure modes, non-negotiables) |
| `.claude/skills/increment/SKILL.md` | One sentence amended at step 8 (§2.7) |

PR body carries: the design-record link, the dry-run evidence (§6), and the deferral
table. No other file moves. No `src/`, `standards/`, `tests/`, `packages/sdk`, or hook
changes.

## 4. Precedent

- **Skill shape**: `.claude/skills/increment/SKILL.md` and `panel/SKILL.md` —
  frontmatter triggers, when/when-not gate, numbered procedure, failure-modes section.
  The `panel` skill additionally contributes the pre-registered-rule and
  losing-arguments disciplines, reused in §2.4's row-call table.
- **The per-run ledger flow**: `increment` step 8 + `.claude/memory-protocol.md`'s
  review-findings exemption (findings with dispositions survive in the vault; the
  retrospective is a *consumer* of that trail, adding no new persistence mechanism).
- **The ad-hoc ancestors**: the issue-#6 retrospective (2026-09-19) and the #129
  retrospective entry + #130/#132 codification arc (2026-09-21) — both in the vault;
  both cited as the practice this standardizes, not replaces.
- **New architecture?** No new mechanism class is invented: this is a third skill in a
  two-skill family plus a cross-reference. That is why the precedent fits.

## 5. Invariant and drift impacts

- **CTL/STO/CON/REG: untouched.** No control-path, state, contract, standards, or
  registry code changes; the skill governs maintainer process only. No new invariant is
  warranted — there is no machine-checkable product behavior here to pin (a prose
  "invariant" with no enforcement surface would be decoration).
- **A06 analogy, stated as analogy, not authority**: the source-class labeling applies
  the evidence-over-assertion doctrine to process reporting; nothing in the control
  path depends on this skill.
- **#71-D2 boundary respected**: no skills-format standardization; frontmatter stays
  name+description.
- **Drift obligations (G5 walk)**: obligations 1–13 do not fire (no MCP/openapi/plugin
  docs/fixture/vendored/pointer/adapter/systemd/dependency/secret/report-family/agent-
  grant surfaces touched). Obligation 14 does not fire (no `tools:`/`disallowedTools:`
  change). No new row is added: the skills surface has no sync partner — the one
  cross-reference created (step 8 ↔ retrospective) is single-hop prose, already inside
  the reviewer's walk. Adding a row per prose cross-ref would be over-governance;
  if a future change gives `.claude/skills/` a mechanical consumer, obligation 12's
  add-the-row-when-the-surface-arrives principle applies then.
- **Tier**: not Tier 3 — no persisted format, schema, or on-disk artifact beyond two
  markdown files; review-rubric tier is docs/process. The scaled slate (adversary +
  code-reviewer) matches the increment skill's tier-scaled rule and the issue's own
  sizing note.
- **CI cost: zero new jobs, zero runtime delta.** The diff adds two markdown edits;
  every existing gate runs unchanged.

## 6. Measurable proof — pre-committed acceptance rule

The artifact is prose, so the proof is a **dry-run with independent re-verification and
a control window**, judged against this rule, which is pre-committed by this record's
commit preceding any dry-run execution.

**Window (pre-committed):** primary = `2026-09-20T00:00Z..2026-09-21T12:00Z` — the
issue's named substrate; it must contain both the #129 merge (04:15Z) and the #132
merge (04:25Z) or the instrument is mis-aimed. Control = `2026-09-19T00:00Z..2026-09-20T00:00Z`
— a period the authoring session did **not** live end-to-end (its facts exist only in
sources: the #6 retrospective entry, the #62 governance record, PRs #106-and-earlier).

**Metric:** source-fidelity of the rendered report. SHIP iff all five hold:

1. **All six sections render from real sources for the primary window** with zero
   placeholder survivors — no TBD, no blank field that is not either a sourced value,
   an explicit `not recorded`, or an explicit "none in period" backed by the harvest
   command's empty result.
2. **Every `[harvested]` number re-verifies.** The reviewer re-runs, from the report's
   own cited commands, at least: the merged-PR count, the closed-issue count, and one
   drain-receipt count — before reading the report's prose — and the numbers match
   exactly. (Metric = count-vs-source equality per number; no fixed count is
   pre-committed because the window boundary, not the count, is the pre-commitment.)
3. **The control window renders with honest sparseness.** Sections 1, 2 (dispositions)
   and 6 still populate `[harvested]`; narrated-only fields (dispatch counts, stalls,
   brief misses) read `not recorded` — and at least one *is* `not recorded` while the
   vault's per-run entries for that window genuinely lack it (verified by the reviewer
   against the same recall). A control that renders as richly as the lived window
   proves the report is session-memory-shaped, not source-shaped: that is a KILL.
4. **Section 3 gives every lane dispatched in the primary window exactly one call**
   (roster verifiable against the #129 run entry naming its four lanes), and any lane
   with `not recorded` yield data carries no call.
5. **The row-call table obeys §2.4 rule 5** — each row carries evidence + falsifier,
   or the zero-row case carries its considered-and-declined negation proof.

**KILL if:**
- any `[harvested]` number fails re-verification (the report asserted a count its
  source does not return);
- a section renders only by invention — unsourced content standing where a sourced
  value or `not recorded` belongs (fix by cutting or marking, never by padding);
- the load-bearing facts of the primary window are all narrated (the skill then has no
  mechanism, only a format — the smoke-and-mirrors failure);
- the control window violates check 3's sparseness expectation.

**UNDERPOWERED, not conclusive, if:**
- the same session authors the skill and renders the primary dry-run *and* performs the
  re-verification (self-rendering bias): the run only counts if the independent
  reviewer lane did check 2's blind re-derivation;
- the reviewer cannot reach the vault (no MCP approval in their session): vault-sourced
  rows verify via the drain archive/receipts instead; if neither lane is reachable,
  re-run the control window on vault-independent sources only, and say so in the
  evidence — vault coverage claims then remain unproven and defer to the next real
  period run.

## 7. RED-adapted slicing (what "RED" means for a markdown artifact)

Honest statement first: a prose skill has no failing test. The nearest RED equivalent,
and the one this run uses:

- **RED (the negative control):** the dry-run attempted **without the skill present**
  — the same agent asked for "a retrospective of the window" in a checkout without
  `.claude/skills/retrospective/` — does not produce the standard sections or the
  source-class labels. This is weakly discriminating (the issue text itself lists six
  sections, so a section *list* could be reproduced from the brief), which is exactly
  why the acceptance rule's load-bearing checks are 2 and 3 (numbers re-verify;
  control-window sparseness) — those cannot be passed by knowing the format. The RED
  is recorded as supporting evidence, not as the gate.
- **Commit sequence:** commit 1 = this design record (the rule provably precedes the
  measurement); commit 2 = the skill + the step-8 sentence; dry-run evidence (primary
  + control + the blind re-derivation) in the PR body before review, per the
  issue's "design record first … then RED-adapted build" sequencing note.

## 8. Top risks and falsifiers

- **R1 over-claiming harvestability** — the design's worst failure would be a section
  3 that looks sourced. Falsifier: reviewer finds a `[harvested]` tag on a dispatch
  count or stall figure (there is no source for those). Guard: check 4 + the
  entry-shape note keeping the boundary explicit.
- **R2 report theater** — the format fills with narrated fluff and every period
  returns a table. Falsifier: rows without falsifiers; padding rows; a zero-row table
  without the negation proof. Guard: check 5; the panel skill's discipline in §2.4.
- **R3 scope creep into maintainer-side process the repo cannot own** — the skill
  starts prescribing the run ledger's shape or the DA session's dispatch discipline
  (those live outside this repository). Falsifier: any skill line that governs an
  artifact not in this repo's tree. Guard: the entry-shape note is a *request the
  skill makes of* step-8 entries, which ARE repo-owned; anything beyond that is D2.
- **R4 self-rendering bias** — the authoring session renders the window it lived.
  Falsifier: check 3's control window; check 2's blind re-derivation.
- **R5 the step-8 pointer dangles** — the skill is renamed/moved later and the
  cross-reference lies. Falsifier: reviewer's G5 walk on any future skills move (the
  same walk that already catches prose cross-ref drift); no mechanical guard claimed.
- **R6 vault recall miss** — semantic recall does not surface a period's entry (this
  design session observed the #129 entry ranking ~7th on a good query). Falsifier: a
  window whose vault entries exist but do not render. Guard: the skill instructs
  tag-scoped and `since`/`before`-filtered recall (both deterministic lanes), not
  free-text only; the residual is disclosed here as a known softness.

## 9. Deferrals (explicit, each with its reopen trigger)

| # | Deferred | Reopen trigger |
|---|---|---|
| D1 | A deterministic harvest helper (script emitting sections 1/6 skeletons from `gh`/`git`/receipts) | A second retrospective run where hand-harvesting proves error-prone, or any acceptance-check-2 mismatch attributable to transcription |
| D2 | A per-lane dispatch-notes convention or dispatch log (making section 3 fully harvestable) | A period retrospective where a needed keep/retire call is blocked by `not recorded` dispatch data |
| D3 | Committing period reports as repo artifacts (e.g. `.claude/deep-review/` or a docs home) | The owner asks for published retrospectives, or an audit needs them in-tree |
| D4 | Any CI/drift-guard integration | Only after a surface exists that a gate could check — none is identified |

No follow-on issue is filed: per the increment skill's amended rule 3, these rows carry
their reopen triggers in-row (documentation deferrals; no scheduled carrier).

## 10. DON'T-BUILD evaluation (considered, rejected on evidence)

The one structural kill-risk investigated: **is the sub-agent section theater?** — if
nothing lane-shaped is harvestable AND narration cannot be trusted, section 3 is a
format field that fills with fluff. Verdict: no, on two grounds. The vault demonstrably
carries lane rosters, verdicts, fix-wave counts and slate-outcome facts in per-run
entries (the #129 entry), and the review-findings exemption already guarantees
per-review findings-with-dispositions. What remains narrated is bounded (counts,
durations, brief misses) and the format makes its absence *visible* (`not recorded`)
rather than papered — which is itself the honest outcome. The section survives; its
unverifiable residue is labeled, not laundered.

Secondary kill-risk: **the format is redundant with the increment skill's step 8.**
Rejected — step 8 closes one run; this closes a period and owns the agent-review
dimension; the issue records that decision as already made, and the coupling is the
one-line pointer, not a rewrite.
