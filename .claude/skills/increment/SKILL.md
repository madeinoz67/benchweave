---
name: increment
description: The repeatable build loop BenchWeave holds itself to — design, build RED-first, independently vet, adversarially refute, MEASURE real value on real data, then PR/CI/land. Use for any non-trivial feature or fix ("build X", "add Y", "next increment"). Encodes the discipline that keeps us shipping real, measured value instead of smoke-and-mirrors.
---

# increment — the BenchWeave build loop

This is the loop that ships qualified behavior: design before code, RED before GREEN,
refute before PR, measurement before merge. The north star: **a plugin from anywhere runs
on a bench here, with checks whose results mean the same thing no matter which host ran
them.** The bar for every increment: **commissioned-grade, evidence-backed, measured — no
smoke-and-mirrors, no unverified claims about hardware.**

## When to use

Any non-trivial feature or fix. For a one-line mechanical edit, just do it. For anything
that touches the control path, admission, state, contracts, standards, the registry seam,
or a public surface, run the loop.

## The non-negotiable principles (the lens)

1. **Measure, don't claim.** Every increment ships with a before/after on real data (run
   history, event streams, the fixture lattice) that quantifies value. "It works" is not a
   result; "8/8 runs recovered to a truthful `interrupted` record where the old path
   reported 0/8" is. If you can't measure it, you don't understand it yet.
2. **Defer-if-buggy over ship-to-hit-a-milestone.** If a refute pass finds a real defect
   you can't cleanly fix, ship the clean core and DEFER the broken part to a
   properly-designed increment. Name the deferral in the PR.
3. **Honest negative results are first-class.** If the measurement shows no meaningful
   value, or a gate can't be cleared, HOLD and report — don't dress up noise. A killed
   idea is a real result.
4. **Never trust a sub-agent's "green."** Independently re-run ruff, mypy and pytest
   yourself, and read the counts from the run, not from a summary line.
5. **Minimal, reviewable increments referencing their design.** No sprawling PRs. Name
   what you defer. Design docs live in `.claude/deep-review/` — committed artifacts, so
   the pre-committed acceptance rule is provably pre-committed (see its README for the
   public/private triage rule).
6. **The system records evidence; the caller concludes.** Ambiguous outcomes stay
   ambiguous on the wire (decision A06): a timeout reports UNKNOWN, an interrupted run
   reports `interrupted`. Nothing in the control path collapses ambiguity into a clean
   answer, and no protective behavior depends on continued AI judgement (A04). An
   outcome without its evidence is a plausible-wrong answer — the worst failure class.

## The loop

