# Issue #451 — sync-completion pacing replaces the bump time window (G-5)

Specified amendment: the ruling is owner-ratified in issue #451 (successor to
the #97 bump-floor precedent of 2026-09-23); this record documents the
mechanism and its falsifiers, not alternatives. Three commits: this record,
the RED arms, the GOVERNANCE G-5 block plus the `train_window` rework.

## Mechanism

**Where the check lives.** Unchanged from #97: `src/benchweave/standards/
train_window.py`, enforced through the standards suite
(`tests/standards/test_train_window.py`), which CI runs on full history
(`fetch-depth: 0`, already commented in `ci.yml`). The public entry keeps its
name — `check_train_windows(root)` — but loses the `floor_seconds` parameter:
wall time is no longer an input to the judgement.

**How it reads history.** The collector keeps its #97 skeleton —
`git log --no-renames --diff-filter=A --format="%ct%x00%H" --name-only --
standards`, version directories derived from the FILE paths git emits, one
entry per `(standard, version)` at its earliest commit (straddled dirs count
once), reset-class heuristic (one commit adding dirs for ≥ 3 standards)
exempt, admission (the standard's chronological first version) exempt. What
changes is the judgement: for every judged bump — commit C adding a new
pure-semver version directory of standard S — the check asserts that the SDK
lock **at C** carries S's previous released version (the prior entry in the
per-standard landing sequence; a same-commit double version makes the higher
one's predecessor the lower one, which no lock can carry — the stacking
refusal). The `-dev` invisibility arm survives verbatim (pure-semver regex).

**What "the lock carries V" reads from.** The machine source is the SDK
lock's carried set: `git ls-tree <C> packages/sdk` gives the gitlink the bump
commit arrived on; `git -C packages/sdk show <link>:standards-lock.json`
(G-3's lock — the carried set, retained ∧ in-range, mirrored from the export
bundle) yields rows `{id, version, ...}`; the lock carries `(S, V)` iff a row
for that pair exists. Yanked rows count as carried: a yank is post-sync
state, and the release-ledger cost the rule prices was already paid. The read
needs the submodule's object store, so it runs lazily — only when a judged
bump exists. An uninitialized submodule (`packages/sdk/.git` absent), a
gitlink whose object the clone lacks (the orphaned-pin class), or a malformed
lock is a typed `train_window_history_unreadable` refusal — fail-closed,
never a laundered pass — mirroring `check.py`'s uninitialized-submodule
posture and the module's own shallow-repository refusal.

**The anchoring.** Self-anchoring survives, re-pointed: the anchor is the
committer timestamp of the FIRST commit (oldest `git log --reverse` match)
whose `src/benchweave/standards/train_window.py` content introduced the
module's G-5 marker literal (`ANCHOR_MARKER`, a constant in the module) —
i.e. this amendment's own arrival commit, found by pickaxe (`git log
-S<marker>`), not a hand-maintained date. History before it is grandfathered
by mechanism. Delete-and-re-add cannot re-anchor: a move or delete changes
the marker's occurrence count and matches pickaxe, but the OLDEST match is
still the amendment's arrival. Residual (stated, as before): bumps are
compared to the anchor by committer timestamp, so a post-amendment commit
carrying a skewed pre-amendment clock would be grandfathered — the same
residual the #97 mechanism carried.

## Historical compliance evidence (measured, this tree, 2026-10-12)

The brief's example names an "otdp 0.2.2→0.2.3" bump; no 0.2.3 exists on
this branch — the post-#97-anchor judged bumps (from the current module's
own census) are: otdp 0.2.1 (`b0a41f39`), otdp 0.2.2 (`05354b4b`),
execution 0.2.0 (`54a59fab`), plugin-ui 0.3.0 and plugin-ui-preview 0.2.0
(`b9ea4846`), registry 0.1.2 (`899f074a`). Reading each commit's gitlink
lock shows the rule's demand was already met where it is readable: the locks
at `b0a41f39`/`05354b4b`/`54a59fab`/`b9ea4846` carry otdp 0.2.0, otdp 0.2.1,
execution 0.1.0, plugin-ui 0.2.0 + plugin-ui-preview 0.1.1 respectively —
every predecessor present. The registry bump's gitlink (`79a32e1f`) is an
orphaned pin (the object exists neither in the local submodule clone nor on
the SDK remote — an unmerged-branch lineage that later vanished), which is
exactly why the amendment re-anchors at its own arrival: under G-5 the whole
pre-amendment history, readable or not, is grandfathered, and post-amendment
the same posture is a typed refusal instead of a silent verdict.

## Acceptance rule (pre-committed)

1. RED: the reworked arms fail on the un-amended tree (the old module's
   `check_train_windows(root, floor_seconds)` arity and its missing
   `sync_completion_violations`/`ANCHOR_MARKER` surface name the failures).
2. GREEN, scratch family (real git, real locks): a judged bump whose commit's
   lock lacks the predecessor REFUSES with a typed, prefixed message in the
   `train_window_` family; a bump whose lock carries the predecessor PASSES
   regardless of wall-clock distance (two compliant bumps an hour apart
   pass — the #97 behaviour that motivated this amendment); per-standard
   scope; admission and reset-class exempt; pre-anchor grandfathered;
   straddled dirs count once; same-commit double version refuses the stack;
   a yanked predecessor row counts as carried; delete-and-re-add does not
   re-anchor; an unreadable pinned lock and an uninitialized submodule each
   refuse by name (no SHAs misattributed); shallow repositories still refuse
   to judge; `-dev` dirs stay invisible.
3. GREEN, real tree: `check_train_windows(ROOT) == ()` — the G-5 anchor lands
   with the amendment, so the real tree has zero post-anchor bumps; the
   scratch family carries the non-vacuity burden (same doctrine as #97).
4. FAST lane per commit; full battery once at the end.

## Tier call (design-time, #254)

Tier 3. Path rule: the diff touches `standards/` (GOVERNANCE.md). Keyword
scan over the expected diff (docs + code), keyword: count — `threading`: 0;
`asyncio`: 0; `subprocess`: present in the module rework and the test
fixtures (~10 occurrences, the git plumbing both already carry); `sha256`: 0;
`hashlib`: 0; `migrate`: 0; `recovery`: 0; `protection`: 0. The
standards-governor mandate fires (any `standards/` touch). The review
re-derives the tier independently.

## Falsifiers and deferrals

- Falsifier for the lazy-lock read: a judged bump plus an empty
  `packages/sdk` must refuse, not pass (arm 15) — a check that silently
  skipped unreadable locks would launder pacing.
- Falsifier for the anchor: a pre-amendment bump on a non-compliant lock
  passes (grandfathered), the same bump post-amendment refuses — the anchor
  must actually move judgement forward (arm 10).
- Deferred: no runtime/CLI surface exposes the new check (parity with #97 —
  the suite is the enforcer); `docs/internal/invariants.md` line ~478 still
  describes the collector as counting release directories, which remains
  true and needs no amendment; `ci.yml`'s `fetch-depth: 0` comment cites #97
  — still accurate, left untouched.
