# Compatibility Record — WP02 MCP/Client Spike

> Evidence for the delivery plan's WP02 risk gate: "Exact 2026-07-28 live
> discovery/tool exchange and wrong-audience/expired/scope rejection; record
> exact dependency/client versions before freezing adapters."

## Verdict

**Bounded stdlib adapter is viable; the official MCP SDK is deferred.** The
complete exchange (initialize → tools/list → tools/call, JSON-RPC over
streamable-shaped HTTP with the `Mcp-Session-Id` header) was exercised over
real loopback sockets with zero runtime dependencies. Nothing observed
justifies taking the SDK dependency before WP07's parity work; revisit if a
future slice needs SSE streaming responses, transports other than streamable
HTTP, or client auth flows beyond a bearer token.

## Exact versions exercised

| Component | Version |
|---|---|
| CPython | 3.13.13 (macOS aarch64) |
| uv | 0.12.12 (c4be69153, 2026-09-09) — upgraded from 0.11.16 mid-spike; see below |
| Runtime dependencies | **none** (stdlib `http.server`, `urllib.request`, `json`, `hmac`, `hashlib`) |
| MCP protocol negotiated | `2026-07-28` (initialize echo) |
| Dev tools | pytest 9.1.1, ruff 0.16.6, mypy 2.3.1 (strict) |
| Lock | `uv.lock` (committed) |

## Exchange proven

- `initialize` → protocolVersion `2026-07-28` + `Mcp-Session-Id` response header
- `notifications/initialized` → 202
- `tools/list` → all **17 tools** from the vendored `contracts/interface-v1.1.0/mcp-tools.json` (`stg_v1_*` namespace) — the corpus itself, not a fixture copy
- `tools/call` (`stg_v1_gateway_info`) → content result

## Authentication proven (`benchweave.interfaces.identity`)

Local test issuer, HMAC-SHA256, principal/audience/scopes/expiry, injected
clock (pure, deterministic), constant-time signature compare, fail-closed
rejections. Status mapping exercised over the live loopback:

| Condition | HTTP | Reason token |
|---|---|---|
| Valid scoped token | 200 | — |
| Wrong audience | 403 | `wrong_audience` |
| Missing scope | 403 | `insufficient_scope` |
| Expired | 401 | `expired` |
| Malformed / bad signature | 401 | `malformed_token` / `bad_signature` |

Enforcement point in the spike server: `initialize` open, `tools/*` gated —
recorded as a decision to revisit when the interface contract grows an auth
vocabulary (it has none today; checked, not assumed).

## Environment note (venv editable install — ROOT CAUSE)

The intermittent `import benchweave` → `ModuleNotFoundError` (2026-09-10, 5
occurrences across uv 0.11.16 AND 0.12.12) is NOT a uv bug: the venv's `.pth`
files were carrying the macOS `UF_HIDDEN` file flag, and CPython's site.py
refuses hidden `.pth` files (`python -v` shows `Skipping hidden .pth file`),
silently disabling the editable install while `.pth` + dist-info look intact.
Proof: `stat -f '%Sf'` showed `flags=hidden`; `python -v` showed the skip.

**Heal (instant):** `chflags nohidden .venv/lib/python3.13/site-packages/*.pth`
then re-run. (`uv sync --reinstall-package benchweave` also works; it rewrites
the file without the flag.) The actor setting the flag between runs is
UNIDENTIFIED — on recurrence, run `ls -lO .venv/lib/python3.13/site-packages/*.pth`
immediately and check holders via `lsof +D .venv`. An earlier draft of this
section attributed the failures to the uv 0.11.16 → 0.12.12 upgrade; the
recurrence on 0.12.12 disproved that and prompted this correction.

---

# WP07 Qualification Record — FastMCP/FastAPI Gateway (2026-09-13)

> Supersedes the WP02 verdict above for WP07 and later: the deferred SDK
> adoption happened (principal directive, 2026-09-12). The WP02 stdlib
> exchange above remains proven evidence and the recorded fallback.

## Verdict

**FastMCP 4.0.3 over the official MCP SDK is qualified for the gateway.**
One FastAPI ASGI application serves the 20 REST routes under `/v1/*` and a
FastMCP server mounted at `/mcp` on the same loopback port; both adapters
wrap the one typed core-operations seam. REST↔MCP parity is proven per
operation — the full contract envelope compared field-for-field across
transports, each reachable failure class at its contract code
(`tests/integration/test_interface_parity.py`) — and event recovery after
SIGKILL is proven (`tests/integration/test_event_recovery.py`).