1. **Design.** Spawn the `increment-designer` agent grounded in the REAL code (read,
   don't assume) plus the decision record (`docs/smart-test-gateway-decisions.md`) and
   the invariants (`docs/internal/invariants.md`). It must deliver: the mechanism, the
   minimal first-increment scope with explicit deferrals, precedent from proven in-tree
   mechanisms, invariant impacts, the MEASURABLE proof with a pre-committed acceptance
   rule, and top risks. DON'T-BUILD is an accepted outcome.
2. **Decide.** Read the design. Surface any genuine product-behavior fork to the owner;
   otherwise pick the defensible default and proceed. For a contested call, run the
   `panel` skill.
3. **Build, RED-first.** The `increment-builder` agent works in a fresh worktree off
   `origin/main` (`UV_PROJECT_ENVIRONMENT=venv`). For every behavior change: write the
   test, show it FAILS without the code, then implement. `tests/faults/` runs for
   anything touching `state/`, `control/`, or concurrency.
4. **Vet (you, independently).** `uv run ruff check .` and bare `uv run mypy` clean;
   focused `uv run pytest` for the touched modules plus the fault suite. RED-check the
   key guards discriminate (toggle off → fail) using a `cp` backup, NEVER `git checkout`
   on files with uncommitted work.
5. **Adversarial refute.** Spawn the `adversary` agent with a REFUTE mandate. **Tier-3
   per the review rubric (contracts, standards artifacts, persisted format, registry
   seam, fixture digests, concurrency, dependencies, the SDK submodule pointer) → the
   refute pass is mandatory.** Any diff touching `standards/`, contract locks, the SDK
   vendored tree, or version strings ALSO dispatches the `standards-governor` agent
   (tier-independent; #69) — a governance review that never ran is a skipped gate. For anything moving a deadline, threshold, digest rule or
   lease computation, also run the `mechanism-critic`. Reconcile: both clean → stands; a
   real evidenced defect → fix it; a genuine correctness split → DEFER to the owner. Fix
   every real finding, with RED-proven guards.
6. **Measure — the acceptance gate.** The `bench-measurer` agent proves real value on
   real data with a NON-GAMEABLE test. Prefer a control that fluff can't pass: a RED
   check (mechanism disabled → effect gone), and where correlation is involved, a
   timestamp-shuffle / permutation null. Report the number.
7. **Land.** PR into `main` (working branches only — never commit to `main` directly),
   title + body naming what shipped + what's deferred, referencing the design — and
   **every deferral in the body must cite an open issue, created at PR-open time if
   absent — an orphan deferral blocks the merge (reviewer-enforced; no mechanical
   gate yet)** (#69). Multiple PRs from one work use
   **PR stacks**: each dependent PR opens with base = its predecessor's branch (so it
   shows only its own delta); merge bottom-up, retargeting successors to `main` as
   their base lands. **A run is complete only when every PR it raised — in BOTH repos —
   is merged**; SDK PRs open stacked at pointer-commit time, not end-of-run. Watch CI
   to green (`gh pr checks --watch`). Merge when all-green and authorized; otherwise hand
   off. If a gate is red or a finding is unfixed, HOLD and report — do not merge.

## Contributor PRs

Don't bounce nitpicks back to a strong contributor, especially after multiple
round-trips. Either adjust their branch yourself (`maintainerCanModify=true`: merge
`main` INTO their branch, resolve, push — a merge commit, not a force-push) or merge and
do a small follow-up PR. Still hold the bar (Tier-3 refute, CI green). Serialize merges
that touch the same hot signatures — a parallel merge silently drops a feature once.

## Simulator first, real bench by commissioning

Prove mechanisms on the simulator plugins and the fixture lattice before any real
hardware is claimed. A real bench is a commissioned thing (decision A02): its numeric
envelope, safe transition and response times come from qualification evidence, not from
a control interface working. Never open a store a live gateway holds — the single-holder
lock exists for exactly that; at-rest commands (backup/restore) refuse while it is held,
and that refusal is the discipline working, not an obstacle to route around. Claims
about device behavior cite captured evidence or say `speculative`.

## Pipelining

While one increment's build/refute runs, design the next (agents notify on completion).
Keep the owner's roadmap and any contributor backlog both advancing. Run several loops in
sequence for a big push; stay in the loop between them.

**Parallelism is surface-aware (#69).** Dispatch increments in parallel only across
DISJOINT surfaces. Increments sharing a surface — `main`'s merge result, the SDK
submodule pointer, a proof-vehicle plugin, one standard's tree — serialize on it by
design: the second one **parks at review-complete** (not CI-green) and rebases onto the
merged predecessor exactly once. Before ANY push of a branch that bumps a standard or
moves the SDK pointer, run a **merge-result pre-check**: simulate the branch + current
`origin/main`, run the sibling rows' lane tests against that tree (CI tests the merge
result, not your base). Two distinct tripwires, not one: **(a) branch-side** —
`git diff origin/main...HEAD -- standards/` showing deletions means YOUR branch deletes
standards bytes, which is itself a copy-never-move violation regardless of base staleness;
**(b) stale base** — inside the merge-result tree, `git diff origin/main -- standards/`
(two-dot) showing deletions means the merge result drops main's standards state — your
base predates a sibling's merged bump and the branch must re-roll onto main.
