# Review rubric Step 1: ui/ TypeScript tier rule + design-time keyword check — design of record (issue #254)

**Date:** 2026-09-28
**Status:** Design complete — build may start
**Issue:** madeinoz67/benchweave#254
**Carrier increment:** #242 slice 1 (the increment that surfaced both gaps); deferral row D2 of
`2026-09-28-issue242-ui-contract-design.md` §11.
**Triage:** public-safe — process rules and repo-internal document names only.

**This increment's own tier: TIER 3, by the keyword rule the amendment restates.** The
diff text necessarily contains the Tier-3 keyword list (the rubric's rule is quoted) and
the `protection-active` example — a docs-only change that mentions protection-related keys
takes the deep lane, by intent; this record is the first demonstration of its own rule.
The Step-1 keyword scan was run over this record's expected diff text (`docs/internal/review-rubric.md`,
`.claude/deep-review/README.md`, this file): all eight keywords appear — once each because
the amendment quotes the rule's own keyword list, and `protection` fifteen times (the
list, the interplay note, the walkthrough). No path rule fires (docs-only).

---

## 1. The two gaps (verified against the live rubric)

1. **Path gap.** Tier 2's rule reads "any other change to Python logic under `src/`,
   `scripts/`, `tests/`, `.github/`, or root config". `ui/` TypeScript matches no path
   rule; Tier 1 is docs-only. The #242 slice 1 design record had to say "Tier
   2-equivalent" precisely because no rule applied — the hedge is the defect's signature.
2. **Keyword-rule gap.** Step 1's keyword rule (diff text containing `threading`,
   `asyncio`, `subprocess`, `sha256`, `hashlib`, `migrate`, `recovery`, `protection` →
   Tier 3, first-match-wins) fired correctly on slice 1's diff at REVIEW time via
   `protection-active` — but nothing required the DESIGN record to run the scan, and the
   record self-classified "Tier 2-equivalent". The catch was dispatch luck, not procedure.

## 2. Tier placement: `ui/` TypeScript → Tier 2 (path rule), evidence

- The #242 record's own judgement was Tier 2 — the burden matched; only the missing rule
  forced the hedge.
- ui/ changes carry executable renderer code and the contract pins
  (`ui/src/contract-*.test.ts`) — the "standard" evidence burden: the ui battery
  (`npm test`/`typecheck`/`lint`), G4 against the ui-contract behaviour contract
  (obligation 12 names it the normative surface), and G-render for draw-visibility
  claims. G-render is already tier-independent, so no tier special-casing is needed.
- Safety-relevant renderer work escalates by CONTENT via the keyword rule — #242 slice 2
  (R-PROTECT-1, `protection-active` rendering) fires `protection` → Tier 3. This is the
  rubric's design: path rules set the default depth, the keyword rule escalates on what
  the text carries.

Disclosed non-goal, structurally backstopped: `ui/package.json` dependency changes fall
under the ui/ Tier-2 path rule, not the Tier-3 Python dependency trigger. npm deps are
isolated, exact-pinned in `package-lock.json`, and audited in CI's `ui` job — and any
ui-dep change that affects shipped renderer bytes is forced deeper regardless of the
ui/ tier: `ui/vite.preview.config.ts:13` writes the preview build into
`packages/sdk/src/benchweave_sdk/preview_assets/site`, and CI's renderer-freshness step
(`ci.yml:146-148`, `git -C packages/sdk diff --exit-code`) fails on any diff there, so
the change cannot land without advancing the `packages/sdk` submodule pointer — itself a
Tier-3 trigger that also dispatches the standards-governor. A dep change that leaves
shipped bytes identical (dev-only tooling) stays Tier 2 by path; if the owner wants ALL
ui dependency motion deep-laned, that is a separate rubric row, not this amendment.

## 3. The amendments (wording)

**3.1 Tier 2 path rule** — "Python logic" becomes "production or test code", and `ui/` is
named:

> **TIER 2 — standard.** Any other change to production or test code under `src/`,
> `scripts/`, `tests/`, `ui/` (the TypeScript renderer, its tests and styles — including
> the contract-pin tests), `.github/`, or root config (`pyproject.toml`, hatchling
> config). Test-only changes sit here, not in Tier 1 — the CI contract and the fixture
> lockstep live in the test tree, and the ui contract pins live in `ui/src`.

**3.2 Design-time tier call + keyword scan** — new paragraph in Step 1, after the
"state the tier" sentence:

