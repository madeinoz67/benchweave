# Issue #62 — SDK preset-validation scope: lane-1 envelope blindness + unreferenced-preset gap

**Status:** design (pre-implementation). **Date:** 2026-09-19.
**Evidence base:** main checkout `main` @ `cc501b2`; SDK standalone checkout `main` @ `e0c09dc`
(post-OTDP-0.2.0). Both gaps were re-verified against the real CLI lanes in-process on these
SHAs (see §7 "measured BEFORE").

## 0. Verdict

BUILD — as one **plugin-ui 0.2.0 standards train**. Both gaps are real and measured, and the
fix rides entirely proven mechanisms: the canonical-validator pattern (`contracts.py`
vendored byte-for-byte into the SDK), the copy-never-move bump mechanics, and the census
harness. There is no new architecture. The dominant cost is the version bump's re-version
cascade, which is precedented (OTDP 0.2.0, issue #64, one train earlier) and unavoidable
(§3 explains why a no-bump change is structurally refused by the drift gates).

One honest negative survives the fix and is stated up front: **lane 1 still applies no
descriptor envelope for plugins whose authored settings schema deliberately carries a
non-corpus `$id`** — for those, the default invocation degrades loudly (a printed note, §4.1)
and full envelope coverage remains lane 2's job (or the explicit `--action` flag). Closing
that residual would require inventing an action-inference the preset contract cannot support
(§2.1).

## 1. Root cause, verified

The canonical validator `src/benchweave/presentation/contracts.py` (byte-identical to the
SDK's vendored `src/benchweave_sdk/standards/plugin-ui/contracts.py`, verified `diff` clean;
the SDK lock pins its sha256 `3154f33…` as a `plugin-ui@0.1.1` file) has two structural
facts:

**Gap 1 — lane 1 never consults descriptor actions.** `validate_preset`
(`contracts.py:142`) validates `preset.settings` against exactly one schema: the
author-supplied settings-schema bytes (`:226-233`, code `invalid_settings`). The descriptor
bytes it already receives are used only for identity (`plugin_id`), profiles, and firmware —
never for `actions[*].input_constraints` and never for the canonical corpus action schema.
The check-preset CLI already **requires** `--descriptor` (`benchweave_sdk/cli.py:146`), so
this is not a missing input; the validation simply never reaches the descriptor's action
table. The envelope checks exist only inside `validate_presentation`'s configuration-binding
loop (`:541-549` canonical corpus schema; `:552-559` descriptor `input_constraints`).

Structural cause: **a preset document does not name an action.** The plugin-ui 0.1.1 preset
shape (`ui-manifest.schema.json` `$defs.preset`) carries `settings_schema {id, sha256}` but
no `action_id`; the action association exists only through binding → catalogue target in
lane 2. Lane 1 has no binding, so it has no action — unless one is derived or supplied
(§4.1).

What is blind after OTDP 0.2.0: the corpus action schema for
`otdp.oscilloscope.configure/1.0.0` (verified in `standards/otdp/0.2.0/device-profile-catalog.json`)
bounds `sample_count ≤ 1e6` and `averaging_count ∈ [1,64]` — and sim_scope's shipped
settings-schema file is a parsed-equal copy of that schema (pinned by
`test_settings_schema_tracks_corpus`), so those bounds reach lane 1 through the file. The
**remaining blind class is descriptor-only envelopes**: `range_v [0.001,10]`,
`offset_v [-10,10]`, `probe_ratio enum {1,10,20,50}`, channel pattern `^ch[1-4]$`,
`sample_rate_hz ≤ 1e6` — all declared only in
`plugins/benchweave/sim_scope/src/benchweave_sim_scope/descriptor.json:675-712`
(`actions["otdp.oscilloscope.configure/1.0.0"].input_constraints`) and absent from both the
authored schema and the corpus schema. The guide documents this as expected behavior
(`docs/device-developer-guide.md:173-183`).

**Gap 2 — check-ui validates only binding-referenced presets.** The loop at
`contracts.py:524` iterates `binding.get("preset_ids", [])`. An asset that is declared in
the manifest (digest-checked via `_resource`, `:479-486`) but referenced by no
configuration binding — or declared by a target's `preset_asset_ids` yet listed by no
binding — receives a digest check and nothing else. Both sub-cases verified red (§7).

## 2. Why the fix must be a standards bump (and cannot be SDK-local)

`src/benchweave/presentation/contracts.py` is a **normative path of the plugin-ui 0.1.1
standard** (`standards/standards-manifest.json`, plugin-ui entry, last normative row). The
sync check (`src/benchweave/standards/check.py:run_check`) re-exports the bundle and
compares the exported `plugin-ui/contracts.py` digest against the SDK lock at the same
version — a byte change with no version move fails `make check-sdk-standards` with
`content_drift_without_version` (`check.py:112-122`). GOVERNANCE.md's drift gate refuses
normative bytes changing without a bump. So:

- Gap 2's fix must edit `validate_presentation` inside `contracts.py` (the SDK wrapper
  `benchweave_sdk/presentation.py` only forwards `resources` and the vendored call's
  findings; it cannot see which presets the loop validated without duplicating the
  enforcement logic — exactly the fork CON-4 exists to prevent).
