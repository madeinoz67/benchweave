# G2 design — read-only gateway UI and browser session (issue #303, PRD 12)

**Verdict: BUILD-WITH-DEFERRALS.** Triage call: mechanisms, issue numbers and code paths
only — no person, client, bench, serial or install detail — public path as named is
defensible.

**Evidence baseline:** gateway `origin/main` `46410da` (2026-10-03); SDK submodule at the
main pin `7d9a8ba` (primary checkout shows the standalone subtree at SDK `54b7616`, PR
#74 merged = I1 landed). Trigger state verified: #301 (G1e) CLOSED 2026-10-02; #311 (F1
tracking) OPEN with the `deferred` label — the exit gate's "F1 tracking issue raised" item
is already satisfied and only needs the §12 back-link confirmed in the G2 PR body.

## 1. Premise check (what was verified, not assumed)

- `create_app` (`src/benchweave/interfaces/app.py:913-1052`) includes the REST router
  BEFORE the catch-all `app.mount("/", mcp_app)`; the UI router slots into the same
  ordering window. GW-04 is testable against the composed app exactly as `/v1` is.
- The seam serves 20 operations (`operation-catalog.json`): 12 read
  (gateway_info, bench_list, bench_get, device_list, device_get, document_get, run_get,
  run_find, events_get, evidence_get, artifact_read, change_get) and 8 mutating. G2's
  read views are fully covered by existing seam methods — zero seam changes.
- `benchweave-ui-html` 0.1.0 is a workspace member (`packages/ui-html`, root
  `pyproject.toml:73`) exposing typed partials (`partials.py`), the staleness predicate,
  the manifest grammar, and `assets/verify_vendored_assets()` with an inventory over
  three CSS files. No JS assets are vendored yet (§5 decision below).
