# Issue #283 — Standalone web UI, increment I1 (skeleton over MockHost): design record

**Date:** 2026-10-01 · **Tracker:** madeinoz67/benchweave #283 (sub-issue of epic #282)
**PRD:** `docs/implementation-planning/11-standalone-web-ui-prd.md` (§6 a–d.1, §7 NFR-S/NFR-P, §8 Q1/Q2/Q10, §9 I1 row)
**Evidence baseline:** gateway `origin/main` `132ead6`; SDK `origin/main` `8062392` (the standalone checkout at
`~/Documents/src/benchweave-sdk` — local main was behind; re-branch from `origin/main` when building).
Files read for this record: SDK `interfaces.py`, `preview_server.py`, `capture.py`, `testing.py`, `scaffold.py`,
`presentation.py` (compressed), `cli.py` (compressed), `served.py` (compressed), `pyproject.toml`; gateway
`src/benchweave/interfaces/app.py:940–1052`; `docs/internal/{invariants,drift-and-obligations,review-rubric}.md`;
`docs/smart-test-gateway-decisions.md`; `.claude/deep-review/README.md`.

---

## 1. Problem (root cause, evidenced)

Standalone mode has no operator surface. The SDK ships an authoring preview (`preview-ui`: simulated data, React
renderer, stdlib HTTP) and a capture writer, but nothing that imports a plugin's Python, drives its adapter and
serves readings/UI/REST/MCP without a gateway. The scaffold's own seeded skill says it outright
(`scaffold.py`, develop-plugin skill §4): *"The SDK ships no MCP server. To use this plugin standalone, write a
project-local MCP server … Keep it out of the distributed package unless the owner decides otherwise."* Every
plugin author hand-rolls one; the fork cited in the PRD hand-rolled all three surfaces for one board.

I1 is the first shippable slice of the PRD's answer: one process serving HTMX UI + REST + in-process MCP over one
operations seam, over `MockHost`-class scripted transport — mock first, hardware in I3, the same order the
gateway took.

## 2. Placement (PRD §8 Q1) — decided for this increment

**Adopt the PRD's recommendation: option 2, a sibling distribution in the SDK repo — landing in a
relocation-cheap subtree until Q1 is formally ruled.**

- New subtree `standalone/` in the **standalone SDK checkout** (`~/Documents/src/benchweave-sdk`, branch off
  `origin/main`), own `pyproject.toml` (`benchweave-standalone`), own `src/benchweave_standalone/`, own tests,
  own uv lock. **Never `packages/sdk`** (deinitialized main-side; the SDK-workspace directive).
- Relocation design: the subtree is self-contained — its only repository coupling is the dev-only path source
  `[tool.uv.sources] benchweave-sdk = { path = "..", editable = true }` (not wheel metadata) and one CI workflow.
  Moving to its own repo later is a `git mv standalone/` + path flip + workflow copy. Q1's formal ruling is
  scoped to I3 by the PRD (§9: "Q1 … ruled" at I3) — this is the PRD's own "throwaway package path" note.
- **PKG-1/PKG-2 hold structurally:** zero bytes move under `src/benchweave_sdk/`, the root `pyproject.toml`,
  `standards-lock.json`, or `hatch_build.py` — enforced as an acceptance check (E below), not a promise.
- **No uv workspace is declared** (that would edit the root pyproject); commands run
  `--project standalone` / from inside `standalone/`.
- Two-repo implications: the implementation branch + PR are SDK-repo-side, tracking gateway issue #283 on the
  single issue stream (the SDK tracker is retired; the SDK PR body notes that no SDK-side issue exists by
  design). This design record itself commits to the **gateway** branch `feat/issue283-i1-skeleton` (records are
  committed artifacts where the issue lives). Main-repo bytes otherwise do not move in I1.

**Owner-confirm fork (not blocking):** MCP tool namespace. The design adopts the PRD's Q4 recommendation
`bws_v1_*` (own namespace, interface-0.1.0-shaped where semantics match) so agents cannot assume gateway
guarantees from familiar `stg_v1_*` names. If the owner prefers Q4 option 1, only the catalogue's name-prefix
constant changes.

## 3. The mechanism

### 3.1 Composition — mirror `interfaces/app.py`, minus gateway state

