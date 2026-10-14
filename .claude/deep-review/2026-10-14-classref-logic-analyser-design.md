# Per-class reference presentations — vertical slice on `otdp.logic_analyser`

**Date:** 14 October 2026
**Scope:** gateway issues #463 rows 1–2 and the rendered gate; #462 rows 1–2 (pattern-library
composition). Out of scope: #460, #461, #463 rows 3/7/8.
**Branch:** `feat/classref-gw-c7k2` (gateway). SDK work lands in `benchweave-sdk` under the
same gateway issue (single issue stream; the SDK PR notes no SDK-side issue exists by design).
**Evidence baseline:** SDK v0.12.0 (`7063a88`), gateway `origin/main` (`e1b1bf84`),
plugin-ui 0.3.1 both sides, OTDP 0.2.3, `benchweave-ui-html==0.2.1`.
**Binding design points:** D1–D12 from the original brief, plus **D13 (effective
capability)** and **D14 (action coverage)** folded 2026-10-14 as first-class owner
points of the same rank — D13 lands in §2.4 and §3.7–§3.8, D14 in §2.5, §3.9 and the
gate's always-on coverage arm (§5); both move the schema (§2.2), the fixtures (§3.5)
and the acceptance rules (A1, A4, A9, A10). A second owner ruling the same day rolls
the **recipe vocabulary IN** (supersedes the D-2 deferral; mechanism in §2.6), and a
third makes every deferral an **owner row-call** (§8's table is the candidate list;
the numbered row-call list lives on the tracker).

## 0. Summary