- The PRD 11 I1 standalone host LANDED 2026-10-01 (SDK PR #74) as `benchweave-standalone`
  0.1.0 — self-contained, NOT depending on ui-html, vendoring its own `htmx.min.js`,
  `sse.js`, `standalone.css` + inventory. Its `tokens.css`/`themes.css` sha256 values are
  **byte-identical** to ui-html's — the CSS halves are already converged; only the JS and
  host chrome differ.
- **`cursor_expired` has no emitter in the seam** (`docs/compatibility.md` D-final-fix-wave:
  "the overtake branch is `event_gap`'s raise site; `cursor_expired` now has no emitter,
  because trim deletes contiguous prefixes"). The G2 exit gate still requires it "induced
  and rendered" — resolved in §7 (test-boundary induction, disclosed; adding an emitter
  would be an interface behavior change, excluded by the PRD's own non-goals).
- **The event vocabulary carries no samples.** The seam emits six kinds
  (`run_changed`, `lease_changed`, `bench_changed`, `authority_changed`,
  `registry_status_changed`, `evidence_gap` — `operations.py`), all state, and the
  device/bench projections (`interface.schema.json` `$defs`) carry no reading values.
  "Live readings" over the read-only interface therefore means: observations the gateway
  already made (run evidence, datasets) rendered as reading tiles, plus state changes via
  the event bridge. A live sample stream is not an interface 0.1.0 capability (§9 D4).
- #307 closed with the 6-hour lease default ruling; its GW-44 floor consequence is G3's
  exit item, not G2's (GW-40–44 are in G3's requirement set).

## 2. The mechanism

Four moving parts, all extending proven in-tree shapes. Nothing here invents new
architecture; the one new subsystem (the session store) is the smallest thing that
satisfies GW-90–94/NFR-S1–S2, and it is proposed as a new invariant row (§8).

### 2.1 Composition and routing (GW-01–04)

New `src/benchweave/interfaces/ui.py`: `build_ui_router(operations, sessions, *, limits,
now_epoch, csrf) -> APIRouter` with `prefix="/ui"`. In `create_app`, between the REST
include and the catch-all mount:

```python
if ui_enabled:
    app.include_router(build_ui_router(...))   # before app.mount("/", mcp_app)
```

`ui_enabled` is a keyword-only `create_app` parameter (the `execution_corpus` precedent at
`app.py:924`: composition parameter, no env in the factory). `app_entry.build()` reads
`BENCHWEAVE_UI` (fail-loud parse, the `_QUOTA_ENV_KEYS` pattern at `app_entry.py:88`);
**recommended default: enabled** (the deploy posture is loopback single-operator and the
UI is the PRD's deliverable; the flag exists to disable, per GW-03's wording) — flagged
F2 for the owner in §11. Disabled means the router is never registered: absent, not
stubbed. Both postures are pinned by the GW-04 test.

At construction with the UI enabled, `create_app` calls
`benchweave_ui_html.assets.verify_vendored_assets()` and **refuses to compose** on any
mismatch — this is the obligation-12 wiring ("the wiring lands with G2 / PRD 11") and
I1's construction-time-verification precedent.

### 2.2 The session layer (GW-90–94, NFR-S1–S3)

New `src/benchweave/interfaces/sessions.py` — a `SessionStore` holding
`session_id -> SessionRecord` (principal, audience, scopes, expires_at, csrf_token,
bridge registry) under one lock, with an injected `now_epoch` (pure, testable, the
`identity.py` discipline). Sessions are server-side only: a gateway restart empties the
store and invalidates every session (GW-94). The cookie (`bw_session`) is `HttpOnly`,
`SameSite=Strict`, `Path=/ui`, `Secure` when served over TLS, and carries the opaque
session id — never a token, never a scope, never an expiry (the server owns all three).

Login-link flow, exactly the Q1 ruling:

1. **Mint** — `POST /ui/login-codes`, authenticated by the **Bearer header** through
   `identity.validate` (the rest.py `_identity` idiom verbatim; adapters never construct
   an Identity from request data). Body: optional `scopes` (subset of the caller's) and
   `ttl_seconds` (bounded by the caller token's own `expires_at` and a configured
   ceiling). Narrowing is enforced structurally: `requested ⊄ granted` or
   `requested_expiry > caller.expires_at` → `forbidden` (NFR-S2: narrower allowed, wider
   never). The mint generates `code = secrets.token_urlsafe(32)` — random, opaque,
   encoding nothing — stores `sha256(code) -> {identity fields, expires_at =
   now + 60 s (configured), used=False}`, and returns `{"login_url": .../ui/login?code=…}`.
   The hash-keyed store makes the lookup timing-safe by construction (no string compare
   on the secret; I1's non-constant-time-compare LOW does not carry over).
2. **Exchange** — `GET /ui/login?code=…`: unknown/expired/used → rendered `unauthenticated`
   refusal (the §C.3 partial) and a server-side log line naming the refusal class, never
   the code. Valid → atomically mark used (single-use under the store lock), create the
   session, respond `303` to `/ui` (clean URL) with `Set-Cookie` and
   `Referrer-Policy: no-referrer` (GW-92; the header rides every `/ui` response).
3. **Logout** — `POST /ui/logout` (CSRF-checked, NFR-S4): deletes the session record and
   tears down its bridges; the cookie alone is dead from that moment (GW-94).
4. **CLI** — `benchweave ui-login --gateway-url … --token … [--scope observe]
   [--ttl-mins N]` in `cli/commands.py` (the `status` command's `GatewayClient` pattern),
   printing the URL. Obligation 23's sweep list applies (§8).

The code's URL transit is once, by design; the log-exposure risk it creates is real and
is handled explicitly: uvicorn access logging would otherwise record the query string.
`serve` configures uvicorn with the access log's query strings suppressed for `/ui/login`
(the log-format arm is part of the acceptance matrix — the exit gate's "no code
observable in … logs" is a test, not a hope).

Configuration: `ui_login_code_ttl_ms` (default 60 000), `ui_session_ttl_ms` (default
28 800 000 = 8 h), `ui_max_bridges_per_session` (default 4) join the `app_entry._LIMITS`
table with env overrides parsed fail-loud. These are service/security parameters in the
existing limits table (the `max_json_bytes` class), not bench safety envelopes — A02's
commissioning rule governs bench hazards, not gateway session knobs; defaults are
hints, deployment-tunable, and the mint's narrowing bound is the caller token's expiry
regardless of the default.

### 2.3 Security middleware (NFR-S4–S7), the I1 guard set adapted

Each guard an individual middleware object on the `/ui` routes (I1 `security.py`
precedent, so acceptance arms can construct the app minus exactly one guard):

| Guard | Mechanism |
|---|---|
| Trusted-Host | port of I1's `_host_is_trusted` logic (bracketed IPv6, port match, `localhost` ⇒ loopback bind) on every `/ui` request — DNS rebinding (NFR-S5) |
| CSRF | per-session token rendered into the page, sent by htmx `hx-headers`, checked server-side beside `Origin` on every state-changing route (G2: logout; the mechanism exists for G3) |
| CSP | `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'` on HTML responses — `frame-ancestors` from day one (I1's accepted-risk LOW is not carried); htmx configured via `<meta name="htmx-config">` (`allowEval=false`, `selfRequestsOnly=true`); a template test refuses any `<script>` without `src` |
| Body cap | `max_json_bytes` on the mint POST (the rest.py `_json_body` idiom) |
| CORS | none on `/ui` — no headers, ever |

### 2.4 Read views over the 12 operations (GW-10–14, 20–23, 55, 60–61, 80–81)

Page templates live in the **gateway host** (`src/benchweave/interfaces/ui_templates/`,
wheel-shipped — the hatch config addition rides the same commit; the `package.yml`
installed-tree census catches a drop). Hosts own pages; the package owns components
(UR-01). Every handler is the rest.py three-step translation with the Identity source
swapped: session cookie → `SessionStore.resolve` → seam call → render; failures render
through the shared `refusal.j2` (GW-11) with `correlation_id` shown, `not_found` as
"unavailable to this caller" (GW-14), and no code rewritten softer.

Routes (all read): `/ui` (index: `gateway_info` + `bench_list` + the session's principal
and scopes — GW-81), `/ui/benches/{id}` (`bench_get` + `device_list` + first events
page + mode banner GW-80), `/ui/benches/{id}/devices/{id}` (`device_get` + the plugin
presentation page), `/ui/runs/{id}` (`run_get`), `/ui/requests/{request_id}`
(`run_find` — the reconcile view GW-12 names), `/ui/evidence/{id}` (`evidence_get`),
`/ui/artifacts/{id}` (chunked download looping `artifact_read` within
`max_chunk_bytes`, complete digest verified before the response completes — GW-60/61),
`/ui/documents/{sha256}` (`document_get`, digest shown), plus `/ui/assets/{path}`
(vendored assets, inventory-verified at construction).

Device pages (GW-21–23): resolve the plugin's presentation attachment from admitted
documents, validate through the gateway's own validator
(`presentation/admission.py::validate_attachment` — the SW-41 parity surface; the
standalone host uses the SDK's bytes, the gateway uses these bytes), and render panels
with the ui-html partials per `manifest.py`'s grammar. Required panels the host lacks
render `panel_unavailable` (SW-41's rule, as a refusal); optional panels render
unavailable. Readings are observations (GW-22): tiles populate only from gateway-reported
data — in G2, run evidence and projections (§1's finding); staleness via
`staleness.py` from the observation's own timestamp (GW-23). There is no optimistic copy
anywhere and no reading tile in a live region.

GW-55's G2 half: run pages render status, ownership and terminal state exactly as
`run_get` reports them. The cancel-control wording ("cancel requested") belongs to the
G3 cancel control; G2 renders no mutating control at all — pinned by the observe-scope
test (§7).

### 2.5 The event bridge, `events_get` → SSE (GW-30–34)

`GET /ui/benches/{id}/events/stream` — Starlette `StreamingResponse`,
`text/event-stream`. One bridge per (session, bench): the `SessionStore` record holds
`bench_id -> BridgeState`; a second stream for the same pair is refused (`conflict`
rendered), the per-session count is capped by config, and the bridge deregisters in the
generator's `finally` — a closed tab ends every read made on its behalf (GW-33).

The loop (all reads on the session's Identity, server-held cursor — it never appears in
any response body):

- Poll `events_get(identity, bench, after=cursor, limit=…)` at ≥ `min_poll_ms`
  (advertised limit), emit one SSE event per bench event; one poll's batch is flushed
  together (the coalescing half of GW-34; the host script's per-frame swap batching is
  the other half).
- `OperationFailure(event_gap)`: emit a `bw-gap` SSE event carrying the failure's
  `details` watermarks (`stream_id`, `oldest_sequence`, `current_sequence` — the closed
  six-key object), restart the listing from `after=None` (the retained window replays;
  the browser dedupes by `(stream_id, sequence)` — the §7 rule), and the page renders
  the persistent §C.3 `event_gap` warning naming the watermarks (GW-31: it does not
  skip the gap) plus a re-read of the affected run/evidence views.
- `OperationFailure(cursor_expired)`: restart from `after=None`, dedupe by stable
  resource identity, render the advisory (GW-32). Induction is test-boundary only —
  the seam has no emitter (§1, §7).
- State changes announce through the page's ARIA live region; samples never do
  (GW-34/SW-26 — pinned as a template assertion, since no sample lane exists to drive
  it live).

The bridge runs on the serving event loop and `events_get` is blocking SQLite — this is
exactly D13's disclosed single-loop posture (bounded, non-material at PoC scale). The
acceptance matrix carries a bridge-load arm so G2 does not silently worsen it (§9 R1).

### 2.6 Vendored JS assets — the one package change

`htmx.min.js` and `sse.js` (byte-identical to the standalone's vetted pair — same
library version, sha256-pinned on landing) plus a new `bw-host.js` (generic host script:
htmx bootstrap, SSE connect driven by `data-*` attributes the templates emit, per-frame
swap coalescing, live-region announcements, theme handling) are added to
`packages/ui-html/src/benchweave_ui_html/assets/` with inventory rows; version bumps
0.1.0 → 0.2.0 (content addition, MINOR; `uv.lock` moves with the workspace member
version — a disclosed Tier-3 trigger, §10). This follows PRD §5/§9 Q5/UR-10 (the package
is the one asset home; one inventory serves both hosts) over the alternative of a
gateway-private asset copy, which would create a third home. The standalone host keeps
its own copies for now (§9 D5 records the convergence question — fixing the SDK side is
not G2's to do). The `publish-ui-html` release event is a separate owner call; the
gateway consumes the workspace path and does not wait for it.

## 3. Slice split — three, stacked

G2 is too large for one PR against the one-RED→GREEN-slice-per-commit discipline and the
review battery, and its trust boundary deserves its own refute. Three slices, stacked
(`base` = predecessor), merge bottom-up:

| Slice | Scope | Named exit items it carries |
|---|---|---|
| **G2a** session + shell + routing | session store, login-link mint/exchange/logout, CLI `ui-login`, the middleware guard set, `/ui` router composed before the mount with the off-flag, assets route + construction-time inventory verification, ui-html JS vendoring (first commits of the branch), the index shell with gateway identity strip and mode banner machinery | GW-01–04, GW-80–81, GW-90–94, NFR-S1–S9; GW-04 routing test green (both postures, pattern-library pin included); login-code refusal matrix green; I02 extension arm green |
| **G2b** read views | the eight read pages + plugin presentation pages through the validator, refusal rendering incl. the induced-code matrix, run_find view, observe-no-control pin, route-mapping test | GW-10–14, GW-20–23, GW-55 (render half), GW-60–61, NFR-Q1–Q4; route-mapping test green; observe session sees every read view |
| **G2c** live updates | the SSE bridge, server-held cursor, event_gap/cursor_expired handling, teardown, coalescing + ARIA, I09 extension | GW-30–34; event_gap and cursor_expired induced and rendered; I09 extended to `/ui` and green |

## 4. Precedent (principle 9 — extend, don't invent)

| Piece | Proven mechanism extended |
|---|---|
| Router-before-catch-all composition | `app.py:1040-1048` (REST include order, frozen by its own comment); `execution_corpus` keyword-only param (`app.py:924`) for `ui_enabled` |
| Adapter-over-seam handler shape, Identity from one source, `_guard` failure translation | `interfaces/rest.py` (`_identity`, `_guard`, `_json_body`) |
| Local issuer, fail-closed validation, injected clock | `interfaces/identity.py` |
| Events, cursors, watermarks, event_gap semantics | `operations.py::events_get` + `encode_cursor`/`decode_cursor` + `test_seam_events.py` |
| Cookie/CSRF/CSP/Trusted-Host/body-cap middleware as individually omittable guards; construction-time asset verification; vendored htmx/sse bytes + inventory | SDK standalone I1 (`benchweave_standalone/security.py`, `assets.py`, `ui_assets/` — PR #74, merged) |
| Component partials, staleness, manifest grammar, refusal rows as data, asset inventory + verify | `packages/ui-html` 0.1.0 (`partials.py`, `staleness.py`, `manifest.py`, `assets.py`) |
| Presentation validation | `presentation/admission.py::validate_attachment` (the gateway's own validator, already admission-proven) |
| Loopback-boot integration fixture, per-op transport arms | `tests/integration/test_interface_parity.py` (`_boot`, `_token`, module gateway fixture) |
| Env-driven limits, fail-loud parse | `app_entry.py` (`_LIMITS`, `_QUOTA_ENV_KEYS`) |

New architecture introduced: the session store and the SSE bridge — both are the
smallest mechanisms satisfying ruled requirements (Q1; GW-30–34) for which no in-tree
equivalent exists (verified: I1 defers its SSE/coalescing to I2; nothing in the gateway
streams). The bridge reuses the seam's own cursor/restart rules rather than defining new
stream semantics.

## 5. Root cause / why this is the right shape

The gateway has no browser surface because it never needed one; every operator surface
today is a client (REST/MCP/CLI/TUI) holding a bearer token. The browser cannot hold a
bearer token (NFR-S1 — script-readable storage), so the gap is not "serve some HTML" but
"map a cookie to a validated, narrowable Identity without ever exposing the token" —
which is why the session layer is slice G2a and an invariant candidate (§8), not a
template detail. The read views themselves are thin: the seam already answers every
question they ask, the contract already defines every refusal they render, and the
package already renders every component they compose. The design's real decisions are
the three the PRD left open at this level: where the JS assets live (§2.6 — the ruled
package, evidenced against I1's deviation), how `cursor_expired` is proven without an
emitter (§7), and what "readings" honestly means over a read-only interface (§1, §9 D4).

## 6. Minimal first increment

G2a as scoped in §3 — nothing else. Its first commits are the ui-html JS vendoring
(copy bytes, inventory rows, version bump; RED = census/inventory arms fail without the
files), then the session store (RED = the refusal matrix's expired/replay/narrowing arms
fail against an empty store), then the router + middleware (RED = GW-04 and the
minus-one-guard arms), then the CLI command and its doc sweep.

## 7. Measurable proof — pre-committed acceptance rule

Deterministic functional gates; no sampling. Every count from `--junitxml` attributes or
TRUE exit codes (never a filtered summary line); `UV_PROJECT_ENVIRONMENT=venv` on every
invocation; fast lane per commit, cold full battery + both tripwires
(`git diff origin/main...HEAD -- standards/` empty; no version-string touches) before
each push.

**A. GW-04 routing (G2a).** For the composed app with UI on: `/v1/benches` (bearer) →
REST JSON; `/ui` (session) → HTML; `POST /mcp` → MCP; an unknown `/ui/nope` → the UI
router's own 404 shape (never an MCP envelope); `/ui/patterns/**` and every
pattern-library path → 404 (obligation 25's pin, closing that row). With UI off: every
`/ui` path → the mount's 404 (absent, not stubbed). SHIP iff all six hold.
**MECHANISM-TOGGLE CONTROL:** delete the include-order (move the include after the
mount) on a scratch copy → the `/ui` ownership assertions must RED.

**B. Login-code matrix (G2a).** Mint → exchange: 303 to a code-free URL, cookie set with
all four posture attributes, `Referrer-Policy: no-referrer` present. Then, each RED-able
alone: replay of a used code → rendered `unauthenticated` + logged; expired code
(injected clock past TTL) → same; unknown code → same; narrowing: `--scope observe` from
a control token yields a session whose bridge/pages refuse control-tier seam calls; a
wider request (scope outside the caller's, TTL past the caller's expiry) → mint refused
`forbidden`; logout → cookie replay dead; app re-construction (new store) → cookie dead.
Log exposure: boot the parity-style uvicorn server, run a full mint+exchange, assert the
code string appears in **no** captured log line (access log included — the suppression
arm). SHIP iff every arm holds; KILL if any replay/expiry arm passes.
**MECHANISM-TOGGLE CONTROL:** neutralize the single-use marking → the replay arm must
RED.

**C. I02 extension (G2a/G2b).** In the parity fixture's shape (same `_boot` pattern):
session for principal p1 on bench A — request bench B's device page, events stream, and
evidence → every one renders `not_found` as unavailable-to-caller (cross-bench reads
refused); no `/ui` route accepts any principal/identity parameter (grep the route
signatures + a posted-principal probe is ignored/refused). SHIP iff both hold for every
read route.

**D. Route-mapping (G2b).** Enumerate the mounted `/ui` routes from the app object;
every mutating route must map to exactly one of the eight operations via the route
registry (`UI_ROUTES` specs; session-layer routes are explicitly flagged non-interface —
the mint/exchange/logout trio is the complete non-interface set, itself asserted). SHIP
iff the enumeration matches the declared set exactly. **KILL CONTROL:** a planted
mutating route without a mapping must RED the test (proving the test polices, not
documents).

**E. Observe-no-control + read-view completeness (G2b).** An observe session renders
every read view in §2.4 (each page 200, its seam data present) and contains no enabled
mutating control: assert no form/button on any rendered page targets a mutating method
on a non-session route, and (belt) a direct POST to any mutating `/ui` route that exists
is refused for `observe` scope. SHIP iff both hold.

**F. Refusal matrix, NFR-Q2 (G2b).** One arm per §C.3 code (15 + `no-response`): induce
each code on a `/ui` read route — real inductions where the read wire allows (unknown
id → `not_found`; expired session → `unauthenticated`; cross-bench → `not_found`;
cross-principal → `not_found`; body over cap on the mint → `payload_too_large`;
monkeypatched seam refusal for the classes the read wire cannot produce naturally
(`conflict`, `policy_denied`, `not_ready`, `gone`, `rate_limited`, `unavailable`,
`internal_error`, `cursor_expired`, `event_gap`) — and assert the rendered refusal
carries the parsed row's severity, sent-status wording and operator action, plus a
`correlation_id`. `no-response` renders sent status `UNKNOWN` with the `run_find`
reconcile action present. SHIP iff all 16 arms hold. Induced-not-emitted classes are
labelled as such in the test docstring (the honesty rule).

**G. Event bridge (G2c).** Real induction for `event_gap`: drive emissions, `trim_stream`
past the bridge's cursor → the SSE stream yields the `bw-gap` event with the failure's
exact watermarks, the page renders the persistent warning naming them, and the stream
continues from the restarted listing with dedupe (no sequence delivered twice).
`cursor_expired` induced via a seam double at the bridge boundary (the disclosed
no-emitter fact; §1) → restart, dedupe by `(stream_id, sequence)`, advisory rendered.
Teardown: abort the SSE request → the bridge deregisters (a subsequent stream for the
same pair starts clean; the per-session cap refuses a fifth). Coalescing: a burst of N
events in one poll window yields one flush boundary. Cursor privacy (I09): assert no
response body on any `/ui` route contains a cursor-shaped value (the bridge's cursor is
server-held; this is the I09 extension arm together with the cross-principal bridge
refusal in C). SHIP iff every arm holds. **MECHANISM-TOGGLE CONTROL:** disable the gap
restart → the dedupe/continuation arm must RED.

**H. Browser lane (G2b/G2c, `-m browser`).** One module-scoped in-process server
(the parity suite's `_boot` pattern: a uvicorn thread on an ephemeral loopback port)
serving the composed app with seeded fixtures; Playwright+axe at WCAG 2.2 AA on every gateway page
template, both themes; the planted-violation control from G1d's lane applies; the
component-CSS obligations inherited from obligation 26 (interactive targets ≥ 24 px; no
glow on normal/limiting readings; limiting border exactly `var(--bw-limiting)`) assert
in the same lane. SHIP iff axe clean on all pages × themes and the CSS pins hold.

**I. Asset verification (G2a).** Tamper one vendored byte on a scratch copy →
`create_app` refuses to compose, naming the asset. SHIP iff the refusal fires before
any route exists.

**Ship it if** A–I all hold on the implementing agent's run with outputs recorded, and
each slice's battery is green before its push. **Kill it if** any mechanism-toggle
control stays green (the tests don't discriminate), any B-arm replay/expiry/widening
case passes, or the bridge delivers a duplicated sequence after either restart. Kill
also if the ui-html vendoring's wheel census fails (packaging dropped the JS bytes).
**Underpowered, not conclusive:** Playwright/browser-environment failures (fix and
re-run — no verdict until a clean lane run); Windows-leg flakes (the windows lane is
evidence-posture, not gating — record on #207 per its doctrine); uv/port environment
failures. A bridge-load regression beyond D13's disclosed posture is a HOLD named to the
owner with numbers, not an automatic kill (§9 R1).

## 8. Invariant, drift, and CI impact

- **CTL/STO/REG: untouched.** No `control/`, `state/`, or `registry/` bytes move; G2
  adds no protective behavior and no store change. A04 is honoured structurally: nothing
  in G2 requires an AI or a live client for protection or completion — the UI is
  read-only, sessions expire server-side, and a closed tab stops nothing but reads.
- **A06:** `no-response` renders sent status `UNKNOWN` with a reconcile action; refusal
  rendering never rewrites a code softer; ambiguous outcomes stay ambiguous on the page.
- **A13/CON-5:** the UI is a third adapter over the seam. Proposed amendment (lands with
  G2b): *CON-5 amendment (2026-10, G2): the `/ui` session adapter is a third transport
  over the one seam; its identity comes only from the server-side session, its refusals
  render the contract envelope's own code, and the I02/I09 suites cover it like REST and
  MCP.*
- **New invariant proposed (lands with G2a):** *CON-15: browser sessions are server-side,
  cookie-mapped, at-most-as-wide projections of a validated Identity — the cookie carries
  an opaque id only; scopes and expiry live server-side; narrowing is permitted and
  widening is structurally refused at the mint; logout, expiry and gateway restart
  invalidate server-side; the bearer token never reaches the browser —
  `src/benchweave/interfaces/sessions.py`.* (Anchored on the module contract; the
  acceptance B-matrix is its first enforcement.)
- **On-disk formats/schemas:** none. No `standards/` bytes, no interface-catalog motion,
  no store schema. The ui-html inventory gains rows (package data, not a persisted
  gateway format); `uv.lock` moves with the workspace member's version bump — a
  disclosed Tier-3 trigger, not a dependency add (Jinja2/MarkupSafe unchanged).
- **Obligations (drift-and-obligations.md):** 4 (operator-guide, README, the CLI
  reference rows for `ui-login`); 9 (the systemd env example gains `BENCHWEAVE_UI` and
  the three session knobs); 12 (the serve-time verification wiring — **landed here**,
  closing its "wiring lands with G2" clause; the row's wording updates in the same
  change); 23 (the CLI sweep: operator-guide §10 both tables + the website CLI card; the
  docs-site standards-CLI page does not regenerate for the `benchweave` CLI); 25 (the
  pattern-library routing pin — **landed here**, closing the row); 26 (the component-CSS
  obligations — carried by the host CSS, asserted in lane H).
- **CI cost:** `gates` grows by the new unit/integration suites (no browser marker —
  excluded there by construction); `browser` grows the server-based axe arms (one
  module-scoped server; the lane stays serialized); `windows` inherits via its selection
  (evidence posture); timing untouched; `package`'s wheel census automatically covers
  the gateway's new template dir and ui-html's new assets; `publish-ui-html` unaffected
  until a release event.

## 9. Deferrals (each with home + reopen trigger)

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | Session-expiry warning UI (Q2 floors applied to sessions, GW-44's session half) | G3 (#304) design record | the G3 design record is committed on its branch |
| D2 | Mutating-form wiring: server-generated `request_id` fixed at render (GW-13), `no-response` reconcile action submit (GW-12's action half), GW-55's cancel-control wording | G3 (#304) | the G3 design record is committed on its branch |
| D3 | Chart hydration for `engineering-plot`/`digital-lanes` skeletons (ECharts or the ruled alternative) | #310's plot slice (PRD 11 Q12) | #310's ruling landing (G2 renders the contract-compliant skeleton + legend + description; no draw claims) |
| D4 | Live sample updates on device pages — the read-only interface carries no sample lane (six state-only event kinds; no reading values in projections). Readings render from retained observations. If live tiles are wanted, that is an interface capability change (a sample-bearing observation read), raised upstream, not a UI route | this record + #303's exit note (owner fork F1' below) | the owner's call on this record, or an interface issue being filed for a sample-bearing read — whichever first |
| D5 | ui-html ↔ standalone asset convergence (I1's own `ui_assets` vs the package's one-inventory rule; CSS already byte-identical) | I2 (#284) / the standalone lane; G2 only discloses | the I2 design record, or any standalone release consuming ui-html ≥ 0.2.0 |
| D6 | `change_get` page (the one read operation without a G2 view — administration owns the change UX) | G4 (#305) | the G4 design record is committed on its branch |
| D7 | Manual theme override (light/dark toggle); G2 serves `prefers-color-scheme` only | G3's UX polish rows | the G3 design record, or the owner's earlier call |
| D8 | `frame-ancestors`/CSP hardening beyond §2.3 (permissions-policy, referrer on non-UI surfaces) — only if a review lane finds a gap | design-record deferral row | any Tier-3 refute finding on the G2a guard set |
| D9 | Bridge-load measurement follow-up if the §7-G acceptance arm shows material p95 movement (D13's posture) | #303's exit note | the acceptance arm's numbers exceeding D13's disclosed bands |

## 10. Review tier (Step-1 call, rubric #254) and keyword scan

**Tier 3 — maximum across the three slices**, by multiple independent rules: (i) the
keyword rule over the expected diff text (below); (ii) `uv.lock` motion via the ui-html
version bump (G2a); (iii) a new network-serving auth surface (G2a) and a new concurrent
subsystem (G2c) — the Tier-3 lane is the right depth regardless. Consequences: the
two-lane adversarial refute per slice (Tier-3 doctrine) and the cold full battery. The
standards-governor mandate does NOT fire: no `standards/` bytes, no vendored-tree edits,
no version-string literals (the UI derives nothing from corpus version strings;
`gateway_info` carries versions as data).

Keyword scan over the expected diff text (new `src/benchweave/interfaces/{ui,sessions}.py`
+ templates, `cli/commands.py` additions, `packages/ui-html` asset additions +
inventory, new `tests/interfaces_ui/` + browser arms, deploy/env + docs sweeps, and this
record — docs and code alike; estimates of the expected diff, re-derived over the real
diff at each review):

| keyword | expected count | where |
|---|---|---|
| `asyncio` | ~8 | bridge + tests (5), record (3) |
| `threading` | ~4 | session store lock + parity-boot reuse (2), record (2) |
| `subprocess` | 0 | — |
| `sha256` | ~14 | login-code hashing + inventory rows + tests (9), record (5) |
| `hashlib` | ~5 | sessions/assets code (3), tests (1), record (1) |
| `migrate` | 0 | — |
| `recovery` | ~2 | record prose only |
| `protection` | ~3 | record prose only (G2 renders no protection-disabled controls; `protection-active` first appears in G3 diffs) |

## 11. Top risks, each with its falsifier

- **R1 — bridge load on the disclosed single-loop posture.** N bridges × polling adds
  blocking reads to the event loop (D13's accepted posture). Falsifier/control: the §7-G
  load arm (4 sessions × capped benches, p95 of concurrent reads vs the D13 bands);
  mitigation if material: fewer bridges per session or a threaded poll lane (a HOLD with
  numbers, D9 — not a silent change).
- **R2 — the login code leaks through logs despite the URL design.** Falsifier: the §7-B
  log-capture arm (any hit kills). The uvicorn access-log suppression is part of the
  mechanism, not an ops note.
- **R3 — cookie/CSRF/CSP fights htmx bootstrap** (I1's R2). Falsifier: any template
  needing inline script; the template test makes it a failure, not a temptation.
- **R4 — `cursor_expired` proof reads as faked.** Mitigation: §1's disclosure + the
  labelled seam-double induction; the honest statement is that the gateway cannot emit
  it today, so G2 proves the *behaviour* (restart/dedupe/advisory), not an emission.
- **R5 — cross-train collision with I2 (#284, in design in parallel) over
  `packages/ui-html`.** Mitigation: G2's package change is additive (new files, new
  inventory rows, version bump); merge rule: first landing wins, the other rebases; both
  records name it. Falsifier: a nontrivial semantic conflict at rebase.
- **R6 — wheel packaging drops the gateway's page templates or the new JS assets.**
  Falsifier: the `package` lane's installed-tree census (both directions) — it reds at
  PR time, by construction.
- **R7 — scope creep into G3 (lease UI, staging, cancel).** Falsifier: any mutating
  `/ui` route beyond the session trio at G2 review; the §7-D enumeration is the tripwire.

## 12. Maintainer decisions (forks, not blockers)

- **F1' (D4):** accept observation-only readings for G2 (recommended — it is the
  interface's honest read surface), or file the interface issue for a sample-bearing
  observation read now.
- **F2:** `BENCHWEAVE_UI` default — recommended ON (loopback posture, the flag disables);
  the alternative (default OFF until G3) is one line in `app_entry`.
- **F3:** the ui-html 0.2.0 release event timing (the gateway rides the workspace; PyPI
  publication is the `publish-ui-html` trigger and can trail the G2 merges)

## 13. Addendum (2026-10-03, G2c fold wave — corrects §2.5's consumer-side sentences)

The two-lane refute of the G2c build returned one converged MEDIUM and two LOWs; the
folds and the rulings that narrowed §2.5's claims, recorded here so the record does not
out-run the mechanism (rubric G4):

- **Dedupe is the server-side high-water mark.** §2.5 said "the browser dedupes by
  `(stream_id, sequence)`". No browser dedupe exists and none is needed: the bridge
  itself never puts a sequence on the wire twice (the per-stream high-water mark over
  EMITTED rows — advanced only over rows a flushed fragment actually carried), and the
  host script's swap REPLACES the region's content, so a hypothetical duplicate is
  structurally inert client-side. The kill criterion's "the bridge delivers a
  duplicated sequence" is enforced at the producer.
- **Announcements are the named-event listeners, not every state change.** §2.5's "state
  changes announce through the page's ARIA live region" reads as a per-change
  announcement. What exists: the `bw-gap` listener announces the gap (and, from this
  fold wave, `bw-end` announces stream termination) through the one
  `data-bw-announce` region. Ordinary event swaps do NOT announce — announcing every
  swap is chatter, not access (the refuted row, narrowed here rather than built).
- **One flush per poll tick, no row cap.** §2.5's "one poll's batch is flushed
  together" resolves to: the tick drains the retained window (pages with the returned
  cursor until a short/empty page) and flushes ONE message event carrying every
  drained row. The interim 20-row render cap silently dropped the remainder while the
  dedupe mark advanced past it — the converged MEDIUM, fixed with the paging drain.
- **SSE framing splits only on CRLF/CR/LF.** `str.splitlines` also splits on Unicode
  separators that are not SSE terminators; the framing now uses the grammar's own set.
  Latent (all fragment fields are gateway-minted), pinned by the round-trip arm.
- **Observation, no fix (a refuted row):** a stream whose bench row is deleted while
  events remain retained keeps serving — faithful to the seam's own guard
  (`events_get` checks bench existence only when the stream is empty); disclosed for
  the PR body, not changed here..
