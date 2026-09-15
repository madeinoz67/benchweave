# SDK Repository Operational Self-Sufficiency — Design

Date: 2026-09-15 · Status: approved design (brainstormed with principal), pre-implementation

## Problem

The standards migration (PR #8) moved the SDK's *content* into
`github.com/madeinoz67/benchweave-sdk` but not its *operating environment*. A fresh
clone of the SDK repo gets code and CI, but: no SDK-authored documents; no memory
system (sessions leave zero durable findings); no code-reviewer agent; no `.claude`/MCP
wiring; no gortex indexing. The SDK repo is not yet a first-class project.

## Decisions made with the principal

1. **Same vault, tagged by origin.** The SDK repo drains to the existing `benchweave`
   MuninnDB vault (one project brain); every proposal originating in the SDK repo MUST
   carry the `sdk` tag, enforced by the SDK repo's proposal validator.
2. **Docs: move + cross-link.** SDK-authored documents move into the SDK repo
   (single home each — no competing copies); the main repo links across; **both repos'
   README/index point at each other** with a short "sister repository" block.
3. Reviewer, memory hooks, MCP wiring, gortex tracking, and AGENTS/CLAUMD conventions
   as presented (no forks raised).

## Components

### 1. Documents — move + link

- `docs/plugin-sdk.md` moves to the SDK repo (`docs/plugin-sdk.md` there). The main
  repo replaces it with a one-paragraph stub linking to the SDK repo's copy (path
  anchors stay valid for readers following old links).
- Standards/contract docs stay main-side (they are the canonical corpus the
  standards-manifest pins — already settled by PR #8).
- Main `README.md` gains a sister-repository block linking `madeinoz67/benchweave-sdk`;
  the SDK repo's `README.md` gains the reciprocal block linking back, each stating the
  other's role (gateway+canonical standards vs SDK tooling) and the submodule
  relationship.
- `docs/project-index.md` (main) references the SDK repo for SDK documentation.

### 2. Memory system — port with origin tagging

- Port from main: `.claude/hooks/memory-propose.mjs`, `memory-drain.mjs`,
  `memory-freshness.mjs`, `ledger-guard.mjs` (if present), `memory-protocol.md`, and
  the hook tests under `.claude/hooks/tests/`.
- The SDK repo's `memory-propose.mjs` validator additionally REQUIRES the `sdk` tag on
  every proposal (mirroring the ≥1-tag rule; the error names the missing tag).
- Drain targets the same instance: `--base http://127.0.0.1:8125/mcp`, vault
  `benchweave`, on PreCompact/SessionEnd/Stop — identical trigger wiring.
- The SDK repo's `memory-protocol.md` carries the same review-findings-persist rule
  and the `sdk`-tag convention.

### 3. code-reviewer agent

`.claude/agents/code-reviewer.md` in the SDK repo, adapted from main's:
scope = SDK surfaces (packaging/preview/scaffold/CLI code, standards-sync invariants,
two-repo discipline); gates = `uv run ruff check .`, `uv run mypy` (its pyproject
config), `uv run pytest` where tests exist (note: the SDK test suite still lives
main-side — the reviewer states this and runs main's targeted tests via the parent
checkout when operating from there); same never-posts/never-merges contract; same
closing memory step (proposals carry the `sdk` tag).

### 4. `.claude` + MCP wiring

- `packages/... ` — SDK repo root gains `.mcp.json` naming the `muninndb-benchweave`
  server (streamable http, `http://127.0.0.1:8125/mcp`) with the header token
  referencing `${MUNINN_BENCHWEAVE_KEY}` — the key lives only in
  `~/.claude/settings.json` env, never in any repo file.
- `.claude/settings.json` (SDK repo) wires the drain hooks to the lifecycle events,
  mirroring main's hook commands with the correct relative paths.

### 5. Gortex tracking

Checked live at spec time: the daemon's registry holds `benchweave-ui` (which indexes
the `packages/sdk` submodule path) but NOT the standalone `~/Documents/src/benchweave-sdk`
clone — the daemon's repo list (go-parts, gortex, BenchWeave, benchweave-ui, muninndb,
…) excludes it. `gortex track ~/Documents/src/benchweave-sdk` gives the standalone
clone its own logical graph so sessions running there get the same read/write mandate;
the submodule path stays covered under benchweave-ui. Verified with a probe read after
tracking.

### 6. AGENTS.md / CLAUDE.md (SDK repo)

- `CLAUDE.md` — thin: points at AGENTS.md, carries the Gortex mandate and the
  two-repo discipline (submodule commits first, push, then main pointer).
- `AGENTS.md` — the memory rules (ledger, ≥1 tag AND `sdk` tag, review-findings
  persist), the gortex-first read/write mandate, the two-repo discipline, and the
  docs-home map (what lives here vs main).

### 7. Verification

- A fresh-clone simulation: in a temp clone of the SDK repo, the memory hook
  round-trips (propose → drain → recall in the `benchweave` vault carrying the `sdk`
  tag).
- Both READMEs render the sister blocks; all cross-links resolve.
- `gortex` serves graph queries for the SDK repo.
- Main repo gates stay green after the doc moves (no main test references the moved
  doc's path — verified by grep before moving).

## Acceptance criteria

- [ ] A fresh clone of `benchweave-sdk` contains: SDK docs, memory hooks + protocol,
      code-reviewer, `.mcp.json`, AGENTS/CLAUDE conventions.
- [ ] Proposals from the SDK repo land in the `benchweave` vault tagged `sdk`.
- [ ] Both READMEs cross-link with role descriptions; moved docs have single homes
      with main-side stubs.
- [ ] Gortex serves the SDK repo's graph.
- [ ] Main repo gates green after the moves; no broken intra-repo links (grep proof).
- [ ] SDK repo CI green (its own workflow) with the new files in place.

## Non-goals

- No SDK test-suite migration (tests stay main-side; recorded as a known follow-up).
- No changes to the standards-sync mechanism itself (issue #9 covers its follow-up).
- No secrets in-repo, ever; the MCP key stays in user settings.
