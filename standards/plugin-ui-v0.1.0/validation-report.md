# Plugin UI contracts 0.1.0 — validation report

Evidence record for the landed presentation-contracts increment. Commits
covered: `50b28de` (contracts, validators, SDK packaging/scaffolding, smoke
extension, plus the terminal-projection and protection receive-time race fixes
with their regression tests), `24bf7b4` (strict-CI typing for the presentation
tests), `633a2c0` (SDK guide layout documentation). Every command below was
run on 2026-09-13 against the clean working tree at main `78a8857`, which
contains all three commits. No claim below extends beyond what ran.

## Versions and platform

| Component | Version / identity |
|---|---|
| Contract family | `plugin-ui-v0.1.0` (envelope, ui-manifest, binding-catalogue, configuration-preset) |
| OTDP / adapter API / registry | `0.3.0` / `1.1` / `1.0.0` (unchanged by this increment) |
| Gateway distribution | `benchweave 0.1.0` |
| SDK distribution | `benchweave_sdk 0.1.0` (`__version__ == "0.1.0"`) |
| Platform | macOS aarch64 (Darwin 25.6.0), CPython 3.13.13 |
| Dev tools | uv 0.12.12, pytest 9.1.1, ruff 0.16.6, mypy (strict) 2.3.1 |

## Exact commands and results (run 2026-09-13)

### 1. Focused presentation/SDK suites

```sh
UV_PROJECT_ENVIRONMENT=venv uv run pytest \
  tests/architecture/test_plugin_ui_contracts.py \
  tests/unit/test_presentation_contracts.py \
  tests/unit/test_presentation_manifest.py \
  tests/unit/test_presentation_presets.py \
  tests/unit/test_presentation_specimens.py \
  tests/sdk/ -q --junitxml=<junit>
```

Result: **68 passed / 0 failed / 0 errors / 0 skipped** (1.75 s).

### 2. Full suite (three interleaved runs)

Run as part of the same-day WP08 watch-flake closure protocol on this tree
(`uv run pytest -q --junitxml=<junit>`, three runs 2026-09-13T15:30–15:32Z):

Result: **683 passed / 0 failed / 0 errors / 0 skipped, three times**
(28.6 s / 28.5 s / 28.0 s).

### 3. Built distributions and installed-wheel smoke

```sh
UV_PROJECT_ENVIRONMENT=venv uv run --no-project --python 3.13 \
  scripts/sdk_smoke.py --out-dir dist/packages
```

Result: **exit 0.** What actually ran: gateway and SDK built (uv builds the
wheel from the sdist, exercising both); an isolated venv installed both wheels;
a `--with-ui` starter was generated *outside* the checkout, its wheel built and
installed, and its 4 generated tests passed from `python -I` with no checkout
on `PYTHONPATH`; the installed check then verified:

- 34 packaged contract files byte-identical to the checkout across all three
  contract sets (`otdp-v0.3.0`, `registry-v1.0.0`, `plugin-ui-v0.1.0`);
- the packaged SDK validator copy (`benchweave_sdk/_presentation_contract.py`)
  and the gateway canonical source (`benchweave/presentation/contracts.py`)
  share one SHA-256;
- `validate_presentation` (SDK) and `validate_attachment` (gateway admission)
  both accept the installed `--with-ui` resources;
- identify/read dispatch over the installed wheel via MockHost; a helper module
  tampered after admission is rejected (`file_hash_mismatch`) **before import**.

Machine-written report: `dist/packages/sdk-smoke.json` (contract_files_verified
34; "wheel installed outside checkout; identify/read passed"). Observed and
disclosed, not investigated: uv emitted `warning: The package 'fastmcp==4.0.3'
does not have an extra named 'server'` while resolving the isolated install
(non-fatal metadata warning).

Gates at the same tree: `uv run ruff check .` clean; `uv run mypy src tests`
(strict) clean.

## Built artefact identities

| Artefact | SHA-256 |
|---|---|
| `dist/packages/gateway/benchweave-0.1.0-py3-none-any.whl` | `5ed43cc05b84a66d22399a021f20f76bd3e7b6a8cbe04bb0603b53824129c3e0` |
| `dist/packages/sdk/benchweave_sdk-0.1.0-py3-none-any.whl` | `eb02a032fd4bfbbb9215b1875922a4a7485e57e150b3cddcf99c019cc61a583f` |
| Canonical validator `src/benchweave/presentation/contracts.py` (SDK copy is byte-identical) | `90cc8b4bbe5519ee2ae02bb862bc8f43c815260b822a27734c228f816407b69a` |

