## Findings that outlive the session

Durable findings go through the proposal ledger — the contract, the bar, and the schema
live in CLAUDE.md § Findings that outlive the session and `.claude/memory-protocol.md`.
Tags required on every vault write.

## Two-repo discipline: the SDK submodule

`packages/sdk` is a git submodule with its own repository
(`madeinoz67/benchweave-sdk`) and its own CI. Editing anything under
`packages/sdk` is always **two commits, in this order**:

1. Commit inside the submodule, **push it**, and **open the SDK PR now** — stacked
   (`base` = the predecessor SDK branch when one is in flight) — not at end-of-run.
   The SDK repo's CI and releases run from its own remote, and an unpushed submodule
   commit is invisible there, breaking main-repo CI, which checks out submodules by
   SHA. A pinned SHA reachable only via an unmerged feature branch stays reachable
   only while that branch lives — the MERGE makes the lineage durable; the PR
   tracks it (#69).
2. Then commit the advanced submodule pointer in the main repository.

**Single issue stream:** all issues — for either repository — file on THIS
tracker (`madeinoz67/benchweave/issues`); the `benchweave-sdk` tracker is retired
(principal directive 2026-09-20; first use of the rule was issue #107). SDK-side
work tracks under a gateway issue, and an SDK PR notes in its body that no
SDK-side issue exists by design.

**Multi-PR work uses PR stacks (#69):** dependent PRs open with `base` = the
predecessor's branch so each shows only its own delta; merge bottom-up, retargeting
each successor to `main` as its base lands. **A work is complete only when every PR
it raised — in both repos — is merged**; main-repo merges alone never call done.

`make sync-sdk-standards` enforces the order: it refuses to run against a
submodule working tree with uncommitted changes, and its report reminds you
that the pointer commit is still yours to make. Nothing in the flow pushes or
commits for you.

**The SDK-side order rule (issue #408): SDK PRs merge → the SDK release cut
(`make release-cut VERSION=x.y.z` in the SDK repo) → the gateway pointer PR.**
The gateway pointer PR advances the submodule gitlink and its `.gitmodules`
`pin` in the SAME commit — the `sdk-drift` lane reds when they disagree. A
pin naming a tag older than the SDK's latest release is green with a
`::warning::` (`pairing pending`); the gateway release-time walk (row 6 of
the family doc) reads that annotation — green alone does not close the
window.

Planning docs under `docs/superpowers/` stay local-untracked in **both**
repositories (they are force-added only at close-out, when they document
something that has landed).

## Multi-agent worktree discipline (retro 2026-09-25, R1)

Every concurrently-dispatched agent lane works in its OWN worktree, named in its
brief — never hand two live agents the same probe path (observed 2026-09-24:
two adversary lanes shared one build worktree; one lane's RED neutralization sat
live in the other's probe tree). Worktree-list-before-remove, and remove only your own
worktree: CLAUDE.md §3.7. The git stash stack is shared across ALL worktrees of this
repo family — never a blind `git stash pop` (it can apply a peer's stash);
`git stash push -u -m "<unique-tag>"` if stashing at all, and prefer `cp` backups
for mechanism-neutralization in RED runs.

**Worktree placement (2026-09-28, owner directive):** parallel-lane worktrees
live UNDER the repo root at `.wt/<lane>-<nonce>/` (gitignored) — never `/tmp` —
and the lane's session CWD is that worktree. Gortex discovers a session-anchored
in-family checkout as an automatic overlay of the primary graph, so parallel
lanes keep graph access for the worktree's life and lose it on fold (the
temporary tracking the owner requires); a `/tmp` worktree forfeits indexing
entirely (the tourniquet rule) and is only for truly external scratch. Folding
at run close: remove only your own worktree (CLAUDE.md §3.7).
