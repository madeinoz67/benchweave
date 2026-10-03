# GW-22 follow-up — populate device-page reading tiles from retained observations (issue #369)

**Verdict: OWNER_FORK — recommend adopting shape (1), the evidence join, and building
slice 1 as specified here.** Triage call: mechanisms, issue numbers and code paths only —
public path as named.

**Evidence baseline:** gateway `origin/main` `c183db4` (2026-10-03), read in worktree
`.wt/i369-6101` off branch `feat/issue369-reading-tiles`. Open sibling PRs on the shared
surface: #371 (G2a folds) and #372 (G2b folds — includes the GW-22 addendum that filed
this issue); SDK #98 (I2b) touches the standalone host, not the gateway device page.

The fork the owner owns: the issue's reopen trigger reserves "shape (1) vs (2)" to the
owner. Reading the code makes that call one-sided (§3): shape (2) is not buildable in a
UI lane at all — the project's own decision record already ruled it an interface
capability change to be raised as an interface issue, never a UI route. What remains a
genuine owner call is whether evidence-grounded (non-live) tiles satisfy GW-22's intent,
or whether the owner prefers to keep tiles conservative and file the interface issue for
a live sample-bearing read instead. Options with recommendation in §12.

## 1. Premise check (verified against the code, not assumed)

Everything below was read at `c183db4`; `file:line` anchors may drift, symbol names win.

