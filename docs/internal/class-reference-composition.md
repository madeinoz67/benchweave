# Class-reference composition: three-layer action resolution

Maintainer architecture note for gateway issue #541 (slices 1–3, and this
documentation slice). It explains the mechanism the class-reference family and
the SDK expander now share — how a descriptor action resolves, where the
provenance of every control comes from, and which honesty rules keep the
no-refusal promise from becoming a silent-derivation promise. It is an
engineering record, not a normative surface: the normative text for the
composed document is the corpus README section "Composed action classes"
(`standards/plugin-ui-class-reference/0.4.0/README.md`), and the design
arguments live in the records listed at the end. Cross-references replace
restatement here by design.

Design records:

- `.claude/deep-review/2026-10-22-issue541-classref-composition.md` — the
  parent program record: the gap, the three layers, the honesty mechanism,
  the slices, and the deferral table (D1–D9) this note cites by id.
- `.claude/deep-review/2026-10-22-issue541-s2-standards-design.md` — the
  composed-action-class schema and the 0.4.0 family bump (the schema's closed
  sets and their derivations).
- `.claude/deep-review/2026-10-20-classref-composition-gate-design.md` — the
  cross-class composition gate (gateway issue #500).
- `.claude/deep-review/2026-10-16-classref-l5-plugin-ui-0-4-0-design.md` —
  the input-trio widening the ladder and field rows ride.

## 1. The problem the three layers solve

The class reference is a designed presentation per device class. It cannot
exhaust vendor operations: the long tail of a plugin's own verbs is open-ended
by construction, and every class reference is authored in isolation from the
plugins that will claim it. Before this increment, an action no served catalog
described was a hard stop — `derive-ui` raised `classref_unknown_action`. The
parent record's census (§1) locates the defect precisely: that one code was
raised from seven sites covering **two different conditions** — integrity
faults (a missing profile catalog, an unreadable or digest-mismatched pinned
document) and a recoverable knowledge gap (the descriptor declares an action
no catalog row describes). Conflating them meant a builder whose device was
mostly a class, with a handful of vendor features, was refused for a gap the
corpus was never going to close — a builder who had done nothing wrong, with
no path forward short of an upstream request.

The parent record's §1.1 finding bounds the increment: the refusal was the
*only* blocker. The derivation path for an uncovered action already existed —
the `vendor_actions` coverage slot, the device-features page, generic field
rows, generic control nodes — and the ladder already turned any input schema
into reachability plus field rows. So this is not a generic renderer added; it
is the removal of an assumption (every action has a catalogue row) plus an
honesty mechanism to replace the refusal's disclosure function.

## 2. The three layers

![The three-layer resolution decision](assets/classref-layer-resolution.png)

*Figure 1 — the resolution decision per declared action: a served catalog row
is layer 1 (`resolution: catalog`), a composed action class's claim is layer 2
(`resolution: composed`), and anything left is the residual layer 3
(`resolution: custom`). Editable source:
`assets/classref-layer-resolution.drawio`.*

- **Layer 1 — class actions (unchanged).** A descriptor action the served
  OTDP catalog or a pinned vendor catalog describes resolves exactly as
  before: the catalogue `input_schema` and the descriptor's `input_constraints`
  intersect (D13), and the ladder derives level and field kinds.
- **Layer 2 — composed action classes.** Mechanism, in one sentence: layer 2
  is layer 1 with the catalogue side supplied by a composed action-class
  declaration instead of the served catalog. A claim is an explicit versioned
  action key; the class document contributes `input_schema` and `side_effect`
  and nothing presentational. The claim joins the same `actions` map the
  catalog walk fills (the injection site in
  `packages/sdk/src/benchweave_sdk/classref.py::_vendor_documents`), so
  **D13, the reachability ladder and the field-row derivation are shared, not
  duplicated** — one intersection function (`_effective_action_schema`), one
  ladder (`_ladder_level`), one field-row derivation (`_field_rows`) runs for
  all three layers. The declaration asserts no component: the ladder keeps
  ownership of the component mapping, and the schema refuses a `component`
  field outright (the s2 record §3 derives this and the closed `side_effect`
  set from the axes the gate actually consumes).
- **Layer 3 — residual custom members (always on).** An action no catalog and
  no class claims derives from the descriptor's own `input_constraints`, which
  is already JSON Schema; the effective schema is the constraints alone (the
  `_effective_action_schema` residual mode), and the row lands on the
  device-features page through the existing vendor-actions arm. There is no
  flag and no opt-in: the acceptance scenario is a builder who does not know
  the class reference exists (parent record §3).

Two derivation refinements ride the same path and belong to no single layer:
the D13 intersection is narrowing-only on bounds (both sides value-typed
before comparison; an empty admittance refuses `classref_effective_schema_empty`),
with the parent record's B10 correction carried — `pattern` and `multipleOf`
take the constraint's value rather than intersecting it, a pre-existing
replacement this increment did not widen; and a residual action whose
`input_constraints` carries no `properties` key at all declares nothing, which
derives `L0` with a disclosure naming the absence rather than a one-click
button (the W7 fold: silence must not become dispatch).

## 3. Resolution through to the gate

![Resolution through to the gate](assets/classref-resolution-to-render.png)

*Figure 2 — the pipeline every declared action travels: the layer decision is
recorded on the plan row first, then the shared machinery (effective schema,
ladder, field rows, layout section) runs, and `verify-ui` separates findings
(a defect; the run fails) from reported rows (a disclosure; the run passes).
Editable source: `assets/classref-resolution-to-render.drawio`.*

The order is load-bearing: resolution is decided and recorded **before** the
shared machinery runs, so every downstream surface reads the same provenance
rather than re-deriving it. `verify-ui`'s two channels are the honesty
boundary the no-refusal promise rests on — a defect (a coverage miss, a
forbidden control) is a `findings` failure; a disclosure (a custom member, an
unapplied class, a deferred vocabulary member) is a `reported` row that never
fails a run and never disappears.

## 4. Provenance as data

Every control plan row carries `resolution: "catalog" | "composed" | "custom"`
— provenance is data in the derivation output, not a log line (parent record
§4.1). A composed row additionally carries `class` (the class URN, whose
suffix is the class's own version) and the class's declared `side_effect`.
The stamp is derived at exactly one point — the catalogue-row check in the
plan construction (`classref.py` plan build) — and every consumer reads the
row: the conformance ledger's inventories, the gate's read-back sets, the
`derive-ui` output. A reader can therefore trust which layer produced a
control because the label cannot be re-decided downstream, and because the
only writer of `composed` provenance is the composed walk itself (rule 1
below). What this does **not** catch: a future surface that derives controls
without reading the plan row would bypass the provenance entirely — the
pinning is on the current consumers (ledger, gate, read-backs), not on the
renderers' internals.

## 5. The honesty rules

Removing a fail-closed refusal without a replacement is the failure this
design refuses to commit; the rules below are the replacement, and each one
was taught by a specific defect rather than invented for symmetry.

**1. Composed provenance has exactly one writer.** The composed walk is the
only code path that writes `composed_class` onto an action row; a
vendor-catalog action row carrying a stray `composed_class` key is **stripped**
on read (`_vendor_documents`, the N2 fold). Defect that taught it: the
document-shape discriminator is conjunctive over top-level keys (`urn` AND
`claims`) and never inspects keys riding inside an action row, so a stray key
rode beside a `side_effect` into the D7-feeding plan row and could launder the
composed label — the review's disposition assumed the conjunctive test made
the strip unnecessary; it did not.

**2. The ledger records the classes the derivation applied, and both tools key
to that set.** `composed_classes` records the classes the derivation
*applied* — a class applies when at least one of its claims names an action the
descriptor declares (`_applied_class_urns`). Both `verify-ui` (the composed
read-back, `_composed_inventory_findings`) and `migrate-ui` (the drift
arithmetic in `_migrate_classref_ledger`, over `composed_ledger_inventory`)
key to exactly that set. Defects that taught it, both in the same field: the
drift arithmetic originally carried actions only, so a ledger whose
`composed_classes` rows were deleted passed both tools green and the next
family bump re-stamped the family stamps without re-resolving the now-unnamed
classes — silently losing the validation record (the s2 record §8 refute
correction); and keying to the pin-declared set instead refused
`migrate_ui_ledger_drift` against a ledger `derive-ui` had just written for a
sanctioned class whose claims name nowhere on this descriptor — the author's
re-derive looped on byte-identical output (the R1 fold).

**3. Four states are reported, never silent.** All four ride `verify-ui`'s
`reported` channel in both gate arms (the reference-less arm carries every
disclosure too — the B6/B7/R3 discipline):

| State | Disclosure | Defect that taught it |
|---|---|---|
| A pinned class that applied nowhere | `composed class <urn> is pinned (<path>) but its claims name no action this descriptor declares` | invisible before the row existed — and, per rule 2, simultaneously miscounted as drift (R1/B7) |
| An empty catalog pin | `pinned document <path> contributed nothing (its vendor-catalog actions map is empty)` | a shape-valid vendor catalog declaring no actions contributed nothing and said nothing (R5) |
| An ignored pin | `pinned document <path> contributed nothing` | a digest-verified pin matching neither shape was dropped silently; the same walk crashed on bare `AttributeError` for a non-object pin or a non-dict `actions` map before those faces were typed refusals (B7/R4) |
| A declared member with no derivation | `<kind> <member>: derivation deferred (the <vocabulary> vocabulary has no derivation in this increment; D1)` | a computed measurement and a custom decoder declare cleanly and derive nothing; silence there is indistinguishable from "we rendered it and it looked fine" (R10) |

**4. The ledger is read back, both directions.** The authored
`ui/class-reference.json` is compared against the derivation —
`custom_actions` against the derived custom set (the W10 fold),
`composed_actions` and `composed_classes` against the derived composed
inventory **including the action→class mapping** (the B6 and R6 folds) — and
every mismatch is a reported row, never a `findings` failure. Defect that
taught it: the inventories were write-only — an authored ledger could omit
every residual member (or name a nonexistent URN) and pass, and a
`composed_actions` row naming the wrong class for an action verified clean and
migrated with "nothing to do". On the reference-less path the honest report is
`inventory unavailable`, never a mismatch blaming a declaration that does not
exist (G5/R3).

**5. Refusals the split did not remove.** Digest mismatch and unreadability of
a pinned document; a missing profile catalog or absent profile; claim
conflicts (a claim a served row or another class holds — refused
`classref_composed_claim_conflict`, sort order never picks a winner);
`side_effect` under-classification against the descriptor's own declaration
(`classref_composed_side_effect_under`, the S20 direction at the class layer);
a reference slot naming an unserved action (D4); an empty admittance
(`classref_effective_schema_empty`); the D7 non-downgradable carve-out —
nothing stands between the operator and abort. Only one refusal was removed,
and only in its knowledge-gap sense (parent record §8).

## 6. The promotion path

![The promotion path from plugin-local declaration to corpus](assets/classref-promotion-path.png)

*Figure 3 — a composed class ships inside the plugin package on the proven
`descriptor.contracts[]` pin seam (path + sha256; a digest mismatch still
refuses), resolved descriptor-relative by the SDK and from admission bytes by
the gateway — the same pin, the same digest. Corpus promotion is maintainer
curation: a reviewed copy into a corpus family version directory (digest-
pinned, copy never move). Promotion is available, never required — it is not
an authoring gate. Editable source: `assets/classref-promotion-path.drawio`.*

Two sources, one resolver: the shared corpus (curated, maintainer-owned) and
the plugin package (vendor-local) ride the same pin seam and the same shape
discrimination. Promotion is literally a file move from the plugin's
declaration directory into a corpus version directory — which is why promotion
never blocks authoring: a vendor class is fully functional from the plugin
package before, during, and without any corpus review. The promotion guard
that refuses a duplicate class urn, and the written promotion procedure,
land with the first real promotion (DS4 in the s2 standards record; parent
record's D-table row for the guard rides the same trigger).

## 7. What is deferred

Each row names its deferral id in the parent record
(`.claude/deep-review/2026-10-22-issue541-classref-composition.md` §6) so a
reader can trace the argument; the reopen triggers are the record's.

| Deferred | Id | Where it surfaces today |
|---|---|---|
| The other six vocabularies — procedures, observation variables, channels and decoders, datasets and capture shapes, plot kinds, settings idioms — each needing its own layer-2 declaration and layer-3 residual rule | **D1** | actions only in this increment; a member of these vocabularies that no class and no served catalog covers declares cleanly and derives nothing |
| Computed measurements and custom decoders — the two named member shapes of D1's vocabularies | **D1** | the gate discloses each one per run on the reported channel (`deferred_members`, naming the deferred vocabulary); a computed measurement derives no surface, a custom decoder whose lanes no derived plot hosts renders no lane |
| The reference-less device — a descriptor matching no class still refuses (`derive_ui_reference`); layers 2 and 3 need a page structure to resolve into | **D2** (fork F1) | no derive path; `verify-ui`'s reference-less arm reports the inventory as unavailable |
| Per-control provenance badges — the layout vocabulary's `/control` node admits only `binding_id`, `field`, `kind` | **D3** | the `custom` marker renders at section level only (the derived section's own label) |
| The gateway mirror (CON-12) — the gateway derivation still refuses the recoverable case | **D9** (mirror leg DS5) | `derive_attachment` in `src/benchweave/presentation/classref.py` still raises `classref_unknown_action`; the shipped state is "a plugin derives and previews", not yet "runs on a bench here" |

The complete deferral table (including the reference-slot knowledge gap, the
cross-class shared-claim question, the terminal-slug resolution hazard and the
SDK user-guide coverage owed as D7) is the parent record §6. The corpus prose
for the declaration document (D8) closes with this increment's README
extension. Deferral is not a defect: each row carries its reopen trigger, and
the named states above are disclosed rather than dropped.

## 8. Enforcing surfaces

What keeps this note from drifting from the code (named mechanisms, not a
promise to re-read):

- The derivation and gate suites in the SDK — the acceptance fixture (the
  invented Meridian M-400 device: mostly DAQ, one composed action, one
  residual action) and the per-fold arms pin M1–M5 of the parent record
  (no refusal for the recoverable case; nothing silent; three distinguishable
  resolutions for one URN; the integrity refusals survive; RED-sanity per
  mechanism).
- `tests/ui_html/test_classref_composition.py` (gateway issue #500) — the
  cross-class pair gate over the real selection and merge.
- The corpus baseline suite (`tests/contract/test_baseline.py`) and the
  family contract test (`tests/architecture/test_plugin_ui_class_reference_contracts.py`)
  — copy-never-move, source lineage and schema pins over the family trees.
- The ledger's own tools: `derive-ui` writes the inventories, `verify-ui` reads
  them back, `migrate-ui` re-stamps them under set arithmetic — the three-way
  agreement in rule 2.

Fixture names in this family ("Meridian", "Veridian", the `ch1`/`ch2` channel
naming) are invented, per the corpus README's Names section.