> **Design-time tier call (#254).** The tier is not first discovered at review: a design
> record (`.claude/deep-review/`) states its slice's tier and that the Step-1 keyword
> scan was run over the record's expected diff text — the whole expected diff, docs and
> code alike. The review re-derives the tier independently; a record that omits the tier
> statement or the scan, or whose stated tier disagrees with the rules, is a review
> finding, not a reclassification courtesy.

**3.3 Interplay note** — new paragraph, immediately after:

> **Keyword-rule interplay.** The keyword rule is text-based and first-match-wins, by
> design: a docs-only change whose diff text merely mentions a protection-related key — a
> contract row naming `protection-active`, prose defining protective behaviour — still
> takes the Tier-3 lane. The deep lane is bought by what the text carries, not by the
> file type; text that defines or carries protective behaviour gets the protective
> review depth.

Step 4 is deliberately NOT extended: a missing tier statement is a review finding
(approve-with-required-changes territory), and Step 4's any-"no"-downgrades-to-DEFER
pattern does not fit a record-content finding. The enforcement sentence lives once, at
the rule.

**3.4 Record-content alignment** — `.claude/deep-review/README.md`'s opening (where
record content is enumerated) gains one sentence, so record authors meet the requirement
where the record contract lives; the rubric stays the authority for both rules:

> A record also states its slice's review tier and that the review rubric's Step-1
> keyword scan was run over the record's expected diff text (issue #254) — the tier call
> is part of the pre-commitment, and `docs/internal/review-rubric.md` is the authority
> for both rules.

The rubric↔README coupling is a one-directional authority pointer, the same shape as
CLAUDE.md's references to the rubric: the README points at the rubric as authority and
restates nothing, so no drift row is registered for the pair, by that precedent.

## 4. Cross-reference inventory (tier-bearing surfaces)

| Surface | Content | Disposition |
|---|---|---|
| `docs/internal/review-rubric.md` | Step 1 tier rules — the authority | **touched** (§3.1–3.3) |
| `.claude/deep-review/README.md` | the design-record content contract; silent on tiers today | **touched** (§3.4, one sentence) |
| `packages/sdk/docs/internal/review-rubric.md` | independent SDK adaptation: different Tier-3 triggers (lock/tree/stamps, refusal prefixes, scaffold, conformance, self-containment), Tier 2 names SDK paths, NO keyword rule, no `ui/` tree | untouched — not a synced copy (no sync obligation governs it; drift obligation 19 covers skills only); the ui/ rule and the main keyword rule are meaningless in the SDK repo; no contradiction arises |
| `packages/sdk/.claude/deep-review/README.md` | the SDK repo's own record-content contract (same opening shape as the main README, pre-#254 text) | untouched — no sync obligation (obligation 19 covers skills only), and the new requirement references the main rubric's Step-1 keyword scan, a rule the SDK rubric lacks; the temporal clause governs SDK-side records only if the SDK adopts its own rule |
| `.claude/agents/code-reviewer.md` | paraphrases the rubric's Tier-3 trigger list (line 46: "contracts, standards artifacts, persisted format, registry entry seam, fixture digests, concurrency, dependencies, the SDK submodule pointer") — an accurate description, not a restatement | untouched — the paraphrase names no rule text that could drift, and the agent's own opener makes the rubric the authority ("Follow docs/internal/review-rubric.md literally") |
| `.claude/agents/increment-designer.md` | the design author's enumeration ("What a design must contain") and reading list — read neither the rubric nor the deep-review README before this fold | **touched** (fold row 12) — the reading list gains the review rubric (item 5), and the enumeration gains the tier + keyword-scan-result clause |
| `.claude/agents/*` (others: adversary, standards-governor, bench-measurer, mechanism-critic) | no tier rules; defer to the rubric as the authority | untouched — defers |
| `.claude/skills/increment/SKILL.md` | the Design step's deliverables enumeration (the loop's step 1); the record contract itself is deferred to the deep-review README | **touched** (fold row 11) — the deliverables gain the tier + keyword-scan-result clause, so designs the skill commissions are compliant by construction |
| `.claude/skills/panel/SKILL.md` | tier-bearing activation gate: "a **Tier-3 or doctrine fork**" (line 22) decides when the panel runs | untouched — the gate names the tier concept but no rubric rule text, and this amendment changes no tier trigger the gate cites; no drift today |
| `CLAUDE.md` / `AGENTS.md` | no tier rules; the review section names the rubric as authority | untouched — defers |
| `docs/evidence/poc/decisions/d13-async-posture.md` | "Tier 2 — stress" is the timing-lane stress-tier concept | untouched — different concept, same word |
| `.codex/agents/*.toml` | paraphrases the rubric; **untracked** (0 tracked files) | untouched — local-only tooling, not repo content; owner refreshes locally |
| `.claude/deep-review/2026-09-28-issue242-ui-contract-design.md` | the gap's own record (F1 finding, D2 row) | untouched — frozen history ("committed records are frozen history and are never retrofitted"); D2's reopen trigger is this issue's merge |
| `docs/internal/drift-and-obligations.md` | obligations + CI map; no tier rules | untouched |

