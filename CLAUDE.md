@AGENTS.md

<!-- Codanna section for CLAUDE.md — author: Stephen Eaton -->

## Code navigation: Codanna

This repo is indexed by Codanna (local symbol graph + semantic search).

If the location of a symbol or the shape of a module is not already known, find it with
Codanna before reading files or grepping. A file already named in the issue or the error
is not a search: read it. A hook nudges once per session when a search starts with `rg` or `grep`
before Codanna has been used, so the rule is not something to remember.

### Which interface
- **Main session:** use the `mcp__codanna__*` tools. The server runs `serve --watch` from the main checkout and stays current as files change.
- **Subagents:** use the `codanna` CLI through Bash (the `x-ray` skill wraps it). The CLI reads the index in its current directory, so it stays correct inside worktrees.
- **Whole-codebase shape** (module map, hubs, which modules talk to each other, history): use the `graph` skill.

### Workflow
1. **Rephrase first.** Search for what is meant, not the literal words (e.g. "the login stuff" → "authentication session token validation").
2. **Locate:** semantic search with context, limit 5. Focus on results with score > 0.6. Use `find_symbol` for exact names and `search_symbols` for partial ones.
3. **Read narrowly:** read only the returned line range (`sed -n 'A,Bp' file` or Read with offset/limit).
4. **Expand:** follow 1–2 important relationships per result (`retrieve describe`, callers, calls). Run `analyze_impact` **before** changing any public symbol, signature, or shared function.
5. **Docs:** `search_documents` for project docs and markdown.
6. **Refine or fall back:** if the scores are weak, rephrase once. Use `rg` for exact strings, config keys, HTML/CSS/templates, and any language Codanna doesn't parse.

CLI equivalents:
- `codanna mcp semantic_search_with_context query:"..." limit:5 --json`
- `codanna mcp find_symbol <Name> --json`
- `codanna mcp find_callers <Name> --json`
- `codanna mcp analyze_impact <Name> --json`
- `codanna retrieve describe <Name|symbol_id:N>`
- `codanna retrieve calls <Name>`

Add `lang:<language>` to a search to narrow it by language.

### Calibration: the graph narrows scope, source confirms behavior

Graph queries *narrow scope*; they do not *replace reading the implementation*. The graph
tells you **where** the logic lives and **what** connects to it; the source tells you
**how** it behaves. For the symbol you are about to change or depend on, read its full
body — do not act on a one-line summary alone.

Be especially deliberate with **behavior-critical code** — database migrations, retry /
fallback / error-recovery paths, compatibility shims, concurrency-sensitive sections, and
the tests that pin them. For these, read the real implementation. Reserve summaries for
breadth (surveying many symbols); use full source for the few you are about to commit to.

### Rules
- Codanna results are navigation hints, not ground truth. Confirm against the file before editing.
- Before renaming or changing a signature, list every caller in your plan.
- If a Codanna command exits with code 7 (stale index), run `codanna index .` in the current checkout and retry.
- Prefer `symbol_id:N` over names when available; it avoids ambiguity.
- Guessing `pytest -k` filters is the anti-pattern this section replaces — `analyze_impact` names the affected symbols, and the §3 lanes remain the verification.

### Orca worktrees
- In Orca, each agent is a full Claude Code session whose working directory is its own worktree. Orca's `scripts.setup` builds that worktree's Codanna index, and the `.mcp.json` server indexes the worktree, so `mcp__codanna__*` tools are correct there.
- If a Codanna tool reports a missing or stale index (exit code 7) right after the worktree opens, setup may still be running: wait, or run `codanna index .` once.
- Never share `.codanna/` between worktrees (symlink or `sharedDirectories`).

### Subagents and worktrees
- A subagent in `.claude/worktrees/*` must **not** use `mcp__codanna__*`. Those tools read the main checkout's index, which doesn't match the worktree's files.
- Worktree subagents build their own index first (`codanna index .` from the worktree root), then use the CLI.
- Never point the CLI at the main checkout from inside a worktree (`--config ../..`, `cd` to the repo root). Worktree isolation blocks it anyway.
- Delegate read-only investigation to `codanna-explorer` and isolated edits to `codanna-implementer`.

## Findings that outlive the session

