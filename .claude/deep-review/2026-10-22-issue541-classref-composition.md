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
| D1 | The other six vocabularies — procedures, observation variables, channels and decoders, datasets and capture shapes, plot kinds, settings idioms — each needs its own layer-2 declaration and layer-3 residual rule; this increment lands actions only | documentation here | a plugin ships (or an owner-supplied descriptor declares) a member of one of these vocabularies that no class and no served catalog covers, and `derive-ui` refuses or mis-derives on it |
| D2 | The reference-less device — `derive_ui_command` raises `derive_ui_reference` when no class reference matches the descriptor's profiles, so a fully custom device still has no derive path; layers 2 and 3 do not help it because there is no page structure to resolve into | documentation here | the owner's ruling on fork F1 below |
| D3 | Per-control provenance badges — the layout vocabulary's `/control` node admits only `binding_id`, `field`, `kind`, so a `custom` marker renders at section level only | documentation here | the next layout-vocabulary widening opens (a `plugin-ui-class-reference` family bump for any other reason), at which point the provenance field rides it |
| D4 | The reference-slot knowledge gap (`derive_ui:706`) — a class's own slot naming an unserved URN is a corpus fault, not a vendor gap; the split leaves it refusing | documentation here | a class reference in the corpus is shown to name an action URN that no served catalog describes |
| D5 | Composed-class claims across two classes for one URN — refuse, never merge; a shared action class is a corpus-side design question | documentation here | a second plugin or a corpus class needs to claim an URN another class already claims |
| D6 | The `_urn_for_binding` global terminal-slug resolution hazard (composition record §4) becomes easier to reach as more actions land on one device-features page | documentation here; recorded in `.claude/deep-review/2026-10-20-classref-composition-gate-design.md` §4 | the owner's ruling on that record's §4 rows arrives, or a composed device renders one class's staging fields under another class's button |
| D7 | The SDK user guide's coverage of the new developer-facing surfaces — `resolution` provenance, `ui/class-reference.json`'s `custom_actions`, `verify-ui`'s `custom: <urn>` rows, and the "Custom device actions" section — is owed, not present (`user_guide/plugin-sdk.qmd`, currently mentioning `ui/class-reference.json` only for the `migrate-ui` pointer). **Extended 2026-10-23 after the slice-2 review:** it must also carry the composed authoring contract — the declaration's document shape (`urn`, `claims`, `input_schema`, `side_effect`), the claims and conflict rules, the closed `side_effect` set and the S20 direction — plus the `composed_actions` and `composed_classes` ledger rows. The SDK vendors no corpus README, so without this a vendor has no shipped, versioned description of the document they must author | documentation — slice 4 of this increment (task #146) | the release cut that ships either slice's behaviour, which must not land before this row closes; the cut's checklist reads this row |
| D8 | The corpus prose for the declaration document is under-described: `standards/plugin-ui-class-reference/0.3.0/README.md` §"The deviation ledger contract" still describes the document as profile, version and `deviations` only, while the SDK now writes a third key. The "zero standards motion" claim in §9 is scoped to **schema bytes** — no schema governs the declaration's key set — and does not cover this prose | documentation — slice 2's standards leg, which adds the 0.4.0 copy | the release cut that ships slice 1's behaviour, which must not land before this row closes |
| D9 | The CON-12 gateway mirror still refuses the recoverable case: `src/benchweave/presentation/classref.py::derive_attachment` raises `classref_unknown_action` at ~1765/1791/1805. Slice 1 is SDK-only by design, so the shipped state is "a plugin derives and previews", not yet "runs on a bench here" | documentation here; carried to the pointer PR | the gateway pointer advances to the release that carries slice 1 |

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
