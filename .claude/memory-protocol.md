# Memory proposals — how a finding survives the session

A session produces knowledge; the little of it that is not recoverable from git, the PR,
or the tracker is what memory is for — persistence that depends on someone remembering to
remember does not happen under load. So: **do not print a memory. Append it to the
ledger.** The ledger is a file, and files do not evaporate.

## The bar — what qualifies

A proposal must be **durable, non-obvious, and not recoverable elsewhere** — a measured
result and its number, a decision and why it beat the alternative, an honest negative with
the evidence that killed it, a defect *pattern* (the defect itself is in the PR), context
a future session would otherwise rediscover, or a trap that looks safe. Do not propose
progress narration, restatements of a diff/commit/PR body, the tracker's contents,
anything you would look up again anyway, or five variations of one idea (one atomic
concept per memory). A noisy vault is worse than a small one: 74% of supersession pairs in
one pollution analysis were template junk.

**One class is exempt from the noise bar: review findings.** Every review — code-reviewer,
RedTeam, adversarial audit, or a human review relayed by an agent — appends its findings
record to the ledger before the session ends, at **every severity including LOW and NIT**,
each finding with its disposition (fixed / deferred / accepted-risk). Ship it as one
"review record" proposal (verdict + severity-ranked findings + dispositions) or one
proposal per follow-up item; prose-only output does not survive. *(Principal directive
2026-09-14: review findings must never be forgotten, no matter how low-risk or
nit-picked.)*

## How to append

**Recall before you propose.** Spend one `muninn_recall` on the vault using the fact's own
concepts; if it already holds the fact, correct the engram with `muninn_evolve` or cite
it — never mint a rival copy. This judgment is the proposing session's, never a hook (the
pipe stays dumb; the drain-gate postmortem lives in `.claude/hooks/README.md`). The rtk
pytest-counts trap reached four vault copies through four independent rediscoveries, none
of which recalled first.

**Use the helper.** It validates before it writes, fills in `vault`, and refuses a batch
rather than queueing a bad line. Every proposal carries **at least one tag** — an untagged
memory is invisible to tag-scoped recall, and the validator rejects tag-less proposals.
The invocation shape and the JSON example live in one place: CLAUDE.md § Findings that
outlive the session.

Run the validator with `--check`; it names bad fields on rejection. The schema lives in
one place — `.claude/hooks/memory-schema.mjs` — imported by the producer, the guard, the
drain and the migration. **Egress disclosure:** when the key resolves, scoring ships each
proposal's `concept`, `content`, and `summary` to the external judgment endpoint
(`api.typesafe.ai`) — on by default; `--no-score` opts out, `--check` never scores, and
scoring is advice, never a gate. Raw appends to `.claude/memory-proposals.jsonl`
(gitignored) still work — never rewrite or reorder the file, append only. Write it
self-contained: a memory that only makes sense next to its conversation is a comment, not
a memory.

**Privacy is not relaxed here.** The ledger is subject to the same rule as committed
content: no vault names, no client or tenant identifiers, no memory content copied out of
someone's vault, no commercial terms. The gitignore and the pre-commit guard are backstops,
not permission.

## How it drains

It drains itself. `PreCompact`, `SessionEnd` and a debounced `Stop` are wired in
`.claude/settings.json`. To run it by hand: `node .claude/hooks/memory-drain.mjs`
(`--dry-run`, `--max N`).

**The drain is a pipe, not a curator** — identity → write → archive → truncate; no recall,
no relevance computation. The contract properties (idempotency, receipts, the watermark,
the SIGTERM/lock mechanics) and the retracted HELD-gate postmortem live in
`.claude/hooks/README.md` § Drain internals. The generalisable lesson: **a gate whose
remedy is invisible gets routed around — its discriminating variable moves at a rate
correlated with the phenomenon it suppresses, so it fails anti-correlated with need.**

### Curation — deferred, not dropped

Supersession curation is a human-run pass over the vault (adjudicated with
`muninn_evolve`) that is **not built yet**; until it is, near-duplicates from the drain are
the accepted cost. `memory-proposals.drained.jsonl` records every engram id the drain
produced — exactly the candidate set such a pass needs.

### Worktrees — one ledger per repository

**There is exactly one ledger per repository: the main checkout's.** A linked worktree's
`.git` is a file pointing at `<main>/.git/worktrees/<name>`, and `paths()` resolves through
it; `MUNINN_LEDGER_ROOT` overrides. A per-worktree queue only works if a drain runs per
worktree, and none ever will — 17 real proposals were once found stranded this way.