Durable, non-obvious findings (measured numbers, decisions and why, defect *patterns*, traps
that look safe) go through the proposal ledger rather than ad-hoc `muninn_remember`:

```sh
node .claude/hooks/memory-propose.mjs <<'JSON'
{"concept":"short label","content":"the fact itself, self-contained","summary":"one line","type":"fact","tags":["gotcha"],"source":"main"}
JSON
```

- **Tags are required (>= 1) on every vault write**, ledger or direct MCP — untagged memories
  are invisible to tag-filtered recall. The validator rejects tag-less proposals.
- Subagents that write findings over MCP (code-reviewer, adversary probes) follow the same
  rule; brief them with it.
- The bar for what merits a proposal, and the do-not-propose list: `.claude/memory-protocol.md`.
- The drain moves the queue into the `benchweave` vault on PreCompact / SessionEnd / Stop.
  **Codex sessions:** no drain hook fires there — run
  `node .claude/hooks/memory-drain.mjs --base http://127.0.0.1:8125/mcp` before ending a
  session that queued proposals.
- **Vault routing:** every memory for this project belongs in the `benchweave` vault — never the
  default memory vault. Direct `muninn_remember` over MCP goes through the project server
  `muninndb-benchweave` when approved; the ledger is the fallback that survives without it,
  and the drain delivers it.

<!-- gortex:communities:end -->

---

This file governs how AI agents work in this repo: what BenchWeave *is*, the principles
that must never be violated, and how to write and review changes that fit the project.
The deep reference lives in `docs/internal/` — this file is the index and the
non-negotiables.

## 1. What BenchWeave is

BenchWeave is a **local test-bench gateway for reusable instrument and DUT plugins**:
Python 3.13, `uv`, hatchling, strict mypy. Its one-line promise, from the architecture
doc, is load-bearing — every change is measured against it:

> **A plugin from anywhere runs on a bench here, with checks whose results mean the same
> thing no matter which host ran them.**

The three clauses map to real subsystems:

- **a plugin from anywhere** → the OTDP device-plugin ABI, the registry's pinned
  dependency closure, trusted-plugin admission.
- **runs on a bench here** → the control core: admission, binding, the eight-kind
  procedure executor, the protective transition, the single-writer store.
- **the same results on any host** → the vendored standards corpus (sha256-pinned,
  machine-checkable), digest-verified admission, evidence-exact run records.

If a change makes a bench behave less like this — a check that means different things on
different hosts, a protective path that can be vetoed, a run record that launders
ambiguity — it is wrong even if the suite passes.

### Architecture map

The subsystem/package component map lives in `docs/internal/architecture-map.md` — read it
when a change spans subsystems.

Reference docs: `docs/internal/invariants.md` (hard invariants, CTL/STO/CON/REG),
`docs/internal/review-rubric.md` (the gated review protocol),
`docs/internal/drift-and-obligations.md` (cross-surface sync obligations + the CI map),
`docs/smart-test-gateway-decisions.md` (why the project is the way it is, A01–A14).

## 2. Core principles (the lens for every change)

Each traces to a decision record (`docs/smart-test-gateway-decisions.md`) or a
`docs/internal/` doc.

1. **Evidence over assertion (A06).** A transport success is not completed physical work;
   ambiguous outcomes stay ambiguous on the wire (`dispatch_state` UNKNOWN, `interrupted`
   runs), duplicate suppression sits at the gateway boundary, and recovery reconciles
   before dependent actions proceed.
2. **Protection and completion never depend on continued AI judgement (A04).** An AI agent
   may drive the interfaces; the protective transition and the run's bounded authority
   must not require one to keep working. A client cannot silently promote an ordinary
   operation to autonomous execution.
3. **Qualified, not assumed (A02).** Neither low voltage nor an instrument's rating
   establishes acceptable energy. Missing requirements block control; numeric envelopes,
   safe transitions and response times are commissioned per bench from qualification
   evidence — never hardcoded constants tuned on one bench.
4. **One controlling procedure per bench (A03).** Explicit resource ownership and
   scheduled observations; the one-writer store hold makes two coordinators
   structurally impossible, not merely discouraged.