```
build_app(seam, *, security) -> FastAPI
    FastAPI(lifespan=_lifespan)          # SW-01
    app.include_router(rest_router(seam, security))     # /v1 JSON + / HTML routes, included FIRST
    mcp_app = build_mcp(seam, security).http_app(path="/mcp")
    app.mount("/", mcp_app)              # /mcp lands; REST already won /v1  (app.py:1040–1048 precedent)
    @_lifespan: async with mcp_app.lifespan(app): yield   # combined lifespan (app.py:1018 — FastMCP's
                                                          # http_app lifespan MUST run on the host or
                                                          # initialize 500s)
```

The gateway precedent (`src/benchweave/interfaces/app.py:985–1048`) is copied shape-for-shape with the store,
worker, write-gate and recovery sweep removed: standalone has no leases, policy, runs or second-writer hazard
(SW-04: one adapter session per process; a second device is a second process).

### 3.2 The operations seam (SW-10–13) — one closed catalogue behind all three surfaces

`standalone/src/benchweave_standalone/catalogue.py`:

- `OperationSpec(name, implemented, input_schema, result_schema, error_codes)` and
  `CATALOGUE: tuple[OperationSpec, ...]` — **the full closed SW-10 set of 18 names**, defined as data on day one.
  I1 marks six implemented (`host_info`, `device_discover`, `device_connect`, `device_disconnect`,
  `device_get`, `parameter_read`); the rest carry `implemented=False`.
- Unimplemented operations are **refused, never silently absent from the catalogue**: the seam answers
  `unavailable` with `correlation_id` and a `reason: "increment_deferral"` detail; `host_info` reports the
  served and deferred sets so an agent cannot assume a capability (the SW-32 honesty rule applied to our own
  roadmap).
- Error vocabulary (SW-11): the interface 0.1.0 codes the PRD names (`invalid_request`, `not_found`,
  `conflict`, `not_ready`, `payload_too_large`, `unavailable`, `internal_error`) + `correlation_id`;
  `policy_denied`/`forbidden`/lease codes are **structurally absent from the catalogue's code set** (there is
  no policy engine to deny). Machine authority: the code list is pinned by a test against the SDK's
  digest-verified vendored `standards/interface/0.1.0/operation-catalog.json`
  (`benchweave_sdk.served.vendored_root()` after `verify_vendored_digests()` — CON-4's discipline, one reader,
  no local copy of the standard).
- `StandaloneSeam.call(operation, arguments, correlation_id)` is the only mutation path; REST handlers, HTML
  routes and MCP tool bodies are adapters over it (A13's one-contract rule; parity tests pin each transport to
  the catalogue, never to the sibling transport — the WP07 lesson).

### 3.3 Session manager and the live mock transport

`session.py` owns the adapter lifecycle exactly as `DevicePlugin` discipline requires (REG-1): import with no
side effects via the descriptor's `integration.adapter.entry_point` (project `src/` on `sys.path`), one
`open(descriptor, services, context)`, per-operation contexts, idempotent-tolerant `close`.