## Exact versions exercised (uv.lock, committed)

| Component | Version |
|---|---|
| fastapi | 0.141.1 |
| uvicorn | 0.52.4 |
| fastmcp | 4.0.3 (pin `==4.0.3`, `server` extra) |
| mcp (official SDK, under FastMCP) | 2.2.0 |
| CPython (project venv) | 3.13.13 (macOS aarch64) |
| Dev tools | pytest 9.1.1, ruff 0.16.6, mypy 2.3.1 (strict) |

## Transport verified

Real loopback HTTP throughout: uvicorn on an ephemeral port, REST `/v1`
and MCP `/mcp` served by the one application. Not verified — out of PoC
scope: TLS, OAuth flows beyond the local HMAC bearer issuer, and
non-loopback binding.

## Introspection notes (what actually worked)

- `initialize` requesting `2026-07-28` **counter-offers `2025-11-25`**
  (`LATEST_HANDSHAKE_VERSION`; `HANDSHAKE_PROTOCOL_VERSIONS` ≤ 2025-11-25
  in this SDK generation, so initialize can never echo a modern revision).
  The 2026-07-28 revision is served via `server/discover`; `gateway_info`
  advertises `mcp_version "2026-07-28"` on both transports.
- FastMCP 4.0.3 signature inference cannot reproduce vendored schemas, so
  every tool is constructed with the vendored `inputSchema` verbatim via
  the SDK's explicit-schema override route (the function signature is only
  the callable). `tools/list` deep-equals the vendored corpus: all 17
  `stg_v1_*` tools, `required` included.

## Deviation register (D1–D13, pinned by the parity suite)

Each deviation has a pinning test or an explicit disclosure; none is
silent. Full wording for D1–D7 lives in the
`tests/integration/test_interface_parity.py` module docstring. D8–D13 are
the final-fix-wave register (2026-09-13, from the two whole-branch
reviews); each names its WP08 reconciliation.

