# Issue #241 slice 1 — the timing lane and the priming-starvation classification

Design record for the first stabilization increment of the #240 red-lane class.
Written before any post-merge measurement (see the acceptance rule, §5). Tree:
`main` at `d648ab8`. Standards-bump hold: this diff moves no standards bytes
(`git diff origin/main...HEAD -- standards/` is empty; no version strings touched).

## 0. Root cause established, not assumed — row 7's mechanism is corrected here

The sweep inventory (issue #241 comment) attributes row 7
(`test_divergent_wall_moves_x2_not_x1`, CI run 36309281160) to a "uvicorn
signal-server startup race at rig bring-up (STARTUP_FAILURE SystemExit 3)" and
prescribes "rig-side startup retry/backoff in the priming wait".

That mechanism does not exist. Evidence:

- An import census over the tree (`import uvicorn`, `uvicorn.Config(`,
  `def _boot`) shows **zero** uvicorn references in
  `tests/integration/test_cross_instance_continuity.py`. The `ContinuityRig`
  (`test_cross_instance_continuity.py:555`) is pure in-process: two `OTDPBridge`
  instances over in-memory adapters, a `RunStreamHost`, a `_RunMonitor`, one
  SQLite store. No server, no port, no signal-server process.
- The gates-job log of run 36309281160 (job 108591978690) shows the actual
  failure:

  ```
  FAILED tests/integration/test_cross_instance_continuity.py::test_divergent_wall_moves_x2_not_x1
    - AssertionError: a bench signal failed to serve at priming
  ```

  The `SystemExit: 3` / `uvicorn/server.py line 109 startup` lines in the same
  log are the **pinned, passing** traceback text of
  `test_startup_admission_refusal.py::test_startup_refuses_poisoned_lattice_and_leaves_store_empty`
  (that test exists to prove uvicorn exits 3 on a poisoned lifespan — invariants
  CON-1 amendment). The sweep lane read adjacent log lines as the mechanism.

The row-7 failure SITE: `ContinuityRig.__init__`'s C14 priming block asserts
every bench signal served **valid** at the priming read. The observed
invocation's attribution is corrected by the fold review (§8 R1): run
36309281160's failing leg is the PROBE leg of the same test
(`monitor_wall_rate=10.0`, `no_trip=True`, `continuous_conditions=[]` — db
`rig-non_capture-buffered-10.db` in the log), where the divergent wall inflates
every host age ~9x construction elapsed and, with no conditions live, nothing
can latch a block — the validity assert is the only gate; the same run's
rate-1.0 baseline trials passed moments earlier. So the OBSERVED red is
wall-rate-driven age inflation on the probe config, not bare loaded-host
starvation, and the wall-rate guard (§8 F2b) is what closes that instance. The
classification this slice adds remains load-bearing for the CONDITIONED-policy
presentation the same site admits (the wave-1 adversary showed it is the only
retry path): under a loaded runner, construction itself (store migration,
descriptor publishes, two bridge opens) is an un-polled window —
`drain_until_quiet`'s own docstring names it ("construction time — imports, the
store migration, the priming dispatch — is itself an un-polled window whose
backlog would otherwise age the first settle tick past the bound on a loaded
host") — so sig-rig-b's first read can arrive aged past `max_age_ms` with a
conditioned policy live, and the assert fires. That presentation is
construction-time fixture starvation: exactly the class `TrialInfrastructureError`
(review finding F4 on PR #236) was built for — "a trial whose measured dispatch
never ran because the host starved the fixture BEFORE it" — but the priming site
predates the classification and raises a plain `AssertionError`, which
`run_trial`'s retry loop (`test_cross_instance_continuity.py:943`) lets straight
through. The rig-side startup retry the sweep asked for already exists; one
classification site is missing. Slice 1 adds it (§2.1).

A correction comment goes on issue #241 as part of this slice's arc (the
inventory is evidence; wrong mechanisms in it would misdirect slice 2).

## 1. Mechanism — what the fragility is and what slice 1 changes

**The fragility.** The suite runs serially (`uv run pytest -q`, no xdist —
`.github/workflows/ci.yml` `gates` job), so the load that breaks these tests is
not intra-suite parallelism. It is runner-level wall-clock stretch on a shared
GitHub-hosted VM: noisy neighbors, plus the serial suite's own residue by the
time a fragile test runs (page-cache and memory pressure, draining threads from
prior rigs, WAL checkpoints of prior tmp stores, GC). Measured shape (the sweep's
quiet-machine proof pass vs CI): `test_second_dispatch_lock_block` waits 56.2 ms
quiet vs 302.4 ms in CI against its 200 ms bound (5.4x); the range gate's X1
trial hit 107.5 ms in CI; `drain_until_quiet` hit its 2000 ms cap with 39 frames
due. The bounds themselves are honest measurement bands; the *condition* under
which they are measured is not controlled.

**What slice 1 changes — two things.**

1. **A dedicated `timing` CI lane** (new `timing` job) that runs the real-paced,
   marker-selected set on its own fresh VM, and a `gates` change to deselect that
   set (`-m "not timing"`). The two filters are complementary, so their union is
   the full collection — no test loses CI execution (structural, not
   policy-checked; §5 AR-1 pins it). What this honestly buys on hosted runners:
   (a) removes the suite's own residue (the marked tests run within ~2 min of VM
   boot, before any bulk-suite churn); (b) re-rolls the noisy-neighbor dice on an
   independent VM; (c) **attribution** — a red `timing` check is legible as a
   timing question, not a logic question, and vice versa; (d) a stable,
   same-shaped-every-run measurement environment for slice 2's re-band
   distributions. What it cannot buy: a guarantee of quiet. A 5.4x stretch can
   still land on the timing lane; §5's acceptance rule pre-commits both
   directions of that bet.
