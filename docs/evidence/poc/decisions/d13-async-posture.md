# D13 async posture — decision record (WP09 Task 10, 2026-09-14)

**Decision: permanent disclosure; no fix slice.** The pre-stated
protocol's third branch applies — PRD-load targets met on both gating
measurements, stress tier clean of material degradation. The
single-loop gateway (blocking SQLite served on one ASGI event loop)
stands as the disclosed PoC architecture.

Evidence: `docs/evidence/poc/timing/prd-load.json` (reference,
gating) and `docs/evidence/poc/timing/stress-16.json` (non-reference,
non-gating) — measurements landed `939fb5e`, retained evidence
`545d527`. Registered in the D13 row of `docs/compatibility.md`.

## The pre-registered question

D13's remainder after the WP08 close: the gateway runs **blocking
SQLite on one event loop** — stdlib `sqlite3` called from synchronous
request handlers, no async driver, no executor offload. Every request
that touches the store holds the loop for its store work's duration,
so concurrent callers queue behind whichever call is executing: the
registered risk is **head-of-line blocking under concurrent calls**.
WP08 re-ledgered exactly this remainder to WP09 with the
pre-registered agreement that the measured read/admission targets
decide fix vs permanent disclosure; the protocol below was written
before any measurement existed.

## The pre-stated protocol (verbatim, WP09 spec Slice 4)

> - **D13 decision protocol (pre-stated):**
>   - PRD-load target blown → profile, fix inside WP09 (async SQLite
>     off the loop or equivalent bounded fix); a fix that would
>     reshape architecture escalates to the principal as a scope
>     review instead.
>   - PRD load met, stress tier shows material degradation →
>     permanent disclosure records **both** tiers; a fix slice is
>     named for the backlog.
>   - PRD load met, stress tier clean → permanent disclosure with
>     both tiers' evidence.
>   - In every branch the outcome is written into the D13 row of
>     `docs/compatibility.md`.

This record executes the third branch. The branch was selected by the
recorded numbers, not re-derived.

## The measured evidence (quoted from the committed artifacts)

Host disclosure, identical in both artifacts (`host`): Darwin 25.6.0,
arm64, CPython 3.13.13. Gateway `gw-cli-evidence`, ephemeral
SIMULATION-labeled gateway, seed 20260914, generated
2026-09-14T09:17:10Z. Timer: `time.perf_counter` around each
`GatewayClient` call (stdlib only); percentile: linear interpolation,
rank = q * (n - 1), over the sorted sample.

### Tier 1 — PRD load (`timing/prd-load.json`: `"reference": true`, `"gating": true`)

| JSON field | `prd-load-reads` | `prd-load-acceptance` |
|---|---|---|
| `p50_ms` | 2.487 | 2.084 |
| `p95_ms` | **4.746** | **4.790** |
| `max_ms` | 17.157 | 9.501 |
| `count` | 100 | 100 |
| `observers` | 2 | 1 (`observers_declared: 2` — caveat below) |
| `active_run` | true | false (idle-bench accept, disclosed in the artifact) |
| `active_run_coverage` | 1.0 | — |
| `target_p95_ms` | 500 | 2000 |
| `verdict` | `"pass"` | `"pass"` |

Measured read set (bench-scoped, both tiers): `GET /v1/benches`,
`GET /v1/runs/{id}`, `GET /v1/benches/{id}/events`, rotating.

### Tier 2 — stress (`timing/stress-16.json`: `"reference": false`, `"gating": false`)

| JSON field | `stress-16` |
|---|---|
| `p50_ms` | 14.053 |
| `p95_ms` | **24.614** |
| `max_ms` | 32.833 |
| `count` | 1600 |
| `observers` | 16 |
| `active_run` | true |
| `active_run_coverage` | 0.9418 |
| `verdict` | `"recorded"` |

Method (both artifacts): 16 observers × 100 metadata reads each, the
same rotating read set, barrier-started so the whole burst is
simultaneous, while the active-run driver keeps a run live. The tier
exists to make this disclosure honest, not to gate anything.

## The branch taken

