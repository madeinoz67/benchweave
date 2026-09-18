<!-- gortex:communities:start -->
## Community Skills

| Area | Description | Explore |
|------|-------------|---------|
| Architecture 1 Dirs Append | 24 symbols | `analyze(operation:"communities", id:"community-18")` |
| Architecture 1 Dirs Fromisoformat | 16 symbols | `analyze(operation:"communities", id:"community-27")` |
| 2 Dirs | 12 symbols | `analyze(operation:"communities", id:"community-31")` |
| 1 Dirs Snapshot | 8 symbols | `analyze(operation:"communities", id:"community-34")` |
| Architecture 1 Dirs Specimen | 7 symbols | `analyze(operation:"communities", id:"community-23")` |
| 1 Dirs Run Checks | 7 symbols | `analyze(operation:"communities", id:"community-35")` |
| Architecture Visit Check Closure | 6 symbols | `analyze(operation:"communities", id:"community-12")` |
| Architecture 1 Dirs Refs | 5 symbols | `analyze(operation:"communities", id:"community-24")` |
| Architecture 1 Dirs Jsonschema Draft202012validator | 5 symbols | `analyze(operation:"communities", id:"community-14")` |
| Architecture Interval Pass | 5 symbols | `analyze(operation:"communities", id:"community-20")` |
| 1 Dirs Walk | 5 symbols | `analyze(operation:"communities", id:"community-17")` |
| 1 Dirs Test Cli Entrypoint Prints Vers | 4 symbols | `analyze(operation:"communities", id:"community-36")` |
| Architecture Check Check Execution | 3 symbols | `analyze(operation:"communities", id:"community-19")` |
| Architecture Check Check Devices | 3 symbols | `analyze(operation:"communities", id:"community-13")` |
| Architecture Visit Check Execution | 3 symbols | `analyze(operation:"communities", id:"community-21")` |
| Architecture Check Check Closure | 3 symbols | `analyze(operation:"communities", id:"community-10")` |
| Architecture Check Check Registry | 3 symbols | `analyze(operation:"communities", id:"community-26")` |
| Architecture Check Check Planning | 3 symbols | `analyze(operation:"communities", id:"community-25")` |
| Architecture Check Check Interface | 3 symbols | `analyze(operation:"communities", id:"community-22")` |
| Jsonschema Draft202012validator | 3 symbols | `analyze(operation:"communities", id:"community-2")` |

<!-- gortex:communities:end -->

---

## Findings that outlive the session

**This applies to you, the main session, not only to subagents.** If a session produces
something **durable, non-obvious, and not recoverable from git, the PR, or the tracker** —
a measured number, a decision and why it beat the alternative, an honest negative, a defect
*pattern* rather than a defect, a trap that looks safe — propose it to the memory ledger:

```sh
node .claude/hooks/memory-propose.mjs <<'JSON'
{"concept":"short label","content":"the fact itself, self-contained, readable in a year","summary":"one line","type":"fact","source":"main"}
JSON
```

Read `.claude/memory-protocol.md` for the bar (a noisy vault is worse than a small one, and
the "do not propose" list is as load-bearing as the "do"). The ledger is gitignored and is
subject to the same rule as committed content: no credentials, no client identifiers.
Proposals drain themselves into the `benchweave` memory vault on `PreCompact` /
`SessionEnd` / a debounced `Stop` via `.claude/hooks/memory-drain.mjs`, and
`memory-freshness.mjs` reads the drain receipt back at `SessionStart` and speaks up when
the queue is stale. Direct `muninn_remember` over MCP stays available; the ledger is what
survives a session with no MCP access or a context that ends before anyone writes it down.

There is **one ledger per repository**, in the main checkout — appends from a linked
worktree resolve through `.git` to the same file. Its tests are
`node --test .claude/hooks/tests/*.test.mjs` — run them if you touch the drain.
**codex sessions:** no drain hook fires there — run
`node .claude/hooks/memory-drain.mjs --base http://127.0.0.1:8125/mcp` before ending a
session that queued proposals.

**RedTeam and external review workflows route through this rule too** (principal
directive 2026-09-14): when the RedTeam skill or any adversarial/audit workflow runs
against this repo, its synthesis step is not the record — the full findings list (every
severity, LOW and NIT included, each with its disposition: fixed / deferred /
accepted-risk) is proposed to the ledger before the session ends. The skill files stay
generic; this repo's protocol is what binds them here. Review findings are never
forgotten.

## Two-repo discipline: the SDK submodule

`packages/sdk` is a git submodule with its own repository
(`madeinoz67/benchweave-sdk`) and its own CI. Editing anything under
`packages/sdk` is always **two commits, in this order**:

1. Commit inside the submodule and **push it** (the SDK repo's CI and releases
   run from its own remote — an unpushed submodule commit is invisible there
   and breaks main-repo CI, which checks out submodules by SHA).
2. Then commit the advanced submodule pointer in the main repository.

`make sync-sdk-standards` enforces the order: it refuses to run against a
submodule working tree with uncommitted changes, and its report reminds you
that the pointer commit is still yours to make. Nothing in the flow pushes or
commits for you.

Planning docs under `docs/superpowers/` stay local-untracked in **both**
repositories (they are force-added only at close-out, when they document
something that has landed).