- Gap 1's fix belongs in the same file once a bump is forced anyway: putting lane-1
  envelope application in the SDK wrapper would create two enforcement sites for the same
  envelope semantics (wrapper for lane 1, vendored module for lane 2) that can drift
  independently. One enforcement point, vendored byte-for-byte, is the in-tree precedent.

**Change class: MINOR (0.1.1 → 0.2.0).** Gap 2 refuses packages that previously passed (an
unreferenced preset asset becomes a finding) — a tightening. Direct precedent: OTDP
0.2.0's `sample_count` bound was classified MINOR precisely because "documents valid under
0.1.2 are refused" (standards-lock compatibility notes). Gap 1 alone would be additive
errata (optional parameter, default-on resolution never adds findings — §4.1), but a batch's
bump follows the highest change class it contains (GOVERNANCE, bump minimization), so one
MINOR bump carries both. The standards-governor review confirms or reclassifies at PR time;
a PATCH that silently refuses previously-valid documents would misstate severity.

Bump mechanics per GOVERNANCE: copy `standards/plugin-ui/0.1.1/` → `0.2.0/`, edit only the
copy; 0.1.1 stays digest-frozen; corpus-manifest 0.2.0 rows cite the 0.1.1 corpus paths as
`source`; pins move only via `uv run python -m benchweave.standards repin`. Note
`contracts.py` is not a corpus-manifest row (main's `corpus-manifest.json` pins only the
four schema JSONs for plugin-ui); its bytes travel manifest → export → SDK lock.

## 3. Design

### 3.1 Gap 1 — descriptor-aware envelope validation in `validate_preset`

**Mechanism.** In the 0.2.0 copy of `contracts.py`:

1. `validate_preset` gains a keyword-only optional parameter `action_id: str | None = None`
   (default `None` = today's behavior, plus the resolution below).
2. New pure helper `_preset_envelope_findings(preset, action, documents, path)` — factored
   OUT of the existing lane-2 lines (`:541-559`) so both callers share one implementation —
   applies, AND-wise, code `invalid_settings`:
   the canonical corpus action input schema when resolvable, and the descriptor action's
   `input_constraints` (an empty constraint schema is a natural no-op under
   `Draft202012Validator`, same as lane 2 today).
3. Action resolution order:
   - explicit `action_id` wins; if it names an action absent from `descriptor["actions"]`,
     emit `Finding("unresolved_reference", "preset.action", …)` — a caller/declaration
     mismatch, refused loudly, never silently skipped;
   - otherwise resolve by identity: scan `schema_documents` for a document whose
     `actions[action]["input_schema"]["$id"]` equals `preset["settings_schema"]["id"]`
     (the same scan pattern `_target_findings` already uses for `action_schemas`). This is
     exact, not a heuristic: lane 2 *requires* the settings-schema `$id` to equal the bound
     action's corpus input-schema `$id` (`identity_mismatch` otherwise,
     `contracts.py:507-511`), so every preset that could ever pass lane 2 resolves to its
     own action. Multiple actions never share an input-schema `$id` in the corpus
     (urn-per-action), so the match is unique;
   - no match (authored schema with a custom `$id`): apply no envelope, and say so — the
     check-preset success message prints the loud negative (below). No new finding, no new
     failure. This is the optionality the issue names: descriptors without constrained
     actions, and custom-schema presets, behave exactly as today.
