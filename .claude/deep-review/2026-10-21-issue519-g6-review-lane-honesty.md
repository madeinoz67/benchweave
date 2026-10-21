# Issue #519 — G6's "cross-vendor audit" sentence claims a property the repository cannot deliver: rewrite to install-property honesty

**Date:** 2026-10-21 · **Tracker:** madeinoz67/benchweave#519 (single issue stream; gateway-only diff) · **Status:** design of record
**Base:** origin/main `5ff6668b` (line anchors are as of that SHA; when they drift, re-locate by
the quoted structure, not the number)

**Alias-resolution evidence, vendor-neutral by design.** The audit installation's routing
specifics — router, vendors, model IDs, settings and log references — appear nowhere in
tracked content: this repository is public and those specifics are the `private/` triage
trigger of `.claude/deep-review/README.md`. The design rests on the shape alone, which
needs none of them: on the audit installation both the producing and refuting pins
resolved to the same model and vendor — no cross-vendor separation was available in the
`.claude` fleet there, which is exactly the case the rewritten G6 sentence must disclose
instead of assuming away. (Record-history note: the branch's first commit carried this
evidence as a deliberately untracked companion under `private/`; the owner direction at
fold-time moved it into this vendor-neutral statement and the companion was deleted. The
correction is a visible follow-up commit, not a silent rewrite, so the acceptance rule in
§5 stays provably pre-committed.)

**Review tier — design-time call (#254): Tier 2.** Rubric Step 1, second rule: the expected
diff is test code under `tests/` plus internal docs and this record. No Tier-3 trigger
matches: no `standards/`, `src/benchweave/contracts/`, `state/`, `registry/` or `fixtures/`
motion, no JSON Schema, no dependency-file change, no submodule pointer advance.
**Step-1 keyword scan over the whole expected diff** (this record, the rubric hunk, the
drift hunk, the new test): `threading` 0 · `asyncio` 0 · `subprocess` 0 · `sha256` 0 ·
`hashlib` 0 · `migrate` 0 · `recovery` 0 · `protection` 0. **Scan self-reference
disclosure:** the eight words occur in the expected diff ONLY inside this scan statement's
own vocabulary — the #254 shape mandates naming each keyword with its count, so the listing
is self-referential by construction; over the diff text EXCLUDING this paragraph, each
keyword's count is 0.

---

## 1. The finding — a vendor-diversity claim with no mechanism behind it

`docs/internal/review-rubric.md:167-168` (G6 Adversarial refute) currently reads:

> The repo's standing independent lane is the cross-vendor audit — never the model that
> produced the change.

That sentence binds the REPOSITORY to a vendor-diversity property. The repository has no
mechanism that delivers one: agent definitions declare model PINS (`model: opus`), and what
an installation resolves a pin to — same vendor as the producing lane, a different vendor,
different back ends behind the same alias — is an installation property. A reviewer
following the rubric literally on a single-vendor installation is instructed to rely on a
diversity that does not exist there, with no instruction for what to do when it is absent.
Under the rubric's own G4 claim discipline this is a defect in the normative text: the set
named in prose ("cross-vendor audit") is not regenerable from any mechanism the repo
controls.

## 2. The owner ruling that governs the fix

The model aliases exist precisely so the repository never pins a vendor: contributors may
all be on one vendor, and may be on different back ends behind the same alias. The repo
therefore cannot buy vendor diversity and must not design a control that assumes it.
**No agent frontmatter changes** — `adversary`, `mechanism-critic` and `standards-governor`
stay on `opus` (`adversary.md:11`, `mechanism-critic.md:11`, `standards-governor.md:10`).
Same-pin convergence is an owner-accepted posture: `adversary.md:11` and
`increment-builder.md:9` share `opus` today, so a SEPARATION test (asserting two lanes'
pins differ) would red on main against owner intent — this design does not add one.

## 3. What ships

1. **The rubric rewrite** (`review-rubric.md:167-168` — the whole normative fix): the
   quoted sentence is replaced by the text in §3.1.
2. **A drift obligation** (`drift-and-obligations.md` obligation 14, `:219-227` at base)
   gains the `model:` field: an agent model change re-diffs every agent frontmatter and
   cites the new test.
3. **A structure test** pinning the precondition of the new claim:
   `tests/contract/test_agent_model_pins.py`, a declaration-completeness check that every
   `.claude/agents/*.md` frontmatter declares a `model:` line. The new sentence's honesty
   ("its model is whatever the installation resolves that agent's declared pin to")
   presupposes that every agent DECLARES a pin; the test is what makes that presupposition
   regenerable (G4) instead of assumed.

Precedent: obligation 14's sibling-diff rule (re-extract every sibling's frontmatter on a
frontmatter change) and `tests/contract/test_baseline.py`'s structure-pin shape
(`ROOT = Path(__file__).resolve().parents[2]`, docstring stating non-catches, plain
assertions, no fixture machinery).