Contract schemas (docs copies byte-identical to `contracts/plugin-ui-v0.1.0/`,
pinned by `contracts/manifest.json`):

| Schema | SHA-256 |
|---|---|
| `presentation-envelope.schema.json` | `1f56d52edea32659102111092789ad1c250e8afd188d92c4eca485aefebaebda` |
| `ui-manifest.schema.json` | `f6eb48255bc275a468b23b9df0c0ab64776dfbe5eb9bacb9d063130c272c42f1` |
| `binding-catalogue.schema.json` | `070734887a57654f2aec4c9c96d959cabcdd670deaed55b802d22939669643a8` |
| `configuration-preset.schema.json` | `bea991c3de717db302a1758fd9721893902b0a22d45653135a5eb6e7bc2706e6` |

Wheel bytes are build-environment-dependent (timestamps); the pinned
identities above are the byte-parity anchors the tests and smoke actually
check.

## Invalid-case coverage (design acceptance items → pinning tests)

| Acceptance item | Pinning tests (all in the 68-test focused run) |
|---|---|
| Malformed input | `test_strict_document_rejects_invalid_input[7 params: duplicate-key, nan, overflow, array, utf8, depth, bytes]` |
| Identity / digest binding | `test_descriptor_hash_binds_attachment`, `test_manifest_hash_uses_exact_bytes`, `test_hashes_exact_settings_schema_bytes`, `test_schema_identity_is_checked`, `test_asset_digest_is_checked`, `test_ui_check_rejects_modified_manifest` |
| Binding / capability honesty | `test_cannot_invent_parameter`, `test_cannot_change_parameter_unit`, `test_unknown_page_binding_is_rejected`, `test_duplicate_binding_is_rejected`, `test_profile_must_supply_the_bound_action`, `test_rejects_incompatible_preset[profile_ids-…]` |
| Paths / resources | `test_rejects_unsafe_resource_keys[traversal ×4]`, `test_missing_resource_is_rejected`, `test_ui_check_rejects_symlinked_resource`, `test_ui_check_rejects_resource_root_escape` |
| Plots | `test_non_numeric_plot_is_rejected`, `test_waveform_requires_vectors` |
| Presets | `test_rejects_incompatible_preset[6 mutation cases]`, `test_requires_known_compatible_firmware[None/2.0]`, `test_preset_cannot_bypass_canonical_action_schema`, `test_unknown_schema_reference_is_offline_failure` |
| Panel availability | `test_unavailable_panel_is_explicit[False/True]`, `test_missing_required_feature_is_rejected` |
| No execution | `test_unknown_executable_field_is_rejected`, `test_minimal_manifest_needs_no_graph_and_rejects_unknown_fields` — the closed schemas reject unknown fields (an `executable` field included); the validator exposes no import/exec path by construction (admission helper docstring: no folder scan, no panel import, no acquisition, no approvals) |
| Default compatibility | `test_optional_ui_preserves_descriptor_and_adapter` (`adapter.py`, `protocol.py`, `descriptor.json`, `vectors.json` byte-identical with and without `--with-ui`) |
| Installed parity | `test_sdk_wheel_rebuilt_from_sdist_contains_exact_presentation_contract` + the smoke installed-check above |

## CI status (observed, not inferred)

- Observed via `gh run list` on 2026-09-13: `ci`, `Package` and
  `device-plugins` workflows all reported `success` on head `633a2c0`
  (runs created 2026-09-13T08:30Z) and on head `24bf7b4` (02:28Z). Both heads
  contain `50b28de`, so the whole increment has green observed CI. `ci.yml`
  runs lint + full pytest on ubuntu-latest/Python 3.13 with fixture signing
  keys from repo secrets; `package.yml` runs the build matrix (Linux/macOS)
  on every push, with publication gated behind an owner action.
- **Not run by CI:** the WP08 slice-1 commits (`33a34f6..78a8857`, main is
  ahead 16 of origin) and this report's commit — unpushed at writing time;
  their evidence is the local gates recorded above only.
- The Linux leg of the matrix is CI evidence, not a local claim; this report's
  local runs are macOS aarch64 only.

## Scope deliberately not delivered by this increment

There is **no renderer, no executable panel runtime, no automatic acquisition
or device polling, no live plugin installer or attachment activation, and no
new profile/streaming support**. Configuration and waveform specimens are
synthetic contract evidence, not qualified device drivers; the current adapter
bridge still supports identify and scalar read/write only. `check-ui` /
`check-preset` success means offline compatibility — never admission or
approval to apply settings. Next implementation work: renderer and class-panel
integration against a verified frontend architecture, plus (separately
versioned) registry linkage of the presentation envelope.