One reference presentation per device class, written as **data in a new standards family**
(`plugin-ui-class-reference/0.1.0`), is the single source for three consumers: the
pattern-library class page (#462), an SDK expander that turns a class-conformant descriptor
into a normal plugin-ui 0.3.1 manifest set (#463 row 1), and an SDK gate that renders the
result through the real preview host and compares the **rendered component inventory**
against the reference's `expect` (#463 row 2). The gateway application
(`src/benchweave/`) is untouched.

Root cause established (why the manual-correction burden exists today):

- `benchweave_sdk/presentation.py::create_ui_resources` derives presentation targets from
  `descriptor["parameters"]` only (`_ui_targets`, `benchweave-sdk/src/benchweave_sdk/presentation.py`).
  A logic-analyser descriptor is channel/action-shaped — the OTDP class example carries
  `"parameters": []` (`standards/otdp/0.2.3/examples/class-logic_analyser.json`) — so
  `new --with-ui` **refuses** such a descriptor outright ("UI scaffolding requires at least
  one readable descriptor parameter"). There is no working path to correct: the author
  hand-writes every domain artifact, and any descriptor edit breaks the envelope pin
  (`presentation.json` `/descriptor_sha256` + `/manifest/sha256`; `ui/manifest.json`
  `/descriptor_sha256`) and the catalogue's capability binding. The measured baseline
  (fresh scaffold: one `time_series` plot, "1 plotted channel from host-observed reads",
  no lanes, no configuration page, no run buttons) is the scalar-device residue of that
  parameter-shaped derivation.

## 1. D3 ruling — a new standards family (option a)

**Ruling: new data-only family `plugin-ui-class-reference`, first version `0.1.0`,
admitted on gateway main.** Not a plugin-ui bump; not SDK-internal.

Precedent, each with file + mechanism:

1. **The change-class row admits it.** `standards/GOVERNANCE.md` change-class table:
   "New standard | admission | Review + `status: stable`; new tree dir at its first
   version". The first-version admission is exempt from the bump window (G-5 retains the
   first-version exemption).
2. **`plugin-ui-preview` is the in-tree shape of a data-only UI-adjacent family.**
   `standards/plugin-ui-preview/0.2.0/` = two schemas (+ MIGRATION.md), no code row, and a
   floor-compliant multi-serving range (`>=0.1.1,<0.3.0`) — because it has **no live code
   object** to protect (`standards/standards-manifest.json` `dependency_policy.standards.
   "plugin-ui-preview".note`). Our family is the same shape: schemas + reference documents,
   no code rows, multi-serving from birth.
3. **Option (b) breaks D11 mechanically.** plugin-ui's normative bundle row lists
   `src/benchweave/presentation/contracts.py` — a live gateway code object — in every
   carried version's row (`standards-manifest.json` `normative` for plugin-ui 0.3.1).
   A plugin-ui bump therefore (i) moves gateway `src/benchweave` bytes (D11 forbids),
   (ii) forces the narrow-range slide and re-stamp of every 0.3.0 pin
   (`dependency_policy.standards."plugin-ui".note`, the D2-wall memory), and (iii) drags
   the renderer-adjacent validator through a corpus repin — all for a document that is
   pure data.
4. **Option (c) contradicts the corpus direction.** GOVERNANCE "Direction": standards land
   main-side first, flow outward via the exported bundle, consumed by revision-pinned
   locks — "Never SDK-first". An SDK-internal contract also cannot be consumed by another
   host, which is the point of writing the reference as data.

Admission mechanics (what Landing 1 physically does):

- New dir `standards/plugin-ui-class-reference/0.1.0/` with
  `class-reference.schema.json`, `class-logic_analyser.json`, and a short `README.md`
  prose companion (prose is not digest-pinned). File set follows `plugin-ui-preview`'s
  minimal shape (schemas + migration/prose as needed; no machine-written validation
  report — the report-writer families are otdp/registry/execution/interface, and
  `plugin-ui-preview` ships none).
- `standards/standards-manifest.json`: a new admission entry (`id`, `version: "0.1.0"`,
  `status: "stable"`, `released`, `supersedes: null`, `normative` list) plus a founding
  `dependency_policy.standards."plugin-ui-class-reference"` block
  (`range: ">=0.1.0,<0.2.0"`, empty yank/retire). The policy block is governance data in
  the same family as `sdk_compatibility` (G-3 posture); the founding range is part of the
  admission, not a later range change.
- `standards/corpus-manifest.json`: founding rows cite the authoring path as `source`
  (the founding-family convention — e.g. `plugin-ui-preview/0.1.0/*` rows cite
  `docs/plugin-ui-preview-v1/…`). Bytes are staged at the authoring path on the branch,
  digests written **only** by `benchweave.standards repin` (CON-7), staging removed in
  the same PR (provenance lives in git history + the `source` field — the founding
  families' own shape: their `docs/…-v*` authoring paths no longer exist in-tree).
- Identity block: **no change** — CON-8's closed-world enumeration requires only
  otdp/registry/execution/interface; plugin-ui and plugin-ui-preview sit outside it, and
  the new family joins them there.
- Cross-constraints (`standards/cross-constraints.json`): **no row in this increment.**
  The reference carries its plugin-ui target inside the document (§2) and the expander
  enforces it; a resolve-time cross-constraint row is vacuous while plugin-ui serves a
  single version. Deferred (D-6 in §8).
- Standards-governor mandate applies (any `standards/` touch); the compatibility matrix
  and website stamps regenerate from the manifest by their own mechanisms (CON-12/CON-13)
  — verified by `matrix --check` and the site assembly in CI, never hand-swept.

## 2. The reference document (schema + logic_analyser content)

### 2.1 Design rules the schema enforces

- **Structure, not data (D2 / A02).** The reference may author STRUCTURAL strings (page
  ids/titles, binding id patterns, the group label pattern, slot names) and STRUCTURAL
  numbers (group size 8, the 64-lane ceiling it inherits from plugin-ui, pattern arity).
  It may NOT author data: no values, units, thresholds, voltage or rate limits, channel
  names, or parameter names. Every one of those resolves at expansion time from the
  descriptor or the OTDP action schemas. The schema makes this partly structural: no
  field in the reference vocabulary has a data-bearing shape (no `default`, no `value`,
  no `unit`, no numeric bound fields beyond the structural trio above).
- **Layout vocabulary == what plugin-ui 0.3.1 can carry (D12a).** The reference's page/
  plot vocabulary is exactly `ui-manifest.schema.json` 0.3.1's: page kinds
  (`configuration`, `readings`, `dataset`; `class_panel`/`custom_panel` exist in the
  schema but require a registered host panel id — D1: none exists, so the reference uses
  none), plot kinds (`digital_lanes`), `channel_hints` (visible-only on lanes),
  `lane_groups`, `decoder_lanes`, presets via `preset_asset_ids`.
  **Recipe vocabulary rolled IN (owner ruling 2026-10-14, supersedes the D-2
  deferral):** the gap between the §6.1 recipe vocabulary and what a manifest can
  carry closes IN THIS INCREMENT, through the family's namespaced layout block
  riding the plugin-ui 0.3.1 `extensions` seam — §2.6 carries the mechanism and the
  evidence that decides it. The workbench §6 clause ("Plugin-defined component
  recipes require a separately reviewed, versioned presentation-contract addition")
  is satisfied BY the family: `plugin-ui-class-reference` is the reviewed, versioned
  addition; no ungoverned extension field carries a component tree.
- **Colour carries nothing (D6).** The reference's lanes vocabulary has no colour
  concept at all (plugin-ui 0.3.1 already refuses `color_role` on `digital_lanes`
  hints — `ui-manifest.schema.json` `$defs.plot.allOf`, `not required color_role`;
  restated in prose by the plugin-ui README and contract §E.4).
- **Run-group safety (D7).** The reference's run-actions vocabulary has no confirm
  affordance: `arm`/`abort` render as plain buttons. `abort` is the energy-removing
  action of the class (stops acquisition); `docs/internal/ui-contract.md` §C.1
  R-DEENERGISE-1: "An energy-removing action … is one action, never confirmed, never
  gated. Nothing in the presentation may stand between the operator and de-energising
  (decision A04)." `arm` is not energy-sourcing under §C.1's definition (it closes no
  energy path to the DUT — it prepares acquisition), so it takes no `confirm-action`
  either. The reference schema has no field that could put a confirm on a run action,
  and the gate's `forbid` list asserts it in the render (§5).

### 2.2 Reference document schema (`class-reference.schema.json`)

```
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://benchweave.dev/contracts/plugin-ui-class-reference/0.1.0/class-reference.schema.json",
  "type": "object", "additionalProperties": false,
  "required": ["contract_version", "profile_id", "title", "targets", "slots", "pages",
               "expect", "cannot_derive"],
  "properties": {
    "contract_version": {"const": "0.1.0"},
    "profile_id": {"$ref": "#/$defs/profile_id"},       // e.g. "otdp.logic_analyser/1.0.0"
    "title": {"type": "string"},
    "targets": {                                          // the vocabulary this reference speaks
      "type": "object", "additionalProperties": false, "required": ["plugin_ui"],
      "properties": {"plugin_ui": {"type": "string", "pattern": "^>=?[0-9]"}}   // ">=0.3.1"
    },
    "slots": {                                            // derivation inputs, keyed by role
      "type": "object",
      "additionalProperties": {"$ref": "#/$defs/slot"}
    },
    "pages": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/page_template"}},
    "expect": {"$ref": "#/$defs/expect"},
    "cannot_derive": {"type": "array", "items": {"$ref": "#/$defs/cannot_derive"}}
  },
  "$defs": {
    "profile_id":  {"type": "string", "pattern": "^otdp\\.[a-z_]+/[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "action_urn":  {"type": "string", "pattern": "^otdp\\.[a-z_]+\\.[a-z_]+/[0-9]+\\.[0-9]+\\.[0-9]+$"},
    "slot": { "oneOf": [
      { "type": "object", "additionalProperties": false, "required": ["kind"],
        "properties": {
          "kind": {"const": "channels"},
          "where_role": {"type": "string"},              // "digital_input"
          "key": {"const": "id"}, "label": {"const": "label"} } },
      { "type": "object", "additionalProperties": false, "required": ["kind", "action"],
        "properties": {
          "kind": {"enum": ["dataset", "configuration", "procedure"]},
          "action": {"$ref": "#/$defs/action_urn"},
          "when_declared": {"type": "boolean"},           // optional-slot switch (default false)
          "schema_source": {"enum": ["input_schema", "output_measurement"]},
          "variables": {"type": "object"},               // per-slot variable template (below)
          "host_supplied": {"type": "array",             // D13: input field names the HOST
            "items": {"type": "string"}}                 // owns (acquisition_id, active
                                                         // configuration_id) — structural
        } },
      { "type": "object", "additionalProperties": false, "required": ["kind"],
        "properties": {"kind": {"const": "vendor_actions"}}
                                                        // D14: every declared action URN
                                                        // not claimed by a named slot (§2.5)
        }
    ]},
    "page_template": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "title", "kind", "binding_slots"],
      "properties": {
        "id": {"type": "string"}, "title": {"type": "string"},
        "kind": {"enum": ["configuration", "readings", "dataset"]},
        "binding_slots": {"type": "array", "items": {"type": "string"}},   // slot keys
        "vendor_features": {"type": "boolean"},          // D14: this page hosts the
                                                         // Device-features section (§2.5)
        "plot": { "type": "object", "additionalProperties": false,
          "required": ["kind", "over_slot"],
          "properties": {
            "kind": {"const": "digital_lanes"},
            "over_slot": {"type": "string"},               // the dataset slot
            "group_size": {"const": 8},
            "group_label_pattern": {"const": "D{first}-D{last}"},
            "group_radix": {"enum": ["hex", "decimal"]} } } } },
    "expect": {
      "type": "object", "additionalProperties": false,
      "required": ["components"],
      "properties": {
        "components": { "type": "object",
          "additionalProperties": {"$ref": "#/$defs/component_expect"} },
        "controls": {"type": "object",                    // D14: per-action reachability
          "additionalProperties": {"enum": ["button", "staging", "preset",
                                            "deviation"]} },
        "forbid": {"type": "array", "items": {"type": "string"}} } },
    "component_expect": {
      "type": "object", "additionalProperties": false,
      "required": ["count"],
      "properties": {
        "count": {"type": ["string", "integer"]},          // integer or an expression (§3.4)
        "attribute": {"type": "object"},                   // {"data-bw-lane-kind": "channel"}: expr
        "per_page": {"type": "string"},
        "must_not_be_wrapped_by": {"type": "array", "items": {"type": "string"}} } },
    "cannot_derive": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "aspect", "reason", "author_action"],
      "properties": {
        "id": {"type": "string"},
        "aspect": {"type": "string"},                      // "safe threshold range", ...
        "reason": {"type": "string"},
        "author_action": {"type": "string"} } }            // where the author supplies it
      // note: array-of-this-object at the top level
    }
  }
}
```

(The committed schema is full JSON Schema with the closed-world discipline of the sibling
families — `additionalProperties: false` everywhere, limits on string lengths and array
sizes mirroring plugin-ui's own limit posture: 262,144-byte documents, 32 nesting levels.
The family ships a SECOND machine file, `layout.schema.json` — the namespaced layout
block's vocabulary, §2.6.)

### 2.3 The logic_analyser reference (content sketch — the committed file is normative)

Slots:

| key | kind | resolves |
|---|---|---|
| `lanes` | `channels`, `where_role: digital_input` | ordered lane list from `descriptor.channels[]` |
| `capture` | `dataset`, action `otdp.logic_analyser.fetch/1.0.0`, `schema_source: output_measurement` | the fetch dataset: `x` = the regular-axis time variable (number, unit `s`, vector, `axis_role: x`), one `logic`-alphabet lane variable per resolved channel |
| `configure` | `configuration`, action `otdp.logic_analyser.configure/1.0.0`, `schema_source: input_schema` | settings schema = the action's input schema; fields `configuration_id`, `channels[{channel, threshold_v}]`, `sample_rate_hz`, `sample_count`, `trigger{...}` |
| `arm`, `abort` | `procedure` (required-class) | run buttons on the capture page |
| `trigger` | `procedure`, `when_declared: true` | software-trigger button, present only when the descriptor declares the optional action |
| `decode` | `dataset`, action `otdp.logic_analyser.decode/1.0.0`, `when_declared: true` | decoder lanes (the `decoder_lanes` plot array), one per descriptor-pinned decoder whose `channel_map` line roles resolve to declared channels |

Pages:

1. **Capture** (`kind: dataset`, binding_slots `[capture, arm, abort, trigger?]`,
   `plot: digital_lanes over capture, group_size 8, group_label_pattern D{first}-D{last},
   radix hex`) — the waveform-first capture view (#449 F8's host-side page, now grounded).
2. **Configuration** (`kind: configuration`, binding_slots `[configure]`) — schema-driven
   form + preset wiring (`preset_asset_ids: []` at birth — presets are commissioned
   evidence, `cannot_derive`).

`expect.components` (expressions resolved numerically by the expander, §3.4):

| component | count | attribute counts |
|---|---|---|
| `digital-lanes` | `1` on the capture page | lanes with `data-bw-lane-kind=channel`: `{n_lanes}`; `=group`: `{n_groups}`; `=decoder`: `{n_decoders}` |
| `button` | `{n_run_actions}` on the capture page (arm + abort + trigger?) | — |
| `numeric-input` | `{n_configure_fields}` on the configuration page | — |
| `panel` | `{n_pages}` | — |
| `mode-banner` | `1` per page (preview honesty marking, contract §D) | — |

`forbid`: `confirm-action` wrapping any run-action button (D7); any `color_role` hint on a
`digital_lanes` channel (belt over the schema's own refusal); any lane label not traceable
to the descriptor or the group pattern.

`cannot_derive` (printed by the expander into its output AND the generated AI-GUIDE — D8):

| id | aspect | reason | author_action |
|---|---|---|---|
| `thresholds` | safe `threshold_v` range for the logic family | a class reference cannot know a bench's acceptable thresholds (A02: qualification is per bench) | constrain the settings schema (`input_constraints`) on the descriptor |
| `arm-safety` | safe trigger/arm sequencing | device- and DUT-specific; the reference binds the buttons, not the sequence | procedure/policy at commissioning; AI-GUIDE notes |
| `lane-names` | lane names beyond descriptor labels | the descriptor owns channel identity | label channels in the descriptor |
| `presets` | preset settings values | presets are commissioned evidence, never derived | author `ui/presets/*.json` via check-preset |
| `decode-settings` | decode options beyond the closed unions | the closed trio unions are the contract; anything else is a named extension | descriptor `decoders[]` declarations |

### 2.4 D13 — Effective capability, not catalogue

The expander never offers what the device does not admit. For every action, the
**effective schema** = OTDP catalogue `input_schema` ∧ descriptor
`input_constraints` ∧ bench policy **where available at preview**:

- The descriptor schema types `input_constraints` as a FREE-FORM object
  (`otdp-device-descriptor.schema.json` `properties.actions.additionalProperties.
  properties.input_constraints` = `{"type": "object"}` — verified), so the expander
  owns a **closed intersection vocabulary** applied per property: `type` (within the
  same JSON type family), `enum`, `const`, `minimum`/`maximum`/
  `exclusiveMinimum`/`exclusiveMaximum`, `multipleOf`. A constraint fragment using
  anything else refuses `classref_constraint_unsupported:` naming action and field —
  degrade loudly: silently DROPPING a constraint would offer a value the device does
  not admit, which is precisely the failure D13 exists to prevent.
- Enum options, bounds, steps and fixed values for rendered controls come from the
  intersection. A `const` renders a read-only fixed display, never an editable offer.
  Steps: neither catalogue nor constraints carry a step vocabulary — the host-derived
  step stays the host's own rule (the `staged_control_html` precedent derives step
  from the declared range; presentation granularity is host territory).
- Bench policy: the SDK standalone host has none (no commissioned policy exists at
  preview, and A02 forbids inventing one) — the intersection there is catalogue ∧
  constraints, DISCLOSED in the gate output. Where policy exists (gateway admission),
  it narrows further; the record names that seam without implementing it.
- Optional-action slots resolve on the actions the descriptor ACTUALLY declares
  (`when_declared`, §3.1) — the effective-capability statement of slot resolution.
- The same AND-wise composition the preset lane already applies at validation time
  (plugin-ui README, "Configuration presets": the canonical action input schema and
  the descriptor's input constraints apply AND-wise in both SDK lanes) is applied
  here at DERIVATION time, so the expander-materialised `ui/settings/*.schema.json`
  IS the effective schema and check-preset stays consistent by construction.

Multi-profile devices and the capability fixture pair are §3.8 and §3.5.

### 2.5 D14 — Coverage rule independent of class

Every key of `descriptor.actions` — any URN; the descriptor schema's actions map is
`additionalProperties` with no key pattern (verified) — must be **reachable through
a rendered control, or carry a declared deviation** (the D12c ledger). The rule binds
every plugin, with or without a class reference.

**Reachability ladder** (derived from the effective schema; the expander computes it,
the gate asserts it):

| level | condition | rendered control |
|---|---|---|
| L1 | no required inputs after removing `host_supplied` names | bare procedure `button` |
| L2 | required inputs all numeric | staging pair (`numeric-input` + rotary, the host staging precedent) + invoke button |
| L3 | configuration-shaped (`state_change`, complete-document nature) | preset selection + Apply (the sanctioned preset lane; the host's `preset_list`/`preset-apply` routes) |
| L4 | dataset (`side_effect: none`, dataset output) | dataset binding + plot/table |
| L0 | required inputs include types §E.1 cannot express, and no preset covers it | DECLARED deviation required; undeclared ⇒ gate fails |

`host_supplied` names the acquisition-lifecycle fields the OTDP model assigns to
host ownership — `acquisition_id` (arm/fetch/abort/trigger) and the active
`configuration_id` (arm). It is structural knowledge (field NAMES), not data —
D2-clean.

**The §E.1 inventory has no text-input, select or boolean component** (verified
census: button, numeric-input, rotary-control, reading-tile, alert-bubble,
engineering-plot, digital-lanes, data-table, panel, mode-banner, confirm-action).
That vocabulary gap is recorded as deferral D-10; closing it is a ui-contract §E
addition on the contract's own lane — NOT this increment (D4's no-renderer-change
line and D12d's §E-only rule both hold).

**Device features.** The `vendor_actions` slot resolves every declared action URN not
claimed by a named class slot — vendor profiles resolve from the descriptor's
digest-pinned catalogs (pinned vendor catalogs are admitted shape-wise at the
composition seam; the plugin-ui README's "pinned contract documents" clause). It
renders as a "Device features" page (`vendor_features: true`) composed of §E
components only, at each action's ladder level. The SDK derives this page even
WITHOUT a class reference — D14 binds every plugin; the reference may declare the
section's placement when one exists.

**Class-slice consequences (honest):** `configure` is L3 — its `configuration_id`
string, `channels` array and `trigger` object are inexpressible at L2 — so the
configuration page is preset-mediated with a declared deviation at birth (no
commissioned presets yet; `cannot_derive.presets`); `arm` is L2
(`max_duration_ms` numeric; ids host-supplied); `abort` and `trigger` are L1;
`fetch` is L4; `decode`'s invocation carries enum settings (inexpressible) — declared
deviation at birth — while its decoder LANES still render as capture-plot annotations
(declaration-level, not invocation).

**Frequency counter — deferred, with the promotion criterion (D-9).** Default lane
TODAY: vendor profile — a descriptor pins a vendor catalog carrying a
vendor-namespaced frequency-counter profile and action; D14 renders it in Device
features; no corpus motion. Promotion to a **dmm optional action**: evidence = at
least one real admitted plugin whose frequency surface's action I/O maps 1:1 onto
the dmm profile's scalar measurement model (scalar numeric observation, no new
dataset shape) — lands as an OTDP catalog revision with vectors. Promotion to a **new
class** `otdp.frequency_counter`: evidence = at least two independent real plugins
whose frequency surfaces DISAGREE on action shapes such that one profile cannot
express both (the A10 bounded-classes logic: classes are minted on demonstrated
divergence, not anticipation).

### 2.6 The layout vocabulary (D12a roll-in — the extension seam)

**Mechanism: the family's layout vocabulary rides the plugin-ui 0.3.1 `extensions`
seam as a namespaced, family-schema'd block — `plugin-ui-class-reference:layout` —
carried by plain 0.3.1 manifests today. No plugin-ui bump.** The evidence that
 decides it (verified, not assumed):

- **Option A (plugin-ui 0.4.0 carrying the vocabulary) is OUT on the owner's own
  bindings, by direct evidence.** The family's normative code row
  `src/benchweave/presentation/contracts.py` embeds the version literals
  (`SCHEMA_ROOT = "https://benchweave.dev/contracts/plugin-ui/0.3.1/"` line 20;
  `contract_version != "0.3.1"` guards lines 247 and 372) — a bump EDITS gateway
  `src/benchweave` bytes (D11 violated), re-stamps every carried pin through the
  single-serving wall, and any new layout validation would live in the same
  validator file. A bump also needs renderer consumption of the new vocabulary —
  a renderer change D4 forbids.
- **Option B's seam is real and verified.** `ui-manifest.schema.json` 0.3.1 admits
  `extensions` as a namespaced map (`patternProperties
  "^[a-z][a-z0-9.-]+:[a-z][a-z0-9._-]+$"`, value schema `{}`, `maxProperties: 64`),
  and the canonical validator is EXTENSION-BLIND: zero references to `extensions`
  in `contracts.py` (881 lines, verified) — a manifest carrying the block validates
  IDENTICALLY to one without it. The plugin-ui README names the seam's rule:
  "Fields are closed except explicitly namespaced manifest extensions."
- **Rendering without a renderer change (D4 holds).** The block composes ONLY
  §E.1 partials (panels, buttons, staging pairs, tiles, plots) — the ui-html
  package and its contract harness never change. Consumption is HOST composition:
  the SDK preview host (`benchweave_sdk_server` — SDK-side code) renders the block
  by grouping and ordering the partials it already renders; a host that does not
  know the namespace ignores the block and serves the manifest's plain pages —
  degrade-by-ignoring, never an error. The owner's stop-and-report fork resolves
  by evidence: the renderer CAN consume the vocabulary because the vocabulary was
  drawn from what the renderer already ships (§E.1's inventory), not from §6.1's
  full aspiration.
- **The block is the workbench §6 "separately reviewed, versioned
  presentation-contract addition":** its schema is a machine file of THIS family
  (`layout.schema.json`, corpus-pinned, versioned `0.1.0` with the family),
  reviewed through the same governor lane as the rest — governed where the
  ungoverned extension field is refused.

**The vocabulary** (family `layout.schema.json`; closed world, §6.1's prohibitions
schema-enforced — no JavaScript, templates, arbitrary HTML/CSS, external URLs,
credentials, polling or raw commands; bounded: ≤64 nodes per page, depth ≤3,
grid spans ≤12, text ≤512 characters):

```
layout            := { "contract_version": "0.1.0", "pages": [layout_page] }
layout_page       := { "page_id": <must match a manifest page id>, "sections": [section] }
section           := { "id", "title"?, "surface": "raised"|"recessed", "children": [node] }
node              := section | control | text | reading | plot_ref
control           := { "binding_id": <a manifest binding on this page>,
                       "kind": "button"|"numeric"|"rotary",
                       "field"?: <an input field of the binding's action> }
text              := { "body": ≤512 chars }          // AUTHOR capability only —
                                                  // the class reference authors
                                                  // none (D2: structure, not data)
reading           := { "binding_id": ..., "kind": "reading-tile"|"data-table" }
plot_ref          := { "plot_index": <a plot of this page> }   // orders/places the
                                                  // page's declared plot
```

The component kinds map 1:1 onto the §E.1 inventory (panel, button, numeric-input,
rotary-control, reading-tile, data-table, engineering-plot, digital-lanes); grid
placement is host CSS-grid composition of panels (the styleguide's own layout
rule), not a new component. §6.1 items with NO §E.1 component — tabs, splits,
sliders, switches, selectors, keypads, text inputs — stay OUT of the vocabulary
(their absence is structural: §E.1 ships no such component; row-call D-10).

**D12a parity holds by construction:** the reference's layout sections and a
hand-authored block are the SAME vocabulary under the SAME family schema — one
vocabulary, two writers, identical validation (A11). The reference's layouts
carry structure only (panels, controls, binding and field references); `text`
nodes are the author's (overlay or hand-written), never the reference's.

**The honest gap, row-called (D-11):** the GATEWAY production host is as
  extension-blind as the validator — it will ignore the block until gateway-side
  consumption work lands. That work is structurally excluded from THIS increment
  by D11 itself (no `src/benchweave` change); it is a row-call, not a silent cut.

## 3. Expansion semantics (SDK side)

### 3.1 Slot resolution

- **Lanes** — `descriptor.channels[]` where `role == "digital_input"`, in descriptor
  declaration order. **Lane identity is position** (contract §E.4.1; plugin-ui README):
  the lane's `data-bw-lane` index is its declared position, never renumbered.
- **Lane variables** — one variable per resolved channel on the `capture` dataset target;
  variable id = channel id (catalogue `variables[]`, `shape: vector`); the `x` variable
  names the dataset's regular axis per the plugin-ui README's authoring rule
  (t_i = start + i·step).
- **Actions** — required-class actions (`configure`, `arm`, `fetch`, `abort` — verified
  against `standards/otdp/0.2.3/device-profile-catalog.json`
  `profiles["otdp.logic_analyser/1.0.0"].required_actions`) must be declared by the
  descriptor; optional actions (`trigger`, `decode`, `decode_annotated`,
  `optional_actions` in the same row) bind only when declared (`when_declared`).
- **Bindings/catalogue targets** — per `ui-manifest.schema.json` `$defs.target`:
  dataset target (`action_id`, `profile_ids`, `measurement_schema_id` = the descriptor's
  pinned `urn:otdp:measurement:…`, `variables`); configuration target (`action_id`,
  `profile_ids`, `input_schema_id` = the action URN's `:input` `$id`,
  `schema_asset_id` = `ui/settings/configure.schema.json` — materialised by the expander
  as the action's input schema, `preset_asset_ids: []`); procedure targets
  (`action_id`, `profile_ids`, `input_schema_id`).
- **Decoder lanes** — only under `when_declared`: one decoder lane per descriptor-pinned
  decoder declaration whose line roles resolve to declared channels; `binding_id` names
  the decode dataset binding on the same page (the other-action rule the validator
  enforces).

### 3.2 Chunking rule (D6)

Groups of **8 consecutive lanes**; the last partial group is allowed; a trailing remainder
of **exactly 1** lane forms **no group** (plugin-ui `lane_group.member_ids` `minItems: 2`
— a one-member group is schema-impossible; the lone lane stays an ungrouped channel
lane). Group id `lanes-{k}` (k from 1); label `D{first}–D{last}` over 1-based positional
numbers; `radix: "hex"` (default); `member_ids` = the channel ids in declaration order,
**first declared member = LSB** (contract §E.4.3); `default_collapsed` is NOT set by the
reference (a host-collapse preference is author territory, overlay-writable).

### 3.3 Fail-closed cases (typed refusals, snake_case per STD-4)

| condition | refusal prefix |
|---|---|
| 0 channels with `role=digital_input` | `classref_no_lanes:` |
| >64 such channels (plugin-ui `y.maxItems: 64` for `digital_lanes`) | `classref_lane_ceiling:` |
| descriptor missing a required-class action | `classref_required_action_absent:` (names the URN) |
| reference document naming an action URN absent from the served OTDP catalog | `classref_unknown_action:` |
| active plugin-ui version below `targets.plugin_ui` | `classref_target_version:` |
| reference document failing its own schema | `classref_invalid_reference:` |
| descriptor failing `validate_descriptor` | existing validator findings (unchanged lane) |

### 3.4 Expect resolution

The expander evaluates the reference's `expect` expressions over the resolved slot
inventory (`n_lanes`, `n_groups = floor(n_lanes/8) + (1 if 2 <= n_lanes mod 8 else 0)`,
`n_decoders`, `n_run_actions`, `n_configure_fields` = required+optional properties of the
configure input schema, `n_pages`) and emits a **numeric expectation document** — the
gate's assertion input. Expression vocabulary is closed (the six names above, integer
literals, `+`); anything else refuses `classref_expect_expression:`.

### 3.5 D2 proof plan

A second invented descriptor — fixture family "d-series" (`d0`..`d33`, labels
`Data line 0`…, invented vendor "Veridian LA-32", 34 channels: four full groups + a
two-lane remainder) — expands and validates through the canonical validator
(`validate_presentation` → `valid=true`), and:

- the **structural** strings of both expansions (page ids/titles, binding ids, group
  label pattern instantiations `D1–D8`…`D33–D34`) are identical in shape;
- the **data** strings differ exactly where the descriptors differ (channel ids, labels);
- a test asserts the manifest's data-string set is a subset of descriptor ∪
  action-schema strings (no reference-authored data), and that the reference document
  itself contains no numeric literals outside the structural trio (8, 64, pattern arity)
  — grep-level, machine-checked.

**Fixture plan under D13/D14 (attribution isolation).** D2 varies NAMES holding
capability fixed; D13 varies CAPABILITY holding the class fixed. One fixture cannot
serve both proofs without confounding attribution — a failure could be name-caused
or capability-caused. The plan is therefore FOUR descriptors over THREE proof axes:
F1 (2-channel, class-shaped — the A1 primary), F2 (the **32-channel d-series rename
`d0`..`d31`** — the task's named fixture, kept exactly; the D2 proof: 4 full groups,
zero remainder), F3a narrow (fixed `threshold_v` via `const`, single-value
`sample_rate_hz` enum, no optional actions) and F3b programmable (bounded
`threshold_v` range, `sample_rate_hz` bounds, `trigger` + `decode` declared) — the
D13 pair; **F3b runs 34 channels (`d0`..`d33`) and carries the partial-group arm
(`D33–D34`)**, so the remainder arithmetic is covered on the capability axis without
touching the task's named 32-channel fixture. A fifth fixture — a vendor action
(invented `com.veridian-labs.auto-threshold/1.0.0` through a pinned vendor-catalog
fixture) — serves A10's Device-features arm; a sixth — a hand-authored
layout-bearing manifest — serves A11's parity arm.

### 3.6 Version stamping (D4)

All three generated documents (`ui/manifest.json`, `presentation.json`,
`binding-catalogue.json`) stamp `active_version("plugin-ui")` — the derived-never-stated
rule `create_ui_resources` already follows (`benchweave-sdk/src/benchweave_sdk/
presentation.py`). No renderer change is needed or made: the preview host already renders
`digital_lanes` plots through `benchweave_ui_html.lanes.compose_lanes` +
`partials.render_lanes` (`benchweave-sdk/src/benchweave_sdk_server/plots.py` — "the host
authors no lane markup"). **If implementation discovers a renderer gap, work stops and
reports** (the dispatch's stop condition; nothing found in evidence — the declaration-only
lanes render exists at ui-html 0.2.1).

### 3.7 Effective-schema intersection (D13) — designed against the real mechanism

**Where `input_constraints` actually live and what they carry (verified):** the
descriptor's per-action `input_constraints` fragments are FULL JSON-Schema objects
applied CONJUNCTIVELY — the gateway checks "the input validates against the action's
catalog input schema, and the input also satisfies your descriptor's
`input_constraints` narrowing" (`docs/device-developer-guide.md`, the invoke gate),
and both SDK preset lanes apply the same AND-wise composition (plugin-ui README).
Real in-tree shapes: `fixtures/execution/descriptor-sim-psu.json` narrows
`otdp.dc_psu.configure/1.0.0` with `properties` carrying `minimum`/`maximum`/
`exclusiveMinimum`/`pattern` (`^ch1$`)/`type`, plus a top-level `required` list —
not the empty `{}` the class example shows. The class fixture's emptiness is the
UNNARROWED case, not the mechanism.

**Consequence for the design — the expander does not merge schemas for validation
(validation already composes AND-wise in the existing lanes); it derives the
EFFECTIVE ADMITTANCE per rendered field, for control derivation only:**

- Numeric fields (`number`/`integer`): intersect the bounds family
  (`minimum`/`maximum`/`exclusiveMinimum`/`exclusiveMaximum`/`multipleOf`,
  type-within-family) — a numeric control is emitted whose `min`/`max`/`step` are
  the intersection; every value the control can submit is admittED by both
  schemas. `const` → read-only fixed display (never an editable offer).
- `enum` → fixed option set from the intersection.
- `pattern` → renderable ONLY when the admitted set is finite and enumerable
  (a literal alternation `^(a|b|c)$` derives fixed options; any other pattern —
  `^ch1$` narrows to one value, so `^ch1\d+$` shapes — marks the field
  INEXPRESSIBLE: a free control cannot guarantee admittance, and offering one
  would violate D13's rule). An inexpressible required field drops the action to
  L0 (declared deviation) while the existing validation lanes still enforce the
  constraint — nothing is silently unenforced.
- Array/object constraints (`items`, `minItems`, `uniqueItems`) and `required`
  additions do not derive form controls; they ride the existing conjunctive
  validation untouched. The ladder's "no required inputs" test uses
  catalogue-required ∪ constraints-required.
- Unknown keywords outside this vocabulary refuse
  `classref_constraint_unsupported:` (same loud-degrade rule — dropping a
  constraint would offer an unadmitted value).

Fail-closed cases (typed, joining §3.3's table):

| condition | refusal prefix |
|---|---|
| a constraint narrows a field to a different JSON type family than the catalogue's | `classref_effective_schema_conflict:` (names action + field + both types) |
| a REQUIRED field's enum/bounds narrow to an empty admittance set | `classref_effective_schema_empty:` (names action + field) |
| constraint keywords outside the closed vocabulary | `classref_constraint_unsupported:` (names action + field + keyword) |

The expander-materialised `ui/settings/*.schema.json` stays the constraints-derived
effective document, so check-preset's AND-wise lane enforces exactly what the forms
offered.

### 3.8 Multi-profile merge (D13)

A device claiming several profiles gets the MERGED references under ONE ownership
domain: one manifest, one envelope, one `plugin_id`, one descriptor hash (A03's
single-ownership rule; workbench-design §2 — "Separate profile names never permit
independent clients to drive the same underlying hardware concurrently" — mirrored
at the presentation layer: one presentation document per device). Deterministic
merge: profile ids sorted bytewise; the FIRST reference keeps bare page ids; every
subsequent reference's page ids are prefixed `{profile_slug}-`; binding ids derive
from the action URN slug (unique by namespacing) and prefix on collision. Two
references claiming the SAME action URN through different named slots refuse
`classref_profile_slot_conflict:`. A profile with no reference yet contributes only
the D14 vendor-actions lane — its actions stay covered.

### 3.9 Coverage derivation (D14)

The expander emits a per-action control plan (action URN → ladder level) into the
expectation document. The reference's `expect.controls` declares the INTENDED level
per class action; a divergence between intended and derived (a constraint made a
field inexpressible, an action absent) is a REPORTED deviation requiring declaration —
the same D12c ledger, one mechanism. The gate's coverage arm consumes the plan
(§5.1).

## 4. D12b — overlay file with deterministic composition

**Choice: derived core + author overlay, composed by the expander.** Not a stored-base
three-way merge.

Precedent and justification:

- The scaffold_update precedent (`benchweave-sdk/src/benchweave_sdk/scaffold_update.py`)
  is copier's `run_update` over *template* files with git history, protected-file
  restore, and conflicts reported never resolved. Adapting it here would require a
  **JSON three-way merge engine** — new architecture with no in-tree precedent
  (principle 9), for a document that is deterministically regenerable from
  (descriptor, reference). The overlay composition gets the same guarantees
  deterministically.

Mechanics:

- `ui/manifest.json` — **derived, wholesale**, never hand-edited. The expander refuses to
  overwrite a `manifest.json` that differs from its own last composed output unless
  `--force` (the `upgrade_dirty_tree` posture: refuse loudly, point at the overlay).
- `ui/manifest.overrides.json` — **author-owned, never written by the expander**.
  Vocabulary = the same manifest vocabulary an author can hand-write (pages, bindings,
  plots, channel_hints — D12a): overlay rows merge by stable id (a page row with id X
  deep-merges into derived page X; overlay-only ids append). The overlay cannot delete
  derived rows (`overlay_delete_refused:`) and cannot touch `contract_version`,
  `plugin_id`, `descriptor_sha256` (`overlay_immutable_field:`). The composed manifest
  must pass the canonical validator — an overlay that breaks it is refused with the
  validator's findings.
- `ui/class-reference.json` — **author-owned conformance declaration**: the reference
  the project follows (`profile_id` + family version) and the declared-deviation ledger
  `deviations: [{expectation_id, reason}]` (D12c). An `expectation_id` outside the
  reference's expect vocabulary refuses (`classref_unknown_expectation:` — an unknown id
  cannot launder a divergence); a declared deviation downgrades exactly that
  expectation's failure to a REPORTED row in the gate output; undeclared divergence
  FAILS.
- The overlay and declaration files are authoring state that ships inert in the wheel
  (undeclared in manifest `assets`, read only by the expander) — disclosed here and in
  UI-GUIDE.

RED proof for D12b: author overlay renames a page title and adds a channel hint;
re-derive preserves both (against the current behaviour — regeneration destroying author
edits — which is the measured today-posture).

## 5. Gate method (D5)

`benchweave-sdk verify-ui <project>` (name free at SDK v0.12.0):

1. **Validate**: existing `check_ui` lane (envelope/manifest/catalogue/resources through
   the vendored plugin-ui validator).
2. **Derive**: expand(descriptor, reference) + overlay → documents + the numeric
   expectation document (§3.4).
3. **Render**: build the standalone host's app in-process
   (`benchweave_sdk_server.web.build_app`) and drive it over an ASGI transport (httpx —
   already a test dependency; no subprocess, no port). The host pins
   `benchweave-ui-html==0.2.1` via the `[server]` extra (`pyproject.toml`), so the render
   runs on the pinned ui-html by construction. `GET /pages/{page_id}` for every derived
   page.
4. **Census**: parse the served HTML (stdlib `html.parser`; no new dependency) counting
   components by **contract-pinned surfaces only** — §E.1 class hooks (`bw-lanes`,
   `bw-lanes__lane`, `bw-button`, `bw-numeric`, `bw-panel`, `bw-confirm`) and
   data-attributes (`data-bw-lane`, `data-bw-lane-kind`, `data-variant`, `aria-label`) —
   the same surfaces the ui-html contract harness pins, never template internals
   (risk R1 mitigation).
5. **Assert**: numeric `expect` per page; `forbid` checks (zero `bw-confirm` ancestors of
   any run-action button; lane labels traceable); deviation ledger applied (§4);
   undeclared divergence FAILs with census-vs-expect deltas. **Layout arm (§2.6):** the
   `plugin-ui-class-reference:layout` block, when present, is validated against the
   family's `layout.schema.json` (a block failing the family schema refuses
   `classref_layout_invalid:` — the canonical validator is extension-blind, so the
   FAMILY schema is the block's only authority); the census then asserts the composed
   grouping (the Run group's `bw-panel` contains the arm and abort `bw-button`s in
   declaration order — DOM-order assertion, not just counts). **Extension-blindness
   control:** a layout-bearing manifest passes the gateway-vendored canonical validator
   UNCHANGED — pinned by a test, because it is the load-bearing fact the whole seam
   rests on.
6. **Exit**: 0 clean; non-zero with typed findings (`classref_gate_missing:`,
   `classref_gate_excess:`, `classref_gate_forbidden:`, `classref_gate_undeclared:`,
   `classref_gate_uncovered:`).

### 5.1 The coverage arm (D14 — always on)

Independent of class matching, the gate enumerates every key of
`descriptor.actions` and asserts, per action: a rendered control at its ladder level
(§2.5) OR a declared deviation in `ui/class-reference.json`. Neither present ⇒
`classref_gate_uncovered:` naming the URN. Placement: the `verify-ui` command, plus
the generated project test scaffold wires it into a plugin's own CI (the
`_write_preview_examples` conformance-test precedent), so coverage is checked where
the plugin lives, not only where the SDK lives.

**Baselines under D14 (stated expected outcomes):**

- The fresh scalar scaffold (no class reference; its descriptor declares no
  invoke-class actions): coverage PASSES — nothing declared beyond L1-reachable
  actions; the class-expect arm skips. The gate does not invent obligations the
  descriptor does not create.
- The banked class baseline fixture: coverage FAILS ADDITIONALLY (arm, abort,
  configure, fetch, decode all unreachable in the hand-minimal manifest) — A4's
  finding count rises accordingly.

**RED control (pre-committed):** the gate FAILS on the banked baseline fixture — a
hand-minimal manifest of the two-channel class descriptor reproducing today's posture
(one `time_series` plot, no lanes, no configuration page, no arm/abort) — with findings
naming every missing component. The baseline facts are the task's measured ones; the
fixture is synthetic (invented names) and committed under the SDK tests.

## 6. Acceptance rules (pre-committed, with denominators and both kill directions)

Deterministic census assertions; the "sample" is the fixed fixture set (F1/F2/F3a/F3b
expansion descriptors + 4 refusal fixtures + the baseline fixture + the overlay
fixture + the vendor-catalog fixture + the hand-authored layout manifest — §3.5).
Every rule was written before any gate output existed; A9–A11 arrived with the
D13/D14 and vocabulary folds, still before any gate output existed.

| # | rule (ship if) | kill if |
|---|---|---|
| A1 | 2-channel class descriptor: `validate_presentation` valid; gate PASS; census **2/2** channel lanes, **1/1** group lane (`D1–D2`), **0** decoder lanes, run buttons **2/2** (abort L1 bare, arm L2 with **≥1** `numeric-input` for `max_duration_ms`), configuration page preset-mediated with its birth deviation REPORTED, **0** forbidden components | any count off, or validation fails |
| A2 | 32-channel d-series descriptor (`d0`..`d31`, the task's named fixture): valid; gate PASS; **32/32** channel lanes, **4/4** full groups, **0** remainder groups, data-string trace clean (§3.5) | any reference-authored data string found, or expansion fails |
| A3 | refusal fixtures all RED with their typed prefixes (§3.3): **4/4** | any fixture expands instead of refusing |
| A4 | gate FAILS on the banked baseline fixture with ≥6 findings (lanes, group, configuration page, run buttons, plus the D14 coverage findings for the unreachable actions) | gate passes the baseline (it proves nothing) |
| A5 | overlay fixture survives re-derive: **2/2** overlay effects present after regeneration; composed manifest valid | either effect lost, or composed manifest invalid |
| A6 | deviation ledger: declared id downgrades **1/1** failure to REPORTED; undeclared divergence still FAILS; unknown id refused **1/1** | any undeclared divergence passes, or an unknown id is accepted |
| A7 | all generated documents stamp `active_version("plugin-ui")` — **3/3** equal, no literal | any hardcoded version |
| A8 | Landing 3: the pattern-library class page exports in **2/2** themes; screenshot count increases by the recorded per-entry number | either theme missing |
| A9 | D13 pair: F3a (narrow) — `threshold_v` renders as a fixed read-only display (**0** numeric-inputs for it), **0** trigger button, **0** decoder lanes, gate PASS; F3b (programmable, 34 channels) — bounded numeric-inputs whose asserted min/max EQUAL the fixture's constraint values (bounds from the intersection), trigger button **1/1**, decoder lanes per pinned decoder, **1/1** partial group `D33–D34`; the two manifests' inventories differ exactly on the capability-derived controls | any bound not matching the constraint bytes, or a narrow-only control appearing in F3b (or vice versa) |
| A10 | D14 coverage: class fixture **7/7** actions covered (**5** rendered + **2** declared: configure-preset-deviation, decode-enum-deviation), gate PASS with both REPORTED; deleting the decode declaration ⇒ FAIL (`classref_gate_uncovered:`); the vendor-action fixture renders in Device features at its ladder level and is covered; the scalar scaffold: coverage PASSES, class arm skips | any undeclared action passing, or a declared one still failing |
| A11 | Layout parity and render (§2.6): a HAND-AUTHORED layout-bearing manifest (fixture) and the EXPANDED manifest both validate **identically** — canonical validator `valid=true` for both (extension-blindness) AND family `layout.schema.json` `valid=true` for both; the SDK host renders the block — census asserts the Run-group `bw-panel` contains arm+abort buttons in declaration order (DOM order, not count alone); a layout block naming a page id absent from the manifest refuses `classref_layout_invalid:` | either writer validating where the other fails (parity break), or the composed order differing from the declared order |

Underpowered rather than conclusive: if the census cannot be keyed on contract-pinned
surfaces (parser cannot resolve a §E.1 surface the render actually emits), the gate's
expect vocabulary needs redesign — that is a measurement-instrument failure, reported,
not a pass/fail on the increment.

## 7. Three-landing sequence

**Landing 1 — gateway main: the standard.** Family dir + schemas + reference +
README — now TWO machine schemas (`class-reference.schema.json` and
`layout.schema.json`, the D12a roll-in) + the `class-logic_analyser.json` reference
+ README; standards-manifest admission entry + founding dependency_policy block; corpus
rows via repin; this design record. Governor review + Tier 3. No `src/benchweave`
bytes. CI: existing standards suites cover the new rows (coverage is both-directions fail-closed
per repin); matrix/site stamps regenerate mechanically.

**Landing 2 — SDK: expander + gate + docs + release.** `sync-standards` ingests the new
family into the vendored tree + lock (the sync machinery derives families from the
manifest; **build-time verification:** if any SDK surface enumerates families, the row is
added in the same change). New module (expander + overlay composer + gate + census
parser), CLI `derive-ui` / `verify-ui`, the fixture set and acceptance tests (A1–A10),
AI-GUIDE/UI-GUIDE `cannot_derive` text (D8). D13/D14 mechanisms land here: the
effective-schema intersection (§3.7) with its fail-closed cases, the reachability
ladder and per-action control plan (§3.9), the multi-profile merge (§3.8), the
Device-features derivation (§2.5), the gate's always-on coverage arm wired into
the generated project test (§5.1), the expander's emission of the
`plugin-ui-class-reference:layout` block and the preview host's consumption of it
(§2.6 — host composition of existing §E.1 partials; the ui-html package and the
canonical validator are untouched, and the extension-blindness control is pinned by
a test), and the A11 layout-parity fixture. The fixture set grows to F1/F2/F3a/F3b
plus the vendor-catalog and hand-authored-layout fixtures (§3.5). SDK release cut
(`make release-cut`) so the gateway pointer advances to a tag. The SDK PR body notes
the gateway issue (single stream).

**Landing 3 — gateway: pointer advance + pattern-library page + docs.** Submodule
gitlink + `.gitmodules` pin advanced in one commit (`sdk-drift` lane shape); the
pattern-library **capture-page composition** for the analyser class (#462 row 2 —
composed from the existing §E.1 components, host-owned, no new contract rows); the
mockup's analyzer composition (#462 row 1); styleguide/workbench doc updates
(ui-styleguide.md composition note; **its "Plugin presentation" paragraph gains the
family-extension reconciliation** — the namespaced `plugin-ui-class-reference:layout`
block is the sanctioned, family-schema'd use of the extension seam, so the "do not
encode a private component tree in extension fields" guidance now names the one
governed exception; workbench-design stays historical-rationale).
A8 rides here.

## 8. Deferral table — OWNER ROW-CALLS (nothing defers by default)

**Process rule (owner, 2026-10-14):** every row below is a CANDIDATE the owner
decides — roll in or defer; nothing defers by default and nothing rolls in by
default. The numbered row-call list (what / structural reason or "effort only" /
recommendation) is returned to the tracker with this record; the owner's calls fold
back into this table before the design is final. The former D-2 (recipe vocabulary)
is REMOVED — the owner rolled it in (§2.6).

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D-1 | the other 11 OTDP classes' references (dc_psu first — it has the existing mockup) | follow-on issue (gateway #463 remains open for the class sweep; the sweep issue names dc_psu next) | this slice's gate PASSes on logic_analyser and lands (the train closing) |
| D-3 | host-owned analyser `class_panel` (D1) | follow-on issue | a registered host panel id exists (a panel admission lands in the gateway UI surface) |
| D-4 | gateway-side fallback for plugins shipping no manifest | follow-on issue (gateway) | a gateway G-team issue asking for the reference-derived default page |
| D-5 | decode-annotation overlay (`decode_annotated` spans beyond the closed trio) | follow-on issue | a descriptor pins a decoder declaration exercising the annotation form (an arrival on the registry) |
| D-6 | `cross-constraints.json` row for the family (plugin-ui floor) | documentation in the family README at the next family bump | plugin-ui's served range widens past one version (a plugin-ui bump landing) |
| D-7 | preset derivation (`preset_asset_ids` wiring) | follow-on issue | an author supplies a commissioned preset through check-preset (a published preset on the registry) |
| D-8 | #460 (upgrade artifact migration), #461 (venv symlink damage), #463 rows 3/7/8 | their own issues (already filed) | per those issues |
| D-9 | frequency-counter support | follow-on issue (OTDP catalog lane) | the first registry arrival of a plugin descriptor declaring a frequency-measurement action; the promotion criterion is §2.5's three-way rule (vendor-profile default; dmm-optional on 1:1 scalar-model evidence; new class on two-plugin divergence) |
| D-10 | §E.1 input vocabulary for non-numeric action fields (text input, select, boolean toggle) | follow-on issue (ui-contract §E lane — a contract addition, not this increment) | a D14 deviation ledger entry whose reason names an inexpressible field type arrives on the SDK tracker (the ledger itself is the observable surface) |
| D-11 | GATEWAY production-host consumption of the `plugin-ui-class-reference:layout` block (the SDK preview host renders it; the gateway host is extension-blind until this lands) | follow-on issue (gateway G-lane) | this slice's Landing 3 merges (the pointer advance + docs land, making the gateway consumption the only missing half) |

## 9. Review tier and Step-1 keyword scan (#254)

**Tier 3** — the maximum across the three landings, triggered by: Landing 1 touches
`standards/` (new family, corpus-manifest rows, standards-manifest) and adds JSON Schema
files (rubric rule 1); Landing 2 adds `sha256`/`hashlib`-bearing code and fixture bytes
(keyword rule); Landing 3 advances the `packages/sdk` submodule pointer (rule 7). Each
landing's own scan covers its own expected diff; all three are Tier 3.

Step-1 keyword scan over the **expected diff text** (all landings, docs and code
alike; estimates from the designed content — the review re-derives on the real diff):

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~35–45 | corpus rows (4), expander/tests (descriptor_sha256 throughout), design record |
| `hashlib` | ~3–5 | expander + tests |
| `protection` | ~2–4 | design record prose citing §C.1/A04 only; zero in code |
| `threading` | 0 | — |
| `asyncio` | 0 | gate client is sync httpx over ASGI |
| `subprocess` | 0 | in-process render |
| `migrate` | 0 | no state/format migration |
| `recovery` | 0 | — |

Standards-governor pass is mandatory on all three landings (any `standards/` or
submodule-pointer touch).

## 10. Top risks, each with its falsifier

- **R1 — expect-vocabulary couples to renderer internals.** Mitigated: census keys only
  on §E.1 contract surfaces (class hooks + data attributes), which the ui-html contract
  harness itself pins — a renderer change that moves them reddens the harness first.
  Falsified if the served HTML lacks a §E.1 surface the census needs (then the gate
  vocabulary is redesigned; A-rules declare this the underpowered branch).
- **R2 — version cascade through self-pinning lattices.** The new family has no code
  row, so plugin-ui's narrow-slide wall does not apply to it; but the reference targets
  plugin-ui semantics and every plugin-ui bump forces a family review. Mitigated by
  `targets.plugin_ui` + `classref_target_version:` refusal. Falsified if a plugin-ui
  bump lands vocabulary the reference silently mis-derives (A2's trace test must red).
- **R3 — ui-html pin drift (SDK gate vs gateway pattern page).** The SDK pins
  `benchweave-ui-html==0.2.1`; the Landing-3 composition ships in the next ui-html
  release and the SDK pin advances per train (pin-freshness warns on lag — the
  `ui-html-pin-freshness` job). Falsified if the Landing-3 composition needs renderer
  bytes the pinned 0.2.1 lacks — then Landing 3 must ride the pin advance (order swap,
  disclosed on the PR).
- **R4 — sync machinery family generality.** If `standards_sync.py` or the lock writer
  enumerates families anywhere, the new family needs an explicit row. Build-time
  verification named in §7; falsified by sync refusing the new family.
- **R5 — group-of-one edge.** `member_ids.minItems: 2` forces the no-group rule for a
  1-lane remainder; a descriptor with exactly 1 digital_input channel renders one
  channel lane and zero groups (legal). Falsified only by a validator refusal on such a
  descriptor — covered by a fixture in A1's family (1-channel variant).
- **R6 — A02 pressure to smuggle limits.** The reference schema structurally refuses
  data fields; reviewers must hold the line that threshold safety is commissioned per
  bench (`cannot_derive.thresholds`). Falsified if any acceptance fixture's manifest
  carries a limit the descriptor did not declare.
- **R7 — intersection correctness (D13).** A wrong intersection either OFFERS a value
  the device does not admit (the D13 failure) or HIDES one it does. Mitigation: the
  closed vocabulary, the refuse-unknown rule, and A9's bounds-equal-constraint-bytes
  assertion. Falsified if A9's asserted bounds diverge from the fixture's constraint
  bytes in either direction.
- **R8 — `host_supplied` mis-declaration (D13/D14).** Naming a field host-supplied
  that no host actually supplies yields a button that cannot complete an invocation.
  Mitigation: the names come from the OTDP acquisition-lifecycle model
  (`acquisition_id`, `configuration_id`), and A10's invocation-path arms exercise the
  rendered controls against the preview host's real call path. Falsified if an L1/L2
  control cannot complete its invocation in the SDK test lane.
- **R9 — the extension seam's looseness (§2.6).** The canonical validator is
  extension-blind (verified), so the family schema is the layout block's ONLY
  validation authority — a plugin could carry a malformed block past `check-ui`.
  Mitigation: `verify-ui` refuses `classref_layout_invalid:` and the generated
  project test runs it in CI; a block the family schema does not know refuses rather
  than renders partially. Falsified if a malformed block renders anything in the SDK
  host or passes `verify-ui`.

## 11. Invariant and drift impacts

- **CON-7** (repin the only corpus-row writer): Landing 1 writes digests via repin only.
- **CON-8** (identity closed-world): unchanged — the family joins plugin-ui* outside the
  enumerated block; verified, not assumed (the enumeration names four families).
- **CON-12/CON-13** (matrix/site stamps derive from the manifest): the new family's
  surfaces move by their own mechanisms; `matrix --check` and site assembly verify in CI.
- **CON-4** (`check-sdk-standards` three-way agreement): Landings 1–3 move main standards,
  SDK lock and vendored tree through the sanctioned sync loop, in the sanctioned order.
- **No CTL/STO/REG invariant is touched** — no gateway runtime bytes change. The
  presentation-safety obligations that apply (§C.1 R-DEENERGISE-1, §D mode banners) are
  asserted by the gate, not redefined. **A02 note (D13):** the effective schema is a
  NARROWING composition only (catalogue ∧ constraints ∧ policy-where-commissioned);
  no path widens admittance, and bench policy enters only where a bench's own
  commissioned record supplies it — never invented at preview.
- Drift walk (G5): the plugin-ui README's layout description and the workbench-design §6
  "recipe" language stay truthful (the recorded D12a gap is disclosed, not papered over);
  `docs/internal/drift-and-obligations.md` gains no new numbered obligation in this
  increment (no new cross-surface motion beyond the existing standards loop) — the
  governor may add one for the family if review finds a walk gap.

## 12. Public-repo discipline

All fixture names are invented ("Veridian LA-32", `d0`..`d33`, channel labels "Data line
N"). No real plugin, vendor, bench, serial, or corpus identifier appears in any committed
file, filename, or the record itself. The real project that motivated the issue is never
named here.