4. Canonical lookup given an action id: same scan — first document in `schema_documents`
   carrying `actions[action_id]["input_schema"]` (only the device-profile catalog does).

**CLI surface.** `benchweave-sdk check-preset` gains an optional `--action` flag passed
through the SDK wrapper (`benchweave_sdk/presentation.py:87-97` gains the pass-through). The
default path needs no flag. The `_render_report` success message for check-preset is
extended (CLI layer, SDK repo) to state which envelope was applied or, when none was, why:
`envelope applied: <action_id>` / `no descriptor envelope applied (settings schema is not a
corpus action schema; pass --action to force one)`. This is the "degrade loudly" half; the
measurable half is the exit code. `ValidationReport`'s shape is deliberately unchanged
(no new field) — the CLI recomputes the note via a small exported pure helper
(`resolve_preset_action`) that `validate_preset` itself uses, so the note cannot disagree
with the enforcement.

**Why not auto-apply the single constrained action** (the count heuristic): a plugin with
two configuration actions where only one declares `input_constraints` (e.g. a PSU:
`set_output` constrained, `set_ovp` not, both with a `voltage` field and different
legitimate ranges) would have the wrong envelope ANDed onto the other action's presets — a
false refusal on a valid package. The `$id` resolution cannot mis-bind a package that lane
2 accepts; the count heuristic can. Rejected.

**Why not a third lane:** the issue floats "(or a new lane)". A third CLI command fragments
the "validate with both SDK lanes" story the guide must now re-scope anyway, and adds a
surface to keep in sync with nothing new enforced. The optional-parameter extension keeps
one command, one report type, one enforcement module. Rejected.

### 3.2 Gap 2 — every preset-shaped asset validated or refused in `validate_presentation`

Three changes inside the 0.2.0 `contracts.py` `validate_presentation`:

1. **Target-centric preset validation.** After the binding loop's structural checks
   (membership, kind agreement — unchanged), iterate configuration *targets*: for each
   target, resolve `schema_asset_id` (missing asset ⇒ `unresolved_reference`, as today for
   binding-referenced presets, now also covering declared-but-unlisted ids) and validate
   **every** `preset_asset_ids` entry via `validate_preset` + the shared
   `_preset_envelope_findings` — regardless of whether any binding lists it. A
   target-declared preset is wired by the author; binding exposure is a UI choice, so a
   *valid* declared-unused preset still passes. The binding loop keeps only its membership
   and kind checks, so a binding naming a preset the target does not declare still yields
   `unresolved_reference` (existing behavior, existing path).
   Side effect, accepted and noted: a preset listed by two bindings is now validated once,
   not twice (finding de-duplication on multi-binding packages).
2. **Orphan sweep with a new finding code.** For every manifest asset not claimed by any
   configuration target's `preset_asset_ids`, probe preset shape: parse with
   `parse_document` (a `DocumentError` — including the 256 KiB `MAX_DOCUMENT_BYTES` refusal
   — means not preset-shaped, skipped) and require a dict carrying `contract_version` plus
   both `settings` and `settings_schema` keys. A positive probe on an unclaimed asset emits
   `Finding("unreferenced_preset", <asset-id>, "Preset-shaped asset no configuration
   target declares")`. Rationale for refusing rather than validating: an unclaimed preset
   has no action association and no schema asset association; inferring either is the
   heuristic this design refuses elsewhere. The author wires it (then change 1 validates
   it fully) or deletes it. This is a Python-seam semantic check in the style of the
   channel-hints membership checks; the schema stays silent on asset-to-target wiring.
3. The probe cost is bounded: assets are already fully read and digested; `parse_document`
   caps at 256 KiB so the probe cannot be ballooned by a large non-preset asset.

**Finding-code surface:** new `unreferenced_preset`; reuses `invalid_settings`,
`unresolved_reference`, `identity_mismatch`, `digest_mismatch`, `incompatible_firmware`
unchanged. The 0.2.0 README and validation-report document the new code (prose companions
move with the bump).

### 3.3 What does NOT change

- The preset/manifest/envelope/catalogue schema shapes (only `contract_version` consts and
  `$id` roots move to 0.2.0 — no new fields, none removed).
