# Cross-instance continuity instrument — row 1's executable decision rule (issue #172)

**Date:** 2026-09-26 · **Issue:** [#172](https://github.com/madeinoz67/benchweave/issues/172)
(the measurement rig for row 1 of the #43 record).
**Parent records:** `.claude/deep-review/2026-09-23-issue159-optionb-native-async-host-design.md`
(the §6 pre-committed decision rule — **frozen; this instrument implements it, never adjusts
it**) and the #167 activation record (the shared measurement surface this rig extends; its
merge `1211ab3` released the §8 park).
**Corpus:** no standards bytes move; no SDK touch; no `src/` change of any kind — the entire
instrument lives under `tests/`. `make check-sdk-standards` stays green trivially.
**Triage:** public, promoted deliberately — synthetic fixtures only (`bench.continuity-rig`,
`dev-rig-a`, `dev-rig-b`), every number from the committed rig or a named record, no real
bench, person, client, serial, or commercial term. Same content class as the #159 record.
**Verdict: BUILD.** The park is released (#167 merged 2026-09-24, verified below), the
instrument is test-only buildable against today's tree (every seam it needs exists in
production code), and machine checks (1), (3), (4), (5), (7) of the frozen rule are fully
landable now; (2) lands its boundary half; (6) is a when-built gate that stays pinned for
the reopen. Each partial landing is a named deferral with its home — never silent scope
creep, never a rule edit.

## 0. What this instrument is (and is not)

The #159 record made row 1 *decidable-in-principle*: §6 states the FIRE/KILL/UNDERPOWERED/
INCONCLUSIVE rule, written before any cross-instance number exists. What is missing is the
**numerator machinery** — a two-instance rig that measures X1–X4 on both dispatch arms, the
consistency controls around `T_acq_min`, and the classifier that turns trial ledgers into
arm verdicts. This increment lands exactly that, test-only.

Two rules live in this record and they are NOT the same rule — conflating them is the
easiest way to corrupt the frozen one:

- **The decision rule** (#159 §6): evaluates measured axes against **commissioned** bounds
  `G1/G2/P/TB`. No such bounds exist (A02: they come from a bench's qualification
  evidence). The instrument makes the rule *executable* — it never *evaluates* it against
  invented numbers. Every bound input the classifier tests use is synthetic table data,
  labelled as such; a missing bound reads UNDERPOWERED, it never defaults.
- **The instrument's own acceptance rule** (§5 below): ships the rig. Its denominator is
  the rig's own dispatch duration and the matched control — explicitly NOT `G1/G2/P/TB`
  and never citable as a commissioning.

## 1. Verified ground (read this session, not assumed)

- **#167's activation is on main.** Merge `1211ab3` (PR #177, 2026-09-24) added
  `control/stream_host.py` (RunStreamHost), `interfaces/device_closures.py`, the app.py
  `_build_run_factory` run-path bridge construction, the `_MonitoringClock` poll-slice
  wiring, and `tests/integration/test_run_activation.py`. Local main tip `456db63`.
  The composition: per adapter-mode device with a commissioned closure, `build_run`
  constructs `CaptureStagingStore` + `build_capture_services` + `build_stream_services`
  over the worker-thread store, loads a real `OTDPBridge` per device, registers each with
  the run's single `RunStreamHost`; `_RetainingCoordinator._prepare_run` arms the host
  (subscriptions derived from bench signals with declared `poll_ms`);
  `_MonitoringClock.wait_ns` runs `stream_host.poll_slice` inside wait slices.
- **The rig being extended runs green.** `UV_PROJECT_ENVIRONMENT=venv uv run pytest
  tests/integration/test_capture_sequential_model.py --junitxml=…` → 4 tests / 0 failures
  / 1.924 s (junitxml attributes; the rtk summary line is unreadable by convention —
  counts come from the XML). Tests: monitor gap 0.06 s, queued delay 0.11 s, lock-block
  0.06 s, contention 1.67 s.
- **The seams the axes need all exist in production code** (citations by symbol; line
  numbers drift, `docs/internal/invariants.md` convention):
  - `_RunMonitor.tick` → `read_signal_values(self._plugins, …)` — the snapshot builder is
    **multi-device-keyed** (`plugins: dict[str, DevicePlugin]`, one bench signal per
    `source.device_id`), freshness decided there as `age_ms = max(host-computed age,
    device-reported age)` with `valid = age_ms <= max_age_ms` **inclusive**
    (`control/protection.py` `read_signal_values`). A future-stamped `observed_at` is
    invalid, never maximally fresh.
  - `_RunMonitor.retain` — the WP07 per-tick snapshot hook (`retain: Callable[[dict,
    str]]`, called with `dict(snapshot)` every tick): the **X2 recording seam**.
  - `_MonitoringPlugin.dispatch` — the verb-agnostic `tick → block_result →
    inner.dispatch → tick` wrapper: the **X1 recording seam** (the existing rig's
    `_recording_tick` already wraps it).
  - `RunStreamHost.on_event` — replaceable per-run telemetry observer invoked from the
    contained dispatcher after each transactional landing: the **X3 landing seam**.
    `PollOutcome.host_received_at` carries the bridge's receipt stamp.
  - `ProtectionEngine._dispatch_actions` — safe actions dispatched through the (wrapped)
    plugins dict keyed by `action["device_id"]` under `min(action timeout, remaining
    protection)`: the **X4 seam**. Constructible directly in a harness
    (`plugins, policy, bench, clock, wall`).
  - `OTDPBridge` — per-instance `threading.RLock` + one `asyncio.Runner` per bridge;
    `dispatch` and `poll_event` both take that instance's lock; `_run`'s `bounded()`
    wraps every adapter await in `asyncio.timeout`. **B's lock is not held by A's
    dispatch** — the structural fact the movable/§8-bound separation pins (§2.6).
  - `bench_poll_ns` — the one poll-cadence derivation (min declared `poll_ms`, floored at
    the 10 ms default): the rig's fixtures declare `poll_ms` so the cadence is explicit,
    never the silent default.
- **The capture arm cannot go through the run path today** — the ACTIVE execution corpus
  (`execution/0.2.0`) still closes `step` at eight kinds; the capture family lives in the
  `0.2.0-dev` head only (`0608490`, #176; roll-up deferred per the devstage policy). The
  non-capture arm (slow `read`/`write` step with `timeout_ms`) IS procedure-expressible
  today. This splits the rig's composition strategy (§2.1) and seeds deferral D2.

## 2. Mechanism

### 2.1 Rig shape — a sibling file, composing production objects directly

**New file `tests/integration/test_cross_instance_continuity.py`** plus helper module
**`tests/integration/_continuity_rule.py`** (the `tests/control/_harness.py` precedent for
non-test helper modules under `tests/`). Not an extension of
`test_capture_sequential_model.py`: that file's docstring pins slice-1 *disclosure*
quantities and its `MonitoredHarness` is single-instance with an empty monitor plugin dict
and a vacuous `max_age_ms: 600_000` — the instrument needs different fixtures with
different meanings; surgery on the old rig would blur both docstrings' claims. #167 set the
sibling precedent (`test_run_activation.py` beside the sequential file).

**The harness is the `MonitoredHarness` shape extended to two instances** — direct
construction of the production objects, no registry/admission stack:

- ONE `Store` (one SQLite file, `check_same_thread=False`) — matching production, where
  the worker store is shared by every bridge's services.
- Device A (`dev-rig-a`): the capturing/slow-dispatch instance — `CapturingAdapter`
  variant (chunk-paced capture per the existing rig) and a paced-read/write variant for
  the non-capture arm; `build_capture_services` bundle; bridge with `capture=controller`,
  `stream=None`; `stream_host.adopt("dev-rig-a", bridge_a)` (close authority without
  stream registration — the app.py shape for an event_sink-less bridge).
- Device B (`dev-rig-b`): the non-capturing instance — streams (`build_stream_services`
  controller, `stream_host.register`), serves a bench signal under a declared device
  class (§2.3), and is the safe-action target for X4.
- Bench signals: `sig-rig-a-temp` sourced from `dev-rig-a` (the §8-bound comparator) and
  `sig-rig-b-level` sourced from `dev-rig-b` with `poll_ms: 50` (streamable; drives
  `bench_poll_ns` explicitly). **`max_age_ms` is dispatch-scale** (250 ms against a
  200 ms dispatch arm) — the #159 §2 pin that the old fixture's 600 000 ms made aging
  vacuous. The fixture's `max_age_ms` serves measurement discriminability ONLY; it is a
  rig constant, never a commissioned `G2` (A02 — §0's first rule).
- Monitor: `_RunMonitor(store, bench_id, policy, bench, **wrapped_plugins**, clock, wall)`
  — unlike the old harness's empty dict, the wrapped plugin dict is passed so ticks
  actually read both signals (this is the load-bearing difference; the C14 priming
  dispatch is kept and extended to assert both signals serve).
- A `RunStreamHost` armed exactly as production: `arm(bench, wrapped_plugins, monitor)`
  mints B's subscription; the harness drives `poll_slice` through a real
  `_MonitoringClock.wait_ns` during idle windows (the delay-step rhythm).

**What is reused vs built test-only:**

| Reused (production, unchanged) | Built test-only |
|---|---|
| `_RunMonitor`, `_MonitoringPlugin`, `_MonitoringClock`, `ProtectionEngine` | The B-device adapter (two classes, §2.3) |
| `read_signal_values`, `evaluate_conditions`, `bench_poll_ns` | The A-device slow read/write variant |
| `OTDPBridge`, `_run/bounded()`, per-instance lock | The two-signal dispatch-scale bench fixture |
| `build_capture_services` / `build_stream_services` / `CaptureStagingStore` | The trial loop + trial-log emitter (§2.7) |
| `RunStreamHost.arm/poll_slice/teardown/close`, `StreamPollEngine` (via the host) | The classifier + ledger dataclasses (`_continuity_rule.py`) |
| `retain` hook, `on_event` seam, `tick_recorder` shape | Census monkeypatch, divergent-wall clock, controls |

### 2.2 Arms

- **Capture arm** (light rig only — corpus gate, §1): `plugin.dispatch(capture_request,
  deadline_ns = now + budget)` with the chunk-paced adapter, exactly the existing rig's
  shape: natural duration ≈ 200 ms, declared budget 50 ms so the deadline-max cut lands
  `UNKNOWN` (the honest `bounded()` timeout arm; the revert map — disable `bounded()` and
  the gap tracks the natural duration — is inherited).
- **Non-capture arm (the mandatory F1 arm):** the same two-instance rig, but A's dispatch
  is a paced `read` (and a `write` leg) whose natural duration is `T_acq_min = 200 ms` —
  paced in adapter-internal slices with NO artifact traffic — dispatched with a deadline
  that accommodates it (`T_acq_min + margin`) so it completes `OK`. This is the arm the
  #159 refutation proved the exposure class runs through today (read/write are
  corpus-expressible and run-path-activated since #167's Decision 1).
- Both arms run on the same two-instance fixture; both carry the §3 controls.

### 2.3 The B-device classes (check 7's buffered/unbuffered pair)

The axis quantity is THE envelope `read_signal_values` computes —
`max(host-computed age, device-reported age)` — and both classes report it; the classes
differ in device behaviour, not in axis definition.

- **Buffered class** (§8-conformant host-driven feed): B's telemetry frames exist only
  when polled (`next_event`; "no hidden background task" is §8's own rule — the adapter
  keeps no background sampler). The device-side emission *schedule* is time-derived (a
  pure function of the harness monotonic clock: one frame per 20 ms since subscribe — no
  threads), and each event carries its device emission stamp in a schema-legal
  x-extension key (`x-rig-emit-ns`, matching the bridge's `x-[a-z0-9]+-[a-z0-9_-]+`
  pattern; the closed `$defs/event` key set otherwise). The parameter `read` serves the
  newest **received** frame with its true device stamp (`observed_at` = frame stamp,
  `age_ms` = elapsed since it). During A's dispatch the polls stop → the newest received
  frame ages by the blackout → **X2 is dispatch-scale on this class**. This is not a
  contrived fixture: it is the honest model of a host-driven stream device's parameter
  read under the corpus's own scheduling rule.
- **Unbuffered class** (fresh conversion per read): `read` performs an immediate
  conversion; `observed_at = now`, `age_ms = 0`. X2 collapses to host-side skew (~0) —
  the honest comparator showing the axis quantity is device-class-dependent and a bench
  must declare its class (A09 territory, not the rig's call).

**Modeling disclosure (finding, not a rule adjustment):** X2's dispatch-scale content on
the buffered class rests on the reading above of §8's host-driven feed. If a spec reading
shows an OTDP parameter read must always serve a fresh conversion, the buffered class
collapses toward the unbuffered one and X2's dispatch-scale content dies — the axis would
read ≈ period on every class and could never fire. That is a finding to surface with the
erratum path named (§8), not a reason to adjust §6: the envelope remains measurable
exactly as written either way.

### 2.4 The axes — measurement, clock domain, recording seam

Per trial (a trial = one fresh harness on a fresh tmp store; ≥5 trials per
arm × device-class):

- **X1 — tick-gap class.** Monotonic ms (`clock.now_ns` deltas from the
  `_recording_tick` wrapper — the existing rig's seam). The blackout reality pin:
  `max_tick_gap ∈ [dispatch − 50 ms, dispatch + 150 ms]` (the honest-form band inherited
  from the existing quantity-1 test). **Share separation** (the #159 §5 gap): the retained
  per-tick snapshots carry BOTH signals' envelopes — A's signal is the §8-bound share's
  indicator (its reads serialize with A's dispatch on A's lock under every host model),
  B's is the movable share's indicator. The structural pair (§2.6) makes the separation
  mechanical.
- **X2 — non-capturing-signal freshness gap at dispatch end.** The `age_ms` envelope of
  `sig-rig-b-level` in the FIRST post-dispatch retained snapshot (the `retain` hook
  seam). Wall-derived age domain (host-computed age is `wall_now() − observed_at`). Both
  device classes report it; the trial log records the class label.
- **X3 — events emitted vs landed.** For the device-emitted frames whose `x-rig-emit-ns`
  falls inside the dispatch window: `landed = true/false during window` plus the worst
  emission→landing latency, both on the harness monotonic clock (the x-stamp and the
  `on_event` landing stamp — one clock domain by construction; the wall-domain
  `observed_at`/`host_received_at` fields are recorded alongside and are the object of
  check 5). Seam: `stream_host.on_event` replaced by the trial recorder. After the
  dispatch returns, the harness drains via `_MonitoringClock.wait_ns` slices until the
  subscription is quiet, so every emitted frame eventually lands and the latency set is
  complete.
- **X4 — protective-action latency to the non-capturing device.** B's device model
  crosses the numeric condition bound at a scripted monotonic instant `T_cross` INSIDE
  A's dispatch window (time-derived step; the harness knows `T_cross` exactly). The
  monitor trips at the first post-dispatch tick; the harness then calls
  `ProtectionEngine(...).enter(...)` with the wrapped plugins (mirroring
  `_finish_run`), whose safe action is a `write` to `dev-rig-b`. Axis value =
  `action-landed − T_cross`, absolute monotonic ms. **Zero-point decision (disclosed,
  owner may veto):** the frozen rule says "absolute milliseconds" without naming the
  zero; this instrument pins **hazard onset → action landed** (the safety-honest bound)
  and additionally records the decomposition `onset → observation` and
  `observation → action` so the reopen can re-cut without re-measuring.

### 2.5 `T_acq_min` — consistency controls only, never the authority

The acquisition minimum is a device/qualification fact (A09); the rig's 200 ms pacing is a
fixture parameter. Two consistency controls per §6, asserted conjunctively, both labelled
as consistency checks in the trial log:

- **(i) Matched short-T control:** the same arm dispatched with `T = 20 ms` budget → the
  acquisition fails (`TIMEOUT`/`UNKNOWN`, never `OK`) — the pacing is a real floor for
  this fixture, not a label.
- **(ii) Split-refusal control:** capture arm — the fixture's device model makes the
  acquisition one-shot per window; dispatching it as two half-dispatches fails the second
  half (device-rejected; the manifests cannot cover the window), asserted against the
  fixture. Scalar-read arm — definitional (a single conversion is not splittable);
  recorded as a definition row, not a fake assertion.

### 2.6 The §8-bound / movable structural pair

Two short controls on the light rig, run during A's dispatch from a helper thread (the
existing quantity-3 thread shape):

- A helper-thread `read` on **B's** bridge during A's dispatch **succeeds promptly**
  (B's per-instance lock is free; nothing in B's bridge blocks) — the movable share's
  existence proof.
- A helper-thread `read` on **A's** bridge during A's dispatch **blocks until the capture
  ends** (§8 per-instance serialization) — the §8-bound share's proof.

Together they pin, mechanically and today, the #159 §5 claim the old single-source
fixture could not separate: the blackout is the single engine thread, not the device
topology. (Helper threads appear ONLY in these controls; the axis trials themselves are
single-threaded, like the production run path.)

### 2.7 Trial ledger and provenance emitter (check 3)

`_continuity_rule.py` defines `TrialRecord` (arm, device_class, axis samples with their
clock domains, control outcomes, fixture parameterization, and the exact reproducing
pytest invocation) and `emit_trial_log(records) -> dict` — a consolidated JSON with one
row per figure, each row carrying `command` and `parameterization` fields. The measurement
tests write it under the trial tmp dir and print the path. A shape test asserts every
numeric row in an emitted log carries both fields — the machine-enforceable half of
"every record-quoted figure cites a reproducing command". The future measurement record
quotes from this log; hand-transcription into prose is out of scope by design (prose
pinning is the review rubric's job, not a test's).

### 2.8 The classifier (check 1) — test-only, the frozen rule made executable

`classify(trials, bounds, controls) -> Arm` in `_continuity_rule.py`, implementing #159 §6
verbatim with the precedence order:

1. **UNDERPOWERED** — any axis missing its commissioned bound (a `None` in the bounds
   mapping); any measured axis absent (the single-instance-rig clause); any axis's trial
   range > 25% of that axis's own bound.
2. **FIRE** — `T_acq_min` controls asserted AND any axis breaching (strictly greater;
   equality passes) in ≥3 of 5 trials.
3. **KILL** — ≥2 device classes × ≥5 dispatches each (including ≥1 declared
   non-compositional, unsplittable class) where every dispatch admits T-tightening or
   splitting until all axes fit. `T_acq_min` dispatches are KILL-exempt by construction.
4. **INCONCLUSIVE** — everything else, including 2-of-5 and 1-of-5 breach series with
   tight spread and commissioned bounds.

Inputs are the trial ledger + a bounds mapping (`float | None` per axis) + declared
per-dispatch tightening/splitting outcomes and class labels. **The rig supplies the
classification INPUTS; the class labels and non-compositionality are device qualification
facts the fixture declares, never something the rig establishes** (finding F-C, §8). The
table test enumerates the (breach-count 0–5 × splittable × spread × bounds-present ×
controls) grid and asserts every cell yields exactly one arm; the 2-of-5/tight/bounds cell
must read INCONCLUSIVE (RED if it reads FIRE or KILL); a both-armed cell is unrepresentable
(single enum return — the test asserts totality and single-valuedness across the grid);
equality-at-bound is not a breach; `None` bounds read UNDERPOWERED. Each classifier clause
carries an inline citation to its §6 line so a record amendment visibly orphans the test.

## 3. Machine checks (1)–(7) — what lands now, honestly

| # | Frozen-rule check | Lands now (test-only) | Deferred with |
|---|---|---|---|
| 1 | Classifier table | Full grid test over `_continuity_rule.classify` (§2.8) — RED on the 2-of-5 cell and on any both-armed/non-total shape | — |
| 2 | Aged-reading representation + boundary table | **Boundary half:** direct `read_signal_values` table at `max_age_ms` = M with ages M−1 / M / M+1 (valid, valid, invalid — the inclusive pin), plus the documented-deficiency pin: an aged-in-bound `SignalValue` yields ZERO violations from a numeric/boolean condition (`evaluate_conditions` reads `age_ms` only in the product-skew path — pinned as today's truth with the reopen-flip stated inline) | **Representation half:** the `SignalValue` aged/stale visibility + trip-evaluator change is src/ work — row 1's own reopen scope, home = #159 §2 pin + the reopen train; the boundary pin going RED at that change IS the watched flip |
| 3 | Provenance | The trial-log emitter + its shape test (§2.7) | Quoting-into-prose discipline stays review-rubric territory |
| 4 | Store-connection census | Monkeypatch-count `Store.open` during trials: zero additional opens, one opening thread — the two-instance baseline the reopen must hold | The census AS a host build gate rides the reopen |
| 5 | Divergent wall clock | Injected stretched wall (monitor wall runs 10× the device/bundle wall): X2's host-age component scales ≥5×, X1's monotonic gap unchanged within the rig's ±50 ms band | — |
| 6 | Bit-identical TestClock fault-suite run | **Nothing lands** — the gate is defined only "under the host's wait primitive", which does not exist; a baseline captured against today's sync `wait_ns` is trivially identical to itself and proves nothing about the async suspension change | The gate stays pinned verbatim in #159 §4 (CTL-8) and the reopen's record; home = row-1 reopen |
| 7 | Non-capture arm fixtures | The buffered/unbuffered B-device pair (§2.3), both classes × both arms × ≥5 trials | — |

## 4. Minimal first increment and deferrals

The increment: the two files under `tests/integration/` plus this record (commit one on
`feat/issue172-continuity-instrument`). Nothing else moves. No fixture-lattice change is
required (the light harness authors its documents in tmp_path, the `MonitoredHarness`
pattern) — named here as a deliberate non-change because the obligation list makes lattice
touches expensive.

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| D1 | Aged-reading representation (src/ `SignalValue` + trip evaluator + skip-busy semantic) | #159 record §2 pin + row-1 reopen train | The #159 §6 FIRE arm firing, or its three original arms restated |
| D2 | Composed-path re-measurement (both arms through `_build_run_factory` / the real worker; the capture arm needs the corpus) | Follow-on note in this record; nearest carrier = the execution train | The capture family's promotion to the ACTIVE execution corpus (observable: corpus-manifest active execution version bump) — both arms then re-measure through the run path |
| D3 | Check 6 — bit-identical TestClock fault-suite gate | #159 §4 (CTL-8) + the reopen's design record | The native-async host build (D1's trigger) |
| D4 | The RED multiplexing control (disabled → X2–X4 return to dispatch-duration class; enabled → cadence class) | #159 §6 RED-control clause | The host existing (D1) |
| D5 | The decision evaluation itself — running `classify` against commissioned `G1/G2/P/TB` | #159 §6 + the #172 issue | First commissioned bench supplying the bounds (the #159 §3 row-2 completion trigger) |
| D6 | Classifier promotion out of `tests/` (e.g. a reporting surface) | Follow-on to this record, if ever wanted | An operator-facing row-1 report being commissioned |

## 5. Measurable proof and the pre-committed acceptance rule (instrument-level)

Written 2026-09-26, before any cross-instance axis number exists (the rig does not exist).
This rule ships or kills the INSTRUMENT; it never evaluates the frozen decision rule
(§0). Fixture scale: dispatch arm 200 ms, poll_ms 50, B frame period 20 ms, 5 trials per
arm × class, plus a matched short-dispatch control (5 trials, non-capture arm, buffered
class). Bands follow the existing rig's discipline (generous tolerances on ~50–300 ms
fixtures; CI-stable lanes that exist, no Windows lane).

- **SHIP iff all of:**
  1. Every (arm, class) produces 5/5 completed trials with all four axes recorded.
  2. **Separation** (the instrument's floor semantics — a control that passes both ways
     proves nothing): long-arm buffered X2 median ≥ dispatch − 50 ms AND control X2
     median ≤ 50 ms; X3 worst emission→landing ≥ dispatch − 50 ms in the long arm AND ≤
     3× poll_ms in the control; X4 onset→action ≥ dispatch − 50 ms long AND ≤ 1 s
     control (the verify-loop's `stable_for_ms` makes the control's absolute floor
     protection-shaped, so only the separation is asserted, not a tight control bound).
  3. X1 max tick gap within [dispatch − 50 ms, dispatch + 150 ms] on both arms (blackout
     reality; if this ever fails the serial model changed and the disclosure is stale —
     inherited verbatim).
  4. Classifier grid total + single-valued; 2-of-5 cell = INCONCLUSIVE; None bounds =
     UNDERPOWERED; equality passes.
  5. Census: zero additional `Store.open` during trials, one opening thread.
  6. Wall divergence: X2 host-age ≥ 5× baseline under the 10× wall; X1 within ±50 ms.
- **KILL the increment if:** separation fails (long ≈ control — the axes are vacuous; a
  wiring/fixture defect to fix before merge, the M-A posture: explicitly NOT row-1
  evidence); OR the census finds a second store-opening thread; OR wall divergence leaks
  into X1 (clock-domain contamination); OR any axis cannot produce 5 stable trials across
  3 consecutive runs (flaky fixture — fix the pacing, decide nothing).
- **UNDERPOWERED reading (instrument-level):** any axis's trial range > 25% of the
  DISPATCH DURATION (the rig's own scale denominator — chosen because no commissioned
  bound exists; explicitly NOT the §6 bound and never citable as one) → fix fixture
  pacing, decide nothing.
- **Kill directions on the measurement itself, pre-stated:** if the buffered class's X2
  does not separate from the control, the §8 host-driven-feed model is wrong for this
  tree (§2.3's disclosure fires — surface the spec reading, do not tune the fixture to
  force separation).

CI cost: one new integration module targeted < 60 s on the `gates` lane (≈20 trials ×
~0.5–1 s + table/census/boundary tests ≈ 2 s + the wall-divergence pair). The
sequential-model suite's 1.9 s sets the parity bar. The measurement tests join plain
pytest like their siblings — run-lane separation is NOT taken (no marker added); if CI
time bites, reducing trial count is refused in favor of marking the measurement tests
run-lane, because the trial count is the rule's sample size.

## 6. Invariant and drift impacts

No invariant changes (tests-only). Recorded for the reopen and for review:

- **CTL-8:** untouched — the fault suite is not touched by this increment, and the rig's
  axis trials are single-threaded on `SystemClock` (integration-tier timing tests in the
  existing rig's class). Check 6's gate (bit-identical TestClock runs under the host's
  wait primitive) stays pinned for the reopen (D3); CTL-8 is amended with evidence or
  preserved there, never silently flaked here.
- **A02/A09:** the fixture's `max_age_ms`/`poll_ms`/`T_acq_min` are rig parameters,
  never commissionings; the classifier's bounds are explicit inputs with `None` =
  UNDERPOWERED; `T_acq_min` authority stays with qualification evidence (§2.5).
- **A06:** the aged-reading honesty hazard is pinned, not fixed — check 2's
  documented-deficiency half records that an in-bound aged reading currently evaluates
  clean, with the reopen-flip stated.
- **REG-2/§8:** the structural pair (§2.6) re-uses the bridge's per-instance lock
  discipline read-only; nothing proposes concurrent in-flight calls on one instance.
- **Obligations (`docs/internal/drift-and-obligations.md`):** not triggered — no MCP/REST/
  CLI surface, no operator/device-developer guide change, no vendored byte, no fixture
  lattice, no SDK pointer. The `tests/` tree is the only code surface.

## 7. Top risks and what falsifies this design

| Risk | Falsifier |
|---|---|
| Fixture timing instability in CI makes trials flaky | The 3-consecutive-runs stability kill (§5); the band discipline is inherited from a suite that is green today (1.9 s, re-run this session) |
| The light harness measures a harness artifact, not the run path | Every axis seam is a production object (§1); D2's composed-path re-measurement is the falsifier when the corpus admits capture steps — a class disagreement there re-opens this record |
| The §8 host-driven-feed reading behind the buffered class is wrong | The buffered X2 fails separation (§5's pre-stated kill) or a spec reading shows fresh-conversion reads are mandatory — surface as the §8 loose thread with the #159 erratum path; the envelope axis stays implementable regardless |
| The x-extension emission stamp is rejected by bridge event validation | Self-verifying: the subscribe/poll path refuses or poisons on a non-schema event, so the rig fails loudly at first poll; the pattern is cited from the bridge's own `_X_KEY_PATTERN` |
| The classifier drifts from the frozen §6 text | Inline per-clause citations (§2.8) make an amendment visibly orphan the table test; review checks the mapping |
| X4's zero-point choice (hazard onset) is contested | The trial log records the full decomposition (onset/observation/action) — the axis can be re-cut from the same ledger without re-measuring; the owner may veto the pin before build |
| Scope creep into `src/` via the aged-reading representation | D1 names it with its home and trigger; check 2 ships only the boundary half |

## 8. Surface collision and loose threads

**This increment: proceed, no park.** Surfaces touched: `tests/integration/
test_cross_instance_continuity.py`, `tests/integration/_continuity_rule.py`,
`.claude/deep-review/2026-09-26-issue172-continuity-instrument-design.md`. The in-flight
#215 multi-version-serving stack (gateway PR #234 + SDK PR #58) holds standards/policy/
export — disjoint; merge-result pre-check at push covers it, no park needed.

- **(a) X4 zero-point** — defined here (onset→action, decomposition recorded), flagged
  for the owner; not a §6 edit (the rule names neither zero-point).
- **(b) The buffered-class model** (§2.3 disclosure) — if falsified, the finding posts to
  #159 per its own loose-threads convention; the rule text is untouched either way.
- **(c) KILL-arm class evidence** — the classifier consumes declared class labels and
  tightening/splitting outcomes; non-compositionality is qualification fact, rig-declared
  only (F-C). The KILL arm's evidence standard therefore lives with the bench, not the rig.
- **(d) One correction to the dispatch brief's framing:** the brief describes the
  mandatory non-capture arm as "at acquisition minimum" — kept, but note the arm's
  dispatch deadline must ACCOMMODATE `T_acq_min` (a completing slow read), while the
  capture arm's deadline CUTS at the budget (the deadline-max shape). The two arms
  intentionally differ in completion posture; both black out ticks for their natural
  in-flight duration, which is the exposure class being measured.

## 9. File inventory for the builder

1. `.claude/deep-review/2026-09-26-issue172-continuity-instrument-design.md` — this
   record; commit one on `feat/issue172-continuity-instrument`.
2. `tests/integration/_continuity_rule.py` — `TrialRecord`, `emit_trial_log`,
   `classify`, the `Arm` enum; per-clause §6 citations.
3. `tests/integration/test_cross_instance_continuity.py` — the two-instance harness
   (both arms, both device classes), the four axes with their seams, the §2.5/§2.6
   controls, the census, the wall-divergence pair, the check-2 boundary pins, the
   classifier table test, the provenance shape test, the trial loop (≥5 per cell).

Gates: `uv run ruff check .`, `uv run mypy` (bare), `uv run pytest
tests/integration/test_cross_instance_continuity.py` (+ the sibling suite re-run), counts
from `--junitxml` attributes — never an output-filter summary line. RED discipline: the
discriminative assertions each name their revert map (drop the monitor wrapper → priming
fails; disable `bounded()` → the natural-duration gap fails; break the classifier's
2-of-5 cell → the table test fails).
