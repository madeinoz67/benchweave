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

# retrospective — the standardized end-of-period report

Retrospectives happened before this skill; the vault proves it. What did not exist was
a shape: three recent periods produced three different output shapes for the same
nominal activity, so period-over-period comparison was impossible — "are the process
improvements working?" was unanswerable because the units differed every time. This
skill fixes the units, and does for period retrospectives what the proposal ledger did
for findings: it turns a discipline that depended on remembering into a procedure with
named persistence targets.

The report is **source-shaped, not session-memory-shaped.** Every fact carries its
source class; what no source carries reads `not recorded`. A period report that prints
"adversary lane: 6 findings, 2 stalls" over an invented count is the same lie class as
a transport success reported as completed physical work (decision A06, stated as
analogy: nothing in the control path depends on this skill).

## When to use

When a period of work closes — a run, a week, a session spanning multiple increments —
and the owner asks for a retrospective, a period report, or a wrap-up. NOT-FOR: the
per-run ledger entry at a single run's close. That is `increment` step 8's job; this
skill harvests those entries later.

## The window

The period is a `(from, to)` pair of **UTC timestamps stated in the report header**,
chosen by the owner, defaulting to the span since the last ledgered retrospective —
or, when none exists yet, the running session's span, stated explicitly either way.
The window is load-bearing and auditable: every harvest command in the report carries
the same window strings, and a verifier re-running them must get the same counts.

## Who runs it

The main session, not a sub-agent: the report needs the tracker CLI, the repo
filesystem, the project memory MCP server, and owner interaction for the row-call
rulings. A sub-agent may pre-harvest sections 1 and 6 mechanically; that is an
optimization, not the design.

## The honesty rule — source classes

Every section, and every numbered row inside it, carries a source tag. This is the
core honesty rule, and it is checkable by a reviewer without trusting the author:

- `[harvested: <exact command or vault query>]` — the command with the window strings
  substituted, re-runnable as cited.
- `[narrated: session recollection — unverified]` — remembered, not sourced.
- `not recorded` — no source and no memory: an honest absence.

There is no dispatch log in this repository. Per-lane dispatch counts, stall
durations, swap events and brief-quality misses are **not harvestable — never invent
them, never launder narration into numbers that look sourced.** The vault carries them
only incidentally, and incidentally is not reliably.

## The six sections

### 1. Landed

`[harvested]` throughout:

- `gh pr list --state merged --search "merged:<from>..<to>"` — one row per merged PR:
  number, title, issue link.
- `gh issue list --state closed --search "closed:<from>..<to>"` — the closed-issue
  roll.
- `git log origin/main --since "<from>" --until "<to>"` — the commit count.

### 2. Process findings — worked/didn't, with evidence

Three harvest lanes:

- Vault recall on the `benchweave` vault — tag-scoped (`retrospective`, `workflow`)
  and `since`/`before`-filtered to the window. Review records carry their own tags
  (review / code-review / governance-review shapes); they are found via the archive
  lane below, not by recall vocabulary.
- The drained archive `.claude/memory-proposals.drained.jsonl` — every ledger-routed
  vault entry minted in the window (by `drained_at`), including review records whose
  tags fall outside the recall vocabulary; the deterministic index when recall
  under-returns. It does not cover MCP-direct vault writes, and it carries no window
  index — window by `drained_at`.
- The review-finding dispositions carried in fix-wave commit messages: the messages
  name the finding IDs they fold (`review F3/F5/F6/LOW-1/NIT-2` shape).

Narrated additions are permitted, tagged narrated.

### 3. Sub-agent review — the section nothing else owns