- `HostOperationContext` (in-package): `operation_id`, `dataset_id=None`,
  `deadline_monotonic = time.monotonic() + timeout_ms/1000` where `timeout_ms` comes from **the descriptor's own
  operation policy** (SW-13 bounded by declared policy, not a host-invented constant — A02's posture: the
  plugin's declared bound is the bound; the host adds no uncommissioned envelope), cooperative `cancel()`,
  `mark_dispatch_started()`.
- `LoopingMockHost(MockHost)` (in-package subclass of `benchweave_sdk.testing.MockHost`): the scaffold's
  generated adapter speaks exactly two exchanges (`scaffold.py` `PROTOCOL`:
  `ID?\n → "SDK Example,demo,SIM001,1.0.0\n"`, `V?\n → b"3.3\n"`, `stream_exchange`, `max_bytes` 128, `lf`).
  `MockHost` is finite-script — a live server would exhaust it on the second poll. The subclass (a) stores a
  deepcopy of the original script and restores it when the deque empties (`cycles=None` loops forever;
  `cycles=k` is the exact-finite control used by the acceptance RED arms); (b) overrides the clock reads to
  real time (`monotonic() -> time.monotonic()`, real `utc_now()`) and the deadline/cancellation check to judge
  on that same clock, so inherited expiry arithmetic stays honest on live deadlines. Everything else —
  exact-dict matching, dispatch-marker enforcement, `ConformanceError` on mismatch, evidence recording — is
  inherited unchanged from the tested SDK class. The SDK file itself is not touched (PKG-2).
- Operation→verb mapping: `device_get` → `identify`; `parameter_read` → `read {parameter}`; adapter result
  envelopes pass through with `status`/`error.code`/`dispatch_state` preserved end-to-end (SW-12: permission,
  transport and device rejection stay distinct outcomes; REG-2's ambiguity-preservation is the seam's pass-through rule).

### 3.4 REST + HTML (SW-20–21, SW-27)

- `/v1/*` JSON routes generated from the implemented catalogue (request bodies validated against
  `input_schema`); OpenAPI for free at `/docs`.
- HTML routes (Jinja2 templates, no build step): `/` (shell: banner + device summary + link), `/devices/{id}`
  (readings page), plus one HTMX poll partial for readings (`hx-trigger="every 2s"`, server-rendered —
  coalescing/SSE is I2's SW-26). Read-only in I1 except connect/disconnect buttons (state-changing ⇒ CSRF).
- **I1's device page renders from the DESCRIPTOR** (readable parameters as reading tiles: name, value, unit,
  quality) — presentation-manifest-driven rendering (pages/bindings/plots from `plugin-ui 0.2.0`) is I2's
  SW-40–43. The scaffold's `presentation.json` is **validated at startup** (SW-05) but not yet rendered. This
  boundary is deliberate scope control, not an omission.
- Persistent banner on every page (base template): **`STANDALONE — no gateway`** — distinct from preview's
  `SIMULATED PRESENTATION DATA` (SW-27); the page also names the loaded plugin package/version (NFR-S7
  disclosure).

### 3.5 Tokens, vendored and digest-verified (SW-21, NFR-P3)

`standalone/src/benchweave_standalone/ui_assets/`: `tokens.css`, `themes.css` vendored **byte-for-byte from the
gateway repo's `ui/src/styles/`** (the canonical UI corpus), plus `htmx.min.js` + its SSE extension, plus
`inventory.json` in the `preview_assets` shape (`{api_version, assets: [{path, size, sha256}]}`). A serve-time
verifier mirrors `preview_server.verify_bundled_assets` (same traversal refusals, prefixed
`standalone_ui_asset_*`) and runs at app construction — tampered or missing assets refuse startup. Templates
link only vendored, inventory-hashed files; `themes.css` light/dark follows `prefers-color-scheme` (manual
override is I2). The cross-repo freshness gate is deferral D5 (§7).

### 3.6 MCP surface (SW-30–32, SW-35, NFR-S8)

- One tool per **implemented** catalogue operation, `bws_v1_<operation>`, registered via
  `mcp.tool(fn, name=..., description=..., parameters=<spec.input_schema>, output_schema=<spec.result_schema>)`
  — schemas are handed over explicitly from the catalogue, never inferred from the Python signature (CON-3's
  lesson applied to a non-corpus tool set: inference drift would put the host out of conformance with its own
  catalogue; pinned by acceptance F). Lease/run/bench tools are absent, not stubbed (SW-32).
- `host_info` returns `mode: "standalone"`, the absent-guarantees list (`leases`, `policy`, `approvals`,
  `procedures`, `runs`), served/deferred operation sets, plugin identity + descriptor digest, transport kind,
  and the SDK version **derived** via `importlib.metadata.version("benchweave-sdk")` (no version literal —
  obligation 18's closing clause).
- `stdio` entry (SW-03): `benchweave-standalone mcp <plugin project>` runs the same FastMCP server over stdio,
  no HTTP listener, no listener/Host/CSRF checks (NFR-S4). Q5's default-choice ruling (proxy vs in-process for
  agent-launched servers) stays with I3 as the PRD schedules it.
- **Authoring tools (SW-35, NFR-S8):** `plugin_new` (composing `scaffold.create_project` +
  `presentation.create_ui_resources` for `--with-ui`, exactly as `cli.py new` does), `plugin_check`
  (`validation.validate_descriptor`), `ui_check` (`presentation.validate_presentation` via the
  `check_ui`/`load_validated_preview_inputs` path with the plugin's real document paths). Results carry the
  SDK's stable diagnostic codes and paths. These three tools exist **only** when the host starts with
  `--authoring`; without the flag they are absent from the tool list, not refused on call (test-pinned).
  `preset_check`/`inventory`/`standards_check` and the SW-36–39 patch/reload/test loop land with I2 (D6).

### 3.7 Security (NFR-S1–S6) — each guard an explicit middleware object

| Guard | Mechanism | Precedent |
|---|---|---|
| Listener | `preview_server.validate_listener` called verbatim from the SDK (loopback default, wildcard refused, `--allow-network` + warning) | `preview_server.py` `validate_listener` |
| DNS rebinding | trusted-Host middleware on every request (HTML, `/v1`, `/mcp`) porting `_host_is_trusted`'s logic (bracketed IPv6, port match, `localhost` ⇒ loopback-bound) | `preview_server.py` `_handler._host_is_trusted` |
| CSRF | per-session token in the page, sent by HTMX `hx-headers`; `SameSite=Strict` cookie; every state-changing HTML route verifies | PRD NFR-S3 |
| REST mutations | per-launch bearer token, generated at startup and printed with the URL; mutations without it refused | NFR-S3 |
| MCP over HTTP | `Origin` allow-list (loopback origins only) + the same per-launch token ahead of the FastMCP app (fail-closed ordering — the CON-6 shape at one layer; stdio exempt) | NFR-S4 |
| CORS / CSP | no CORS headers anywhere; CSP `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'` on HTML — htmx configured via `<meta name="htmx-config">` (`allowEval=false`, `selfRequestsOnly=true`), never inline script; a template test refuses any `<script>` without `src` | NFR-S5 |
| Body cap | 64 KiB request cap middleware (`payload_too_large` refusal) | `MAX_REQUEST_BYTES`, NFR-S6 |

The `serve` CLI constructs the complete guard set unconditionally; the guards' being individual middleware
objects is what lets the acceptance RED arms construct an app minus exactly one guard (§5 D). Startup
validation order (SW-05): descriptor + presentation validate **before** the port binds; refusal
`standalone_plugin_invalid:` carries the SDK diagnostic codes (snake_case-prefixed, SW-05).

## 4. Precedent table (extend, don't invent)

| Piece | Proven in-tree mechanism being extended |
|---|---|
| App factory, `/mcp` mount, combined lifespan, REST-before-mount | `src/benchweave/interfaces/app.py:985–1048` |
| One seam behind REST+MCP, catalogue as authority | `interfaces/operations.py` `Operations` + `standards/interface/0.1.0/operation-catalog.json` (A13/CON-5) |
| Explicit MCP schemas, no inference | `interfaces/mcp.py` vendored-exact registration (CON-3's rule, applied to an in-package catalogue) |
| Listener/trusted-Host/cap/vendoring | `preview_server.py` `validate_listener`, `_host_is_trusted`, `MAX_REQUEST_BYTES`, `verify_bundled_assets`/`bundled_assets` |
| Adapter lifecycle + contexts | `host/plugin.py` `DevicePlugin` discipline; `scaffold.py` ADAPTER template is the conforming client |
| Scripted transport | `testing.py` `MockHost`/`MockContext` (subclass; SDK bytes untouched) |
| Digest-verified standards reads | `served.py` `vendored_root()`/`verify_vendored_digests()` (CON-4) |
| Authoring calls | `scaffold.create_project`, `presentation.create_ui_resources`/`check_ui`, `validation.validate_descriptor` — the same functions `cli.py` commands call (SW-35's "functions, not CLI text") |

New architecture introduced by this design: **none** beyond the composition itself, which is the PRD's stated
headline position (§ Summary 1) and the gateway's own shape.

## 5. Acceptance rule (pre-committed — written before any measurement below was run)

Metric: deterministic functional pass/fail over one freshly scaffolded starter plugin per run; no timing
claims. Every command below runs in the SDK standalone checkout on the implementation branch;
`UV_PROJECT_ENVIRONMENT=venv` throughout; exit codes are read unpiped.

**Gates (all must hold):**

- **E. Packaging integrity (PKG-1/PKG-2, structural):**
  `git diff --stat origin/main...HEAD -- src/benchweave_sdk pyproject.toml standards-lock.json hatch_build.py`
  is **empty**, and `git diff origin/main...HEAD --name-only -- src/benchweave_sdk/standards/` is empty
  (standards tripwire). The branch adds files only under `standalone/`, `.github/`, `docs/`, `README.md`.
- **G. Static:** `cd standalone && uv sync` then bare `uv run ruff check .` exit 0; fresh cache
  (`rm -rf .mypy_cache`) bare `uv run mypy` exit 0.
- **T. Suite:** `uv run pytest --junitxml=../.reports/junit.xml` exit 0, collected count **≥ 25**, failures 0,
  errors 0 — counts read from the junitxml attributes, never an output-filter summary. A collected count of 0
  is a FAILED gate (rubric G3).
- **A. Serve-and-read (UI):** after `benchweave-standalone serve <starter> --transport mock --port <p>
  --no-open` on a `plugin_new --with-ui` scaffold: `GET /` 200 and contains the literal
  `STANDALONE — no gateway`; `GET /devices/<id>` 200 and contains the `voltage` reading with value `3.3` and
  unit `V`; 10 sequential poll requests to the readings partial all return 200 containing `3.3` (loop proof);
  every HTML response carries the CSP header with `script-src 'self'` and no `unsafe-inline`.
- **B. MCP operations:** over an in-process client (HTTP mount or the stdio entry): `host_info` returns
  `mode="standalone"`, the five absent guarantees, and served/deferred sets; `device_discover` → exactly 1
  device; `device_connect` ok; `device_get` → `{manufacturer: "SDK Example", model: "demo", …}`;
  `parameter_read{parameter:"voltage"}` → `{value: 3.3, unit: "V"}`; 20 sequential reads all ok.
- **C. Authoring (SW-35/NFR-S8):** with `--authoring`: `plugin_new` scaffolds a new project (returned
  inventory lists `descriptor.json`, `presentation.json`); `plugin_check` on it returns clean with the SDK's
  diagnostic surface; `ui_check` returns clean. Without `--authoring`: `plugin_new`, `plugin_check`,
  `ui_check` are **absent from the tool list** (list_tools does not contain them).
- **D. Security refusals (≥ 10 arms, each red-then-green):** wildcard listener refused; non-loopback without
  `--allow-network` refused (with it: allowed + warning); `Host: evil.example` → 403 on `/`, `/v1`, `/mcp`;
  CSRF-less connect POST → 403; bearer-less REST mutation → refusal; MCP HTTP with disallowed `Origin` →
  refused; missing MCP token → refused; no `Access-Control-Allow-Origin` on any response; body > 64 KiB →
  `payload_too_large`. **RED controls:** (i) `LoopingMockHost(cycles=1)` — the second `parameter_read` must
  fail honestly (`unavailable` + `correlation_id`, page shows the refused state), proving the recycle
  mechanism is what sustains reads; (ii) an app constructed **minus exactly one guard** (each middleware
  individually omittable in the test harness; `serve` never omits any — a separate test pins the CLI's config
  complete) lets that guard's attack through — e.g. no-Host-middleware ⇒ `evil.example` request passes —
  proving each guard is the mechanism, not incidental.
- **F. Tool-set pin:** the registered MCP tools' names + `parameters` + `output_schema` equal the catalogue's
  implemented set exactly; the error-code vocabulary equals the interface-0.1.0 code list read from the
  vendored, digest-verified `operation-catalog.json`.

**Ship it if:** E, G, T, A, B, C, D, F all hold on the implementing agent's run, with commands and outputs
recorded in the PR body (whose measurements they are), and CI green on the SDK branch once pushed.

**Kill it if:** any gate's failure traces to the mechanism (looping mock cannot preserve exact-match
semantics; the FastMCP mount cannot share the lifespan as `app.py` does; explicit-schema registration is not
honoured by fastmcp 4.0.3) rather than to a test defect — the increment's premise is wrong; stop and
re-report rather than warping the design around the failure.

**Underpowered, not conclusive:** failures confined to environment (uv resolution/network, port allocation,
font/locale-dependent rendering) — fix the environment and re-run; no verdict exists until a clean run
completes. CI-red on the pushed branch is a hold, not a kill, until triaged.

## 6. Invariant impacts (walk of `docs/internal/invariants.md`)

- **CTL-*, STO-***: untouched — no gateway control/state code moves; standalone deliberately has no protective
  transition, leases or store (PRD non-goals). The A04-relevant property here is *honesty*, not protection:
  `host_info` + the banner state the absent guarantees (SW-27/SW-32), and no client can promote the session
  beyond the descriptor's own declared operation bounds.
- **CON-3**: not applicable (no `stg_v1` corpus tools) — its rule is imported as discipline (§3.6, gate F).
- **CON-4/PKG-1/PKG-2**: the SDK wheel is untouched by construction; gate E is the mechanical proof. The
  standalone package's own vendored UI assets follow the `bundled_assets` inventory pattern (serve-time
  digest verification).
- **CON-5 (A13)**: the seam + catalogue is this invariant's shape applied to standalone; transport tests pin
  against the catalogue, not each other.
- **CON-6**: the standalone MCP-over-HTTP path is fail-closed ahead of the FastMCP app (token + Origin);
  stdio needs neither (NFR-S4) — same trust boundary reasoning, single process, no socket.
- **REG-1/REG-2**: adapter lifecycle and dispatch-state honesty are preserved by pass-through (§3.3); the
  scaffold's own adapter is the conforming client the seam drives.
- **Obligations (drift-and-obligations.md):** 7/12 (renderer freshness, ui contract) — not touched (no `ui/`,
  no `preview_assets` change; tokens are governed copies, D5). 20/22 (version-literal zero gate) — the new
  tree sits **outside** the counter's scopes (`src/benchweave_sdk/`, gateway scopes); the design rule for the
  new package is zero version literals (SDK version derived via `importlib.metadata`); folding the tree into
  a scope is part of Q1's ruling, recorded here so that ruling inherits the duty. 19 (shared skills) — no
  skill files touched. 6 (vendored contract bytes) — no lock rows move.
- **No new invariant rows in I1.** Promotion candidates when the surface stabilises (I2/I3 design's call):
  the NFR-S8 tool-absence rule and the catalogue/refusal-vocabulary pin (gate F) are the two with
  invariant-shaped generality.

## 7. Deferrals

All homes are "documentation here" except D5, the single follow-on issue. Triggers name observable events.

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | SSE live readings, the seam event bus, `events_get`, SW-26 coalescing/ARIA | documentation here | the I2 design record is committed on its branch |
| D2 | Presentation-manifest rendering (SW-40–43), staged/apply (SW-22–25), presets, ECharts plot wrapper, structural parity suite, axe/WCAG lane (NFR-Q1/Q2) | documentation here | the I2 design record is committed on its branch |
| D3 | Capture operations via `StandaloneCaptureWriter`, serial provider backend, discovery, retention (SW-33/34, SW-49–62, NFR-O*) | documentation here | the I3 design record is committed on its branch |
| D4 | Analysis views + HTML report (SW-52–53) | documentation here | the I4 design record is committed on its branch |
| D5 | **Cross-repo UI-token freshness gate** — a main-repo CI lane comparing `ui/src/styles/{tokens,themes}.css` digests against the SDK pin's vendored copies (the `check-sdk-standards` shape), plus the regen/sync script entry point | **follow-on issue** (filed on the gateway tracker, linked to #283) | any commit touching `ui/src/styles/tokens.css` or `themes.css` after I1 merges, or the I2 parity work consuming the tokens structurally — whichever arrives first |
| D6 | Remaining authoring tools (`preset_check`, `inventory`, `standards_check`) and the SW-36–39 patch/reload/test loop (incl. `plugin_test`'s subprocess isolation, Q10/Q11 confirm gates) | documentation here | the I2 design record is committed on its branch |
| D7 | Q4 final naming ruling (design ships `bws_v1_*` per the PRD recommendation); Q5 stdio-default ruling; Q6 JS budget confirmation (ECharts lands in I2) | documentation here | the owner's call on this record, or the I2/I3 design records — whichever rules first |
| D8 | Windows serial scope (Q9) — no I1 impact; recorded so it is not lost | documentation here | the I3 design record is committed on its branch |

## 8. Review tier (Step-1 call, rubric #254) and keyword scan

**Tier 3** — maximum across this slice's expected diff, triggered by *three* independent rules:
(i) **adds/re-pins dependencies** — a new `standalone/pyproject.toml` + `uv.lock`
(fastapi `>=0.141.1`, fastmcp `[server]==4.0.3`, uvicorn `>=0.52.4`, jinja2 — aligned with the gateway's pins,
NFR-P2); (ii) keyword hits in the expected diff text (below); (iii) it is a new network-serving surface with
auth middleware (the Tier-3 lane is the right depth regardless). Consequences: mandatory independent
adversarial refute (G6) before merge. The **standards-governor mandate does not fire**: no `standards/` bytes,
no vendored-tree edits, no version-string literals (derived, §3.6); tripwires reported in gate E.

**Keyword scan over the expected diff text** (new `standalone/**` code+tests, the CI workflow, README/docs
additions, and this record — docs and code alike; counts are this record's estimates of the expected diff, to
be re-derived over the real diff at review):

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~10 | assets verifier (4), token/inventory tests (3), this record (3) |
| `hashlib` | ~4 | assets verifier import/use (2), tests (1), this record (1) |
| `asyncio` | ~6 | app/tests (4), this record (2) |
| `threading` | 0 | no threads introduced (uvicorn's internals are outside the diff) |
| `subprocess` | ~1 | this record's D6 prose only (the I2 `plugin_test` description) |
| `migrate` | 0 | — |
| `recovery` | 0 | — |
| `protection` | ~2 | this record's invariant/tier prose only |

## 9. Top risks, each with its falsifier

- **R1 — fastmcp 4.0.3 mount + combined lifespan doesn't compose outside the gateway's exact wiring.**
  Falsifier: the composition spike (gate B) failing with initialize-500s the gateway's Task-1 note describes.
  Mitigation: the wiring is copied from a working in-tree example, not reinvented.
- **R2 — CSP without inline script fights HTMX bootstrap.** Falsifier: any template needing `<script>` without
  `src`. Mitigation: htmx reads `<meta name="htmx-config">`; gate A's template test makes inline script a
  failure, not a temptation.
- **R3 — the `LoopingMockHost` subclass leaks manual-clock semantics into live deadlines** (expired ops never
  timing out). Falsifier: a deadline-expiry test (1 ms deadline ⇒ `TimeoutError`/`TIMEOUT` refusal) — in the
  suite, not hoped for.
- **R4 — relocation cost if Q1 rules option 3.** Falsifier: any coupling outside `standalone/` + the workflow
  file. Mitigation: gate E's empty-diff checks + the dev-only path source; reviewed as a hard boundary.
- **R5 — vendored tokens drift from `ui/src/styles/` with no gate** (the CON-4 defect class, cross-repo).
  Falsifier: a main-side token commit after I1 with no sync. Mitigation: D5's follow-on issue carries the
  gate; the serve-time digest check bounds the damage to *detected* tamper, not freshness — disclosed here as
  the known residual until D5 lands.
- **R6 — scope creep into I2** (manifest rendering creeping into the readings page). Falsifier: any template
  reading `presentation.json` bindings in I1. The §3.4 boundary is the control; review checks it.
- **R7 — MockHost's exact-match discipline rejects legitimate live traffic shapes** (e.g. adapter variations
  the scaffold didn't generate). Falsifier: gate B against a *second*, hand-varied scaffold. Accepted for I1:
  the scaffold's adapter is the declared I1 surface (the PRD's own I1 row), and I3 replaces the transport
  wholesale.

## 10. CI cost

One new SDK-repo job (`standalone`): uv sync + ruff + fresh-cache mypy + pytest for the subtree, python 3.13
single lane — same shape as the SDK's existing gates job, est. 1–2 min cold. No main-repo CI change in I1
(D5 defers the cross-repo lane). Workflow diff is additive under `.github/workflows/`.

## 11. What this record does not decide

Q1's formal ruling (placement is provisional by design), Q4's final namespace call (owner confirm), Q5/Q6/Q9
(D7/D8), and every I2–I4 scope line (D1–D4, D6). Nothing in this record moves standards bytes, the SDK wheel,
or the submodule pointer.
