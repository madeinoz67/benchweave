# SDK UI preview and fixture design

**Status:** Approved design, pending written-spec review  
**Date:** 2026-09-14  
**Scope:** BenchWeave plugin developer SDK and host UI development loop  
**Audience:** SDK maintainers, UI engineers, plugin authors, reviewers and AI coding agents

## 1. Purpose

Add a deterministic local preview and conformance workflow to the existing plugin presentation SDK. A plugin author must be able to validate declarative presentation resources, exercise representative runtime states and view the result through the version-matched BenchWeave host renderer without hardware, gateway credentials or plugin-supplied browser code.

This increment extends the existing `benchweave-sdk new --with-ui` and `check-ui` capabilities. It does not replace admission, permission, hardware qualification, physical-device testing or production gateway validation.

## 2. Decisions

1. Deliver preview and reusable fixture/conformance support together.
2. Bundle a production-built host renderer in the SDK wheel for offline, version-matched use.
3. Support an optional renderer URL override for BenchWeave UI development and hot reload.
4. Provide mandatory SDK baseline scenarios plus validated author-defined device scenarios.
5. Reuse the existing presentation validation path before preview construction.
6. Keep plugin presentation declarative and host-rendered. Plugins cannot supply JavaScript, HTML or CSS.
7. Bind to loopback and select an ephemeral port by default.

## 3. Architecture

```text
Plugin resources ── check-ui ──┐
                               ├─ Preview model builder ─ Fixture validation
Fixture files ─────────────────┘              │
                                              ▼
benchweave-sdk preview-ui ── loopback HTTP server
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
       Bundled renderer assets         --renderer-url override
                │                             │
                └──── same preview API ───────┘
```

The Python SDK owns file safety, contract validation, fixture validation, deterministic baseline generation and local server lifecycle. The React host owns rendering. Both the bundled renderer and the Vite development renderer consume the same versioned preview API.

### 3.1 Module boundaries

- `presentation.py` continues to load and validate presentation envelopes, manifests, resources and catalogues.
- `preview_models.py` defines immutable validated preview, scenario, observation and simulated-receipt models.
- `fixtures.py` loads author fixtures, performs catalogue cross-checks and generates mandatory baseline scenarios.
- `preview_server.py` owns loopback HTTP routing, static renderer delivery and clean shutdown.
- `cli.py` handles arguments, stable diagnostics and process exit only.
- The React preview adapter maps the preview API to existing host-owned components and compositions.

Each module must be independently testable. Server code must not reinterpret plugin contracts, and UI code must not perform filesystem validation.

## 4. CLI contract

The primary command is:

```sh
benchweave-sdk preview-ui \
  src/example_plugin/presentation.json \
  --descriptor src/example_plugin/descriptor.json \
  --resources src/example_plugin \
  --catalogue src/example_plugin/binding-catalogue.json \
  --fixtures src/example_plugin/ui/fixtures \
  --firmware 1.0.0
```

Options:

- `--renderer-url URL` uses a development renderer instead of bundled assets.
- `--host 127.0.0.1` selects the listener. Loopback is the default and normal mode.
- `--allow-network` is required when the selected host is not loopback and prints a prominent exposure warning.
- `--port 0` selects an available port and is the default.
- `--no-open` starts without opening a browser and is suitable for CI and automated tests.
- repeated `--feature` and `--panel` options retain the semantics of `check-ui`.

The command validates all inputs before listening. It prints the selected local URL, renderer/API versions, scenario count and the statement that all presentation data is simulated. `SIGINT` and `SIGTERM` produce a clean shutdown.

## 5. Renderer distribution and compatibility

The SDK wheel and sdist include:

- production-built preview renderer assets;
- the preview fixture JSON Schema;
- an asset inventory with SHA-256 hashes;
- the renderer version and supported preview API version.

The SDK verifies its bundled asset inventory before serving. Missing or altered assets fail closed.

The development renderer declares the same preview API version. `--renderer-url` performs a compatibility check before exposing the preview. An incompatible renderer produces a stable diagnostic and no partially functional page.

Renderer assets are produced from the repository `ui/` application during the SDK build. Generated-asset drift is checked in CI. The same validated preview model must produce the same page structure in bundled and development modes.

## 6. Fixture contract

Author fixtures live under the plugin presentation resource tree:

```text
ui/
├── manifest.json
└── fixtures/
    ├── normal.json
    ├── warning.json
    └── high-load.json
```

Each fixture is a closed, versioned JSON document containing:

- stable scenario ID, title and description;
- deterministic timestamp strategy;
- binding values with value, declared unit, quality, freshness and provenance label;
- observer, controller and administrator permission state;
- lease and approval state;
- configured simulated request outcomes;
- unavailable required or optional panels;
- expected severity and operator-visible state.

Fixture values must match validated catalogue binding IDs, types, units, scalar/dataset shapes and finite-number requirements. Unknown properties and unknown bindings are rejected. Fixture files use the same bounded, regular-file, no-symlink rules as presentation resources.

Fixtures contain only simulated presentation data. They cannot invoke adapter code, open transports, load secrets, declare permissions or establish device conformance.

### 6.1 Mandatory baseline scenarios

The SDK generates these scenarios in memory from the validated descriptor, catalogue and manifest:

1. normal;
2. loading;
3. stale;
4. disconnected;
5. warning;
6. critical;
7. protective trip;
8. recovery;
9. simulated request rejection.

Authors may add device-specific scenarios but cannot replace, rename or suppress baseline scenarios. Baseline values are deterministic and conservative. When a meaningful numeric value cannot be inferred, the state is represented without inventing a normal engineering reading.