2. **The priming-starvation classification** (§0): the signal-validity priming
   assert in `ContinuityRig.__init__` becomes a `TrialInfrastructureError`
   raise, routing construction-time starvation into `run_trial`'s existing
   fresh-rig retry (max twice, fresh store per attempt — `trial_index * 10 +
   attempt`). No bound changes anywhere: every numeric assert in the marked set
   is byte-identical after this slice. The retryable class widens by exactly one
   structurally-typed site, pinned by test, and an exhausted retry still fails
   the trial (`TrialInfrastructureError` subclasses `AssertionError`).

Not in slice 1, deliberately: no re-band of any bound (that is slice 2, from
load-lane measurements), no virtual-clock migration, no change to
`drain_until_quiet`'s loud cap (a cap-hit currently fails hard; whether that
class should be retryable is decided from lane data — deferral D1).

## 2. Minimal first-increment scope

### 2.1 Priming classification (RED-first, Python behavior change)

In `ContinuityRig.__init__`, end of the C14 priming block — the assert whose
message is `"a bench signal failed to serve at priming"` — becomes:

```python
if not all(value.valid for value in self.snapshots[-1][1].values()):
    raise TrialInfrastructureError(
        "a bench signal failed to serve at priming "
        "(construction-time starvation; run 36309281160)"
    )
```

The sibling asserts stay plain: `"monitoring fixture degenerate"` (priming
dispatch status), `"the wrapper never ticked"`, `"the retain seam never fired"`
police wiring degeneracy and have no CI evidence of load-triggering — retrying
them would mask a dropped wrapper behind two wasted rigs.

