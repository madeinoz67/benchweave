# Issue #541 slice 2, standards leg: the composed-action-class schema and the 0.4.0 family bump

Status: designed 2026-10-22 in `.wt/std541-k2r9` (branch
`feat/issue541-s2-standards`, base `origin/main` `e2ffa82a`; SDK submodule
at the pin `3fa10c7`, benchweave-sdk 0.18.0, whose lock already serves this
family's 0.3.0 as active — the G-5 sync-completion precondition for the
bump). Parent program record:
`.claude/deep-review/2026-10-22-issue541-classref-composition.md` (§3 layer
2, §12 fork F2). Owner authorization 2026-10-22 ("land all slices"); F2's
recommendation adopted — the schema is a sibling file inside the
`plugin-ui-class-reference` family, and vendor-to-corpus promotion stays a
file move inside one family.

Triage check (`.claude/deep-review/README.md`): public. Invented names only;
the motivating real-world evidence is cited by issue reference, per
CLAUDE.md §4.

**This is a design pass.** The drafted artifacts sit uncommitted in the
worktree (paths in §2); the build leg lands them. Slice 1 was in flight
(`feat/issue541-s1-residual`, 4 commits at design time) and its fold may
still move; §7 is the robustness contract against that.

## 1. The mechanism, in one paragraph

A composed action class is a vendor-authored, versioned JSON document
validated by a new sibling schema in the family's 0.4.0 copy. It claims
action URNs explicitly, carries their `input_schema`, and states one
`side_effect` from a closed three-value set derived from what the gate's
forbid arms actually check. It rides the existing
`descriptor.contracts[]` path+sha256 pin seam (the proven vendor-catalog
mechanism, both resolvers), plays the catalogue side of the D13 narrowing
intersection unchanged, and asserts nothing presentational — the ladder
still derives every control. Its `contract_version` is a dialect version
(`0.1.0`) decoupled from the family directory version so pinned, digest-
verified vendor bytes survive family bumps. The family bumps 0.3.0 → 0.4.0
under copy-never-move: ten re-stamped machine files plus the new schema,
eleven new corpus rows, the 0.3.0 tree and its rows frozen in place.

## 2. What is drafted, where

All paths repo-relative under `.wt/std541-k2r9/` (uncommitted;
`git diff --numstat` = `55 0 corpus-manifest.json`,
`1 1 cross-constraints.json`, `18 14 standards-manifest.json`, plus the
untracked 0.4.0 tree):

- `standards/plugin-ui-class-reference/0.4.0/` — the 11-file copy: two
  family schemas and eight class files re-stamped (version strings only,
  verified line-by-line: each class file differs on exactly the
  `contract_version` line; the schemas on exactly their four/three
  version-bearing lines), the README extended (§5), and the new
  `composed-action-class.schema.json`.
- `standards/corpus-manifest.json` — 11 rows appended after the family
  block (§4).
- `standards/standards-manifest.json` — the family entry moves to 0.4.0
  (`supersedes 0.3.0`, `released 2026-10-22` — the build leg re-dates to the
  landing day if it differs), `normative` now names eleven 0.4.0 paths,
  `dependency_policy` range `>=0.1.0,<0.4.0` → `>=0.1.0,<0.5.0` with the
  0.4.0 migration note.
- `standards/cross-constraints.json` — one new row for 0.4.0, evidence
  citing this record; predecessor rows untouched.

Draft-time mechanical evidence (the sanctioned tools, real runs, true exit
codes): `benchweave.standards repin` → `corpus manifest already current`,
exit 0 (coverage both directions and every digest agree, including the new
rows — the draft's digests were computed with the same algorithm and repin
rewrote nothing); `pytest tests/contract/test_baseline.py` → 19 passed,
exit 0 (the copy-never-move/source-lineage/obsolete-version guards accept
the tree); `benchweave.standards check` → exit 1 with 15 findings — the 12
naming the SDK vendored tree lacking 0.4.0 (`missing_asset` ×11,
`stale_generated` ×1) plus three naming the SDK lock itself
(`served_set_drift`, `sdk_version_mismatch`, `policy_mirror_drift`, each
carrying `run make sync-sdk-standards`). All 15 are SDK-side findings in the
#408 order, disclosed here as the build sequence, not a defect.

