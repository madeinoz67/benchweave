# 2026-10-21 — Parking a lane: the ACK-or-stop bound

Design record for the 2026-10-21 harness-audit adjacent finding: a lane parked
behind a sibling had no stop bound — stopping it depended entirely on a message
being delivered, and delivery is the measured-failing mechanism.
Tracker: madeinoz67/benchweave#517 (this repo's single issue stream; no SDK-side issue exists by design — gateway-only diff).

## 0. Finding verification — every claim re-derived at source this pass

Checkout: `fix/parklane-stop-bound` cut from `origin/main` tip `5ff6668b`, clean.

| Claim | Verdict | Evidence |
|---|---|---|
| SKILL.md stops lanes only inside step-8 run close | CONFIRMED, one line correction | `.claude/skills/increment/SKILL.md:118-120` — "stop any still-running dispatched agent lanes" opens at :119 and completes at :120; the finding's ":118-119" undercounts by one line. No other stop clause exists in the file. |
| SKILL.md names park with no bound | CONFIRMED | SKILL.md:160 — "the second one **parks at review-complete** (not CI-green) and rebases onto the merged predecessor exactly once" — no deadline, no ACK, no consequence. |
| increment-builder park duty is advisory | CONFIRMED | `.claude/agents/increment-builder.md:115-116` — "When parked behind a sibling (shared surface): stand by at review-complete (NOT CI-green) and rebase onto the merged predecessor exactly once." Nothing enforces the stand-by. |
| The inbox check precedes only the lane's SELF-report | CONFIRMED | increment-builder.md:117-118 — "Check your inbox before reporting 'standing by'". No orchestrator-visible ACK, no deadline, no consequence anywhere in the file. |
| The drained ledger records 0/3 stop messages delivered silently, a parked lane pushing onto the owning train's PR head, and the runaway that had to be hard-killed | REPORTED, not re-derived | First-hand orchestrator ledger, quoted by the design; no in-tree bytes record it (the ledger lives in the vault, not the repo). Carried as reported. |
| TaskStop exists in this installation and worked when a human triggered containment | REPORTED | Designer's first-hand report. Key fact the audit missed: containment was discovery-triggered, not impossible — the harness primitive the bound needs already exists and has fired. |

## 1. Root cause

Stopping a parked lane depended on the stop notice reaching the lane — a message
over the orchestrator's mailbox. That mailbox measured 0/3 delivered on the
recorded wave (first-hand report; the root cause of the drop is itself deferred,
D4). This design removes the dependency on delivery rather than trying to fix
delivery: at the deadline, an uncooperative lane is dead because it no longer
exists — its worktree is force-removed — not because it obeyed a message.

## 2. Mechanism (fail-closed)

- **ARM — at the park decision T0.** The orchestrator sends a best-effort
  notice, runs `scripts/lane_park.sh arm <worktree> <lane> [D=15]` (writes
  `PARK.intent` recording the arm epoch), and starts the deadline wake via
  background Bash `(sleep $((D*60)); lane_park.sh enforce …)`. A second arm
  while `PARK.intent` exists is refused — the bound never extends.
- **LANE DUTY (cooperation only shortens the wait).** Write
  `.wt/<wt>/PARK-ACK` (ISO time + lane) before finishing the current command;
  never proceed past a reported blocker; re-check the inbox before any push.
- **ENFORCE at T0+D.** `check` returns QUIESCENT iff PARK-ACK is present AND
  there are zero commits on the lane branch since PARK.intent's arm epoch;
  otherwise ACTIVE. ACTIVE → the orchestrator TaskStops the lane (a harness
  primitive, not a message) and folds.
- **FOLD.** Archive branch ref to `archive/parked/<lane>-<ts>`,
  `git worktree remove --force` (dirty state included), ledger row.
- **RESUME.** `git worktree add` from the archived ref.
- **No ACK ⇒ the lane is dead at T0+D because it no longer exists, not because
  it obeyed.**

**ORCHESTRATOR VS LANE.** The orchestrator owns intent, wake, verdict,
TaskStop, fold and archive; the lane owns only the ACK and stopping early. Lane
non-cooperation is fatal to the lane's scratch, never to the train. A lane
killed mid-write leaves debris only in its own `.wt/<lane>-<nonce>/`; fold
force-removes dirty state; the branch ref survives until archived; the shared
checkout cannot be dirtied by the fold.