Both gating verdicts are `"pass"`: reads p95 4.746 ms against
`target_p95_ms: 500` (~105× under), acceptance p95 4.790 ms against
`target_p95_ms: 2000` (~417× under). The first branch (target blown →
fix inside WP09) does not open. The stress tier records the
head-of-line shape with numbers — read p95 inflated 4.746 → 24.614 ms
at 8× observer count — yet every absolute figure stays in the tens of
milliseconds, `max_ms: 32.833` across 1600 calls. That is the
registered risk observed, bounded, and non-material at PoC scale: no
call approached any target, nothing timed out, nothing retried. The
second branch requires degradation that is *material* — degradation a
client of this product would feel against its targets; none is
present. **Third branch taken: permanent disclosure recording both
tiers' evidence; no backlog fix slice is named.**

## Head-of-line: what the stress tier does and does not exercise

**Mechanism.** One ASGI event loop; one SQLite connection behind it;
single-writer serialization. A barrier-started burst of 16 read
observers queues each store round-trip behind the other fifteen's —
read p95 rising from 4.746 ms (2 observers) to 24.614 ms (16
observers) **is the head-of-line signal**: it is the loop's queue,
measured. It is visible, reproducible, and bounded — the queue drains
in tens of milliseconds per call because each unit of store work is
itself sub-millisecond to a few milliseconds.

**Not exercised by this tier:**

1. **Concurrent acceptance** — structurally impossible at PoC scale;
   the caveat below bounds it by proxy.
2. **Write-heavy mixes** — the measured set is read-dominated (three
   GET kinds); the only concurrent writer is the driver's restart
   cycle (binding-variant store, preflight, `run_start`, state
   transitions — a 17th client, disclosed in the artifacts' method
   text).
3. **Long single store operations** — no artifact-sized writes,
   checkpoints, or migrations were in the measured set, so the
   worst-case serialization unit (one long write holding the loop
   ahead of everyone) has no number in this evidence.

The disclosure therefore claims exactly what was measured:
read-dominated concurrency at 16 observers on this host is bounded and
non-material. Heavier profiles are held to the reopen rule below, not
to this evidence.

## Acceptance-sequential caveat (`observers: 1` achieved, 2 declared)

`prd-load-acceptance` records `observers: 1` with
`observers_declared: 2`. Concurrent acceptance measurement is
structurally impossible on the committed fixture lattice:
`admit_startup_bench` reads exactly one `bench.json` (one bench per
gateway), and §5 holds one live run per bench — a second concurrent
`run_start` on the same bench CONFLICTS at accept (it measures a
refusal, not an acceptance). The measurement therefore ran
sequentially on the one bench over distinct §9 keys; the artifact's
method text discloses the full reasoning. Acceptance-contention
head-of-line is consequently not directly evidenced — but it is
bounded by the reads/stress evidence: the accept decision is ordinary
fast store work of the same SQLite-on-one-loop class the stress tier
exercised (`p95_ms: 4.790`), not a long operation, and a conflicting
second accept is refused at the same speed.

## Disclosure phrasing rules (binding, from the Task-9 review)

1. **`active_run_coverage` reads as "no OBSERVED gap", never "no
   gap".** Coverage is interval-derived — accept-response to terminal
   observation at 0.2 s poll granularity — so observation lag of up to
   one poll interval is inside the number. `active_run_coverage: 1.0`
   means no gap was *observed* within that bias;
   `active_run_coverage: 0.9418` means 5.82% of the window was
   observed idle. Any restatement claiming more than observation is
   inadmissible.
2. **The measured read set is bench-scoped.** The events route in the
   measured set is `GET /v1/benches/{id}/events` — **no global events
   surface exists on the interface-v1.1.x wire**. The planning
   documents' `/v1/events` shorthand is a plan-side abbreviation and
   must never be restated as if it named a measured route.

## Reopen rule

This posture — blocking SQLite on one event loop, closed as permanent
disclosure with no fix slice — holds for concurrent-call profiles at
or below the stress tier's: 16 observers, read-dominated,
millisecond-scale store units, on the recorded reference host. A
future workload whose concurrent-call profile materially exceeds that
profile — more concurrent callers, write-heavy mixes, long store
operations (artifact I/O, checkpoints, migrations), or any measured
regression against a PRD target — re-opens D13's posture question
with new measurements under this same protocol; the fix lane the
first two branches name (async SQLite off the loop, or an equivalent
bounded fix) remains the pre-registered response.