The `--with-ui` scaffold adds author examples for normal and warning state. Generated examples remain explicitly synthetic and are not evidence vectors.

## 7. Preview API

The initial protocol is `v1`:

- `GET /api/v1/preview` returns validated manifest/page structure, compatibility metadata and the mandatory simulation banner.
- `GET /api/v1/scenarios` returns stable scenario summaries.
- `GET /api/v1/scenarios/{id}` returns one complete deterministic presentation state.
- `POST /api/v1/scenarios/{id}/requests` creates an in-memory simulated control receipt based on the fixture's configured outcome.
- `GET /healthz` reports local readiness and protocol version.

Responses are JSON with explicit content type, bounded size and no permissive cross-origin policy. The server accepts requests only for known routes and methods. Path traversal, arbitrary file serving and directory listing are prohibited.

The simulated request endpoint changes only the current in-memory preview session. It never calls plugin code or gateway services. Reloading the scenario or restarting the SDK restores its original deterministic state. A receipt distinguishes accepted, permission rejected, lease rejected, approval required, policy rejected, transport failed, device rejected and unknown final state.

## 8. Security and safety boundaries

- Default listener: `127.0.0.1` with an ephemeral port.
- Non-loopback binding requires explicit `--allow-network`; wildcard hosts are rejected in the initial version.
- No gateway connection, physical transport, credential loading or plugin execution.
- No arbitrary plugin JavaScript, HTML or CSS.
- All presentation resources, fixture files and renderer assets remain size-bounded and hash/contract validated.
- Every preview page and exported state is visibly labelled `SIMULATED`.
- A staged control produces no physical effect and no optimistic device reading.
- Preview success is not admission, permission, compatibility evidence or hardware qualification.

## 9. Error handling

Diagnostics use stable machine-readable codes alongside human-readable paths and corrective text. Categories remain distinct:

- invalid presentation contract;
- invalid fixture schema;
- unknown or incompatible binding;
- wrong type, unit or shape;
- unsafe resource path or symlink;
- exceeded file count, file size or aggregate payload bound;
- unavailable required panel;
- missing or altered bundled renderer assets;
- unsupported renderer protocol;
- unsafe listener configuration;
- browser launch failure;
- server bind failure.

A browser launch failure does not invalidate an already-ready `--no-open` equivalent server; the CLI prints the URL and continues. Validation, compatibility, integrity and bind failures occur before readiness and return non-zero.

Simulated runtime failures are fixture state, not CLI failure. Permission, lease, approval, policy, transport and device rejection must remain separately visible to the renderer.

## 10. UI integration

The renderer maps validated pages and bindings only to registered host-owned components. It reuses the Layered Precision themes and components in `ui/src`.

The preview UI provides:

- persistent `SIMULATED PRESENTATION DATA` labelling;
- scenario selection and scenario description;
- light and dark theme selection;
- observer/controller/administrator role selection where the fixture permits it;
- page and panel rendering through production component mappings;
- deterministic staged-control receipts;
- visible unavailable-panel and compatibility states;
- textual state descriptions for accessibility and automated assertions.

Preview-only controls are visually separated from the plugin-rendered workbench. Plugin resources cannot style or hide the preview frame or simulation banner.

## 11. Generated starter changes

`benchweave-sdk new --with-ui` retains its current descriptor, adapter and protocol output. It additionally creates:

```text
src/<package>/ui/fixtures/
├── normal.json
└── warning.json
tests/
└── test_presentation_preview.py
```

`UI-GUIDE.md` documents `check-ui`, `preview-ui`, fixture authoring, baseline scenarios and the safety boundary. The generated project remains buildable without Node.js because the renderer ships with the SDK.

## 12. Testing and acceptance

### 12.1 Python SDK

- Unit tests cover fixture validation, catalogue cross-checking, baseline generation and deterministic request receipts.
- Negative tests cover unknown bindings, wrong units/types/shapes, non-finite values, unknown fields, traversal, symlinks, excessive files and oversized payloads.
- Server tests use an ephemeral loopback port and never open a browser.
- CLI tests cover bundled mode, development override, incompatibility, listener safety and clean shutdown.
- Scaffold tests confirm plain projects remain unchanged and `--with-ui` adds valid examples.

### 12.2 Packaging

- Wheel and sdist tests prove the fixture schema, renderer assets and asset inventory are included.
- A wheel rebuilt from the sdist remains self-contained.
- CI compares installed contract and renderer hashes with canonical build outputs.

### 12.3 React renderer

- Integration tests cover all mandatory baseline scenarios and author fixture selection.
- Tests prove controls return simulated receipts without changing observed values optimistically.
- Bundled and Vite modes consume the same preview API and produce the same page structure.
- Storybook covers normal, loading, stale, disconnected, warning, critical, trip, recovery and request rejection in light and dark themes.
- Accessibility tests cover names, roles, keyboard access, focus, non-colour severity cues and reduced motion.

### 12.4 Acceptance criteria

The increment is complete when an independently scaffolded `--with-ui` plugin can be validated and previewed from its built SDK environment without Node.js or hardware; its author fixture and every mandatory baseline state render through the host component mapping; all safety labels remain present; and package, SDK, UI and contract test suites pass.

## 13. Explicit non-goals

- Connecting to a gateway or physical device.
- Executing plugin Python or arbitrary browser code.
- Installing plugin dependencies.
- Saving user workbench layouts.
- Building the custom-device component-recipe contract.
- General arbitrary time-series synthesis.
- Pixel/screenshot approval testing.
- Publishing the SDK or plugins to a public registry.

These require separate specifications after the deterministic preview contract is stable.
