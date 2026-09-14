# Specification and Standards Synchronisation — Design

Date: 2026-09-14 · Branch: `feat/standards-sync` · Status: approved design, pre-implementation

## Problem

The main `benchweave` repository is the authoritative source of truth for Benchweave
specifications, standards and canonical schemas. The SDK today consumes those standards
by reaching into the main tree at build time (`hatch_build.py` force-includes contract
sets and the gateway presentation validator from the checkout), so the SDK is not
independently buildable and there is no versioned, verifiable record of which standards
a given SDK release carries. The SDK is also about to become its own repository
(`github.com/madeinoz67/benchweave-sdk`), which makes the reach-in impossible and
demands a real synchronisation mechanism.

## Decisions already made with the principal

1. **One branch carries the whole arc** (split + sync mechanism) on
   `feat/standards-sync` — accepted trade-off against PR granularity.
2. **History is preserved into the SDK repo** via `git subtree split -P packages/sdk`.
3. **Architecture: manifest-verified bundle transfer.** One standards manifest in the
   main repo, one deterministic exported bundle, one lock file in the SDK repo; every
   verification is a hash or manifest comparison.
4. **Submodule mounts at `packages/sdk`** — the uv workspace member path, smoke paths
   and build reaches keep working unchanged.

## Architecture

```
benchweave (main)                          benchweave-sdk (submodule)
──────────────────                         ─────────────────────────
standards/standards-manifest.json    ──►   src/benchweave_sdk/standards/<id>/…
    (canonical: versions, status,          (generated, stamped, hash-guarded)
     normative lists, hashes)         ──►   standards-lock.json
docs/<set>/ + contracts/<set>/             (versions + hashes + compatibility
    (sources of truth)                       declaration, SDK-owned)
    │
    ▼  export (deterministic, validates)
.standards-bundle/  (gitignored working artifact)
    │
    ▼  make sync-sdk-standards ── benchweave-sdk sync-standards .standards-bundle
    │                                (verifies, classifies, writes, reports)
    ▼
make check-sdk-standards (non-mutating; re-export + compare everything)
```

## Components

### 1. SDK split and submodule mount (step zero)

- `git subtree split -P packages/sdk` → push as `main` on `benchweave-sdk` (full
  history; remote `https://github.com/madeinoz67/benchweave-sdk.git`).
- Remove `packages/sdk` from the main index; `git submodule add` at the same path.
- All workflows gain `submodules: recursive` on checkout.
- `uv` workspace membership is unchanged (the submodule provides the same files at the
  same path). `scripts/sdk_smoke.py` builds from the submodule checkout exactly as
  before; its out-of-checkout assertions still hold because the SDK wheel after this
  design carries its own vendored standards tree (component 4) instead of reaching for
  main-repo files.

### 2. Standards manifest — `standards/standards-manifest.json` (main repo)

One entry per standard. Initial standards: `otdp`, `registry`, `execution`,
`interface` (1.1.1, superseding 1.1.0), `plugin-ui`, `plugin-ui-preview`.

Each entry records:

| Field | Meaning |
|---|---|
| `id` | stable standard identifier |
| `version` | standards version (semantic, independently bumped) |
| `status` | `draft` \| `stable` \| `deprecated` |
| `released` | release date of this version |
| `supersedes` | previous standards version this one replaces, recorded on the superseding entry |
| `sources` | canonical source paths (docs + contracts) |
| `normative` | relative paths of assets whose content hash forces a version bump — schemas, protocol definitions, conformance vectors; for `plugin-ui` this includes the gateway presentation validator `src/benchweave/presentation/contracts.py` (parity asset) |
| `conformance` | conformance vectors and fixtures shipped to the SDK |
| `sdk_packaged` | whether the standard ships in the SDK wheel |
| `compatibility` | minimum SDK version, migration note (required for breaking) |

The existing `contracts/manifest.json` remains the docs→contracts byte-pin authority.
A consistency check ties every file named in `standards-manifest.json` to a matching
entry (path + sha256) in `contracts/manifest.json` — there is no third hash authority.

### 3. Export — `uv run python -m benchweave.standards.export` (main repo)

- Validates before assembling: every referenced file exists; both manifests agree;
  JSON schemas parse; conformance assets present.
- Writes deterministic output to gitignored `.standards-bundle/`: canonical JSON
  (sorted keys, LF), sorted paths, per-file sha256, and `bundle-manifest.json`
  recording each standard's version and hashes.
- Fails closed on any missing or inconsistent reference.
- Never writes into the submodule. The bundle is a working artifact; the durable,
  reviewable record is the SDK repo's commit produced by component 4.

### 4. Import — `benchweave-sdk sync-standards <bundle>` (SDK repo)

- Verifies every bundle-manifest hash against bundle content before touching anything.
- Diffs against `standards-lock.json` and reports per standard:
  added / changed / deprecated / removed.
- **Refuses a normative change without a standards-version increment** (hash changed,
  version unchanged → error naming the standard and asset).
- Writes the vendored tree `src/benchweave_sdk/standards/<id>/…`; every generated file
  carries a first-line stamp: `Generated from <id>@<version> — do not edit`.
- Updates `standards-lock.json` (versions, hashes, compatibility declaration,
  source commit of the export).