5. **Bounded procedures (A12).** Versioned JSON documents, sequential actions, fixed-count
   loops, lexical references, explicit deadlines. A shared or generated procedure can
   never rewrite its operating envelope; all endings take the approved safe transition
   and terminal pass requires verified final safety.
6. **One core contract behind REST and MCP (A13).** Transports are adapters over typed
   operation/result contracts and durable run identity — and behavior is pinned against
   the frozen contract (`standards/interface/0.1.0/interface-contract.md`), never against
   the sibling transport. Parity tests are not contract tests.
7. **Audit failure constrains new work (A07).** Refuse new energising actions when their
   intent cannot be recorded, while protective action and the approved active-procedure
   response continue — accountability without making evidence storage a dependency of
   protection.
8. **Features land as minimal, reviewable increments referencing their design (the
   `increment` skill).** Each names what it defers. Design records are committed
   (`.claude/deep-review/`) so pre-committed acceptance rules are provably pre-committed.
9. **Extend proven in-tree mechanisms over inventing new architecture.** Find the
   precedent first; new architecture needs a justification the precedent can't satisfy.
10. **Verify claims independently; severity can go up, not just down.** Never take a
    report's or a PR description's claim on faith.
11. **Honest negative results are first-class.** A killed idea on measured evidence is a
    real result, not a failure to have something to show.
12. **Claim discipline (`docs/internal/review-rubric.md` G4).** A set named in prose is
    regenerable from a mechanism; a guard states what it does not catch;
    *cannot/never* needs the structural reason inline; every number carries its
    denominator and says whose measurement it is. Full form:
    `docs/internal/review-rubric.md` G4.
13. **A standards version bump copies, never moves** (`standards/GOVERNANCE.md`):
    the old version dir and its corpus-manifest rows stay in the tree,
    digest-frozen; all edits land in the new version's copy, whose rows cite the
    old corpus path as `source`.

## 3. How we work

**Verify, don't assume.** For any non-trivial change:

1. **Confirm the commit you're on.** The working checkout can be stale; run
   `git branch --show-current` / `git log --oneline -3` and diff against `main` before
   asserting what the code does. Work happens on working branches — never commit to
   `main` directly. When in doubt, work in a fresh worktree off `origin/main`.