## 5. Pre-committed acceptance

| # | Check | Pass |
|---|---|---|
| A1 | The amended Step 1 classifies `ui/` TypeScript under an explicit path rule — a design record can state a ui slice's tier without any "equivalent" hedge | the words "equivalent" appear in no rule text; `ui/` is named in Tier 2 |
| A2 | Design records must state tier + keyword-scan-run, with the omission a review finding | §3.2 paragraph present in the rubric |
| A3 | The interplay note states text-based, first-match-wins, docs-only-included, intended | §3.3 paragraph present |
| A4 | **The falsifier — the S1 scenario.** A reviewer applies the amended Step 1 to #242 slice 1's expected diff (docs + `ui/src/*.test.ts`, diff text containing `protection-active`) | walkthrough below lands Tier 3 at design time |
| A5 | Cross-reference sweep: every tier-bearing surface touched or named-untouched with reason | §4 table complete |

**A4 walkthrough (RED-shaped: old text → wrong answer, new text → right answer).**

*Old text:* the ui/src test files match no path rule (Tier 2 is Python-scoped, Tier 1 is
docs-only) — the design record could only hedge ("Tier 2-equivalent"), and nothing
required it to run the keyword scan; its design-time tier call was therefore WRONG
(Tier 2) and stood until the review's keyword hit corrected it. The miss was possible
because the tier rules ran only at review time.

*New text:* the same expected diff walks the rules — Tier 3's path rules: no match;
Tier 3's keyword rule: the diff text contains `protection` (via `protection-active`) →
**match, Tier 3, first-match-wins over the Tier-2 path match** (which the ui/src files
now do take, explicitly, no hedge). The design record must state its tier and that the
scan ran; the record written under the new rules reads "Tier 3, keyword `protection`"
before any code exists. The exact miss — a record self-classifying Tier 2 while its diff
text carries a Tier-3 keyword — is now a stated review finding and cannot repeat
silently where the review's re-derivation runs; the mechanism is procedural, not
structural (a review that skips the re-derivation still skips it — the rule makes that
a defect, not an impossibility).

## 6. Gates

Docs-only increment: per-commit bare ruff + fresh-cache bare mypy + focused pytest
(PYTHONPATH workaround for the .wt/ UF_HIDDEN environment defect), full battery once
before push, `git diff origin/main...HEAD -- standards/` empty. No Python, no ui tree
touched — the battery is the regression net, not the proof.

## 7. Review fold (2026-09-29)

The review battery's 19-row fold landed as one batch commit on this branch. Where the
folded rubric text is stronger than §3's proposed wording, the LANDED text is the rule
and §3 remains the proposal as written (not retro-absorbed). The fold adds: the ui/
parenthetical widened to "code, config, and manifests" plus a default-tier clause
(nothing falls through un-tiered); the design-time paragraph's conditional opener,
scan-RESULT requirement (keywords and counts, not "was run"), multi-slice allowance
(per-slice tiers or maximum tier + per-scan diffs), verdict floor (minimum APPROVE WITH
REQUIRED CHANGES; records never retrofitted), and temporal clause (records written
after the rule lands); the interplay paragraph's converse residual (keyword-free
protective changes take the path-tier default — the eight words are a proxy, not the
territory) and self-fire sentence (keyword-list/Step-1 edits self-fire Tier 3, intended);
G2's ui battery clause (bare `npm --prefix ui` exit codes + the renderer-freshness
gate); the same temporal clause on the README sentence; and the two authoring surfaces
(`.claude/skills/increment/SKILL.md` Design-step deliverables;
`.claude/agents/increment-designer.md` reading list + design enumeration), so designs
are compliant by construction rather than corrected at review. §2's npm non-goal gained
its structural backstop (the renderer-freshness gate forces any shipped-byte-affecting
ui-dep change through the SDK pointer — a Tier-3 trigger and a governor dispatch,
regardless of the ui/ tier); §4's inventory gained the SDK record-README and panel-skill
rows, corrected the code-reviewer row (it paraphrases the Tier-3 trigger list at line 46
— an accurate description, not "no tier rules"), and marks the two touched authoring
surfaces; §5's walkthrough overclaim was reworded to the procedural truth.
