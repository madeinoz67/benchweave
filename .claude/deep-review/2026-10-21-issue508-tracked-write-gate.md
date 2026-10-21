# 2026-10-21 — Tracked wiring for the gortex write-gate (harness enforcement shipping gap)

Design record for the 2026-10-21 harness-audit finding (HIGH, with adjacent MED/LOW).
Tracker: madeinoz67/benchweave#508 (single issue stream; gateway-only diff).
Two corrections made by the implementing lane before this record's first commit,
both evidenced: the tracker line above (issue #508 now exists — the pre-commit
draft said none did), and the C1 git-path typo (`.claude.settings.json` →
`.claude/settings.json`, the tracked file's real path).

## 0. Finding verification — every claim re-derived at source this pass

Checkout: `main` at `b905b19a`, working tree clean for tracked files.

| Claim | Verdict | Evidence |
|---|---|---|
| Only PreToolUse gate lives in `.claude/settings.local.json:31-51` | CONFIRMED | `settings.local.json:31-42` (`gortex hook --mode=deny`, matcher `*`), `:43-51` (write-gate, matcher `Edit\|Write\|MultiEdit`, command at `:48`). `git grep PreToolUse` over tracked `.claude/` matches only the comment at `gortex-write-gate.mjs:2`. |
| `.claude/settings.json` has zero PreToolUse | CONFIRMED | Read in full: hooks block is `settings.json:31-96`, five entries, no PreToolUse. |
| Local file untracked via `.gitignore:56` | CONFIRMED | `git ls-files --error-unmatch .claude/settings.local.json` exits 1; `.gitignore:56` is the ignore line. |
| `CLAUDE.md:5` declares the mandate | CONFIRMED | `CLAUDE.md:5-11` (mandate), `:19-32` (edit-routing card, table `:24-29`). |
| Fresh clone / CI worker / other contributors get no structural enforcement | CONFIRMED, one correction | Fresh clone and the other two contributors: confirmed — the hook script IS tracked (`git ls-files`: `.claude/hooks/gortex-write-gate.mjs`, `.claude/hooks/tests/write-gate.test.mjs`) but nothing invokes it. Correction: a CI worker was never an enforcement surface — Claude Code hooks fire in interactive agent sessions, not CI; the exposed population is contributors' sessions. |
| MED: `:38-40` approves truncated input (no `file_path`) | CONFIRMED | `gortex-write-gate.mjs:38-40`; live probe `{"tool_input":{}}` → exit 0. |
| MED: parse failure throws uncaught → non-blocking exit | CONFIRMED | `:38` uncaught; live probe `printf 'not-json' | node …` → node exit 1 + SyntaxError trace (PreToolUse exit ≠ 2 is non-blocking → allow). |
| MED: `:14` hardcodes `/opt/homebrew/bin/gortex`, so `:68` no-ops off-Brew | CONFIRMED | `:14` const; `:65-68` null → ALLOW. |
| MED: fail-open documented at `:7-9` | CONFIRMED | Header comment `:6-9`. |
| LOW: agent briefs instruct direct reads | CONFIRMED, nuanced | `adversary.md:19-21` and `mechanism-critic.md:19-21` say "read the RULES docs directly" — defensible; `increment-designer.md:35-36` ("the actual code paths you intend to change … cite file:line") is the real collision with `CLAUDE.md:5`. |

Additional defects found this pass (mine, not the audit's):
- `gortex-write-gate.mjs:48` — `filePath.replace(/\/[^/]*$/, "")` is a POSIX-only dirname; a
  Windows-style path yields `dir == filePath` → `git -C` fails → `:50` ALLOW. Windows hosts
  no-op even with git and gortex present. Deferred (D2).
- `:44` exempts `/.claude/worktrees/` — a path convention this repo no longer uses
  (worktrees live under `.wt/`, AGENTS.md "Worktree placement"); behavior-neutral (the
  worktree exit is `:61-63`), noted, not changed.

## 1. Root cause

The gate was built as tracked artifacts (script + tests, both committed) but wired only in
the gitignored per-machine settings file. The repo's shipping surface for hook wiring —
tracked `.claude/settings.json` — already carries five tracked entries
(`settings.json:31-96`) and was never given the sixth. The declared mandatory
edit-routing control is therefore structurally enforced on exactly one machine.

## 2. Mechanism

1. **Tracked wiring.** Add one PreToolUse entry to `.claude/settings.json` `hooks`:
   matcher `Edit|Write|MultiEdit`, command `node "$CLAUDE_PROJECT_DIR/.claude/hooks/gortex-write-gate.mjs"`
   — the exact invocation shape of the five existing tracked entries (`settings.json:38`
   is the pattern; quoted `$CLAUDE_PROJECT_DIR` per tracked convention, unlike the local
   file's unquoted `settings.local.json:48`). The owner's local entry stays and
   double-fires identically (both exit 2); hooks from all settings sources merge
   additively — harness-documented semantics, named unmeasured in §7.
2. **Binary resolution.** `gortex-write-gate.mjs:14` becomes a candidate list:
   `process.env.GORTEX_BIN`, then `"gortex"` (PATH — the resolution `sh("git", …)` at
   `:49` already relies on, so no new failure class), then `"/opt/homebrew/bin/gortex"`
   (preserves the owner's machine bit-for-bit). First candidate that executes wins;
   none → `:68` fail-open unchanged.
3. **Deliberate fail-open on unparseable input.** Wrap `JSON.parse` (`:38`) in the same
   early-exit posture as the stdin read (`:31-36`): catch → stderr notice
   `[GortexWriteGate] unparseable payload — allowing (fail-open by design, pinned by tests)`
   → exit ALLOW. Missing `file_path` (`:39-40`) stays ALLOW, now pinned by a test.

**Posture decision (stated, with reason).** The gate fails OPEN on: absent daemon, absent
binary, absent git, malformed payload, untracked/branch-new targets, worktree targets. It
denies only the one case it can decide on evidence: a tracked file inside a
gortex-tracked primary checkout (`:69-75`). Reason: the gate protects edit-routing
discipline — which write path an agent uses — not bench or data safety. A bypassed route
is a visible working-tree diff caught by review and CI; a wrong deny bricks every Edit
call for a harness or host the gate cannot see. Fail-closed here converts a hygiene gate
into an outage.

## 3. What this increment does NOT change (each with its deferral home, §5)

- `gortex hook --mode=deny` (`settings.local.json:33-42`) stays local: it is the daemon's
  own machine-wide access policy behind an absolute binary path; promoting it would run a
  missing binary on every tool call for non-Brew contributors (exit-127 noise per call).
- Windows separator correctness (`:48`) — Windows keeps the fail-open posture.
- Agent-briefing read-path drift (LOW) — separate surface, obligation 14 fires when it is
  touched.
- CI lane for node hook tests — verified absent today: no node test step in any of
  `.github/workflows/{changelog,ci,codeql,device-plugins,docs,package,publish-ui-html}.yml`.

## 4. Precedent

The five tracked hook wirings at `.claude/settings.json:31-96` (ledger-guard `:32-41`,
drift-guard `:42-50`, memory-drain `:52-84`, memory-freshness `:85-95`) — same file, same
`node "$CLAUDE_PROJECT_DIR/…"` shape, same committed-with-tests discipline. In-file PATH
precedent: `sh("git", …)` at `gortex-write-gate.mjs:49`. No new architecture; the
increment is a sixth entry plus three small corrections to the script it invokes.

## 5. Minimal first increment — scope and deferrals

Files: `.claude/settings.json` (+~9 lines), `.claude/hooks/gortex-write-gate.mjs`
(~8 lines), `.claude/hooks/tests/write-gate.test.mjs` (+~55 lines), `CLAUDE.md` (+2
lines: the routing card names the gate as wired for every clone and its fail-open
posture). Nothing else. Not config-only: without the `:14` resolution change, a tracked
entry would invoke a hook that can only no-op off the owner's machine — shipping the
wiring without the control.

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | promoting `gortex hook --mode=deny` into tracked settings | documentation here | gortex ships a documented, PATH-safe, fail-open project-settings hook entry point (an arriving release/feature, inspectable in gortex's repository) |
| D2 | Windows path-separator correctness at `:48` (dirname via `node:path`) | documentation here | a contributor reports the gate silent on a Windows host, or a Windows-executable hook-test lane exists |
| D3 | agent-briefing read-path drift (`adversary.md:19-21`, `mechanism-critic.md:19-21`, `increment-designer.md:22-36`) | follow-on issue | the issue is worked |
| D4 | CI lane for `node --test .claude/hooks/tests/` | follow-on issue | a hook-behavior regression reaches main undetected by local lanes |

## 6. Invariant and drift impacts

- Invariants: none touched, none new. The diff matches no CTL/STO/CON/REG group's files
  (`docs/internal/invariants.md` group headers at `:17/:151/:246/:1010` are all
  gateway-runtime scopes). The gate's contract is CLAUDE.md's routing card plus its
  tests — not bench-facing.
- On-disk format/schema: none → not Tier 3 by the schema rule.
- Surfaces that move: CLAUDE.md only. It keeps the engineering register — an internal
  agent-workflow file, not published operator/user documentation under the ASD-STE100
  rule. MCP tools, REST/openapi, CLI, operator docs, device guide, vendored standards,
  fixture lattice, SDK repo: unchanged.
- Obligations walked (`docs/internal/drift-and-obligations.md`, all 29 rows + CI map):
  none trigger now; row 14 (agent frontmatter) fires only when D3 is worked.
- CI cost: zero — no workflow change, no new lane. FAST lane unaffected (no Python in
  the diff); full battery before push per standing rule.

## 7. Honest residuals — what this design cannot measure

- Hook merge semantics (tracked + local additive; no local subtract) is harness-documented
  behavior, not executable from this repo. The shipping claim (C1) does not depend on it;
  the "cannot be silently disabled by a local file" property does.
- First-run approval: each contributor's harness must approve tracked project hooks once;
  a contributor who declines keeps the prose mandate only. Host-side UX, unmeasured here.
- The deny path on a literal fresh clone: a fresh clone is not gortex-tracked, so the
  gate's CORRECT behavior there is ALLOW (`:68`). The increment ships the wiring; the deny
  appears per-machine once — and only if — the contributor's gortex tracks their checkout.
  That is the deliberate "never brick a harness that cannot reach a daemon" boundary:
  structural for gortex-equipped contributors, prose for the rest.

## 8. Review tier and keyword scan (#254)

Tier 2, by the default rule (`docs/internal/review-rubric.md:60-62`: no Tier 3 path or
keyword matches; not docs-only, so not Tier 1). Step-1 keyword scan over the whole
expected diff text (§5's four files): `threading` 0, `asyncio` 0, `subprocess` 0,
`sha256` 0, `hashlib` 0, `migrate` 0, `recovery` 0, `protection` 0. The CLAUDE.md
sentence and test comments are written to carry none of the eight.

## 9. Measurable proof — pre-committed acceptance rule

Written before any implementation number existed. All checks paste real output at PR time.

- **C1 wiring-ships** (the finding's core; fresh-clone-representative because it reads
  HEAD bytes — what a clone receives):
  `git show HEAD:.claude/settings.json` → parse → assert a `hooks.PreToolUse` entry whose
  command contains `gortex-write-gate.mjs` and whose matcher covers Edit/Write/MultiEdit.
  RED today (verified: zero PreToolUse in the tracked file), GREEN at the reviewed merge
  commit.
- **C2 malformed posture, RED→GREEN**: `printf 'not-json' | node .claude/hooks/gortex-write-gate.mjs`
  → at HEAD exit 1 + SyntaxError (verified live this pass); after, exit 0 + `/unparseable/`
  notice. Encoded as a test.
- **C3 missing-`file_path` pin**: `{"tool_input":{}}` → exit 0 before and after. Stated
  honestly: cannot RED; it exists so the fail-open decision survives an eager later
  "fix".
- **C4 env-candidate honored, RED→GREEN** (primary-checkout branch only, following the
  existing environmental branch at `write-gate.test.mjs:44-54`): set `GORTEX_BIN` to a
  stub script that prints `does not track`, feed a tracked-file payload → at HEAD exit 2
  (env ignored, real gortex says tracked); after, exit 0 (stub honored, `:68` allows).
  Proves the resolution chain is live. A GORTEX_BIN-missing assertion would be WRONG
  under the candidate list — the brew fallback would still deny on the owner's machine —
  hence the stub form.
- **C5 gate-fires live** (manual, this checkout): tracked-file payload → exit 2 + the
  routing message (verified live this pass).

**SHIP iff**: C1 GREEN at the merge commit; C2 and C4 RED at HEAD and GREEN on the
branch; C3 GREEN; C5 pasted from the PR session; FAST lane and full battery green.

**KILL if**: C1 cannot go GREEN within §5's file scope; C2 or C4 will not RED at HEAD
(the defect is not as described — re-scope before touching code); any battery lane reds.

**UNDERPOWERED, not conclusive, if**: C5 returns 0 — the gate fail-opens when the daemon
is unreachable, so a daemon-down C5 measures nothing; rerun only after
`gortex call workspace --arg operation=info` names this toplevel. C4's RED arm requires a
gortex-equipped primary (on a host without gortex, HEAD already allows); it must run in
the owner's checkout or an equivalently tracked primary, and is skipped in worktree lanes
by the same environmental branch the existing test uses.

## 10. Top risks, each with its falsifier

- **R1 Harness merge semantics differ** (a local file can suppress tracked hooks) → the
  "not silently disableable" property fails while shipping holds. Falsify: harness docs
  or a contributor-machine experiment contradicting additive merge.
- **R2 Contributors decline the tracked hook at first-run approval** → control stays
  prose for them. Falsify: observe a contributor's unapproved-hook state (§7: not
  repo-measurable).
- **R3 PATH resolution loses the gate in minimal-PATH hook environments** (plausibly why
  the local file used an absolute path). Falsify: run the tracked entry under the
  harness's hook environment on the owner's host and get ALLOW where C5 gave DENY.
  Mitigation in-design: the `/opt/homebrew/bin/gortex` fallback candidate keeps the
  absolute path, so R3 needs `gortex` off PATH AND the fallback moved — two regressions
  at once.
- **R4 Double-fire on the owner's machine** (local + tracked entries) — cosmetic
  duplicated deny message, both exit 2. Falsify: any behavioral difference beyond the
  duplicated stderr line.
- **R5 Someone later "hardens" unparseable → deny** and bricks a harness edge case.
  Mitigation: C2+C3 pin the posture; the catch block's comment states the reason inline.

## 11. DON'T-BUILD assessment

Not a don't-build. The defect is verified at source (§0), live probes show the gate both
fires (C5: exit 2) and accidentally fail-opens on malformed input (exit 1) today, the fix
extends a five-entry tracked precedent with one config entry plus three small script
corrections, and the proof is executable in both directions with named underpowered
cases. The adjacent MED/LOW items ride only where they make the tracked wiring honest
(portability, deliberate posture); the rest defer with homes and triggers.
