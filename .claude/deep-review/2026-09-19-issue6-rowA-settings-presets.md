# Issue #6 Row A — settings as presets, zero contract change

Date: 2026-09-19
Status: design for review. One increment, no standards bytes move, no SDK
submodule change, no runtime control-core change. Everything below was verified
against the working checkout (`main`, commit `8bc83a5`) by reading the code and
running the real CLI lanes, not by trusting issue prose.

Row A definition (issue #6, maintainer-verified 2026-09-14):

> Model averaging, channel enablement, and per-channel gain/offset (as writable
> `float` parameters, `semantic: configuration`) through the
> configuration-action + settings-schema path; ship named setups as `ui/presets/`
> documents. *Acceptance: `benchweave-sdk check-preset` passes for each shipped
> preset; settings validate against both the settings schema and the action
> input schema; labels/units remain in the descriptor.*

## 1. Problem and root framing

An operator of a real six-channel ADC plugin (external fork, not in-tree) keeps
named measurement setups — averaging, which channels are on, per-channel
gain/offset — in the plugin's private `config.json`, because no upstream
contract expresses "a named, redistributable, complete set of device settings".
The plugin-ui 0.1.0 preset contract now exists
(`standards/plugin-ui/0.1.0/ui-manifest.schema.json:43` `$defs/preset`) and the
SDK has a working offline checker (`benchweave-sdk check-preset`,
`packages/sdk/src/benchweave_sdk/cli.py:144`), but **nothing in the tree uses
them**: no in-tree plugin ships a configuration binding, a settings schema, or
a preset. The mechanism is contracted and implemented but unexercised — which
also means `check-preset` has no behavioral test (it appears only in the CLI
framework smoke list, `tests/sdk/test_cli_frameworks.py:21`).

Row A closes that by building the first real instance: an in-tree simulator
plugin whose named setups ship as preset documents, validated by the existing
lanes, with the settings surface declared in its descriptor.

### The interpretation fork the maintainer must see

The three settings families do not have equal representation in the contracted
surfaces, and this design does not pretend they do. Verified against every one
of the 50 action input schemas in `standards/otdp/0.1.1/device-profile-catalog.json`
(all are `additionalProperties: false` — closed):

| Family | Action-input home (preset-borne) | Descriptor-parameter home |
|---|---|---|
| Channel enablement | `otdp.oscilloscope.configure` `channels[]` — membership **is** enablement | — |
| Per-channel gain/offset | `otdp.oscilloscope.configure` channel items: `probe_ratio` (gain), `offset_v`, `range_v`, `coupling` | `chN_*` writable parameters |
| Model averaging | **none anywhere** — no profile action schema carries an averaging count; `sample_count` is total samples, the DMM `aperture` is a different concept on a single-channel profile | `averaging_count` writable parameter, live-write only |

So there are two readings of Row A's sentence:

- **Reading 1 (maximal):** all three families ride preset `settings`. This is
  **falsified by the contracts**: a preset's `settings` must validate against the
  canonical action input schema (`src/benchweave/presentation/contracts.py:521-531`
  validates against `schema_documents[target["input_schema_id"]]`, and
  `_target_findings` at `contracts.py:356-365` requires that id to be a corpus
  action input `$id`), and every such schema is closed. An `averaging_count` key
  in preset settings is structurally unrepresentable in 0.1.0/0.1.1.
- **Reading 2 (issue-literal, chosen):** the settings become writable
  `semantic: configuration` parameters in the descriptor (the issue's own
  "Verified current state" calls parameters "the natural home for per-channel
  gain/offset as writable `configuration` parameters"); the preset carries the
  complete action-input document — which natively covers channel enablement and
  per-channel gain/offset on the oscilloscope profile; averaging is
  parameter-only until a profile revision admits it (a standards-governance
  event: copy, never move).

This design implements Reading 2 and turns its central limitation into a pinned
RED control (§7): a preset that smuggles `averaging_count` into settings MUST be
refused by the canonical check. If the maintainer wanted Reading 1, Row A is not
buildable without a standards change and this document is the evidence for that
claim.

### Why the existing simulators cannot be the vehicle

- `plugins/benchweave/sim_psu` and `sim_controller` ship descriptors in the
  **runtime execution-contract dialect** — `parameters` a list of names,
  `actions` a list of `{action_id, issued}` — which `control/documents.py:111-119`
  (`_check_descriptor`) admits but the OTDP 0.1.1 descriptor schema forbids.
  Both FAIL `benchweave-sdk check` today (verified: id `descriptor-sim-psu`
  violates the `^[a-z0-9]+(\.[a-z0-9-]+)+$` pattern among other things). Since
  `check-preset` runs `validate_descriptor` first
  (`packages/sdk/src/benchweave_sdk/presentation.py:87-97`), no preset can be
  checked against them. Converting them means touching the byte-pinned execution
  fixture lattice (`tests/contract/test_sim_layout.py:15`).
- `plugins/fnirsi/dps150` PASSES `benchweave-sdk check` (verified) but is
  deliberately read-only: no `profiles`, no `actions`, no writable parameters —
  it cannot host a configuration target at all.

A new plugin is the minimal move. It is additive: `test_sim_layout.py` pins only
the two existing sims, and `plugins/benchweave` is already vendored verbatim into
the wheel (`pyproject.toml:63` force-include), so packaging needs no change.

## 2. Mechanism

### 2.1 Proof vehicle: new simulator plugin `sim_scope`

`plugins/benchweave/sim_scope/` (package `benchweave_sim_scope`), a deterministic
oscilloscope simulator implementing the `otdp.oscilloscope/1.0.0` profile — the
**only** profile whose configure action natively carries per-channel
gain/offset-shaped fields. Four analogue-input channels `ch1`–`ch4` (count is
arbitrary; the mechanism is count-independent). Structure mirrors the WP05
`sim_psu` pattern exactly: injected clocks, `create_plugin(now_fn,
monotonic_ns_fn)`, `plugin_open`/`plugin_close`, `simulation` property labelled
`simulated=True`, per-action handlers dispatched under `OperationVerb.INVOKE`
with `action_id` + `input` arguments (`plugins/benchweave/sim_psu/src/benchweave_sim_psu/plugin.py:297-316`
is the precedent).

Actions (all five the profile names — four required plus the optional trigger;
declaring the profile while omitting required actions would be a dishonest
capability claim):

- `otdp.oscilloscope.configure/1.0.0` — validates `configuration_id`, channel
  membership, per-channel numerics; applies each channel's
  coupling/range/offset/probe through internal parameter writes (the
  `_write_parameter` re-homing pattern, `sim_psu plugin.py:318-344`); stores the
  `configuration_id` token exactly as sim_psu does (`plugin.py:369`).
- `arm` / `trigger` / `fetch` / `abort` — minimal deterministic lifecycle:
  `fetch` returns `sample_count` synthetic points for the **configured
  (enabled) channels only**. This makes channel enablement behaviorally real in
  the simulator, not decorative: a preset that configures two channels yields
  two-channel fetches.

### 2.2 The descriptor — settings surface, labels, units, narrowing

`src/benchweave_sim_scope/descriptor.json` in full OTDP 0.1.1 form (passes
`benchweave-sdk check`, S01/S02 included): id `dev.benchweave.sim-scope`,
`identity.firmware_policy: "listed"` with `supported_firmware: ["sim-1.0.0"]`,
declarative serial transport (scaffold precedent for simulated protocols,
`packages/sdk/src/benchweave_sdk/scaffold.py:345-356`), capabilities
`identify/read/write/invoke` with matching `operations` (S01 requires the sets
to match).

- **`channels[]`** — `ch1`–`ch4`, role `analogue_input` (the profile's one
  channel role), each with a human `label`. **Labels live here and only here.**
- **`parameters[]`** — the writable-configuration surface, every one
  `access: "rw"`, `semantic: "configuration"`, `binding: {kind: "adapter"}`,
  `write_policy: {effect: "setting", completion: "readback", retry: "never"}`
  with `verification_parameter` pointing at itself (the sim verifies writes by
  reading back its own state; `effect: "setting"` — never `energise` — keeps
  the A02 posture that a settings bundle implies no energisation):
  - per channel: `chN_probe_ratio` (float, dimensionless), `chN_offset_v`
    (float, unit `V`, range `[-10, 10]`), `chN_range_v` (float, unit `V`,
    range `[0.001, 10]` — corrected in the fix wave; as first written this said `]0, 10]`, but the shipped descriptor declares the inclusive 1 mV floor), `chN_coupling` (enum `ac|dc|ground`);
  - `averaging_count` (int, range `[1, 64]`) — the one family with no
    action-input home;
  - `identity_model` (ro, string) for identify/read smoke coverage.
  **Units live here and only here.** 17 parameters total.
- **`actions{}`** — dict form, each entry with the six required fields; the
  configure entry carries a real `input_constraints` narrowing (the plugin's
  actual envelope, AND-ed onto preset settings and, in future apply paths,
  action inputs): `channels.items.channel` pattern `^ch[1-4]$`,
  `channels.items.probe_ratio` enum `[1, 10, 20, 50]`, `sample_rate_hz`
  maximum `1000000`.
- `required_features` including `otdp.profile_actions/0.1.0` and
  `otdp.oscilloscope/1.0.0`; `contracts[]` pinning the profile catalog and
  measurement schema like the class examples do.

### 2.3 The ui resources — settings schema, catalogue, manifest, presets

In-package, exactly the layout the scaffold's UI-GUIDE already documents
("Add settings/ and presets/ only for configuration actions the descriptor
implements" — `packages/sdk/src/benchweave_sdk/presentation.py:381-385`):

```
src/benchweave_sim_scope/
  descriptor.json
  presentation.json            # envelope: resource_root "ui", manifest pinned by sha256
  binding-catalogue.json       # one configuration target
  ui/
    manifest.json              # assets: settings schema + both presets, sha256-pinned
    settings/oscilloscope-configure.schema.json
    presets/fast-survey.json
    presets/low-noise-pair.json
```

- **`ui/settings/oscilloscope-configure.schema.json`** — a byte copy of the
  corpus action input schema, extracted from
  `device-profile-catalog.json → actions["otdp.oscilloscope.configure/1.0.0"].input_schema`
  (the specimen test's own construction, `tests/unit/test_presentation_specimens.py:42-43`).
  It must carry the corpus `$id`
  (`urn:otdp:action:oscilloscope.configure:1.0.0:input`) because the binding
  loop checks asset `$id == target.input_schema_id`
  (`contracts.py:498`) and `_target_findings` requires that id to resolve in
  the corpus (`contracts.py:356`). A parsed-equality test (§7) pins the copy
  against the corpus so it cannot silently drift.
- **`binding-catalogue.json`** — one target:
  `{id: "configure", kind: "configuration", action_id:
  "otdp.oscilloscope.configure/1.0.0", profile_ids: ["otdp.oscilloscope/1.0.0"],
  input_schema_id: "urn:otdp:action:oscilloscope.configure:1.0.0:input",
  schema_asset_id: "settings-schema", preset_asset_ids: ["preset-fast-survey",
  "preset-low-noise-pair"]}`.
- **`ui/manifest.json`** — the three assets with sha256s; one binding
  `{id: "configure", kind: "configuration", target_id: "configure",
  preset_ids: [both]}`; one page `{id: "settings", kind: "configuration",
  title: "Acquisition settings", bindings: ["configure"], required: true}`.
- **Two presets** — complete settings documents, nothing else:
  - `fast-survey`: all four channels (dc, range 5 V, offset 0, probe 1x),
    `sample_rate_hz` 100000, `sample_count` 4096, `pretrigger_fraction` 0,
    `trigger {kind: immediate}`, `configuration_id "preset-fast-survey"`.
  - `low-noise-pair`: channels `ch1` and `ch3` only — a **non-contiguous
    subset**, chosen so enablement-by-membership is visibly not an index slice —
    (10x probes, 1 V ranges, offsets +0.05/−0.05 V), rate 1000, count 1024,
    pretrigger 0.25, `trigger {kind: edge, source_channel: "ch1", slope:
    "rising", level_v: 0.5}`, `configuration_id "preset-low-noise-pair"`.
  - Both: `contract_version "0.1.0"`, `revision "1.0.0"`,
    `plugin_id "dev.benchweave.sim-scope"`, `profile_ids
    ["otdp.oscilloscope/1.0.0"]`, `supported_firmware ["sim-1.0.0"]`,
    `settings_schema {id: <corpus $id>, sha256: <of the settings-schema bytes>}`,
    `provenance {author: "BenchWeave simulator plugins", revision: "1",
    evidence: "synthetic"}` — synthetic because they configure a simulator;
    `documented` would be a false claim about hardware.

### 2.4 How the two acceptance lanes map to code

- **Lane 1, `check-preset`** (`cli.py:144-162` → `presentation.py:87`
  `validate_preset` → vendored `contracts.py:142-235`): decodes preset,
  descriptor and settings schema as exact bytes; validates the preset against
  the canonical `$defs/preset`; checks `plugin_id`, `profile_ids ⊆
  descriptor.profiles`, firmware in both the preset's and the descriptor's
  supported sets; checks the settings-schema digest and `$id` pins; validates
  `preset.settings` against the settings-schema file.
- **Lane 2, `check-ui`** (`cli.py:116-141` → `validate_presentation`,
  `contracts.py:402`): walks envelope → manifest → assets (every asset
  digest-pinned) → catalogue; for the configuration binding it re-runs
  `validate_preset` per referenced preset, **then validates `preset.settings`
  against the canonical corpus action schema** (`contracts.py:521-531`) **and
  against the descriptor action's `input_constraints`** (`contracts.py:532-541`).
  This is the only lane that performs the "both the settings schema and the
  action input schema" acceptance clause, so Row A's proof must run both lanes.

One wrinkle to carry forward explicitly: the action schema requires a
`configuration_id` in settings, so each preset embeds a placeholder. At any
future apply time the gateway-issued token must replace it (the runtime marks
`configuration_id` issued — CTL-7, `control/semantics.py:140-160`; sim_psu's
measure/output enforce the stored token, `sim_psu plugin.py:389-395, 408-414`).
[Corrected in the fix wave, 2026-09-19 — the original sentence claimed
replay "is a trap" the sim exposes; the executed repro showed otherwise:]
the sim's token checks catch only token MISMATCH (a half-substituted apply:
configure under one token, arm under another). CONSISTENT replay — configure
and arm under the same literal preset `configuration_id` — passes clean, and
is pinned as passing by `test_arm_accepts_consistent_replay_documenting_the_
trap`. Defense against consistent replay is the apply path's job: substitute
the gateway-issued token (CTL-7 issued-key marking — which attaches to the
runtime execution-contract dialect and cannot apply to this full-form
descriptor). Row A ships documents only and defers that path (§5).

## 3. Precedent (principle 9)

Every moving part extends a proven in-tree mechanism; none is new architecture:

1. **WP05 action simulator** — `sim_psu` already implements profile actions over
    INVOKE with per-channel state, `configuration_id` token discipline and
    deterministic clocks. `sim_scope` is that pattern on a richer profile.
2. **The preset/manifest/catalogue wiring** — `tests/unit/test_presentation_specimens.py`
    builds exactly this shape (envelope/manifest/catalogue/settings-asset/preset,
    configuration binding with `preset_ids`) against the class-dc_psu example.
    Row A materializes the specimen as a shipped plugin.
3. **Corpus-extracted settings schema** — the specimen extracts the action input
    schema from the catalog as the settings asset (`test_presentation_specimens.py:42-43`);
    Row A adds the drift pin the specimen lacks.
4. **SDK CLI-lane testing** — `tests/sdk/test_presentation_cli.py` drives
    `benchweave_sdk.cli.main` in-process with a syspath prepend; Row A's preset
    tests follow it line for line.
5. **Descriptor-authoring precedent** — the scaffold's synthetic descriptor
    (`scaffold.py:322-384`) and the class examples define the full-form
    conventions (listed firmware, declarative transport, adapter binding,
    provenance with synthetic vectors). `dps150` proves a real-shaped descriptor
    passes `check`.

## 4. Cross-surface sync list (everything that moves)

| Surface | Moves? | Why |
|---|---|---|
| `standards/` bytes, corpus-manifest, `make check-sdk-standards` | **No** | Zero contract change is the row's premise; nothing to repin |
| `packages/sdk` submodule | **No** | `check-preset`/`check-ui` already support everything Row A ships; the pointer does not move |
| MCP tools / openapi / CLI reference | **No** | No interface surface touched |
| Runtime control core (`control/`, `state/`, `interfaces/`) | **No** | Presets are documents; select ≠ apply; no apply path exists or is built |
| `docs/device-developer-guide.md` | **Yes** — one short section | Obligation 3 (plugin/device-visible behavior): point plugin authors at `sim_scope` as the reference instance of authoring `ui/settings/` + `ui/presets/` for a configuration action, and state the labels/units-in-descriptor rule |
| Fixture lattice (`fixtures/execution/`, builder, catalogue.json) | **No** | sim_scope is not wired into execution contracts (see §8 risk 1) |
| `ui/` renderer | **No** | Rendering the configuration page is out of scope; the manifest is valid input to the existing preview/renderer work without requiring it |
| Wheel contents | Grows | `plugins/benchweave` force-include already vendors the tree verbatim (`pyproject.toml:61-63`); a few KB |
| CI | Grows | Two new test files join the existing `gates` pytest job (offline, in-process); no new job, no subprocess orchestration |

## 5. Minimal first increment — and what it DEFERS

The increment ships: the `sim_scope` plugin (descriptor + plugin.py + vectors +
pyproject), its five ui-resource files (envelope, catalogue, manifest, settings
schema, two presets), two test files (§7), and the developer-guide section.

**DEFERS, each with its reason:**

1. **The apply path and select-≠-apply runtime** — designed in the plugin-ui
   spec §Configuration presets, not contracted; Row D territory. Includes the
   `configuration_id` substitution question (§2.4).
2. **Averaging in preset settings** — structurally impossible under closed
   action schemas (§1). Revisit only via a profile revision
   (`standards/GOVERNANCE.md`: copy, never move), which is a separate
   standards-governance event with its own evidence bar.
3. **Bench presets / user drafts lifecycle** — designed, uncontracted (issue
   correction 1); independent of plugin-supplied documents.
4. **Scaffold support for configuration targets** — `create_ui_resources`
   stays observation-only; generating configuration bindings is a scaffold
   interface change (SRF-1) that should wait for a second real instance to
   pattern from.
5. **Preview fixtures for sim_scope** (`ui/fixtures/` + `preview-ui`) — the
   preview lane works for any valid manifest; shipping curated scenario
   fixtures adds polish, not proof.
6. **Runtime execution-contract admission of sim_scope** — blocked by the
   descriptor dialect fork (§8 risk 1); a reconciliation design of its own.
7. **Folding sim_scope into the shared `CONFORMING_PLUGINS` parametrization**
   — the shared suite asserts `operator_note` writes the scope plugin
   deliberately lacks; a separate file now, consolidation when the suite grows
   a capability-based selection.

## 6. Invariant impacts

- **No CTL/STO/CON/REG invariant is created, amended or weakened.** No
  protection, store, transport or admission path is touched.
- The design *applies* existing posture rather than changing it: plugin files
  confer no authority (REG-3/A11 — presets are data; `check-preset`'s own
  success message says "not admission or approval to apply settings");
  presets contain redistributable settings only — [corrected in the fix
  wave:] the closed action schema closes the key SET of `settings`, not the
  string VALUES: an endpoint-looking string inside a corpus-required field
  such as `configuration_id` passes both lanes clean, so
  endpoints/wiring/secrets are narrowed, not structurally unrepresentable
  (the developer guide's narrower phrasing is the accurate one), and the
  no-presentation-fields test (§7) pins that no label/unit/colour leaks in
  either; select ≠ apply holds trivially because no apply exists.

  Mechanism boundary disclosed in the same fix wave: an empty
  `input_constraints: {}` is silently vacuous — sim_scope's own
  arm/trigger/fetch/abort actions declare `{}`, so the lanes check nothing
  beyond the corpus schema for them. Only the configure action's constraints
  bite, and only in lane 2. This becomes load-bearing the day an apply path
  trusts lane 2 as preset verification: vacuous constraints on an action
  would then mean unverified settings.
- One **new plugin-level pin in the CON-2 spirit** (not an amendment — CON-2
  governs the registry fixture lattice): the parsed-equality test tying the
  shipped settings-schema copy to the vendored corpus. Without it the copy is
  exactly the "silent drift: yesterday's guarantees" CON-2 warns about, one
  level down.
- Tier: no on-disk format or gateway schema changes → not Tier 3. Plugin
  package files are data, digest-pinned by their own manifest.

## 7. Measurable proof — pre-committed acceptance rule

**Written before any number below was looked at.** The baseline counts in §7.1
were measured after this rule was drafted; the pass/fail controls in §7.2 are
specified before the artifact exists.

### 7.1 Baseline (measured 2026-09-19, this checkout)

- In-tree plugins passing `benchweave-sdk check`: **1 of 3** (dps150; both sims
  fail on the runtime dialect). Measurement: this session, real CLI.
- In-tree configuration bindings / shipped settings schemas / shipped presets:
  **0 / 0 / 0** (grep over `plugins/` for `ui/presets|binding-catalogue`).
- Behavioral `check-preset` tests: **0** (only the framework smoke list,
  `tests/sdk/test_cli_frameworks.py:21`).

### 7.2 The rule

Population is a **census, not a sample**: the shipped preset set (N = 2) and the
control matrix below. Metric: process exit codes of the real CLI lanes, read
from `cli.main` return values (never output-filter text), plus finding codes
where a control targets a specific refusal.

**SHIP iff all hold:**

1. Lane 1 = 0 for each shipped preset: `check-preset <preset> --descriptor
   <sim_scope descriptor> --settings-schema <ui/settings file> --firmware
   sim-1.0.0` — 2 of 2.
2. Lane 2 = 0: `check-ui <package>/presentation.json --descriptor … --resources
   <package> --catalogue <package>/binding-catalogue.json --firmware sim-1.0.0`.
3. Every RED control exits nonzero **with the expected finding code**:
   - L1-a settings violating the schema (negative `range_v`; smuggled
     `averaging_count` key) → `invalid_settings`;
   - L1-b firmware `other-9.9.9` → `incompatible_firmware`;
   - L1-c settings-schema bytes drifted (trailing newline) → `digest_mismatch`;
   - L1-d preset naming a different `plugin_id` → `identity_mismatch`;
   - L2-a preset settings key outside the action schema → `invalid_settings`
     via the canonical check (the shipped-artifact twin of
     `test_preset_cannot_bypass_canonical_action_schema`);
   - L2-b value inside the corpus schema but outside the descriptor's
     `input_constraints` (`sample_rate_hz` 2e6) → `invalid_settings`;
   - L2-c preset file bytes mutated after manifest pinning → `digest_mismatch`;
   - L2-d catalogue naming a nonexistent preset asset → `unresolved_reference`.
4. Structure pins hold: `test_settings_schema_tracks_corpus` (parsed equality
   with the vendored catalog's action input schema), `test_presets_carry_no_
   presentation_fields` (settings keys ⊆ {configuration_id, channels,
   sample_rate_hz, sample_count, pretrigger_fraction, trigger}; channel-item
   keys ⊆ {channel, coupling, range_v, offset_v, probe_ratio}), `test_
   descriptor_labels_units_present` (every channel has a label; every
   V-dimensioned parameter has unit `V`).
5. Plugin dispatch tests hold (host-ABI, deterministic): configure applies
   per-channel state observable by READ; fetch covers configured channels
   only; out-of-envelope writes (averaging 0, probe 3) rejected
   `INVALID_ARGUMENT`/`NOT_DISPATCHED`; unknown parameter rejected; identify
   and simulation labelling conform.

**KILL iff:** any part of 1–2 can only be made green by editing bytes under
`standards/` (falsifies the row's zero-contract-change premise — escalate to a
contract-change increment with this document as evidence), or any RED control
in 3 passes clean when it should fail (the mechanism is not load-bearing, so
the measurement proved nothing).

**UNDERPOWERED iff:** lane failures are dominated by packaging mechanics
(`unsafe_path`, `unresolved_reference` on the *unmutated* artifacts) rather
than settings semantics — the run measured resource wiring, not Row A; fix the
harness and re-run before concluding anything.

### 7.3 Test files (RED-first: each control written and shown failing against a
deliberately broken artifact copy before the artifact is fixed/finalized)

- `tests/sdk/test_sim_scope_presets.py` — lanes 1–2 over the shipped package,
  the eight RED controls (applied to tmp copies, never the shipped bytes), the
  three structure pins. Modeled on `tests/sdk/test_presentation_cli.py`
  (syspath prepend, `cli.main` exit codes).
- `tests/contract/test_sim_scope_plugin.py` — host-ABI dispatch suite, modeled
  on `tests/contract/test_sim_plugins.py` (injected `Clock`, `NullServices`,
  explicit module load by path).

One RED→GREEN slice per commit: (1) plugin + dispatch tests, (2) ui resources
+ lane tests + controls, (3) docs. The lane tests in slice 2 are written first
against hand-broken copies (mutation matrix), then the real artifacts land.

## 8. Top risks, each with its falsifier

1. **The descriptor dialect fork is the biggest latent trap.** sim_scope's
   full-form descriptor is NOT admissible by the runtime execution-contract
   path (`control/documents.py:111-119` requires the minimal list dialect;
   `binding.py:156,164` and `semantics.py:157` consume it). sim_scope therefore
   cannot appear in execution-contract fixtures or seam runs — a future
   contributor could mistake that for a defect. *Falsifier:* any attempt to add
   sim_scope to `fixtures/execution/` fails `_check_descriptor`; the design
   states the fork rather than papering over it, and reconciliation is deferred
   (§5.6). If the maintainer wants one dialect, that is its own increment.
2. **Settings-schema copy drift.** The corpus bumps 0.1.1 → 0.1.2; the shipped
   copy stales silently. *Falsifier/mitigation:* `test_settings_schema_tracks_
   corpus` fails loudly on parsed inequality the moment the vendored tree
   moves; `make check-sdk-standards` keeps the corpus itself pinned. The
   residual: the pin runs in the same CI job as the standards sync, so both
   move together or the job is red — the drift cannot land silently.
3. **Preset `configuration_id` placeholder replay.** A future apply path that
   replays the literal id collides with gateway token discipline (CTL-7 marks
   the key issued at the runtime layer). *Mitigation, corrected in the fix
   wave:* the sim's token checks refuse only MISMATCHED tokens (the
   half-substituted apply); consistent replay passes and is pinned as
   passing, so the sim is explicitly NOT the replay defense — the apply path
   must substitute the gateway-issued token itself.
4. **Reading-2 mismatch with maintainer intent.** If the maintainer actually
   wanted averaging inside preset settings, Row A as designed delivers less
   than expected. *Falsifier:* §1's table — the closed-schema evidence is
   checkable in one command; the design surfaces the fork as the one open
   decision rather than burying it.
5. **Scope creep via the profile's required actions.** arm/trigger/fetch/abort
   could balloon. *Containment:* each is a deterministic stub sufficient for
   fetch-covers-enabled-channels; no dataset/measurement-schema work (fetch
   returns the plugin-ABI shape, not an admitted dataset — dataset targets are
   a different catalogue kind and out of scope).
6. **`input_constraints` authored wrong** (accidentally widening is impossible
   — constraints are AND-ed — but an over-tight enum could reject legitimate
   presets). *Falsifier:* L2-b proves tightening bites; the two shipped presets
   prove the envelope is livable; any future preset rejected by the enum is a
   descriptor edit, not a standards event.

## 9. DON'T-BUILD assessment

**Build — with one honest partial.** The premise survives every check:
`check-preset` exists and works end to end (verified by reading its full
implementation and running the descriptor gate); the configuration-binding
path performs exactly the both-schema validation the acceptance names; the
oscilloscope profile gives channel enablement and per-channel gain/offset real
preset homes; the artifact set is small, additive and CI-cheap. The partial —
model averaging cannot ride presets under the current closed action schemas —
is a measured negative with its evidence in §1 and its RED control in §7.2;
treating it as anything else (stuffing averaging into `sample_count`,
re-labelling DMM `aperture`, or widening a schema under the table) would be
the silent substitution this project exists to prevent. If the maintainer
reads Row A as Reading 1, this document is the kill record: not buildable
without a standards change, and the change to make is a profile revision
through governance, not this increment.
