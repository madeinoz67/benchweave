# Design record — issue #459: is a release pre-flight gate the right instrument for tonight's four failures?

- **Date:** 2026-11-09 (design pass, same night as the incidents it studies)
- **Base:** `cfac5d34` (`origin/main`, "Merge pull request #614" — fetched and verified this
  session before any citation was made)
- **Checkout disclosure:** this pass ran in a primary checkout sitting at `084c5e6c`, several
  merges behind `cfac5d34` — the exact stale-checkout trap this record classifies as failure
  F2. Every file cited below was verified byte-identical across `084c5e6c..cfac5d34`
  (`git rev-parse` per path), except `docs/internal/drift-and-obligations.md`,
  `scripts/standards/count_version_literals.py`, and `tests/win_core_manifest.json`, which
  were read from `cfac5d34` via `git show`. The record is written against `cfac5d34`.
- **Scope:** design only. No production code, no commits, no issues, no PRs from this pass.

---

## 0. Verdict

**No new gate. No new release pre-flight.** The four failures recorded tonight do not share
a lifecycle point, and a gate is a single-point instrument. Three of the four already have a
mechanical owner or a cheaper intervention point than any gate offers; the fourth is not
mechanically checkable at all. The buildable work is **two small slices** — an edit-time
warning plus a 6-second fast-lane arm for the win_core ratchet (slice 1), and a session-start
facts hook for the stale-checkout and submodule traps (slice 2) — plus one process row that
is deliberately not mechanized. CLAUDE.md §2 principle 11 (honest negative results are
first-class) is the license for the negative half of this verdict.

