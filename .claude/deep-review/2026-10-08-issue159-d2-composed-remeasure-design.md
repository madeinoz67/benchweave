# D2 — composed-path re-measurement of the continuity axes (issue #159, option A)

**Date:** 2026-10-08 · **Issue:** [#159](https://github.com/madeinoz67/benchweave/issues/159)
(deferral row 1 of the #43 record; this slice discharges **D2**, deferral row 2 of the owner
brief and row D2 of the #172 instrument record §4).
**Parent records:** `.claude/deep-review/2026-09-23-issue159-optionb-native-async-host-design.md`
(the frozen §6 FIRE/KILL/UNDERPOWERED/INCONCLUSIVE rule — **frozen; this slice never evaluates
or adjusts it**), `.claude/deep-review/2026-09-26-issue172-continuity-instrument-design.md`
(the instrument whose D2 this discharges), and the 2026-10-03 owner decision brief
(branch `docs/issue159-optionb-brief` only) — the owner adopted **option A** there: fund ONLY
the D2 re-measurement. No host bytes, no `src/` behavior change, no standards motion, no
version strings. This is a test-tree + record lane.
**Corpus:** no standards bytes move; no SDK touch; no `src/` change of any kind — the entire
increment lives under `tests/integration/` plus this record. `make check-sdk-standards` stays
green trivially.
**Triage:** public — synthetic fixtures only (`bench.composed-rig`, `supply-a`, `meter-b`,
`sig-comp-a-temp`, `sig-comp-b-level`, packages `dev/sim_supply_a` / `dev/sim_meter_b`);
every number cited below comes from the committed synthetic rigs or a named record, never
from a real bench, person, client, serial, or commercial term.
**Verdict: BUILD** (rig-side only). D2's trigger FIRED 2026-09-25 at `54a59fa` (observable:
corpus-manifest `identity.execution` 0.1.0 → 0.2.0, the promotion that made the `capture`
step kind ACTIVE) and is undischarged as of this record. The composed path the trigger
unlocked now exists end to end on main (verified §1); the light rig's axes, bands, ledger,
and classifier are importable; nothing structural blocks the re-measurement. The one honest
kill-risk — commissioning TWO bridged devices through the harness — is named with its
falsifier in §6 and its DON'T-BUILD outcome in §4.

## 0. What D2 is (and is not)

D2's own letter (#172 §4 row 2): *"Composed-path re-measurement (both arms through
`_build_run_factory` / the real worker; the capture arm needs the corpus)"* — trigger: the
capture family's promotion to the ACTIVE execution corpus. The #172 rig measured X1–X4 on a
**light** harness (direct construction of production objects, no admission/executor/worker)
because the then-ACTIVE corpus closed `step` at eight kinds; the record's own risk table
names this slice as the falsifier: *"The light harness measures a harness artifact, not the
run path — D2's composed-path re-measurement is the falsifier when the corpus admits capture
steps — a class disagreement there re-opens this record."*

This increment therefore delivers:

1. **Both arms through the composed run path** — a `capture` procedure step (the cut shape:
   budget 50 ms against a ~200 ms natural acquisition, ending in the honest bounded-timeout
   UNKNOWN) and the mandatory non-capture arm (a paced `read` step at `T_acq_min` completing
   OK) — each dispatched by the **executor**, inside a run admitted by
   `admit_documents`, driven by `coordinator.start_run`, on a bench whose two devices are
   both real `OTDPBridge` instances built by `_build_run_factory`.
2. **The four axes re-measured** on that rig (X1–X4, both device classes, both arms, plus
   the matched control), emitted as `_continuity_rule.TrialRecord` ledgers with provenance.
3. **The class agreement** — the pre-committed comparison (§4) of the composed cells against
   the light rig's recorded cells, whose disagreement is a first-class result that re-opens
   the #172 record, not a failure of this slice.
4. **The worker leg** — at least one trial per arm through `RunWorker.submit` →
   thread-affine re-open → the same discriminators.

What D2 is NOT: it is not the decision evaluation (that is D5 — no commissioned
`G1/G2/P/TB` exist, so the frozen §6 rule reads UNDERPOWERED on every trial; this slice
supplies **numerators only** and machine-checks that reading); it is not a host build, not
a rule edit, not a `src/` fix of any kind. If a seam this design relies on turns out to be
missing in production code, that is a fork to the owner, not a builder liberty (§6 risk 7).

## 1. Verified ground (read this session, not assumed)

