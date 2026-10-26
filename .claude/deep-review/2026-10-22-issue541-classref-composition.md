# Class-reference composition: actions resolve in three layers (gateway issue #541)

Status: designed 2026-10-22 in `.wt/comp-q8v3` (branch
`feat/issue541-classref-composition`, base `origin/main` `e2ffa82a`; SDK
submodule at its `main` lineage, `benchweave-sdk` 0.18.0). Owner directive
2026-10-22: the class reference must handle customization — a plugin builder
with a device mostly covered by a class and a few vendor features must get a
complete styled UI with no refusal, no upstream request, no hand-written
manifest pages and no plugin-authored CSS. Converged design: three-layer
resolution that never refuses. **Actions land first**; the other six
vocabularies follow the same shape in their own increments.

Triage check (`.claude/deep-review/README.md`): public. The record carries
invented fixture names. The real-world evidence is cited by issue reference,
not by product name, per CLAUDE.md §4.

## 1. The gap, located exactly

`benchweave-sdk` `src/benchweave_sdk/classref.py` raises
`classref_unknown_action` from seven sites. They are **two different
conditions wearing one code**, and that conflation is the defect:

| Site | Condition | What it actually means |
|---|---|---|
| `_catalog_documents:199` | the descriptor's profile catalog is not in the served tree | **platform fault** — the SDK installation is incomplete |
| `_vendor_catalogs:224` | a pinned vendor catalog file is unreadable | **platform or project fault** |
| `_vendor_catalogs:229` | a pinned vendor catalog's digest does not match its pin | **integrity fault — tampering or corruption** |
| `_profile_row:743` | the descriptor's profile is absent from the served profile catalog | **platform fault** |
| `derive_ui:681` | the descriptor declares an action URN no served catalog describes | **knowledge gap — recoverable** |
| `derive_ui:706` | a reference slot names an action URN no served catalog describes | **knowledge gap OR corpus fault** |
| `coverage_plan_without_reference:1458` | same as `derive_ui:681`, reference-less path | **knowledge gap — recoverable** |

The recoverable condition is the last three. A vendor operation the eight
classes cannot cover is not an integrity problem; it is the long tail the class
reference can never exhaust. Today that long tail is a hard stop.

