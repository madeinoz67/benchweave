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
