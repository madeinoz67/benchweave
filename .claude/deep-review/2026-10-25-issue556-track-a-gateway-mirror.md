# Track A — the gateway mirror resolves composed and residual actions (gateway issue #556)

Status: designed 2026-10-25 in `.wt/556-lane-a-m4t7` (branch
`feat/556-gateway-mirror`, base `origin/main` `99ecd774`; the `packages/sdk`
gitlink pins `benchweave-sdk` v0.21.0 `88dcc4d` — the release whose semantics
this record mirrors). Parent record:
`.claude/deep-review/2026-10-22-issue541-classref-composition.md` (row D9
fired its reopen trigger: the pointer advanced to the release that carries
slices 1–4). Owner directive for this track: **zero deferrals** — catalog,
composed and custom resolution land gateway-side, with the provenance and
disclosure surfaces, in this run.

Triage check (`.claude/deep-review/README.md`): public. Every fixture name is
invented (the Meridian M-400 / Veridian families already in tree); no bench,
client, operator or product identifier appears.

Reading note: every SDK line reference below is to `benchweave-sdk` at
`origin/main` `dc6e429` (the v0.21.0 lineage), read via
`git show origin/main:src/benchweave_sdk/classref.py` — the local SDK
checkout sits at 0.19.0 and is stale. Every gateway line reference is to the
worktree at base `99ecd774`.

## 1. The gap, located exactly

The SDK at v0.21.0 resolves an action in three layers (served/pinned catalog
row → composed action-class pin → residual derivation from the descriptor's
own `input_constraints`), marks every control-plan row with
`resolution: catalog|composed|custom`, mints a visible custom section, and
discloses ignored pins / unapplied classes / empty action pins / deferred
members through the gate's REPORTED channel. The gateway's mirror
(`src/benchweave/presentation/classref.py`, 1842 lines) predates all of that:

- `_vendor_catalog_documents` (`:1106-1136`) reads only
  `document["actions"]` — a composed action-class pin contributes nothing,
  and there is no shape discrimination, no conflict arms, no disclosures.
- `derive_attachment` (`:1709`) raises `classref_unknown_action` from three
  sites — `:1771` (descriptor declares an action absent from every served
  catalog — the recoverable knowledge gap the SDK now resolves),
  `:1797` (profile absent from the served profile catalog — a platform
  fault the SDK re-coded `classref_profile_absent`), `:1811` (a reference
  slot naming an unserved URN — the D4 corpus fault the SDK **keeps**).
- The integrity refusals at `:1125` (pin not admitted), `:1131` (digest
  mismatch) and `_catalog_document:1153` (profile catalog unserved) all wear
  `classref_unknown_action` — the pre-split conflation the SDK retired.
- `_effective_action_schema` (`:538`) requires a catalogue row; there is no
  residual mode. `_derive_controls` (`:707`) subscripts `catalog_actions[urn]`
  (`:727`); no `resolution` exists anywhere gateway-side.
- `_build_layout` (`:975`) mints no custom section; `_complete_authored_buttons`
  (`:947`) appends to `sections[-1]` (post-slice-1 that is the custom section
  in the SDK); `_insert_ladder_numerics` (`:922`) lacks the one-field-one-
  control dedupe (the SDK's W8) and runs BEFORE completion (the SDK's W1
  reversed the order) — see §5.
- `_assemble_documents` subscripts `catalog_actions[urn]` at `:1492`
  (configuration settings schema) and `:1538` (procedure `input_schema_id`)
  — a custom action under a configuration or procedure slot is a KeyError
  (500) today; the SDK tolerates the `None` row (`classref.py:1929`,
  `:2004` at origin/main).

