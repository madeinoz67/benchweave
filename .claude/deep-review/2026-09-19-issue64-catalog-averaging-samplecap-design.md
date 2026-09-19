# Issue #64 — configure-schema revisions: averaging concept + sample_count maximum

**Status:** design (pre-implementation). **Date:** 2026-09-19. **Base:** `main` @ `8081783`.
**Scope:** one OTDP governance bump (0.1.2 → 0.2.0) carrying two catalog revisions disclosed by
issue #6 row A, plus the in-tree motion the bump obligates. No core `src/benchweave/control/`,
`state/`, or `interfaces/` code changes.

Everything marked `[V]` below was verified by reading the named file/line on this checkout this
session; `[I]` marks inference the build must confirm.

---

## 1. Root cause (why the current state is as it is)

Two independent governance gaps, both structural, both verified:

1. **Averaging has no action-input home.** All 50 catalog action input schemas are
   `additionalProperties: false`; none carries any averaging concept `[V — every input_schema in
   standards/otdp/0.1.2/device-profile-catalog.json; the oscilloscope one at :809]`. sim_scope
   therefore ships `averaging_count` as a writable descriptor *parameter* only
   (`plugins/benchweave/sim_scope/src/benchweave_sim_scope/descriptor.json:369-386`, range
   `[1,64]` at :375), and its own description says why it cannot ride preset settings
   (`descriptor.json:370`). The refusal is pinned by two RED controls that smuggle
   `settings.averaging_count = 8`: `tests/sdk/test_sim_scope_presets.py::test_l1a_smuggled_averaging_key_refused`
   (:159) and `::test_l2a_key_outside_action_schema_refused_by_canonical_check` (:225). The
   consequence: a named measurement setup ("low-noise") cannot express its defining setting in the
   preset — the setting survives only as an out-of-band live write that preset evidence cannot
   carry.

2. **sample_count is unbounded at the corpus.** The three acquisition configure inputs declare
   `sample_count: {type: integer, minimum: 1}` with no maximum `[V — oscilloscope :723,
   logic_analyser :1172, daq :3125]`. Row A's refute F1 showed a lane-passing preset with a huge
   sample_count OOMs fetch; the shipped mitigation bounds it at descriptor + plugin level only
   (`descriptor.json:480` `"maximum": 1000000`; `plugin.py:49` `SAMPLE_COUNT_MAX = 1_000_000`
   enforced at `plugin.py:380-385`). That leaves a pinned honest residual:
   `test_settings_envelope_census_top_level[sample_count-1000000000000-True]` asserts
   **lane 1 exits 0** on a 1e12 preset (`test_sim_scope_presets.py:429-458`, the matrix row
   `("sample_count", 10**12, True)` at :430 with `assert lane1_exit == 0` at :455) — because lane 1
   (check-preset) validates settings against the settings-schema *file* and never consults
   descriptor `input_constraints` (comment block :332-341). Any plugin whose author forgot the
   descriptor ceiling has no bound at all until runtime. The corpus-level bound is the structural
   fix because both lanes consume corpus bytes.

A third fact shapes the design: the plugin's `_action_configure` validates input **manually** and
**silently ignores unknown top-level keys** — there is no `additionalProperties` equivalent at
dispatch (`plugin.py:304-453`; the comment at :391-398 admits trigger-shape keys are "lanes-only").
So admitting `averaging_count` at the corpus without teaching the plugin to *apply* it would
produce the worst outcome: presets pass both lanes, configure returns OK, and the acquisition
never averages — evidence that launders a no-op.

## 2. Bump class and target version

