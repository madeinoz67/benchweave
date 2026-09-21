# Capture & streaming design of record (issue #43)

**Date:** 2026-09-21 · **Issue:** [#43](https://github.com/madeinoz67/benchweave/issues/43) (absorbs #77)
**Corpus:** `standards/otdp/0.2.0` — read-only here. No standards byte moves in any slice of
this design; the obligations section names the cases that would.
**Verdict on the contributor proposal:** BLESS-AS-AMENDED (Decisions 1, 3–5, 7–8 amend;
the rest bless as proposed).
**Amendment 1 (2026-09-21):** integrated a 12-analyst source-grounded RedTeam pass.
Two load-bearing mechanism claims were checkably false and are corrected in place; the
safety-monitoring, quota, and acceptance-rule machinery is now designed rather than
assumed. See **Amendment 1** at the end for provenance and the change list.
**Amendment 2 (2026-09-21):** standalone capture mode added as slice-1 scope
(Decision 9) — plugin-local capture for development and bench testing without the
gateway: same `CaptureServices` shape, filesystem backend, default location under
the plugin directory, path configurable.

## 0. Grounding corrections — checked against code and corpus, not the issue prose

- **Version.** The issue says "OTDP 0.3.0"; the canonical corpus and the vendored tree
  are at **0.2.0** (gateway authority: the standards manifest, `standards/otdp/0.2.0`;
  the lock file lives SDK-side at `packages/sdk/standards-lock.json`). Every capability
  the issue cites — capture/stream verbs (`otdp-runtime.schema.json` `$defs/operationRequest`
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
  `ContentStore` (content-addressed artifact storage, windowed reads with sha256,
  per-context evidence quota), `RetainingServices` in `content/store.py` (only
  `retain_evidence` live; the rest raise loudly), the run coordinator with per-dispatch
  monitoring, MCP `stg_v1_artifact_read`/`stg_v1_evidence_get`, and the derived-variable
  evaluator (`measurement/derivation.py`). No production path constructs a bridge yet —
  only tests call `load_otdp_plugin`. Conversely, **what does not exist and is slice
  construction, not delegation**: any append/append API on `ContentStore` (`put_artifact`
  is whole-blob content-addressed; `MAX_CHUNK_BYTES` clamps read windows only),
  any cross-bridge concurrency (see Decision 1), any `next_event` poll loop, any
  `emit_event`/`register_reading_sink` implementation (both raise `NotImplementedError`),
  any `max_event_batch` enforcement, and any byte-quota accounting. `artifact_append`,
  `next_event`, and `CaptureServices` have zero hits in gateway source. Slices 1–2 build
  these; nothing below claims them as existing.
- **The bridge docstring** says *"Dataset, profile and stream semantics need a native
  async host"* (and "OTDP 0.3/API 1.1" — prose drift). For capture/stream the async-host
  part overstates the need (Decision 1); the sentence is amended when slice 1 lands to
  name the real boundary and fix the version.

## Decision 1 — Option A affirmed: extend the synchronous bridge (serial model disclosed)

The spec's own scheduling model is per-instance serialization — §8: *"Host scheduling
allows at most one execute/next_event call in flight on the instance."* The bridge's
`RLock` + one `asyncio.Runner` per instance provides exactly that. But the engine that
would run N bridges concurrently **does not exist**: the coordinator is explicitly
*"single-threaded and deterministic on the injected clocks"*, the run worker is one FIFO
thread with exactly one active run, and the executor walks procedure steps sequentially.
Today there is exactly one dispatch in flight engine-wide, and per-instance serialization
is satisfied trivially.

**What slices 1–2 therefore ship, named:** globally serialized long captures on the one
worker thread. Four consequences are disclosed and priced, not deferred:

1. **§7 monitoring blackout during captures.** `_MonitoringPlugin` wraps each dispatch
   as tick → dispatch → tick; no tick can run inside a blocking dispatch, so condition
   evaluation (trip latching), run-cancel detection, and lease-loss detection all freeze
   for the capture's duration. On a physical-bench product this is a safety-posture
   change, not a latency risk. Slice 1 discloses it and **bounds it by policy**: capture
   dispatches carry a capture-scaled deadline (next paragraph), and the first slice-1
   PR includes the monitor-gap measurement (below).
2. **Cancel latency equals capture length.** `monitor.request_cancel()` is honored at
   the next tick — after the capture. Accepted for slices 1–2 under the same deadline
   policy; re-measured when Option B is evaluated.
3. **Protective actions against the capturing device wait out the capture** (they block
   on the bridge `RLock`, and the bridge's deadline check runs after lock acquisition).
   Accepted with the same policy bound; named here so it is a decision, not a surprise.
4. **Queued runs delay** behind a long capture. Part of the same measured trade.

**Capture deadline policy (new, slice-1 scope).** Nothing in the tree grants a capture
dispatch its deadline today: the monitor wrapper slices dispatches at bench poll cadence,
under which any realistic capture (seconds of acquisition) would be cancelled and
poisoned **by construction**. Slice 1 therefore defines the derivation: a capture
dispatch's `deadline_ns` is capture-scaled — taken from the procedure's capture budget
(procedure-declared, validated against G1–G3 arithmetic at admission), never the poll
slice. The `bounded()` timeout and the unknown/poison posture on over-deadline captures
are unchanged.

**Measurement timing (amended).** The Option-A-decisive mechanism is observable in
slice 1 (tick starvation and monitor-gap duration during a real capture), so the
head-of-line/monitor-gap measurement moves **into slice 1's PR**. Its quantities are
sequential-model quantities: monitor-gap duration during a deadline-max capture vs bench
poll cadence; queued-run delay; protective-action latency on a capturing bridge. Option B
is still recorded, not rejected (Deferrals, row 1) — but its reopen trigger is restated
in those measurable quantities (row 1), not in invented concurrency thresholds.

**Amendment to the issue's framing:** the docstring's "needs a native async host" is true
of *poll multiplexing across devices on one thread* and of the eventual invoke/dataset
scheduling — not of capture/stream correctness. Slice 1 rewrites that sentence to say so.
What actually forces Option B is the polling engine of slice 2 — which is mini-Option-B
machinery inside the executor, priced there (Decision 4).

## Decision 2 — scope rides the two lanes

| Lane | Verbs/services | Corpus status | Slice here |
|---|---|---|---|
| Core capture | `capture` (one channel, `waveform_f64le`/`raw_binary`), `artifact_append/finalise/abort` | fully specified (§5, §7, §8; runtime schema) | **1** |
| Streaming | `stream_subscribe`/`stream_unsubscribe`, `next_event` | fully specified (§5, §7, §8; `$defs/event`) | **2** |
| Dataset/invoke | `invoke`, `dataset_publish`/`dataset_lookup`/`artifact_read`/`payload_*` | fully specified (§14, extension-contract §3) | deferred (row 2) |

## Decision 3 — core capture mechanism (slice 1, the minimal first increment)

`dispatch` grows `capture` with the closed argument set
`{capture_id, format, sample_count, max_bytes}`; the **host mints** `capture_id`
(run-engine-issued, like operation IDs — `_operation_id` is the in-tree precedent).

**The staged-append store writer is a designed slice-1 component, not delegation.**
`ContentStore.put_artifact(data: bytes)` is whole-blob and content-addressed — you cannot
append to an `art-<sha256>` row that does not exist yet. Slice 1 builds the writer as a
new store surface (one new migration — the migration list below is no longer "only the
QuotaLimits field"):

- **Staging table** keyed by `capture_id` with a state marker
  (`staged | finalised | aborted`) decided at slice 1 so later GC never needs heuristics;
  ordered chunk rows; incremental SHA-256 as chunks arrive.
- **Finalise** concatenates staged chunks, completes the digest, publishes the
  content-addressed row, and marks staging `finalised`.
- **Abort** deletes staged rows and marks the staging entry `aborted` — the only delete
  path, reference-checked against published digests.
- **Crash recovery:** a startup/reconcile sweep reclaims staging orphaned by host death
  mid-capture, mirroring the existing `reconcile_dangling_requests` pattern.
- **Byte accounting:** charge-per-append with refund on abort/timeout; the writer refuses
  (RESOURCE_LIMIT receipt, not session poison — a resource condition is not a protocol
  lie) when an append exceeds the allowance, and refuses appends after the SDK context
  reports cancellation (`is_cancelled()` is already on every `artifact_append` call).
- **Writer states:** `open → finalise/abort → terminal`; appends after terminal are
  refused. Host-side abort wiring: the **bridge**, not the adapter, runs a bounded
  abort epilogue in the dispatch failure/timeout path, and `plugin_close` sweeps any
  still-open writer. R2's zero-rows assertion (below) is defined against this writer.

**Honest memory bound:** until and unless the staged writer exists there is no chunk-size
bound; the design's bound is `max_capture_bytes` (operator ceiling). With the staged
writer, memory is bounded by chunk size and the store by quota — stated as the mechanism
it is, built in slice 1, not inherited.

Three pre-dispatch gates, all refusing `RESOURCE_LIMIT`/`INVALID_ARGUMENT` `not_dispatched`
**before the adapter is called** — with descriptor limits type-validated inside the gate
region so a malformed descriptor yields a clean `INVALID_ARGUMENT` refusal, never an
exception escaping `dispatch` (the existing gate region has no exception frame; a
string/negative/absent `capture_limits` must not crash the caller):

| Gate | Check | Source |
|---|---|---|
| G1 arithmetic | `waveform_f64le`: `sample_count × 8 ≤ max_bytes` | §7 (count×8 is spec *prose*, line 154 — the schema pins field presence only) |
| G2 descriptor | `sample_count ≤ capture_limits.max_samples` ∧ `max_bytes ≤ capture_limits.max_bytes`; format ∈ descriptor `capture_formats`; subscription ceiling from host `QuotaLimits` (Decision 4) | §7 *"Requests must satisfy both descriptor and host limits"* |
| G3 quota | writer allowance **checked and reserved** (decrement at gate time; refund on abort/timeout/poison); allowance = `min(max_capture_bytes, max_dataset_bytes − used)`; per-append enforcement then lives in the writer | QuotaLimits docstring; §7 |

**G4 (new): finalise-time byte validation.** Spec line 204 mandates it —
*"artifact_finalise accepts format/start time and optional waveform metadata, **validates
actual bytes**, and returns the complete captureManifest"* — and the previous revision of
this record omitted it. At finalise the host cross-checks `byte_length ==
sample_count × 8` for `waveform_f64le`, and cross-checks the manifest's `sample_count`,
`format`, and `capture_id` against the dispatch request (host-minted id echoed wrong is
refused). A lying or truncated capture is refused at finalise, never published.

**Two-sided manifest contract (named).** Host-computed fields (`byte_length`, `sha256`)
are override-proof by construction — the digest source is the store. Adapter-supplied
waveform fields (`unit`, `sample_interval_s` — mandatory per the schema's allOf and spec
line 154, arriving through the adapter's finalise metadata, the only channel that carries
them) are **validated** at finalise against the descriptor's declared waveform metadata;
a descriptor that does not declare them cannot admit a `waveform_f64le` capture.

**Permission gating (named).** Spec §8/S15: *"Only artifact_writer permission grants
these services."* Registry admission — which already owns S-checks — is the gating site:
an adapter admitted without `artifact_writer` gets no capture writer (the composing
capture-services object omits it), and a `capture` dispatch from such an adapter is
refused `not_dispatched` at the gate. `event_sink` gets the same treatment at slice 2.

**Quota context-key pinned.** The composing services object passes a **host-minted
run/session context key**, never a caller-supplied one — the caller-controlled key in the
existing evidence path is a live quota-bypass (rotating keys reset the window) and the
capture path must not inherit it.

A composing **capture-services object** implements the spec §8 shape
(`monotonic`/`utc_now`/`record_evidence`/`artifact_append`/`artifact_finalise`/
`artifact_abort`) by delegating to gateway capabilities: clocks from the host clock
(a fresh timestamp per call — never a construction-frozen `now`, the `RetainingServices`
pattern the composing object must not copy), evidence to `ContentStore.put_evidence`,
artifacts through the staged writer.
`artifact_abort` is idempotent, publishes nothing, and stays callable from inside the
adapter's own `execute` cleanup after a deadline (§8; the chain is verified end-to-end
against merged bridge code: timeout → CancelledError at the await → cooperative `finally`
cleanup → abort during unwinding → `context.cancelled` → `_failed`/unknown posture). For
non-cooperative cleanups the bridge-side bounded abort epilogue (above) is the host
guarantee. **Abort after finalise is a no-op retract** — a published capture stands; this
is pinned so an unconditional `finally: artifact_abort()` cannot unpublish.
`QuotaLimits` grows two finite fields with defaults (`max_capture_bytes`,
`max_subscriptions` — additive; `test_host_abi.py` pins HostServices *methods*, not quota
fields; construction sites in-tree are updated in the same PR).

**Slice-1 pin movements, corrected:** the real forced movements are the
`test_otdp_bridge` `UNSUPPORTED` narrowing (the supported-verb set changes consciously)
and the `QuotaLimits` construction sites (mypy-forced). The `ADAPTER_GAPS` /
`EXPECTED_CAPTURE_SERVICES` flips are slice 2 (and the "capture surface is SDK-only"
comment flip is comment-prose, not comparator-forced — the bridge never touches the
capture members).

## Decision 4 — streaming mechanism (slice 2, including the poll engine as named scope)

- `dispatch` grows `stream_subscribe`/`stream_unsubscribe` with the closed §5 argument
  sets; **subscription IDs are host-minted globally-unique uuid4 opaques** (mirroring the
  bridge's operation ids), echoed by the adapter, **never parsed by host code** — the
  bridge's registry keys on the full id only, so the format stays reversible.
- `stream_limits` enforced at G2 against **both** the descriptor's declared values and a
  host ceiling: `min_interval_ms` is a floor validated ≥ 1 and the descriptor's value is
  advisory pacing, not enforcement; `max_subscriptions` is checked against the new host
  `QuotaLimits` field — an author-claimed descriptor value alone would allow unbounded
  bridge state growth.
- **The poll loop is slice-2 construction, named.** No round-robin engine exists in the
  tree. The slice-2 poll engine multiplexes `next_event` across live subscriptions inside
  the executor's existing wait-slice rhythm: each `next_event` is bounded to one poll
  slice (mirroring the `_MonitoringClock.wait_ns` contract — deadline-sliced, tick at each
  slice boundary), and monitor ticks run between polls. A long poll is thereby never a
  monitoring blackout; the loop's shape is designed against the same §7 continuity rule
  as captures. This is mini-Option-B machinery and is priced as slice-2 scope, not
  presented as existing.
- **Event validation** against the closed `$defs/event`: kinds
  `telemetry|alarm|gap|ended`; `telemetry` requires a `reading`, the others require
  `code`+`message`; `sequence ≥ 0` and **strictly increasing per subscription** (an
  equal sequence is a duplicate and is `PROTOCOL_ERROR`); **`ended` is terminal** — any
  event after `ended` is `PROTOCOL_ERROR`; an event whose `subscription_id` does not
  match the polled subscription is `PROTOCOL_ERROR` (no cross-subscription laundering —
  the `_convert` operation-id correlation precedent, extended). Regression/non-schema/
  duplicate/after-`ended`/wrong-subscription all poison, like any protocol lie.
- **Refusal taxonomy for `next_event` (named):** unknown subscription →
  `INVALID_ARGUMENT` `not_dispatched` (clean refusal); known-but-already-`ended` →
  `INVALID_ARGUMENT` `not_dispatched`; quota exhaustion at a landing boundary → clean
  `RESOURCE_LIMIT` refusal plus subscription teardown with a host-cause `ended` marker —
  **never session poison**, because quota is a resource condition, not a protocol lie.
- **Gap honesty, host side.** Sequence regression and non-schema events are refused; a
  *forward jump without a preceding `gap`* is not protocol-refusable, so the host
  records it: the bridge flags jump-without-gap as an evidence annotation. R4 pins this
  host mechanism (not the fixture's emission duty — a control that tests only the
  adapter's cooperation stays green when the mechanism reverts, which the acceptance
  rule forbids).
- **Landing shape (specified before any telemetry flows — this is a one-way door).
  Event rows land as `event_log`-kind evidence with a content_ref carrying at minimum:**
  `{subscription_id, sequence, event kind, host_received_at, payload digest,
  capture/dataset linkage}`. Slice 3's per-stream projection groups on these fields;
  adding them after accumulation would be a data migration. `emit_event` and
  `register_reading_sink` are priced as named slice-2 components (both raise
  `NotImplementedError` today; the batch quota enforcement is new code, not wiring).
- **Quota stack (named).** Event rows consume a **kind-scoped accounting dimension**, so
  `max_evidence_entries` keeps meaning only what `retain_evidence` consumed and published
  quota history is never falsified by repricing. `max_event_batch` bounds each landing
  batch; batches land transactionally (or the partial-batch posture is disclosed —
  chosen: transactional per batch, since `put_evidence` rows are independent INSERTs
  today). Exhaustion mid-stream: clean refusal + teardown (above), never poison.
- **No hidden background task** (§8): the run engine polls inside the wait-slice rhythm;
  subscriptions live inside run lifecycles and die with the run ("No stream outlives its
  host-owned subscription authority"). Poison clears the bridge's subscription registry
  (and emits host-cause `ended` markers), so a poisoned session cannot leak live
  subscriptions until close.

## Decision 5 — #77 fetch-lane bound (absorbed): bounded-by-mechanism

The #64 position — fetch pairs count with `max_bytes`, the operative materialization
budget — is kept, and grounded in the built mechanism (Decision 3's staged writer), not
in machinery that precedes it:

- **Core lane:** G1–G4 plus the writer's per-append enforcement. The schema ceiling stays
  absent *because* the request carries its own `max_bytes` and the **built writer** never
  allocates the cap — bounded chunk appends mean an absurd `max_bytes` can only be
  refused (G2/G3) or fill the quota, never OOM the host. The #64-F1 failure shape
  (a preset baking a huge count that fetch materializes later) cannot recur: nothing
  durable bakes an unbounded count on this lane. Before the staged writer exists this
  argument is aspirational; the slice-1 PR that lands the writer lands the argument.
- **Class lane:** fetch inputs carry `max_bytes` (no count); the acquisition count was
  bounded at configure by the 1e6 ceiling — device-classes §2: *"A class bound is a
  resource backstop for the fetch lane, not an instrument capability claim."* G2/G3/G4
  apply host-side identically. No new schema ceiling. Class-lane worst case for the
  throughput measurement: complex128 (VNA) = 16 MB/fetch, twice the core-lane 8 MB.
- **`sample_rate_hz`: unbounded above, by decision, with the rationale recorded.** No
  resource term multiplies by rate: at bounded count (≤ 1e6) and fixed width, fetch bytes
  are independent of rate; duration = count/rate *falls* as rate rises, and the low-rate
  direction is bounded by the operation deadline plus honest partial datasets
  (device-classes §3). Streaming rate is governed by `min_interval_ms`, not
  `sample_rate_hz`. Two precision notes from the RedTeam, accepted: width is **not**
  fixed for `utf8_json`-encoded string variables (the bound there is `max_bytes`
  directly), and the "8 MB/fetch" anchor is core-lane only. A schema ceiling would be a
  plausibility claim needing per-class hardware evidence this design does not carry
  (#64's bar). The cheaper alternative — a non-normative SDK-side descriptor plausibility
  advisory — is recorded as **considered and declined for now**: it is an authoring aid,
  not a resource bound, and belongs in the authoring-procedure train if wanted.
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

**The mitigation is permanent, not a review pass.** The confusion audience is gateway
contributors and guide readers (adapters conform structurally and never import the
gateway protocol), so the load-bearing mitigations are: cross-naming docstrings **plus a
standing device-developer-guide glossary entry**, and scaffold/guide examples must never
present the two `HostServices` as one concept (scaffold output is an interface — SRF-1 —
so the generated text is where the collision would calcify).

## Decision 7 — contributor comment on capture-event storage: BLESS-AS-AMENDED

| Point | Disposition | Evidence |
|---|---|---|
| Host-managed storage; host issues capture ID + writer allowance | **Bless** — already normative | §7; §8 *"The host supplies a monotonic clock … scoped transport and optional capture writer"* |
| Per-artifact SHA-256 + length bound in a manifest | **Bless** — it is the existing `payload_finalise` contract, which *"computes and returns the artifact object (ID, encoding, byte length, SHA-256)"*; the prototype's delta (it has `size_bytes`, no digest) is precisely this | extension-contract §3 |
| "A capture event groups multiple files" under one ID | **Amend.** In the dataset lane, grouping exists today: one dataset manifest carries per-variable artifacts each with its own `{id, sha256, byte_length}` (measurement-model §1–2, M11) — the grouping key is `dataset_id`. In the **core lane the manifest is closed single-artifact**; grouping there is a corpus revision, refused in these slices | `$defs/captureManifest` (`additionalProperties: false`) |
| Three artifact classes (primary / manifest / derived renderings) with different lifecycles | **Amend.** At publish time every admitted artifact is integrity-bound identically; the classes are **retention-time selectors** and land with the retention slice (Decision 8) as policy selectors, not as a capture-layer concept | — |
| VCD + rendered graphs as artifacts | **Amend.** VCD is a container format → *"Compression/container formats require an explicit new encoding contract"* (measurement-model §2); a logic capture's primary in-model form is `digital_trace`/`logic_u8`. Renderings are regenerable and are **not admitted to the artifact store at all** — stricter than "cache at most" (Owner call 3) | measurement-model §2 |

**Renderings footnote (added).** "Regenerable" is version-conditional: regeneration is
bit-identical only under the pinned evaluator version, and the run record pins document
digests, not the evaluator's. Two rules follow: (a) **promote-on-demand** — a rendering
that becomes decision-input is admitted as evidence at that moment (the only promotion
path, and it is deliberate); (b) the version-dependence is disclosed in the guide's
rendering section. Separately, deferral row 2's trigger is re-examined at slice-2 merge
with the contributor's own migration comment in hand — it arguably satisfies the trigger
today, and the re-examination is scheduled, not left to chance. The grouping model's
**first shipping home is standalone mode** (Decision 9); the dataset lane remains its
corpus home.

## Decision 8 — retention & reporting: report first, dispose never (until audited)

- **Slice 3 = the reports, read-only.** A retention/disposal view mapping each
  capture/dataset to its governing policy and disposal date (or `held`/permanent), plus
  the storage-growth projection (per-stream byte rate × duty × window), as a CLI
  projection over the content store — recomputed each run from current policy, never
  cached dates. The indefinite/hold tier is what makes the projection load-bearing
  (issue §8–§9), and it exists because quotas (`max_dataset_bytes`) still bound the
  unbounded-retention case.
- **Standing rule (new): slice 3 writes nothing back.** Pure projection — no data-class
  stamps into durable rows, no cached disposal dates, no write-back of any projection
  result. The moment classification is stamped into durables, any later corpus
  data-class restructure becomes a reclassification migration and the slice flips
  one-way. `retain_after: last_access` policies are fictional until the store durably
  tracks access times (an acceptable, bounded column backfill if wanted later);
  policies referencing it before that tracking exists are a validation error.
- **Join key (named).** Per-data-class selectors group on a classification **computed at
  report time** from landed fields (format/kind mapping for the core lane; the dataset
  lane's declared kinds for the dataset lane) — never a landing-time stamp the closed
  `captureManifest` cannot carry.
- **Quota-wedge disclosure (new).** Between slice 3 and the audit-trail slice, a
  hold-heavy bench that fills quota is hard-blocked (G3 refuses new captures) with no
  deletion path — that wedge is accepted and **disclosed** here, and the projection
  includes **time-to-quota-exhaustion** per project so the operator sees it coming. The
  named remediation at exhaustion: raise quota, or wait for the audit-trail slice — the
  operator choice is manual by design until disposition is auditable.
- **Byte accounting note (new).** Content addressing (`INSERT OR REPLACE` on
  `art-<digest>`) means byte-identical captures share one artifact row; sum-of-manifests
  accounting double-counts. The projection derives from the artifact table (source of
  truth), so dedup **under**-counts storage — the honest direction — and the report
  labels the method.
- **Clock (new).** The composing services object stamps a fresh host timestamp per call;
  `RetainingServices`' construction-frozen `now` is a pattern the capture path must not
  inherit, and the slice-3 report computes from per-row `stored_at`, which is only
  meaningful under the live clock.
- **Policies:** declarative, schema-validated, composed of the admitted primitives
  (`duration`, `retain_after` ∈ {`last_access`,`run_end`,…}, `on_disposition` ∈
  {`delete`,`archive`,`review`}, `hold`, data-class selectors) — the issue's Option A.
  First home: gateway-local validated configuration; corpus promotion only on trigger
  (row 7).
- **Sequencing invariant:** no automated disposition ships until the disposition audit
  trail exists. Slice 3 deletes nothing; a disposal decision is a report row until the
  audit trail slice lands after it.
- **Granularity:** global default + per-data-class in slice 3 (per-bench is a natural
  key and comes free). Per-project is **resolved: not in #43** (Owner call 1).

## Decision 9 — standalone capture mode: plugin-local, hostless (slice-1 scope, added by Amendment 2)

Plugin and device development — and bench testing — happen on machines that never run
the gateway. The contributor's own prototype (one `stem` per capture event: primary
artifact + sidecar metadata + renderings) is exactly this mode, and #43's capture path
as previously written was host-driven end to end, leaving it unserved. Slice 1 adds the
standalone leg:

- **Same shape, second backend.** The SDK ships a standalone implementation of the
  existing `CaptureServices` protocol (`artifact_append`/`artifact_finalise`/
  `artifact_abort` — verified in `interfaces.py`; additive SDK code, the normative
  interface shape is unchanged, no corpus byte moves). An adapter written against
  `CaptureServices` runs unchanged against either backend: the gateway's composing
  object (Decision 3) or the standalone file writer.
- **Where data lives.** Default: `captures/` under the plugin directory. Configurable,
  precedence named once: explicit constructor argument > `BENCHWEAVE_CAPTURE_DIR`
  environment variable > the plugin-directory default. The gateway never reads this
  configuration — host-managed storage stays normative in-gateway, and standalone path
  selection exists only outside the gateway boundary.
- **Layout and manifest parity.** Each capture event is one directory keyed by
  `capture_id` (the "stem"). The directory tree, pinned:

  ```
  <capture-root>/                  # captures/ under the plugin dir, or BENCHWEAVE_CAPTURE_DIR
  └── <capture_id>/                # one capture event
      ├── manifest.json            # fixed name; integrity + metadata for the event
      ├── staging/                 # chunk files during capture; removed at finalise
      ├── <capture_id>.<ext>       # primary artifact; ext from the format
      │                            #   (waveform_f64le → .f64, raw_binary → .bin)
      └── renderings/              # optional; plugin-written ordinary files
  ```

  `manifest.json` carries the gateway-manifest integrity fields — real per-artifact
  SHA-256 + byte_length computed at finalise over the actual bytes (the prototype's
  missing-digest gap, closed) — plus `capture_id`, `format`, `state`
  (`finalised`), `started_at`, and waveform metadata when applicable. Staging chunks
  live under `staging/` so a crashed capture is distinguishable from published data;
  finalise concatenates staging into the primary artifact and removes `staging/`;
  **abort removes the event directory entirely** (standalone is development tooling —
  no forensic marker is required, unlike the gateway's abort-marker evidence row).
  Renderings live in `renderings/` so the three-class split (Decision 7) is visible
  in the tree: the contributor's capture-event grouping model realized where it
  genuinely lives — standalone, where no store exists to admit or refuse renderings.
- **Integrity is not optional standalone.** At publish, everything is integrity-bound
  identically (Decision 7's rule) in both modes: digest over real bytes, length over
  real bytes, abort leaves zero chunk residue.
- **Writer semantics mirror the gateway writer where mode-independent:** writer states
  `open → finalise/abort → terminal`; appends after terminal are refused; cancellation
  honored at append (`is_cancelled()` is already on the SDK context); one capture in
  flight per services instance (§8).
- **Boundary (crisp).** Standalone mode never runs in-gateway; the bridge and the
  composing capture-services object never read `BENCHWEAVE_CAPTURE_DIR` or any
  plugin-local path configuration. No automatic import of standalone captures into the
  gateway — ingest is a separate, deliberate path (likely riding the dataset lane,
  deferral row 2, where the grouping model's corpus home already exists).
- **Acceptance:** R9 below. **Guide obligation:** the device-developer guide's capture
  section documents standalone mode (default location, path configuration, manifest
  layout).

## §11 open questions — resolved or deferred

| Item | Disposition |
|---|---|
| Video / continuous capture | **Defer** (row 4): `image` kind exists; no camera control profile; segmented acquisition explicitly unstandardized (measurement-model §5); codec/container needs a new encoding contract. It is the retention stress case, which slice 3's projection surfaces without standardizing video. |
| Derived quantities / virtual channels | **Resolved, no action:** standardized since 0.2.0 — `derived_variables` + grammar + M15/S19 (measurement-model §8), evaluator in-tree (`measurement/derivation.py`). Ad-hoc gateway-side expressions remain excluded by the execution contract, as the issue notes. |
| Retention granularity | **Resolved for slices:** global + per-data-class (+ per-bench); per-project resolved out (Owner call 1). |
| Disposition audit trail / archival tier | **Defer** (row 3), gated before any automated disposition (Decision 8). |
| Buffering (in-memory vs spooled) | **Resolved by built mechanism:** slice 1 builds the staged-append writer (Decision 3) — memory bounded by chunk size, store bounded by quota, staging reclaimed on abort and by the crash-recovery sweep. Before that build lands, the honest bound is `max_capture_bytes`; the record previously claimed the strong bound as if inherited — corrected. |
| Transport providers (UVC / vendor SDKs) | **Defer** (row 6): separately reviewed host-provider contracts (extension-contract §6 says so verbatim). |
| Multi-device concurrency & time correlation (issue §6) | **Concurrency resolved in Decision 1:** slices 1–2 ship a single-threaded, globally serialized engine — N bridges are orchestrated sequentially, and captures can never overlap in time, which makes the §6 posture safe for a reason now stated. **Time:** per-capture `started_at` and manifest timing are already normative (`$defs/captureManifest`), and §5's rule stands — sharing an acquisition ID or a time axis does not prove cross-device synchronisation. Full per-channel timing (offsets, skew uncertainty) is measurement-model content riding the deferred dataset lane (row 2). Nothing in slices 1–3 assumes synchronisation. |

## Minimal first increment and slice order

1. **Slice 1 — core capture** (Decision 3): gates G1–G4, the staged-append store writer
   (migration, staging lifecycle, recovery sweep, accounting) as a designed component
   with its own tests, composing capture-services object over it (+ `max_capture_bytes`
   and `max_subscriptions` quota fields with defaults), `dispatch(capture)` with manifest
   conversion and the G4 cross-checks, abort semantics incl. host-side epilogue and
   close/poison sweeps, permission gating at registry admission, capture-deadline
   derivation policy, **the standalone capture services (Decision 9) as the slice's
   SDK-side leg** (new additive module in `benchweave-sdk`; SDK commit + push first,
   gateway pointer after — TWO-1), docstring amendment, **and the monitor-gap
   measurement** (Risk 1's slice-1 quantities).
2. **Slice 2 — streaming** (Decision 4), including the poll engine as named scope.
3. **Slice 3 — retention reports** (Decision 8).

One RED→GREEN slice per commit; working branch, PR, double review; gates
(`uv run pytest`, `ruff check .`, bare `uv run mypy`) before each commit. Each merged PR
opens at most one follow-on issue.

## Pre-committed acceptance rule (for the implementation PRs — a floor, extensible)

Written before any implementation number exists; amended in Amendment 1 with R5–R8. All
controls must (a) pass with the mechanism present and (b) **fail when only the mechanism
is reverted** — the reviewer reverts the mechanism commit and watches red, restores and
watches green. Any control failing in (a) kills the slice; a control that stays green
under (b) does not test the mechanism and must be fixed before merge. No underpowered
mode applies. **The rule is a floor:** any control review adds (from this record's
findings or build-time discovery) meets the same absence-presence standard before merge.

- **R1 (bounds before device):** a capture violating G1 (and G2/G3 variants — including
  malformed descriptor limits, which must yield clean `INVALID_ARGUMENT`, never an
  escaping exception) against an admitting descriptor returns
  `RESOURCE_LIMIT`/`INVALID_ARGUMENT` `not_dispatched` with a spy adapter recording
  **zero** `execute` calls.
- **R2 (abort-not-published):** an adapter that appends bytes then raises post-dispatch
  leaves **zero published artifact rows**, zero staging rows (the writer's reclaim
  asserted directly), exactly one host-written **abort-marker evidence row** (aborted
  captures stay forensically visible), and the result is `unknown`/`error` with
  `dispatch_state` `dispatched|unknown`. Host-side abort wiring (failure path + close
  sweep) is the mechanism under test — not the adapter's own cleanup.
- **R3 (host-computed integrity + count honesty):** the manifest's `sha256`/`byte_length`
  equal the host's recomputation over `artifact_read` chunks; an adapter-supplied wrong
  length is ignored; **a short-writing adapter (declared `sample_count` exceeding
  delivered bytes) is refused at finalise by G4**; a manifest echoing a wrong
  `capture_id`/`format`/`sample_count` is refused. Zero-byte finalise exercises the
  eof-on-first-read path and is refused for `waveform_f64le` by G1 arithmetic.
- **R4 (stream honesty, host mechanisms only):** a non-monotone sequence (including an
  **equal duplicate**) is `PROTOCOL_ERROR`; an event **after `ended`** is
  `PROTOCOL_ERROR`; an event with a mismatched `subscription_id` is `PROTOCOL_ERROR`;
  after a simulated drop, the **host's** jump-without-gap evidence annotation is present
  and the row shape of Decision 4's landing contract is asserted (`subscription_id`,
  `sequence`, kind, `host_received_at`, payload digest, capture/dataset linkage).
- **R5 (cancellation mid-capture):** a capture cancelled at its deadline mid-append
  leaves zero published artifact rows, zero staging rows, `unknown` outcome with the
  poison posture — and the cancellation control asserts the bridge's bounded abort
  epilogue ran (staging reclaimed) without depending on adapter cooperation.
- **R6 (non-cooperative cleanup is bounded):** an adapter whose cleanup never yields
  cannot wedge dispatch longer than the bridge's abort-epilogue timeout; `plugin_close`
  completes and the session reaches its failed posture deterministically.
- **R7 (cross-session isolation):** an adapter appending to another session's
  `capture_id` is refused (writer keyed per session; echo correlation at finalise).
- **R8 (permission gate):** an adapter admitted without `artifact_writer` gets no
  capture writer and a `capture` dispatch is refused `not_dispatched` before any writer
  exists; the negative path is asserted, not just the positive.
- **R9 (standalone integrity parity):** the standalone writer's finalise manifest digest
  equals recomputation over the published artifact file; `artifact_abort` leaves zero
  chunk residue on disk; appends after terminal are refused; a cancelled append writes
  nothing; and the standalone manifest carries the same integrity fields as the gateway
  manifest, so one adapter's capture is structurally identical in both modes.

## Invariant and cross-surface impacts

- **STD-1/2/3/5:** untouched in slices 1–3 — no vendored byte moves,
  `sync-standards --check` stays green. **TWO-1 now applies at slice 1:** the standalone
  capture services (Decision 9) are an additive SDK module — no interface shape change,
  no corpus change — landing as an SDK commit + push with the gateway pointer advancing
  after. Slices 2–3 change no SDK surface (`CaptureServices` is already vendored in
  `interfaces.py`).
- **Slice 1 adds one store migration** (the staging table) — in the gateway's own
  versioned migration sequence, with the recovery sweep; this is new scope named by
  Amendment 1, previously unstated.
- **Pins that move, main-side:** `tests/unit/test_otdp_bridge.py` — the `UNSUPPORTED` pin
  narrows to the still-refused verbs (slice 1); `QuotaLimits` construction sites update
  (fields have defaults; mypy-forced, same PR). `tests/sdk/test_adapter_agreement.py` —
  `ADAPTER_GAPS` loses `next_event` and the capture-surface comment flips at **slice 2**,
  when the bridge actually calls `adapter.next_event`. `tests/contract/test_host_abi.py`
  — unchanged (methods-only pin; quota fields are free). `tests/integration/test_otdp_loading.py`
  — unaffected.
- **Interface corpus:** no new operation in slices 1–3 (captures run inside runs;
  artifacts already served by `stg_v1_artifact_read`). Row 5 carries the exposure case.
- **Dataset lane (deferred):** SDK `interfaces.py` grows `dataset_publish`/`payload_*`
  then — SDK commit first, pointer after (TWO-1), user-guide + AI-GUIDE obligations per
  drift-and-obligations items 1–2.
- **CI cost:** none new; R1–R8 are plain pytest.

## Top risks and what falsifies this design

| Risk | Falsifier |
|---|---|
| **Monitoring blackout during captures** (promoted from an unnamed consequence to the top risk): trip latching, cancel detection, and lease-loss detection freeze for the capture duration | Slice-1 measurement: monitor-gap duration during a deadline-max capture vs bench poll cadence; protective-action latency on a capturing bridge. If the gap exceeds policy bounds → capture-deadline policy tightens or Option B evaluates early (row 1) |
| Queued-run delay behind long captures (the sequential model's second cost) | Same slice-1 measurement, queued-run axis; feeds the same row-1 evaluation |
| sqlite single-writer end-to-end append + serving throughput (adapter → services → store → commit under `synchronous=FULL`, fsync per commit) including the serving path (`artifact_chunk` recomputes the full-blob digest per window — the artifact row should carry the stored digest so reads stop re-hashing; named as a slice-1 writer option) and the evidence `COUNT(*)` quota's O(rows) scan | Slice-1 throughput measurement at the 16 MB class-lane worst case (complex128) and the 8 MB core-lane case; below budget → spooling design (row 8) |
| Two same-named `HostServices` protocols confuse authors | Permanent mitigation: docstrings + guide glossary + scaffold rule (Decision 6); docs-coverage review verifies at slice 1 |
| Retention report projecting from stale policy or stale stamps | Report recomputes; live clock mandated (Decision 8); no cached dates or stamps anywhere |

## Deferrals — every row carries carrier and reopen trigger

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| 1 | Option B native async host | Follow-on issue opened at slice-1/2 merge (one issue — pre-scheduling a successor issue is a sequencing choice, owned) | Slice-1 measured quantities breach policy: monitor gap or queued-run delay beyond the capture-deadline policy bound, or the slice-2 poll engine cannot hold poll-slice contracts. (The prior invented thresholds — >2× median, ≥3 bridges — are withdrawn; a deferral trigger measured against nonexistent concurrency cannot fire honestly) |
| 2 | Dataset/invoke lane (invoke dispatch, `dataset_publish`/`payload_*`, SDK interfaces) | Separate issue at slice-2 merge (existing queue if one already carries it) | First class-profile plugin needing multi-channel/typed capture from the gateway — **re-examined at slice-2 merge with the contributor's own migration comment in hand, which arguably satisfies the trigger already** |
| 3 | Automated disposition + audit trail (+ archival tier) | Documentation here; issue at slice-3 merge | Slice 3 (reports) merged — audit trail is the next slice, and no automated deletion may precede it |
| 4 | Video/continuous capture; VCD/codec encoding contracts; camera profile | Documentation here | A concrete video/image-capture requirement from a real project (unnamed here by policy) |
| 5 | Interface-corpus exposure of capture/telemetry (new MCP operations) | Documentation here | A caller needing capture or live telemetry outside the run engine |
| 6 | Transport providers (UVC, vendor SDKs) | Documentation here | A device class in scope whose transport is not one of the scoped primitives |
| 7 | Retention-policy schema corpus promotion (execution package) | Documentation here | A policy needing to travel with a package or bench definition |
| 8 | Host-side spooling for large captures | Documentation here | Risk-3 throughput measurement below budget |
| 9 | Run-engine capture driving (activation wiring: constructing real bridges with capture-services over the worker-thread store, procedure-step shape for capture verbs) | Issue at slice-2 merge | First real capture-class plugin — without it #43 ships capability-without-activation; the tracker must own that gap |

## Owner calls on the forks (resolved 2026-09-21)

All four forks went to the owner with recommendations; all four recommendations were
agreed the same day. They are decisions of record, and the implementation slices
inherit them:

1. **Per-project retention — resolved: global + per-data-class (+ per-bench) now.** No
   project entity is introduced inside #43; one arrives only when more than retention
   wants it.
2. **Retention-policy home — resolved: gateway-local validated configuration.** Corpus
   promotion stays row 7's trigger.
3. **Derived renderings — resolved: none admitted to the artifact store.** Gateway-served
   renderings would need a new non-evidence artifact class (corpus-adjacent); not taken
   here.
4. **Telemetry surface — resolved: run-internal only.** Caller-facing subscription reads
   stay with row 5's interface-corpus train.

## Amendment 1 — RedTeam integration (2026-09-21)

Twelve source-grounded adversarial analysts (3 concurrent × 4 waves) attacked the merged
record; every finding was verified against code by its reporting analyst and reconciled
by convergence before integration. Converged core: the phantom chunked-append writer
(confirmed by 10 analysts) and the false coordinator concurrency (6+). **Changed in
place:** Decision 1 (serial model disclosed; capture deadline policy added; measurement
moved to slice 1; Option-B trigger re-anchored to measurable quantities); Decision 3
(staged writer designed in full — staging table, state marker, recovery sweep, byte
accounting, writer states, host-side abort, close sweeps; G4 finalise validation added
per spec line 204; G3 reservation + allowance formula; two-sided manifest contract;
permission gating; context-key pinning; live clock; abort-after-finalise pinned;
malformed-descriptor exception safety); Decision 4 (poll engine named as slice-2 scope
with poll-slice contracts; landing shape specified; subscription-id scope; quota stack
with kind-scoped ledger and transactional batches; strictly-increasing monotone;
`ended`-terminality; echo correlation; refusal taxonomy; `max_subscriptions` ceiling;
poison-clears-subscriptions); Decision 5 (bound re-grounded in the built writer; 16 MB
worst case; utf8_json width note; advisory recorded as declined); Decision 6 (permanent
mitigations: glossary + scaffold rule); Decision 7 (promote-on-demand + version-
dependence; row-2 trigger re-examination); Decision 8 (pure-projection standing rule;
join key; wedge disclosure + time-to-exhaustion; dedup-aware accounting; live clock);
acceptance rule extended to R1–R8 with the floor statement; risks reordered
(monitoring blackout first); deferral row 1 trigger re-anchored, row 9 (activation)
added; pin movements corrected; §0 corrected (whole-blob store, single-threaded
coordinator, presence-only allOf, zero-hits inventory, citation slips). **Left standing
(verified sound):** all corpus citations, the content-addressed integrity core, host-
minted IDs, the abort-after-deadline chain, the R-control shape, the unbounded
`sample_rate_hz` rationale, report-first retention, the two-lane split, slice 3's small
scope. Verdict after integration: the record is implementable as written; slices 1–2
are construction (named as such), not wiring.

**Amendment 2 (2026-09-21): standalone capture mode (Decision 9).** Principal
directive: account for standalone plugin/device capture — development and bench testing
without the gateway — with data under the plugin directory by default and a configurable
path. Added Decision 9 (same `CaptureServices` shape, filesystem backend, default
`captures/` under the plugin dir, `BENCHWEAVE_CAPTURE_DIR` override with named
precedence, manifest parity with real digests, crisp in-gateway boundary, no automatic
ingest) and placed it in slice 1 as the SDK-side leg. Acceptance rule gains R9
(integrity parity); slice 1 now carries an additive SDK module under TWO-1 (SDK commit
+ push first, gateway pointer after); Decision 7 notes the grouping model's first
shipping home is standalone.