**Consequence (issue #556's own words, verified):** a plugin derives and
previews with the SDK, but does not run on a bench here with the composed
presentation the SDK produced — the gateway's L4 no-manifest fallback
(`interfaces/ui_presentation.py::_classref_fallback:693`) renders the typed
refusal instead.

## 2. Precedent — nothing here is new architecture

This is the fourth classref mirror leg and follows
`.claude/deep-review/2026-10-21-classref-plot-kind-mirror-design.md` exactly:
read the widened SDK expander at the pin, mirror the functions in the same
arc, pin byte-parity through the committed B8 fixtures regenerated from the
pinned expander (the convention's oracle, that record §5.2), refuse typed
where the SDK refuses. The vendor-catalog pin seam itself
(`_vendor_catalog_documents` resolving descriptor pins from admission bytes —
"the admission store is the gateway's equivalent", the existing docstring) is
the proven mechanism the composed source rides, per parent record §2. The
disclosure surface extends the existing host-derived disclosure block
(`ui_templates/device.j2:20-22`, pinned by
`tests/interfaces_ui/test_ui_presentation.py::test_derived_pages_render_the_host_derived_marker`).

The one precedent that does NOT fit, rejected on the mirror doctrine: letting
the gateway invent its own refusal codes or its own disclosure vocabulary.
Every code and every disclosure line format below is the SDK's, or the SDK's
adapted only in the detail sentence that names the resolution source.

## 3. The mechanism

### 3.1 The refusal split (first motion, own commit)

Mirrors SDK `_vendor_documents` (`:347-583` at origin/main) and
`_catalog_documents:228` / `_profile_row:1452`. Gateway sites, current →
target:

| Gateway site | Condition | Class | Old code | Target code |
|---|---|---|---|---|
| `:1123` `_vendor_catalog_documents` | pin not in the admission store | platform/project fault | `classref_unknown_action` | `classref_vendor_catalog_unreadable` |
| `:1129` | pinned bytes fail the digest | integrity fault | `classref_unknown_action` | `classref_vendor_catalog_digest_mismatch` |
| new | pin parses to a non-object | platform fault | (crash) | `classref_vendor_catalog_invalid` |
| new | pin's `actions` is not an object | platform fault | (crash) | `classref_vendor_catalog_invalid` |
| `_catalog_document:1153` | profile catalog unserved | platform fault | `classref_unknown_action` | `classref_profile_catalog_unserved` |
| `derive_attachment:1797` | profile absent from the served catalog | platform fault | `classref_unknown_action` | `classref_profile_absent` |
| `derive_attachment:1771` | declared action absent from every catalog | **knowledge gap — resolves** | `classref_unknown_action` | **removed** (§3.3) |
| `derive_attachment:1811` | reference slot names an unserved URN | corpus fault (D4) | `classref_unknown_action` | **kept, unchanged** |
| new (composed walk) | schema-invalid composed doc; ambiguous pin (`actions` AND (`urn` OR `claims`)) | authoring fault | — | `classref_invalid_composed_class` |
| new | claim vs served row / vs pinned row / vs another class; class URN in two pins | authoring fault | — | `classref_composed_claim_conflict` |
| new | class `side_effect: none` under a descriptor action `state_change` | authoring fault (S20) | — | `classref_composed_side_effect_under` |
| new (`_catalogue_row`) | catalog row present but not an object | platform fault | (crash) | `classref_catalog_row_invalid` |
| new (`_field_rows`) | qualified field-name collision | authoring fault | — | `classref_duplicate_field` |

The gateway-specific "not admitted" arm keeps its own detail sentence
("pinned vendor catalog {path} is not admitted (digest {pin})") under the
SDK's `classref_vendor_catalog_unreadable` code — the admission store is the
gateway's equivalent of the SDK's unreadable file, and one code vocabulary
across both derivations is what CON-12's mirror discipline wants. This is a
disclosed divergence of detail, not of code: recorded in the module
docstring beside the existing `_resolve_parameters` divergence note.

Also in this commit: `_check_slot_conflicts` moves from `:1814` (last) to
immediately after reference resolution — the SDK's position
(`classref.py:1377` at origin/main) — so a multi-fault descriptor raises the
same code both sides. Observable only on multi-fault inputs; both orders
refuse.

### 3.2 The vendor-documents walk (composed + discrimination)

`_vendor_catalog_documents` becomes the mirror of SDK `_vendor_documents`,
same resolution source as today (the `vendor_catalogs` map, digest-keyed):

1. Walk `descriptor.contracts[]`, skip `urn:otdp:` ids; resolve each pin from
   the map; integrity arms first (§3.1) — bytes verify whatever shape they
   carry.
2. Discriminate by shape: `urn` AND `claims` (conjunctive) → composed class,
   validated against the **corpus** `composed-action-class.schema.json`
   (already vendored and manifest-pinned at
   `standards/plugin-ui-class-reference/0.4.0/` — verified in the corpus
   manifest at `64e0ae95c8a6…`; **zero standards bytes move**); the
   validation registers the family reference schema at its `$id` in the
   registry (claims `$ref` it) — mirror of SDK `_validate_composed_class:259`.
   `actions` AND (`urn` OR `claims`) → ambiguous, refuses
   `classref_invalid_composed_class` naming the carried keys. Neither shape
   and no `actions` key → ignored pin (disclosed). `actions` non-object →
   typed refusal. `actions` empty → empty pin (disclosed). A vendor-catalog
   action row carrying a stray `composed_class` key is stripped (the N2
   anti-laundering fold) — composed provenance has exactly one writer, the
   composed walk.
3. Conflict arms (refuse, never merge): a claim the served OTDP catalog
   describes; a claim a pinned catalog row describes; a claim another class
   holds; one class URN in two pins — all `classref_composed_claim_conflict`,
   each naming which side. Then `classref_composed_side_effect_under` (class
   `none` under descriptor `state_change`; over-classification stays legal).
4. Survivors' claimed URNs join the catalogue side as
   `{"input_schema": cls.input_schema, "side_effect": cls.side_effect,
   "composed_class": cls_urn}` — **including claims the descriptor does not
   declare** (DS3: a named reference slot may bind a composed-claimed URN;
   the `:1811` slot check runs against the merged map, exactly the SDK's
   order). D13 narrowing then runs on them unchanged.
5. Returns `(actions, classes, ignored_pins, unapplied_classes,
   empty_action_pins)` — the SDK's five-tuple, with `unapplied` as
   (class urn, pin path) pairs keyed to the APPLIED rule (a class applies
   when at least one claim names a declared action; a sanctioned
   claims-nowhere class discloses, never drifts).

`ComposedClass` mirrors the SDK dataclass (`urn`, `side_effect`,
`input_schema`, `claims`, `pin_path`). The SDK's public wrappers
(`validate_composed_class`, `composed_ledger_inventory`) exist for
migrate-ui — an authoring surface the gateway does not have; they are not
mirrored (CON-12 mirrors the derivation, not the SDK's CLI).

### 3.3 Residual (custom) resolution

Mirror of SDK `_effective_action_schema:1012` (catalogue row now
`dict | None`), `_check_residual_fragment:880`, `_check_value_types:822`,
`_intersect_declared_values:948`, `_catalogue_row:1234`, and
`_derive_controls:1255`:

- `_catalogue_row(urn, catalog_actions)`: absent key → `None` (residual
  mode); present non-object row → `classref_catalog_row_invalid` (never a
  false `custom`).
- `resolution` on every plan row: `composed` when the row carries
  `composed_class`, else `catalog` when a row exists, else `custom`.
  Composed rows carry `class` (the class URN) and `side_effect` (the class's
  declaration) — data on the derivation output, mirroring the SDK's plan
  rows.
- Residual mode: the declared fragment IS the effective schema, verbatim
  after the same closed-vocabulary gate at every depth
  (`_check_residual_fragment` recurses `properties`/`items`), the same
  empty-admittance refusal, and the G4 value-type rider.
- W7: "declares nothing" vs "declares no inputs" — a residual action whose
  raw `input_constraints` carries no `properties` key at all derives L0 with
  `input_undeclared: True` (silence never becomes a one-click dispatch).
- The fold hardening on shared paths rides along (all released semantics,
  all on paths the gateway derivation shares): W5/M6 `_check_admittance`
  widening (empty enum, inverted length bounds), W9
  `minLength`/`maxLength` join `_CONSTRAINT_CONTROL_KEYWORDS` (a bounded
  string used to refuse `classref_constraint_unsupported`), W3
  `_intersect_declared_values` (a declared value set under declared bounds
  narrows to the admitted subset; emptied refuses; const outside bounds is a
  conflict) and the `_field_rows` qualified-name collision refusal
  (`classref_duplicate_field`) with the shared `seen` set threaded through
  the descent.
- The `:1771` per-action refusal loop is deleted — this is the removed
  refusal, in its knowledge-gap sense only.

### 3.4 The layout emission (custom section + W1/W8) and the disclosure surface

- `_build_layout` gains `custom_children`: residual members' controls derive
  into a second section `{page_id}-custom` titled "Custom device actions"
  (the SDK's §4.2 surface); catalogued vendor actions keep the main section —
  resolution partitions, never mixes. The custom section never appends into
  an authored page (the authored branch stands as authored; parent record
  §11 risk 4).
- `_complete_authored_buttons`: skips `resolution == "custom"` rows and
  targets the page's MAIN derived section (`{page_id}-section`, falling back
  to `sections[-1]`) — a catalogued action's button must never land in the
  custom section (W1's scoping).
- W1 ordering: completion runs BEFORE the ladder-numeric insert.
- W8: `_insert_ladder_numerics` gains the `(binding_id, field)` dedupe — one
  field, one control. **This changes committed fixture bytes** (see §5).
- The empty-sections disclosure text ("No additional device features.") is
  the SDK's; the gateway's derived pages today emit no section at all when
  empty — mirror the SDK's fallback section (every declared page renders a
  panel) only if the regenerated fixtures carry it (the regen decides; the
  prediction is they do for pages the SDK's W-fold now never leaves empty).

**The disclosure surface (the gateway's REPORTED analog).** The gateway has
no verify-ui gate; its honesty surfaces are the derived marker block and the
rendered page. `DerivedAttachment` gains four frozen fields mirroring the
SDK's `DerivedUI` disclosure fields: `resolutions` (tuple of
`(urn, resolution, class_urn | None)`, sorted), `ignored_pins`,
`unapplied_classes`, `empty_action_pins`. `_classref_fallback` composes a
`disclosures: tuple[str, ...]` from them — formats fixed here, mirrored from
the SDK's REPORTED rows where the SDK has them:

- `custom: {urn}` when the derived layout block mints control nodes for the
  action's slug (the `_custom_minted_slugs` discriminator: every node
  binding id in the derived block — the G1/G2 per-action rule), else
  `custom, renders nothing: {urn}`;
- `ignored pin: {path} contributed nothing (shape matched neither a vendor
  catalog nor a composed class)`;
- `composed class {class_urn} pinned at {path} applied to no declared
  action`;
- `pinned vendor catalog {path} declares no actions`;
- one line per APPLIED composed class:
  `composed: {class_urn} (validated against {family_version}) supplies {n}
  declared action(s)`.

`PresentationState` gains `disclosures: tuple[str, ...] = ()` (derived arm
only); `device.j2` renders them, when non-empty, as a
`<ul data-bw-presentation-disclosures>` inside the existing
`bw-presentation-derived` block. Disclosures are never findings — they never
fail the page, exactly the SDK's REPORTED-never-silent split. The absence
note's pinned bytes (`l4-no-attachment-note.html`) are untouched: the
disclosure list renders only inside the derived branch.

The plan row's `side_effect` rides as data, mirroring the SDK; its consumers
(the gate's D7/forbid arms) are SDK surfaces and are not mirrored — the
gateway has no authored deviation ledger to feed. The R10 deferred-members
disclosure (`derived_variables`, decoder-no-lane) is the six-vocabulary
track's surface (issue #556 Track B), not the action resolution's.

### 3.5 Settings/procedure tolerance

`_assemble_documents` settings arm (`:1491`) and procedure arm (`:1538`)
switch from `catalog_actions[urn]` subscripts to `_catalogue_row(urn,
catalog_actions) or {}` — a custom or composed action bound to a
configuration/procedure slot derives its settings schema from the effective
schema alone, `$id` falling back to `urn:otdp:action:{urn}:input`, and the
procedure target's `input_schema_id` falls back to `None` (the SDK's shapes
at `:1929-1939`, `:2004-2007`).

## 4. What stays refused — the survival arms (constraint: integrity refusals MUST survive)

The arms below each prove one survivor with its distinct code; the review's
first question is whether the split dropped one. Thirteen arms, one per row
of the §3.1 table that refuses (all but the removed `:1771`):

not-admitted pin; tampered pin bytes; non-object pin; `{"actions": 5}` pin;
unserved profile catalog (a copied corpus with the catalog row removed);
absent profile (a `references_override` naming a profile the catalog does
not carry); **slot names an unserved URN — the D4 arm, `classref_unknown_action`
survives the retirement of its own code everywhere else**; schema-invalid
composed doc; ambiguous pin; claim-vs-served-row; claim-vs-pinned-row;
two-classes-one-claim; class-urn-in-two-pins; side-effect-under; plus the
two surviving effective-schema refusals pinned by existing/new arms
(`classref_effective_schema_empty` incl. the W5 shapes;
`classref_effective_schema_conflict` incl. the W3 shapes).

## 5. The parity fixtures regenerate — the byte delta is expected and bounded

The five committed triples (`f1`, `f2`, `f1-da`, `f5-trio`, `f6-smu`) pin the
**pre-W8** emission: f1/f2/f1-da's device-features carries
`margin_ppm, hysteresis_mv, margin_ppm, hysteresis_mv` — each numeric twice
— and f6-smu doubles `max_duration_ms` (arm) and `max_bytes` (fetch). The
released expander emits each once (W8: "the pair used to render twice on
every derived page, catalogued pairs included") and completes buttons before
the insert (W1). So the regeneration from the pinned v0.21.0 expander
**changes existing fixture bytes**, and the gateway derivation must match
the new bytes — keeping the old doubling would be the CON-12 drift the B8
pin exists to catch. The expected delta class, stated before the regen runs:

1. every doubled staging numeric collapses to one occurrence (W8);
2. a completion-appended button may gain its numeric pair where completion
   now precedes the insert (W1) — predicted to touch no committed fixture
   (none exercises completion on a numeric-bearing action), verified by the
   regen diff;
3. nothing else. **Any regen delta outside this class is a mirror defect or
   an undiscovered SDK fold on a shared path — the response is to mirror it
   or report the divergence to the maintainer, never to edit the fixture to
   match the gateway** (kill direction (e) below).

Regeneration procedure (build leg, step 0): materialize the pinned SDK
without touching the submodule working tree —
`git -C packages/sdk archive 88dcc4d | tar -x -C /tmp/sdk-021` — then run
its expander (`derive_ui`) over each fixture descriptor with the corpus
reference resolved the SDK way, canonical-serialize, commit under
`tests/presentation/classref_fixtures/`. The submodule working tree stays
pristine (no `uv` project dir inside it; the `sdk-drift` lane sees no dirt).
Two new fixture tags join the five: an m400-shaped acceptance tag (the
SDK's `descriptor-m400.json` adapted: DAQ profile + the
`urn:meridian:composed-burst:1.0.0` pin + `com.meridian.m400.self_cal` as
the residual — one descriptor carrying all three resolutions) and a
composed-conflict-free variant tag is NOT added (refusal arms mutate
documents in place, the suite's existing `_derive_from_document` shape).

## 6. Commit plan — what each commit proves

Every commit carries the FAST lane (bare `uv run ruff check .`, fresh-cache
bare `uv run mypy`, focused `uv run pytest` for the touched modules); the
full battery (plus both standards tripwires) runs once before push. Each
commit's RED evidence goes in its message.

1. **The refusal split** (§3.1 codes + `_check_slot_conflicts` position;
   no behavior change beyond codes/order). Proves: every integrity arm fires
   with its own new code; the D4 arm still fires `classref_unknown_action`.
   RED: the new-code arms red against the old codes pre-change.
2. **Emission alignment + fixture regeneration** (W1 + W8 + the empty-page
   disclosure section if the regen carries it; the five fixtures
   regenerated from the pinned expander). Proves: the gateway emission
   equals the released expander's on the shared paths. RED: B8 red against
   the committed (doubled) fixtures before the regen — pasted as the
   commit's RED evidence.
3. **Residual resolution** (§3.3 + custom section + `_complete_authored_buttons`
   scoping + `resolutions` field + `classref_catalog_row_invalid` +
   settings/procedure tolerance §3.5). Proves: the `:1771` refusal is gone
   for the recoverable case; a residual action derives labelled controls;
   W7's undeclared-input shape derives L0 with the disclosure. RED: the
   residual arm reds today with `classref_unknown_action`.
4. **Composed resolution** (§3.2 walk + conflicts + side_effect + DS3 +
   the composed disclosure data). Proves: a composed pin supplies the
   catalogue side, D13 narrows it, the plan row names the class, and the
   m400 acceptance tag derives all three resolutions. RED: the composed arm
   reds today (the pin contributes nothing; `:1771` fires).
5. **The disclosure surface + serve-path arms + docs** (PresentationState
   field, `device.j2` list, the composition-level arms over the content
   store, the device-developer-guide presentation paragraph, CHANGELOG,
   this record's obligations walk). Proves: G-M2/G-M7 at the real serve
   path; the rendered page carries the disclosures and the custom section.
   RED: suppress the disclosure assembly → G-M2 reds.

## 7. Pre-committed acceptance rule

Written before any arm ran. Metric: derivation and composition outcomes
through the real code paths — `derive_attachment` over admission-shaped
bytes, and `compose_device_presentation` over the content store — never a
mock, never a test-side reimplementation. Sample: the deterministic fixture
set = 5 regenerated tags + 1 new acceptance tag + the mutated-document
refusal arms (the suite's existing in-place mutation shape).

**SHIPS if all seven hold:**

1. **G-M1 — the recoverable refusal is gone.** The m400-shaped acceptance
   fixture derives with zero refusals AND 100% of its declared actions carry
   a non-null `resolution` on the derivation output. Denominator: the
   descriptor's declared action set, asserted by reading the descriptor
   document — never a literal count (7 actions for the fixture as committed;
   the assertion derives it).
2. **G-M2 — nothing silent.** Every custom member appears as a rendered
   disclosure line (`custom: {urn}` or `custom, renders nothing: {urn}`
   — the renders-nothing form chosen by the per-action minted
   discriminator), and each of ignored pin / unapplied class / empty pin
   produces its line when its shape is presented. Denominator: the count of
   custom members + presented disclosure shapes in the arms; a presented
   shape with no line FAILS.
3. **G-M3 — the layers are distinguishable, gateway leg.** One URN
   (`com.meridian.m400.burst_mode`-shaped) derives `custom` with no pin,
   `composed` with the pin, and — for a served-namespaced sibling —
   `catalog`: three derivations over the real path, three asserted
   resolutions, the composed leg naming its class URN. (Parent record M3's
   gateway leg; the parent's SDK leg is already released.)
4. **G-M4 — the integrity survivors fire, each with its own code.** All
   §4's arms pass; in particular `classref_unknown_action` fires for
   exactly one condition gateway-side (the D4 slot arm) and nothing else.
   Denominator: the enumerated arm list in §4 (15 refusal arms + the 2
   effective-schema survivors).
5. **G-M5 — parity, B8 extended.** For each of the 6 tags (5 regenerated +
   1 new), the gateway derivation's canonical-JSON triple equals the
   committed fixture bytes byte-for-byte, and the fixtures were generated
   from the pinned v0.21.0 expander (the regen procedure's output, with the
   generation recorded in the commit). Denominator: 6 tags × 3 documents =
   18 byte-equalities.
6. **G-M6 — RED-sanity.** Each mechanism neutralized (a `cp` backup of the
   touched file, never `git checkout`) reddens its arm: residual mode off →
   G-M1 reds with the old refusal; `resolution` forced to one value → G-M3
   reds; the disclosure assembly suppressed → G-M2 reds; composed
   discrimination off (composed keys read as ignored) → the composed legs
   of G-M1/G-M3 red; custom-section routing off → the custom-section
   assertion reds.
7. **G-M7 — the serve path.** `compose_device_presentation` over a content
   store admitting the m400-shaped bytes yields `valid=True`, `derived=True`,
   a device-features page whose sections include the `-custom` section, and
   rendered HTML carrying `data-bw-presentation-disclosures` with every
   G-M2 line. Denominator: one composition per presented shape.

**KILLS if any of:** (a) a clean arm needs a corpus byte edited, a pinned
digest re-pointed, or an existing gate assertion weakened to pass — that is
a corpus/mirror conflict for the maintainer, not a test to tune; (b) a
custom or composed member is silent on any surface (derivation output,
disclosure list, rendered section); (c) any §4 refusal is weakened, or two
conditions collapse onto one code that the SDK keeps distinct; (d) a
residual action renders control field rows that do not match its declared
`input_constraints` (the generic surface must be honest about what it
admits); (e) the regenerated fixtures diverge from the gateway derivation
in any way outside §5's stated delta class — the gateway mirrors or the
divergence escalates; the fixture is never edited toward the gateway.

**UNDERPOWERED, not conclusive:** the parity arm cannot run the pinned
expander (environment cannot materialize the archive) — G-M5 is then
UNDERPOWERED and escalates; it is never marked passed on the gateway's own
output alone. Likewise a regen delta that reveals an SDK fold this record
did not analyze halts the parity commit and escalates rather than widening
§5's delta class after the fact.

## 8. Invariant and drift impacts

- **No CTL/STO/CON/REG invariant changes, and none gains an amendment.**
  The slice is read-time presentation derivation inside the L4 frame: no
  store write, no admission event, no control authority, no transport
  surface. REG-4 (the adapter mirror) is untouched — the classref mirror's
  pin is B8 at test level, as the plot-kind record §7 already ruled; this
  leg extends that ruling to the three-layer arc. A02 is *strengthened*:
  D13's narrowing is unchanged for catalogued and composed rows alike, and
  the residual mode never claims admittance a catalog granted — it renders
  the plugin's own declared constraints and labels the row `custom`.
- **Standards: zero bytes move.** The composed schema is already vendored
  and manifest-pinned at 0.4.0 (verified). No family bump, no corpus-manifest
  row, no `make check-sdk-standards` obligation beyond its standing green in
  the battery. No standards-governor dispatch is owed (no `standards/`,
  lock, or version-string motion).
- **Submodule: zero motion.** The pointer already pins v0.21.0; the regen
  reads the pinned commit through `git archive`, leaving the working tree
  pristine. No SDK PR, no #408 order rule engagement.
- **Surfaces that move:** `src/benchweave/presentation/classref.py` (the
  walk, the residual/composed resolution, the emission folds, the
  disclosure fields, the mirrored-source pin paragraph of the module
  docstring — it gains the v0.21.0 arc); `src/benchweave/interfaces/
  ui_presentation.py` (`disclosures` on `PresentationState`, the fallback's
  composition of them); `src/benchweave/interfaces/ui_templates/device.j2`
  (the disclosure list inside the derived block);
  `tests/presentation/test_classref_derive.py` + new/regenerated files
  under `tests/presentation/classref_fixtures/` (NOT the Tier-3
  `fixtures/registry/` lattice — the plot-kind record's ruling);
  `tests/interfaces_ui/test_ui_presentation.py` (serve-path arms);
  `docs/device-developer-guide.md` (a short presentation paragraph: the
  gateway resolves actions in three layers at serving time; authoring
  contract lives in the SDK user guide — drift row 12's plugin-visible
  clause); CHANGELOG. Operator guide: no (no service/config/CI change).
  MCP/REST/CLI/openapi: untouched (the device page is schema-excluded; the
  derivation is internal).
- **CI cost:** in-process tests only; no new job, no browser, no network.
  Estimated +3–6 s on the presentation and interfaces_ui lanes.

## 9. Tier statement (Step 1, rule #254)

**Tier 3 — keyword rule.** The expected diff touches no Tier-3 *path*
(no `standards/`, no `contracts/`, no state migrations, no registry, no
`fixtures/registry/`, no `pyproject.toml`/`uv.lock`, no submodule pointer),
but the diff text carries Step-1 keywords: `sha256` (the walk's digest
verification, the fixture helpers' pin keys, the arms — the touched files
today carry 13+23+7 occurrences and the diff adds more) and `hashlib`
(10+5+7 today, plus the new walk's call); the other six keywords occur
zero times in the code half of the expected diff. First match wins on the
`sha256`/`hashlib` text → Tier 3: mandatory second adversarial reviewer.
No standards-governor pass (no standards motion, per §8).

Keyword scan, measured over this record's own committed text on
2026-10-25 (grep -o, whole file, 553 lines): `sha256` ×2, `hashlib` ×2,
`threading` ×2, `asyncio` ×1, `subprocess` ×1, `migrate` ×2, `recovery` ×1,
`protection` ×1. All but one occurrence sit in §9/§10 themselves — this
enumeration, and §10 risk 2's prose phrase "seen-set threading" (the field
descent threading a recursion set, not the concurrency keyword); the one
outside is §3.2's technical name "migrate-ui" (the SDK CLI, not the
migration sense). Before §9 the body carries `migrate` ×1 and every other
keyword ×0 — the record's mechanism prose says "digest", never the literal.
The CODE half of the expected diff is where the tier actually lands: the
touched files today carry `sha256` ×13 (classref.py) / ×23
(ui_presentation.py) / ×7 (test_classref_derive.py) and `hashlib`
×10/×5/×7, and the mirrored walk and arms add occurrences of both —
first match wins on text, Tier 3 stands on those two alone. The build leg
re-runs the scan over the committed diff before review; the review
re-derives the tier independently.

## 10. Top risks, each with its falsifier

1. **The split drops an integrity refusal** — the single most likely defect
   (parent record §11 risk 2). Falsifier: G-M4's per-code arms, one per
   §4 row, each asserting the exact code.
2. **The regeneration reveals a delta outside §5's class** — an SDK fold on
   a shared path this record did not analyze (e.g. row-order effects from
   the `_field_rows` `seen`-set threading, or a fixture whose bytes move for
   the empty-section fallback). Falsifier/containment: kill (e); the parity
   commit halts and escalates; the delta class is never widened after
   seeing the bytes.
3. **The disclosure surface breaks the pinned absence-note bytes** — a
   device.j2 edit leaking into the absence branch. Falsifier: the existing
   `test_unknown_class_fails_open_to_the_pre_l4_absence_note` byte-equality
   arm stays green in commit 5's lane.
4. **The `_urn_for_binding` slug hazard worsens** — more actions landing on
   one device-features page (catalog + composed + custom mixed) raises the
   terminal-slug collision odds (parent record D6). Falsifier: the
   acceptance arm asserts each action's controls carry its own field rows;
   the hazard itself stays tracked under D6's home.
5. **mypy strict churn from the widened signatures**
   (`_effective_action_schema` Optional, the five-tuple walk return)
   rippling into `_assemble_documents` call sites. Falsifier: fresh-cache
   bare `uv run mypy` in every commit's FAST lane.
6. **Tooling: the gortex graph served a stale index this session** (a text
   query returned zero for a directly observed symbol). Build/review legs
   must not trust graph empties as absence — the mandate's
   content-identity check.

## 11. What this record checked that the brief asserted

- Issue #556's Track A premises verify against the code: the three
  `classref_unknown_action` sites in `derive_attachment`, the
  `document["actions"]`-only walk, the pinned release. One nuance: of the
  three sites, only `:1771` is the recoverable gap — `:1797` is a platform
  fault (re-coded, still refuses) and `:1811` is the D4 corpus fault (kept,
  same code). The issue's "raises at three sites" is accurate; the split is
  not three removals.
- The SDK is not wrong anywhere I must diverge from instinct — no
  report-to-maintainer item on the semantics. The one deliberate gateway
  divergence (not-admitted ≡ unreadable, §3.1) is a source-mapping decision
  already half-made by the existing docstring; it is disclosed in the
  module docstring, not silent.
- Zero deferrals: no deferral table. The track boundary this record draws
  (six vocabularies → Track B; SDK authoring surfaces → the SDK repo) is
  issue #556's own split, not a deferral of this track's scope.

## 12. Gate commands

```
UV_PROJECT_ENVIRONMENT=venv uv run ruff check .
rm -rf .mypy_cache && UV_PROJECT_ENVIRONMENT=venv uv run mypy
UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/presentation/test_classref_derive.py -v
UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/interfaces_ui/test_ui_presentation.py -v
UV_PROJECT_ENVIRONMENT=venv uv run pytest          # full battery + both standards tripwires, once before push
```

Evidence discipline per CLAUDE.md §3.2: TRUE exit codes (unpiped,
`PIPESTATUS`, or output-to-file), counts from `--junitxml` or exit codes
never a filtered summary line, mypy always fresh-cache. RED-sanity
neutralizations use `cp` backups, never `git checkout` (shared stash stack
across worktrees). Worktree: `.wt/556-lane-a-m4t7` only; fold only this
lane's worktree.
