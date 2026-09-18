# Review rubric — the dependable-review protocol

This is the backbone of `code-reviewer`. It is written so that **even a weak model that
follows it literally produces a review you can trust**, because the judgment is offloaded to
mechanical evidence (ruff, strict mypy, pytest, the RED-sanity procedure) and to objective
routing rules, not to the model's insight. The model's job is to run the gates and attach
the evidence, or to escalate honestly when it can't.

Three ideas run the whole thing:
1. **Evidence, not opinion.** Every gate produces pasted command output or it did not happen.
2. **The system picks the depth.** Risk tier is decided by objective path/keyword rules.
3. **A hard confidence floor.** If a gate can't be satisfied with evidence, the verdict is
   DEFER, never approve-on-faith. Deferring is cheap and safe. A wrong merge is not.

---

## Step 0 — Confirm what you're reviewing (always)

- `git branch --show-current`, `git log --oneline -3`. Work happens on working branches
  (never directly on `main`); diff the branch against `main`. If the checkout looks stale,
  review in a fresh worktree off `origin/main`.
- **Read this rubric and the contract docs from `main`, not from the branch** (the branch may
  predate a docs update).
- Record the head SHA in your review. If you can't confirm the SHA you reviewed, stop.

## Step 1 — Pick the risk tier (objective, grep-driven)

Run the diff's file list through these rules, top to bottom. First match wins.

**TIER 3 — deep, mandatory second adversarial reviewer.** Any of:
- touches `src/benchweave/contracts/`, or anything under `standards/` (the interface
  machine-artifact home: `interface.schema.json`, `openapi.json`, `mcp-tools.json`,
  `operation-catalog.json`, `corpus-manifest.json`, `standards-manifest.json`), or any JSON
  Schema file
- touches the persisted-format surfaces: `src/benchweave/state/migrations/`,
  `src/benchweave/state/store.py`, `src/benchweave/control/documents.py` (the run/document
  schema)
- touches `src/benchweave/registry/` discovery, loading, collision, or policy behavior (the
  seam where third-party plugins enter the bench)
- touches the fixture digest lattice: `fixtures/registry/`, `catalogue.json`, or
  `scripts/registry/`
- the diff text contains any of: `threading`, `asyncio`, `subprocess`, `sha256`, `hashlib`,
  `migrate`, `recovery`, `protection`
- adds, removes, or re-pins a dependency (`pyproject.toml`, `uv.lock`)
- advances the `packages/sdk` submodule pointer

**TIER 2 — standard.** Any other change to Python logic under `src/`, `scripts/`, `tests/`,
`.github/`, or root config (`pyproject.toml`, hatchling config). Test-only changes sit here,
not in Tier 1 — the CI contract and the fixture lockstep live in the test tree.

**TIER 1 — light.** Only docs (`*.md`), comments, or web copy — and nothing that matches
Tier 3.

State the tier and the rule that triggered it at the top of your review.

## Step 2 — Evidence gates (run every gate in scope; attach real output)

Each gate is PASS only with pasted output. No output means the gate did not run, which means
you cannot APPROVE.

**G0 Secrets (all tiers, before anything else).** Scan the diff — source, tests, comments,
fixtures, commit message, and filenames — for `mk_`, `mdb_`, `gorag_`, `ghp_`, `github_pat_`,
`sk-`, `Bearer ` literals, and private paths. Any hit → **BLOCK**. This is the one finding
whose severity is never downgraded; a key in git history is unfixable after the fact, and a
scrub of the tip is not a scrub.

**G1 Static gates (all tiers).** `uv run ruff check .` and `uv run mypy` — **bare, never
with path args**: explicit paths override `[tool.mypy] files =` and silently drop
`packages/sdk/src` from the build (ci.yml did this once; fixed in fe45361). Run uv with
`UV_PROJECT_ENVIRONMENT=venv` or it silently creates a stray `.venv/`. This repo is
strict-mode: a new `Any` or an untyped def is a finding, not a style note. Any failure →
**BLOCK**.

**G2 Tests (Tier 2 and 3; Tier 1 if any test exists).** Run the focused tests for the
packages the diff touches; run the **full suite** for Tier 3 and for any
`.github/workflows/` change (cold, not warm-cache). Include `tests/faults/` when the change
touches `state/`, `control/`, or anything concurrency-shaped. Paste the tail. **Read the
counts from `--junitxml` attributes or the exit code, not from an output-filter summary** —
the rtk filter can print "No tests collected" over a fully green run (observed twice on this
repo). Any failure → **BLOCK**.

