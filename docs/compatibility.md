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

## Deviation register (D1–D7, pinned by the parity suite)

Each deviation has a pinning test; none is silent. Full wording lives in
the `tests/integration/test_interface_parity.py` module docstring.

| # | Deviation |
|---|---|
| D1 | `run_get` tier: seam fixed to catalog authority (observe); both tiers pinned |
| D2 | `change_apply` body: the catalog's REST schema omits `approver_token`, the adapter forwards it as a seam kwarg; the vendored catalog is frozen authority and is not edited — WP08 amendment |
| D3 | required-vs-defaulted params: REST rejects an absent param 400 `invalid_request`; MCP tool-signature defaults fire (fastmcp 4.0.3 does not enforce the pinned schema's `required` at dispatch) |
| D4 | event evidence: the seam emits free-form evidence dicts while the contract's `evidence` def is a closed `{id, version, sha256}` document ref |
| D5 | wire `tools/list` schemas are vendored-minus-`$defs` (the corpus `$defs` are unreferenced and inert; serve-time middleware is the SDK's) |
| D6 | token-shaped rejections collapse to a transport 401 on MCP (no envelope can exist pre-auth); `payload_too_large` is REST-only |
| D7 | token-shape probes pinned on both transports: expired → 401 `unauthenticated`; wrong-audience → 403 `forbidden`; an stg-audience token as `approver_token` fails closed 403 |

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
- **Queued-cancel is a recorded no-op**: cancelling a queued (not yet
  dispatched) run emits the `run_changed` event and forwards nothing —
  the worker can only cancel the active coordinator; the run's own
  lifecycle decides the outcome (§5).
- **Repeated-binding runs land `outcome_unknown`**: a second `run_start`
  on the same binding document is accepted by the seam (different §9
  request keys) while the coordinator dedups on the binding's own request
  id; the worker's poison guard contains the failure and the run closes
  terminal without a record — honest `outcome_unknown`, never a
  fabricated pass. WP08 hardening item.
- **Auth is the local HMAC test issuer, loopback only** — OAuth and TLS
  are out of PoC scope (see Transport verified).