- Lane 2's authority set for referenced presets (identical three checks, now shared code).
- The gateway: `benchweave.presentation.admission.validate_attachment` forwards to
  `validate_presentation` and its only caller is `scripts/sdk_smoke.py` (verified — no live
  admission path consumes presentation findings today), so the gateway inherits the
  tightening at its next smoke run without code motion.
- CTL/STO/CON/REG invariants: none amended, none added. The design *uses* CON-4 (vendored
  sync), CON-7 (repin). Review rubric tier: **Tier 3** (schema files + sha256s move).

## 4. Two-repo motion (order per AGENTS.md: SDK PR first, then main pointer)

**Main branch `feat/issue62-plugin-ui-020`** (one train, in-arc per GOVERNANCE bump
minimization):

1. `standards/plugin-ui/0.2.0/` copied from 0.1.1; schema `$id`s and `contract_version`
   consts → 0.2.0; new README + validation-report rows (both behavior changes, the new
   finding code, the resolution rule and its loud negative) citing 0.1.1 corpus paths as
   `source`. 0.1.1 tree untouched.
2. `src/benchweave/presentation/contracts.py`: `SCHEMA_ROOT` → 0.2.0; the §3.1/§3.2 code.
3. `standards/standards-manifest.json`: plugin-ui → `0.2.0`, `supersedes: 0.1.1`,
   `released: <date>`. Then `edit → repin → export` (`uv run python -m
   benchweave.standards repin`; corpus-manifest gains frozen-source 0.2.0 rows).
4. sim_scope re-version + repin: `ui/manifest.json`, `presentation.json`,
   `binding-catalogue.json`, both presets → `contract_version 0.2.0`; digest cascade
   (preset bytes change ⇒ manifest asset pins ⇒ envelope manifest pin). `descriptor.json`
   untouched (OTDP-side). Same mechanism as the #64 wave.
5. Docs: `docs/device-developer-guide.md:173-183` lane text re-scoped (both lanes enforce
   the envelope; lane 1 resolves the action by settings-schema identity, loud negative for
   custom schemas; unreferenced preset assets are refused); sim_scope README "Authored
   envelopes" paragraph updated (`input_constraints` now AND-ed by both lanes).
6. Tests (see §5 RED plan; full motion list): census flips + preamble rewrite,
   `tests/unit/test_presentation_presets.py` (0.1.1→0.2.0 glob + literals),
   `tests/unit/test_presentation_specimens.py`, `tests/unit/test_presentation_manifest.py`,
   `tests/unit/test_presentation_contracts.py` (version literals),
   `tests/standards/` bump tests, `tests/contract/test_baseline.py` (admits 0.2.0).
7. Export the bundle; `make sync-sdk-standards` into the SDK checkout.

**SDK branch `feat/issue62-plugin-ui-020`** (commit, push, **open the SDK PR now**):

1. Vendored tree via sync: `src/benchweave_sdk/standards/plugin-ui/0.2.0/` replaces the
   0.1.1 dir (single-active-version, per the OTDP 0.2.0 sync `f5e05fa`), updated
   `contracts.py`, regenerated `_GENERATED.txt` stamp.
