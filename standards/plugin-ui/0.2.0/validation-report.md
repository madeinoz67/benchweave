# Plugin UI contracts 0.2.0 — validation report

Evidence record for the SDK preset-validation scope increment (issue #62; design
`.claude/deep-review/2026-09-19-issue62-sdk-validation-scope-design.md`, committed
on the branch before any implementation, with its pre-committed acceptance rule
§7). The 0.1.1 increment's evidence record remains in
`standards/plugin-ui/0.1.1/validation-report.md`, digest-frozen with its tree.

## What moved

plugin-ui 0.1.1 → 0.2.0 (MINOR: a tightening — packages with unreferenced
preset assets, valid under 0.1.1, are refused; the batch also carries the
additive lane-1 errata, and a batch's bump follows its highest change class).
Bump mechanics per `standards/GOVERNANCE.md`: copy-never-move, new corpus rows
cite `standards/plugin-ui/0.1.1/<file>` as `source`, digests moved only by
`benchweave.standards repin` (4 rows re-pinned), 0.1.1 tree untouched. Schema
shapes are unchanged — only `$id` roots, `contract_version` consts and titles
moved (verified: byte-diff against 0.1.1 shows version strings only). The
behavior rides the validator (`src/benchweave/presentation/contracts.py`,
vendored byte-for-byte) plus SDK CLI surface.

Two gaps closed (issue #62):

- **Lane-1 descriptor envelopes.** `validate_preset` gains keyword-only
  `action_id`: an explicit id wins (one absent from the descriptor is refused
  as `unresolved_reference` on `preset.action`, never silently skipped); the
  default resolves the action from the preset's settings-schema identity via
  the exported `resolve_preset_action` — exact, not heuristic, because lane 2
  requires the settings-schema `$id` to equal the bound action's corpus
  input-schema `$id` (`identity_mismatch` otherwise), so every preset that
  could pass lane 2 resolves to its own action, and corpus input-schema
  `$id`s are urn-per-action. The shared `_preset_envelope_findings` applies,
  AND-wise and with code `invalid_settings`, the canonical corpus action
  input schema and the descriptor action's `input_constraints`; lane 2's
  former inline copy of those checks is deleted in favor of the shared
  helper. A custom-`$id` settings schema applies no envelope by design (no
  action inference) — the check-preset success message prints the loud
  negative (`no descriptor envelope applied … pass --action to force one`),
  and `--action` forces a named envelope. `benchweave_sdk.presentation`
  exports `resolve_preset_action` (the same resolver the enforcement uses, so
  the CLI note cannot disagree with what was applied).
- **Unreferenced / declared-unlisted presets.** `validate_presentation`
  validates every preset a configuration target declares (the author wired it
  by declaring it; binding exposure is a UI choice; a preset two bindings
  list is validated once — finding de-duplication on multi-binding packages),
  and refuses a preset-shaped asset no target declares with the new
  `unreferenced_preset` finding rather than guessing its wiring. The probe is
  bounded: assets are already read and digested, `parse_document` caps at
  256 KiB, and only documents carrying `contract_version` plus `settings`
  and `settings_schema` count as preset-shaped. The binding loop keeps only
  membership and kind checks (a binding naming a preset the target does not
  declare still yields `unresolved_reference`, existing path).

Honest residual (stated up front in the design §0): lane 1 still applies no
descriptor envelope for plugins whose authored settings schema deliberately
carries a non-corpus `$id` — for those the default invocation degrades loudly
and full envelope coverage remains lane 2's job (or the explicit flag).

sim_scope re-versions to 0.2.0 (`ui/manifest.json`, `presentation.json`,
`binding-catalogue.json`, both presets; settings-schema bytes unchanged —
OTDP-side — so its digest pin is stable; descriptor untouched). Docs: the
device-developer guide's lane text re-scoped (both lanes enforce the
envelope; identity resolution; the orphan rule), the sim_scope README's
authored-envelopes paragraph moved to both-lane enforcement, the project
index and the compatibility matrix follow the version. The SDK repo (branch
`feat/issue62-plugin-ui-020`, commits `f923179` + `67dcb69`) vendors the
tree single-active-version, adds `--action` + the notes, loads plugin-ui at
0.2.0, and keeps `benchweave-sdk`'s own version at 0.0.2 (the behavior rides
the next release train; precedent `f5e05fa`).

