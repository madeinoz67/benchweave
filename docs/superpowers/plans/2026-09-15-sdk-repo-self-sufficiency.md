# SDK Repository Self-Sufficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fresh clone of `benchweave-sdk` a first-class project: docs, memory system (same `benchweave` vault, `sdk`-tagged), code-reviewer, `.claude`/MCP wiring, gortex tracking, cross-linked READMEs.

**Architecture:** Port-and-adapt from the main repo. Every artifact that moves gets exactly one home; the main repo links across. Spec: `docs/superpowers/specs/2026-09-15-sdk-repo-self-sufficiency-design.md`.

**Tech Stack:** Node .mjs hooks (bun/node), MuninnDB MCP at `http://127.0.0.1:8125/mcp`, gortex daemon, markdown docs.

## Global Constraints

- Two-repo discipline: SDK-side commits land in the SUBMODULE repo first (push it), then a main-repo pointer commit; main-side doc changes are their own main commit. Both repos' gates green before each commit.
- Secrets NEVER in repo files: the MCP token is referenced as `${MUNINN_BENCHWEAVE_KEY}` (lives in `~/.claude/settings.json` env only).
- Every proposal from the SDK repo carries the `sdk` tag (validator-enforced).
- Standards/contract docs stay main-side (canonical corpus, PR #8's authority).
- rtk fabricates pytest output — `rtk proxy … -p no:warnings` for evidence. Node hook tests: `node --test .claude/hooks/tests/*.test.mjs`.
- Post-commit hook (`gortex enrich churn`) is minutes-slow and can hang after landing — chain commits, background near 600s, verify via git log/status in BOTH repos.
- This session's working checkout is benchweave-ui; the SDK-side files are edited via the submodule path `packages/sdk/…` (equivalent to the standalone clone — same repo). The standalone clone `~/Documents/src/benchweave-sdk` is used only for the fresh-clone verification (Task 4).

---

### Task 1: Documents move + cross-linked READMEs

**Files:**
- Move: `docs/plugin-sdk.md` (main) → `packages/sdk/docs/plugin-sdk.md` (SDK repo)
- Create: `docs/plugin-sdk.md` stub (main, links to SDK repo copy)
- Modify: `README.md` (main, sister-repo block), `packages/sdk/README.md` (reciprocal block), `docs/project-index.md` (main, SDK docs pointer)

**Interfaces:** Produces the doc-home map AGENTS.md references in Task 3.

- [ ] **Step 1:** Grep main for references to `plugin-sdk.md` (`docs/development.md`, `README.md`, `AGENTS.md`, `docs/project-index.md`, code comments) — each either updates to the absolute GitHub link or gains the stub path (prefer stub path for in-repo links).
- [ ] **Step 2:** `git mv docs/plugin-sdk.md` is NOT possible across repos — copy the file into `packages/sdk/docs/plugin-sdk.md` (verbatim), then `git rm docs/plugin-sdk.md` main-side after writing the stub. Commit SDK side first: `docs: adopt the plugin SDK guide`, push submodule; then main: stub + README sister block + project-index pointer + submodule pointer in one commit `docs: SDK guide moves to the SDK repository`.
- [ ] **Step 3:** README sister blocks — main: a short section naming `madeinoz67/benchweave-sdk` (role: offline SDK tooling; mounted at `packages/sdk` as a submodule; its own CI). SDK README: reciprocal (role: this is the SDK; the gateway and canonical standards live in the main repo; submodule relationship). Keep each under 8 lines.
- [ ] **Step 4:** Verify: all in-repo markdown links resolve (`grep -rn "plugin-sdk" --include="*.md" .` shows only the stub + absolute links); main gates green (`uv run ruff check .`, `uv run mypy`, targeted pytest for docs-touching suites — full suite if any test reads the moved path; `make check-sdk-standards`).

### Task 2: Memory system port with `sdk`-tag enforcement

**Files (all SDK repo, under `packages/sdk/`):**
- Create: `.claude/hooks/memory-propose.mjs`, `memory-drain.mjs`, `memory-freshness.mjs`, `ledger-guard.mjs` (port from main, adapting paths), `.claude/memory-protocol.md`, `.claude/hooks/tests/` (ported tests), `.gitignore` additions (memory ledger + receipts, mirroring main's ignore lines)

**Interfaces:** Consumes main's hook implementations (read them first — they resolve repo root via `git rev-parse`). Produces: proposals carrying `sdk` tag; drain to vault `benchweave` at `http://127.0.0.1:8125/mcp`.

- [ ] **Step 1:** RED: a test asserting `memory-propose.mjs` REJECTS a proposal without the `sdk` tag (port main's tag-validation test, add the sdk-specific case).
- [ ] **Step 2:** Port the hooks (they are repo-relative already — verify no hardcoded main paths); add the `sdk`-tag check to the validator with an error naming it.
- [ ] **Step 3:** Port `memory-protocol.md`, editing: drain target (same 8125/vault `benchweave`), the mandatory-`sdk`-tag rule, the review-findings-persist rule (carried verbatim), and "one ledger per repository" scoped to the SDK repo.
- [ ] **Step 4:** Wire lifecycle hooks in `packages/sdk/.claude/settings.json` (PreCompact/SessionEnd/Stop → drain with `--base http://127.0.0.1:8125/mcp`; SessionStart → freshness check) mirroring main's `.claude/settings.json` hook commands with corrected paths.
- [ ] **Step 5:** `node --test .claude/hooks/tests/*.test.mjs` green (run from the SDK repo root); live round-trip: propose a tagged record, drain, `muninn_recall` shows it in vault `benchweave` with the `sdk` tag.
- [ ] **Step 6:** SDK commit `feat(memory): ledger with sdk-tagged proposals draining to the benchweave vault`, push; main pointer commit.

### Task 3: code-reviewer, AGENTS.md/CLAUDE.md, `.mcp.json`

**Files (all SDK repo):**
- Create: `.claude/agents/code-reviewer.md`, `AGENTS.md`, `CLAUDE.md`, `.mcp.json`

**Interfaces:** Consumes the doc-home map (Task 1) and memory rules (Task 2).

- [ ] **Step 1:** `code-reviewer.md` — adapt main's (read it first): scope = packaging/preview/scaffold/CLI + standards-sync invariants (lock↔tree, stamps, two-repo discipline, refusal prefixes); gates = `uv run ruff check .`, `uv run mypy` (SDK pyproject config), SDK self-check `benchweave-sdk sync-standards --check`; tests note (suite lives main-side; run via parent checkout when there); never-posts/never-merges; closing memory step with `sdk` tag.
- [ ] **Step 2:** `AGENTS.md` — memory rules (ledger, tags incl. mandatory `sdk`, findings-persist), gortex-first mandate, two-repo discipline, doc-home map. `CLAUDE.md` — thin pointer + gortex mandate (mirror main's CLAUDE.md shape).
- [ ] **Step 3:** `.mcp.json` — `muninndb-benchweave` server, streamable-http `http://127.0.0.1:8125/mcp`, header token `"${MUNINN_BENCHWEAVE_KEY}"`. NO literal key material.
- [ ] **Step 4:** Verify: `python3 -c "import json; json.load(open('.mcp.json'))"` parses; secrets scan of the whole diff (`grep -rE "mk_|mdb_|gorag_|ghp_|sk-|Bearer " .claude .mcp.json` → zero hits); SDK CI workflow green locally (ruff/mypy/self-check still pass — the new files must not break the build; `.claude/` is not in the wheel path, confirm hatch ignores it).
- [ ] **Step 5:** SDK commit `feat(repo): reviewer agent, agent conventions and MCP wiring`, push; main pointer commit.

### Task 4: Gortex tracking + fresh-clone verification + close-out

- [ ] **Step 1:** `cd ~/Documents/src/benchweave-sdk && git pull` (the standalone clone now has everything); `gortex track` it; probe: one graph read via the daemon for the SDK repo path.
- [ ] **Step 2:** Fresh-clone simulation in a temp dir (`git clone ~/Documents/src/benchweave-sdk /tmp/sdk-fresh`): assert docs/plugin-sdk.md, .claude/hooks/memory-propose.mjs, .claude/agents/code-reviewer.md, .mcp.json, AGENTS.md, CLAUDE.md all present; run the hook tests from the clone; propose→drain round-trip from the clone lands `sdk`-tagged in the vault.
- [ ] **Step 3:** Force-add the spec main-side (`git add -f docs/superpowers/specs/2026-09-15-sdk-repo-self-sufficiency-design.md` + this plan), commit `docs(spec): SDK repo self-sufficiency design and plan`.
- [ ] **Step 4:** Both repos' gates + `make check-sdk-standards` green; memory proposal summarising the arc (tags: sdk, repo-setup).
- [ ] **Step 5:** Open the main-repo PR (`feat: SDK repository operational self-sufficiency`) with the acceptance checklist; push branch (do not merge).

## Self-Review

1. **Spec coverage:** docs (T1), memory+tag (T2), reviewer/conventions/mcp (T3), gortex+verification+close (T4) — all seven spec components mapped; acceptance criteria all covered.
2. **Placeholders:** none — steps name exact files and commands.
3. **Type consistency:** vault `benchweave`, base URL, and the `sdk` tag are named identically in every task.