**Final-fix-wave code corrections shipped the same day** (behavior pins
updated with them): the §7 retention-overtake failure is `event_gap`, not
`cursor_expired` (the overtake branch is `event_gap`'s raise site;
`cursor_expired` now has no emitter — trim deletes contiguous prefixes, so
a hole cannot arise by construction); `run_cancel` is owner-or-admin
scoped (§6 — a control-tier stranger gets 403); the artifact offset floor
moved into the seam (negative offsets serve head bytes on both
transports); the five mutating MCP tools hold the app's `WriteGate`
(mirroring REST's seven gated handlers); and MCP failure envelopes carry
`isError: true` (D10, closed).

| # | Deviation |
|---|---|
| D1 | `run_get` tier: seam fixed to catalog authority (observe); both tiers pinned |
| D2 | `change_apply` body: the catalog's REST schema omits `approver_token`, the adapter forwards it as a seam kwarg; the vendored catalog is frozen authority and is not edited — WP08 amendment |
| D3 | CLOSED (WP08 Task 1, side effect of D8): the MCP tool-signature defaults still fire (fastmcp 4.0.3 does not enforce the pinned schema's `required` at dispatch), but the seam now validates the defaulted payload — every empty-string default violates the corpus pattern/`minLength`, so an omitted required string param surfaces `invalid_request` on MCP too (parity with REST's 400; `test_interface_parity.py::test_invalid_request_required_param_rest_vs_mcp_default`). Residuals, pinned: the paging defaults (`limit=1`, `cursor=None`/`after=None`) are schema-valid well-formed requests and still succeed over MCP — a transport default, not a validation gap; and fastmcp's signature-based argument handling (numeric strings coerce to the annotated int; string-where-object is rejected pre-seam with fastmcp's own non-contract error) remains the D3-family root, disclosed in `test_mcp_signature_coercion_boundary` |
| D4 | event evidence: the seam emits free-form evidence dicts while the contract's `evidence` def is a closed `{id, version, sha256}` document ref. D12 exception (WP08 Task 3): `authority_changed` emits the def's closed ref exactly (the takeover pins the binding document, the release the commissioned bench configuration) — the first kind reconciled; the legacy free-form family is pinned per-family by `test_interface_parity.py::test_event_evidence_shape_deviation` (realigned) and stays the WP08 reconciliation item. Related finding, RESOLVED by the fix-wave rename (reviewer I1, controller-ruled): the def's `stream_id` pattern `^[a-z][a-z0-9_.-]*$` forbids the seam's colon-bearing `bench:{bench_id}` naming for EVERY kind (a live contract violation every emitted event inherited, pre-D12). The seam now constructs `bench.{bench_id}` (dot — in the pattern's allowed class) at both naming sites (`append_bench_event` and `events_get`), NO errata: the D2 errata stays scoped to `approver_token`. Wire-visible change: `stream_id` values and the stream-scoped cursor namespace are now dot-form; pins flipped (`test_seam_events`, `test_seam_admin`, `test_interface_parity`, the takeover suites) and the takeover validators now check the VERBATIM vendored def (un-patched) — verbatim conformance is the green proof. No data migration: pre-release, no deployed clients (contract §12: no compatibility claim) |
| D5 | wire `tools/list` schemas are vendored-minus-`$defs` (the corpus `$defs` are unreferenced and inert; serve-time middleware is the SDK's) |
| D6 | token-shaped rejections collapse to a transport 401 on MCP (no envelope can exist pre-auth — the WP02 map's 403 semantics surface only at REST); `payload_too_large` reached REST-only until WP08 Task 5 closed it (D13): the MCP adapter now enforces the same `limits["max_json_bytes"]` ceiling over the tool-call arguments (canonically re-serialised; arguments arrive parsed, REST measures raw bytes) with the identical envelope text — pinned by `test_interface_parity.py::test_payload_too_large_envelope_parity` |
| D7 | token-shape probes pinned on both transports: expired → 401 `unauthenticated`; wrong-audience → 403 `forbidden`; an stg-audience token as `approver_token` fails closed 403 |
| D8 | CLOSED (WP08 Task 1): the seam validates every public operation's payload against the vendored corpus — `interfaces/validation.py::SeamValidator` builds one schema per operation (the MCP `inputSchema` where a tool twin exists, else the OpenAPI `requestBody`; their `required` sets cross-checked at registry build with path params reconciled) and every `Operations` method validates as its first act after `require_permission`, so type-confused/shape-invalid inputs are the contract `invalid_request` on both transports (`tests/unit/test_seam_validation.py` + the parity suite's D8 re-pins: 500/coerced-409/garbage-201 all flipped to 400). Boundary disclosed and pinned: fastmcp dispatch validates the tool SIGNATURE, not the vendored schema — numeric strings coerce to the annotated int and string-where-object is rejected pre-seam on MCP with a non-contract error, so those two classes never reach the seam over MCP; the seam itself rejects both (REST arms prove it end-to-end). Named residual, same root: extra-property enforcement is seam-only — the REST adapter's named-field extraction (`_field` and the per-route keyword lists) DROPS unknown body properties before the seam (the request succeeds with the property silently ignored), and MCP rejects an unknown tool argument at dispatch with fastmcp's own non-contract error (`unexpected_keyword_argument`); neither wire surfaces the contract `invalid_request` for this class, and wire-level enforcement requires adapter changes frozen out of this slice (`test_interface_parity.py::test_extra_property_wire_truth_on_both_transports` pins both wires) |
| D9 | CLOSED (WP08 Task 2): §5 accept-time pre-checks live in the seam. `run_start` refuses synchronously — 409 `conflict`, before the request key is written — when (a) the bench has a live run (busy oracle: `Store.list_run_states`, states accepted/running/protecting; the store had no per-bench run view, so activity is derived from `run_states`) or (b) the binding document's own `request_id` (content-store resolution, `run_check`'s idiom) differs from the §9 request id. §9 replay stays ahead of both: an already-filed request key returns the existing run before any §5 check (peek via `find_request`; `accept_request` remains the atomic race authority). Lease authority is modeled on the run row (`runs.authority`, migration v3: `lease` when a `lease_id` was named, else `gateway`) — takeover itself is Task 3. Postures pinned in `tests/integration/test_seam_prechecks.py`: an unstored binding digest is not decided at accept time (the worker's poison guard keeps owning that async failure); the catalog blesses no busy-specific code, so contention rides `conflict`. Consequence disclosed: a second run can no longer queue behind a live one ("no queue waits indefinitely for control") — the pre-D9 queued-cancel recorded-no-op pin was unreachable-premised and was replaced by the §5 contention pin (`test_event_recovery.py::test_second_run_start_on_live_run_conflicts_and_frees_after_terminal`); the worker's FIFO drain remains an internal residual. Bonus closure: the Task-10 repeated-binding worker crash (same binding, different §9 id) is now refused at the seam (binding-mismatch conflict before acceptance) |
| D10 | MCP `isError` — FIXED by the final fix wave: failure envelopes now serve `isError: true` with the contract envelope intact as structured content (`test_interface_parity.py::test_mcp_is_error_flag_on_failure_and_success`). Closed |
| D11 | CLOSED (WP08 Task 5, ALIGNED to the §8 letter): input coercion stays clamp-not-reject for the numeric bounds — `limit`/`length` clamp to `[1, max]`, artifact `offset` floors at 0 (at the seam) — while the beyond-size `offset` case follows the contract letter exactly: "At EOF an offset equal to size yields zero bytes; offsets beyond size fail." At-size still serves the zero-byte `eof=true` chunk (pinned); beyond-size now raises in `ContentStore.artifact_chunk` (Python slicing used to clamp it to a silent empty tail) and the seam maps it to `invalid_request` — the artifact exists (not `not_found`) and the caller already holds its size, so the un-existable window is a bad request. One construction site at the seam ⇒ identical envelopes on both transports; pinned in `tests/integration/test_interface_parity.py::test_artifact_offset_letter_beyond_size_fails_at_size_serves_empty` |
| D12 | CLOSED (WP08 Task 3): `run_start` honors `lease_id` as a commissioned-takeover assertion, woven into the §5 pre-check flow (`_assert_bench_acceptable`, after the generation fence and the §9 replay peek). Validation: resolve via `_find_lease` → unknown/released/expired/consumed `not_found`; wrong-bench `conflict`; expiry by seam clock `not_found`; holder §6 owner-or-admin `forbidden` (the shared `is_owner_or_admin` predicate — same one `run_cancel` scoping uses). A validated lease is CONSUMED before the request key is written (`Store.consume_lease`, state→released — the closed lease enum has no 'overridden' value; the `authority_changed` event + `runs.authority='lease'` are the audit trail), which (a) lets the worker's `reserve` see an idle bench instead of `bench_busy` (the real-coordinator proof is the REST pin: a takeover run reaches `passed`), (b) makes the lease single-shot — a NEW request re-presenting a consumed lease fails `not_found`, while a §9 replay of the same request returns the existing run (the peek precedes validation), and (c) never waives §5 contention — another live run still conflicts (corpus: "another active controlling run … still conflicts"). `authority_changed` gains its first emitters: the takeover path (before enqueue, evidence = the closed binding-ref doc) and `lease_release` (evidence = the commissioned bench configuration ref). `authority='lease'` on the run row is now evidence a real validated lease was presented (closes the Task-2 unvalidated-column warning). Pinned in `tests/integration/test_takeover.py` (seam) + `test_event_recovery.py::test_run_start_with_lease_takeover_over_http` (wire); collateral pins realigned: the Task-2 authority pin now creates a real lease, the D4 evidence pin asserts the closed ref per-family. Residual disclosed: the run row does not record WHICH lease (Task-2 concern) — `lease:{id}` encoding deferred; and the seam-consume→worker-reserve window can still be raced by an unrelated `lease_create` (lease_create does not check bench contention — a pre-existing §6 "rejects conflicts with existing authority" gap, D13-family) |
| D13 | batch A (store side) CLOSED (WP08 Task 4): lease expiry is enforced on every seam busy read — `Operations._live_lease` treats the stored `expires_at` as the read-time oracle at the injected clock (`limits.max_lease_ms` bounds minting, never reads), so an expired-unreleased lease stops pinning its bench `busy` (the bench projection and the configuration-activation idle boundary both read it; an unparseable stamp cannot wedge the bench either; §5 run-side busy stays the `LIVE_RUN_STATES` oracle — expiry clears only the LEASE side); the events cursor-read is index-served — `idx_events_stream_seq` (migration v4), proven by EXPLAIN QUERY PLAN in `tests/unit/test_store_hygiene.py` (the v1 composite-PK autoindex was already usable; the explicit index makes the serving structure declared and planner-preferred); the `accept_request`→`create_run` crash-window is reconciled at startup — `Store.reconcile_dangling_requests` rides `_recover_interrupted_runs` (the lifespan's ONE recovery entrypoint, the interrupted-run idiom): a RUN key whose run never materialized is purged so the same request id proceeds — the sweep is scoped to run keys (its anti-join must resolve in EVERY durable table — batch B added `leases`: a `lease_renew` §9 key's `run_id` column holds the LEASE id, which has resolved since creation, so renewal keys are never dangling and keep replay protection; keys resolving in `changes` or `leases`, and run keys with a runs row — live or tombstoned — keep replay protection; review fix I1 pinned in `test_d13_sweep_spares_change_submit_keys`, the lease leg in `test_d13_sweep_spares_lease_renew_keys`), no event is emitted (nothing observable happened; the seven-kind fence has no vocabulary for it); hygiene fold: `release_lease`/`consume_lease` share one guarded `_close_lease` transition. batch B (transport/error side) CLOSED (WP08 Task 5): the MCP transport carries the body ceiling (the D6 residual — every registered tool enforces `limits["max_json_bytes"]` over the canonically re-serialised tool-call arguments, same `payload_too_large` code and message text as REST's pre-parse 413; arguments arrive parsed, REST measures raw bytes); `internal_error` is ONE construction site (`errors.internal_failure`) — message text transport-invariant, per-instance detail (the exception class only) parameterised into `details`, and every envelope mints `uuid4().hex[:16]` into `correlation_id` (the §10 "a correlation ID links internal diagnostics" link); `change_apply`'s undecided-crash envelope advertises `retry: never` (re-entry on an unknown change is the two-phase `conflict` — the state machine's own answer, pinned — so `same_request` lied about re-entry semantics); §6 lease semantics closed: `lease_create` rejects conflicts with existing manual or gateway-owned authority (a live run OR a live lease → `conflict`; `_assert_bench_acceptable`'s busy oracle + the `_live_lease` idiom — closing the D12-disclosed consume→reserve window: an unrelated `lease_create` landing while a takeover run is live is refused instead of bench_busy-ing the worker's reserve into the poison guard), and `lease_renew` files §9 request keys (a duplicate returns the SAME renewal, no second extension; a different body under the key → `conflict`; the replay peek precedes validation) and refuses to revive an expired-unreleased row (`not_found` at the seam clock — expired means expired). Fixture consequence disclosed: the §6 one-live-manual-lease-per-bench invariant re-structured three test surfaces — the parity module's lease inventory spreads over seeded spare benches, the rest_routes setup lease moved to bench-two behind a terminal poll, and the retention-overtake wire test drives its twelve emissions as one create + eleven renewals (identical emission arithmetic). REMAINING: the async single-loop posture runs blocking SQLite on one event loop (head-of-line blocking under concurrent calls). Adjacent residual disclosed, NOT folded: a crash between `create_run` and `put_run_state` still replays `not_found` (run exists, no queue-state row — same wedge class, needs a run-state-aware sweep; deferred because distinguishing a never-accepted run from a recovery-finalized run requires ordering analysis against `_recover_interrupted_runs`, a material diff) |

## Licence/provenance display (Task 12 verdict: store-retained, not wire-exposed)

The ratified §D carry is served **nowhere on the interface-v1.1.0 wire —
by the schema's own decision**. The `bench` and `device` $defs are closed
(`additionalProperties: false`) with no licence field, and the fallback
landings are closed the same way: `evidence_get`'s data object admits
exactly `{evidence_id, kind, content_ref, artifact_id}`, and
`document_get`'s document object exactly `{id, version, sha256}`. The
honest landing: the licence bootstrap admits stays in the benches and
devices store rows (Task-2 columns; `"proprietary"` where the fixture
lattice declares no licence) — queryable at the store, never wire-exposed.
Pinned by
`tests/unit/test_seam_observe.py::test_bench_projection_carries_licence_where_schema_permits`,
which also pins the closed $defs, so a future interface version that
admits a licence field flips that test and forces the wire carry.

## Conformance boundaries (disclosed, not hidden)

- **Registry change kinds are not reachable** without a registry session:
  `package_admission` and `configuration_activation` fail closed
  `not_ready` — this PoC runs the fixture bench with no resolver session
  (WP08 wires it).
- **`trip_reset`'s gate reads an always-False flag**: the bench projection
  hardcodes `tripped=False` (no live trip source in the PoC), so the
  reset-refusal gate never fires; reconciled physical state is the
  contract's assumption, not a wired signal here.
- **Queued-cancel branch is interface-unreachable (D9)**: a second
  `run_start` on a bench with a live run now conflicts at accept time, so
  no run can queue behind another through the interface; the recorded-no-op
  cancel branch remains for a single run's accept→dispatch window only
  (the worker's FIFO drain is an internal residual).
- **Repeated-binding second starts conflict at the seam (D9)**: a
  `run_start` whose §9 request id differs from the binding document's own
  `request_id` is refused synchronously (409 `conflict`) before
  acceptance; the same §9 id is a §9 replay. The pre-D9 async shape
  (seam accepts, coordinator dedups on the binding's own id, worker's
  poison guard closes the run `outcome_unknown`) is retained only for
  unstored binding digests, which are not decided at accept time.
- **Auth is the local HMAC test issuer, loopback only** — OAuth and TLS
  are out of PoC scope (see Transport verified).