## RED (pre-implementation, commit `d6b171f`; submodule at the pre-change pointer)

All lane behavior tests main-side, per design §5. **35 collected / 11 failed /
0 errors** (junitxml):

- the six `should_refuse=True` census rows (`range_v` 25.0 / 0.0005 / 10.001 /
  0.0009, `offset_v` 100.0 / −10.001) each fail `assert lane1_exit != 0` —
  lane 1 exited 0 on all six;
- `test_l2_descriptor_constraints_tighter_than_corpus_still_refuse` — the
  added narrowed-descriptor lane-1 assertion fails (`assert 0 != 0`);
- `test_l1_default_resolves_action_by_schema_identity` — `assert 0 != 0`;
- `test_l1_explicit_action_flag_forces_envelope` —
  `TypeError: validate_preset() got an unexpected keyword argument
  'action_id'`;
- `test_l2e_unreferenced_preset_asset_refused` — `assert 0 != 0` (check-ui
  exited 0 on the envelope-violating orphan);
- `test_l2f_target_declared_unlisted_preset_validated` — `assert 0 != 0` (the
  violating declared-unlisted preset was never validated).

The optionality control
(`test_l1_custom_settings_schema_applies_no_envelope_loudly`) is green in
both worlds by design — it pins the no-over-tightening requirement (design
metric C); no RED exists for it by construction and none was faked.

## GREEN

- Census + lanes (`tests/sdk/test_sim_scope_presets.py`): **35/0** at the
  synced submodule. Metric A: 6/6 True rows refuse; 3/3 endpoint False rows
  (`range_v` 10.0 / 0.001, `offset_v` −10.0) and 2/2 shipped presets still
  exit 0. Metric B: the envelope-violating orphan refuses with
  `unreferenced_preset` and WITHOUT `invalid_settings` (refused, not
  settings-validated); the unmodified package and the valid extra
  target-declared unlisted preset (metric B2) both exit 0. Metric C: the
  custom-`$id` row exits 0 with no envelope finding, before and after.
- Unit presentation + architecture suites: **67/0**.
- `tests/standards` + `tests/contract/test_baseline.py`: green after the
  matrix regeneration and the SDK sync (the pre-sync run's `test_real_tree_is_clean`
  `sdk_version_mismatch` and the two stale-matrix failures were the expected
  mid-sequence window, matching the OTDP 0.2.0 train's disclosed shape).
- Full cold suite: **1290 collected / 1 failed** — the single failure is
  `test_submodule_head_matches_the_recorded_gitlink`, which compares the
  submodule HEAD against the COMMITTED gitlink and therefore closes exactly
  when the pointer commit lands (this commit's successor), the same closure
  the 0.1.1 and OTDP 0.2.0 trains recorded.

## Gates

`uv run ruff check .` clean; bare config-driven `uv run mypy` clean (177
source files, includes `packages/sdk/src`); `make check-sdk-standards` clean
(sync check + `matrix --check` at the advanced pointer);
`benchweave.standards versions`: standard `plugin-ui@0.2.0` = sdk lock
`plugin-ui@0.2.0`. Falsifier sweep (design §4): no live `plugin-ui/0.1.1`
path or `0.1.1` contract literal remains outside the frozen trees, the
frozen corpus rows, and the design records; the SDK repo's one live deep
link was swept with `67dcb69`. SDK repo: ruff clean, strict mypy clean,
pytest **10/0**, `sync-standards --check` agrees. Fixture-key note: the
registry suites need the gitignored signing keys
(`fixtures/registry/keys/*.pem`) copied into a worktree; without them 8
registry tests fail environmentally (verified the same tests pass in the
maintainer's main checkout at the base commit `cc501b2`).