*Correction, governance review 2026-10-22:* this paragraph originally
reported 12 findings "all naming the SDK vendored tree". The count was
measured wrong at draft time and the scope overstated — the three
lock-facing findings are a distinct surface. Re-measured independently:
exit 1, 15 failures, the code census above.

## 3. The schema, and why every closed set is what it is

```json
{
  "$id": "https://benchweave.dev/contracts/plugin-ui-class-reference/0.4.0/composed-action-class.schema.json",
  "title": "BenchWeave plugin-ui-class-reference composed action class 0.1.0",
  "type": "object",
  "additionalProperties": false,
  "required": ["contract_version", "urn", "title", "claims", "input_schema", "side_effect"],
  "properties": {
    "contract_version": { "const": "0.1.0" },
    "urn":       { "$ref": "#/$defs/class_urn" },
    "title":     { "$ref": "#/$defs/title" },
    "claims": {
      "type": "array", "minItems": 1, "maxItems": 64, "uniqueItems": true,
      "items": { "$ref": ".../0.4.0/class-reference.schema.json#/$defs/action_urn" }
    },
    "input_schema": { "type": "object" },
    "side_effect":  { "$ref": "#/$defs/side_effect" }
  },
  "$defs": {
    "class_urn":   { "type": "string", "minLength": 1, "maxLength": 256,
                     "pattern": "^otdp\\.action\\.[a-z_][a-z0-9_]*/[0-9]+\\.[0-9]+\\.[0-9]+$" },
    "title":       { "type": "string", "minLength": 1, "maxLength": 256 },
    "side_effect": { "enum": ["none", "state_change", "energy_removing"] }
  }
}
```

Each decision, with its derivation:

- **`side_effect ∈ {none, state_change, energy_removing}` — derived, not
  invented.** OTDP already owns this axis: the served catalog's action rows
  carry `side_effect` (`otdp.dc_psu.output/1.0.0` is `state_change`,
  `measure` is `none`), and `otdp-device-descriptor.schema.json`'s action
  map declares the same two-value enum per descriptor action. The first two
  values are that vocabulary verbatim. `energy_removing` is the one
  addition, and it exists because the parent record's named consumers — the
  gate's `confirm-wrapped-run-action` census ban
  (`classref_gate.py:630-635`), `intermediated-energy-removing-action`
  (`_forbid_findings:298-354`, keying today on the abort *slug*), and the
  D7 carve-outs (`_not_d7:182`, `validate_declaration_vocabulary:1894-1900`)
  — draw exactly one distinction: energy-removing versus everything else,
  today by name-derivation guess. The declared value is the explicit
  evidence that replaces the guess: a class claiming
  `side_effect: "energy_removing"` puts its actions into the D7 set
  (never confirmed, never intermediated, never downgradable) by declaration.
  Against the descriptor's own per-action declaration the class value obeys
  the S20 direction (otdp-specification.md §4/S20: over-classification at
  the verb is legal, under-classification refused), applied at the class
  layer: `energy_removing`/`state_change` over a descriptor row saying
  `state_change`, `none`-or-absent is legal; `none` under a descriptor row
  saying `state_change` refuses (`classref_composed_side_effect_under`).
  The parent record §3's example literal `"configuration_write"` is
  **superseded by this set** — a configuration write IS a `state_change`,
  and forking a classref-private effect vocabulary would fork an axis the
  descriptor already owns. No value ships without a consumer:
  `energy_admitting` (the §C.1 engage direction) is deliberately absent —
  no gate arm consumes it (the load-class README assigns §C.1 renderer
  enforcement to the safety-behaviours slice) — and the 0.4.0 README
  carries the standing rule that a widening must ship its consuming arm in
  the same change.
- **`claims` — explicit, many-per-class, closed shape.** Entries are action
  URNs validated by `$ref` to the family schema's existing
  `$defs.action_urn` (one authority for the pattern — the same cross-file
  `$ref` style the family schema already uses for layout).
  `minItems: 1` (a class claiming nothing is meaningless), `maxItems: 64`
  (the family's slots ceiling; the largest corpus profile declares 6
  actions), `uniqueItems: true`. A claim naming an URN a served catalog row
  already describes, an URN another composed class claims, or a second
  pinned document carrying one class urn refuses
  `classref_composed_claim_conflict` (parent §8: refuse, never merge — sort
  order never picks a winner). A claim naming an URN the descriptor does
  not declare is not a refusal: a corpus-promoted class legitimately
  claims URNs across many plugins; it simply does not apply here.