The issue's own first increment already proved the positive pattern and drew its boundary:
`scripts/standards/train_preflight.py` (PR #503) is the pre-push aggregate for **standards
release-train surfaces** — pointer pin, mirror, matrix, literal counts, docs claim register.
Tonight's four failures are not standards-train surfaces. Extending the train pre-flight to
own them would couple a release-time instrument to session-time and edit-time failures — the
ceremony the task brief warned against, and the exact "re-runs what CI already runs" shape
PR #503's design refused ("use the checks that exist; never a second copy").

---

## 1. The four failures, classified by where a control can fire

| # | Failure (tonight's evidence) | Checkable before work starts? | Checkable at push time? | Owner today | Where it was discovered |
|---|---|---|---|---|---|
| F1 | win_core manifest ratchet drift | No (nothing has moved yet) | **Yes, and cheaper: from the moment of edit** | `scripts/ci/win_core_manifest.py --check`, run in CI by `tests/contract/test_win_core_partition.py` in `gates` | Battery/CI time, after the work was otherwise finished |
| F2 | Design pass on a stale primary (`084c5e6c` vs `origin/main` ahead); second lane, same night | **Yes — only here** | No (meaningless after design is done) | CLAUDE.md §3.1 (discipline only — it failed twice in one night) | Mid-pass, by accident |
| F3 | Fresh worktree with unmaterialized `packages/sdk` reddens bare mypy with an error that reads like a code failure | **Yes — only here** | No (environment, not diff) | Nowhere in the repo (memory + dispatch briefs only — verified by grep over CLAUDE.md, AGENTS.md, drift-and-obligations.md: zero hits) | At first gate run |
| F4 | Lane dispatched onto a slice a design-record addendum had already ruled deferred | **No** | No | None possible today (see §6) | After the fact |

The lifecycle mismatch is the whole argument: F1 wants a signal at **edit/commit** time, F2
and F3 want one at **session start**, F4 wants a **human reading a ruling**. A release
pre-flight is a **pre-push** instrument. One gate cannot own failures that live at three
different points, and for F1 the gate already exists — the defect is *when it first fires*,
not *whether*.

### F1's evidence base is larger than the brief stated

The brief cites PRs #609 and #612. The manifest-motion log on `cfac5d34`
(`git log --oneline cfac5d34 -- tests/win_core_manifest.json`) shows **four manifest motions
tonight across four PRs**:

- `be90a6bc` (#606 candidate B) — refresh folded into the work commit
- `0b0ec4c2` (#608) — **dedicated follow-up commit** ("Refresh the win_core manifest: three
  new arms, two totals")
- `656114f8` (#609) — folded, but only after a mid-run red; the PR body states the gap
  plainly: "the design record's §7 walk did not name it"
- `cdec3e1c` (#612, closing #610) — **dedicated follow-up commit** ("Refresh the win_core
  manifest: one new arm")

So the ratchet was touched by every test-adding PR tonight, with at least 3 of 4 motions
discovered late (two remediation commits plus #609's admitted red). This is not a rare
class; it is the default outcome of adding a test without knowing the obligation exists —
because the obligation lives in the CI map **table** at the bottom of
`docs/internal/drift-and-obligations.md` (the `windows` row), not in the numbered rows that
design-record obligations walks and the drift-guard hook read.

---

## 2. Why a gate is the wrong instrument (the record's central answer)

1. **The gate for F1 already exists.** `tests/contract/test_win_core_partition.py`
   subprocesses `scripts/ci/win_core_manifest.py --check` inside the `gates` CI lane
   (drift-and-obligations CI map, `windows` row: "run by
   `tests/contract/test_win_core_partition.py` in gates"). Its detection teeth are proven
   in-suite — a doctored manifest, dropped row, and bumped core count each assert a nonzero
   exit. A pre-flight that re-runs it before push adds no coverage the `gates` lane lacks;
   it only moves the same red ~15 minutes earlier for the one actor who runs it. The
   cheaper and earlier move is to make the signal fire at **edit** time (a warning hook)
   and at **fast-lane** time (~6 s, see §3) — before the work is "otherwise finished."
2. **F2/F3 are not diff properties.** A gate evaluates a diff or a tree at a point in time.
   "HEAD is behind `origin/main`" is a property of the *session's starting state* and is
   unknowable from the diff; "the submodule checkout is empty" is an environment property
   that no push-time check can see. Both are one `git`/`existsSync` call at session start —
   the instrument is a session-start facts hook, not a gate.
3. **F4 has no tree-derivable predicate.** "An addendum ruled this slice deferred" is a
   semantic fact living in issue threads and design-record addenda. Mechanizing it requires
   a machine-readable deferral ledger that does not exist; pretending a keyword scan
   approximates it would be a check that fails open. Classified not-checkable (§6).
4. **The blocking-gate shape has an observed failure mode on this repo.** During this very
   design pass, `win_core_manifest.py --check` exited **2 (fail-closed)** in 2.9 s because
   the checkout carries untracked locally-duplicated files (`tests/... 2.py` copies, a sync
   artifact on the design machine) — the row parser refused them by name, exactly as its
   docstring promises. That is correct behavior for a tree-state check, and it is precisely
   why this check must **not** become a blocking pre-commit arm yet: a hard gate would have
   refused every commit in that checkout over environment noise. Warn-and-early-check
   degrades gracefully; block does not. (This observation sets deferral D2's promotion bar,
   §13.)

---

## 3. The ratchet, specifically (the brief's named question)

> Could the per-file collected-count manifest be made self-updating on refresh, or checked
> cheaply in the fast lane?

**Self-updating: refused, with the structural reason.** The ratchet's entire purpose is that
count motion is a *visible, owner-reviewed diff*: "growth AND shrinkage refuse `--check`
until `--refresh` moves the file — the refresh diff is the review surface"
(`scripts/ci/win_core_manifest.py:6-9`, design of record
`.claude/deep-review/2026-10-15-windows-core-subset-design.md`, the #221 docs-baseline shape
applied to the test partition). Auto-refresh on drift would bless exactly the class the
ratchet exists to catch: a test file that silently stops collecting shrinks a total, and an
auto-updated manifest launders the drop with no diff for a human to read. Under claim
discipline (rubric G4), "the ratchet prevents silent drops" is only true while the refresh
is a human action. **Checked cheaply in the fast lane: yes — measured.** On the design
machine, `pytest --collect-only -q` costs 3.0 s (full tree) and 2.5 s (`-m wincore`), so
`--check`'s two collection passes cost ≈ 6 s end-to-end on a clean tree (observed 2.9 s to
its fail-closed refusal on the noisy tree above). That is fast-lane cheap — comparable to a
warm ruff pass — and it is the same fail-closed posture the lane already accepts.

So the ratchet fix is **not** a new gate and **not** a self-updating manifest; it is moving
the existing 6-second check's first invocation from battery time to edit time and fast-lane
time, and making the obligation discoverable by the walks that keep missing it.

---

## 4. Slice 1 (build): the ratchet's early signal

Three one-motion edits, one mechanism: *the manifest's signal fires when the count moves,
not when the battery runs.*

### 4.1 drift-guard rule — `win-core-manifest-motion` (edit time)

Append one rule to the `RULES` array in `.claude/hooks/drift-guard.mjs` (9 rules today;
warn-never-block, once-per-session, satisfaction-recorded-first — all existing mechanics,
nothing rule-specific to add). The trigger is **manifest-keyed, not path-guessed**: the hook
loads the committed manifest's `files` keys once (try/catch → empty set; a missing manifest
is the check's own failure to report), and fires only when an edited path is a pinned file —
so `docs/internal/ui-contract.md` (200 collected items) warns while an unrelated docs edit
never does, and the trigger set self-maintains as the manifest grows.

Shape (final wording is the builder's; the semantics are the contract):

```js
{
  // Obligation 32 — the win_core ratchet: count motion needs a same-commit refresh.
  id: 'win-core-manifest-motion',
  triggers: (p) => WINCORE_FILES.has(p),
  satisfies: (p) => p === 'tests/win_core_manifest.json',
  message: [
    '**[Drift 32] A win_core-manifested file was edited — did its collected count move?**',
    '',
    'tests/win_core_manifest.json pins per-file (total, core) counts; ANY motion (new or',
    'removed test, docs contract row) refuses --check until refreshed:',
    '  uv run python scripts/ci/win_core_manifest.py --refresh   # ~6 s',
    'Commit the refresh diff WITH the count-moving change — the diff is the review surface.',
  ],
}
```

with `WINCORE_FILES` a module-level `Set` of `Object.keys(json.files)` from
`tests/win_core_manifest.json` (read once, absent-file tolerant).

### 4.2 Obligations row 32 (walk discoverability — the #609 gap)

Add a numbered row to `docs/internal/drift-and-obligations.md` promoting the ratchet out of
the CI-map table: "**A test collected under the win_core manifest** 🪝 →
`tests/win_core_manifest.json` moves in the SAME commit (`--refresh`; ≈6 s); the refresh
diff is the review surface. Design-record §7 walks name this row." Cross-reference it from
the `windows` CI-map row (one clause), which stays as the lane description. The 🪝 marker
becomes true the moment 4.1 lands. Two ride-along one-liners, both folded into this slice:
the drift-guard.mjs header comment still says "twelve" obligations (stale; the doc carries
31) — correct the count; and the doc currently carries two rows numbered "29" (observed
this pass) — leave existing numbering untouched (renumbering churns every cross-reference;
owner's call if wanted) and append as row 32.

### 4.3 Fast-lane arm (commit time)

One sentence added to CLAUDE.md §3.2's FAST-lane definition, after the focused-pytest
bullet:

> When the diff touches any file pinned by `tests/win_core_manifest.json`, also run
> `uv run python scripts/ci/win_core_manifest.py --check` (≈6 s: two collect-only passes);
> count motion takes `--refresh` in the same commit, and the refresh diff is the review
> surface. A local exit 2 naming duplicate/space-carrying paths is environment noise in the
> checkout, not a code failure — clean the tree.

The last clause exists because of the observed exit-2-on-local-duplicates behavior (§2.4);
it converts a misleading refusal into a named condition at the exact place a lane meets it.

### 4.4 What slice 1 does NOT do

No CI change (zero new lanes — the `gates` lane already runs the check). No pre-commit arm
(D2). No manifest change. No self-update path (§3).

---

## 5. Slice 2 (build): session-start facts (`session-preflight.mjs`)

New file `.claude/hooks/session-preflight.mjs`, registered as a **second** `SessionStart`
entry in `.claude/settings.json` beside the existing `memory-freshness.mjs` entry (pure
append; the event is already wired — no `make hooks` / `core.hooksPath` motion, because a
Claude-Code hook is settings-wired, not a git hook). Posture copied from drift-guard:
**always exit 0, warn never block**, emit warnings as `hookSpecificOutput.additionalContext`
(the in-tree JSON shape), silent when everything holds. Two facts, because exactly two
traps bit (F2, F3):

1. **Behind-count.** `git fetch origin` (spawnSync, 5 s timeout; failure → say
   "fetch failed — comparing against last-fetched refs" and continue), then
   `git rev-list --count HEAD..origin/main` in the session's checkout. If > 0:
   "HEAD is N commits behind origin/main (<sha>) — rebase or re-verify before design work
   (CLAUDE.md §3.1)." A checkout that never fetched and cannot fetch now degrades to a
   count against the stale local ref — disclosed in the warning text when that happens.
   This is best-effort by design: tonight's case (multiple lanes in one repo family, refs
   shared across worktrees, someone had fetched) is caught; a hermetically unfetched
   checkout is not, and the checklist row remains the backstop.
2. **Submodule materialized.** If `packages/sdk/src` is absent in the checkout:
   "packages/sdk is not materialized here — run `git submodule update --init packages/sdk`;
   bare mypy otherwise exits 2 with 'Cannot read file packages/sdk/src', which reads like a
   code failure and is not one."

Deliberately excluded: anything about local venv/path configuration (owner-machine
specifics stay in dispatch briefs, not the repo — public-hygiene posture), ahead-count,
gortex state, and any network check beyond the single fetch. ~50 lines including guards.

---

## 6. Not built: F4 (deferral rulings) — classified, with its reopen trigger

F4 ("a lane was dispatched onto a slice an addendum had already ruled deferred") is a
coordination failure between a dispatcher and a written ruling. No committed artifact
encodes "deferred" in a machine-readable form today: rulings live in free-text issue
comments and dated addenda inside design records. A gate would need a predicate over that
text; the honest predicate does not exist, and a keyword approximation fails open by
construction (a ruling that phrases deferral differently is invisible to it).

The control that IS available costs one line and no code: the dispatch-brief convention
(already the carrier for worktree naming, nonce rules, and the Gortex mandate) gains the
row **"read the carrying issue's thread and the design record's addenda for deferral
rulings before accepting a slice."** Reopen trigger for mechanization, named now: a
machine-readable deferral ledger exists — e.g. a tracker-label/form field or a
design-record frontmatter key that a script can enumerate — at which point a
"dispatch-vs-ruling" check becomes a ~20-line script over that ledger, and not before.

---

## 7. Arms (RED-first, and what each fails on today)

### Slice 1 — `.claude/hooks/tests/drift-guard.test.mjs` (append; the file's existing
spawnSync-end-to-end shape, 5 tests today)

- **RED (the gap):** write a `tests/unit/test_example.py` path through the hook on the
  pre-change RULES — no warning is emitted (the rule does not exist). This is the #609
  failure restated as an arm: today the hook is silent exactly when it should have spoken.
  The arm asserts the warning text `[Drift 32]` appears — it fails on `main` tonight.
- **GREEN (the rule):** with 4.1, the same input warns once; a second manifested-path edit
  in the same session stays quiet (once-per-session); a session that touches
  `tests/win_core_manifest.json` FIRST stays quiet on later manifested-path edits
  (satisfaction-recorded-first — both follow the file's existing test idioms verbatim).
- **Manifest-keyed trigger arm:** a non-manifested `docs/*.md` edit emits nothing (guards
  the trigger against path-guess drift).
- The `--check`/`--refresh` machinery needs no new arms — its teeth are pinned in-suite by
  `tests/contract/test_win_core_partition.py`; slice 1 cites them, never re-proves them.

### Slice 2 — `.claude/hooks/tests/session-preflight.test.mjs` (new)

- **RED:** the hook file does not exist, so the suite cannot run it (spawnSync ENOENT) —
  the honest RED for a new file, stated plainly rather than dramatized.
- **Behind-fixture:** temp git repo; two commits; `git update-ref refs/remotes/origin/main
  <sha2>` while HEAD sits at `<sha1>` — no network needed. Expect exit 0 plus a warning
  naming the count and both SHAs.
- **Clean fixture:** HEAD == the faked origin ref → no output at all.
- **Submodule fixture:** repo with `packages/sdk/` present but no `src/` → the mypy warning;
  with `src/` present → silent.
- **Fetch-failure degrade:** origin pointed at a nonexistent local path → exit 0, warning
  text says the fetch failed and gives the last-fetched count anyway.

---

## 8. Pre-committed acceptance rule (written before any post-merge number is looked at)

### Slice 1

- **Mechanical gate (deterministic):** all §7 slice-1 arms green on the slice branch, run
  with `node --test .claude/hooks/tests/`; the RED arm demonstrated failing on the
  pre-change head (quoted output in the PR body, per the house RED-evidence convention).
- **Field metric:** the *late-discovery rate* — of the PRs that move a manifested file's
  collected count, the fraction where the win_core refresh lands as a separate follow-up
  commit or where battery/CI first reports the drift. **Baseline (tonight): ≥3 of 4**
  (0b0ec4c2, cdec3e1c as dedicated follow-ups; #609's admitted mid-run red).
- **Sample size:** the next **4** count-moving PRs, observed within **3 weeks** of the
  merge.
- **Ship:** mechanical gate green AND late-discovery rate **0/4**.
- **Kill (the hook half):** mechanical gate green BUT late-discovery **≥2/4** with the hook
  active in the working sessions → the edit-time warning is not reaching lanes; delete the
  drift-guard rule (keep row 32 and the fast-lane arm) and promote deferral D2 (pre-commit
  arm) instead, accepting its environment-noise cost with a documented bypass.
- **Underpowered:** fewer than 4 qualifying PRs in 3 weeks → extend 3 more weeks; never
  conclude from fewer than 4.

### Slice 2

- **Mechanical gate:** all §7 slice-2 arms green in `node --test`. The arms ARE the proof
  of mechanism; F2/F3 field events are too rare to power a rate (2 stale-checkout lanes in
  one night is the only observed cluster), and pretending otherwise would be a fake
  denominator.
- **Ship:** arms green, SessionStart wall time under 5 s on the development machine
  (measured; the 10 s wiring ceiling is the bound, 5 s is the comfort margin).
- **Kill:** wall time ≥5 s after the degrade path engages → drop the fetch step
  (last-fetched-refs mode) and re-measure; still ≥5 s → delete the hook, keep the
  checklist row (CLAUDE.md §3.1 already carries the discipline; the hook was a nudge, not
  a gate).

---

## 9. Obligations walk, invariants, drift surfaces, CI cost

- **Obligations (drift-and-obligations.md):** this change *edits the list itself* — new
  numbered row 32 (🪝 via 4.1), a cross-reference clause on the `windows` CI-map row, and
  the stale "twelve"-count comment fix in drift-guard.mjs. No other numbered row moves:
  no `src/`, `standards/`, `fixtures/`, CLI, or docs-site surface is touched. CLAUDE.md
  §3.2 (fast lane definition) gains one sentence — that file is the fast lane's own
  definition, so the motion is the obligation. `.claude/settings.json` gains one
  SessionStart entry — settings are not a synced surface in the list. AGENTS.md: no motion
  (no git-hook install changes; `make hooks` untouched).
- **Invariants (docs/internal/invariants.md):** none touched. The four families
  (Control & execution, State & persistence, Contracts & standards, Registry & plugin)
  govern gateway behavior; both slices move repository process tooling only — no
  `src/benchweave/` byte, no `standards/` byte, no persisted format, no transport. No new
  invariant and no amendment.
- **On-disk formats/schemas:** none. `tests/win_core_manifest.json` is read by the new hook
  rule but never written by it; its schema (`benchweave.win-core-manifest/1`) is untouched.
- **CI cost:** zero new lanes, zero changed lanes. Hook tests run locally via
  `node --test` (the existing convention — no `.github/workflows` entry runs hook tests
  today, verified by grep; adding one is out of scope and would contradict §3's cost
  argument).
- **Memory protocol:** findings from this pass go through the proposal ledger with tags,
  per CLAUDE.md.

---

## 10. Tier (#254 design-time call) and the Step-1 keyword scan

- **Tier: 2** for each slice (maximum across slices: 2). Trigger: the default rule — the
  expected diff is code under `.claude/hooks/` plus `.claude/settings.json` and `*.md`
  docs; it matches no Tier-3 path (no `src/benchweave/contracts/`, no `standards/`, no
  state/migrations, no registry, no fixture lattice, no dependency re-pin, no submodule
  pointer motion) and is not docs-only, so it does not reach the Tier-1 rule before the
  default catches it.
- **Keyword scan over the expected diff text** (both slices' expected diff as speced in
  §4–§5 and §7: the rule block, the two doc sentences, the obligations row, the hook and
  its tests — docs and code alike, first-match-wins text rule):

  | keyword | count |
  |---|---|
  | `threading` | 0 |
  | `asyncio` | 0 |
  | `subprocess` | 0 |
  | `sha256` | 0 |
  | `hashlib` | 0 |
  | `migrate` | 0 |
  | `recovery` | 0 |
  | `protection` | 0 |

  All eight zero over the speced diff. The node hook spawns git via `node:child_process`
  — the word that would self-fire the deep lane is simply not needed to say what the hook
  does. The review re-derives both facts independently, per #254.

---

## 11. Precedent (every mechanism extends an in-tree one)

- **drift-guard.mjs** — the warn-once PostToolUse hook with a `RULES` append point and an
  end-to-end test file; slice 1 is one rule plus one test block in exactly its idiom.
- **memory-freshness.mjs** — the existing `SessionStart` wiring slice 2 appends beside;
  the event, timeout ceiling, and settings shape are all established.
- **name-screen test suite** — the `.claude/hooks/tests/*.test.mjs` convention (node:test,
  spawnSync the real hook, fixture repos/dirs) both slices' arms follow.
- **win_core_manifest.py `--check`** — the check slice 1 merely invokes earlier; its
  fail-closed parser and in-suite teeth are prior work this design cites, never duplicates.
- **The train-preflight's own §4 posture** — "use the checks that exist; never a second
  copy" — is the posture this record applies to a different failure set.

---

## 12. Top risks, each with its falsifier

1. **The once-per-session quieting burns the warning before the count moves** (a lane
   edits a manifested file early, the warning fires, three hours later the manifest motion
   goes unwarned). Falsifier: the acceptance rule's end-to-end form — if late-discovery
   stays ≥2/4 with the hook active, the warning latency hypothesis is dead and D2 is
   promoted. This is risk #1's stated kill path; it is the same path as the field kill.
2. **Warn-only hooks get ignored** (lane blindness). Falsified or confirmed only by the
   field rate; the fast-lane arm (§4.3) is the non-ignorable backstop for lanes that run
   the lane definition at all, and the `gates` CI lane remains the hard stop for
   everything else.
3. **Session-start fetch latency or offline sessions degrade the hook** — handled by the
   degrade path and the 5 s kill line in §8; worst case is a best-effort count against
   stale refs, disclosed in the warning text.
4. **The fast-lane arm is protocol text, not an enforced gate** — a lane that skips the
   fast lane skips the arm. Disclosed residual; its teeth are the existing CI stop, and
   the edit-time warning exists precisely because protocol text alone failed tonight.
5. **Manifest-keyed triggers lag the manifest** (a file collected but not yet manifested —
   impossible: the manifest pins every collected file or `--check` reds; the trigger set
   and the check read the same file). Stated to close the loop; not a live risk.
6. **The design's cost claims are single-machine.** The ≈6 s figure is the design machine's;
   CI-class hardware is faster. The acceptance rule does not depend on the number (the
   fast-lane arm rides an existing lane definition), so a slower clone degrades comfort,
   not correctness.

---

## 13. Deferrals (named, each with a home)

- **D1 — F4 mechanization.** Not built (§6). Home: this record's reopen trigger; nothing
  else carries it.
- **D2 — a blocking pre-commit arm for the manifest check.** Refused tonight on observed
  evidence (§2.4: local duplicate files produce exit 2 in a clean-code tree); promotion
  path is slice 1's field kill. Home: this record.
- **D3 — session-preflight growth** (venv/path facts, ahead-count, gortex state). Refused:
  owner-machine specifics do not belong in a public repo hook. Home: dispatch briefs.
- **D4 — #459's standing deferrals D1–D5** (merge-result coherence, unregistered claim
  sites, status wording, component claims, publishing-guide line) — untouched by this
  pass; they remain the issue's own carrier per its close-out comment.
- **D5 — hook tests in CI.** Refused: zero-CI-cost is part of this design's claim; a
  `node --test` lane is a separate decision with its own cost argument.
- **Folded, not deferred:** the stale "twelve" comment fix (§4.2) and the CLAUDE.md §3.2
  duplicate-path note (§4.3) ride their slices' diffs.

---

## 14. What would falsify this design's verdict

If, after slice 1 and slice 2 land, a fifth failure class appears that (a) is a property of
the diff or tree, (b) first surfaces at push time, and (c) no existing lane checks — that
would be the first legitimate occupant of a *release* pre-flight since PR #503's train
surfaces, and the "no new gate" verdict should be reopened with it as evidence. Tonight's
four do not meet those conditions; a checklist row, a six-second arm, a fifty-line hook,
and a dispatch-brief sentence cover them at the point each one actually fails.