One block per lane dispatched in the period (designer, builder, adversary,
standards-governor, mechanism-critic, code-reviewer, bench-measurer — the `increment`
loop's lanes). Verdict and findings yield are `[harvested]` from the period's review
records and per-run retrospective entries: every review lane already ledgers its
findings record with dispositions (the review-findings exemption), so this section
**cites** those records — it never re-ledgers them — and finds them via the §2
archive lane, not recall alone. Evidence may also live in the period's design-record
fold sections and PR bodies in git: when a lane's yield is recorded there, cite the
file path + section, not a vault id. Dispatch counts, stalls/swaps and
brief-quality misses are `[narrated]` or `not recorded` wherever no entry carries
them. Gate-redundancy observations (three lanes redundantly re-running full gates, as
#129 recorded) come from the per-run entries when present.

Each lane gets **exactly one call — keep / adjust-brief / scale / retire —** with the
evidence that drove it. A lane with no period data gets `not recorded` fields and
**no call**: a call without evidence is the over-claim this skill exists to prevent.

### 4. Deviations & disclosures

Judgment calls made without explicit owner sign-off. Seed it `[harvested]` from the
period's PR bodies' deferral sections and design-record deferral tables (both mandated
by `increment` step 7). The narrated residue is the point: this is the formal slot for
"did X without asking."

### 5. Numbered row-call table

Every process recommendation that needs the owner's call, numbered (R1, R2, …). Each
row carries: the recommendation, its evidence citation (issue, PR or vault entry),
what it would cost to adopt, and **the falsifier** — the evidence that would say the
recommendation is wrong (the `panel` skill's losing-arguments discipline). Rows the
evidence does not support are not offered.

**Zero rows is a legal outcome**, and it must carry the considered-and-declined list
with reasons. An empty table with no negation proof is report theater — and so is a
table padded to look thorough.

### 6. Where everything went

`[harvested]` throughout:

- `.claude/memory-drain-receipt.json` — current drain receipt: counts, `last_run_at`,
  outcome; `.claude/memory-drain-receipts.jsonl` is the run log behind it.
- `.claude/memory-proposals.jsonl` — the queue. Undrained proposals are a disclosure,
  not a failure.
- `.claude/memory-proposals.drained.jsonl` — the archive, which records every engram
  id the drain produced: the source for vault entries minted this period.
- `git log --since "<from>" --until "<to>" -- .claude/ docs/` — skill, agent and doc
  amendments landed in-window.

Archive and queue counts are render-time measurements of append-only sources — pin
them "as at <the drain-receipt `at` timestamp>" so a verifier re-derives at the same
moment.

## The entry-shape note

Section 3 is only as harvestable as the per-run entries `increment` step 8 mandates. A
run-close retrospective entry should, when the facts exist, name: the lanes
dispatched; each lane's verdict and finding count by severity; the disposition
summary; any stall/swap; any brief-quality miss — tagged `retrospective`. The skill
adds no tooling to enforce this; it makes the contract explicit so future entries can
be harvested rather than excavated.

## Persistence, in order

1. **Present the report to the owner** in-session, posted where the owner directs
   (a tracker comment when asked for there).
2. **One ledger proposal per period retrospective** — the verdict plus the row calls,
   with the owner's rulings appended when they come. One concept per memory, per the
   noise bar; review findings are cited, never re-proposed.
3. **Accepted row calls become their natural durable artifacts** — issues, PRs, skill
   amendments — where they live forever. The report itself is **not committed to the
   repo by default**: a period report is operational narration, not a pre-commitment
   proof.

## Failure modes to watch for

- **A `[harvested]` tag on a dispatch count or stall figure.** There is no source for
  those; a section 3 that looks sourced is this skill's worst failure.
- **Report theater.** Narrated fluff filling the format; every period returning a
  table; rows without falsifiers, padding rows, or a zero-row table without its
  negation proof.
- **Scope creep beyond the repo's tree.** The skill does not prescribe the run
  ledger's shape or any session's dispatch discipline — those live outside this
  repository. The entry-shape note is a request made of step-8 entries, which are
  repo-owned.
- **A report shaped like the session's memory of the window.** Render from sources: a
  field you cannot source reads `not recorded` even when you remember it. The lived
  window must not render richer than its sources warrant.
- **The step-8 pointer dangling.** If this skill is renamed or moved, `increment`
  step 8's cross-reference lies; any skills move re-checks it (the reviewer's
  prose-cross-reference walk — no mechanical guard claimed).
- **Vault recall missing a period's entry.** Observed once (2026-09-21, the #129 run
  entry): it ranked ~7th on a good query. Use tag-scoped and `since`/`before`-filtered
  recall — both deterministic lanes — not free-text only.