### 3.1 The rubric sentence (exact landing text)

> The repo's standing independent lane is a second pass under a different mandate — its own
> agent definition, prompt, and tool grants; its model is whatever the installation resolves
> that agent's declared pin to. Model diversity is an installation property, not a repository
> property: the repository declares pins, never vendors. The repo therefore cannot promise
> the refute runs a different model than the producing lane; where an installation resolves
> both pins to one model, the second pass's independence rests on its mandate and evidence
> standard, not its model. Where the installation has a genuinely different-vendor set of
> agents (the sibling Codex fleet under `.codex/agents/`), dispatching the refute there is
> the strongest available cross-vendor option — recommended where present, never a
> requirement every contributor can meet. Each refute report quotes the model string its
> own installation reports: self-reported, an audit trail, not a gate.

(Only the claim sentence at `:167-168` is replaced; the surrounding G6 prose — the intro
question and "The two reviews are compared:" leading the comparison bullets — is untouched.
Line wrapping follows the file's existing column discipline.)

### 3.2 The test's stated non-catches

- Same-pin convergence: two lanes declaring the same pin is owner-accepted (§2); this test
  does not compare pins.
- Vendor identity: which vendor an installation resolves a pin to is an installation
  property, invisible to repository state; no in-repo test can catch it.
- Presence-only: the test proves a non-empty `model:` line EXISTS in each frontmatter. It
  does not validate that the pin names a real alias (the repo holds no authority for the
  alias set), nor that the declared pin served any given run.

Parsing is stdlib-only (`pathlib`, string operations) — no new dependency, no YAML import.

## 4. Deviation from the issued design, with evidence

The issued design said obligation 14's model rule "re-diffs all seven frontmatters". The
tree at base carries EIGHT agent files — adversary, bench-measurer, code-reviewer,
document-writer, increment-builder, increment-designer, mechanism-critic,
standards-governor (`ls .claude/agents/`; each carries exactly one `model:` line,
`grep -c '^model:'` = 1 for all eight). Obligation 14's own "seven files" phrasing is stale
at base. This change rewords the row count-free ("every agent file") so the row cannot
drift again, and the test globs the directory, count-agnostic by construction.

## 5. Pre-committed acceptance rule (written before any measurement)

**SHIP** if both:

- **M1** — the pin-declaration test is green on main's agent set (this diff touches no
  `.claude/agents/` file, so the branch's run IS main's input set for this test), and
  RED-demonstrates under the named mutation: in a scratch copy of the agent tree plus the
  test, delete one agent's `model:` line → pytest exits non-zero with output naming the
  file.
- **M2** — in `docs/internal/review-rubric.md`, occurrences of "vendor"/"cross-vendor"
  (the tokens as written, case-insensitive; the pre-existing "vendored" at `:49`, `:93`,
  `:182` is the standards-corpus lexeme — counted and reported separately, never a
  diversity claim) are confined to the new sentence's install-property disclosure
  ("never vendors") and its single sibling-fleet naming ("different-vendor",
  "cross-vendor"), and no sentence in the file binds the repository to a model- or
  vendor-diversity property.

**KILL** if the test passes with the pin deleted (it pins nothing), or any rubric sentence
still claims model or vendor diversity for repository-configured lanes.

**NOT MEASURED and NOT PROXIED:** a model's blind spots; refute-lane defect-detection
quality; actual vendor divergence per install. The mechanism buys pin visibility and claim
honesty only — nothing in this increment measures whether a second pass finds defects.

## 6. Deferrals, with homes and reopen triggers

- **D1 — mandating the sibling-fleet pass on every Tier-3** (dispatching the refute to
  `.codex/agents/` when present becomes a MUST): deferred to a follow-on issue. Reopen
  trigger: a Tier-3 merge ships a defect both in-repo passes missed while the rubric's
  DEFER path was never taken. Note: `.codex/agents/` is installation wiring, not a tracked
  repo artifact — it exists on the audit installation (seven TOML agent definitions) and
  the rubric clause is conditional on its presence by design.
- **D2 — a machine-readable lane-model ledger field** (each refute run records its model
  string as data, not prose): deferred; the documentation of the deferral is this record.
  Reopen trigger: a report's quoted model string diverging from the routing log.

## 7. Risks

- The sibling-fleet clause could be read as a soft requirement — mitigated inside the
  sentence itself by "never a requirement every contributor can meet".
- The declaration test is presence-only — stated in its docstring and §3.2.
- The refute report's model string is self-reported — verbal evidence, an audit trail, not
  a gate (the sentence says so).

## 8. Privacy

This repository is public. No file, tracked or untracked, names the audit installation's
router, vendors or model IDs: the install evidence lives only as the vendor-neutral
statement in the header paragraph ("both the producing and refuting pins resolved to the
same model and vendor"), and the rubric sentence names no installation at all.