Evidence the refusal fires in the field: a public community plugin's descriptor
(OTDP 0.2.2) declares `set_trigger_position`, no served catalog describes it,
and `derive-ui` refuses with `classref_unknown_action` across SDK 0.12.0–0.18.0
(issue #541's own evidence row). The same shape appears in the preview-fixture
path for dataset shapes (#449 slice 2), which is why the pattern must
generalize.

### 1.1 The refusal is the *only* blocker

This is the finding that bounds the whole increment. The derivation machinery
for unclaimed actions **already exists and already renders**:

- Every class reference carries a `vendor_actions` slot — the corpus README
  0.3.0 calls it "the D14 coverage hook: it covers every declared action URN
  that no named slot claims" — and a `device-features` page that hosts it
  (`class-daq.json` pages, `vendor_features: true`).
- `_derive_controls:615` defaults an action with no named slot to page
  `device-features`.
- `_build_layout:1567-1587` derives staging nodes and buttons for every plan
  action whose page is this page — the comment there reads "D14: actions whose
  bindings carry no page (vendor actions) still derive their controls on their
  plan page".
- `_ladder_level:557` and `_row_mode:480` turn any input schema into L1/L2/L3
  reachability plus numeric/text/enum/const/boolean field rows, from the closed
  vetted vocabulary.

So the path an uncovered vendor action takes — plan row on the device-features
page, generic field rows, generic control nodes — is **already built**. What is
missing is one thing: `_derive_controls:611` calls
`_effective_action_schema(urn, catalog_actions[urn], constraints)`, and that
subscript assumes a catalogue row exists. Nothing about the *rendering* is
missing.

That reframes the increment: this is not "build a generic renderer". It is
"stop assuming every action has a catalogue row, and say out loud which
resolution produced each control."

## 2. What already exists that the design must extend, not replace

**The plugin-package payload seam.** `_vendor_catalogs:206` resolves
descriptor-pinned vendor catalogs from files relative to the descriptor,
digest-checked against `descriptor.contracts[].sha256`. The gateway's mirror
(`src/benchweave/presentation/classref.py::_vendor_catalog_documents:1100`)
resolves the *same* pins from admission bytes by digest, and its docstring
states the equivalence explicitly: "the gateway has no plugin package dir; the
SDK resolves descriptor-relative files, the admission store is the gateway's
equivalent". This is the proven mechanism for shipping vendor knowledge **inside
the plugin** at zero coordination cost, and it is exactly what the owner's
constraint "vendor classes ship inside the plugin package" asks for.

**The D13 narrowing rule.** `_effective_action_schema:403` composes the
catalogue's `input_schema` with the descriptor's `input_constraints` as a
**narrowing intersection only** on the axes it computes — bounds intersect,
exclusivity carries, an empty admittance refuses
`classref_effective_schema_empty`, and no path widens what the catalogue
admits on those axes (A02's discipline: the SDK never invents admittance).
*Correction, refute lane A via the 2026-10-23 fold (B10):* two pre-existing
keywords are REPLACED by the constraint's value rather than intersected —
`pattern` and `multipleOf` (`_intersect_property` assigns
`effective[...] = constraint[...]` for both) — so a looser constraint
pattern or a coarser multipleOf widens the catalogue's admittance on
exactly those two keywords. Both predate this increment (verified
untouched by the #541 slices' diffs); the "no path can widen" sentence
above was wider than the code and is corrected here rather than left
claiming more than the mechanism delivers.

**The author-owned declaration.** `derive-ui` already writes
`ui/class-reference.json` (`_build_declaration:1814`) — an author-owned
conformance ledger with a deviation vocabulary that refuses unknown ids
(`classref_unknown_expectation`) and refuses to launder the D7 energy-removing
case at all.

**The gate's REPORTED channel.** `classref_gate.py`'s `GateReport` carries
`reported_deviations` beside `findings` (`:34-45`), filled by `_assert_expect`
(`:200`, `:286`) and by `_coverage_findings:417` — which reports an action
covered by a declared deviation instead of failing it. "REPORTED, never silent" is an
existing, released honesty surface — not something this design invents.

## 3. The three layers, precisely

### Layer 1 — class actions (unchanged)

A descriptor action the served OTDP catalog or a pinned vendor catalog
describes resolves exactly as today. Catalogue schema AND descriptor
constraints intersect (D13); the ladder derives level and field kinds.

### Layer 2 — composed action classes

**Mechanism, in one sentence: layer 2 is layer 1 with the catalogue side
supplied by a composed action class document instead of the served OTDP
catalog.** Nothing else changes — same intersection, same ladder, same field
rows, same layout emission.

A composed action class is a versioned declaration:

```json
{
  "contract_version": "0.1.0",
  "urn": "otdp.action.numeric_staging/1.0.0",
  "title": "Numeric staging action",
  "claims": ["otdp.<vendor-namespace>.set_trigger_position/1.0.0"],
  "input_schema": { "type": "object", "properties": { "...": {} } },
  "side_effect": "state_change"
}
```

Amended 2026-10-22 after the slice-2 standards design: the closed `side_effect`
set is `none | state_change | energy_removing`, taken from the axis OTDP already
owns (served catalog action rows and the device-descriptor schema both declare
`none | state_change`), with `energy_removing` as the one refinement the gate's
arms actually consume — the census confirm ban, `intermediated-energy-removing-action`
and the D7 carve-outs all key on energy-removing versus the rest. This record's
earlier example literal `configuration_write` is superseded: a configuration
write *is* a state change, and forking the axis would contradict the descriptor's
ownership of it. The declaration's `contract_version` is its own dialect version
(`0.1.0`), not the family version, so a family bump does not repin every vendor
document.

Design calls this shape settles:

- **`claims` binds explicitly.** A class names the action URNs it presents —
  never a name-derivation guess. One class may claim many actions (that is what
  "composed" buys: a vendor with ten same-shaped operations declares one class),
  and a claim conflicts with a catalogue row, another class, or another claim
  refuse typed rather than let sort order pick a winner.
- **The ladder keeps ownership of the component mapping.** The declaration
  supplies `input_schema`; `_row_mode` and `_ladder_level` still decide which
  §E control renders and at what reachability. A declaration may never assert
  "render this as a button" for an action with required numeric inputs — that is
  how a control silently loses its fields. So "a component key from the fixed
  inventory" (the owner's phrasing) resolves to: **the component inventory is
  the existing one, applied by the existing rule.** No new component vocabulary.
- **`side_effect` is evidence, not layout.** It is the declaration's statement
  about what the action does, and its consumer is the gate's forbid arms
  (`confirm-wrapped-run-action`, `intermediated-energy-removing-action`) and the
  D7 check — the axes where an undeclared side effect is a safety question, not
  a presentation question. A value outside the closed set refuses.
- **Two sources, one resolver.** The shared corpus (curated, maintainer-owned)
  and the plugin package (vendor-local). The plugin-package source rides the
  existing `descriptor.contracts[]` pin seam (§2): path + sha256, resolved
  descriptor-relative SDK-side and by digest from admission bytes gateway-side.
  Corpus promotion is then literally a file move from the plugin's declaration
  directory to a corpus version directory — maintainer curation that never
  blocks authoring, exactly as directed.

### Layer 3 — residual custom members (always on)

An action URN no catalogue and no composed class claims derives from the
descriptor's own `input_constraints`, which is already JSON Schema. The
effective schema is the constraints alone; the ladder and field rows run
unchanged; the row lands on the device-features page through the existing
vendor-actions arm.

**Layer 3 is always on. There is no flag.** A flag would be friction, and the
owner settled it: the acceptance scenario is a builder who does not know the
class reference exists.

## 4. What replaces the refusal — the honesty mechanism

Removing a fail-closed refusal without a replacement is the failure this design
must not commit. Four mechanisms replace it, and each is visible to a different
reader:

1. **Provenance on every plan row.** Each control plan row carries
   `resolution: "catalog" | "composed" | "custom"` (and for `composed`, the
   class URN and version). The provenance is data in the derivation output, not
   a log line.
2. **A named section on the page.** Residual actions derive into their own
   section on the device-features page, whose title the expander mints —
   the same authority that already mints `{page_id}-section` ids and the "No
   additional device features." body. The section is the visible `custom` label.
   *Per-control* provenance badges need a layout-vocabulary field
   (`/control` admits only `binding_id`, `field`, `kind`), so they are deferred
   (row D3) rather than smuggled in.
3. **A REPORTED row per custom member in the gate.** `_coverage_findings` and
   `_assert_expect` already carry `reported`; a custom member lands there by
   name, every run. A custom member cannot pass the gate silently, and cannot
   become a `findings` failure either — it is a disclosure, not a defect.
4. **The declaration records the custom inventory.** `ui/class-reference.json`
   gains the custom rows, so the project's own conformance record — the file
   `upgrade` and `migrate-ui` re-stamp — states what is uncatalogued from birth.

The invariant this buys: **an action is never refused for being unknown, and is
never rendered without saying so.**

## 5. Slices

**Slice 1 — residual resolution (SDK only, no standards bytes).**
Split the seven `classref_unknown_action` sites into integrity faults (still
refuse, with their own codes) and the recoverable knowledge gap (resolve
residual). `_effective_action_schema` gains the no-catalogue-row mode;
`_derive_controls` stops subscripting the catalogue; plan rows gain
`resolution`; the expander mints the custom section; the declaration records
the custom inventory; the gate reports them. Test arms: the acceptance fixture
below, a RED arm per mechanism, and the integrity-refusal arm proving the
survivors still refuse.

**Slice 2 — layer 2 composed action classes (SDK + standards leg).**
The declaration document, its resolver and conflict refusals; the
plugin-package source through the existing pin seam; `side_effect` feeding the
forbid arms; `migrate-ui` re-stamping the declaration's `contract_version` and
its claimed class versions across a contract bump.

The declaration needs a schema, and a schema is a contract: **this slice
carries a `standards/` leg and therefore parks on Stephen's word before it
lands.** Recommended home: a sibling schema file in the existing
`plugin-ui-class-reference` family rather than a new family — the family is
already the presentation-declaration home, and the promotion path is then a file
move inside one family. The honest cost: a family version bump re-stamps the
family manifest and its eight class files under copy-never-move.

**Slice 3 — the acceptance fixture and the render arms.**
The invented Meridian M-400 fixture (mostly DAQ, one composed action, one
residual action) through `new --with-ui` → `derive-ui` → `verify-ui` on the real
standalone host, plus the packaging arm: a wheel carrying a vendor-local action
class installs and previews standalone.

## 6. Deferrals

Home uniform across all rows: **documentation here** (this record), except where
a row names a follow-on issue.

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | The other six vocabularies — procedures, observation variables, channels and decoders, datasets and capture shapes, plot kinds, settings idioms — each needs its own layer-2 declaration and layer-3 residual rule; this increment lands actions only | documentation here | a plugin ships (or an owner-supplied descriptor declares) a member of one of these vocabularies that no class and no served catalog covers, and `derive-ui` refuses or mis-derives on it. **CLOSED 2026-10-26 — the trigger fired and was answered.** #556 Track B landed the six vocabularies (SDK slices B1–B6; the gateway mirror B7). Evidence: the Track B record `.claude/deep-review/2026-10-25-issue556-track-b-vocabularies.md` (its SDK-side copy ships at benchweave-sdk v0.22.0) and the two merged gateway pull requests #561 (the 0.5.0 family and the v0.22.0 pointer) and #559 (the composed-member mirror). The close-out row-state table and the gateway re-check are §15. |
| D2 | The reference-less device — `derive_ui_command` raises `derive_ui_reference` when no class reference matches the descriptor's profiles, so a fully custom device still has no derive path; layers 2 and 3 do not help it because there is no page structure to resolve into | documentation here | the owner's ruling on fork F1 below. **UNCHANGED 2026-10-26.** Out of #556's scope: Track B's record §0 extends this row's boundary by one sentence (vendor-minted pages) and does not reopen it. The trigger has not fired. |
| D3 | Per-control provenance badges — the layout vocabulary's `/control` node admits only `binding_id`, `field`, `kind`, so a `custom` marker renders at section level only | documentation here | the next layout-vocabulary widening opens (a `plugin-ui-class-reference` family bump for any other reason), at which point the provenance field rides it. **UNCHANGED 2026-10-26.** The 0.5.0 layout vocabulary still admits only `binding_id`, `field` and `kind` on `/control` (measured on `standards/plugin-ui-class-reference/0.5.0/layout.schema.json` `$defs.control`); no widening opened. |
| D4 | The reference-slot knowledge gap (`derive_ui:706`) — a class's own slot naming an unserved URN is a corpus fault, not a vendor gap; the split leaves it refusing | documentation here | a class reference in the corpus is shown to name an action URN that no served catalog describes. **UNCHANGED 2026-10-26.** Still refused. #556 added the member half (an applied procedure or configuration claim no served or pinned catalog describes refuses `classref_unknown_action`); the reference-slot half is unchanged. |
| D5 | Composed-class claims across two classes for one URN — refuse, never merge; a shared action class is a corpus-side design question | documentation here | a second plugin or a corpus class needs to claim an URN another class already claims. **UNCHANGED 2026-10-26.** Still refuse-never-merge. #556 widened the conflict family — a claim another member or an applied composed class holds refuses `classref_composed_slot_conflict` — and no shared-claim merge landed. |
| D6 | The `_urn_for_binding` global terminal-slug resolution hazard (composition record §4) becomes easier to reach as more actions land on one device-features page | documentation here; recorded in `.claude/deep-review/2026-10-20-classref-composition-gate-design.md` §4 | the owner's ruling on that record's §4 rows arrives, or a composed device renders one class's staging fields under another class's button. **UNCHANGED 2026-10-26.** The owner's §4 ruling has not arrived. One mechanism change is recorded and is not a closure: #556 Track B's B4 fold made the slot-keyed binding map win over the action-slug scan in `_urn_for_binding`; the slug scan stays the founding fallback. |
| D7 | The SDK user guide's coverage of the new developer-facing surfaces — `resolution` provenance, `ui/class-reference.json`'s `custom_actions`, `verify-ui`'s `custom: <urn>` rows, and the "Custom device actions" section — is owed, not present (`user_guide/plugin-sdk.qmd`, currently mentioning `ui/class-reference.json` only for the `migrate-ui` pointer). **Extended 2026-10-23 after the slice-2 review:** it must also carry the composed authoring contract — the declaration's document shape (`urn`, `claims`, `input_schema`, `side_effect`), the claims and conflict rules, the closed `side_effect` set and the S20 direction — plus the `composed_actions` and `composed_classes` ledger rows. The SDK vendors no corpus README, so without this a vendor has no shipped, versioned description of the document they must author | documentation — slice 4 of this increment (task #146) | the release cut that ships either slice's behaviour, which must not land before this row closes; the cut's checklist reads this row. **CLOSED 2026-10-26 — verified in B8.** The SDK user guide at v0.22.0 carries the coverage this row names (`user_guide/plugin-sdk.qmd`: the three-layer resolution, `custom_actions`, the `custom: <urn>` rows, the "Custom device actions" section, the composed action-class authoring contract, and the `composed_actions` / `composed_classes` / `composed_members` ledger rows), shipped by Track B's B6. One stale sentence remains in that guide and is a named follow-up, not a reopen: "The gateway mirror of this resolution is also deferred. A gateway still refuses an action that the SDK resolves" is false since gateway #557; recorded in §15. |
| D8 | The corpus prose for the declaration document is under-described: `standards/plugin-ui-class-reference/0.3.0/README.md` §"The deviation ledger contract" still describes the document as profile, version and `deviations` only, while the SDK now writes a third key. The "zero standards motion" claim in §9 is scoped to **schema bytes** — no schema governs the declaration's key set — and does not cover this prose | documentation — slice 2's standards leg, which adds the 0.4.0 copy | the release cut that ships slice 1's behaviour, which must not land before this row closes. **CLOSED 2026-10-26 — verified in B8.** The family's 0.4.0 copy describes the declaration's full key set (`standards/plugin-ui-class-reference/0.4.0/README.md` §"The deviation ledger contract" names `profile_ids`, `contract_version`, `reference_version` and four inventories), and the 0.5.0 copy extends the prose. The row's home — slice 2's standards leg — landed. |
| D9 | The CON-12 gateway mirror still refuses the recoverable case: `src/benchweave/presentation/classref.py::derive_attachment` raises `classref_unknown_action` at ~1765/1791/1805. Slice 1 is SDK-only by design, so the shipped state is "a plugin derives and previews", not yet "runs on a bench here" | documentation here; carried to the pointer PR | the gateway pointer advances to the release that carries slice 1. **CLOSED 2026-10-26.** Track A's gateway mirror landed (PR #557) and the pointer advanced to v0.22.0 (PR #561) — the row's own trigger. Evidence: `.claude/deep-review/2026-10-25-issue556-track-a-gateway-mirror.md`; the gateway's `derive_attachment` resolves the recoverable case, pinned by `tests/presentation/test_classref_derive.py`. |

## 7. Pre-committed acceptance rule

Written before any arm ran. Metric: derivation and gate outcomes through the
real code path (`derive_ui`, `verify_ui`, the real standalone host) — never a
mock and never a test-side reimplementation.

**SHIPS if all five hold:**

1. **M1 — the refusal is gone for the recoverable case.** The acceptance
   fixture (mostly DAQ, one composed action, one residual action) derives with
   zero refusals, AND 100% of its declared actions appear in the control plan
   with a non-null `resolution`. Denominator: the descriptor's declared action
   set, stated by assertion over the descriptor, never a literal.
2. **M2 — nothing degrades silently.** Every residual member appears in
   `GateReport.reported_deviations` labelled `custom`, and the declaration's
   custom inventory is non-empty exactly when residuals exist. A run where a
   custom member is absent from the report FAILS this metric.
3. **M3 — the layers are distinguishable.** The same action derives
   `resolution: "custom"` with no class, `"composed"` with a plugin-local class,
   and `"catalog"` when a served catalog describes it — three distinct outcomes
   for one URN, each asserted. **Leg ownership, stated so a later reader cannot
   score this on a partial arm:** slice 1 closes the catalog and custom legs;
   the composed leg is slice 2's, and M3 is satisfied only when all three are
   asserted on one branch.
4. **M4 — the integrity refusals survive.** A tampered pinned catalog (digest
   mismatch), an unreadable pinned catalog, and a missing profile catalog each
   still refuse, with distinct codes. Removing the recoverable refusal must not
   have removed these.
5. **M5 — RED-sanity.** Each mechanism arm fails when its mechanism is
   neutralized: residual resolution off → M1 reds with the old refusal; the
   `custom` label suppressed → M2 reds; the provenance field forced to one value
   → M3 reds. The neutralization uses a `cp` backup, never `git checkout`.

**KILLS if any of:** (a) a clean arm needs a corpus byte edited or an existing
gate assertion weakened to pass — that is a corpus/expander design conflict for
the owner, not a test to tune; (b) any residual member is silent on any surface
(report, declaration, or rendered page); (c) an integrity refusal is weakened;
(d) a residual action renders a control whose field rows do not match its
declared `input_constraints` (the generic surface must be *honest* about what it
admits).

**UNDERPOWERED, not conclusive:** a clean arm reds because the HOST cannot
render a surface the schema admits. That is a discovered host defect, not
evidence about the resolution design; it escalates and the rule is never tuned
to make it pass.

## 8. What stays refused

Removing a refusal is the one motion this slice must be able to defend in front
of a reviewer, so the survivors are listed before the build:

- digest mismatch or unreadability of a pinned vendor catalog;
- a missing profile catalog or a profile absent from the served catalog;
- a composed class claiming an URN a catalogue row or another class already
  claims, or two classes claiming one URN;
- a composed class's `side_effect` outside the closed set;
- a reference slot naming an action no catalog describes (D4);
- an effective schema narrowing to an empty admittance
  (`classref_effective_schema_empty`, unchanged);
- a D7-class deviation attempt (unchanged — nothing stands between the operator
  and abort);
- a composed member declaration whose `plot.over_slot` is not the member's
  own `slot` key — `classref_composed_plot_slot_mismatch` (added 2026-10-25
  by #556 track B's B2 fold: a declaration conflict, a document referring to
  itself inconsistently; the code is enumerated in the track B record §3
  rule 4, the family 0.5.0 schema description and README).

**B7 addendum (2026-10-26, #556 Track B):** the composed-member mirror adds
its own survivors to this set, the SDK's walk-side inventory carried over
(the B3 fold's F3 and the B5 fold's F3 named this row as the gateway-side
home): the member-declaration schema refusal
(`classref_invalid_member_declaration` — a schema-invalid document, a member
pin against a corpus whose active family serves no member schema, and an
applied action member whose declaration carries no vendor profile row);
`classref_composed_plot_slot_mismatch` (the over-slot self-reference);
the member conflict family under `classref_composed_slot_conflict` (a slot
key a reference slot or another member holds, a claim a member, class or
reference slot holds, a page the reference does not declare, and a member
slot key spelling a derived observation id at the mint);
`classref_composed_plot_page_mismatch` (a dataset-binding plot kind on a
readings page); the member half of D4 (`classref_unknown_action` for an
applied procedure or configuration claim no served or pinned catalog
describes); and `pinned_id_shadow` over exactly the accepted pin set (the
shared guard's own code, not a `classref_*` name). None of these replaces
a disclosure: capacity and placement limits (the joined page over the lane
ceiling, a plot on a page that already hosts one, the composed series past
the analog ceiling) drop and REPORT, per the 2026-10-25
capacity-versus-declaration boundary.

**B7 divergence entry, ruled by the team lead 2026-10-26 — the class-only
analog over-ceiling case.** CON-12 binds the gateway to the SDK's intended
semantics, not to every behaviour the SDK happens to ship, and an unhandled
failure where a refusal belongs is not a semantic; mirroring it would make
two halves wrong together. The condition, precisely: an analog plot
(`time_series` or `waveform`) whose OWN y series — the class's traces, NOT
the composed computed variables (those mirror the SDK's B1 fold exactly:
dropped from the plot, disclosed on the residual channel, wire shape
unchanged) — exceed the manifest schema's `y.maxItems` 16 (`_ANALOG_Y_CEILING`).
Both halves are now REPRODUCED, each through its production path (this
paragraph updated 2026-10-26 by the refute follow-through; the entry's
original wording cited the SDK side from the Track B record's B1 addendum
rather than measuring it — no longer). GATEWAY side, through
`derive_attachment` on this branch: the typed refusal
`classref_series_ceiling: {N} numeric variables ride the {kind} plot
(ceiling 16)`, counted over the non-computed ids only — pinned by
`test_a_numeric_series_ceiling_refuses_typed`
(`tests/presentation/test_classref_derive.py`). SDK side, independently
reproduced 2026-10-26 through the shipped gate (`create_ui_resources`
deriving and writing a manifest whose plot carries `y` count 17,
unrefused and undropped, then the real `verify_ui` raising
`PluginLoadError: standalone_plugin_invalid:
preview_invalid_presentation: invalid_document: ui-manifest: Document
does not satisfy its schema`) at SDK main `37905f7`; the derive-half
(`derive_ui` green with the 17-entry `y`, the schema violation captured
by raw jsonschema over the derived manifest) first reproduced at
`20ad123` during the refute differential, identical at `37905f7`. The
divergence is deliberate and convergent, and it is an OUTSTANDING
MIRROR OBLIGATION: the moment the SDK fixes its own class-over-ceiling
handling, the gateway adopts whatever it lands on.

Only **one** refusal is removed, and only in its knowledge-gap sense: "I do not
know what this action admits" becomes "I derived it from the plugin's own
declaration, and I am telling you so."

## 9. Invariant and drift impacts

- **No CTL/STO/CON/REG invariant changes.** The slice is presentation
  derivation. The A02 discipline is *strengthened* if anything: D13's narrowing
  rule is untouched for catalogued actions, and layer 3 never claims admittance
  a catalogue granted — it renders the plugin's own declared constraints and
  labels the row `custom`.
- **CON-12 (the SDK mirror) is the live obligation.** The two derivations
  (`src/benchweave/presentation/classref.py` gateway-side and
  `benchweave_sdk/classref.py` SDK-side) are deliberate mirrors. Slice 1 is
  SDK-only by design — the gateway's `_vendor_catalog_documents` and
  `derive_attachment` keep refusing the recoverable case until the mirror lands,
  which is disclosed here rather than discovered later. The mirror is a named
  follow-on, not an omission: **the gateway's L4 no-manifest fallback is
  production serving motion and is not in this increment's licence.**
- **Surfaces that move:** SDK package (`classref.py`, `classref_gate.py`, tests,
  CHANGELOG, a MINOR version); gateway design record; slice 2 additionally the
  `plugin-ui-class-reference` family and the pointer PR (gitlink + `.gitmodules`
  pin in one commit, #408 order: SDK merge → release cut → pointer).
- **CI cost:** in-process ASGI renders only, the existing `verify-ui` shape. No
  browser, no network, no new job.
- **Obligations walked:** #408 order rule; `make check-sdk-standards` on the
  pointer PR; `sdk-drift` green with pin == released tag; `migrate-ui`'s
  re-stamp arm for the new declaration (slice 2); the scaffold's
  `regen-fixtures` path unaffected but re-run if catalogue rows move.

## 10. Tier statement (Step 1, rule #254)

**Tier 3.** First match: the slice advances the `packages/sdk` submodule pointer
and, at slice 2, moves `standards/` bytes and version strings. The
`standards-governor` pass is owed at slice 2 regardless of tier; the adversary
pass is mandatory at tier 3 and runs **two independent lanes** (#181 R3) on the
slice that touches the declaration schema.

Keyword scan over this record's expected diff text (this file only, scanned
2026-10-22): the Step-1 keyword set occurs in this section's own enumeration and
nowhere material — the record's body carries `digest` and `pin` as ordinary
mechanism vocabulary, which is the mechanism's actual subject, not a self-fire.
The build leg re-runs the scan over the committed diff before review; the review
re-derives the tier independently.

## 11. Top risks, each with its falsifier

1. **Layer 3's generic surface is dishonest** — it renders field rows from
   constraints alone and a reader reads that as catalogue-admitted. Falsifier:
   acceptance rule (d). Mitigation: `resolution: "custom"` on the row, the
   section label, the REPORTED gate row, and the declaration inventory — four
   surfaces, none of which can be suppressed without reddening M2.
2. **The removal is wider than intended** — a careless edit drops an integrity
   refusal along with the knowledge gap. Falsifier: M4. This is the single most
   likely defect in the slice, and the reason the split is the first commit's
   work rather than a cleanup after it.
3. **`resolution` proves harder to thread than it looks** — the plan row flows
   into `_build_layout`, `_complete_authored_buttons`, `_insert_ladder_numerics`
   and `_build_expectation`, and any of them may key on the row's shape.
   Falsifier: M3 (three distinct resolutions for one URN) plus the existing
   class-reference suite passing unchanged.
4. **The custom section collides with the authored path** — a reference that
   authors its own device-features layout would have the derived section
   appended into an authored page. Falsifier: a fixture class with an authored
   vendor-features page. Mitigation: the derived section appends only where the
   page has no authored layout block, and the conflict arm asserts it.
5. **The SDK work collides with an in-flight local train.** The standalone
   checkout currently sits on an unpushed branch bumping to 0.19.0. Falsifier:
   the release cut refusing, or a merge conflict on `pyproject.toml` /
   `standards-lock.json`. Mitigation: the version bump is a release-cut-time
   motion, not a slice commit, and the slice branches off `origin/main` (0.18.0).

## 12. Forks for the owner

- **F1 — the reference-less device.** Layers 2 and 3 fix devices that *are*
  mostly a class. A device that matches no class still refuses
  (`derive_ui_reference`). Recommendation: **defer** (D2). The acceptance
  scenario is "mostly a DAQ", and inventing a page structure for a device with
  no reference is a design question with its own evidence needs — a synthetic
  baseline reference would be the shape, and it deserves its own increment.
- **F2 — the declaration's standards home.** Recommendation: a sibling schema
  in the existing `plugin-ui-class-reference` family (promotion inside one
  family) rather than a new `plugin-ui-action-class` family (a family
  migration). Either way it is a standards motion and parks on your word.
- **F3 — the `custom` label's granularity.** Recommendation: **section-level
  now, per-control later** (D3). The layout vocabulary cannot carry a per-control
  marker without a widening, and a widening to carry a label is a poor trade for
  the vocabulary's first motion.

## 13. Gate commands

SDK (`UV_PROJECT_ENVIRONMENT=venv`, evidence from true exit codes / junitxml,
never a filtered summary line):

```
UV_PROJECT_ENVIRONMENT=venv uv run ruff check .
rm -rf .mypy_cache && UV_PROJECT_ENVIRONMENT=venv uv run mypy
UV_PROJECT_ENVIRONMENT=venv uv run pytest src/benchweave_sdk/tests/test_classref_residual.py \
  src/benchweave_sdk/tests/test_classref_expand.py \
  src/benchweave_sdk/tests/test_classref_gate.py \
  src/benchweave_sdk/tests/test_classref_cli.py -v
UV_PROJECT_ENVIRONMENT=venv uv run pytest          # full battery before push
```

Gateway (this record's commit; slice 2's pointer PR):

```
UV_PROJECT_ENVIRONMENT=venv uv run ruff check .
rm -rf .mypy_cache && UV_PROJECT_ENVIRONMENT=venv uv run mypy
UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/ui_html tests/presentation
UV_PROJECT_ENVIRONMENT=venv uv run pytest          # full battery + both standards tripwires
make check-sdk-standards                           # pointer PR only
```

The test paths above are the intended homes; the build leg corrects them to the
SDK's actual layout if it differs, and says so in the commit.

## 14. Addendum (2026-10-26, the B7 refute fold) — the record corrected, the census carried, the fallback mirrored

The adversarial lane on the B7 mirror (23-scenario hand differential,
SDK derivation vs gateway derivation) found the mirror faithful — every
refusal code, every disclosure row and every derived surface it reached
agreed — and found five things besides. All five fold in one commit;
the dispositions and their evidence follow.

**F1a (MEDIUM) — the gateway-side per-surface comparison obligation is
unaddressable as written, and nothing said so.** The B5 fold's mirror
obligation (the SDK-side Track B record, 2026-10-26) ends: "The
gateway's per-surface gate rows grow the reading-tile comparison beside
its data-table one." That sentence assumes a surface that does not
exist on this side. Measured by the refute lane, line-pinned on this
branch's tree: the gateway has no coverage gate, no authored ledger and
no per-surface comparison of any kind —
`src/benchweave/presentation/classref.py:1275-1278` merges every
reference's `expect.components` into the merged reference, and its ONLY
consumer is the `expect.controls` read at `:2601`; a grep of
`src/benchweave/presentation/` for the per-surface vocabulary
(reading-tile/data-table beyond the layout node KINDS at `:1848`/
`:1879`) and for the gate's own detector names
(`_reading_surface_findings`, `_data_table_surface_findings`, census,
`data-bw-binding`) finds nothing — `contracts.py` carries zero hits;
the B7 test modules
(`tests/presentation/test_classref_members.py`,
`test_classref_member_disclosures.py`) carry no per-surface arms. The
SDK carriers the obligation points at are `classref_gate.py:588` and
`:644`, wired at `:1067`/`:1076`, with the census reading the render's
`data-bw-binding` at `:126`/`:131` (SDK refs at `37905f7`; the lane
verified the detectors exist and are wired — the MISSING-not-
downgradable / EXCESS-downgradable directionality wording is the
record's own, not a line it read). Therefore the per-surface
expectation obligation has NO GATEWAY HOME — this is not a deferral;
the surface does not exist on this side — and what the mirror carried
is the derive-side minted sets those rows would consume (the
reading-tile expansion, the per-page plot emission, the disclosed
placements — byte-pinned by the f6-smu and dmm tags). If a gateway
coverage surface is ever built, the comparison rides it. The defect
was the record's, not the code's, and this entry is the correction.

**F1b (MEDIUM) — the equivalence census gained its composed-member
arms.** This record's CON-12 obligation ("the equivalence census gains
composed-member arms when B7 lands") is carried:
`tests/sdk/test_descriptor_equivalence.py` now drives the same
descriptor and pin through BOTH derivations — the gateway's
`derive_attachment` over admission-shaped bytes and the pinned SDK's
`derive_ui` over a spooled package (every non-`urn:otdp:` pin file
written beside the descriptor, the reference read from the pinned SDK's
vendored family tree) — over eight table cells: the m400 acceptance
tag (all three resolutions, triples byte-equal, disclosure data and
resolutions equal), the dmm fallback tag, the ambiguous pin, the
claim-vs-served-row, side-effect-under and digest-mismatch refusals
(codes equal both sides), the ignored/unapplied/empty pin-disclosure
cell (data tuples equal — the row formats themselves pinned by the F4
literals in `test_ui_presentation.py`, because the pinned gate's
comprehensions are pure f-strings over exactly those tuples), and the
member-pin PIN-LAG cell: the pinned SDK ignores a members document
while the gateway refuses `classref_invalid_member_declaration`
against a corpus serving no member schema — pinned as a NAMED
divergence that flips to a clean-equal comparison when the pointer
advances past the B3–B5 lineage (the cell's assertion message says so).
A teeth arm plants a disagreement (the discriminator over-firing on a
plain catalog) so the table's green proves the comparison runs. Not
covered, stated in the module docstring: refusal DETAIL sentences
(codes only — the sanctioned detail divergences stay here and in the
Track A record); the SDK gate's own REPORTED minting (renderer-borne,
pinned SDK-side); the gateway-only mints (composed-supplies row, member
residual rows); the member vocabulary beyond the pin-lag cell. Runtime:
the census module runs 174 tests in the lane's ordinary time — the
differential adds eight in-process derivations, no new job, no
renderer.

**F2 (LOW-MEDIUM) — the empty-page fallback is mirrored, by decision.
** Track A §3.4 deferred the fallback to "the regen decides"; no
committed fixture carried an empty page, so the regen never decided and
the conditional stayed open. The refute reached the divergence on the
plain committed `descriptor-dmm.json` (the pinned SDK's own classref
fixture, unmutated): the pinned SDK's layout carries three pages, the
gateway's two — the device-features page, fully placed, omitted. The
gateway's omit site (`if sections:` gating the page append) is
identical at pre-B7 main `255a6a6d` — the divergence is pre-existing
from Track A, not B7-widened. Ruled 2026-10-26: mirror the SDK. The
mechanism (`presentation/classref.py::_build_layout`, the `if not
sections` block) is the pinned SDK's own emission since the 0.3.0
family widening (present at the `88dcc4d` pin), mirrored verbatim —
"No additional device features." on a `vendor_features` page, "No
additional surfaces for this page." otherwise. Byte-stability
evidence, before/after: **zero of the 28 committed fixture files
moved** (measured two ways — `git status` shows only the four NEW dmm
files, and every reference-declared page on all six pre-existing tags
derives non-empty, so the fallback never fires for them); the four new
files are the dmm tag, generated from the pinned SDK expander at
`88dcc4d` with its own emitted fallback bytes (sha256: descriptor
`2ecc070b…`, envelope `3b65182d…`, manifest `1f49f864…`, catalogue
`9ba8f54a…`). RED, pre-fix: `assert {'readings', 'configuration'} ==
{'readings', 'configuration', 'device-features'}` — "Extra items in
the right set: 'device-features'" (the fallback arm), and the dmm
parity cell red on the manifest diff.

**F3 (LOW-MEDIUM) — the test stand-in schema is a declared bridge, and
the bridge announces its own retirement.** The B7 member arms run on a
test-authored stand-in because the served corpus (0.4.0 at this
pointer) serves no member schema — the real one is the B2 standards
motion, ahead of the pointer. The stand-in is MATERIALLY LOOSER than
the real `composed-member-declaration.schema.json`, and
`classref_members_support`'s module docstring now enumerates the SIX
loosenesses the refute measured (no member ceiling, no closed
channels/action member split — no `oneOf`, no
`additionalProperties:false` — no required claims on action members,
no plot conditionals — series not required on analog kinds, group keys
absent — no length or pattern bounds anywhere the real schema pins
them, no vendor-profile constraints) and what production will narrow;
its "same required keys and closed sets" claim — false — is gone. The
refute's behavioral pin: a channels member carrying `claims` is
refused by the real schema on both sides
(`classref_invalid_member_declaration`, the oneOf finding), while
under the stand-in the walk ACCEPTS the document and reaches
`classref_composed_slot_conflict` — which is why the arms prove the
WALK, never the schema. The guard arm
`test_the_stand_in_announces_the_real_schema` FAILS the day the
committed corpus serves any member schema at the ACTIVE family
version (presence check, bytes never compared), so the bridge cannot
outlive its premise silently. RED demonstration, planted scratch
corpus (zero standards bytes touched): the guard fired with its
retirement instruction; day-one state green (the committed corpus
serves none).

**The #561 ordering, ruled by the team lead 2026-10-26 (after this
fold's arms were written): the standards PR (`benchweave#561`) lands
the 0.5.0 corpus and the v0.22.0 pointer FIRST, and this fold lands
after it** — which is precisely the condition the guard was built to
announce. Handled in this commit, not deferred to the rebase:
`build_member_corpus` plants the stand-in ONLY in the window where the
active family serves no member schema and returns the copy untouched
when it does; the member arms were driven against the REAL 0.5.0
schema (PR #561's bytes planted at the active family path, sha256
`3c5835d4…`) and **25 of 26 pass in that world — 24 unchanged, the
transitional refusal arm after its premise-construction fix below, and
the guard firing as the retirement instruction** — no arm needs the
stand-in once the corpus serves the real document, so its post-#561
retirement is a deletion, not a port. The two window arms construct
their own premise: the transitional refusal arm strips a served schema
to build its no-schema corpus, and the guard's firing in that world is
the instruction to delete the stand-in and itself together. The member
path's family literals are swept (the reference helpers read the ACTIVE
family version, pinning no 0.4.0). The fixture triples do not move
when the corpus moves (the team lead's ruling: the corpus change is a
re-stamp plus additions).

**The #561 rebase, executed (same day): the stand-in is RETIRED, not
guarded.** Main merged the standards PR (bfc5e197: the 0.5.0 corpus,
schema sha256 `3c5835d4…`, and the pointer to benchweave-sdk `v0.22.0`
at `0d4b44d`); this branch rebased clean onto it and the retirement ran
exactly as measured: `MEMBER_SCHEMA_STAND_IN` and the retirement guard
are DELETED together (the guard's condition — corpus serves the schema
while a stand-in exists — is permanently satisfied and would fire
forever); `build_member_corpus` is a plain copy; the two placement
arms' plots gained the real schema's required `series` key (they had
been written against the stand-in's looser plot — the only arms whose
documents changed, and their purpose, the placement disposition, does
not depend on the missing key); the transitional refusal arm keeps its
constructed premise; **NO arm keeps the stand-in**. The census's
member-pin cell FLIPPED as its own assertion message instructed: both
lanes now walk the member document at v0.22.0 and refuse it
identically (`classref_unknown_action`, the member half of D4 — a
claim no served or pinned catalog describes needs the catalogue side),
so the cell is `both-refuse:classref_unknown_action`. **One fixture
triple moved, the dmm tag** — this fold's own new tag, one corpus
generation behind at birth: the envelope and manifest each moved
exactly one line (the manifest's `contract_version` stamp 0.4.0 →
0.5.0, the envelope's embedded manifest pin following; the catalogue
byte-identical, `9ba8f54a…` before and after) — the pointer lane's
re-stamp class, regenerated from the v0.22.0 expander over the 0.5.0
corpus. Manifest sha256 `1f49f864…` → `28f0ee12…`; envelope
`3b65182d…` → `3a08991f…`. The other six tags' fixtures were re-stamped
on main by the pointer lane and did not move here.

**F4 (LOW) — the three Track A-era pin rows are the SDK's wordings
now.** The ignored-pin, unapplied-class and empty-catalog rows carried
wording the SDK never minted (Track A §3.4's formats), and B7 had
EDITED one of them (the ignored-pin row gained "nor a member
declaration" pre-fold) instead of aligning it — the
`_classref_disclosures` docstring's "mirrored from the SDK's REPORTED
rows where the SDK has them" was false for exactly these three (the
gateway wordings at `ui_presentation.py:744-754`; the SDK gate minted
its rows twice — reference-less arm and reference-carrying arm, at
`37905f7` `classref_gate.py:973-987` and `:1165-1190` — and the member
family already matched verbatim). Aligned to the gate's rows
(superseding §3.4's formats; Track A's record text stands as history):
`pinned document {path} contributed nothing`; `composed class {urn} is
pinned ({pin_path}) but its claims name no action this descriptor
declares`; `pinned document {path} contributed nothing (its
vendor-catalog actions map is empty)`. Zero fixture bytes moved — the
rows are serve-time mints over the derivation's data, not derivation
output (the F1b cell pins the data both sides mint from).
`docs/internal/class-reference-composition.md` rows 170-172 already
carried the SDK wordings — the code was the divergent half, and the
alignment closes the doc-vs-code gap with zero doc edits. RED,
pre-fix: `AssertionError: pinned document extra-1.json contributed
nothing` (the realigned row absent from the rendered page).

**F5 (NIT) — two residuals accepted.** The gateway's residual rows
drop the SDK `ResidualMember.vocabulary` field (SDK `classref.py:96` at
`37905f7`; the gateway's `residual_rows` is a `(kind, member, detail)`
triple): the rendered row ("`{kind} {member}: {detail}`") is identical,
and the field feeds only SDK-side ledger consumers the gateway does not
carry. The seam's reader (`pinned_contract_documents`, gateway
`classref.py:2531`) keeps single-group documents only where the SDK's
presentation-side reader (`presentation.py:174` at `37905f7`) keeps
every non-empty group: on a green derive an ambiguous pin already
refused in the walk (`classref_invalid_composed_class`, gateway
`classref.py:2268-2278`), so the stricter drop is unreachable from a
green derive and errs in the safe direction — a document the walk
refused contributes nothing. The same reader also silently continues on
a non-object pin (gateway `:2529-2530`) where the SDK's reader refuses
typed — likewise unreachable gateway-side (the walk's non-object arm
refuses first, and admission guarantees decodable bytes).

**The builder lane's four-place prose-vs-code list, folded.** The B7
builder lane's report to the team-lead enumerated four places where the
SDK's published semantics and the record's prose disagree; the list is
THE BUILDER LANE'S. The adversarial lane independently verified places
1 and 3; places 2 and 4 it reached by its own separately found findings
(it never read the builder's list — it declined to reconstruct parts it
had not seen, and this entry does not credit it with verifying them):

1. *The per-surface gate rows* ("the gateway's per-surface gate rows
   grow the reading-tile comparison beside its data-table one") —
   VACUOUS: the gateway has no surface to mirror. Verified (F1a above):
   no coverage gate, no authored ledger, no per-surface comparison;
   `expect.components` merged and never consumed; the obligation has no
   gateway home and is not a deferral — the surface does not exist on
   this side.
2. *The class-only over-ceiling case* — the ruled divergence; §8's
   dated entry above is its home and now carries both halves reproduced
   through their production paths. Cross-referenced here, not restated.
3. *A member's plot choice on a readings page* — verified: the code is
   RIGHT on both sides and the prose was WRONG. The emitted time_series
   binds the page's first observation because a dataset binding on a
   readings page is a capability mismatch, so the first-observation
   binding is the only valid emission; the mirror inherited nothing
   bad. A reader who finds the stale prose need not re-litigate.
4. *The SDK's empty-page fallback section stays un-mirrored* — the
   adversarial lane's F2 by another route (three pages against two on
   the plain DMM descriptor). RESOLVED, not carried: this fold's F2 fix
   mirrors the fallback, and the dmm-shaped fixture now pins the shape
   byte for byte.

## 15. Addendum (2026-10-26, the B8 close-out) — D1 closed, the neighbours walked

#556 Track B's slice plan ends at B8: the docs and the close-out. This
addendum records the §6 deferral table's state after the whole arc
merged, so a reader does not have to reconstruct it from the commits.
Every state change below is an explicit dated marker on the §6 row, never
a silent rewrite of the prose that shipped.

| id | state on 2026-10-26 | what changed it |
|---|---|---|
| D1 | **CLOSED** | #556 Track B: the six vocabularies landed in the SDK (B1–B6) and the gateway mirrored them (B7). |
| D2 | open (unchanged) | Out of scope. Track B's record §0 extends the boundary by one sentence (vendor-minted pages) and does not reopen it. |
| D3 | open (unchanged) | No layout-vocabulary widening opened. |
| D4 | open (unchanged) | The member half was added; the reference-slot half still refuses. |
| D5 | open (unchanged) | Still refuse-never-merge. |
| D6 | open (unchanged) | The owner's §4 ruling has not arrived; B4 changed `_urn_for_binding`'s precedence, recorded in the row and not a closure. |
| D7 | **CLOSED** (retrospective) | The SDK user guide's coverage landed with Track B's B6 and is verified against benchweave-sdk v0.22.0. |
| D8 | **CLOSED** (retrospective) | The 0.4.0 family copy described the document's full key set; the 0.5.0 copy extends the prose. |

**What closed D1, with pointers.** D1's reopen trigger was "a plugin
ships (or an owner-supplied descriptor declares) a member of one of these
vocabularies that no class and no served catalog covers, and `derive-ui`
refuses or mis-derives on it". #556 Track B answered the trigger
vocabulary by vocabulary; each row's layer-2 home, layer-3 rule and
REPORTED disclosure is recorded in the Track B record's §4 and its dated
addenda (`.claude/deep-review/2026-10-25-issue556-track-b-vocabularies.md`;
the SDK-side copy of that record ships at benchweave-sdk `v0.22.0`,
commit `0d4b44d`):

- procedures, settings idioms, channels and decoders, datasets and
  capture shapes, and plot kinds compose through one composed member
  declaration with four member kinds (`channels`, `dataset`,
  `configuration`, `procedure`), validated by the family's 0.5.0
  `composed-member-declaration.schema.json`.
- observation variables need no new document: the descriptor's own
  `derived_variables[]` row is the layer-2 declaration; the variable
  derives into dataset shapes and plot series, never a reading tile, and
  the gate reports the states.

Evidence lives in two places, and both are named because either alone is
incomplete: the Track B record carries the design and the per-slice folds;
the two merged gateway pull requests carry the served state — **#561**
(the 0.5.0 family copy and the `v0.22.0` pointer, merge `bfc5e197`) and
**#559** (the composed-member mirror, merge `f485f873`).

**The B8 re-check is code-side, not record-side.** D1's closure is not
taken from the records alone. The shipped gateway derives member surfaces
and discloses the residual states: `src/benchweave/presentation/classref.py`
`_composed_member_inventory`, `_check_member_reference_conflicts`,
`_inject_composed_members` and `_residual_member_rows`; pinned by
`tests/presentation/test_classref_members.py` (25 tests) and
`tests/presentation/test_classref_member_disclosures.py` (15 tests), and
by the classref differential in `tests/sdk/test_descriptor_equivalence.py`
(eight table cells, each driving both derivations over the same descriptor
and pin; `test_classref_lanes_agree_on_every_composed_scenario`, with the
teeth arm `test_the_classref_differential_bites_on_a_planted_disagreement`).

**D7 and D8 close retrospectively, and the reason is stated.** Both rows'
triggers were release cuts that have already happened. Leaving them open
would leave this record claiming a gate that was passed. The coverage was
verified against the shipped artifacts, not assumed: the SDK guide at
`v0.22.0` and the 0.4.0/0.5.0 README copies, by the checks named in the
rows themselves.

**One stale claim found during the walk, reported not fixed here.**
`user_guide/plugin-sdk.qmd` at the pinned SDK `v0.22.0` still says: "The
gateway mirror of this resolution is also deferred. A gateway still
refuses an action that the SDK resolves." That sentence was true when
Track B's B6 wrote it and is false since gateway PR #557 (Track A) and
#559 (the mirror). The fix is in the SDK repository, outside this gateway
branch's licence; it is recorded here so the next SDK documentation pass
carries it. It is not a D7 reopen: D7's coverage requirement is met; the
sentence is a stale claim adjacent to it.