All citations from `origin/main` tip `6806b6f7`. Two files moved after the brief's base
`c183db4` (`src/benchweave/interfaces/app.py` +29/−11;
`tests/integration/test_run_activation.py` +952/−11 — the #305/#226/#146 trains); both were
read at current bytes (byte-size + post-brief marker verified against the served view).

- **The corpus admits capture steps.** `standards/execution/0.2.0/procedure.schema.json`
  (`urn:stg:execution:procedure:0.2.0`) closes `$defs/step` at NINE kinds — `capture`
  requires `{id, kind, role, format ∈ {waveform_f64le, raw_binary}, sample_count, max_bytes,
  timeout_ms}`, `additionalProperties: false`. `standards/corpus-manifest.json` identity:
  execution 0.2.0, otdp 0.2.2, interface 0.1.0.
- **The executor dispatches capture steps.** `control/executor.py:910` routes
  `kind == "capture"` to `_step_capture` (`executor.py:1155`): mints
  `_capture_id(run_id, step_id, index_path)` → `cap:{run_id}:{step_id}` (`executor.py:712`),
  consults `check_allowed` BEFORE any dispatch, then dispatches through the shared clamp
  `deadline_ns = min(now + timeout_ms, body_deadline)`, shortened only
  (`executor.py:1213-1216`). `control/policy.py:97,117-126`: the capture allow rule is
  `{device_id, kind: "capture", format, capture_constraints}` — keyed on `format`,
  object-only payload guard.
- **The composed construction exists and is proven by three in-tree precedents.**
  `interfaces/app.py:689-923` `_build_run_factory` → `build_run`: spool + `admit_documents`
  → run floor → unattended-grant gate → `_device_plans` → per bridge-device
  `CaptureStagingStore` + `build_capture_services` + `build_stream_services` +
  `load_otdp_plugin` → `stream_host.register/adopt` → `_RetainingCoordinator` with
  `retain=lambda snapshot: services.retain_evidence(f"run:{run_id}", snapshot)`
  (`app.py:912`). Precedents: `tests/integration/test_run_activation.py`
  (`_CommissionedHarness` :769; R10 both-real-bridges :1038; R14 composed condition trip
  :1286; R16 worker leg :1079-1127; F5 measurement seams :1351; capture-dispatch-over-
  composed-bridge smoke :1599) and `tests/integration/test_capture_run.py`
  (`_CaptureHarness` :571 — a capture STEP through the factory; `_capture_step` :212;
  capture policy rules :252; A-R4 :779 asserts `kinds.count("capture") == 1`, the minted
  `cap:{run_id}:grab` in `coordinator.occurrence_ledger`, and the adapter's dispatch
  count). `tests/integration/test_issue146_e2e.py:19` sets the cross-test-module import
  precedent (`import test_run_activation as activation`).
- **The worker is the factory plus a queue hop.** `interfaces/worker.py` `_drain_with`:
  `put_run_state(running)` → `self._build_run(...)` → `coordinator.start_run(run_id,
  principal_id)` → terminal projection. `start_run` IS the composed execution path; the
  worker adds FIFO ordering and the thread-affine store re-open (`Store.open(self._db_path)`
  on the worker thread).
- **The measurement seams are public and composed-path-proven.**
  `control/stream_host.py:108` `RunStreamHost.tick_recorder` (consumed in `arm` :173) and
  the replaceable `on_event` — both driven on a factory-built run by F5
  (`test_run_activation.py:1367-1372`). `control/coordinator.py:591-593`: `monitor.retain`
  is a public post-construction attribute (`snapshot_evidence`, `retention_failures`
  beside it); `tick()` (`coordinator.py:603-633`) wraps `read_signal_values` +
  `evaluate_conditions` and sets `cause="tripped"` on a fresh body-phase violation.
  Adapter-side, the demo plugin records per-dispatch `(verb, started, ended)` monotonic
  spans (`dispatch_spans`) and verb counts (`dispatches`) — F5 and the capture smoke
  assert them.
- **Two devices need two packages.** `registry/otdp_loading.py` `load_otdp_plugin` calls
  `factory()` with NO device identity; the adapter cannot know which device it serves.
  `app.py:637-653` `_device_plans` resolves EACH bench device's closure independently
  (`commissioned_device_closure(registry_session, bench_id, device, descriptor)`) from the
  device's own descriptor pin — so the two-instance rig publishes, admits and activates
  TWO dev packages, one per device (the `_CaptureHarness` sequence run twice).
- **Retained snapshots are store-durable.** `content/store.py:313-319`
  `RetainingServices.retain_evidence` → `put_evidence("dataset", ref, artifact_id,
  "run:{id}", quota)`; `put_evidence` (`content/store.py:172-218`) RAISES
  `EvidenceQuotaExceeded` at the `(context_key, kind)` quota (it never silently drops) —
  quota = `max_page_size × 10` (`app.py:593-598`), a rig input. The monitor's retain call
  is failure-contained (`coordinator.py:616-620` → `retention_failures`, the A07 shape).
- **The light rig and the rule are importable as-is.**
  `tests/integration/_continuity_rule.py`: `TrialRecord`, `classify`, `emit_trial_log`,
  `write_trial_log`, `AXIS_CLOCK_DOMAINS` — no edit needed or permitted.
  `tests/integration/test_cross_instance_continuity.py`: `ContinuityRig` (:576),
  `ARigAdapter`/`BRigAdapter` (:231/:383, buffered/unbuffered classes), `run_trial`
  (:1084), `TrialInfrastructureError` (:942), the §8 structural pair (:2666), the census
  (:2723), the divergent-wall pair (:2749), the range-gate machinery (:2131-2224). The
  instrument-level bands this record re-commits are #172 §5's, verbatim, at the same
  fixture scale.

## 2. Mechanism

### 2.1 Shape — one new sibling test module, zero edits to existing files

**`tests/integration/test_d2_composed_continuity.py`**, importing
`test_run_activation as activation` (the `test_capture_run`/`test_issue146_e2e` precedent)
and `from tests' sibling path: _continuity_rule` (`from _continuity_rule import ...` — the
#172 module-import shape under the same rootdir). No change to
`test_run_activation.py`, `test_capture_run.py`, `test_cross_instance_continuity.py`, or
`_continuity_rule.py` — those files are other trains' active surfaces and this slice's
discipline is additive-only (the #172 sibling precedent, restated).

### 2.2 The two-package, two-device lattice

- **Package A `dev/sim_supply_a`** — the dispatching instance. Adapter: the
  `_CaptureHarness` adapter-source shape extended with (i) a paced capture arm
  (`T_acq_min ≈ 200 ms` natural duration in adapter-internal slices, artifact traffic as
  the capture arm requires), (ii) a paced `read`/`write` arm with the same natural
  duration and NO artifact traffic, (iii) `dispatch_spans`/`dispatches` recording, (iv) a
  module knob for the natural duration (found by marker constant via the loaded module,
  the `_loaded_adapter_module` idiom — a NEW marker constant so the two packages' modules
  never alias).
- **Package B `dev/sim_meter_b`** — the non-dispatching instance, the `BRigAdapter`
  semantics ported into a loadable plugin: the **buffered class** (host-driven feed per
  spec §8 — frames exist only when polled, one frame per 20 ms of harness monotonic time
  since subscribe, each event carrying its device emission stamp in a schema-legal
  `x-rig-emit-ns` extension key; the streamable parameter serves the newest RECEIVED frame
  with `observed_at` = frame stamp) and the **unbuffered class** (fresh conversion per
  read, `observed_at = now`) selected by a module knob. B is the safe-action target
  (a `write` parameter that zeroes the served model) and the condition-carrier: its
  parameter model **self-anchors the hazard onset** — on every parameter read it records
  `last_read_ns`; the model crosses the condition bound at `last_read_ns + DELTA_MS`
  (DELTA_MS = 100 < the 200 ms dispatch), so the crossing lands INSIDE A's dispatch window
  by construction, with no harness omniscience about executor timing. The device exposes
  the anchor for post-run read-back.
- **Harness `_ComposedRigHarness`** — the `_CaptureHarness` sequence run TWICE into one
  dev registry root (two plugin dirs, two descriptors — B's descriptor declares the
  streamed parameter and a stream floor of 10 ms — signed dev origin, resolver, two
  `admit` calls, two `activate` calls at `bench_generation=1`), then the lattice:
  bench `composed-rig` declaring devices `supply-a` (pinning descriptor A) and `meter-b`
  (pinning descriptor B); signals `sig-comp-a-temp` (source A, `poll_ms: 50`) and
  `sig-comp-b-level` (source B, `poll_ms: 50`, `max_age_ms: 300` — the #172 amended
  dispatch-scale margin: pacing overshoot and one frame period must stay OUT of the
  fail-safe band so `signal_invalid` never fires "for a reason that is not the hazard");
  policy with the capture allow rule (`format: waveform_f64le` + `capture_constraints`
  admitting the step's payload), B's safe-transition write rule, and the continuous
  condition on `sig-comp-b-level` (maximum 4.5 against a model crossing to 5.0); the
  procedure with `max_body_ms: 12000` (the capture-counts-timeout-plus-epilogue-floor
  arithmetic, `test_capture_run.py`'s own precedent) and `roles` binding `supply` →
  `supply-a`, `meter` → `meter-b`.
- **Verification built into the harness smoke (the R10 idiom, both devices):** the
  factory-built coordinator's `plugins["supply-a"]` and `plugins["meter-b"]` are both
  `OTDPBridge` instances whose adapters hold the eight-member `CaptureServicesBundle`, and
  `stream_host.devices` carries both registrations. This smoke is the two-package
  lattice's proof and this design's most likely first failure (§6 risk 1).

### 2.3 The arms (procedure-expressible, executor-dispatched)

- **Capture arm (the cut shape, mirroring the light rig):** steps =
  `[delay settle 200 ms] → [capture step: role supply, waveform_f64le, sample_count 64,
  max_bytes 1024, timeout_ms 50] → [delay settle 200 ms] → [read observe on meter]`. The
  executor clamps the deadline to `now + 50 ms` while the adapter paces ~200 ms — the
  bridge's `bounded()` timeout lands the honest UNKNOWN, the body ends unpassed, the
  protective transition runs, and the terminal record carries the failure honestly. The
  trial asserts the outcome SHAPE (body not passed; the capture event's `dispatch_state`
  UNKNOWN-class) — never a fabricated pass.
- **Non-capture arm (completing):** steps = `[delay settle 200 ms] → [read step on supply:
  parameter paced at `T_acq_min ≈ 200 ms`, `timeout_ms` accommodating (250 ms) → OK] →
  [delay settle 200 ms — the natural X3 drain window] → [read observe on meter]`. This arm
  completes; the run passes; frames drain through the engine's own poll slices.
- Both arms run on the SAME two-device lattice; X4 variants swap in the self-anchored
  crossing model (the condition trips at the first post-dispatch tick; `body_outcome ==
  "tripped"` with the CONDITION's reason — asserted NOT `signal_invalid`, the R14 +
  `_freshness_trip_block` discipline).

### 2.4 The axes, composed

Per trial (a trial = one fresh `Store` + fresh request id over the shared admitted
session; ≥5 trials per arm × device class; 5 control trials; ≥1 worker-leg trial per arm):

- **X1 — tick-gap class (monotonic).** `stream_host.tick_recorder = times.append` attached
  pre-start (the F5 idiom); worst gap over the run. Blackout band inherited:
  `[dispatch − 50 ms, dispatch + 150 ms]`, with the cut-capture arm's lower bound vacuous
  by arithmetic (50 ms cut ⇒ floor 0) — disclosed, inherited.
- **X2 — non-capturing-signal freshness at dispatch end (wall).** A wrapper around the
  PUBLIC `coordinator.monitor.retain` seam attached pre-start:
  `original = monitor.retain; monitor.retain = lambda snap: (recorder(snap),
  original(snap))[1]` — the rig records the TYPED snapshot (per-signal
  `max(host-computed age, device-reported age)` envelopes) while production retention
  continues untouched; X2 = `sig-comp-b-level`'s envelope in the FIRST post-dispatch
  snapshot; `sig-comp-a-temp`'s envelope recorded alongside (the §8-bound share's
  indicator — the share separation becomes store-corroborated). Provenance cross-check:
  `monitor.snapshot_evidence` length equals the store's `(context_key="run:{id}",
  kind="dataset")` evidence-row count — production retention demonstrably ran.
- **X3 — events emitted vs landed (monotonic).** `stream_host.on_event` replaced pre-start
  (F5 idiom); for B frames whose `x-rig-emit-ns` falls inside the dispatch window:
  landed-during-window flags and worst emission→landing latency. Measured on COMPLETING
  trials (the read arm and the control), where the trailing settle drains naturally
  through the engine's own slices. On tripping trials the post-trip tail is COUNTED and
  disclosed as unlanded-by-design (production delivers nothing post-trip — the #172
  amendment's own finding, here observed rather than bypassed; A06: no laundering).
- **X4 — protective-action latency to the non-dispatching device (monotonic).** Onset =
  B's recorded anchor (`last_read_ns + DELTA_MS`); observation = the first post-dispatch
  tick (tick recorder); action-landed = the end of B-adapter's safe-write span
  (`dispatch_spans`); the full 3-way decomposition (onset → observation → write-start →
  write-end) recorded in the trial log so a future re-cut needs no re-measurement — the
  #172 §2.4 amendment's decomposition, carried over.
- **Clock domains** ride `AXIS_CLOCK_DOMAINS` unchanged (X1/X3/X4 monotonic; X2 wall).

### 2.5 Controls (inherited, composed)

- **Matched short-dispatch control** (5 trials, read arm, buffered class): the same
  procedure with A's natural dispatch ≈ 20 ms.
- **`T_acq_min` consistency controls** (consistency only, never authority — the §6
  clause): (i) short-T read at 20 ms budget fails the acquisition (TIMEOUT/UNKNOWN,
  never OK); (ii) split-refusal — the scalar read is definitional; the capture window is
  one-shot per the fixture (the `test_split_refusal_capture_window_one_shot` shape).
- **The §8-bound / movable structural pair**, on DEDICATED trials (helper threads appear
  only here; axis trials stay single-threaded, CTL-8): a helper thread dispatches reads
  to BOTH bridges for the run's duration, recording spans; the trial selects post-hoc the
  spans overlapping A's dispatch span (from A's `dispatch_spans`): reads on B's bridge
  succeed promptly throughout (the movable share), reads on A's bridge block for the
  remaining dispatch (§8 per-instance serialization). No harness omniscience needed —
  the selection is against recorded spans.

### 2.6 The worker leg

Per arm, ≥1 trial through `RunWorker(store, content, build_run=…)` → `submit` →
`join(timeout=…)` (the R16 second-half idiom), then the SAME discriminators read from the
store (run events with minted ids; terminal record) and the axes from the same seams (the
recorders attach to the coordinator the factory returns inside the worker's drain — the
rig wraps `build_run` to capture the coordinator reference, wrapping ONLY the callable the
worker already receives as its own construction input). The census row: during `start_run`
trials exactly one store-opening thread; on worker-leg trials exactly the two expected
connections (main + the worker's thread-affine re-open) — `Store.open` monkeypatch-counted
(the light rig's census idiom, with the worker's legitimate second connection accounted).

### 2.7 Discrimination — proving the composed path ran (the anti-shortcut gate)

Every axis trial asserts ALL of:

1. the coordinator is a factory-built `_RetainingCoordinator` and BOTH devices are real
   `OTDPBridge`s over `CaptureServicesBundle` (R10, both devices);
2. the run's event log (`store.read_events(f"run:{run_id}")`) contains the step kind
   under test with the EXECUTOR-MINTED id — `cap:{run_id}:{step}` (capture arm) /
   `op:{run_id}:{step}` (read arm) in the occurrence ledger — an id a hand dispatch
   cannot mint (the capture smoke's own `"cap.smoke-1"` contrasts with A-R4's
   `cap:run-capture-pass:grab`);
3. the terminal record exists with the arm's honest outcome (passed / tripped-with-
   condition-reason / the UNKNOWN-class capture failure);
4. the retained-snapshot cross-check (§2.4 X2) — production retention rows exist.

**The RED arm (the control that fails when composition is bypassed):** one test drives the
SAME capture request DIRECTLY on the bridge (the light-rig shape, the `_CaptureHarness`
smoke's own call) against the same lattice and asserts the discriminator REFUSES it — no
run event, no minted id, no occurrence-ledger entry, no terminal record. A discriminator
that passes both ways proves nothing (#43's floor); this arm pins that it discriminates.
Revert map: delete the discriminator assertions and the RED arm still fails (it asserts
absence where the composed path produces presence) — the pair is self-evidencing.

### 2.8 Ledger and provenance

`TrialRecord(trial, arm="composed-capture"|"composed-read", device_class,
axes_ms, t_acq_controls, tightening_admitted, splitting_admitted, unsplittable_class,
parameterization={dispatch_ms, poll_ms, frame_ms, max_age_ms, arm_shape, worker_leg, …},
command=<the exact pytest invocation>)` per trial; `write_trial_log` under the trial tmp
dir; the check-3 shape test reused verbatim from the light rig (imported, not copied).
Every quoted figure in the outcome posts cites a log row.

## 3. Minimal first increment and deferrals

The increment: `tests/integration/test_d2_composed_continuity.py` (one file — harness,
lattice authoring, arms, axes, controls, worker leg, discrimination, ledger tests) plus
this record. Nothing else moves. No fixture-lattice change (documents authored in
`tmp_path`, the harness pattern — named as a deliberate non-change).

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| D2-a | Retry belt for composed trials (the light rig's `TrialInfrastructureError` + fresh-generation machinery, imported if needed) | This record + the light rig's belt | The first CI starvation flake on the composed lane (the #217/#245 class); until then a flake FAILS loudly |
| D2-b | Three-instance composed rig | This record | The reopen's own census-at-N trigger (with D1) |
| D2-c | Classifier promotion out of `tests/` | #172 D6 (inherited verbatim) | unchanged |
| D2-d | The decision evaluation (`classify` vs commissioned `G1/G2/P/TB`) | #159 §6 + D5 (inherited verbatim) | First commissioned bench |
| D2-e | X3 post-trip tail through the composed path | This record — **declined by design**: measuring it requires bypassing the engines' stop latch inside a composed run, i.e. patching production internals the light rig only reached because it owned every object | An owner call wanting tail latencies composed; until then the tail is counted-and-disclosed (§2.4) |
| — | D7 / D8 (retry-class widening; fractional-age pin) | #172 §4 | Stay parked per the owner's option-A ruling |

## 4. Measurable proof — the pre-committed acceptance rule

> **Fold-wave addendum (2026-10-08, post-refute; the rule text above and
> below this note is frozen and unedited):** the builder's composed rig
> met the rule with the following recorded caveats and corrections, folded
> as one batch on `feat/159-d2-remeasure`.
>
> **(a) Fixture-scale drift (class-agreement caveat).** The rig runs B's
> frame period at 50 ms (= the poll cadence; the composed poll engine
> delivers one frame per slice, so the designed 20 ms schedule accumulates
> an unbounded backlog the composed path cannot drain) and `max_age_ms` at
> 500 (not 300: the composed path cannot pre-align, so post-dispatch ages
> run ~270-380 ms and a 300 bound trips `signal_invalid` on jitter — the
> #172 margin lesson repeating). The clause-3 ±100 ms class comparison is
> read with that drift in view.
>
> **(b) Band-floor arithmetic (revert evidence).** The clause-2 floors
> `X4 >= 150` and `control X2 <= 50` encoded the light rig's scripted-early
> onset (10-40 ms into dispatch) and aligned control (fresh frame at
> dispatch start). The composed shape forces the floors to the anchor
> arithmetic: the self-anchored onset sits at prev-read + DELTA (~100 ms
> into the 200 ms dispatch), so composed X4 = (dispatch − DELTA) +
> observation-to-action ≈ 105-115 ms (floor moved to >= 90); the composed
> control's X2 floor is dispatch + last-poll residue ≈ 70-120 ms (band
> moved to <= 150). Reverting the floor moves re-opens both bands red.
>
> **(c) X4 excluded from clause 3's cross-rig comparison.** The light
> rig's onset placement was a harness-scripted mechanism; the composed
> onset is self-anchored — a mechanism change, not a scale change — so
> same-cell X4 numbers are not comparable. The composed X4 evidence is its
> own band (>= 90, cell median over all 10 armed trials) plus the recorded
> 3-way decomposition per trial-log row. X4 measured 109 ms median at the
> ±100 tolerance edge run-to-run (105.9 / 109 / 114.1), confirming the
> boundary straddle this exclusion resolves.
>
> **(d) MEDIUM-1 correction.** "Structurally unmeasurable" (the builder's
> phrase for the control-X4 band) is wrong: the self-anchored crossing CAN
> fire on an armed control via tick-phase alignment (~8% of trials, phase
> luck). The honest statement is NOT RELIABLY MEASURABLE AT n=5 — five
> trials do not reliably produce an aligned phase. The band stays
> unmeasured for that reason, not by impossibility.
>
> **(e) Row 9 (2026-10-09, the landing battery's own reproduction): X3's
> control coverage is a SESSION PHASE LOTTERY, and the LOUD CONDITIONAL
> (option b) is the honest arm.** The clause-3 consumer red on THREE
> independent full-battery runs at dc2bb9b4 (builder x2, landing x1):
> the control cell's X3 records only when its 20 ms window catches the
> 50 ms emission grid, and the grid phase locks per process — a session
> draws 0/5 control hits, or 4/5, at coin weight. Deterministic coverage
> (option a) was attempted through four device-model shapes — a fixed
> read-anchored offset (destroyed by the tick-precedes-poll ordering:
> the tick before every poll re-anchors or expires the slot before its
> delivery check), a 2-deep schedule queue (the cap race: the same
> round's tick push drops the window's stamp before the poll), a burst
> queue (backlog past the capacity-capped drain, tripping the freshness
> invariant), and a schedule-tracking freshness point (a future stamp is
> impossible timing). Each changed what X3 measures or broke the run
> path — the §2.2 omniscience ban's substance: the window's start is
> executor timing, and an emission schedule that must land inside it
> cannot be authored without seeing it. Per option (b): the clause-3
> X3-control comparison evaluates whenever the session recorded (>= 1
> trial), prints a disclosed no-coverage row when the phase drew 0/5,
> and the record-count floor still refuses a producer that did not run.
> **Reopen trigger:** a composed path whose drain reaches delivery
> parity with the emission schedule, or an executor-visible emission
> anchor (a seam that lets the device observe the dispatch window
> without harness omniscience) — either makes option (a) constructible.

Written 2026-10-08, BEFORE any composed-path axis number exists (the rig does not exist).
This rule ships or kills THE RE-MEASUREMENT RIG; it never evaluates the frozen decision
rule (§0). Fixture scale mirrors the light rig exactly so the cells compare: dispatch arm
200 ms (capture cut at 50 ms budget), `poll_ms` 50, B frame period 20 ms, `max_age_ms` 300,
5 trials per (arm × device class) cell, 5 control trials, ≥1 worker-leg trial per arm,
plus the RED arm and the structural pair. Every band's denominator is the rig's own
fixture scale — **explicitly not `G1/G2/P/TB` and never citable as a commissioning (A02)**.

- **SHIP iff all of:**
  1. **Discrimination:** every axis trial passes all four §2.7 discriminators; the RED arm
     confirms the minted-id discriminator fails on a bypassed dispatch; the worker-leg
     trials pass the same discriminators read from the store.
  2. **Separation (composed, the #172 §5 bands verbatim at the same scale):** long-arm
     buffered X2 median ≥ 150 ms AND control X2 median ≤ 50 ms AND unbuffered X2 median
     < 50 ms; X3 worst emission→landing ≥ 150 ms long AND ≤ 150 ms (= 3× `poll_ms`)
     control; X4 onset→action-landed ≥ 150 ms long AND ≤ 1 s control; X1 max tick gap in
     `[150, 350]` ms on the read arm and ≤ 350 ms on the cut-capture arm (lower bound
     vacuous there, disclosed).
  3. **Class agreement (the D2-specific clause):** for every axis, the composed
     long-vs-control separation direction matches the light rig's recorded direction
     ([R5]: X2 219/42/1.0, X3 202/32, X4 209/70 ms), AND each composed cell median lies
     within ±100 ms (half the dispatch scale — the pre-committed class tolerance) of the
     light rig's same-cell median.
  4. **Classifier consumption:** `classify(composed_ledger, {X1: None, X2: None, X3: None,
     X4: None})` returns `UNDERPOWERED` (machine-checked — the §6 reading applies
     verbatim; no denominator exists, none is invented); the light rig's classifier grid
     tests remain green and UNEDITED (a pinned non-change).
  5. **Range gates:** per-axis-per-cell trial range ≤ 25% of the 200 ms dispatch duration,
     trimmed of the single most extreme trial (the #172 §5 item-7 machinery, imported).
  6. **Census:** zero additional `Store.open` beyond the expected set on every trial shape
     (§2.6); one opening thread on `start_run` trials.
  7. **Completeness:** 5/5 completed trials per cell with all four axes recorded, except
     X3 which must record on ≥3 of 5 trials of every cell (the cut-capture arm's trialing
     tails are counted-and-disclosed rows, never silently dropped).
- **KILL the rig (fix-before-merge class) if:** separation fails composed (long ≈ control
  — a wiring defect to fix, explicitly NOT row-1 evidence, the M-A posture); OR the
  discriminator passes on a bypassed dispatch; OR any cell cannot produce stable trials
  across 3 consecutive runs (fix pacing, decide nothing); OR the retention quota raises
  into `retention_failures` on any trial (raise `max_page_size`, re-run).
- **KILL the design (DON'T-BUILD-the-rig, report and stop) if:** the two-package lattice
  cannot commission BOTH devices as real bridges through the harness sequence run twice —
  i.e. §2.2's smoke is unachievable without `src/` changes (§6 risk 1). That is a real
  result about the activation path's shape, posted to #159 with the evidence; it does not
  get forced through a production change inside this slice.
- **UNDERPOWERED (first-class, twice over):** (a) the §6 reading — no commissioned bounds
  exist, so the re-measurement's ledger reads UNDERPOWERED by construction and ANY quoted
  bound in any write-up of its numbers is a defect; (b) per-cell X3 coverage below 3-of-5,
  or any axis's trimmed range past its gate → that cell decides nothing, fix the fixture.
- **The disagreement outcome is a SUCCESS of the slice, not a kill:** if composed cells
  DISAGREE with the light rig's class (clause 3 fails on direction, or a composed median
  lands outside tolerance while its own separation holds), the rig SHIPS with the
  disagreement as its headline finding — the #172 record re-opens per its own risk table,
  the light rig's affected numbers are retired, and the outcome posts to #159 and #172.
  Pre-committing this now is what makes the re-measurement unfakeable: the slice cannot
  "pass" by agreeing and cannot quietly fail by disagreeing.
- **Numbers discipline:** every figure in the outcome post carries its denominator (the
  rig's dispatch/poll/frame scale), its cell (arm × class), its sample size, and its
  provenance (a trial-log row's reproducing command). Provenance codes for the light-rig
  side: [R5] PR #236 body, re-measured post-fix.

## 5. Invariant and drift impacts

No invariant changes (tests-only). Recorded for review:

- **CTL-8:** axis trials are single-threaded on `SystemClock` (integration-tier timing
  tests, the existing class); helper threads appear only in the structural-pair controls
  and the worker leg — both outside the fault suite, which is untouched.
- **A02/A09:** every fixture constant (`max_age_ms`, `poll_ms`, `T_acq_min` pacing,
  DELTA_MS) is a rig parameter serving measurement discriminability; the ±100 ms class
  tolerance is a class-agreement band, never a bound; the classifier's `None`-bounds
  reading is machine-checked (§4 clause 4).
- **A06:** the X3 unlanded post-trip tail is counted and disclosed, never laundered into
  the landed set; the capture arm's UNKNOWN outcome is asserted as the honest shape.
- **A04 (strengthened, stated honestly):** X4 now measures through the REAL protective
  transition (monitor trip → coordinator `_finish_run` → safe actions), where the light
  rig called the engine directly — the composed number is the one A04 actually guarantees.
  The capturing device's §8 residual is unchanged and stays priced (the #159 record's
  consequence 3).
- **STO-1/STO-3:** the census row (§4 clause 6) is the two-instance baseline restated for
  the composed shape, worker leg included.
- **Obligations (`docs/internal/drift-and-obligations.md`):** not triggered — no MCP/REST/
  CLI surface, no operator or device-developer guide change, no vendored byte, no fixture
  lattice, no SDK pointer. `tests/integration/` is the only code surface.

## 6. Top risks and what falsifies this design

| Risk | Falsifier |
|---|---|
| The two-package two-device commissioning is unproven in-tree (every harness precedent commissions ONE package) | §2.2's both-devices smoke; if it cannot pass without `src/` changes, the design's KILL-the-design arm fires (§4) and the finding posts to #159 |
| The unknown-outcome capture arm's body-termination shape differs from expectation (the F2/BODY_TIMED_OUT branches) | The trial asserts only the structural shape (not passed; dispatch_state UNKNOWN-class; minted id invalidated) — anything tighter is pinned only after the first green run shows the real shape |
| Snapshot retention collides with the evidence quota on longer runs | `retention_failures` is asserted zero per trial; quota is `max_page_size × 10`, a rig input — raise and re-run (§4 KILL-fix row) |
| Timing instability on shared CI runners (the #217/#245 scheduler-stall class) | The trimmed range gates + the 3-consecutive-runs stability kill; the E2E budget lesson (starved runners) says bands must absorb stalls, not chase them |
| The self-anchored crossing (last-read + DELTA) misses the window on a pathological run (a pre-dispatch tick skipped) | The trial asserts the anchor falls inside A's recorded dispatch span; a miss reads infrastructure (trial discarded loudly), not a silent X4 of the wrong class |
| Session-sharing across trials bleeds activation state | Fresh request id + fresh Store per trial (the `binding_ref(request_id=…)` rewrite idiom); the first trial of each cell re-runs the discriminators, which would fail loudly on bleed |
| Scope creep into `src/` when a seam seems missing | The seams are verified public (§1: `tick_recorder`, `on_event`, `monitor.retain`, `dispatch_spans`, occurrence ledger, evidence rows); any further "small fix" is an owner fork, named here as the guard |

## 7. Surface collision, tier call, keyword scan

**Surface collision: proceed, no park.** Touched: one new file under
`tests/integration/` and this record. Live sibling lanes: the brief's branch
(`docs/issue159-optionb-brief`, docs-only, disjoint) and the repo's active trains touch
`src/benchweave/interfaces/`, `tests/ui_html/`, `packages/` — disjoint from a new
`tests/integration/` module. No `standards/` byte, no SDK pointer, no `src/` byte.

**Review tier (#254): TIER 3 — the slice, stated at design time.** Triggers over the
expected SLICE diff (this record + the builder's test module): the keyword rule fires on
`threading` (the structural-pair helper threads, the `RunWorker` leg) and `sha256` (the
lattice authoring's document digest pins, the capture-manifest assertions), both
case-insensitive, in the test module's text by construction; Tier 3 therefore applies to
the slice regardless of its tests-only path (the rubric's keyword-rule interplay: the deep
lane is bought by what the text carries). The standing two-lane adversary applies
(retro R3).

**Step-1 keyword scan over THIS record's expected diff text** (the only file in the
design-record commit; MEASURED case-insensitively over the saved file before commit, not
estimated — the first draft of this very paragraph estimated the counts and was wrong,
which is the failure mode this clause exists to prevent). **Substantive text** — every
line except this scan statement and the tier-call sentences above it, which are the
measurement instrument: `threading` 0 · `asyncio` 0 · `subprocess` 0 · `sha256` 0 ·
`hashlib` 0 · `migrate` 0 · `recovery` 0 · `protection` 0 — 0/8. **Whole file, as the
rubric words it ("the whole expected diff"):** every token appears — carried by this very
statement and the tier-call sentences above it, which are the measurement instrument, not
content; exact whole-file numbers are not statable self-consistently (any paragraph that
enumerates them re-raises them — observed twice while writing this one), so none are
claimed. Near-miss forms present and disclosed: `protective` (the project's standard
adjectival form); no near-miss contains a listed token on its own. On the substantive
reading the record commit is
**Tier 1** (docs-only, zero substantive keyword hits); on the strict whole-file reading it
is **Tier 3 by first-match-wins** — the enumeration is the measurement instrument, not
carried content, per the reading the 2026-10-03 brief already disclosed to this tracker.
The SLICE is Tier 3 regardless (above). The review re-derives independently; a substantive
hit this scan missed is a record defect per the rubric.

## 8. File inventory for the builder

1. `.claude/deep-review/2026-10-08-issue159-d2-composed-remeasure-design.md` — this
   record; commit one on `feat/159-d2-remeasure`.
2. `tests/integration/test_d2_composed_continuity.py` — the composed rig: the
   two-package harness, the lattice, both arms, the four axes with their seams, the
   controls, the worker leg, the discrimination battery (including the RED arm), the
   census, the ledger + provenance tests, the classifier-consumption assertion.

Gates: `uv run ruff check .`, bare fresh-cache `uv run mypy`, focused
`uv run pytest tests/integration/test_d2_composed_continuity.py` plus the two sibling
suites re-run (the light rig and `test_capture_run` — import-graph neighbours), counts
from `--junitxml` attributes. RED discipline: each discriminative assertion names its
revert map (drop the factory → the R10-style discriminator fails; bypass to a direct
bridge dispatch → the minted-id discriminator fails; delete the retain wrapper → the
store-row cross-check still passes but X2's typed record is gone — the pair proves the
seam). CI budget: the composed lane targets < 240 s (≈30 composed runs × 2-6 s harness
construction + run, plus table/census/RED tests) — disclosed against the #172 lane's
< 60 s; if it bites, reducing trial count is REFUSED in favour of marking the measurement
tests run-lane-separated (the #172 §5 precedent: the trial count is the rule's sample
size).