2. `standards-lock.json`: plugin-ui → 0.2.0 with new digests; compatibility block notes
   the tightening ("packages with unreferenced preset assets are refused; documents
   re-version to 0.2.0; lane-1 check-preset now applies descriptor envelopes when the
   settings schema identifies a corpus action").
3. `src/benchweave_sdk/validation.py`: `sets` tuple `("plugin-ui", "0.1.1")` → `0.2.0`.
4. `src/benchweave_sdk/presentation.py`: `validate_preset` wrapper passes `action_id`
   through; `create_ui_resources` emits `contract_version 0.2.0` (three literals:
   manifest, envelope, catalogue).
5. `src/benchweave_sdk/cli.py`: optional `--action` on check-preset; envelope-applied /
   loud-negative note in the success render.
6. SDK's own suite (3 files: release/tag/version-constants) — no presentation tests live
   SDK-side today; per established rhythm the lane proof is main-side (`tests/sdk/`
   syspath-prepends `packages/sdk/src`). No new SDK-side behavioral tests; CI green.

**Then main pointer commit** advancing `packages/sdk`, `make check-sdk-standards` green at
the pointer (includes `matrix --check`; the compatibility matrix gains the plugin-ui 0.2.0
row — regenerate), main PR referencing the SDK PR. Merge SDK first; a work is complete only
when both PRs are merged (#69).

**SDK version disposition (deliverable):** do **not** bump `benchweave-sdk`'s version in
this PR. Precedent: the OTDP 0.2.0 vendoring + behavior change (`f5e05fa`, 2026-09-19)
merged without touching `pyproject.toml` (`version = "0.0.2"` unchanged; the last version
commit is `0f105a3 chore(release): 0.0.2`); the lock's `compatibility.sdk` stayed `0.0.2`.
PyPI publishes on tag via Trusted Publishing, so the user-visible change rides the next
release train as 0.0.x — matching the principal's standing bump-minimization rule (one bump
per standard per train; never stack release bumps on standards motion).

**SDK docs site:** the CLI reference pages are generated from `--help` at assembly
(`scripts/assemble_docs_site.py`); `--action` and the note appear at the next release
assembly in `reference/cli/check_preset.*`, `reference/cli/benchweave_sdk.*`, and
`llms*.txt`. The user-guide page makes no lane-scope claim (checked), so no hand edit.
`.docs-assembly` is untracked build output (verified not in SDK git).

## 5. RED-first plan (tests that fail before the change)

All lane behavior tests live main-side. Measured-today reds (verified in-process this
session, §7):

| # | Test (new or moved) | RED today because |
|---|---|---|
| 1 | `tests/sdk/test_sim_scope_presets.py::test_descriptor_envelope_census` — the six `should_refuse=True` rows of `ENVELOPE_MATRIX` change `assert lane1_exit == 0` → `assert lane1_exit != 0`: `("range_v", 25.0)`, `("range_v", 0.0005)`, `("offset_v", 100.0)`, `("range_v", 10.001)`, `("range_v", 0.0009)`, `("offset_v", -10.001)` | lane 1 exits 0 on all six today (empirically confirmed for `range_v=25.0`; the current code pins all six) |
| 2 | same file, `test_l2_descriptor_constraints_tighter_than_corpus_still_refuse` — keep the trailing `lane1 == 0` (now true because the *shipped* descriptor's `[1,64]` admits 16), rewrite the docstring, and ADD: lane 1 against the package's narrowed tmp descriptor (new `descriptor=` param on the `lane1` helper) exits `!= 0` | the added assertion fails today: lane 1 never consults descriptor actions |
| 3 | new `test_l1_default_resolves_action_by_schema_identity`: preset with `settings_schema.id = "urn:otdp:action:oscilloscope.configure:1.0.0:input"`, `range_v = 25.0` → `lane1 != 0` and `invalid_settings` in `preset_report()` findings | measured red (§7 case 1) |
| 4 | new `test_l1_custom_settings_schema_applies_no_envelope_loudly`: settings schema re-`$id`ed `urn:test:custom` (digest repinned) → `lane1 == 0`, no envelope finding | the *control* row — must stay green before and after; pins the optionality requirement |
| 5 | new `test_l1_explicit_action_flag_forces_envelope` (+ `--action` naming an absent action → `unresolved_reference`) | option does not exist today (CLI-level red) |
| 6 | new `test_l2e_unreferenced_preset_asset_refused`: declared manifest asset, preset-shaped, no target claims it → `check-ui != 0`, `unreferenced_preset` in findings | measured red (§7 case 2: exit 0 today, including an envelope-violating orphan) |
| 7 | new `test_l2f_target_declared_unlisted_preset_validated`: target `preset_asset_ids` gains a preset the binding does not list; envelope-violating copy → `invalid_settings`; a valid copy → still exit 0 | red today: declared-unlisted presets get no validation at all |

Supporting main-side motions (not RED, mechanical): `tests/unit/test_presentation_presets.py`
fixture glob `standards/plugin-ui/0.1.1` → `0.2.0` and `contract_version` literals;
specimens/manifest/contracts suites' version literals; `tests/standards/` and
`tests/contract/test_baseline.py` bump rows; census preamble comment rewrite (the
"Lane 1 is pinned at its honest structural behavior … never consults the descriptor's
action input_constraints" paragraph is now false).

RED-sanity protocol: before the SDK change, run the new/changed tests at the pre-change
pointer and record failures (counts from `--junitxml`, `UV_PROJECT_ENVIRONMENT=venv`);
after, re-run plus the full battery. `no tests ran` is a failed check.

## 6. Deferrals (each with a home)

- **Full canonical validation of unclaimed orphans** (recovering the authored schema via
  the preset's `settings_schema.sha256` against manifest assets, action inference): NEW
  issue at PR time. This design refuses orphans instead of guessing their wiring.
- **Descriptor dialect fork** — untouched; lane 1 reads the SDK dict-dialect descriptor
  only, and sim_scope remains a presentation vehicle: existing issue #63.
- **Preset lifecycle / apply path** (gateway-issued `configuration_id`, apply as approved
  procedure): #61.
- **Preview-renderer/console surfacing of `unreferenced_preset`** beyond the existing
  findings table: #67 (UI).
- **Executor pin / census hardening follow-ons**: #73.
- **Corpus-level `sample_rate_hz` ceiling** (currently descriptor- and plugin-only — the
  corpus schema has no max): an OTDP content change, out of scope; raise as its own issue
  if wanted (it would be a new OTDP train, not this one).
- #65 (polish), #76–#79: untouched by this design; listed for completeness per the issue
  tracker's deferral map.

## 7. Pre-committed acceptance rule

**Written before any post-change measurement.** All lane numbers are CLI exit codes read
from in-process `cli.main` returns (the census method), on documents derived from the
shipped sim_scope package via tmp copies; finding codes from the returned reports.
BEFORE values below were measured 2026-09-19 at main `cc501b2` + SDK `e0c09dc`.

- **Metric A (lane-1 envelope, default invocation).**
  BEFORE (measured): `range_v=25.0` → lane 1 exit `0`. The census pins all six
  `should_refuse=True` rows at exit `0`.
  AFTER (rule): all six rows exit `!= 0`; the three `should_refuse=False` rows
  (`range_v 10.0`, `range_v 0.001`, `offset_v −10.0`) still exit `0`; both shipped presets
  still exit `0` (sample: the full shipped set, N=2).
  **Ship** iff 6/6 refuse AND 3/3 endpoints admitted AND 2/2 shipped presets pass.
  **Kill** if any True row still exits 0 (mechanism not applied — do not widen the
  assertion) or any False row / shipped preset newly refuses (over-tightening — the
  resolution rule is wrong, not the corpus).
- **Metric B (orphan refusal).**
  BEFORE (measured): a declared, preset-shaped, envelope-violating orphan → check-ui exit
  `0`; likewise with a second valid orphan present.
  AFTER (rule): exit `!= 0` with `unreferenced_preset` present; `invalid_settings` NOT
  required for the unclaimed orphan (it is refused, not settings-validated). Controls: the
  unmodified package exits `0`; a package with a valid extra target-declared (unlisted)
  preset exits `0` (metric B2, test #7).
  **Ship** iff refuse + both controls hold. **Kill** if the valid-extra-preset control
  refuses (change 1 over-tightened) — fix the loop, never the control.
- **Metric C (optionality / no new descriptor-less failures).** A preset whose settings
  schema carries a custom `$id` exits `0` in lane 1 with no envelope finding, before and
  after (this row is green in both worlds on purpose). **Kill** the default-on resolution
  if it refuses this row.
- **Gates:** main — `uv run ruff check .`; bare config-driven `uv run mypy`; focused
  `uv run pytest tests/sdk/test_sim_scope_presets.py tests/unit/test_presentation_*.py
  tests/standards tests/contract/test_baseline.py`; full cold suite; `make
  check-sdk-standards` (sync check + `matrix --check`) at the advanced pointer. SDK repo —
  its CI (lint/type/3 tests + wheel build). CI cost: no new jobs, no new lanes; existing
  `gates`/`package` jobs cover both repos.
- **Underpowered, not conclusive:** if census rows fail for cascade reasons (re-version
  breaking collection, repin missed) rather than the envelope assertion, the run is
  inconclusive — repair the harness and re-measure; never tune an assertion to a partial
  result.

## 8. Top risks and falsifiers

1. **The re-version cascade strands consumers** (plugin-ui 0.2.0 refuses every 0.1.1
   document). Falsifier: any in-tree package or fixture failing after the in-arc motion.
   Blast radius today is exactly one in-tree consumer (sim_scope) plus scaffold output —
   the OTDP 0.2.0 train proved the pattern. External authors exist only hypothetically
   (SDK 0.0.x, public corpus is sim_scope + scaffold); the SDK release notes must carry the
   migration line.
2. **Schema-identity resolution mis-binds** when an author pins action A's corpus `$id` on
   a settings schema used for action B's presets — lane 1 would apply A's envelope. But
   that package already fails lane 2's `identity_mismatch` (settings `$id` ≠ target
   `input_schema_id`), so lane 1 only refuses earlier with a blunter message. Falsifier: a
   package that passes lane 2 today but refuses lane 1 after the change — metric A's
   False-rows control is designed to catch exactly this.
3. **Governance misclassification** (review wants PATCH, not MINOR, or wants the changes
   split). The design's class argument is §2's; the standards-governor review at PR time is
   the deciding gate. Falsifier for the whole train: if the governor holds that a
   validator-only tightening with no schema-shape change warrants no bump at all, the
   fallback is an SDK-lock-only digest motion — which `check.py` mechanically refuses
   (`content_drift_without_version`) and GOVERNANCE forbids, so the fallback is
   DON'T-BUILD-pending-governance-change, not a quiet in-place edit.

## 9. Surfaces walked (drift-and-obligations)

Obligation 6 (vendored bytes → repin/export/`check-sdk-standards`) — central to this
design. Obligation 7 (submodule pointer pushed before the pointer lands; renderer
freshness — no renderer change, `ui` job unaffected). Obligation 8 (adapter protocol
surface — untouched; no adapter-API motion). Obligation 3 (device-developer guide — lane
text). Obligation 5 (fixture lattice — untouched; plugin-ui is not in `fixtures/registry/`).
Docs-coverage duty: this diff *should* touch `docs/device-developer-guide.md`, sim_scope
README, plugin-ui 0.2.0 README + validation-report, and the SDK release notes at train
time — each is named in §4. CI map: no new jobs; the `gates` job's `check-sdk-standards`
step is the one that would catch a missed sync.

## Appendix — verified anchors

- `benchweave_sdk/cli.py:144-162` check-preset (`--descriptor`/`--settings-schema`/`--firmware` all required).
- `benchweave_sdk/presentation.py:87-97` `validate_preset` wrapper (parses + schema-validates the descriptor, then delegates to the vendored module).
- `benchweave_sdk/validation.py` `contract_documents()` `sets` includes `("plugin-ui", "0.1.1")`.
- `src/benchweave/presentation/contracts.py:20` SCHEMA_ROOT; `:142` `validate_preset`; `:226-233` authored-schema check; `:422` `validate_presentation`; `:524` binding-referenced-only loop; `:541-549` canonical; `:552-559` input_constraints. Byte-identical to both vendored copies (verified).
- `standards/standards-manifest.json` plugin-ui 0.1.1 normative rows (last row = contracts.py path).
- `standards/corpus-manifest.json` — plugin-ui rows are the four schemas only; no contracts.py row.
- SDK `standards-lock.json` — `plugin-ui/contracts.py` sha256 `3154f33…` at 0.1.1.
- `standards/GOVERNANCE.md` — change classes, bump minimization, copy-never-move, drift gates.
- `src/benchweave/standards/check.py:112-122` `_compare_lock` same-version digest drift refusal.
- `tests/sdk/test_sim_scope_presets.py` — `ENVELOPE_MATRIX` (6 flip rows enumerated in §5), `TOP_LEVEL_MATRIX` (already lane-1-refusing via the settings-schema bytes — unchanged by this design), census preamble, `test_l2_descriptor_constraints_tighter_than_corpus_still_refuse`.
- `plugins/benchweave/sim_scope/` — descriptor `:675-712` configure input_constraints; `ui/manifest.json` (3 assets, 1 binding, both presets referenced — no orphans); `binding-catalogue.json` (one configuration target); both presets in-envelope (verified field-by-field).
- `docs/device-developer-guide.md:173-183` — the lane text to re-scope.
- `scripts/sdk_smoke.py:141` — `validate_attachment`'s only gateway-side caller.
- Corpus `device-profile-catalog.json` 0.2.0 oscilloscope configure `input_schema` — no per-channel bounds, no `sample_rate_hz` max (the descriptor-only blind class).