`run_trial`'s docstring enumerates the F4 carrying sites; the list gains this
site ("the construction-time priming signal-validity check — issue #241 slice 1,
the observed CI failure"), keeping the disclosure complete.

New pin test beside the F4 pins (`test_cross_instance_continuity.py`, near
`test_infrastructure_marker_retries_on_a_fresh_trial`):
`test_priming_signal_starvation_is_infrastructure_and_retries` — force the
first rig construction's priming B-read to serve an over-aged reading
(monkeypatch the adapter's read path for the first construction only, the
`flaky_once` counter shape); assert `run_trial(...)` returns an outcome with
`retries == 1` and the second, unpatched construction succeeded. RED on
unmodified `main`: the plain `AssertionError` propagates out of `run_trial` and
the test errors. A second arm pins the type directly (forced staleness on every
construction exhausts at two retries and raises `TrialInfrastructureError` —
the existing exhaustion-pin shape).

### 2.2 The `timing` marker and the lane (selection-only; acceptance per §5 AR-1)

- `pyproject.toml` `[tool.pytest.ini_options]` markers list gains:
  `"timing: real-paced wall-clock measurements (pacing bands, precision gates, busy-retry windows); CI runs these serialized in the dedicated timing lane — deselect locally with -m 'not timing'"`.
- `tests/integration/test_cross_instance_continuity.py` and
  `tests/integration/test_capture_sequential_model.py`: module-level
  `pytestmark = [pytest.mark.timing]` (the files ARE the two real-paced rigs;
  the static classifier-table and retry-pin tests in the continuity file ride
  along — they still run in CI, just in the lane; sub-second cost, disclosed).
- `tests/unit/test_otdp_bridge.py`: `@pytest.mark.timing` on exactly the three
  row-B contention tests (sweep rows 14/15/16):
  `test_row_b_clamp_bounds_the_mid_capture_wait_by_the_step_deadline` (line 2513),
  `test_row_b_both_clamp_orderings_classify_one_pair` (line 2593, 2 param cells),
  `test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot` (line 2638).
  Row 17 (`...negative_injected_remaining...`) stays unmarked per the sweep's
  keep-and-document disposition.
- `.github/workflows/ci.yml`: `gates`'s Test step becomes
  `uv run pytest -q -m "not timing"` (with a comment stating the complementary
  partition); new `timing` job — same checkout (submodules recursive) + setup-uv
  + `uv sync --locked`, then `uv run pytest -q -m timing`. No lint, no mypy, no
  fixture-keys step, no `check-sdk-standards` in the lane: those run in `gates`
  over the same tree, and no marked test depends on the signing keys (the
  signing tests are registry tests, unmarked; if a keys-dependent test is ever
  marked, the keys-skip is named and loud — drift obligation 5's note). The lane
  stays serial forever: adopting xdist there would reintroduce exactly the
  competition this slice removes; the job's comment says so.

### 2.3 Docs

- `docs/internal/drift-and-obligations.md` CI map gains the `timing` row (what
  it catches: the real-paced set, serialized, on its own VM; what it does not:
  guarantee a quiet host).
- That doc's "Testing conventions worth upholding" gains one line: ms-scale
  wall-clock bound asserts on real clocks belong in the `timing` lane (marker),
  or on injected clocks.
- Obligation 4 check at build time: README / operator-guide / development docs
  that describe the CI shape get the fourth job named. The CI-map row is
  mandatory; the prose sweep is the builder's G5 walk.

### 2.4 Tracker

- Correction comment on issue #241 (§0) — the inventory's row 7 mechanism and
  the "uvicorn signal-server" label in the top-3 summary are amended to the
  priming-starvation mechanism, citing the log excerpt.

### Deferral table

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | `drain_until_quiet` cap-hit retryability (converting the loud 2000 ms cap assert to `TrialInfrastructureError` so a starved delivery path retries on a fresh rig) | issue #241 slice 2 | a timing-lane execution whose log carries the drain-cap assert ("hit its 2000 ms cap with N frame(s) still due") — decide retry-vs-band from that lane's frame-due measurements |
| D2 | range-gate re-band (25%-of-200 ms spread bound, 5-trial cells) | issue #241 slice 2 | the first in-lane range-gate red post-merge (the UNDERPOWERED message in a timing-lane log), or slice 2's measurement pass opening — whichever first |
| D3 | `control_x2` 50 ms ceiling re-band (quiet median 38.0 ms, tightest margin in the battery) | issue #241 slice 2 | first in-lane `control_x2` red, or slice 2's measurement pass opening |
| D4 | virtual-clock migration of the sequential-model quantities (order-based restatement of the lock-block and monitor-gap properties, keeping one real-clock representative) | issue #241 (slice-3 posture, documented on the issue) | a second in-lane red of the sequential-model 200 ms family after slice 2's re-bands land |
| D5 | marker-rot guard (an automated check that a new test carrying a real-clock ms bound has the `timing` marker) | documentation here | a `gates` red on an unmarked test whose failure is a ms-bound assert, post-merge |
| D6 | keep-and-document clusters (sweep rows 8/9/17/18/19: event-recovery trio, r11, r12, negative-injected row-17, kill-mid-run; row 20 demo-lattice disclosed flake) | issue #241 closure pass (one documentation comment dispositioning each row) | each row's own recurrence: a second CI flake of that test id |
| D7 | plugin-lane paced tests (sweep row 26, `plugins/fnirsi/dps150/tests/`) | issue #241 closure pass (documented out-of-lane) | a plugin lane entering CI |

## 3. Precedent (all in-tree, all extended not invented)

- **The `slow` marker** (`pyproject.toml` markers list): registered marker whose
  contract is "CI runs these; deselect locally for quick iteration". The
  `timing` marker is the same mechanism with a lane instead of a deselect.
- **The F4 retry classification** (PR #236): `TrialInfrastructureError`
  (`test_cross_instance_continuity.py:841`) + `run_trial`'s type-based matcher
  and fresh-index retry, pinned by `test_infrastructure_marker_retries_on_a_
  fresh_trial` / `..._exhausts_at_two_retries`. Slice 1 extends the carrying-site
  list by one construction-time site — the exact shape F4's docstring describes
  ("the host starved the fixture BEFORE [the measured dispatch]").
- **The existing CI job split**: `gates` / `ui` / `systemd` are already
  responsibility-partitioned jobs over one tree; `timing` is a fourth, and the
  renderer-freshness step in `ui` is the precedent for a check living in exactly
  one job by design.
- **Fail-loud rig helpers**: `drain_until_quiet`'s cap assert and the C14
  priming asserts are the established posture this slice keeps — the one
  behavior change (priming → retryable) follows the F4 charter, and the loud
  cap stays loud (D1).

## 4. Invariant impacts

- **A06 (evidence over assertion)** — the load-bearing one, both directions.
  The lane makes the measurement *condition* attributable: a stretched-host
  artifact no longer presents as a property of the system, and slice 2's re-band
  claims get a named environment to cite. The priming classification is A06 in
  the small: construction-time starvation is an infrastructure fact, and
  presenting it as a trial failure launders an environment artifact into a
  measurement record. Disclosed widening: the retryable class gains one site;
  the marker is structural (type-carried), the exhausted retry still reds.
- **No CTL/STO/CON/REG invariant is touched.** No production code under `src/`
  changes; no store, executor, protection, or admission path moves. No new
  invariant is needed — this is test infrastructure, and the CI map
  (`docs/internal/drift-and-obligations.md`) is the governing doc that moves.
- **Tier**: no on-disk format or schema changes; not a Tier-3 shape. The
  standards-bump hold is satisfied mechanically (empty `standards/` diff, no
  version strings; `pyproject.toml` is touched only in the markers list).
- **Obligations walked**: 4 (CI is operator-visible → CI-map row mandatory,
  prose surfaces swept at build), 5 (workflow change → cold full-suite run in
  the acceptance protocol; no marked test depends on fixture keys), 10 (no
  dependency change). CLAUDE.md §3's merge-on-full-rollup discipline applies to
  the four-job rollup from now on.

## 5. Measurable proof and the pre-committed acceptance rule

**Build-time (PR) acceptance — the yaml part cannot RED; this is its evidence:**

- **AR-1 (partition integrity):** `uv run pytest --collect-only -q -m timing`
  yields set T; `-m "not timing"` yields set G; unfiltered yields set U. Require
  T ∪ G == U and T ∩ G == ∅ (complementary markers make this structural, but it
  is proven, not asserted: the two collected-id lists are diffed), T non-empty,
  and T's membership exactly the two marked files plus the 4 row-B test ids in
  `tests/unit/test_otdp_bridge.py` (4 ids across 3 functions — one
  parametrized function contributes two). Recorded in the PR body.
- **AR-2 (RED→GREEN):** the §2.1 pin test is shown failing on unmodified
  `main` (plain `AssertionError` propagates; observed failure output in the PR)
  and passing on the branch. Collected-count check per the RED-sanity
  convention (a `no tests ran` is a failed check).
- **AR-3 (both lanes green):** `gates` (with `-m "not timing"`, plus lint/mypy/
  check-sdk-standards unchanged) and `timing` both green on the PR, read from
  the full rollup, never a filtered view.
- **AR-4 (cold run):** per drift obligation 5, one cold full-suite run (fresh
  venv) locally: `uv run pytest -q` unfiltered, green — proving the union still
  executes green in one process on a quiet host.

**Post-merge acceptance — pre-committed BEFORE any lane number is read:**

- Unit of observation: one `timing` job execution on CI (main pushes and PR
  runs both count). Counted red: a failing test id inside the marked set. A
  runner-level `startup_failure` (job never started) is a GitHub infrastructure
  fault, categorized separately, never silently counted as either direction.
- **Ship / isolation stands:** at most 1 marked-set red in the first 20
  timing-lane executions. The lane then hosts slice 2's measurements.
- **Kill / isolation alone does not deliver a green lane:** 2 or more
  marked-set reds in the first 20 executions. The kill does not revert the lane
  (attribution and the measurement environment keep their value); it kills the
  "green lane by isolation" claim and makes slice 2's evidence-backed re-bands
  (D1–D3) mandatory before #241 can close.
- **Underpowered, not conclusive:** if slice 2 opens before 20 executions
  accumulate, flake conclusions from the partial sample are anecdotal; a single
  red within the first 5 executions triggers one local induced-load study
  (marked set under deliberate CPU contention) instead of a lane verdict. Every
  published claim carries its denominator: "N timing-lane executions, R red
  inside the marked set".
- **Cost disclosure (expectation, not a gate):** timing job wall-time recorded
  at merge; expected under ~5 min (setup ~90–120 s + marked set ~45–75 s quiet,
  2–3x under load). Gates loses the marked set's runtime; jobs run in parallel
  so PR wall-time tracks the slowest job (gates, ~4 min observed). Runner cost:
  one extra hosted job per run — free on this public repo, disclosed anyway.

**Directional check (not gating):** the marked set's in-lane red rate should be
below its historical gates rate (4 nameable marked-set red events across recent
CI: PR #240 lock-block 302.4 ms; run 35832745149 monitor-gap 353.3 ms; run
36283610572 range-gate X3; run 36309281160 priming starvation — historical
denominator not assembled, so this stays directional and the pre-commit rides
the forward 20-execution sample only).

## 6. Top risks and their falsifiers

1. **Hosted runners stay noisy — isolation cannot promise quiet.** The lane
   removes suite residue and re-rolls the dice; a 5.4x neighbor stretch can
   still land. Falsified by the kill arm of §5 (≥2 reds / 20 executions). This
   is why slice 2 exists and why no bound moved here.
2. **The priming classification masks a real degeneracy.** A signal that
   genuinely never serves now burns three rigs before failing. Mitigated: the
   type is pinned, exhaustion still reds, the sibling wiring asserts stay
   plain, and the retry budget is visible (`outcome["retries"]`, asserted
   `<= 2` by the axis trials — a lane that routinely sits at 2 is slice-2
   signal, disclosed under D1–D3).
3. **Marker rot.** New real-paced tests land unmarked in `gates` and flake
   there. No automated guard in this slice (D5); the reviewer convention line
   (§2.3) is the interim catch. Falsifier: the D5 reopen trigger firing.
4. **Retry-budget interaction.** Priming retries and drain-starvation retries
   draw on the same `retries <= 2` budget the axis trials pin — a loaded lane
   could convert a starvation red into a budget red. Unchanged behavior class
   (the sweep's "retry-budget-dependent" family, documented); watch via the
   lane logs, decide in slice 2.
5. **Lane-variance confound for slice 2.** The timing lane's VM pool could be
   systematically slower than gates', biasing re-band measurements high. Watch:
  the trial-log provenance (`test_trial_log_written_with_provenance`) and the
   printed quiet-reference numbers; slice 2 compares against the sweep's
   quiet-machine medians, not against gates.
6. **The row-7 correction is wrong** (a uvicorn race does exist somewhere).
   The census covered the continuity file and the log shows the passing
   refusal-test traceback adjacent; residual home would be the event-recovery
   child process (real `uvicorn.run` in a subprocess). Watch: any red whose
   traceback shows uvicorn startup frames in the *failing test's own* stack.

## 7. File-level change list

| file | change |
|---|---|
| `pyproject.toml` | register the `timing` marker (markers list beside `slow`) |
| `tests/integration/test_cross_instance_continuity.py` | `pytestmark = [pytest.mark.timing]`; priming signal-validity assert → `TrialInfrastructureError` raise (§2.1); `run_trial` docstring carrying-site list gains the site; new pin test `test_priming_signal_starvation_is_infrastructure_and_retries` (+ exhaustion arm) beside the F4 pins |
| `tests/integration/test_capture_sequential_model.py` | `pytestmark = [pytest.mark.timing]` |
| `tests/unit/test_otdp_bridge.py` | `@pytest.mark.timing` on the three row-B tests (lines 2513 / 2593 / 2638) |
| `.github/workflows/ci.yml` | `gates` Test step → `uv run pytest -q -m "not timing"`; new `timing` job (checkout+submodules, setup-uv, `uv sync --locked`, `uv run pytest -q -m timing`) |
| `docs/internal/drift-and-obligations.md` | CI map `timing` row; one testing-conventions line |
| `.claude/deep-review/2026-09-27-issue241-slice1-timing-lane-design.md` | this record, committed before any lane measurement |
| issue #241 | correction comment on the row-7 mechanism (§0) |

No `src/` bytes move. No `standards/` bytes move. Every numeric bound in the
marked set is byte-identical after this slice.

## 8. Review-fold amendment (post-build, pre-merge; principal directive: fold all)

The adversarial + mechanism-critic review wave on the built branch folded seven
findings. Each fold is RED-first with its own commit; every mechanism choice and
deviation is below.

**F0 (CRITICAL, adversary) — the timing job's workflow did not parse.**
`python-version` sat at step level outside `with:` in the timing job's setup-uv
step (`.github/workflows/ci.yml:79`); pushed run 36320315011 failed with the
invalid-workflow signature. Folded standalone (b455386): one-line indent, action
clean on the fixed tree, RED reproduced locally on the pre-fix blob
(`unexpected key "python-version" for step to execute action`).

**F1/F2 (HIGH, critic + MEDIUM, adversary — converged) — the classification
covered a sub-band of the class it names.** Read-#1 starvation never reached the
validity site: the wrapper's pre-dispatch tick read the aged signal itself, the
fail-safe latched `signal_invalid`, and the monitor refused the priming dispatch
at the door — the trial died non-retryably on the plain degenerate-wiring assert
(confirmed live: the refused envelope in the RED output carries exactly the
`_freshness_trip_block` discriminant inputs). Mechanism **(a)** chosen over
**(b)** with evidence: the priming site classifies a non-OK priming result whose
refusal is the monitor's own `blocked` latch plus the freshness kind — the
discriminant the measured dispatch already uses. Mechanism (b) — hoisting a
validity check before the gated dispatch — was rejected: the first snapshots
exist BECAUSE the wrapper ticks inside the priming dispatch, so a hoisted check
needs a new pre-priming tick (a different construction rhythm, perturbing the
very un-polled window under measurement), and the block-refusal can still land
after a fresh hoisted check — (b) narrows the window without closing it.
`_install_priming_starvation` gained `starve_from_read` (0f69607).

**F2b (MEDIUM, critic) — clock-domain hole at the classified site.** Under the
divergent-wall probe's rate-10 injection the priming age inflates ~9x
construction elapsed; a loaded-host probe could fire the classification with a
FALSE starvation attribution, and the retry is structurally useless (every
construction re-injects the wall). Fold: both priming classification arms guard
on the real wall rate — the same protection the pre-flight staleness check
gives itself under `no_trip` (d160534).

**F3 (MEDIUM, critic) — the retry budget had no evidence base.** A bare
`retries` int discarded the composition; exhaustion reported only the last
attempt's site. Fold: `TrialInfrastructureError` gains a REQUIRED `site=`
keyword (a defaulted label would let a future site raise unlabelled); every
production raise is labelled; `run_trial` records `outcome["retry_sites"]` and
the trial line prints the count and the ordered sites (70a6d77).

**F4/F3' (LOW, critic + NIT, adversary) — construction raises escaped the
failure belt.** The rig is built before `_run_trial_once`'s try, so a starved
construction leaked its store and bridges into the next attempt's timing
envelope. Fold — **mechanism deviates from the briefed shape, with evidence**:
a run_trial-level None-guarded belt cannot see the partial rig (when
`__init__` raises, the local assignment never happens and the half-built
instance is unreachable). `_construct_rig` allocates the instance first
(`__new__` + explicit `__init__`) and belts the failure through the module's
`_close_partially_constructed` shape; machine-checked by a store census —
every `Store.open` across an exhausted construction-starved trial is matched
by a `Store.close` (840df2a).

**F5 (LOW, critic) — disclosure: intra-lane ordering residue.** Collection
order runs the sequential-model battery before the continuity rig; the fresh-VM
claim removes bulk-suite residue from other jobs, not ordering within the lane.
Folded into the CI-map `timing` row's Does-NOT-catch clause (this wave's docs
commit).

**F6 (NIT, critic) — disclosure: the ride-along.** The `-m timing` set carries
the continuity file's mostly-static tests alongside the real-paced cells (50 at
tip — 45 when this fold landed; the fold waves' own pins grew the file), so
a LOGIC regression in that file presents as a timing-lane red. Accepted with
eyes open: the alternative (per-test marking inside the file) splits the file's
retry-machinery pins from the rigs they pin and costs marker discipline for a
diagnosis step a red's traceback already resolves. The PR body carries this
note; recorded here per the fold directive.

### Wave 2 — reviewer residuals on tip 7ee2264 (docs-only; fold-all)

The reviewer verdict on the folded branch was READY with three residual
findings. All three are attribution/wording corrections — no behavior change,
no new pins.

**R1 (MEDIUM, reviewer) — mechanism attribution overclaim at three sites.**
The reviewer pulled run 36309281160's log: the failing invocation is the PROBE
leg of `test_divergent_wall_moves_x2_not_x1` (`monitor_wall_rate=10.0`,
`no_trip=True`, `continuous_conditions=[]`), where the wall inflates every
host age ~9x construction elapsed and the condition-free config leaves the
validity assert as the only gate; the same run's rate-1.0 baseline trials
passed moments earlier. The observed red is therefore wall-rate-driven age
inflation on the probe config — closed by the F2b wall-rate guard (d160534),
NOT by the classification. Folded: §0's mechanism passage rescopes the
loaded-host sentence to the conditioned-policy presentation and names the
wall-rate term for the observed run; the `_install_priming_starvation`
docstring drops "which is how the observed CI failure reached the validity
assert" for the same scoping. The classification stays as built — wave 1's
adversary proved it the only retry path for the conditioned presentation.
**Disclosed erratum:** commit 0f69607's message attributes the observed run
to construction-time fixture starvation; history is not rewritten — that
attribution is wrong per this finding, and this entry is its correction of
record.

**R2 (LOW, reviewer) — the lane comment overclaimed attribution.** The
ci.yml lane comment said "a red here reads as a timing question, not a logic
one", contradicting F6's own ride-along disclosure (50 of 58 wave-end marked
ids are the continuity file, static logic tests included). Folded: the
comment now scopes the attribution to the real-paced subset and names the
ride-along as the exception where a red can be logic.

**R3 (LOW, reviewer) — "proven structurally at build time" overstated the
proof's home.** ci.yml's Test-step comment and the CI-map `timing` row said
the partition is proven at build time; AR-1 places that proof at PR time —
a human-recorded set diff in the PR body, not an automated gate. Folded:
both reworded. The complementary markers make the partition structural BY
CONSTRUCTION (no third state exists); the PROOF is AR-1's recorded diff at
PR time.

**Post-fold state:** still no `src/` bytes, no `standards/` bytes; AR-1's
partition re-proven at wave end with the new collected counts (the fold adds
pins to the timing-marked continuity file, so T grows; the design's §5 numbers
are superseded by the wave-end numbers in the builder's report). Wave 2 moves
prose only — the collected counts stand (T=58, G=2309, U=2367).

### Wave 3 — reviewer findings 4–5 on PR #246 (fold-all, late findings)

**R4 (LOW, reviewer FU-1) — guard-predicate asymmetry at the probe-wall
exemption.** The pre-flight staleness check exempted on `no_trip` while the
priming arms exempted on `monitor_wall_rate == 1.0` — two predicates for one
conceptual exemption. The latent hole (a probe with rate != 1.0 but a live
policy, where the pre-flight check false-fires on wall-inflated ages exactly
as the priming site did pre-F2b) is closed by one shared predicate,
`_probe_wall_injection(rate, no_trip) = rate != 1.0 or no_trip`, used at all
three classification sites; the rig carries the `no_trip` fact explicitly
(policy identity was not a clean carrier). RED (pre-fix, `starve_from_read=4`
— calibrated past construction's own reads so construction completes and the
injected age lands at the pre-flight read): the partial probe's terminal was
`TrialInfrastructureError('pre-dispatch staleness: sig-rig-b-level age 10512
ms')` at rate=10.0/no_trip=False — the misfire itself, exhausted across three
rigs that each re-injected it. Post-fix the same trial never carries the
pre-flight attribution; the pin's truth table holds the one classify state
(1.0, live policy). Calibration note: thresholds 2 and 3 die inside
construction (the pre-tick latch and the subscribe read) — 4 is the first
threshold that presents the pre-flight misfire (394c4b4).

**R5 (NIT, reviewer) — wording drift, four fixes.** (a) AR-1's "four row-B
param cells" now names the verified shape: 4 test ids across 3 functions in
`tests/unit/test_otdp_bridge.py` (one parametrized function contributes
two — verified by collect). (b) F6's ride-along count now reads 50 at tip
(45 when that fold landed; the waves' own pins grew the file). (c) The two
"at most two retries" phrasings now state the fixed three-attempt budget the
exact-equality pin (`len(rigs) == 3`) actually enforces. (d) The
sequential-model "100–150 ms tolerances" claim — drifted against the real
`BUDGET_MS + 300` queued-run band — now names the per-quantity bands; the
same drift appeared in BOTH the module docstring and the marker comment
(review's finding named the comment only; both fixed). None of the edited
strings sits inside an assertion message tests match on (checked: the
synthetic `pre-dispatch staleness` raises pin TYPE-based matching and are
untouched).

**Wave-3 state:** the new pin moves T 58 → 59 (continuity 51 + sequential
model 4 + row-B 4); G and U move with it. Still no `src/` bytes, no
`standards/` bytes.
