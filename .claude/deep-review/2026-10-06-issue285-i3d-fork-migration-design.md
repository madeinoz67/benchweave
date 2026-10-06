# Issue #285 / epic #282, slice I3d — fork migration onto the standalone SDK host

Status: BUILD (designed 2026-10-06; verified premises from the I3d design
pass, gateway tracker issue #285). This record is the build contract: the
mechanism, the acceptance rules pre-committed before any code moved, the
deferral table, the owner forks with their adopted calls, and the keyword
scan that scopes the deletion.

Tier call: **Tier-3-equivalent** — the slice changes what a published
contributor fork ships as its entire runtime surface (deletes a web stack
and a persistent MCP server, cuts the host over to the SDK), so it runs the
two-adversary-lane + resident-review battery before any PR opens. Zero
bytes move in the gateway or SDK repositories: this branch touches the fork
(`benchweave-adc`) only, and the gateway-side `adc_conformance_control.py`
already pins the immutable commit `de132a2` so the conformance lane cannot
drift under this migration.

## 1. Premises (verified against the fork at `d867f13` and the SDK at 0.7.1)

1. **Layout gap.** `benchweave_sdk_server.session.load_plugin_project`
   requires exactly one `src/*/descriptor.json`; the fork ships the plugin
   at `plugins/adc_6ch_12bit/`, so a serve attempt refuses with
   `standalone_plugin_project:` today. The descriptor's entry point
   `adc_6ch_12bit.adapter:create_plugin` already names the moved package,
   so the migration is a `git mv` plus import rewrites — no descriptor
   change.
2. **`presentation.json` is optional at load.** `has_presentation=False`
   degrades to an empty page list, never a refusal. A minimal presentation
   rides the migration so the live-readings UX survives the cutover.
3. **Always-on stdio MCP cannot survive this slice.** Three independent
   reasons: (a) the SDK's stdio `mcp` entry point builds a MOCK seam —
   `_build_seam` has no `--transport/--device` plumbing on that path; (b)
   I3b's lockfile rule refuses serve + stdio over one capture root; (c)
   serve's bearer credential is per-launch. Deleting the fork's
   `mcp_server.py` therefore removes persistent MCP with no equivalent:
   a **disclosed degradation** (serve-time MCP-over-HTTP at `/mcp` remains),
   recovery = the Q5 stdio proxy follow-up.
4. **Pin floor `benchweave-sdk[server]>=0.7.1`.** v0.8.0's tag was pushed
   but unpublished at design time; 0.7.1 is the published floor that
   carries the `[server]` extra and the standalone loader. The 19k SPS
   story needs ≥0.8.0 (#393) and stays deferred.
5. **The adapter already runs on the SDK adapter contract.** Runtime
   imports of the plugin never touch the SDK; `benchweave-sdk` is a dev
   dependency for conformance and validation only. The migration preserves
   that boundary: the SDK host arrives as an *optional* extra.

## 2. Mechanism

Four commits, each gated (see §4):

1. **Design record** (this file).
2. **The migration.** Delete the hand-rolled stack — `src/benchweave/web/`
   (`host.py`, `app.py`, `board.py`, `library.py`, `report.py`,
   `static/` incl. `app.js` + `chart.umd.js`), `src/benchweave/mcp_server.py`,
   `tests/web/` (11 files), `tests/test_mcp.py`, `tests/adc/test_host.py`,
   `tests/adc/test_throughput.py` (verified: it imports
   `benchweave.web.host` — `SerialLink`, `SerialHostServices`,
   `AdcOperationContext` — so it dies with the stack), `scripts/adc_capture.py`,
   `scripts/run_adc_web.sh`, `plugins/__init__.py`, and the docs whose whole
   subject is the deleted stack (`docs/mcp-tools.md`, `docs/analyse-page.md`,
   `docs/library-schema.md`, `docs/rest-api.md`). Move
   `plugins/adc_6ch_12bit/**` → `src/adc_6ch_12bit/**` (`git mv`). Edit:
   the surviving `tests/adc` imports `plugins.*` → `adc_6ch_12bit.*`; the
   adapter docstring's stale "host side lives in `benchweave.web.host`" →
   the SDK server; `.mcp.json` drops the `benchweave-adc` entry (nanodla
   stays); `pyproject.toml` drops fastapi/uvicorn/mcp/send2trash runtime
   deps and the `benchweave-adc-mcp` entry point (keeps `benchweave-adc` +
   `nanodla-mcp`), packages → `src/benchweave` + `src/adc_6ch_12bit`, adds
   the optional extra `host = ["benchweave-sdk[server]>=0.7.1"]`, bumps the
   dev pin to `benchweave-sdk[server]>=0.7.1` (dev-only — runtime stays
   SDK-free), version 0.1.0 → 0.2.0 (breaking: entry points removed, host
   cutover), description/keywords updated, `uv.lock` regenerated (CI runs
   `uv sync --locked`). README/TODO/adapter/development docs updated to the
   new surfaces — AR-D2's gate covers both dotted and slashed spellings, so
   docs that instruct readers to run deleted surfaces must move with them.
3. **Minimal presentation.** `src/adc_6ch_12bit/presentation.json` +
   `ui/manifest.json` + `binding-catalogue.json`: one readings page, the six
   channel read bindings, one analog time-series plot. Validated by the
   host's own startup gate (`load_plugin_project` →
   `load_validated_preview_inputs`), not eyeballs.
4. **Proof arms.** (a) `tests/test_standalone_host.py` — composes the seam
   the way `cli._build_seam` does (mock transport) over this project,
   builds the app, asserts via TestClient: `GET /` serves with the authored
   presentation, `host_info` answers `mode=standalone` with the descriptor
   digest, device ops reachable. RED controls executed and recorded in the
   commit message: an invalid-presentation copy refuses
   `standalone_plugin_invalid:` through the real gate, and the pre-
   migration tree refuses `standalone_plugin_project:` by construction.
   (b) `tests/test_migration_complete.py` — AR-D2's zero-reference gate.
   (c) The adapter conformance lane (AR-D3) green; count re-derived at the
   migrated shape.

## 3. Step-1 keyword scan (recorded before any deletion)

Reference counts at `d867f13` (excluding `__pycache__`):

| Token | src | tests | scripts | docs (+README/TODO) |
|---|---|---|---|---|
| `benchweave.web` | in-web only | web/ + host/throughput tests | — | README 1, adapter.md 1 |
| `benchweave.mcp_server` / `src/benchweave/mcp_server.py` | self | test_mcp.py | — | mcp-tools.md, TODO ×2 |
| `plugins.adc_6ch_12bit` / `plugins/adc_6ch_12bit` | web/ only (5) | 28 across adc/ + web/ | 3 | 7 (README 3, TODO 2, adapter 1, library-schema 1, analyse-page 2, development 1, feature-request 1) |

The only non-deleted code consumers of the moved plugin are
`tests/adc/{fakeboard,test_protocol,test_config,test_discovery,test_adapter_conformance}.py`
— five files whose imports rewrite to `adc_6ch_12bit.*`. Every other hit
sits inside a file the migration deletes, or in docs edited with commit 2.

## 4. Acceptance rules (pre-committed)

- **AR-D1 loads-and-serves.** On the mock transport, the real loader +
   seam + app composition serves `GET /` 200 with the authored
   presentation visible, `POST /v1/host_info` answers `mode == standalone`
   with the descriptor sha256, and device operations answer (not 404).
   RED controls: (i) a corrupted `presentation.json` copy of the project
   refuses `standalone_plugin_invalid:` through `load_plugin_project` —
   executed, output recorded; (ii) the pre-migration tree (parkview
   `main`) refuses `standalone_plugin_project:` — executed via
   `--with 'benchweave-sdk[server]>=0.7.1'` before commit 2, output
   recorded. These controls are migration-RED: the proving test cannot
   exist before the layout exists, so the refusals ARE the failing-state
   evidence.
- **AR-D2 deletion completeness.** Zero references to `benchweave.web`,
   `benchweave.mcp_server`, and `plugins.adc_6ch_12bit` (dotted and
   slashed spellings) across `src/ tests/ scripts/ docs/` — enforced by a
   committed test, not a one-off grep.
- **AR-D3 conformance survives.** `tests/adc/test_adapter_conformance.py`
   green at the migrated shape; collected count re-derived and reported
   (design estimate: 26/26, matching the count pinned at `de132a2`).
- **AR-D4 hardware annex.** NOT this branch — the PR body carries its
   placeholder per AR-3's flatness rule (F-5-gated live-hardware proof).

## 5. Deferral table (do not build)

| Deferred | Where it lands |
|---|---|
| Q5 stdio MCP proxy | The single follow-on gateway issue, filed at PR-open time by the run owner (not this branch) |
| Report/CSV export parity | I4 (Q7) |
| Retention defaults | I3c (Q13) |
| 19k SPS (ring resize) | #393 — needs SDK ≥0.8.0 |
| Capture-corpus data migration | Explicit non-goal: legacy captures stay readable from the pre-migration tag |
| AR-D4 hardware annex | PR body placeholder (F-5-gated) |

## 6. Owner forks (ruled at design delivery)

- **F-D1 — MCP posture.** Option A adopted: ship with the disclosed
  degradation (no persistent stdio MCP; serve-time MCP-over-HTTP remains).
  The disclosure rides the README + this record; recovery is Q5.
- **F-D2 — cross-fork delivery.** The branch lands on a madeinoz67-owned
  repo in the fork network, PR opens parkview-side from there; fallback =
  hand the branch to the contributor. (Build-time note: GitHub refuses a
  second repo for one account in a fork network — madeinoz67 already owns
  the network root `madeinoz67/benchweave` — so the push target is a
  branch on that root repo, which serves F-D2's cross-fork PR identically.
  Disclosed here rather than silently substituted.)

## 7. Gates

The fork's own tooling is the baseline (recorded green at `d867f13`):
ruff check 0, ruff format --check 0, mypy strict fresh-cache 0 (38 files),
pytest 287 passed / 0 failed / 0 skipped (7.7 s). Per commit: the fast
lane (ruff + format + fresh mypy + focused pytest). Full suite once,
immediately before push. Counts from junitxml attributes or redirected
files — filtered summary lines are not evidence. 219 tests are deleted
with the stack (web 172 + mcp 8 + host 38 + throughput 1); 68 survive
(conformance 26 + config 13 + discovery 9 + protocol 18 + package 2);
219 + 68 = 287 reconciles exactly with the baseline.