2. **Run the real gates, not the diff (#247).** Two lanes, both with
   `UV_PROJECT_ENVIRONMENT=venv`:
   - **FAST lane — every commit, no exemptions.** Test-only and docs-only commits
     included; a "docs-only skips ruff" exemption is the hole that shipped the F841
     miss below. Bare `uv run ruff check .`, fresh-cache bare `uv run mypy` (**bare,
     config-driven** — explicit path args silently drop `packages/sdk/src` from the
     build; fresh cache = `rm -rf .mypy_cache` or `--no-incremental`), and the focused
     `uv run pytest` for the touched modules plus `tests/faults/` for anything touching
     `state/`, `control/`, or concurrency. **If you touched a file pinned in
     `tests/win_core_manifest.json`, add its ~6 s check to this lane** —
     `uv run python scripts/ci/win_core_manifest.py --refresh` then the same script's
     `--check`, so count motion is caught at your commit instead of at the end of the
     battery. Exit 1 is the drift you must refresh; exit 2 is fail-closed for everything
     else — a noisy collection (untracked duplicates can do it), or a manifest that is
     absent, malformed or schema-mismatched.
   - **Full battery — once, immediately before push.** The fast triple plus the full
     suite and both standards tripwires. A batch (a row-call fold) lands as ONE commit
     carrying per-row RED evidence in its message, with one battery.
   - **Evidence discipline is part of the gate definition.** Gates read TRUE exit
     codes — unpiped, `PIPESTATUS`, or output-to-file (`cmd | tail -1; echo $?` echoes
     tail's status, not the command's); any claimed mypy result comes from a fresh
     cache. Read counts from `--junitxml` attributes or exit codes, never from an
     output-filter summary line.
   Why both 2026-09-24/25 incidents stay caught: the F841 ruff miss (#176) was lint in
   test code — invisible to pytest by construction — so the no-exemption fast lane
   catches it at the offending commit, EARLIER than the adversary pass that found it
   an hour later; the stale-evidence mypy miss (#146) was an evidence failure (piped
   exit + warm cache), not a coverage gap, so the true-exit-code and fresh-cache rules
   close it, not run frequency.
3. **RED-sanity-check bug fixes.** The test must be shown to *fail without the fix*;
   `no tests ran` is a FAILED check (pytest exits 5 when it collects nothing) — look for
   the collected count, not a green run.
4. **Walk the obligations.** `docs/internal/drift-and-obligations.md` is the list; the
   path-shaped ones additionally warn via `.claude/hooks/drift-guard.mjs` (marked 🪝 in
   that doc) — a reminder, not a gate, and no substitute for walking the list.
5. **Merge on the full rollup, never a filtered view (#181 R1).** `gh pr checks
   --watch | tail` hides failing lanes and masks the exit code (2026-09-23: two
   merges landed with three red lanes). Read the COMPLETE `gh pr checks <n>` output
   and assert zero `fail` and zero `pending` before merging; a background
   CI-watcher's exit is not the verdict. `scripts/merge-verified.sh [owner/repo] <pr>`
   is this gate as a tool — it watches, prints the full rollup, refuses on any
   red, pending, or empty rollup, and only then merges.
6. **Pre-flight before design on a tracked issue (#181 R2).** Before starting design
   or build work: `git fetch origin`, list the remote branches touching the planned
   paths, and check the sibling repo's open/recent PRs — only then design. A brief
   can postdate pushed or merged rival work (2026-09-23: the #147 rival-design
   collision).
7. **Parallel scratch paths carry a nonce (#181 R4).** Scratch worktree names carry
   the agent name plus a nonce; run `git worktree list` before any `worktree
   remove` while parallel agents are active (2026-09-23: one agent's cleanup
   deleted another's live worktree).

**Keep CI fast.** The job map is in `drift-and-obligations.md`; prefer unit and fault
tests, reach for end-to-end proof only when a change genuinely needs it, and never
balloon the pipeline to prove a point a table-driven test could make.

## Documentation register (ASD-STE100)

Operator-, user- and developer-facing published documentation is written in ASD-STE100
Simplified Technical English; internal engineering records (design records, review
rubrics, invariants, tracker text) keep the engineering register, out of scope — STE's
controlled language is the wrong instrument for them. Never change technical content to
obey a register rule. The mechanism: dispatch the `document-writer` agent
(`.claude/agents/document-writer.md`) for any documentation leg that authors or rewrites
operator-facing prose.

## 4. This repository is public

Measure on real benches and real run histories; **never name them**. The corpus a
measurement ran on is not ours to publish — it belongs to an operator, a client, or
another product, and naming it links them to this project permanently.

The rule, in committed content — source, tests, comments, design records, commit
messages, **and filenames**:

- Refer to a measurement corpus as **"a real bench"**. Keep the numbers; drop the name.
- Use invented names in fixtures and examples — not a real colleague, client, contact,
  DUT serial, or another product's module names.
- No client, tenant, or employer identifiers; no pricing or commercial terms.
- Community protocol sources and hardware provenance that are already public may be
  cited as provenance, not claimed as evidence.
- If a design record can't make its point without those, it isn't publishable —
  `.claude/deep-review/README.md` has the triage rule and the `private/` convention.

Git history is forever and a scrub of the tip is not a scrub. Getting it right before the
commit is the only version of this that works.

Machine screen (issue #518): `.claude/hooks/name-screen.mjs` — `make hooks` installs the
pre-commit/pre-push gate, a PreToolUse entry blocks at authoring time, and the
`name-screen` CI job runs the public tier over added lines; the optional local list lives
at `$BENCHWEAVE_NAME_LIST` (default `~/.config/benchweave/name-screen.list`), outside
every repo of the family.

---

## The code-review agent

`.claude/agents/code-reviewer.md` is the repo's resident reviewer — correctness, the
hard invariants (`docs/internal/invariants.md`), and cross-surface drift, with its own
verify-build-test protocol. Use it (or the `/code-review` skill) when reviewing a change,
and proactively before opening a PR. It routes by what the diff touches and follows
`docs/internal/review-rubric.md` as the authority.

Maintainers may have additional local-only tooling (issue triage, review orchestration) that
is not part of this repo.

---

## Attribution

Do not add "Generated with Claude" / Anthropic attribution to any PR body, commit message,
issue, or code comment.