**G3 RED-sanity (any PR that claims to fix a bug, close a race, or add a guard).** Prove the
new test catches the thing:
- Revert ONLY the production fix in place (keep the new test), or check out the pre-fix state
  of the changed source file. Run the new test. It must go **RED**. Paste the failure.
- Restore the fix. Run it. It must go **GREEN**. Paste it.
- `no tests ran` is a **FAILED** RED check — pytest exits 5 when it collects nothing; look
  for the collected count, not just a green run.
- If you cannot produce red-then-green, the fix is **unproven** → you may not APPROVE
  (needs-work, or DEFER if you can't tell why). A test that passes both ways proves nothing.

**G4 Contract check (Tier 2 and 3).** Load `docs/internal/invariants.md` and apply every
group whose files appear in the diff (CTL/STO/CON/REG). For each invariant the diff touches —
plus the architecture contracts (`docs/smart-test-gateway-architecture-v1.5.md`) and any
behavior contract in the changed modules — grep the anchor in the LIVE code, confirm the
contract still describes the code, then state PASS or FAIL. If the doc's own text disagrees
with the live code, the **code wins** — flag the stale doc, don't enforce it. Review the
change's *claims* alongside: a set named in prose must be regenerable from a mechanism; a
guard must state what it does not catch; *cannot/never/may only* claims need the structural
reason inline, otherwise the claim says *is refused unless* and states its residual.

**G5 Cross-surface drift (all tiers).** Walk `docs/internal/drift-and-obligations.md` for
every touched surface. Any unmet obligation is a **required change**, not a nit.

*Do this mechanically, don't eyeball it — the fixture lattice is the one weak models miss.*
A diff that touches `fixtures/registry/`, the builder, or `catalogue.json` has changed the
pinned digest lattice, which the digest-pinning tests and CI's secret-materialised fixture
keys both consume: all four (fixtures ↔ builder ↔ catalogue ↔ tests) must move together,
and a rebuilt lattice without regenerated digests is silent drift that no test failure will
name for you. The same shape applies to every numbered obligation in the doc: absence of
the update is the finding even when the diff touches no `docs/`.

**G6 Adversarial refute (TIER 3 ONLY — mandatory).** A second, independent reviewer runs the
gates again AND actively tries to break the change: what input, ordering, crash point, or
concurrent caller makes it wrong? For a contract change: what previously-valid plugin or
fixture does it now reject? The repo's standing independent lane is the cross-vendor audit —
never the model that produced the change. The two reviews are compared:
- Both reach APPROVE with consistent evidence → APPROVE stands.
- The refuter finds a real, evidenced failure → needs-work.
- They disagree on a correctness or contract point and evidence can't settle it → **DEFER**.

## Step 3 — Verdict (bounded by the confidence floor)

- **APPROVE** — only if every in-scope gate PASSED with attached evidence, and (Tier 3) G6
  agreed. Nothing else earns an approve.
- **APPROVE WITH REQUIRED CHANGES** — gates pass but a G5 obligation or a small, named fix is
  outstanding. List them numbered.
- **NEEDS WORK** — a gate failed or a real defect was found.
- **DEFER (human)** — you cannot satisfy a gate with evidence, the Tier-3 panel is split, or
  the change turns on a domain a review can't settle: real-bench hardware timing or
  instrumentation semantics, DUT safety, licensing of vendored standards. **When you can't
  reach APPROVE or NEEDS-WORK on evidence, DEFER. Never guess, never approve-on-faith.**

## Step 4 — Anti-hallucination self-check (before you emit the verdict)

Answer these literally. Any "no" downgrades the verdict to DEFER:
- Did I attach real pasted output for G1, and for G2/G3 where in scope — counts read from the
  run itself, not an output-filter summary?
- If I claim a fix works, did I show the RED-sanity red-then-green output?
- If Tier 3, did a genuinely independent second pass (G6) run, and do I state its verdict?
- Did I verify each contract I cite against the live code, not just quote the doc?
- Did I append the full findings record — every severity, LOW and NIT included, each with its
  disposition (fixed / deferred / accepted-risk) — to the memory ledger
  (`node .claude/hooks/memory-propose.mjs`)?

A review that reaches APPROVE without the evidence its tier requires is itself invalid.
Re-run it or DEFER.

---

## Why this is safe enough to trust without a human on routine changes

The human doesn't disappear. The human is **escalated to only when the system is honestly not
confident** — a failed gate, a split adversarial panel, or a domain a review can't settle.
Everything else is approved on mechanical evidence that a weak model can produce as reliably
as a strong one: ruff either passes or it doesn't, strict mypy either accepts or it doesn't,
a reverted fix either reddens its test or it doesn't. The floor is what makes "you don't
review routine code anymore" a promise the system can keep instead of a hope.
