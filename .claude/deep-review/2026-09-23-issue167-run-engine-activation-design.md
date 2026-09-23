# Run-engine capture & streaming activation design (issue #167, row 9 of the #43 record)

**Date:** 2026-09-23 · **Issue:** [#167](https://github.com/madeinoz67/benchweave/issues/167)
**Parent record:** `.claude/deep-review/2026-09-21-issue43-capture-streaming-design.md` (through
Amendment 3 + the 2026-09-22 slice-2 errata). This is deferral row 9: the activation wiring that
turns the shipped capture/streaming capability into something a run actually drives.
**Corpus:** no standards byte moves in either repository — verified against the scope below;
`make check-sdk-standards` stays green trivially. **No SDK byte is expected or touched**: the
design composes gateway-side surfaces only (`src/benchweave/interfaces/app.py`,
`control/coordinator.py`, tests, two guides); the SDK protocol, the standalone capture writer and
the vendored trees are untouched.
**Verdict:** BUILD, minimally — construction wiring + streaming activation + containment + the two
fold-ins (#159 arm-3 evaluation, TIMEOUT-on-cut disposition). The capture *procedure-step shape*
is corpus-gated and is designed here, deferred to its train (Decision 6 — the one fork the
maintainer owns).

## 0. Grounding — checked against code, not the issue prose

What slices 1–2 actually left in the tree (the seams this increment wires):

- `build_run` in `src/benchweave/interfaces/app.py:327` (factory `_build_run_factory:324`) is the
  activation point: it already constructs the whole coordinator stack on the worker thread —
  `ContentStore(worker_store)`, admitted documents, `RetainingServices`, sim plugins from the
  hardcoded `_SIM_PLUGINS` tuple (`app.py:54`), `_RetainingCoordinator`. **No production path
  constructs a bridge**: `load_otdp_plugin` (`registry/otdp_loading.py:170`) has zero callers
  outside tests. `RunWorker._drain_with` (`interfaces/worker.py:179`) is the only caller of
  `build_run`; the worker re-opens the store on its own thread (sqlite thread-affinity,
  `worker.py:7–16`), so everything the bridges touch must be constructed inside `build_run` —
  the seam already enforces what the issue asks ("over the worker-thread store").
- The composition factories exist and are permission-gated at construction:
  `build_capture_services` (`content/capture_services.py`, end of file) returns the eight-member
  bundle + `CaptureController` or the five-member shape with no controller;
  `build_stream_services` (`content/stream_services.py:406`) returns a `StreamController` or
  `None` without `event_sink`. Both re-derive the RAW descriptor by pinned digest (CON-10 drops
  `integration`) — the bench document's per-device descriptor pins (resolved in
  `_spool_documents`, `app.py:109`) are the digests they need.
- The sharing seams exist but are unwired: `RetainingServices.__init__` takes
  `reading_sinks=None` and defaults to a fresh instance (`content/store.py:225`);
  `StreamController.__init__` takes `reading_sinks=None` and delivers after batch commit.
  Today nothing constructs both, so "one shared `ReadingSinks` across run services +
  StreamController" is unrepresentable in production — the two would be separate instances even
  if both were built (`app.py`'s `RetainingServices` call passes no sinks).
- The poll engine exists with three named row-9 residuals in its own docstring
  (`control/stream_polling.py:20–46`): the `on_event` escape (containment rests on "the
  run-engine exit path that owns the callback"), the `poll_slice_ns` vs `bench_poll_ns` binding
  ("binds at the run-engine wiring, not here"), and timebase identity (M2: the engine slices on
  a `MonotonicClock` in ns while the bridge cuts on `services.monotonic()` in s — "the binding
  is the run-engine wiring's").
- `bench_poll_ns` (`control/protection.py:52`) is the one derivation of the commissioned poll
  cadence — the minimum declared signal `poll_ms` over the bench's signals, defaulting to 10 ms,
  floored at 1 ms — already consumed by the monitor's tick budget and the coordinator's sliced
  waits (`coordinator.py:633`). The bench fixture's signals (`fixtures/execution/bench.json`)
  declare `poll_ms: 50` with `source: {kind: "parameter", device_id, parameter}` — the
  commissioned per-device observation declarations, the same set `read_signal_values`
  (`protection.py:109`) iterates per tick.
- **Zero production `QuotaLimits` construction sites** — every `QuotaLimits(` in the tree is a
  test. The activation wiring adds the first production one, which makes the A02 commissioning
  question live (Decision 1).
- The fixture descriptors are adapter-mode (`fixtures/execution/descriptor-sim-psu.json`:
  `integration.mode = "adapter"`, `entry_point = "benchweave_sim_psu.plugin:create_plugin"`,
  permissions `["scoped_transport"]` only) and the fixture registry ships them as admitted
  packages (`fixtures/registry/origin-main/benchweave/sim-psu/1.0.0/payload.zip`) — so the demo
  bench's devices are bridge-constructable today without moving a fixture byte (they construct
  WITHOUT capture/stream controllers: no `artifact_writer`, no `event_sink`).
- **The corpus fact that shapes everything:** `standards/execution/0.1.0/procedure.schema.json`
  closes `step` at exactly eight kinds (`invoke`, `read`, `write`, `delay`, `sample`, `assert`,
  `if`, `repeat`), every branch `additionalProperties: false`. No capture or
  `stream_subscribe` step can be expressed without an execution-contract revision. The gateway's
  `OperationVerb` (`host/types.py:86`) already carries all ten verbs and `OperationRequest` is
  verb-open — the blocker is the procedure corpus, not the dispatch types.

## Decision 1 — the activation point is `build_run`; quota ceilings are gateway-local config

Per bench device (from the admitted bench document's `devices[]`, each pinning a descriptor by
digest): resolve the RAW descriptor from the content store by digest. If
`integration.mode == "adapter"` — construct a real bridge; otherwise keep the existing
fixture-sim leg (disclosed as the demo-lattice declarative fallback). Construction, all on the
worker thread inside `build_run`:

1. `writer = CaptureStagingStore(worker_store, ...)` — one per device session.
2. `bundle, capture_controller = build_capture_services(descriptor_digest=…, content=content,
   writer=writer, clock=lambda: run_clock.now_ns() / 1e9, wall=…, quota=run_quota,
   context_key=f"run:{run_id}")` — the fresh-read clock and the host-minted context key are the
   record's Decision-3 pins; the `clock` lambda is the M2 timebase identity (seconds =
   nanoseconds/1e9 of the SAME clock the coordinator and poll engine use — Decision 5 below).
3. `stream_controller = build_stream_services(descriptor_digest=…, store=worker_store, wall=…,
   quota=run_quota, context_key=f"run:{run_id}", reading_sinks=shared_sinks)` (Decision 2).
4. `bridge = load_otdp_plugin(cache_root, manifest, manifest_sha256, entry_relpath, descriptor=raw,
   services=bundle, simulation=SimulationInfo(…), capture=capture_controller,
   stream=stream_controller)`; `bridge.plugin_open(bundle)` (the bridge opens on its
   construction services, `otdp_bridge.py:212`); the wrapped-plugins dict the coordinator
   receives holds the bridge, so `_MonitoringPlugin` ticks around every bridge dispatch exactly
   as it does for sim plugins (CTL-8 unamended in substance).

The package side: the run constructs only from the bench's **admitted closure** — the registry
session (`RegistrySession`, `interfaces/bootstrap.py:230`: resolver, `cache_root`, per-bench
activation records) that `create_app` already receives. The bench device's `generation` field is
the linkage to the bench's activation-record generation; the closure's resolved release carries
the manifest + digest; `integration.adapter.entry_point` names the entry module. The builder
verifies the exact lookup against `bootstrap.py` with the fixture lattice as proof (the demo
bench's `psu`/`controller` must resolve through it). If run-time resolution cannot reuse the
admin-flow machinery cleanly, the increment splits — composition over injected closures first,
registry resolution second — rather than inventing a second admission path (Risk 3; A11: a
downloaded package is data until commissioned locally, and the closure WAS commissioned by the
admin act).

**One context key per run** — `run:{run_id}` — across `RetainingServices`, every capture bundle
and every stream controller in the run. This is what makes the slice-2 erratum's shared
`event_log` accounting dimension TRUE in production (stream events, bundle evidence and forensic
markers consume one `(context_key, kind)` ceiling; the disclosed starvation directions are the
operational consequence, not a wiring accident).

**The quota seam (A02).** `build_run` constructs the run's `QuotaLimits` — the first production
site. `max_evidence_entries` keeps its in-tree derivation (`limits["max_page_size"] * 10`, the
same `quota` integer `create_app` already passes to `_build_run_factory`). `max_dataset_bytes`
and `max_event_batch` are **required gateway-local operator configuration** (new keys in the
app's `limits` mapping): absent keys + an adapter-mode device ⇒ `build_run` refuses loudly
before any device is opened — the worker's poison guard contains the job (honest
`outcome_unknown` projection, `worker.py:181–226`), and the refusal message names the missing
keys. `max_capture_bytes`/`max_subscriptions` take the fork-3 HINT defaults unless configured
(the `QuotaLimits` docstring's own posture; commissioned values come from bench qualification).
No silent defaults for required ceilings; runs without adapter-mode devices are unaffected.
Corpus promotion of the ceilings (commissioning-document fields) is a deferral row — the
Decision-8 precedent (gateway-local validated configuration now, corpus on trigger).

## Decision 2 — one shared `ReadingSinks`, minted once in `build_run`

`sinks = ReadingSinks()` once per run; passed BOTH to `RetainingServices(...,
reading_sinks=sinks)` (the run services — `register_reading_sink` lands there,
`content/store.py`) AND to every `build_stream_services(..., reading_sinks=sinks)` (telemetry
delivery after batch commit, `stream_services.py` `land_events`). The gap the issue names ("today
they can't see each other's state") is exactly the two-default-instances shape; the fix is
wiring, not mechanism — both constructor seams shipped in slices 1–2 for this. Delivery stays
contained on the `ReadingSinks` side (a raising sink counts on `failures`, never fails a landed
batch — `host/services.py:74–80`, the containment precedent Decision 5 extends).

## Decision 3 — streaming activation: run-owned subscriptions from the commissioned bench signals

The run engine — not the procedure — drives the stream verbs (the issue's own wording). The
commissioned source of WHAT to subscribe is the **bench document's declared signals**: for each
signal whose `source.device_id` is a bridge with a `StreamController` (i.e. the device admitted
with `event_sink`), subscribe with `parameters=(signal.source.parameter,)` and
`min_interval_ms = signal.poll_ms`, subscription id host-minted (`mint_subscription_id`), issued
as a `stream_subscribe` dispatch **through the wrapped plugin** so monitor ticks wrap it like
every dispatch. The authority is the admitted bench document — the same authority
`read_signal_values` uses for the monitor's read-based snapshots (A02/A03: commissioned
observations, explicit resource ownership); no new authority path exists, and policy allow rules
remain the procedure-lane gate for productive verbs (a subscription changes host+adapter state,
not device control state — it is an observation channel, argued once here so reviewers do not
re-litigate it per PR).

- **Arm** after monitor arming in `_prepare_run`'s composition (the coordinator gains a small
  run-scoped stream host holding one `StreamPollEngine` per streaming bridge: `poll=bridge.poll_event`,
  `live=controller.live_subscription_ids`, `clock=` the run clock, `tick=monitor.tick`,
  `poll_slice_ns=` Decision 4's derivation).
- **Refusals degrade loudly, never fail the run**: a subscribe refused at G2 (bench commissions
  faster than the descriptor's declared floor) or at the host ceiling is logged (machine-prefixed)
  and that signal simply has no stream — the monitor's read-based snapshot is unaffected. A
  subscribe that poisons the session follows the bridge's existing poison posture (the body ends
  `outcome_unknown` through the executor's normal classification).
- **Drive inside the wait-slice rhythm only** — the record's §8 words ("the run engine polls
  inside the wait-slice rhythm"). `_MonitoringClock.wait_ns` (`coordinator.py:366`) gains the
  stream host: per slice, run each engine's `poll_round(deadline_ns=slice_end,
  on_event=contained)` (the engine ticks the monitor between polls itself — its constructor
  contract), then sleep the unspent remainder so the wait's total duration is preserved. A
  procedure with no `delay` step polls nothing during the body — disclosed residual (the
  monitor's per-dispatch ticks still cover protection; the residual's remedy is the corpus train
  or Option B, not hidden polling — "no hidden background task" is §8's own rule).
- **Teardown at body end, before protection**: for each live subscription, a
  `stream_unsubscribe` dispatch (ticked like any dispatch); anything still live afterwards
  (refused, poisoned) is swept directly through the controller (`sweep(reason="run_body_end")` —
  the run owns the controllers it constructed), and `plugin_close` remains the last-resort sweep
  (`otdp_bridge.py:252–257`). No drain-before-unsubscribe: bounded endings (A12), the teardown
  marker is the record.
- **Aggregate teardown bound (audit F2, disclosed 2026-09-23):** each `stream_unsubscribe`
  carries its own `_DISPATCH_BUDGET_S` (5 s) deadline and the window has no shared cap, so
  body-end to protection-enter can stretch to N x 5 s at the configured subscription ceiling
  (default `max_subscriptions=16` -> ~80 s worst case). Per-dispatch bounding (A12) holds;
  the aggregate worst case is disclosed, not bounded. A shared teardown-window deadline is
  the named hardening if a commissioned envelope ever demands it.
- **The monitor is unchanged**: protection keeps gating on the read-based snapshot
  (`read_signal_values` per tick). Streams add landed `event_log` evidence, gap honesty and sink
  delivery — they do not replace the protection authority (R14 pins this both ways).

## Decision 4 — `poll_slice_ns ≥ bench_poll_ns`: one derivation, equality by construction

The stream host derives `poll_slice_ns := bench_poll_ns(bench)` — the same single derivation
every other consumer uses (`protection.py:52`: "One derivation for every consumer … so the
cadence can never drift between them"), wired where `_MonitoringClock` already derives its wait
slice (`coordinator.py:633`). Equality satisfies ≥ by construction, and both directions of the
rationale are served at equality:

- **The ≥ direction (the invariant):** the commissioned bench cadence is the finest
  device-interrogation the bench sanctioned (A02). Polling finer than `bench_poll_ns` is
  uncommissioned serial-thread load — each poll is a dispatch on the one worker thread. There is
  deliberately **no knob**: a future configurable slice must refuse values finer than
  `bench_poll_ns` (state the refusal, do not ship the parameter). The guard today is structural —
  the un-configurable derivation IS the mechanism.
- **The continuity direction:** each poll is bounded to one slice and monitor ticks run between
  polls (the engine's own contract), so the streaming-state tick gap is bounded by slice +
  overshoot — at equality that is the commissioned cadence plus the measured overshoot class
  (slice 2 measured max 26.0 ms worst-of-8 at a 10 ms slice; M-A re-measures it composed).

## Decision 5 — the `on_event` exit-path containment contract

The run owns the `on_event` callback it hands the engine; the contract has three clauses:

1. **Contained delivery.** Every `on_event` invocation runs inside a contained dispatcher shaped
   on `ReadingSinks.deliver` (`host/services.py:74–80`): a raising consumer increments a
   run-visible failure counter and logs (machine-prefixed); the raise never propagates into
   `poll_round`/`poll_until`, and it cannot fail a landing — the event was already landed
   transactionally inside `poll_event` before the callback fired (`otdp_bridge.py:799`).
2. **Exit-path teardown authority.** Regardless of callback behavior, "no stream outlives its
   host-owned subscription authority" rests on the run's exit path: body-end unsubscribe +
   controller sweep + the `plugin_close` sweep — never on the callback returning cleanly.
3. **Protection is unreachable to skip.** A raising consumer must not change the run's ending:
   the body proceeds, the protective transition runs on ANY body end (CTL-9/A04). R13 pins all
   three clauses under the absence-presence rule.

This closes the engine's own named residual (`stream_polling.py:32–36`) at the layer that owns
the callback — the engine's docstring already disclaims it correctly.

## Decision 6 — the capture procedure-step shape is corpus-gated (the maintainer's fork)

The closed eight-kind procedure schema cannot express a capture; adding kinds is an
execution-contract revision touching **three corpus surfaces in one train**:
`procedure.schema.json` (new step kinds), `safety-policy.schema.json` (CTL-4 requires an
allow-rule vocabulary for state-changing captures — the policy's rules are keyed
invoke-action/write-parameter today), and `execution-contract.md` prose. Copy-never-move, the
GOVERNANCE discipline, a real version train. **This increment cannot land it under the
no-standards-bytes constraint.** What lands here is the shape, designed so the train has a ready
home:

- Step: `{id, kind: "capture", role, format, sample_count, max_bytes, timeout_ms}` — the closed
  §7 argument set the bridge's `supported` map already pins (`otdp_bridge.py:285`); `timeout_ms`
  IS the capture budget (Amendment 3's correction — no new procedure-budget mechanism).
- `capture_id` is host-minted per occurrence — `cap:{run_id}:{step_id}{occurrence-suffix}`,
  mirroring `_operation_id` (`executor.py:589`) exactly as the record's Decision 3 names — and
  surfaces to later steps through the issued-id seam (the `$stg_issue` registry shape).
- The manifest lands in scope as the step's result (like invoke results); dataset-lane sampling
  of captures rides row 2, not this shape.
- Stream steps need no corpus change of their own for THIS increment (subscriptions are
  run-owned, Decision 3); procedure-authored subscribe steps would ride the same train if ever
  wanted.

**Recommendation:** accept the deferral (home: this record's deferral table + the execution-train
issue; trigger: row 9's own reopen trigger — the first real capture-class plugin — or the
dataset/invoke train #146, whichever lands first, since both need the same revision review).
The alternative — waiving the constraint and running the train inside #167 — is a 2–3× increment
and is NOT recommended: the construction wiring must land and be measured before the step shape
can be worth its corpus cost.

## Decision 7 — the deadline-aware busy-timeout clamp: six-point review CLOSES in the serial model (#159 arm 3)

The measured anchor (slice 1, #159): a failed capture dispatch under real second-writer
contention stretches to ~2× `busy_timeout` (10.73 s at the 5 s default, `state/store.py:93`) —
the append's BEGIN plus the abort epilogue's BEGIN, with the gate region a third potential
stretch — classified `RESOURCE_LIMIT`, session surviving. The clamp: make the worker
connection's `busy_timeout` deadline-aware during a capture dispatch. The six points:

1. **Leak discipline — closes.** The clamp is a per-dispatch `PRAGMA busy_timeout` set/restore
   pair on the worker's own connection, wrapped in `try/finally`; the worker is one thread and
   the bridge holds its `RLock` across the whole dispatch, so no interleaved user of that
   connection exists mid-dispatch. A dispatch that dies between set and restore restores in the
   `finally`.
2. **Epilogue budget — closes.** The abort epilogue runs on the failure path where the dispatch
   deadline may already be spent; clamping it to the (expired) deadline would make the epilogue
   fail instantly and leak staging rows. The epilogue therefore gets its OWN bounded budget —
   `min(lifecycle_timeout, busy_timeout)`-class — with `plugin_close`'s `sweep_open` and the
   startup `reclaim_orphans` as the designated retries (B15-iii's existing mold).
3. **Re-entrancy — closes.** Single worker thread + per-bridge `RLock` serialization; the
   main-thread store is a different connection and is the contention SOURCE, not a clamp
   subject.
4. **Refusal-rate trade — closes, and is bounded by construction.** Clamp =
   `min(default_busy_timeout, remaining_deadline)`: the only appends that newly refuse are the
   ones whose wait would have exceeded the deadline anyway (doomed to TIMEOUT regardless).
   Transient sub-deadline contention still waits and succeeds.
5. **Classification honesty — closes.** A clamped-out BEGIN surfaces as the same
   `sqlite3.OperationalError` the writer's stamping discipline already routes to the
   non-poisoning `RESOURCE_LIMIT`/`dispatched` class (`otdp_bridge.py:359–397`, pinned by
   `test_writer_originated_lock_contention_is_resource_limit`); no new classification path.
6. **Sweep exemption — closes.** `sweep_open`, the close path and the startup
   `CaptureStagingStore.reclaim_orphans` run outside any dispatch deadline and are not clamped.

**Verdict: the review closes on all six points within the serial model — arm 3's default reading
is UNFIRED.** The clamp's *build* is deferred (its home and trigger are the deferral table): the
stretch is a disclosed, classified, measured posture, and the clamp changes behavior only under
real cross-writer contention — landing it belongs with the first capture-class plugin's train,
re-measured through the activated composition. The measurement that would fire the arm is M-B
below, pre-committed.

## Decision 8 — TIMEOUT-on-cut disposition (owner call folded 2026-09-23)

**The as-is posture stands: a poll cut by the asyncio timeout at its slice deadline classifies as
session poison.** Rationale — A06, and the system's own standing rule: *the system records
evidence; the caller concludes.* A cut poll cannot prove the adapter did not hang, and a clean
`TIMEOUT` refusal would convert a possibly-hung adapter into a tidy answer with no evidence
behind it — exactly the ambiguity-laundering the project refuses. The alternative (cut polls as
clean `TIMEOUT` refusals) is **REJECTED** on that rationale. Record honesty already holds under
the current posture (PR #161's measurement: teardown markers landed, zero partial rows, in the
one window where a host stall pushed a poll past its slice).

**#43-record check (required by the fold-in):** the record's Decision 4 refusal taxonomy (record
lines ~264–268) names the three clean classes — unknown / known-but-ended (`INVALID_ARGUMENT`)
and quota exhaustion (`RESOURCE_LIMIT` + teardown) — and states protocol lies poison; it does
not address the cut case, which is carried by the slice-2 implementation
(`otdp_bridge.py` `poll_event`'s poison path), PR #161's body, and the engine docstring. **No
#43-record byte contradicts this disposition, so no erratum rides the PR and no #43-record byte
moves.**

## Minimal first increment

One branch, RED→GREEN slices per commit, gates before each commit (`uv run ruff check .`, bare
`uv run mypy`, focused `uv run pytest` + `tests/faults/` — the wiring touches `control/`):

1. `build_run` constructs bridges for adapter-mode devices over the worker-thread store
   (Decision 1): shared sinks, run context key, quota seam with loud refusal, `load_otdp_plugin`
   composition, registry-closure resolution. `_SIM_PLUGINS` remains only as the declarative
   fallback leg.
2. The stream host + coordinator composition (Decisions 3–5): arm/drive/teardown, contained
   `on_event`, slice derivation, `_MonitoringClock` wait-slice driving.
3. The design-record-decided prose: device-developer guide (host-owned subscriptions, poll
   rhythm, sinks, the containment promise) and operator guide (quota config keys, bridge runs).
4. The measurement pass (M-A/M-B/M-C) on the composed harness — the bench-measurer lane.

**Explicitly deferred — each row names its home and reopen trigger:**

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| A | Capture/stream **procedure-step shape** (corpus train: procedure schema + policy schema + contract prose) | This record §Decision 6 + the execution-train issue (open at this PR's merge, one issue) | First real capture-class plugin (row 9's own trigger), or the #146 dataset/invoke train — whichever first |
| B | **Busy-timeout clamp build** (review closed, Decision 7) | This record §Decision 7 + the same train issue as row A | Measured contention stretch exceeding a commissioned step budget through the activated composition on a real bench, or the capture train — whichever first. Measuring condition (added 2026-09-23): the M-B run measured the held-from-start GATE arm only — the anchor's mid-capture 2x-busy shape (a second writer acquiring after the gate) is unmeasured through the activated composition |
| C | **Quota-ceiling corpus promotion** (commissioning-doc fields) | This record §Decision 1 | A bench/commissioning definition needing ceilings to travel with the package (Decision-8 row-7 shape) |
| D | **Fixture-lattice streaming demo** (sim-psu gaining `event_sink` + `stream_limits` + plugin `next_event`; lattice rebuild per obligation 5) | This record §0; tracked in the train issue | The capture train (row A) — it rebuilds the lattice anyway |
| E | **Tick-boundary polling** (poll rounds at dispatch-boundary ticks, not just wait slices) | This record §Decision 3 residual | A real bench needing continuous telemetry through a wait-free procedure; or Option B (#159) |
| F | **Configured poll-slice knob with the ≥ refusal** | This record §Decision 4 | A commissioned bench needing a coarser slice than `bench_poll_ns` |
| G | **F4 loader-residual** — a non-canonical (re-serialized) manifest resolves at closure but refuses at `load_otdp_plugin` with `manifest_hash_mismatch` (the served-raw pin is stricter than the loader's canonical compare) | This record + the train issue | First real package whose manifest bytes are non-canonical, or the corpus train's manifest canonicalization pass — whichever first |

## Precedent (proven in-tree mechanisms this extends)

- `build_run`'s worker-thread construction seam (`app.py:327`, WP07 Task 8) — activation composes
  inside it; nothing new crosses a thread.
- `load_otdp_plugin` + the loader tests' composition pattern (`tests/integration/test_otdp_loading.py`
  — `services=bundle, capture=controller` through the real load path, A11).
- `bench_poll_ns` as the single cadence derivation (`protection.py:52`) — the slice binding joins
  its existing consumers rather than adding a second clock policy.
- `ReadingSinks.deliver`'s contained-failure shape (`host/services.py:74`) — extended verbatim to
  the `on_event` dispatcher.
- The slice-2 engine's own constructor contract (`stream_polling.py:84`) — the stream host is the
  "host loop" its docstring says may drive `poll_round`.
- The monitor's bench-signal iteration (`protection.py:109`) — the subscription set derives from
  the identical admitted declarations through the identical lookup.
- `_RetainingCoordinator`'s subclass hook pattern (`app.py:281`) — the stream host arms
  through the same prepare/finish override shape rather than forking the coordinator.

## Invariant and cross-surface impacts

- **CTL-8 (amendment candidate):** monitoring still wraps every dispatch — the subscribe/
  unsubscribe dispatches go through `_MonitoringPlugin` like all others — and every monotonic
  wait is still sliced at `bench_poll_ns` with a tick per slice; the amendment names that poll
  rounds run INSIDE those slices with the engine's between-poll ticks, and that streaming-state
  tick gaps carry the measured overshoot disclosure.
- **New invariant candidate (CTL-13, run-owned streaming composition):** subscriptions derive
  solely from admitted bench declarations; polls run only inside the wait-slice rhythm;
  `poll_slice_ns` equals `bench_poll_ns` by the one derivation and is never finer; teardown is
  exit-path-owned (body end + close); `on_event` is contained at the run boundary; one shared
  `ReadingSinks` and one run context key per run. Anchors: the stream host module,
  `coordinator.py` wait path, `app.py` construction.
- **CTL-4/CTL-5/CTL-6/CTL-7:** untouched this increment (no new step kind — that is row A's
  first design obligation when the train lands).
- **STO-1/STO-3, REG-1/REG-2:** honored by construction (worker store; loader-contained import
  released at close; timeout-after-dispatch honesty inherited from the bridge).
- **CON-10:** the factories re-derive raw descriptors by digest — the wiring supplies the
  bench-pinned digests already resolved in `_spool_documents`.
- **Obligations (drift-and-obligations.md):** #3 device-developer guide (loading/lifecycle/
  streaming behavior — moves); #4 operator guide + README (quota keys, bridge-constructing runs
  — moves); #5 fixture lattice — NOT touched (row D defers it); #6 vendored bytes — untouched;
  #13 validation reports — no corpus change, no rerun. CI cost: none new — all controls are
  plain pytest on the `gates` job; the measurement pass is run-lane, not CI.

## Pre-committed acceptance rule (written before any implementation number exists)

Floor semantics inherit the #43 record: every control must (a) pass with the mechanism present
and (b) **fail when only the mechanism commit is reverted** — absence-presence, watched red then
green. A control that stays green under (b) does not test the mechanism and must be fixed before
merge. No underpowered mode applies to the controls; the measurements carry their own
underpowered readings below.

- **R10 (real bridges over the worker store):** a run on the demo lattice (adapter-mode fixture
  devices) constructs `OTDPBridge` instances — asserted through the public composition (the
  adapter's received services object is the eight-member bundle shape, the loader-test
  precedent) — and the run's step events/terminal record are produced through them; the
  `_SIM_PLUGINS` path is NOT taken for those devices. RED: revert the construction wiring.
- **R11 (one shared `ReadingSinks`):** a sink registered through the run services
  (`register_reading_sink`) receives a reading delivered by a stream landing on a
  `StreamController` constructed in the same `build_run`. RED: revert to per-instance sinks —
  the sink observes nothing.
- **R12 (binding + timebase):** the composed engine's poll slice equals `bench_poll_ns(bench)`
  (asserted on the composed run, not the unit engine), and a hang-past-slice adapter's asyncio
  cut lands at the slice under the shared timebase — the production instance of the M2 pin,
  through the run wiring. RED: unbind the slice or split the clock — either assertion fails.
- **R13 (containment contract):** an `on_event` consumer that raises on every event: the body
  completes its steps, the protective transition runs, the terminal record is normal, every
  subscription reaches a terminal state (closed by unsubscribe or `host_ended` marker), and the
  failure counter is > 0. RED: remove the contained dispatcher — the escape derails the body or
  strands a subscription.
- **R14 (streams are additive to protection):** during a delay step, telemetry lands as
  `event_log` evidence under `run:{run_id}` carrying the Decision-4 landing fields — AND a
  condition that trips mid-delay still ends the body `tripped` (the read-based monitor gates;
  streams neither replace nor mask it). RED: revert the stream host (zero events) or revert the
  monitor gating (trip lost) — each direction fails its own half.
- **R15 (loud degradation):** a bench signal commissioned faster than the descriptor's declared
  floor → the subscription is refused cleanly, a machine-prefixed log line names it, the run
  proceeds, no session poison. RED: make degradation silent — the marker assertion fails.
- **R16 (quota seam refusal):** adapter-mode device + missing required quota keys → `build_run`
  refuses before any `plugin_open`; the worker contains the job (terminal projection without a
  fabricated outcome). RED: default the keys silently — the refusal assertion fails.

**Measurement contract (the bench-measurer lane, composed harness, real SQLite stores;
every number carries its denominator and names its harness):**

- **M-A — composed delivery budget and tick gap.** Median events/s shared across the bench's
  subscriptions during delay windows, with components (S_eff incl. sleep overshoot, ΣL̄), plus
  worst monitor-tick gap under saturated polling; ≥5 windows. **Ships if** the budget lies
  within its asymptote band `[1/S_eff, N/S_eff]` AND the worst tick gap ≤ slice + the measured
  overshoot class (slice 2's posture: 26.0 ms worst-of-8 at a 10 ms slice — i.e. ≤ ~2.6× slice).
  **Kills (wiring defect, fix before merge):** budget outside the band or tick gap above the
  class — a pacing defect, explicitly NOT Option-B evidence. Sample: ≥5 windows; fewer or
  >25% spread ⇒ underpowered — record as underpowered, re-run with a stable harness, decide
  nothing from it.
- **M-B — #159 arm-3 evidence (pre-committed reading).** The serial-model contention
  measurement through the ACTIVATED composition: a failed capture dispatch under a held
  second-writer `BEGIN IMMEDIATE` (the `test_capture_sequential_model.py` shape), measuring the
  dispatch's wall-stretch vs the commissioned step deadline, ≥5 trials. **Arm 3 FIRES only if**
  the six-point review cannot hold — operationally: the measured stretch exceeds the record's
  stated bound (2× `busy_timeout` + gate-region stretch; slice-1 anchor 10.73 s at the 5 s
  default) by a margin the clamp design cannot remove, or the monitor gap during the stretched
  dispatch breaches the capture-deadline policy bound (slice-1 budget class, 50 ms) with no
  clamp-side remediation. **Default: arm UNFIRED** — the review closed on all six points
  (Decision 7), and a stretch within the recorded bound confirms it. **Underpowered reading:**
  if the contention window cannot be reproduced stably (spread >25% of the bound across ≥5
  trials), record underpowered + arm unfired + the clamp row's trigger gains "re-measure with a
  stable harness". M-B never silently converts to evidence for Option B — firing the arm is a
  written conclusion against these pre-committed bounds, posted to #159.
- **M-C — queued-run delay behind the composed run** (the #159 disclosure axis, re-measured with
  streaming live): expectation — the slice-1 class unchanged (56.1 ms behind a 50 ms capture),
  because poll work is slice-bounded inside waits that already blocked the queue. Ships within
  2× the slice-1 anchor; a larger delay is a wiring defect (find the unbounded poll path), not
  Option-B evidence.

**Measurement outcome note (2026-09-23, post-measurement; attribution corrected after the
cross-vendor audit and the independent review converged on it):** all three axes conclusive —
M-A and M-C shipped inside their bands; M-B read arm-3 UNFIRED on powered evidence (median
5.199 s over 5 trials, spread 1.4%, vs the 10.73 s fire line). The composed finding's
mechanism: under a held-from-start `BEGIN IMMEDIATE` the first contended write is the G3
gate's `open_capture` check-and-reserve (`otdp_bridge.py:493` -> `capture_store.py:150`
waits 1x `busy_timeout`; the F6 arm at `otdp_bridge.py:516` classifies
`RESOURCE_LIMIT`/`NOT_DISPATCHED`) — NOT `mark_dispatch_started`, which is a flag set
plus deadline check with no store access. **Anchor-path disclosure:** the slice-1 anchor
shape (append + abort-epilogue, 2x `busy_timeout`, `DISPATCHED`) was NOT the measured
path — it is reachable only under mid-capture contention, a second writer acquiring after
the gate, and is unmeasured through the activated composition (row B's measuring condition).
The refusal classification and the UNFIRED reading stand unchanged.

## Top risks and what falsifies this design

| Risk | Falsifier / disposition |
|---|---|
| **Run-owned subscriptions are a new dispatch authority** (device interrogations not expressed in the procedure) | The authority is the admitted bench document — the identical declarations and lookup the monitor's read path uses; no procedure bypass exists (policy rules still gate productive verbs). A maintainer ruling that ALL interrogations must be procedure-expressed kills Decision 3 → streaming activation moves to the corpus train with row A; the construction wiring (Decision 1) survives either ruling. |
| **Monitor-tick stretch during poll rounds on the serial thread** | M-A's tick-gap axis; breach of the posture class → polls move to a coarser sub-multiple of the slice (still ≥ cadence) or residual E defers to #159 — measured before merge, not after. |
| **Registry-closure resolution at run time may not reuse the admin-flow machinery cleanly** (the resolver/admission path was built for the change kinds) | Builder verifies against `bootstrap.py` with the fixture lattice as proof; if it does not compose, the increment SPLITS (composition over injected closures first, resolution second) — named here so the split is a plan, not a discovery. Inventing a second admission path is the DON'T-BUILD line: it would violate A11's local-adoption authority. |
| **Quota config keys are an operator-facing addition** | Lazy refusal only for adapter-mode devices (sim/declarative benches unaffected); operator-guide obligation moves in the same PR. A missing key can never silently default (R16). |
| **The shared `event_log` dimension starves a chatty stream against the bundle's evidence** (the erratum-1 disclosure, now real in production) | Inherent to the record's landing kind, disclosed at slice 2 and inherited here by the one-context-key pin; the starvation directions are operational (raise `max_evidence_entries`), not a wiring defect — and splitting the dimension remains the corpus-revision call it was then. |