- **`input_schema: {type: object}` — loose, on the OTDP precedent.** The
  served catalog's own schema (`device-profile-catalog.schema.json`)
  constrains an action's `input_schema` as `{type: object}` and nothing
  more: the closed field vocabulary lives in the consuming derivation
  (`_row_mode`, `_field_rows`, `_intersect_property`), not in the corpus
  schema. The composed schema mirrors that exactly, which is also the
  slice-1 robustness guarantee (§7): a fold widening the constraint
  vocabulary (say `minLength`/`maxLength`) changes no schema byte and
  invalidates no pinned document.
- **`contract_version: const "0.1.0"` — a dialect version, deliberately
  decoupled from the family directory version.** A composed class is
  pinned by digest in `descriptor.contracts[]`; if its version rode the
  family version, every family bump — and this family bumps often (L13
  through L17 all rode one 0.3.0 window) — would invalidate every pinned
  vendor document in every plugin. The exact precedent is the descriptor
  itself: a descriptor pins its own `otdp_version` independent of the
  corpus's active version, and multi-version serving exists precisely
  because pins must survive active-version motion (R-2). Serving exactness
  is preserved: the active family's schema validates dialect 0.1.0
  documents exactly, and a dialect bump is a standards motion of its own
  (DS1).
- **`urn` pattern `^otdp\.action\.[a-z_][a-z0-9_]*/…`** — the parent
  record's shape. The middle segment `action` is reserved (no served
  profile carries that namespace — verified against the 0.2.3 catalog's
  profile list); uniqueness of the class name is by convention (a vendor
  prefixes its namespace), and corpus promotion refuses a class urn a
  served class already carries (DS4 lands that guard with the first real
  promotion; nothing to check until one exists).
- **No component key — the owner's phrase resolved, and I affirm it.** The
  ladder owns the component mapping: `_row_mode` (`classref.py:480-496`)
  turns a schema fragment into numeric/text/enum/const/boolean rows and
  `_ladder_level` (`:557-581`) turns the effective required set into
  L1/L2/L3 reachability. A declaration asserting "render this as a button"
  for an action with required numeric inputs would either duplicate that
  mapping (drift) or override it (silently drop the fields). The
  declaration supplies `input_schema` and nothing presentational;
  `additionalProperties: false` refuses a `component` field outright. The
  existing deviation vocabulary (`expect.controls` intended-vs-derived,
  `_derive_controls:617-625`) is already the honest channel for "I wanted a
  different control than the ladder derived".
- **`title` required (1..256)** — the family's `$defs.title` shape; the
  document names itself for ledger and report surfaces. `description`,
  `output_schema`, `lifecycle` are refused (absent from properties): no
  derivation or gate arm consumes them on this document (DS6; the OTDP
  catalog requires them on *its* action rows, which are a different
  document kind with different consumers).

## 4. The bump plan, counted

- **Copied:** all eleven 0.3.0 files → 0.4.0. Ten machine files re-stamp
  (eight class files: the `contract_version` line only, the L5 shape;
  `class-reference.schema.json`: `$id`, title, `contract_version` const,
  the layout `$ref` — its four version-bearing lines; `layout.schema.json`:
  its three). README.md re-titled and extended (§5). Verified by
  line-by-line diff at draft time: zero non-version changes.