- `--check` mode: read-only — recompute hashes over the vendored tree, compare the
  lock, verify the wheel packaging includes exactly the locked set; report drift;
  exit non-zero on any mismatch.
- `hatch_build.py` is simplified: it no longer force-includes from the main checkout;
  it validates and packages the SDK's own `src/benchweave_sdk/standards/` tree. This
  is what makes the SDK independently buildable. The bundled renderer
  (`preview_assets`) is SDK-owned content, not standards, and stays as-is.

### 5. Orchestration — `make sync-sdk-standards` (main repo)

1. Verify the submodule is initialised, checked out and clean.
2. Export the canonical standards to `.standards-bundle/`.
3. Run the SDK import inside the submodule working tree.
4. Re-validate both manifests.
5. Run SDK conformance tests and the relevant main-repo contract tests.
6. Print the resulting version table: main project, per-standard versions, SDK.
7. Stop. Changes remain in the submodule working tree for review; nothing is
   committed or pushed automatically.

### 6. Verification — `make check-sdk-standards` (main repo, non-mutating)

Re-exports deterministically to a temp directory, then fails — naming the offending
field — when any of:

- the SDK lock's standards versions differ from the main manifest;
- bundle content differs without a standards-version change;
- any content hash mismatch (bundle vs lock vs vendored tree on disk — this also
  catches hand-edited generated files);
- generated SDK resources are stale (re-import would produce a diff);
- compatibility metadata is incomplete for a standard whose status/compat changed;
- required schemas, fixtures or conformance vectors are missing;
- the pinned submodule commit's compatibility declaration does not cover the main
  project's standards set — read from the `standards-lock.json` inside the submodule
  checkout, which in main CI is by construction the pinned SHA.

### 7. CI wiring

| Pipeline | Runs |
|---|---|
| main PR CI | `make check-sdk-standards` (checkout with submodules) |
| main release CI | same check + full gates |
| SDK PR CI | `benchweave-sdk sync-standards --check` (self-consistency only; no main-repo access) |
| SDK publishing CI | `--check` + packaging gates (wheel carries exactly the locked set) |
| docs publishing CI | regenerate compatibility matrix; fail on diff |

### 8. Change classification

- **Normative** — hash change on a `normative`-listed asset. Requires a standards
  version increment, enforced at export, import **and** check (no bypass path).
- **Compatible clarification** — non-normative (prose/doc) change. Normative lists
  exclude prose by construction, so sync reports no normative delta and no version
  bump is required; still reviewed and docs-validated.
- **Editorial** — docs-only; never enters the bundle.
- **Breaking** — version increment with status or compatibility change. Export
  requires the compatibility decision fields (migration note, SDK floor) to be
  present and complete before the bundle is produced.

### 9. Compatibility matrix

Generated by a sibling command of the check from `standards-manifest.json` + the SDK
lock into `docs/compatibility-matrix.md` (committed output, staleness-gated: CI
regenerates and diffs). Each row shows: SDK version, supported main-project range,
supported standards versions, schema/protocol versions, compatibility status, source
commit + release links, deprecation/migration guidance. One generator, both
repositories reference or regenerate from the same inputs — never hand-maintained
twice.

### 10. Test scenarios (main repo, end-to-end)

1. **Unchanged** — `sync` is a no-op report; `check` passes.
2. **Compatible clarification** — doc-only change: sync reports no normative delta,
   no version bump required; check passes.
3. **Breaking (positive)** — normative hash change + version increment + complete
   compatibility fields: sync reports the change and updates the lock; check passes.
4. **Breaking (negative)** — normative hash change *without* version increment:
   export, sync and check each refuse, each naming the standard and asset.

## Change propagation sequence (operating procedure)

1. Change the canonical specification/standard in the main repo.
2. Increment the applicable standards version when normative content changes.
3. Validate and export (`make sync-sdk-standards`).
4. Open a reviewed SDK change containing the synchronised resources (automation may
   prepare the PR; review, compatibility testing and protected branches are never
   bypassed).
5. Run SDK conformance, packaging and documentation gates.
6. Release the SDK when the standards change requires a new SDK version.
7. Update the main project's submodule pointer to the released SDK commit.
8. Run main-project integration and compatibility gates.
9. Record the final main / SDK / standards version combination (compatibility
   matrix row).

## Acceptance criteria

- [ ] One documented command from the main repo prepares an SDK standards update.
- [ ] A separate check command proves both repositories synchronised, modifying nothing.
- [ ] CI detects stale SDK standards resources.
- [ ] CI detects normative content changes without a version increment.
- [ ] The SDK builds independently, never reaching into the main repository.
- [ ] The main project rejects a pinned SDK commit that does not declare compatibility
      with its standards.
- [ ] Release and documentation workflows consume the same version/compatibility
      evidence as CI.
- [ ] Unchanged, compatible-change and breaking-change scenarios are tested end to
      end, including the refused-unversioned-change negative.

## Non-goals

- No new standards content in this work package — the mechanism synchronises what
  exists.
- No automatic SDK releases or submodule pointer advancement; automation prepares,
  humans review.
- The preview renderer build (`preview_assets`) keeps its existing freshness gate;
  it is not a standards artifact.