**Implementation disclosures** (decisions made at design time, pinned by the
tests): the authoritative arm time is the epoch RECORDED in `PARK.intent`
(equal to the file's mtime at write, robust to later mtime perturbation); a
commit whose committer timestamp equals the arm second counts as post-arm
activity (fail-closed toward ACTIVE); the compare is committer-timestamp-based
over the worktree's checked-out branch — a lane forging GIT_COMMITTER_DATE
evades it (the recorded runaways were deaf, not adversarial); a mid-`git
commit` kill leaves at most per-worktree index/lock debris, which dies with
the worktree, and the shared object store only gains unreachable objects.

**Disclosed residual.** Nothing structural stops a WILLFUL lane writing the
shared checkout by absolute path — the recorded runaways were deaf, not
adversarial, and that surface belongs to the write-gate slice (issue #508).

## 3. What this increment does NOT change (each with its deferral home, §5)

- Step-8 run close itself — the stop clause gains a cross-reference only.
- The mailbox and its 0/3 delivery failure — root-causing is D4.
- Push-side containment (a lane pushing to the owning train's PR head after
  arm) — D1; this bound stops the lane locally, not its remote credentials.
- The write-gate surface for willful shared-checkout writes — issue #508's.

## 4. Precedent

`scripts/merge-verified.sh` — the house gate-as-tool shape: plain shell,
explicit arguments, exit codes a script asserts on, refuse-on-ambiguity (#181
R1). Step-8 run close — the stop/fold discipline this bounds. AGENTS.md
multi-agent worktree discipline — `.wt/<lane>-<nonce>/` placement,
worktree-list-before-remove. No new architecture: one script, one test module,
two prose surfaces.

## 5. Minimal first increment — scope and deferrals

Files: `scripts/lane_park.sh` (arm/check/enforce/fold), `tests/unit/
test_lane_park.py`, `.claude/skills/increment/SKILL.md` (subsection + step-8
cross-reference), `.claude/agents/increment-builder.md` (park duties).

All four deferrals live in this record as documentation (no follow-on issue;
none has a scheduled carrier — at most ONE follow-on issue per merged PR is
reserved for scheduled carriers, and none of these is).

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | push-side bound (a per-worktree `remote.origin.push` pin) | documentation here | a commit by a parked lane appears on the owning train's PR head with committer time after that lane's arm epoch (observable on the train branch; nearest plausible carrier: the next shared-surface train that parks a lane) |
| D2 | TaskList auto-tell (arming also updates the lane's task row) | documentation here | a second recorded wave in which lane stop notices were delivered zero-of-N (ledger row naming undelivered stop messages on a live wave) |
| D3 | SubagentStop lifecycle ledgering (the harness's lane-stop event into the retrospective entry) | documentation here | the owner asks for per-lane stop evidence in a run retrospective (owner-fired, disclosed as such; the ask is the event) |
| D4 | mailbox-drop root cause (the 0/3 delivery failure) | documentation here | the delivery failure recurs on a live wave (a lane reports zero delivered messages a second time, ledgered) |

## 6. Invariant and drift impacts

- Invariants: none touched, none new. The diff matches no CTL/STO/CON/REG
  group's files (`docs/internal/invariants.md` group scopes are all
  gateway-runtime; this change is harness-side tooling and prose).
- Obligations walked (`docs/internal/drift-and-obligations.md`, all rows):
  row 14 does not fire (no agent frontmatter change — prose only); row 19
  ruled NO SYNC: the SKILL.md edit attaches to gateway-only bytes — the SDK
  copy's step 8 already lacks the "stop any still-running dispatched agent
  lanes" clause and the SDK repo carries no `.wt/` placement rule or
  `scripts/lane_park.sh`, so the subsection is gateway-specific loop prose per
  issue #99 §6 (evidence: diff of the two SKILL copies this pass); row 20: the
  scripts-scope census counts `.py` files — a `.sh` addition moves no census
  (verified by the zero-literal gate in the full battery).
- Register: engineering (internal design record, agent skill and agent brief —
  not published operator/user documentation; no ASD-STE100 leg).
- CI cost: one fast unit module in `gates` (subprocess-driven, ~seconds).

## 7. Honest residuals — what this design cannot measure or stop

- A WILLFUL lane writing the shared checkout by absolute path (§2 residual;
  write-gate slice, issue #508).
- A lane forging GIT_COMMITTER_DATE reads pre-arm and evades the commit
  compare (the ACK half of the conjunction still requires cooperation).
- The wake is orchestrator-liveness-bounded: if the orchestrator session dies,
  the background wake dies with it. Drill A measures the wake's latency on a
  live session; a dead-session wake is out of scope (the next park arms again).
- A compliant lane committing in the same second as the arm reads ACTIVE and
  is killed (measure-zero in the drills; disclosed, fail-closed by choice).

## 8. Review tier and keyword scan (#254)

**Tier 3, by design judgment** — a mechanism that force-removes worktrees
earns the deep lane — **and by the Step-1 keyword rule**: the expected diff
text carries `subprocess` (7 occurrences, all in `tests/unit/test_lane_park.py`
— the harness invoking the script). Scan over the whole expected diff (the
four §5 files): `threading` 0, `asyncio` 0, `subprocess` 7, `sha256` 0,
`hashlib` 0, `migrate` 0, `recovery` 0, `protection` 0. Tier 3 per the rubric:
two independent adversary lanes at refute + full battery.

## 9. Measurable proof — pre-committed acceptance rule

Written before any acceptance measurement ran in this worktree. The only
pre-record executions here: baseline gates (ruff clean; mypy fresh-cache
clean, 446 source files) and a git-mechanics feasibility scratch outside the
repo (worktree remove via `--git-dir`, `branch -M` after removal, resume from
an archive ref — all exit 0). None touches T1-T4.

**CI tests (RED-first, RED run pasted into the commit message):**

- **T1** a deaf-writer process committing after arm → `check` = ACTIVE
  (`test_t1_deaf_writer_committing_after_arm_is_active`). RED rule: disable
  the commits-since-arm compare and the verdict flips to QUIESCENT, so T1
  fails.
- **T2** ACK plus no commits → QUIESCENT
  (`test_t2_ack_and_no_commits_is_quiescent`).
- **T3** fold removes the worktree AND preserves the ref under
  `archive/parked/` (`test_t3_fold_removes_worktree_and_preserves_ref`; the
  resume `worktree add` from the archived ref is asserted in the same test —
  Drill B's "branch intact" control).
- **T4** fold succeeds with a mid-write partial file present
  (`test_t4_fold_succeeds_with_mid_write_partial_file`).
- Discriminating arms beyond the acceptance minimum: no-ACK → ACTIVE
  (fail-closed), re-arm while bound → refused with the epoch unchanged, and
  `enforce` names TaskStop + fold on ACTIVE (the wake contract the drills
  assert on).

**Live drills, n=2 at D=15 minutes, run by the orchestrator** (a builder
cannot dispatch agents):

- **Drill A (deaf lane — the recorded failure mode).** Brief a real lane to
  ignore all messages and commit about every 2 minutes. Arm, wake, enforce.
  PASS = zero commits with a committer timestamp after arm+D, worktree absent,
  wake latency ≤5 min recorded.
- **Drill B (false-kill control).** A compliant lane that ACKs and idles.
  PASS = it is NOT stopped, its worktree folds cleanly at resume and its
  branch is intact.

**SHIP** = both drills pass. **KILL** = any post-arm+D commit in A, or B's
lane stopped. **UNDERPOWERED** = A's wake fired more than 5 minutes late.

**Rejected explicitly:** "orchestrator sends a stop and the lane confirms" is
NOT the test — delivery is the measured-failing mechanism; the control that
fails without delivery is Drill A.

**GATES (standing):** FAST lane every commit — bare `uv run ruff check .`,
fresh-cache bare `uv run mypy`, focused pytest for touched modules; full
battery ONCE before push. TRUE exit codes only; counts read from junitxml.
RED-first for T1-T4 with the RED run pasted.

## 10. Top risks, each with its falsifier

- **R1 fold's archive-ref collision** (two folds of one lane in the same
  second force-overwrite `archive/parked/<lane>-<ts>`) → pathological by
  timestamp granularity; the overwritten tip stays reachable via reflog.
  Falsify: observe a collision outside a same-second double fold.
- **R2 same-second kill of a compliant lane** → falsified directly by Drill B
  (the false-kill control).
- **R3 the wake never fires** (background shell dies with the session) →
  falsified by Drill A's recorded wake latency; >5 min late = UNDERPOWERED,
  never firing = re-arm and re-run.
- **R4 `git worktree remove --force --force` behavior varies across git
  versions** → falsified by T3/T4 across the CI matrix (ubuntu + macOS) and
  scratch-validated on this host's git this pass.
- **R5 someone later "softens" check to trust mtime over the recorded epoch**
  → pinned by the tests reading `armed_epoch` from `PARK.intent`; the re-arm
  refusal arm pins the bound's immovability.

## 11. DON'T-BUILD assessment

Not a don't-build. The finding is verified at source (§0), the failure mode is
ledgered first-hand (0/3 delivered, a pushed PR head, a hard kill), the fix
extends proven in-tree shapes (`merge-verified.sh`, run close, the `.wt/`
discipline) with no new architecture, the proof is executable in both
directions (RED-rule T1; false-kill Drill B), and the harness primitive it
depends on (TaskStop) is first-hand-verified to exist and fire in this
installation.