- **The tiles today** render `Unavailable` by construction:
  `PresentationTile` defaults (`src/benchweave/interfaces/ui_presentation.py:107-116`)
  and `_tiles_for_page` (`ui_presentation.py:292-323`) build one tile per bound
  observation target's `axis_role == "value"` variable with value `Unavailable`,
  quality `unknown`, freshness `Unavailable`, verdict `no-verdict`. No optimistic copy
  exists anywhere (GW-22's no-fabrication half, pinned by the G2b suite).
- **The staleness predicate is wired and waiting**: `reading_staleness = staleness`
  (`ui_presentation.py:49-52`) re-exports `packages/ui-html/.../staleness.py::staleness`
  — the §B.4 ST-2 boundary predicate, pure, over `(freshness_ms, max_age_ms)`. ST-1
  fixes where `max_age_ms` comes from: *the polled parameter's own declaration in the
  device descriptor* ("host-supplied configuration from the descriptor/profile, never
  invented, never a renderer default" — `docs/internal/ui-contract.md:184`).
- **The tile's parameter identity is declared and validated**: an observation target in
  the binding catalogue carries `parameter_id` (`standards/plugin-ui/0.3.0/ui-manifest.schema.json:604,640`;
  admission validates `target["parameter_id"]` against the descriptor's parameters map —
  `presentation/contracts.py::_target_findings`).
- **What retained observations actually exist, keyed how** — the load-bearing findings:
  1. **The ONLY durable, schema-validated, parameter-keyed observation carrier is the
     telemetry event lane.** Telemetry events carry the full seven-field reading
     (`parameter, value, unit, observed_at, age_ms, quality, source` — validated at the
     boundary by `host/otdp_bridge.py::OTDPBridge._event_reading`, `otdp_bridge.py:1220`)
     and land transactionally as evidence kind `"event_log"`
     (`content/stream_services.py:78` `EVENT_KIND`, `land_events` at
     `stream_services.py:303-373`) with a reference carrying
     `subscription_id/sequence/kind/host_received_at/capture_id/dataset_id`, the event
     JSON as a content-addressed artifact, under context key `run:<run_id>`
     (`interfaces/app.py::build_run`, `context_key = f"run:{run_id}"` — one key shared
     by every device in the run).
  2. **Executor read-step values are NOT retained.** The durable run-step event envelope
     is `{occurrence, kind, resolved_input_sha256, operation_id, status, dispatch_state}`
     (`control/executor.py::_new_event`, `executor.py:855-867`) — the value stays in
     scope for pointer resolution only. A tile therefore cannot join to "the last read
     the executor performed", no matter what the join does. This is the honest limit of
     shape (1) and must be disclosed on the page, not papered over.
  3. **Monitor snapshots are retained but are not contract-shaped for this join.** Every
     monitor tick retains a bench-signal snapshot
     (`control/coordinator.py:610-618`, `read_signal_values` in
     `control/protection.py:109-182`) as kind `"dataset"`
     (`content/store.py::RetainingServices.retain_evidence`) — but the serialization is
     `json.dumps(..., default=str)`, so each `SignalValue` dataclass lands as its
     `repr()` string, invalid readings carry a placeholder `0.0`, and the age semantics
     are the protection window, not the descriptor's ST-1 window. Parsing dataclass
     reprs is a defect pattern, not a contract. Deferred (§7 D2), not joined here.
- **The bench→runs hop exists at store level, read-only**:
  `state/store.py::Store.list_run_states(bench_id)` (`store.py:822`) — every queue-state
  row for one bench. The seam itself has NO run-list-by-bench operation (the 12 read
  operations are gateway_info, bench_list/get, device_list/get, document_get, run_get,
  run_find, events_get, evidence_get, artifact_read, change_get), and `run_get`'s
  projection is closed at seven fields with the terminal record as a bare doc-ref
  digest (`operations.py::_run_projection`, `operations.py:1611-1656`).
- **The seam cannot enumerate evidence**: `evidence_get(identity, evidence_id)` requires
  an id the wire never hands out (`operations.py:463-474`), and `artifact_read` likewise
  needs an artifact id. **This corrects the issue's own stated mechanism**: "an evidence
  join … (`evidence_get`/`artifact_read` over the bench's runs)" is not constructible
  through the seam. The join must be a composition-time store read — which HAS
  precedent: `compose_device_presentation(content, descriptor_raw)` already reads the
  ContentStore directly for admitted documents (`ui_presentation.py:63-101`), ruled in
  the G2b review ("the presentation resolution reads the admitted-document store the
  same admission wrote"). Slice 1 extends that same composition-time, read-only,
  store-read posture from admitted documents to retained evidence artifacts, and names
  the boundary in CON-5 (§9) so it is a ruled surface, not a drift.
- **Artifacts are content-addressed with the digest in the id**:
  `put_artifact` mints `art-<sha256(data)>` (`content/store.py:127-134`), and
  `artifact_chunk(id, 0, n)` returns the window plus the sha256 of the WHOLE artifact
  (`store.py:136-165`) — so a composition-time read can verify the exact bytes it
  trusts, at the admission identity (the PR #372 H2/H3 discipline).

## 2. What GW-22 asks, restated against the code

PRD 12 GW-22 (`docs/implementation-planning/12-gateway-web-ui-prd.md:183`): "Readings
are observations. A tile updates only from gateway-reported state, never from a
submitted value (`reading-tile` row: no optimistic copy). Set evidence renders only when
the gateway observed it (§E.3)." Retained run evidence IS gateway-reported state — the
G2 design record's own §1 finding said exactly this ("observations the gateway already
made (run evidence, datasets) rendered as reading tiles"); the G2 build shipped the
conservative half and deferred the wiring (record §9 D4, PR #372's F4 addendum, this
issue).

## 3. The two shapes, weighed against the real read paths

**Shape (1) — evidence join at composition time.** Feasible, precedent-backed, and
satisfies GW-22/GW-23 without moving one interface byte. Every hop exists: bench→runs
(`list_run_states`), run→device filter (the run's stored binding document decodes
role→device_id — `get_run(run_id)["binding"]`, `state/store.py:371-391`, binding shape
at `control/binding.py:38-42,84-101`), evidence per run (ONE new read-only
ContentStore query — rows by context key, newest-first), parameter join
(`target.parameter_id` ↔ telemetry `reading.parameter`, both already validated against
the same descriptor parameters map), staleness inputs (observed_at from the reading,
`max_age_ms` from the descriptor's parameter declaration per ST-1), digest verification
(artifact id = `art-<sha256>`). One new module + one store query + one wiring change.

Its honest limits, disclosed on the page rather than hidden: only parameters whose
plugin subscribes and streams telemetry populate; executor read values never do (§1.2);
tiles render "retained observation of run R, observed at T — stale" semantics, which
outside a live run is usually stale — and ST-2 says that verdict is CORRECT, not
broken.

**Shape (2) — a sample-bearing observation read on interface 0.1.x.** Not buildable
here, by the project's own ruling twice over: the G2 record §9 D4 ("a live sample
stream is not an interface 0.1.0 capability … that is an interface capability change (a
sample-bearing observation read), raised upstream, not built as a UI route") and the
interface's frozen-contract discipline (A13/CON-5: behavior is pinned against
`standards/interface/0.1.0/interface-contract.md`; a new operation means an interface
version train — standards bytes, the governor mandate, the SDK twin, parity — a
different arc with its own issue). It is also not merely an interface change: the host
has no idle observation-read mechanism (reads happen inside runs through the executor,
or as bench-signal monitoring inside runs), so a live "observe now" surface needs host
mechanism design that touches A02/A03 commissioning questions. Shape (2) remains what
D4 said: an interface issue, filed if and only if the owner wants live tiles after
seeing shape (1)'s honest limits.

**Recommendation: shape (1).** It is the only mechanism that can land in this lane, it
extends proven in-tree mechanisms at every hop, and it converts the device page from a
wall of `Unavailable` into an evidence-grounded view whose every rendered number is
digest-verified gateway evidence. Shape (2) stays a filed-or-not owner call (§12).

## 4. The mechanism (slice 1)

New module `src/benchweave/interfaces/ui_readings.py`, the sibling discipline of
`ui_presentation.py` — pure composition, no route, no session logic:

```python
@dataclass(frozen=True)
class RetainedReading:
    parameter: str
    value: str | float | int | bool        # finite scalar, exactly as landed
    unit: str | None
    observed_at: str                        # the reading's OWN stamp (GW-23)
    age_ms_at_land: int
    quality: str                            # valid | stale | invalid
    source: str                             # device | cache | commissioned
    run_id: str
    stored_at: str

def latest_retained_readings(
    store: Store, content: ContentStore, *,
    bench_id: str, device_id: str,
    sibling_parameter_owners: Mapping[str, int],   # parameter -> #devices declaring it
    now_epoch_ms: int, scan_rows: int,
) -> dict[str, RetainedReading]
```

The join, newest-first and budget-bounded:

1. `store.list_run_states(bench_id)` → runs; order by `updated_at` descending
   client-side (the method orders by run id; the table is per-bench and small).
2. For each run newest-first: `store.get_run(run_id)["binding"]["bindings"]` → the
   bound device ids; skip runs that do not bind this device. Tombstoned runs are not
   skipped (their evidence is retained truth).
3. New read-only ContentStore method `evidence_rows_by_context(context_key, *, limit)`
   — `SELECT evidence_id, kind, content_ref_json, artifact_id, context_key, stored_at
   FROM evidence WHERE context_key = ? AND kind = 'event_log' ORDER BY stored_at DESC,
   rowid DESC LIMIT ?`. (Precedent for the shape: the retention/report CLI reads the
   same columns by raw SQL — `cli/retention.py:488`; composition gets a typed method
   instead of SQL in the interface layer.)
4. Filter rows whose `content_ref` carries `kind == "telemetry"` (plugin
   `record_evidence` rows land the same evidence kind with a bare `{id, version,
   sha256}` doc-ref and no telemetry fields — excluded structurally).
5. Read the artifact in one chunk (`content.artifact_chunk(artifact_id, 0,
   MAX_CHUNK_BYTES)`), **verify `sha256(payload) == content_ref["sha256"]`** and that
   the admission identity `art-<sha256>` matches the row's artifact id; on any mismatch
   skip the row (never render, never crash).
6. Parse the event JSON; take `event["reading"]`; validate it with the SAME validation
   the landing lane used — call the bridge's own reading validator
   (`OTDPBridge._event_reading`) and skip on `InvalidEvent`. No weaker local copy: a
   validation that drifts from the landing lane is the fabrication seam this design
   exists to close. (Exact import shape is the builder's call — direct use or a
   module-level wrapper re-exported next to it — the constraint is one validator, not
   two.)
7. **Attribution rule**: a reading populates THIS device's tile only when
   `reading.parameter == target.parameter_id` AND the run binds this device AND
   `sibling_parameter_owners[parameter] == 1` (the parameter is declared by exactly one
   device on the bench — the count comes from ONE seam call, `device_list`, whose
   CON-10 projections carry parameter names; computed once per render). On ambiguity:
   no attribution guess — the parameter yields no reading for this render (A7).
8. Recency is the OBSERVATION's own timestamp, not run order (GW-23's spirit): among
   candidate readings for a parameter, the one with the newest `observed_at` wins.
9. Stop early when every tile parameter has a reading, or at `scan_rows` decoded
   artifacts — whichever first. `scan_rows` is a service parameter in the
   `app_entry._LIMITS` class (env-overridable, fail-loud parse), not a bench envelope
   (A02 governs bench hazards, not page-composition budgets).

Population — a pure function over the frozen state, `ui_presentation`'s contract
untouched:

```python
def populate_tiles(state: PresentationState, readings: Mapping[str, RetainedReading],
                   descriptor: Mapping[str, Any], *, now_epoch_ms: int) -> PresentationState
```

For each tile, look up `readings[target.parameter_id]`; when present, set
`value = str(reading.value)` (rendered with the tile's declared unit; the reading's own
unit must agree — on disagreement the tile renders the reading's unit and the mismatch
is a validator finding class, not silent), `quality = reading.quality`, `freshness =
reading.observed_at` (rendered), and `stale_verdict = reading_staleness(freshness_ms,
max_age_ms)` where `freshness_ms = now_epoch_ms − parse(reading.observed_at)` and
`max_age_ms` comes from the device descriptor's own parameter declaration (absent ⇒
`None` ⇒ `no-verdict`, ST-3 — never invented). The provenance line the tile row already
supports (`freshness`) carries `observed_at`; the page states the tile's source class
("retained observation from run {run_id}") so a stale retained value never reads as a
live reading.

Wiring — minimal, three hunks:
- `create_app` passes the `Store` handle into `build_ui_router` (it owns both stores
  already; `register_read_pages` currently receives only `operations` and `content`).
- `device_page` (`interfaces/ui_read.py:124-158`) makes the two seam calls it already
  makes, plus `device_list` for the ownership count, then
  `populate_tiles(compose_device_presentation(...), latest_retained_readings(...), ...)`.
  Failures inside the join NEVER fail the page: the join is best-effort with honest
  absence — an exception there renders the conservative tile and logs loudly (degrade
  loudly applies to the log; the page keeps its GW-22 honest floor).
- `now_epoch_ms` rides the existing injected-clock plumbing (the `now_epoch` parameter
  `create_app` already takes).

## 5. Precedent (principle 9 — extend, don't invent)

| Piece | Proven mechanism extended |
|---|---|
| Composition-time read-only store reads for what the seam cannot enumerate | `compose_device_presentation`'s admitted-document resolution (`ui_presentation.py:63-101`), ruled in the G2b review |
| Adapter-over-seam page handler, seam calls on the session Identity, honest refusal rendering | `interfaces/ui_read.py` (the rest.py three-step translation, G2 design §2.4) |
| Staleness from the observation's own timestamp against the descriptor's window | `staleness.py` ST-1/ST-2/ST-3 + `reading_staleness` re-export (`ui_presentation.py:49-52`) |
| Digest-verified artifact reads, admission-anchored identity | `artifact_chunk`'s whole-data sha256 (`content/store.py:136-165`) + PR #372 H2/H3's admission-identity discipline |
| Evidence-row queries over the same columns | `cli/retention.py:488`, `cli/report.py::_evidence_rows` (the CLI's raw SQL becomes a typed store method) |
| Reading-shape validation at consumption = the landing lane's own validator | `OTDPBridge._event_reading` (`otdp_bridge.py:1220-1247`) |
| Service-parameter limits, fail-loud env parse | `app_entry._LIMITS` / `_QUOTA_ENV_KEYS` (`app_entry.py:88`) |

New architecture introduced: none. The one new store method is a typed SELECT in the
same family as the CLI's existing queries.

## 6. Root cause / why this is the right shape

The tiles are `Unavailable` not because a value is missing from the system but because
the one durable carrier that is parameter-keyed, schema-validated, and digest-bound —
the telemetry event lane — is unreachable from the read paths the device page was given:
the seam can fetch evidence by id but cannot enumerate ids, and run projections are
closed. The G2 build chose the honest floor (no fabrication) over a store read the
review had not yet ruled; this design rules the store read (§9's CON-5 amendment names
its boundary) and keeps the floor as the failure mode of every hop in it.

## 7. Minimal first increment and deferrals

**Slice 1 = §4 exactly.** `ui_readings.py`, the one ContentStore query, the
`device_page` wiring + `create_app` store handle, the `_LIMITS` row, tests (§8), the
operator-guide row, the CON-5 amendment sentence, this record.

Deferrals — each with carrier and reopen trigger:

| id | deferred | carrier | reopen trigger |
|---|---|---|---|
| D1 | Live / sample-bearing observation reads (issue shape 2) | an interface issue on this tracker, filed by the owner (§12 fork), citing G2 record §9 D4 and this record §3 | the owner's call to file it — unchanged from D4 |
| D2 | Bench-signal monitor snapshots as a second reading source (needs producer-side JSON-shaped retention first: `SignalValue` repr-strings via `json.dumps(default=str)`, invalid readings' `0.0` placeholder, protection-window age semantics) | a design-record deferral row here + a gateway issue filed at slice-1 merge | the snapshot-retention serialization change landing anywhere |
| D3 | Dataset-manifest joins (dataset-kind pages / plots) | the plot lane (#310's ruling; #244's renderer landed) | the plot slice's design record |
| D4 | Capture-manifest (waveform) tile sources | same as D3 | same |
| D5 | Tile severity mapping from quality (today `neutral` for all retained observations; an `invalid` reading renders with its quality label but neutral severity) | `docs/internal/ui-contract.md` §E.1's owner rows | a ui-contract edit touching the reading-tile severity row |
| D6 | Browser-lane DOM arms for populated tiles | the existing browser lane (`tests/interfaces_ui/test_ui_browser.py`) | any browser-lane finding against tile rendering; the composition itself is pinned without a browser |
| D7 | Historic cross-device ambiguity (a sibling device that declared the same parameter at run time but no longer exists on the bench — the ownership count is bench-current) | this row; the guard's does-not-catch clause in code | D2's producer change or a per-run descriptor-pin resolution, whichever lands first |

## 8. Measurable proof — pre-committed acceptance rule

Deterministic functional gates; no sampling. Counts from `--junitxml` attributes or TRUE
exit codes (never a filtered summary line); `UV_PROJECT_ENVIRONMENT=venv` on every
invocation; fast lane per commit (bare `uv run ruff check .`, fresh-cache bare
`uv run mypy`, focused pytest for `tests/interfaces_ui/`); full battery + both standards
tripwires before push. Arms run against a seeded in-process app (the parity suite's
`_boot` pattern) with injected clocks — no live devices.

- **A1 fresh arm**: seeded single-device run, telemetry landed for parameter `voltage`
  (descriptor `max_age_ms: 500`), `now_epoch_ms` 250 ms past `observed_at` → tile
  renders the landed value, the reading's unit, quality, freshness = `observed_at`,
  verdict `fresh`, provenance naming the run.
- **A2 stale arm**: same fixture, 600 ms past → verdict `stale`, value still rendered.
- **A3 boundary + zero-window arms**: `freshness_ms == max_age_ms` → `fresh` (ST-2
  strict inequality); `max_age_ms: 0` with any age ≥ 1 → `stale`.
- **A4 no-window arm**: descriptor parameter without `max_age_ms` → verdict
  `no-verdict` (ST-3), value rendered — never an invented window.
- **A5 honest absence**: device whose runs retained no telemetry → `Unavailable` with
  the absence reason; no value, no fabricated freshness.
- **A6 tamper arm**: flip one byte of a landed artifact after landing → row skipped
  (digest mismatch), tile `Unavailable`, page 200. **MECHANISM-TOGGLE CONTROL:**
  neutralize the digest verification on a scratch copy → A6 must RED (the tampered
  value must not reach the tile).
- **A7 attribution ambiguity**: bench with two devices both declaring `voltage`,
  telemetry landed under a run binding both → tile `Unavailable` for both devices.
  **DISCRIMINATOR CONTROL:** remove the second device's declaration → the tile
  populates (proves the refusal was the ambiguity rule, not a broken join).
- **A8 recency arm**: two runs whose readings carry out-of-order `observed_at` (the
  newer run's reading is older) → the reading with the newest `observed_at` wins — the
  observation's own timestamp, not run order.
- **A9 bench scoping**: device page on bench A with bench B holding an identical
  parameter's telemetry → bench B's rows are never consulted (the query is
  `list_run_states(bench_A)`-scoped by construction); assert no B value renders.
- **A10 budget arm**: more telemetry rows than `scan_rows` → render completes, newest
  rows within budget populate, no exception, absence disclosed for unreached
  parameters.
- **A11 validator arm**: a hand-seeded `event_log` row whose payload is a telemetry
  event with a non-finite value or a missing field → skipped via the landing lane's own
  validator, tile `Unavailable`, no crash.
- **A12 route-shape arm**: the join is read-only — the `/ui` route set is unchanged
  (the G2b route-mapping enumeration still passes byte-identical) and no join failure
  can render a mutating control.

**SHIP iff** A1–A12 all green on the implementing agent's run (junit counts recorded,
exit 0) AND both toggle controls RED under their neutralizations. **KILL if** any arm
passes under neutralization (the test does not discriminate), or any unattributed,
undigested, or fabricated value reaches a tile, or the join can fail the page render.
**UNDERPOWERED, NOT CONCLUSIVE:** uv/port/browser-environment failures — fix and re-run,
no verdict until a clean lane; Windows legs are evidence-posture per the W1 doctrine.

## 9. Invariant, drift, and CI impact

- **CTL/STO/REG: untouched.** No protective behavior, no store schema, no registry
  bytes. A04 untouched (nothing here requires an AI or client to keep working).
- **A06/A13/CON-5:** the join is a read. Proposed amendment sentence (lands with this
  slice, appended to CON-5's existing G2 amendment): *"— the device page's reading-tile
  composition may read the single-writer store read-only (admitted documents, retained
  evidence rows and their digest-verified artifacts) for rendering data the frozen seam
  cannot enumerate; authorization, refusals and cursors remain seam-mediated, the join
  is bench-scoped by construction, and every rendered value is digest-verified gateway
  evidence or the honest `Unavailable` — `src/benchweave/interfaces/ui_readings.py`."*
  This is the ruled boundary the G2b review established for admitted documents,
  extended deliberately to retained evidence rather than drifted into.
- **On-disk formats/schemas: none.** No `standards/` bytes, no interface-catalog
  motion, no store schema, no ui-html package change (the tile partial already renders
  value/quality/freshness/verdict), no `uv.lock` motion, no SDK pointer.
- **Obligations (`docs/internal/drift-and-obligations.md`):** obligation 4 —
  operator-guide gains the device-page reading-tile semantics row (retained-observation
  source, staleness meaning, absence honesty); no other surface moves.
- **CI cost:** `gates` grows the new unit/integration arms (one new test module, no new
  lane); browser lane untouched (D6); timing untouched.

## 10. Review tier (Step-1 call, rubric #254) and keyword scan

**Tier 3 — maximum across the (single) slice**, by the keyword rule over the expected
diff text (the scan below): `sha256` and `hashlib` both fire (digest verification is
the mechanism's spine). The path rules alone would land Tier 2
(`interfaces/` + `content/store.py` + `tests/` — none of the Tier-3 paths named), so
the keyword rule is what buys the deep lane — stated plainly because the tier is
bought by exactly the words that make the mechanism safe. Consequences: two-lane
adversarial refute, cold full battery, both tripwires. The standards-governor mandate
does NOT fire (no `standards/` bytes, no vendored-tree edits, no version strings).

Keyword scan over the whole expected diff — new `src/benchweave/interfaces/ui_readings.py`,
the `content/store.py` query method, `ui_read.py`/`ui.py`/`app.py` wiring hunks,
`app_entry.py` limits row, new `tests/interfaces_ui/test_ui_readings.py`, the
operator-guide row, the invariants amendment, and this record (docs and code alike;
counts are estimates over the expected diff, re-derived over the real diff at review):

| keyword | expected count | where |
|---|---|---|
| `threading` | 0 | — |
| `asyncio` | 0 | — (the wiring hunks sit inside existing `async def` routes; the word itself does not appear) |
| `subprocess` | 0 | — |
| `sha256` | ~14 | code: digest verify + artifact-id check + reference parse (6); tests: seeds + tamper arm (5); record + invariants amendment (3) |
| `hashlib` | ~5 | code import + two uses (3); tests (1); record (1) |
| `migrate` | 0 | — |
| `recovery` | ~1 | record prose only (the restart-posture sentence) |
| `protection` | ~2 | record prose only (D2's protection-window semantics) |

## 11. Top risks, each with its falsifier

- **R1 — render cost on run-heavy benches.** Many runs × evidence rows per render.
  Falsifier/control: the A10 budget arm plus a wall-clock bound on the seeded
  many-run store (the budget is the mechanism; the arm proves it holds). If real-bench
  scale shows material p95 movement, HOLD with numbers (the D13 posture), do not
  silently widen the budget.
- **R2 — evidence-row shape drift** (the landing lane evolves its reference fields).
  Falsifier: A11 — a wrong-shaped row is skipped, never rendered; the join's only
  trust path is digest + the landing lane's own validator.
- **R3 — shared-surface collision with #371/#372.** This diff touches
  `ui_read.py` (one wiring hunk), `docs/internal/invariants.md` (one sentence appended
  to the CON-5 amendment #372's H4 narrows) and, adjacently, the G2b test files.
  **Rebase expectation, stated explicitly:** slice 1 is designed against `origin/main`
  `c183db4` and does not read #371/#372's branches; when they land, rebase — the
  `ui_read.py` and `invariants.md` hunks are adjacent-line conflicts at worst, and the
  CON-5 sentence is additive to whatever H4's narrowing leaves. Falsifier: a semantic
  (not textual) conflict at rebase — then this record's §9 amendment is re-derived
  against H4's final wording before merge.
- **R4 — cross-device attribution silently wrong.** Falsifier: A7 + its discriminator
  control; the disclosed residual (historic siblings, D7) lives in the guard's
  does-not-catch clause, not in silence.
- **R5 — the store read reads as a CON-5 drift** (a third adapter bypassing the seam).
  Mitigation: §9's amendment names the boundary and its three clamps (bench-scoped,
  digest-verified, honest-absence floor); the Tier-3 refute lanes get it as a named
  target. Falsifier: a refute finding showing data reaching a page the seam would
  refuse the same session — that kills the store-read shape and reopens the fork.
- **R6 — always-stale tiles read as broken UI on sim devices** (`max_age_ms: 0`
  descriptors make every retained observation stale the instant it lands — correct
  ST-2 semantics, discouraging optics). Mitigation: the provenance line ("retained
  observation from run R") and the stale marker render together, so the tile reads as
  evidence-with-age, not a dead gauge. Falsifier: a browser-lane or owner review
  finding that operators misread it — then the tile's source-class wording is the fix,
  never the predicate.

## 12. Maintainer decisions (the fork this issue reserved)

- **Fork A (recommended): adopt shape (1), dispatch slice 1 as specified.** Every
  rendered number becomes digest-verified gateway evidence; the seam, standards and
  interface stay untouched; shape (2)'s carrier is unchanged and can still be filed
  later if live tiles are wanted.
- **Fork B: keep tiles conservative; file the interface issue for a sample-bearing
  observation read instead.** Costs: the device page stays `Unavailable` until a
  multi-train interface arc lands (interface version bump, standards bytes, governor,
  SDK twin, parity — plus a host-side idle-read mechanism that does not exist today);
  the honest-limits findings in §1 (executor reads not retained; the seam cannot
  enumerate evidence) are exactly the facts that issue will need, so this record is
  its evidence base either way.
- **Fork C (not recommended): close #369 as wontfix.** GW-22's own wording already
  names run evidence as the intended tile source; closing leaves the PRD requirement
  half-met by choice rather than by constraint.

Either way, §1's read-path findings (the seam's evidence-enumeration gap, the
executor's non-retained read values, the monitor snapshot serialization) are the
durable facts any future reading-tile work starts from.
