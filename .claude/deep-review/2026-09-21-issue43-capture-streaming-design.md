# Capture & streaming design of record (issue #43)

**Date:** 2026-09-21 · **Issue:** [#43](https://github.com/madeinoz67/benchweave/issues/43) (absorbs #77)
**Corpus:** `standards/otdp/0.2.0` — read-only here. No standards byte moves in any slice of
this design; the obligations section names the cases that would.
**Verdict on the contributor proposal:** BLESS-AS-AMENDED (Decisions 1, 3–5, 7–8 amend;
the rest bless as proposed).

## 0. Grounding corrections — checked against code and corpus, not the issue prose

- **Version.** The issue says "OTDP 0.3.0"; the canonical corpus and the vendored tree
  (`standards-lock.json`, single active version) are at **0.2.0**. Every capability the
  issue cites — capture/stream verbs (`otdp-runtime.schema.json` `$defs/operationRequest`
  verb enum), `next_event` (spec §8), the artifact services (§8 + extension-contract §3),
  the nine dataset kinds (measurement-model §1) — exists in 0.2.0. Citations below anchor
  0.2.0; if a 0.3.0 train lands first they re-anchor to it. Nothing here *requires* a 0.3.0.
- **Two lanes, not one.** Spec §7: *"The retained core capture verb has one channel per
  capture. Multi-channel, irregularly sampled, digital, spectral, tabular and complex
  results use typed class-profile invoke actions and the measurement schema."* The core
  `captureManifest` is closed and single-artifact. The issue's heterogeneous-data goal
  therefore rides the **class/invoke lane** (§14, extension-contract), not the core
  capture verb. This design keeps the lanes separate end to end.
- **What already exists in-tree** (the design must not re-propose): the verified loader
  (`registry/otdp_loading.py` `load_otdp_plugin`), `OTDPBridge` (identify/read/write;
  capture/`stream_*`/`invoke` refused `UNSUPPORTED` before the adapter is called),
  `ContentStore` (content-addressed artifact storage, chunked ≤ 65,536 B, windowed reads
  with sha256, per-context evidence quota), `RetainingServices` (only `retain_evidence`
  live; the rest raise loudly), the run coordinator with per-dispatch monitoring, MCP
  `stg_v1_artifact_read`/`stg_v1_evidence_get`, and the derived-variable evaluator
  (`measurement/derivation.py`). No production path constructs a bridge yet — only tests
  call `load_otdp_plugin`.
- **The bridge docstring** says *"Dataset, profile and stream semantics need a native
  async host."* For capture/stream this overstates the need (Decision 1); the sentence is
  amended when slice 1 lands to name the real boundary.

## Decision 1 — Option A affirmed: extend the synchronous bridge

The spec's own scheduling model is per-instance serialization — §8: *"Host scheduling
allows at most one execute/next_event call in flight on the instance."* The bridge's
`RLock` + one `asyncio.Runner` per instance provides exactly that; N devices = N bridges,
each serialized, concurrent at the coordinator — which already orchestrates N plugins per
run (`_MonitoringPlugin`). `next_event` is another bounded await through the same `_run`
deadline wrapper, mechanically identical to `execute`. Deadline enforcement mid-capture
works synchronously (the `bounded()` timeout cancels at the deadline; an over-deadline
capture yields the existing conservative `unknown`/poison posture, unchanged).

**Amendment to the issue's framing:** the docstring's "needs a native async host" is true
of *poll multiplexing across devices on one thread* and of the eventual invoke/dataset
scheduling — not of capture/stream correctness. Slice 1 rewrites that sentence to say so.
Option B stays recorded, not rejected (Deferrals, row 1).

## Decision 2 — scope rides the two lanes

| Lane | Verbs/services | Corpus status | Slice here |
|---|---|---|---|
| Core capture | `capture` (one channel, `waveform_f64le`/`raw_binary`), `artifact_append/finalise/abort` | fully specified (§5, §7, §8; runtime schema) | **1** |
| Streaming | `stream_subscribe`/`stream_unsubscribe`, `next_event` | fully specified (§5, §7, §8; `$defs/event`) | **2** |
| Dataset/invoke | `invoke`, `dataset_publish`/`dataset_lookup`/`artifact_read`/`payload_*` | fully specified (§14, extension-contract §3) | deferred (row 2) |

## Decision 3 — core capture mechanism (slice 1, the minimal first increment)

`dispatch` grows `capture` with the closed argument set
`{capture_id, format, sample_count, max_bytes}`; the **host mints** `capture_id`
(run-engine-issued, like operation IDs). Three pre-dispatch gates, all refusing
`RESOURCE_LIMIT`/`INVALID_ARGUMENT` `not_dispatched` **before the adapter is called**:

| Gate | Check | Source |
|---|---|---|
| G1 arithmetic | `waveform_f64le`: `sample_count × 8 ≤ max_bytes` (schema already pins `byte_length = count×8` at manifest time) | §7, `$defs/captureManifest` |
| G2 descriptor | `sample_count ≤ capture_limits.max_samples` ∧ `max_bytes ≤ capture_limits.max_bytes`; format ∈ descriptor `capture_formats` | §7 *"Requests must satisfy both descriptor and host limits"* |
| G3 quota | writer allowance ≤ remaining quota, enforced before any write | services.py `QuotaLimits` docstring; §7 |

A composing **capture-services object** implements the spec §8 shape
(`monotonic`/`utc_now`/`record_evidence`/`artifact_append`/`artifact_finalise`/
`artifact_abort`) by delegating to gateway capabilities: clocks from the host clock,
evidence to `ContentStore.put_evidence`, artifacts to chunked `ContentStore.put_artifact`
appends. `artifact_finalise` computes length/SHA-256 **host-side** and returns the
manifest validated against `$defs/captureManifest`; plugin-supplied metadata cannot
override them (§7, quoted verbatim in the issue — confirmed normative).
`artifact_abort` is idempotent, publishes nothing, and stays callable from inside the
adapter's own `execute` cleanup after a deadline (§8) — the session-poison posture of a
late/uncertain result is unchanged. `QuotaLimits` grows one finite field
(`max_capture_bytes`, single-capture ceiling alongside cumulative `max_dataset_bytes`) —
additive; `test_host_abi.py` pins HostServices *methods*, not quota fields.

## Decision 4 — streaming mechanism (slice 2)

- `dispatch` grows `stream_subscribe`/`stream_unsubscribe` with the closed §5 argument
  sets; **subscription IDs are host-minted** (§5: "Host subscription ID"), echoed by the
  adapter. `stream_limits` (`min_interval_ms` floor, `max_subscriptions`) enforced at
  G2; the bridge tracks live subscriptions per instance; close clears them (§7).
- The bridge grows `next_event(subscription_id, deadline_ns)` mirroring `dispatch`'s
  envelope conversion. Events validate against the closed `$defs/event`: kinds
  `telemetry|alarm|gap|ended`; `telemetry` requires a `reading`, the others require
  `code`+`message`; `sequence ≥ 0` and **monotone per subscription** — a regression or
  non-schema event is `PROTOCOL_ERROR` and poisons, like any protocol lie.
- `gap`-before-subsequent-telemetry after discarded data is the adapter's duty (§7); the
  host's monotone-sequence check plus the recorded `gap` events make violations visible.
- **Landing:** telemetry and gap/alarm/ended events land as `event_log`-kind evidence
  rows under `max_event_batch`; `emit_event` and `register_reading_sink` get real
  implementations. They are **not** new interface event kinds — the interface event def
  is closed by design (Deferrals, row 5).
- **No hidden background task** (§8): the run engine polls round-robin across bridges;
  subscriptions live inside run lifecycles and die with the run ("No stream outlives its
  host-owned subscription authority").

## Decision 5 — #77 fetch-lane bound (absorbed): bounded-by-mechanism

The #64 position — fetch pairs count with `max_bytes`, the operative materialization
budget — is kept, and upgraded from a shrug to a mechanism with named enforcement points:

- **Core lane:** G1–G3 above. The schema ceiling stays absent *because* the request
  carries its own `max_bytes` and the host **never allocates the cap** — the writer
  appends in bounded chunks, so an absurd `max_bytes` can only be refused (G2/G3) or fill
  the quota, never OOM the host. The #64-F1 failure shape (a lane-passing *preset*
  baking a huge count that fetch materializes later) cannot recur: nothing durable bakes
  an unbounded count on this lane.
- **Class lane:** fetch inputs carry `max_bytes` (no count); the acquisition count was
  bounded at configure by the 1e6 ceiling — device-classes §2: *"A class bound is a
  resource backstop for the fetch lane, not an instrument capability claim."* G2/G3 apply
  host-side pre-dispatch identically. No new schema ceiling.
- **`sample_rate_hz`: unbounded above, by decision, with the rationale recorded.** No
  resource term multiplies by rate: at bounded count (≤ 1e6) and fixed width, fetch bytes
  are independent of rate; duration = count/rate *falls* as rate rises, and the low-rate
  direction is bounded by the operation deadline plus honest partial datasets
  (device-classes §3). Streaming rate is governed by `min_interval_ms`, not
  `sample_rate_hz`. A schema ceiling would be a plausibility claim needing per-class
  hardware evidence this design does not carry (#64's bar: an evidenced number — 64, 1e6).
  Residual, disclosed: a descriptor claiming a physically absurd rate is an honesty
  defect for the authoring procedure (§2 "Describe only verified capabilities") and C12
  evidence, not a resource bound.
  **Reopen triggers:** any measured OOM/DoS trace where `sample_rate_hz` is the
  load-bearing term; or a catalog revision carrying per-class evidenced ceilings.

## Decision 6 — the two `HostServices` surfaces: compose, don't merge

They are different things, not one unreconciled surface. The gateway protocol
(`host/services.py`: `resolve_content`/`retain_evidence`/`emit_event`/`quota_state`/
`register_reading_sink`) is the **run-host capability surface**, pinned closed by
`test_host_services_is_the_scoped_surface`. The SDK/spec shape (`interfaces.py`,
normative name `HostServices` per §8: `monotonic`/`utc_now`/`transfer`/
`close_transport`/`record_evidence` [+ capture writers]) is the **adapter ABI**. The
bridge requires the SDK shape (constructor checks `monotonic`); `RetainingServices`
implements the gateway shape. Reconciliation = the Decision-3 composing object
implements the SDK shape per plugin session; both protocols stay as they are, each
docstring naming the other. No merge, no rename, no contract-test change.

## Decision 7 — contributor comment on capture-event storage: BLESS-AS-AMENDED

| Point | Disposition | Evidence |
|---|---|---|
| Host-managed storage; host issues capture ID + writer allowance | **Bless** — already normative | §7; §8 *"The host supplies a monotonic clock … scoped transport and optional capture writer"* |
| Per-artifact SHA-256 + length bound in a manifest | **Bless** — it is the existing `payload_finalise` contract, which *"computes and returns the artifact object (ID, encoding, byte length, SHA-256)"*; the prototype's delta (it has `size_bytes`, no digest) is precisely this | extension-contract §3 |
| "A capture event groups multiple files" under one ID | **Amend.** In the dataset lane, grouping exists today: one dataset manifest carries per-variable artifacts each with its own `{id, sha256, byte_length}` (measurement-model §1–2, M11) — the grouping key is `dataset_id`. In the **core lane the manifest is closed single-artifact**; grouping there is a corpus revision, refused in these slices | `$defs/captureManifest` (`additionalProperties: false`) |
| Three artifact classes (primary / manifest / derived renderings) with different lifecycles | **Amend.** At publish time every admitted artifact is integrity-bound identically; the classes are **retention-time selectors** and land with the retention slice (Decision 8) as policy selectors, not as a capture-layer concept | — |
| VCD + rendered graphs as artifacts | **Amend.** VCD is a container format → *"Compression/container formats require an explicit new encoding contract"* (measurement-model §2); a logic capture's primary in-model form is `digital_trace`/`logic_u8`. Renderings are regenerable and are **not admitted to the artifact store at all** — stricter than "cache at most" (Fork 3) | measurement-model §2 |

## Decision 8 — retention & reporting: report first, dispose never (until audited)

- **Slice 3 = the reports, read-only.** A retention/disposal view mapping each
  capture/dataset to its governing policy and disposal date (or `held`/permanent), plus
  the storage-growth projection (per-stream byte rate × duty × window), as a CLI
  projection over the content store — recomputed each run from current policy, never
  cached dates. The indefinite/hold tier is what makes the projection load-bearing
  (issue §8–§9), and it exists because quotas (`max_dataset_bytes`) still bound the
  unbounded-retention case.
- **Policies:** declarative, schema-validated, composed of the admitted primitives
  (`duration`, `retain_after` ∈ {`last_access`,`run_end`,…}, `on_disposition` ∈
  {`delete`,`archive`,`review`}, `hold`, data-class selectors) — the issue's Option A.
  First home: gateway-local validated configuration; corpus promotion only on trigger
  (row 7).
- **Sequencing invariant:** no automated disposition ships until the disposition audit
  trail exists. Slice 3 deletes nothing; a disposal decision is a report row until the
  audit trail slice lands after it.
- **Granularity:** global default + per-data-class in slice 3 (per-bench is a natural
  key and comes free). **Per-project requires a project entity the gateway does not
  have** (benches/runs only) — Fork 1, recommendation: do not introduce one inside #43.

## §11 open questions — resolved or deferred

| Item | Disposition |
|---|---|
| Video / continuous capture | **Defer** (row 4): `image` kind exists; no camera control profile; segmented acquisition explicitly unstandardized (measurement-model §5); codec/container needs a new encoding contract. It is the retention stress case, which slice 3's projection surfaces without standardizing video. |
| Derived quantities / virtual channels | **Resolved, no action:** standardized since 0.2.0 — `derived_variables` + grammar + M15/S19 (measurement-model §8), evaluator in-tree (`measurement/derivation.py`). Ad-hoc gateway-side expressions remain excluded by the execution contract, as the issue notes. |
| Retention granularity | **Resolved for slices:** global + per-data-class (+ per-bench); per-project = Fork 1. |
| Disposition audit trail / archival tier | **Defer** (row 3), gated before any automated disposition (Decision 8). |
| Buffering (in-memory vs spooled) | **Resolved by mechanism:** no whole-capture buffer exists — the writer appends in ≤ 64 KiB chunks straight to the store; memory is bounded by chunk size regardless of capture size. Host-side spooling is unnecessary while sqlite throughput holds (Risk 2 is its trigger). |
| Transport providers (UVC / vendor SDKs) | **Defer** (row 6): separately reviewed host-provider contracts (extension-contract §6 says so verbatim). |

## Minimal first increment and slice order

1. **Slice 1 — core capture** (Decision 3): gates G1–G3, composing capture-services
   object over `ContentStore` (+ `max_capture_bytes` quota field), `dispatch(capture)`
   with manifest conversion, abort semantics, docstring amendment.
2. **Slice 2 — streaming** (Decision 4).
3. **Slice 3 — retention reports** (Decision 8).

One RED→GREEN slice per commit; working branch, PR, double review; gates
(`uv run pytest`, `ruff check .`, bare `uv run mypy`) before each commit. Each merged PR
opens at most one follow-on issue.

## Pre-committed acceptance rule (for the implementation PRs — binary gates, no tuning)

Written before any implementation number exists. All four controls must (a) pass with the
mechanism present and (b) **fail when only the mechanism is reverted** — the reviewer
reverts the mechanism commit and watches red, restores and watches green. Any control
failing in (a) kills the slice; a control that stays green under (b) means the control
does not test the mechanism and must be fixed before merge. No underpowered mode applies:
these are absence-presence gates, not statistical claims.

- **R1 (bounds before device):** a capture with `sample_count×8 > max_bytes` (and a
  G2/G3 variant) against an admitting descriptor returns `RESOURCE_LIMIT`
  `not_dispatched` with a spy adapter recording **zero** `execute` calls.
- **R2 (abort-not-published):** an adapter that appends bytes then raises post-dispatch
  leaves **zero** artifact rows and zero evidence rows (store count assertions) and the
  result is `unknown`/`error` with `dispatch_state` `dispatched|unknown`.
- **R3 (host-computed integrity):** the manifest's `sha256`/`byte_length` equal the
  host's recomputation over `artifact_read` chunks; an adapter-supplied wrong length in
  finalise metadata is ignored in favour of the host value.
- **R4 (stream honesty):** a non-monotone `sequence` for a subscription is
  `PROTOCOL_ERROR`; after a simulated drop, a `gap` event precedes subsequent telemetry
  (fixture adapter), and the evidence rows show it.

## Invariant and cross-surface impacts

- **STD-1/2/3/5, TWO-1:** untouched in slices 1–3 — no vendored byte moves,
  `sync-standards --check` stays green, no SDK push needed (slices 1–2 change no SDK
  surface; `CaptureServices` is already vendored in `interfaces.py`).
- **Pins that move, main-side:** `tests/sdk/test_adapter_agreement.py` — `ADAPTER_GAPS`
  loses `next_event`, the "capture surface is SDK-only" note on
  `EXPECTED_CAPTURE_SERVICES` flips when the gateway implements the writer, and the
  bridge's supported-verb set changes (the comparator forces each consciously).
  `tests/unit/test_otdp_bridge.py` — the `UNSUPPORTED` pin narrows to the still-refused
  verbs. `tests/contract/test_host_abi.py` — unchanged (the scoped surface does not
  grow). `tests/integration/test_otdp_loading.py` — unaffected.
- **Interface corpus:** no new operation in slices 1–3 (captures run inside runs;
  artifacts already served by `stg_v1_artifact_read`). Row 5 carries the exposure case.
- **Dataset lane (deferred):** SDK `interfaces.py` grows `dataset_publish`/`payload_*`
  then — SDK commit first, pointer after (TWO-1), user-guide + AI-GUIDE obligations per
  drift-and-obligations items 1–2.
- **CI cost:** none new; the four R-controls are plain pytest.

## Top risks and what falsifies this design

| Risk | Falsifier |
|---|---|
| Head-of-line blocking: one long capture on the worker thread starves other devices' polls | Slice-2 concurrency test: with bridge A capturing, bridge B's poll latency stays within its budget; if it cannot across ≥ 3 bridges, Option B triggers early (row 1's trigger, measured) |
| sqlite single-writer throughput under chunked appends below real fetch sizes (8 MB/fetch at the 1e6 ceiling) | Sustained-append measurement in slice 1's PR; below the deadline budget → spooling design (row 8's trigger) |
| Two same-named `HostServices` protocols confuse plugin authors | Docs-coverage review of the device-developer guide sections the slices touch |
| Retention report projecting from stale policy | Report recomputes; no cached disposal dates anywhere in the design |

## Deferrals — every row carries carrier and reopen trigger

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| 1 | Option B native async host | Follow-on issue opened at slice-1/2 merge (one issue) | Measured poll starvation (a device's `min_interval_ms` missed by > 2× the median inter-poll interval across ≥ 3 concurrent bridges), or the dataset/invoke lane landing |
| 2 | Dataset/invoke lane (invoke dispatch, `dataset_publish`/`payload_*`, SDK interfaces) | Separate issue at slice-2 merge (existing queue if one already carries it) | First class-profile plugin needing multi-channel/typed capture from the gateway |
| 3 | Automated disposition + audit trail (+ archival tier) | Documentation here; issue at slice-3 merge | Slice 3 (reports) merged — audit trail is the next slice, and no automated deletion may precede it |
| 4 | Video/continuous capture; VCD/codec encoding contracts; camera profile | Documentation here | A concrete video/image-capture requirement from a real project (unnamed here by policy) |
| 5 | Interface-corpus exposure of capture/telemetry (new MCP operations) | Documentation here | A caller needing capture or live telemetry outside the run engine |
| 6 | Transport providers (UVC, vendor SDKs) | Documentation here | A device class in scope whose transport is not one of the scoped primitives |
| 7 | Retention-policy schema corpus promotion (execution package) | Documentation here | A policy needing to travel with a package or bench definition |
| 8 | Host-side spooling for large captures | Documentation here | Risk-2 throughput measurement below the fetch deadline budget |

## Forks for the owner (decisions taken neither here nor in the issue)

1. **Per-project retention** requires a project entity the gateway does not have.
   Recommendation: global + per-data-class (+ per-bench) now; introduce a project entity
   only when more than retention wants it.
2. **Retention-policy home at birth:** gateway-local (recommended, this design) vs
   corpus-side from day one (portable, but a standards train for a first slice).
3. **Derived renderings:** this design admits none to the artifact store (stricter than
   the contributor's "cache at most"). If renderings must be gateway-served, they need a
   non-evidence artifact class — a corpus-adjacent decision.
4. **Telemetry surface:** run-internal only (this design) vs caller-facing subscription
   reads (row 5's interface-corpus train).