**MINOR: 0.1.2 → 0.2.0.** `[V]` Adding `maximum` to a previously-unbounded property rejects
documents that are valid under 0.1.2 (e.g. `sample_count: 2_000_000`) — a tightening, i.e. a
breaking machine change, which is "MINOR at least" (`standards/GOVERNANCE.md:27`). The
`averaging_count` addition alone is additive (PATCH class, GOVERNANCE.md:26), but "a batch's bump
follows the highest change class it contains" (GOVERNANCE.md:36-37), so both ride one MINOR bump.
`[I]` At implementation time, check no other OTDP bump shares this release train (GOVERNANCE.md
#69 bump-minimization); if one does, re-copy from the new predecessor.

Mechanics (GOVERNANCE.md:43-49): copy `standards/otdp/0.1.2/` → `standards/otdp/0.2.0/`, edit
bytes only in the copy, old dir + its corpus rows stay digest-frozen, new rows record
`source: standards/otdp/0.1.2/<path>` `[V — the 0.1.2 rows follow exactly this pattern against
0.1.1: corpus-manifest.json:394-515]`, digests move only via
`uv run python -m benchweave.standards repin` `[V — CLI verified: export|check|matrix|versions|repin]`.

**Inner version strings sweep with the dir.** `[V]` The 0.1.1 precedent proves it: the 0.1.1 copy
carries `$id: "urn:otdp:measurement:0.1.1"` and descriptor-schema `const: "0.1.1"` even though it
was a byte-errata. So the 0.2.0 copy moves: the measurement schema `$id`, every catalog
`$ref: urn:otdp:measurement:0.1.2#...` (e.g. catalog:664), the descriptor schema's
`otdp_version` const (`otdp-device-descriptor.schema.json:4-6`, currently `"0.1.2"`), and the
catalog's own `catalog_version`/`otdp_version` fields (catalog:2-3). "The standard version IS the
schema/protocol version" (`docs/compatibility-matrix.md:7`).

## 3. Averaging scope

**First slice: `otdp.oscilloscope.configure` only.**

Property shape (input schema, and the output `effective_configuration` mirror):

```json
"averaging_count": {"type": "integer", "minimum": 1, "maximum": 64}
```

- **Optional in both; required lists do NOT change** anywhere (required lists at catalog:801-808,
  :948-955 stay byte-identical). Optionality keeps every existing preset, vector and example valid
  against the input side and avoids escalating churn; the batch is already MINOR via sample_count,
  but required-list additions would invalidate every oscilloscope preset for no gain.
- **Why max = 64:** it is the only in-tree evidence — sim_scope's authored parameter range
  `[1, 64]` (`descriptor.json:375`, `plugin.py:46-47` `AVERAGING_MAX = 64`, live-write vectors in
  `vectors.json:35-56`). Inventing headroom (256, 4096) would be an unevidenced number, which is
  the A02 discipline applied to governance: corpus bounds carry the largest value the in-tree
  evidence supports. Widening for a real instrument later is another reviewed revision.
- **Why oscilloscope-only:** averaging semantics are per-class. Scope averaging averages N
  acquisitions; DAQ averaging would be per-point over-sampling; spectrum-analyser averaging is
  sweep averaging (its prose already keeps "averaging … in context",
  `standards/otdp/0.1.2/device-classes.md:161`); a logic analyser has no averaging at all. Writing
  normative `device-classes.md` semantics for classes with no exercising plugin or lane is
  speculative standardization — the exact thing A10 warns about. The counter-argument (batching
  all acquisition classes into this MINOR avoids a later bump) is acknowledged and rejected:
  governance bumps are cheap, unwritten semantics are not.
- **Echo semantics:** output `effective_configuration` gains optional `averaging_count`. When the
  input carries it, the plugin echoes the applied value; when omitted, sim_scope echoes the
  *effective* depth in force (last written value, default 4 — `plugin.py:90`), because
  "Success returns … the effective configuration actually accepted/read back"
  (`device-classes.md:45`). The corpus leaves it optional so a plugin that genuinely cannot report
  it is not forced to fabricate.
- **Normative prose** (`device-classes.md` §6, after :77): averaging_count is the acquisition
  averaging depth; instruments that cannot average refuse it via `input_constraints` (the §2
  intersection rule, `device-classes.md:27`) rather than silently ignoring it.

## 4. sample_count bound

**`"maximum": 1000000` on six sites in `device-profile-catalog.json`** — the three acquisition
configure inputs and their three `effective_configuration` output mirrors:

| Action | input site | output mirror |
|---|---|---|
| `otdp.oscilloscope.configure/1.0.0` | :723 | :870 |
| `otdp.logic_analyser.configure/1.0.0` | :1172 | :1295 |
| `otdp.daq.configure/1.0.0` | :3125 | :3295 |

- **Value:** 1e6 matches the authored ceiling (`descriptor.json:480`, `plugin.py:49`; README
  "Authored envelopes": 32 MB of float64 across four channels). Same evidence rule as averaging.
  The bound is a **class-level resource backstop for the fetch lane**, not an instrument
  capability claim; per-device `input_constraints` narrow below it (AND semantics,
  `device-classes.md:27,39`), nothing widens past it without a revision.
- **Output mirrors bounded too** so a device reporting an effective count above the class bound is
  malformed evidence, not an asymmetry the schema tolerates. Same breaking class; no extra bump.
- **Explicitly OUT of scope, named:**
  - `otdp.function_generator.upload` output `sample_count` (catalog:2079) — the *accepted waveform
    length*, a different semantic; bounded by upload dataset validation (finite values, unit 1,
    `device-classes.md:101`) and artifact byte budgets, not acquisition memory.
  - `otdp-runtime.schema.json` capture-context `sample_count` (:288) and fetch
    `operationRequest` `sample_count` (:543) — the runtime ABI surface. Fetch already pairs count
    with `max_bytes` (the operative materialization budget, README:64-68), and capture contexts
    serve non-acquisition families (controller telemetry). Bound them in a follow-up with their
    own resource analysis, not by coat-tail.
  - `sample_rate_hz` — no memory shape; the descriptor ceiling (`descriptor.json:479`) stays
    plugin-local. Revisit only with evidence.

## 5. Full in-tree motion list

The bump's real risk is the sweep, not the two schema edits. Precedent: the 0.1.2 bump commit
`709de25` moved 47 files `[V — git show --stat]`. Every declarer below was grep-verified on this
checkout this session.

**A. Standards tree (main)**
1. `standards/otdp/0.2.0/` — full copy of 0.1.2 (25 machine files + prose companions).
2. In-copy edits: catalog (averaging_count ×2 sites, maximum ×6 sites, version fields, measurement
   `$ref` sweep); measurement schema `$id`; descriptor schema const; `device-classes.md` (§6
   averaging prose, class-bound statement in §2, baseline header); `otdp-specification.md`,
   `measurement-model.md`, `extension-contract.md` version-string sweep; `validation-report.md`
   regenerated by the architecture check run; examples: `urn:otdp:measurement:0.1.2` → `0.2.0`
   sweep across `examples/*.json` `[V — census: class-*.json and reference-*.json all carry it]`,
   and `examples/class-action-vectors.json` `oscilloscope-configure` entry (:296-362) gains
   `averaging_count: 8` in input **and** effective_configuration (all example sample_counts are
   ≤ 4 — safe under the bound `[V]`).
3. `standards/standards-manifest.json` — otdp entry: version 0.2.0, released date, supersedes
   0.1.2, normative list repointed at `0.2.0/`.
4. `standards/corpus-manifest.json` — via `repin`: new rows `otdp/0.2.0/*` citing
   `standards/otdp/0.1.2/*` as source; `identity.otdp` → `0.2.0` (identity-block edit moves no
   rows — CON-8; `adapter_api` stays `1.1`).
5. `docs/compatibility-matrix.md` — regenerate (`benchweave.standards matrix`); otdp row becomes
   0.2.0, "Supersedes 0.1.2".

**B. Version-literal sweep (main) — verified declarers of `otdp/0.1.2` / `0.1.2`**
- `tests/contract/test_baseline.py:27` (`ADMITTED_DIRS` — add `otdp/0.2.0`; the tuple is currently
  defined-but-unused `[V — no references found]`; update it truthfully, flag the dead variable in
  the PR, wiring it is deferred) and `:110` (`identity["otdp"] == "0.2.0"` — the drift-obligations
  #8 "orphan identity literal").
- `tests/contract/test_sim_plugins.py:34` (`CONTRACTS`), `tests/contract/test_host_abi.py:4`,
  `tests/contract/test_sim_scope_plugin.py:616`.
- `tests/contracts/test_architecture.py:79,82`; `tests/unit/test_presentation_specimens.py:27,34`
  + the `measurement_schema_id` fixture urns at `:168,234`; `tests/unit/test_presentation_presets.py:29`;
  `tests/unit/test_presentation_manifest.py:28`.
- `tests/unit/test_derivation.py:3,4,33`; `tests/faults/test_derivation_faults.py:26`;
  `tests/sdk/test_derivation_agreement.py:32,33,60,68,143`; `tests/sdk/test_standards_sync.py:49`
  (stamp pin `otdp@0.2.0`).
- `scripts/architecture/check_devices.py:22` (`OUT`), `check_execution.py:303`,
  `assemble_docs_site.py:437`, `registry/registry_common.py:219` (docstring),
  `scripts/sdk_smoke.py:101,220`.
- `src/benchweave/host/types.py:1,4`, `src/benchweave/measurement/derivation.py:3,19`,
  `src/benchweave/control/documents.py:135` — docstrings/comments: paths pointing at the ACTIVE
  tree move; historical statements ("OTDP 0.1.2 lets a descriptor declare…") may stay as history
  where the sentence is about the introducing revision — judgment call, listed in the PR.

**C. sim_scope plugin (the exercising consumer)**
- `descriptor.json`: `otdp_version` → 0.2.0 (:2) — forced, the SDK vendored tree is
  single-active-version and the descriptor schema const gates it `[V — the 0.1.2 lock note records
  this exact re-version obligation]`; `contracts[0]` → `urn:otdp:profile-catalog:0.2.0` + the new
  catalog sha256 (:452-457); `averaging_count` parameter description rewritten (:370 — retire the
  live-write-only prose); configure `input_constraints` gains
  `"averaging_count": {"minimum": 1, "maximum": 64}` (:467-482).
- `plugin.py` `_action_configure`: accept, envelope-validate (reuse `_validate`, :187-194), apply
  through the state write (mirroring the `CHANNEL_FIELDS` re-homing pattern, :59-66), refuse
  out-of-envelope INVALID_ARGUMENT/NOT_DISPATCHED, and echo the effective depth in
  `effective_configuration` (:441-451).
- `ui/settings/oscilloscope-configure.schema.json` — byte-copy of the new corpus input schema
  (`test_settings_schema_tracks_corpus`, `test_sim_scope_presets.py:293-303`, mechanically forces
  this via `sdk.OTDP_VERSION`).
- `ui/presets/low-noise-pair.json`: `settings` gains `"averaging_count": 16` — the semantically
  correct home, and the shipped-bytes proof of admission; `fast-survey.json` deliberately carries
  none — the matched pair pins presence **and** omission. Both presets' `settings_schema.sha256`
  repin (new schema digest; `$id` stays `…:1.0.0:input` — action ids are versioned elsewhere,
  GOVERNANCE.md:92-93, the digest is the authority).
- `ui/manifest.json` (`descriptor_sha256` + three asset digests) and `presentation.json`
  (`manifest.sha256`) repin — the pin chain `repin_manifest_and_envelope` walks
  (`test_sim_scope_presets.py:118-129`).
- `vectors.json`: one configure-carried averaging vector (in-envelope accepted + applied;
  out-of-envelope refused).
- `README.md`: rewrite :51-55 (averaging now preset-carried since OTDP 0.2.0; live write remains
  valid) and the "Authored envelopes" section :83-89 (bound now declared at three authorities —
  see §7).
- sim_scope is **not** in the registry fixture lattice `[V — no hits under fixtures/,
  scripts/registry/, catalogue.json]`; CON-2 does not move.

**D. Docs (main)**
- `docs/device-developer-guide.md:165` — the averaging live-write-only prose rewrites
  (obligation 3: plugin-visible behavior).
- `docs/internal/invariants.md` — **no change** (§9 below). `docs/internal/drift-and-obligations.md`
  — no change (its obligations name mechanisms, not versions).

**E. SDK (standalone checkout `~/Documents/src/benchweave-sdk`; never re-init the submodule)**
- Run the `make sync-sdk-standards` loop (it refuses a dirty submodule working tree): export →
  `benchweave-sdk sync-standards` → `benchweave.standards check` → `pytest tests/sdk
  tests/standards`.
- Moves SDK-side: vendored tree → `standards/otdp/0.2.0/` (0.1.2 dir replaced — single active
  version), `_GENERATED.txt` stamp → `otdp@0.2.0`, `standards-lock.json` regenerated **with an
  honest compatibility note** (model: the 0.1.2 note — descriptors must re-version; presets
  pinning pre-0.2.0 settings-schema bytes must repin; both breaking effects land in this same
  train for the one in-tree consumer), `benchweave_sdk/__init__.py:12` `OTDP_VERSION = "0.2.0"`,
  SDK-side version pins in its own suite.

**F. Order and the two-repo discipline (AGENTS.md #69)**
1. RED commit on a working branch (§6 tests, watched failing).
2. Bump commit(s): corpus copy + edits + `repin` + export + main-side sweep + sim_scope motion.
   Expected and disclosed mid-sequence red: `benchweave.standards check` reports the SDK vendored
   tree at 0.1.2 until the sync + pointer land — the 0.1.2 precedent documented exactly this in
   its commit message `[V — 709de25]`.
3. SDK repo: sync, sweep, SDK tests green, push, **open the SDK PR now** (stacked if a predecessor
   is in flight).
4. Main: advance `packages/sdk` pointer; merge SDK PR, then the main PR. The work is complete only
   when both are merged.

**G. Merge-result pre-checks (tripwires)**
- (a) `UV_PROJECT_ENVIRONMENT=venv uv run python -m benchweave.standards check` — green (main
  corpus = bundle = vendored tree = lock).
- (b) `UV_PROJECT_ENVIRONMENT=venv uv run python -m benchweave.standards matrix --check` — green
  (committed matrix = fresh render). (a)+(b) are `make check-sdk-standards`, the CI `gates` job.
- `benchweave.standards versions` — main otdp 0.2.0, SDK lock 0.2.0, submodule SHA exists on the
  SDK remote (obligation 7: an unpushed pointer commit breaks CI).
- Full `uv run pytest -q` with the submodule at the merged SDK commit — the lane suite syspath-
  prepends `packages/sdk/src` (`test_sim_scope_presets.py:31-33`), so main-side lane tests cannot
  go green before the pointer moves.

## 6. RED-first plan

| # | Test (file::function) | Before (RED) | After (GREEN) |
|---|---|---|---|
| 1 | `tests/sdk/test_sim_scope_presets.py::test_l1a_averaging_within_envelope_admitted` (replaces `test_l1a_smuggled_averaging_key_refused`) | lane 1 refuses `averaging_count = 8` — today's pinned behavior | lane 1 exit 0, no `invalid_settings` |
| 2 | `…::test_l1a_averaging_above_corpus_maximum_refused` (65) and `…::test_l1a_averaging_below_corpus_minimum_refused` (0) | refused as unknown key | refused as out-of-envelope, `invalid_settings` |
| 3 | `…::test_l2a_canonical_corpus_bounds_averaging_not_the_file` (replaces `test_l2a_key_outside_action_schema_refused_by_canonical_check`; permissive schema file + `averaging_count = 65`) | refused (unknown key, canonical) | refused (above corpus max, canonical) |
| 4 | `…::test_settings_envelope_census_top_level` — `TOP_LEVEL_MATRIX` row `("sample_count", 10**12, True)` **flips its lane-1 expectation to `!= 0`** | asserts lane 1 exit **0** today (:455) | asserts lane 1 exit **!= 0** — the sharpest single control that the corpus bound reached the lane |
| 5 | `…::test_l2_descriptor_constraints_tighter_than_corpus_still_refuse` (tmp descriptor with averaging max 8; corpus-legal 16) | n/a (new) | lane 2 refuses, lane 1 passes — pins descriptor-AND vs corpus-OR roles |
| 6 | `tests/contract/test_sim_scope_plugin.py::test_configure_applies_averaging_count_and_reads_back` | plugin ignores the key — read-back stays 4 | configure OK, READ `averaging_count` → 8, echo present |
| 7 | `…::test_configure_refuses_averaging_out_of_envelope` (65) | plugin returns OK (drops key) | INVALID_ARGUMENT / NOT_DISPATCHED |
| 8 | `…::test_configure_omitted_averaging_preserves_state_and_echoes_effective` | echo lacks the key entirely | echo reports the in-force depth (e.g. 4) |
| 9 | Census RED for the corpus edit: commit the `class-action-vectors.json` averaging example **before** the catalog edit — the architecture check fails on `additionalProperties: false` | fails | passes once 0.2.0 lands |
| 10 | `…::test_presets_carry_no_presentation_fields` settings-key set gains `averaging_count` (:307-314); census comment block (:332-341) rewritten — the lane-1 residual now applies to descriptor-only envelopes (range_v, offset_v), not corpus-bounded fields | — | — |

Existing tests that must stay green untouched: `test_configure_refuses_sample_count_above_bound`
(`test_sim_scope_plugin.py:655-681`), the live-write averaging pair (:240-252), `test_l1c` digest
drift, `test_l2b/l2c/l2d`, `test_settings_schema_tracks_corpus` (unchanged mechanically — it is
the in-arc forcing pin that goes red if the plugin schema file lags the corpus).

Honest note on RED distinguishability: out-of-envelope averaging values are refused *both* before
(unknown key) and after (above maximum) the revision — the observable that distinguishes the
worlds is the **in-envelope admission** (#1) and the **lane-1 flip** (#4). #2/#3 are regression
pins, not RED controls; say so in the test docstrings rather than performing a fake RED.

## 7. Descriptor ceiling disposition — RETAIN

Keep sim_scope's authored `input_constraints` ceiling (`descriptor.json:479-480`) and the plugin's
dispatch bound (`plugin.py:49,380-385`), and add the averaging twin. Reasons:

- The three sites encode **three different authorities**: class governance backstop (corpus),
  the plugin's own declared envelope (descriptor), observed runtime behavior (dispatch). They
  coincide numerically today and need not tomorrow — a future revision raising the class ceiling
  for deep-memory instruments must not silently raise the simulator's honest envelope.
- This repo's idiom is redundant pins with mechanical agreement checks, not single sources of
  truth: the corpus manifest, the preset→manifest→presentation pin chain, the SDK lock, CON-2,
  CON-4, CON-7. Removing the descriptor bound deletes a fact; the pin lattice detects drift
  instead of preventing duplication.
- Removing it would weaken lane 2, which ANDs `input_constraints` onto preset settings
  (`test_sim_scope_presets.py:338-341`), down to the corpus bound alone.

The README's "declared twice" sentence becomes "declared at three authorities" (corpus — both
lanes; descriptor input_constraints — lane 2; dispatch validation — runtime).

## 8. Deferrals (each with a home)

1. **Averaging for remaining classes** (daq, dmm, spectrum_analyser, vna, smu) — NEW issue; each
   class gated on written `device-classes.md` semantics plus an exercising consumer.
2. **Runtime capture/fetch `sample_count` bounds** (and the `sample_rate_hz` class-ceiling
   question) — NEW issue; needs its own fetch-lane resource analysis (§4).
3. **Wiring `ADMITTED_DIRS`** into a real admission guard in `test_baseline.py` — NEW small issue
   (currently dead `[V]`; the tuple is updated truthfully in-arc, wiring is not this PR).
4. **#63** descriptor dialect fork — untouched; the re-version does not reconcile the
   minimal-list dialect, sim_scope still cannot join `fixtures/execution/` (README:44-49).
5. **#61** preset lifecycle, **#65** scope polish, **#67** UI affordance for averaging once
   presets carry it, **#73** executor pin — untouched, cited.

## 9. Invariant, drift and CI impacts

- **No new invariant; none amended.** The change is corpus content plus a pin cascade already
  covered by CON-1 (digest-verified admission), CON-4/CON-7/CON-8 (vendored-tree agreement, repin
  discipline, identity derivation), CON-2 (untouched — sim_scope is not in the fixture lattice).
  The plugin applying configure-carried settings is ordinary plugin behavior pinned by its
  dispatch suite, not a core-mechanism invariant. REG-4 is untouched — `adapter_api` stays 1.1,
  no protocol shape moves.
- **Obligations walked** (drift-and-obligations): 3 (device-developer guide — §5D), 6 (vendored
  bytes + repin + check-sdk-standards), 7 (pointer pushed before it lands), 8 (identity literal
  `test_baseline.py:110`, manifest versions, descriptor schema const — all in §5). Obligation 1/2
  (MCP/REST surfaces) do not move — no operation surface changes.
- **Tier:** on-disk schemas and digest pins move — this is Tier 3 in the review rubric.
- **CI cost:** zero new jobs; `gates`/`package` already run the standards checks and the sdk
  smoke (whose `OTDP_VERSION == "0.1.2"` assert at `scripts/sdk_smoke.py:101` is swept). Suite
  grows by ~10 tests, all unit/lane-speed. No e2e additions.

## 10. Pre-committed acceptance rule

Written before any post-revision number was looked at. Baseline measured 2026-09-19 on
`main` @ `8081783` (junitxml attributes, not output-filter lines — the filter printed "No tests
collected" over a green 26/26 run during this very session, the documented rtk trap):

- `tests/sdk/test_sim_scope_presets.py` — **26 tests, 0 failures**, including both averaging
  refusal controls and `test_settings_envelope_census_top_level[sample_count-1000000000000-True]`
  green **with lane-1 exit 0**.
- `tests/contract/test_sim_scope_plugin.py -k "averaging or bound"` — **2 tests, 0 failures**.

**SHIP iff all of:**
1. Shipped `low-noise-pair.json` (now carrying `averaging_count: 16`) and a synthetic
   `averaging_count = 8` preset: lane 1 exit 0 **and** lane 2 exit 0, no `invalid_settings`.
2. `averaging_count` ∈ {0, 65}: lane 1 ≠ 0 with `invalid_settings`, lane 2 ≠ 0 (canonical),
   dispatch INVALID_ARGUMENT/NOT_DISPATCHED.
3. `sample_count = 10**12`: lane 1 ≠ 0 (**the flip**), lane 2 ≠ 0, dispatch refuses;
   `sample_count = 1_000_000`: all three pass.
4. Configure with `averaging_count = 8` then READ → 8 (applied, not dropped); echo present;
   omission preserves prior state and still echoes the effective depth.
5. Census counts unchanged: 12 profiles, 50 actions (`scripts/architecture/check_devices.py`
   pins both); zero required-list diffs in the catalog (reviewer checks the diff hunks).
6. Gates: `uv run ruff check .`; bare config-driven `uv run mypy`; `uv run pytest -q`;
   `make check-sdk-standards` (= tripwires a+b); drift walk of §9 obligations.

**KILL if:**
- Post-revision lane 1 still exits 0 on `sample_count = 1e12` — the corpus bound never reached the
  shipped settings-schema bytes; the mechanism failed.
- Averaging admission is green but the dispatch read-back ≠ 8 — the plugin dropped it; that is
  evidence laundering, worse than the status quo (a refusal we understood).
- Green is achievable only by hand-splicing a digest — the repin loop is broken; stop and fix the
  loop, never the manifest.
- Any catalog required list changed — scope violation.

**UNDERPOWERED (not conclusive):** a lane exit ≠ 0 whose findings lack the expected code (an
unrelated refusal masquerading as the boundary) — inspect the findings set, do not re-roll. The
shipped preset census is N = 2 by design (presence + omission); if either preset's control is
indeterminate, add a synthetic third document rather than widen any envelope.

## 11. Top risks

1. **The mid-sequence-red window invites a hand-splice.** Between the main bump commit and the
   SDK pointer, `benchweave.standards check` is red. Falsifier for this design: if the prescribed
   order cannot reach green without manual manifest edits, the design's mechanics are wrong —
   kill and re-derive, per CON-7.
2. **Sweep miss.** A declarer left at 0.1.2 either fails CI loudly (gates) or points prose at a
   frozen tree silently (docstrings). Mitigation: the §5B census is grep-verified; residual risk
   is concentrated in prose judgment calls — enumerate them in the PR body. Falsifier: any
   `grep -rn 'otdp/0.1.2'` hit outside `standards/otdp/0.1.[12]` and git history after the sweep.
3. **The unknown-key tolerance recurs.** `_action_configure` ignores unknown top-level keys
   (verified), so the next corpus admission will silently no-op at dispatch again unless its
   plugin is taught. This increment's guard is the read-back assertion (#6), not the echo — an
   echo alone cannot distinguish "applied" from "parroted". Falsifier: a future admission whose
   RED suite lacks a read-back-style control.
4. **The bounds prove too tight** (averaging 64, count 1e6) for the next real instrument —
   accepted cost: another reviewed MINOR revision, with the evidence that motivates it. That is
   the governance loop working, not failing.