- **New rows: 11.** Ten re-stamps citing
  `standards/plugin-ui-class-reference/0.3.0/<file>` as `source`, plus
  `composed-action-class.schema.json` citing its authoring staging path
  `docs/plugin-ui-class-reference-v3/composed-action-class.schema.json`
  (removed in the same PR — the founding convention; `source` is
  provenance, never required to resolve on disk). The family's rows go
  **16 → 27**; the manifest total 298 → 309. README.md is not a row (zero
  README rows exist in the entire manifest — prose is not digest-pinned,
  GOVERNANCE's own change-class table).
- **Correction to the brief:** the family carries **16** rows across
  0.1.0–0.3.0, not 32 (mechanism: `corpus-manifest.json` `files[]`
  filtered on the `plugin-ui-class-reference/` path prefix, counted
  2026-10-22; 3 + 3 + 10 per version directory).
- **What must NOT move:** the 0.1.0–0.3.0 trees and all 16 of their rows
  (digest-frozen; `repin` verified them unchanged at draft time — the
  corpus-manifest diff is +55/−0), the predecessor cross-constraints rows
  (rows name released versions and accrete, never move — G-4), the corpus
  manifest's `identity` block, `sdk_compatibility`, and every other
  family's bytes.
- **Cross-constraints:** one NEW row for 0.4.0 (`plugin-ui
  >=0.4.0,<0.5.0`, floor unchanged — the composed schema consumes no
  plugin-ui vocabulary beyond 0.3.0's; evidence cites this record §3/§4).
  The 0.2.0 and 0.3.0 rows stay verbatim.
- **No validation-report regeneration:** the machine-written-report rule
  covers otdp, registry, execution, interface — this family has no report
  file (verified: no `validation-report.md` in any family directory).

## 5. The README section the 0.4.0 copy gains

The 0.4.0 README (drafted in-tree) adds: the from-predecessor note above; a
normative section **"Composed action classes (normative, gateway issue
#541)"** — the document shape, the claims rules and conflict refusal, the
no-component-key rule, the closed `side_effect` set with the S20 direction
rule and the D7 extension, the two-sources-one-resolver pin-seam text, the
dialect-version decoupling, and the ledger/`migrate-ui` contract — plus the
Files-table row. Engineering register throughout (corpus prose companions
keep it, like every family README before this one). The section's closing
line is the standing obligation the brief asked for: *if the closed
`side_effect` set widens, the bump carries the consuming gate arm and the
SDK cross-check in the same change, and its cross-constraints row re-cites
the evidence — a value with no consumer is not admissible.*

## 6. The consumption contract (for the SDK and gateway build legs)

- **Discovery (SDK):** `_vendor_catalogs` (`packages/sdk/src/benchweave_sdk/
  classref.py:206-234`) already walks every non-`urn:otdp:`
  `descriptor.contracts[]` row, digest-verifies the pinned bytes and reads
  `document["actions"]`. The extension: the same walk discriminates by
  document shape — a document carrying `urn` matching the class pattern
  plus `claims` is a composed class, validated against the vendored
  `composed-action-class.schema.json` (the family triple — reference,
  layout, composed — loaded through one registry, the `_family_schemas`
  seam gaining its third document); failure refuses
  `classref_invalid_composed_class` (mirroring `classref_invalid_reference`).
  A document carrying BOTH `actions` and `urn`/`claims` refuses the same
  code (ambiguous pin); a document carrying neither is unchanged behavior
  (today's silently-empty vendor catalog) — tightening that is out of this
  slice's licence and named nowhere else, so it stays as-is, disclosed.
- **Discovery (gateway):** `_vendor_catalog_documents`
  (`src/benchweave/presentation/classref.py:1100-1130`) — the same
  discrimination from admission bytes by digest, the same two refusal
  codes, byte-for-byte mirror discipline. This mirror leg is DS5, the
  parent record's named follow-on; the standards leg's job was to fix the
  ONE contract both consume, which is the schema.
- **Resolution:** claimed URNs join the derivation's catalogue side with
  `resolution: "composed"` and the class urn on the plan row; D13 runs
  unchanged (descriptor `input_constraints` still narrow the class
  `input_schema`; `classref_effective_schema_empty` unchanged); the ladder,
  field rows, the device-features page arm and slice 1's custom-section
  machinery all run unchanged. A named class-reference slot MAY bind a
  composed-claimed URN (the slot says where, the class says what) — not a
  conflict; the arm lands with slice 3's fixture (DS3).
- **Conflicts refuse, never merge (§8):** `classref_composed_claim_conflict`
  for claim-vs-catalog-row, claim-vs-other-class, and same-class-urn-twice
  (the detail string names which and both sides); `classref_composed_side_effect_under`
  for under-classification against the descriptor's own declaration.
- **side_effect feeding the arms (SDK leg):** the plan row carries the
  class's `side_effect`; the D7 set becomes {abort-slug actions} ∪ {actions
  whose class declares `energy_removing`}, consumed by `_forbid_findings`'
  intermediated arm, the census confirm ban, `_not_d7`, and
  `validate_declaration_vocabulary` — no refusal code changes, the
  protected set widens by declaration.

## 7. Robustness against slice 1's fold

The fold may change the plan row's `resolution` shape and may widen the
closed constraint vocabulary (`minLength`/`maxLength`). Neither can
invalidate this schema: the schema pins no `resolution` value (the README
mentions `resolution: "composed"` once in prose — a fold renaming the
vocabulary moves that one prose line in the same PR, a docs-only edit), and
`input_schema` is deliberately loose on the OTDP catalog precedent, so no
constraint-keyword widening touches a schema byte or a pinned document. The
ledger's composed rows (below) name class urns, which the fold does not
touch. Verified against slice 1's head (`feat/issue541-s1-residual` @
`55b5cbe`): its `resolution` values are `catalog`/`custom`, its
`_CONSTRAINT_*` sets unchanged from 0.18.0 — both as the parent record
predicted, neither load-bearing here.

## 8. What `migrate-ui` gains and refuses (SDK leg contract)

`migrate_ui` (`packages/sdk/src/benchweave_sdk/presentation.py:574`)
re-stamps bytes in place, validates before writing, and never writes
versions down. Slice 2 extends it:

1. **The ledger joins the re-stamp set.** When `ui/class-reference.json`
   exists, its family stamps (`contract_version`, `reference_version`)
   re-stamp to the target family version byte-in-place — retiring the D2
   detection-only posture for exactly those two stamps (the detection note
   at `presentation.py:780-787` is replaced for them; re-derivation stays
   the sanctioned path for all content).
2. **The ledger's composed rows** (slice 2 adds them beside slice 1's
   `custom_actions` rows, same no-standards-motion posture slice 1
   established): `composed_actions: [{action, resolution: "composed",
   class}]` mirroring the custom rows' shape, and `composed_classes:
   [{class, validated_against}]` — the class urns consumed and the family
   version each was validated against.
3. **What re-stamps:** the two family stamps, and each
   `composed_classes[].validated_against` — the latter ONLY after
   re-resolving that class's pinned document (path + sha256 from the
   descriptor's `contracts[]`) and validating it under the TARGET
   family's vendored composed schema. This is the owner's "action classes
   ride migrate-ui": the validation stamp moves with the family, verified
   against the pinned bytes, exactly the manifest re-stamp +
   validate-before-write discipline.
4. **What refuses, never silently upgrades:** `migrate_ui_composed_unresolved:`
   (pin missing from the package, digest moved, pinned urn ≠ the ledger's
   recorded urn, or schema-invalid under the target) — a class urn's own
   version is content and is never re-stamped; a vendor cutting
   `numeric_staging/1.2.0` re-pins and re-derives, migrate-ui only refuses.
   `migrate_ui_ledger_drift:` — the ledger's inventories must match set
   arithmetic over the current descriptor and pins (custom = declared −
   (catalog ∪ composed-claimed); composed = composed-claimed ∩ declared);
   a mismatch means the project drifted and needs `derive-ui`, not a
   version write.

## 9. Invariant and drift impacts

- **No CTL/STO/CON/REG invariant changes** (the parent record §9 holds;
  this leg is corpus + schema). CON-10's one-dialect discipline is
  *strengthened*: the effect axis stays the descriptor's, the class only
  refines it. The compatibility matrix (CON-12's render) moves by its own
  mechanism (`matrix --check` + regen at build; the entry flips to 0.4.0
  from the manifest). The SDK mirror obligation gains the composed
  discrimination arm on both `_vendor_catalogs` and
  `_vendor_catalog_documents` — the equivalence census extends when DS5
  lands.
- **Version-surface census (collected 2026-10-22, `git grep
  plugin-ui-class-reference/0.3.0`, the operational pre-train rule).**
  Frozen history (never move): nine `.claude/deep-review/` records.
  Generated (move by mechanism): `docs/compatibility-matrix.md` (manifest
  render). **In-arc sweep set, thirteen files**: eleven test files
  (`tests/ui_html/test_classref_{daq,dc_psu,dmm,electronic_load,
  function_generator,oscilloscope,page,smu}.py`,
  `tests/architecture/test_plugin_ui_class_reference_contracts.py`,
  `tests/presentation/test_classref_derive.py`,
  `tests/interfaces_ui/test_ui_presentation.py`),
  `packages/ui-html/src/benchweave_ui_html/classref.py` (docstring
  citations), and `docs/internal/ui-styleguide.md` (prose citing the
  founding reference's path — its drift guard re-derives from corpus files;
  the 0.4.0 copies are byte-identical today, so the sweep moves the paths
  to the active family with zero behavioral delta). All literals naming the
  old family version move in the bump's own PR — GOVERNANCE's in-arc rule.

  *Correction, build leg 2026-10-22:* the census above is **incomplete and the
  method that produced it is wrong**. It was taken with
  `git grep plugin-ui-class-reference/0.3.0` — a path-shaped search, which by
  construction cannot see a bare `"0.3.0"` value. The sweep therefore missed
  **thirteen in-arc files**, and two of the misses are behavioural rather than
  cosmetic: `src/benchweave/presentation/classref.py::FOUNDING_FAMILY_VERSION`
  and `src/benchweave/presentation/panels.py::corpus_pin`, whose staleness made
  the registered class panel render its "unavailable until the panel and the
  corpus move together" banner instead of its composition. Also missed: the two
  `REGISTER` rows in `scripts/standards/count_version_literals.py` (moving the
  constant without them leaves the zero-literal gate passing on stale values),
  five `tests/presentation/classref_fixtures/fixture-*.json` layout
  `contract_version` stamps with their five paired envelopes' derived manifest
  digests, and one assertion in `tests/interfaces_ui/test_ui_presentation.py`
  that moves only with the pin. Measured before the widened sweep: 345
  collected, 21 failed; with the original thirteen-file set, 345 / 2. The
  precedent for the true set is `fa9cfc63`, the 0.2.0→0.3.0 bump, which moved
  exactly these surfaces in the same arc. **The correct census for the next
  bump is a bare-version scan over source and fixtures, not a path grep** —
  `count_version_literals`' own register is the mechanism to extend.

  *Second correction, same build leg, after the full battery:* the widened
  sweep itself was truncated by a `head`, so its "complete" set was also
  wrong. A **fourteenth** literal surfaced only when the battery ran:
  `tests/interfaces_ui/test_ui_readings.py:426`, the layout block's
  `"contract_version": "0.3.0"`, which made the readings page refuse
  `classref_layout_invalid` across twelve tests. The census has now been
  wrong about its own completeness **twice**, the second time after being
  deliberately widened. The rule is therefore not "use a better scan" but:
  **completeness of a version-literal census is proved by a full battery,
  never by the scan appearing exhaustive.** Two further consequences came
  out of the same run and belong to this arc rather than to the SDK-order
  set: the `test_manifest` annotation guard must admit a schema's own
  `contract_version.const` (the dialect decoupling this leg introduced), and
  `test_matrix`'s retained-version seed and `test_train_window`'s bump entry
  move with the fourth family version. The only genuine
  SDK-order reds are the four `tests/standards/test_check.py` arms asserting
  `served_set_drift` and vendored-tree absence.
- **SDK leg (its own PRs, #408 order):** gateway standards PR (this leg +
  sweep) → SDK PR (composed resolution, schema validation, migrate-ui,
  `sync-standards` picking up the eleven 0.4.0 files into the lock and
  vendored tree, flipping active) → SDK release cut → gateway pointer PR
  (gitlink + `.gitmodules` pin in one commit). `make check-sdk-standards`
  on the pointer PR; the draft-time `check` exit 1 (12 sync findings) is
  this order made visible.
- **CI cost:** no new job, no browser, no network. The composition gate's
  pair set is unchanged (eight class files, twenty-eight pairs, identical
  bytes). New tests are unit-shaped: schema fixture arms, conflict arms,
  migrate-ui arms, and the two structural checks (§10 A4). The standards
  tripwires run in the existing full battery.

## 10. Pre-committed acceptance rule

Written before any build-leg number was looked at; the draft-time runs in
§2 are baseline, not the measurement.

**SHIPS if all six hold** (gate commands per CLAUDE.md §3, true exit codes,
`UV_PROJECT_ENVIRONMENT=venv`):

1. **A1 — the bump is mechanically clean.** `repin` exit 0; full battery
   green including both standards tripwires; the sixteen predecessor family
   rows byte-identical before/after (denominator: 16 rows, compared by
   row sha256, this comparison the assertion).
2. **A2 — the fixture lattice is exact.** Exactly 4 valid composed
   documents validate (the README example; a 64-claim boundary class; an
   `energy_removing` class; a class over a descriptor row with no declared
   side_effect) and exactly 6 invalid documents refuse with the named
   keyword (`side_effect` outside the set; duplicate claims; a claim not
   action-urn-shaped; a class urn outside the pattern; a missing required
   field; an additional unknown field). Counts asserted by equality, never
   "at least".
3. **A3 — RED on the closed set.** Neutralize the `side_effect` enum (a
   `cp` backup, admit one bogus value) → the invalid-side_effect arm goes
   RED; restore → GREEN. No mechanism, no effect.
4. **A4 — the decoupling is structural, not aspirational.** Over the
   vendored schema bytes: `"0.1.0"` occurs exactly twice — the title and
   the dialect `const`, both dialect-bearing and both structurally
   untouched by a family bump — and `"0.4.0"` occurs exactly twice, at
   `$id` and at the `claims.items.$ref`, both intra-family; plus a
   test-local future-bump simulation: copy the schema, re-stamp only its
   family-version-bearing bytes to a hypothetical 0.5.0, and the pinned
   example document still validates.

   *Correction, governance review 2026-10-22:* A4 was pre-committed as
   "`0.1.0` occurs exactly once (the dialect const) and `0.4.0` exactly
   twice (`$id`, title)". Measured on the drafted bytes, `0.1.0` occurs
   twice (title, const) and `0.4.0` occurs at `$id` and the `$ref` — the
   title carries the dialect version, not the family version. The property
   A4 protects is intact and in fact stronger than stated: a family
   re-stamp touches exactly two intra-family lines and never the dialect
   bytes that validate a pinned document. The counts and locations above
   are the corrected, runnable rule; correcting them here, before the A4
   run, is the point — an acceptance rule tuned after its measurement is
   not pre-committed.
5. **A5 — the conflicts refuse (SDK leg, shared with the parent's
   metrics).** Three conflict kinds and the under-classification case each
   refuse with their code (§6), each arm RED under its neutralization.
6. **A6 — migrate-ui refuses what it cannot resolve.** A ledger whose
   claimed class fails re-resolution under the target version refuses
   `migrate_ui_composed_unresolved` with nothing written; a drifted
   ledger refuses `migrate_ui_ledger_drift`; a clean ledger re-stamps
   exactly the four stamp kinds and no content byte (the diff is version
   strings only — the migrate-ui discipline, asserted).

**KILLS if any of:** (a) any 0.1.0–0.3.0 byte or corpus row changes;
(b) a valid fixture refuses or an invalid fixture passes; (c) landing the
schema requires a plugin-ui family bump (an unforeseen vocabulary
dependency — the floor claim in the cross-constraints row would be false);
(d) making the schema fold-robust requires admitting a document the gate
cannot honestly consume.

**UNDERPOWERED, not conclusive:** if A4's structural check is judged
insufficient to prove bump-immunity, the complete proof needs the SDK
serving two family schema copies — DS1 machinery that does not exist;
escalate to the owner rather than tune the check. Likewise if the full
battery's composition gate cannot run against the 0.4.0 active tree for
environmental reasons, that is a discovered host defect, never evidence
about the bump.

## 11. Tier statement and Step-1 keyword scan (#254)

**Tier 3.** First match: the diff touches `standards/` and adds a JSON
Schema file; it also (build legs) carries `sha256`/`migrate` diff text and
advances the `packages/sdk` submodule pointer. The standards-governor pass
is mandatory for any `standards/` touch; the Tier-3 adversary pass runs
two independent lanes (#181 R3) on the slice carrying the schema.

Keyword scan over this leg's WHOLE expected diff text — the three manifest
diffs, the twelve new 0.4.0 files, and this record itself (3,388 lines,
scanned 2026-10-22): `threading` 1, `asyncio` 1, `subprocess` 1,
`sha256` 20, `hashlib` 1, `migrate` 18, `recovery` 1, `protection` 3.
Every 1-count is this section's own enumeration of the eight-word set
(self-fire by construction — the rubric's intended interplay); the 20 and
18 are the mechanism's own vocabulary — `sha256` is the pin seam's name in
prose and the manifest's digest field, `migrate` names the `migrate-ui`
contract the README and §8 state. Excluding this record, the
standards-only counts are `sha256` 14 and `migrate` 2, all others 0. The
tier is 3 by path rules regardless; the build leg re-runs the scan over
the committed diff before review, and the review re-derives the tier
independently.

## 12. Deferrals

| id | deferred | home | reopen trigger |
|---|---|---|---|
| DS1 | Dialect-version serving — after a 0.1.0 → 0.2.0 dialect bump the SDK must serve both dialect schemas (the R-2 pattern for a new axis) | documentation here | the first composed-action-class dialect bump |
| DS2 | `energy_admitting` and the §C.1 directional presentation rule | documentation here; the safety-behaviours slice owns the arms | a gate arm that consumes the engage direction |
| DS3 | The reference-slot-binds-composed-URN arm (admitted by design, untested) | documentation here | slice 3's acceptance fixture exercises it |
| DS4 | The corpus promotion guard (duplicate class urn) and the promotion README procedure | documentation here | the first composed class promoted to the corpus |
| DS5 | The gateway mirror leg (`_vendor_catalog_documents` discrimination, `derive_attachment` composed resolution, equivalence census arm) | the parent record §9's named follow-on | the SDK leg's mirror PR |
| DS6 | `output_schema`/`lifecycle`/`description` on composed documents | documentation here | a consumer arm that reads them |

## 13. Top risks, each with its falsifier

1. **The dialect decoupling is the wrong call** — a reviewer shows the
   family-version const (the `class-reference.schema.json` pattern) should
   apply, dialect decoupling being cleverness. Falsifier: name one plugin
   whose pinned composed class survives the L13–L17-style in-window family
   bumps under a family-stamped const — none can; every pin breaks on every
   class addition. The decoupling is the only shape compatible with
   copy-never-move plus digest pinning.
2. **`energy_removing` over-fires** — a vendor over-classifies and the D7
   arms make the UI unusable for an action that is not truly
   energy-removing. This is the S20 direction (over-classification legal)
   taken deliberately: the cost is conservative protection on a
   vendor-declared axis. Falsifier: a real plugin where protection on a
   claimed action renders the device unusable — that escalates to the
   safety-behaviours slice, never a vocabulary silent-fix.
3. **The cross-file `claims.$ref` makes validation heavy** (three-resource
   registry). Falsifier: the SDK leg's validator wiring; if it bites,
   inlining the `action_urn` pattern is a one-line schema change at build
   time with zero document impact — decided then, not now.
4. **The census missed a version surface** — a red lane at landing names
   it. Falsifier: the full battery + `matrix --check` +
   `make check-sdk-standards` on the pointer PR; the census list in §9 is
   the map, and a missed surface is a finding against this record.
5. **The composed document and the vendor action catalog collide on shape**
   — a vendor ships a catalog that happens to carry `urn`/`claims` keys.
   Falsifier: the both-keys ambiguity refusal (§6); if real-world catalogs
   carry those keys, the discriminator gains a typed pin-id convention — a
   build-leg decision recorded in the SDK PR.

## 14. What the owner may still overrule

- The `energy_removing` token (vs `state_change.energy_removing` compound
  or an OTDP-side fourth value added to the descriptor enum itself — the
  latter would be an OTDP bump, a bigger motion than this slice's
  licence).
- The dialect starting at `0.1.0` (vs riding `0.4.0` from birth) — the
  parent record's example literal supports the former; the pinned-bytes
  argument in §3 is the deciding evidence either way.
