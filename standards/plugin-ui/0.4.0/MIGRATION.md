# plugin-ui 0.3.1 → 0.4.0 migration note

From-predecessor note for the 0.4.0 MINOR bump (the L5 §E.1 input trio —
text-input, select, boolean-input — gateway issue #463; design record
`.claude/deep-review/2026-10-16-classref-l5-plugin-ui-0-4-0-design.md`, whose
§5 carries the owner-worded sanction for the standards motion this bump is).

## What changed

Three things moved in the train, none of them in this schema set:

1. **The renderer** (`packages/ui-html` 0.3.0, landed ahead of this corpus in
   the train's PR-1): three §E.1 partials — `render_text_input`,
   `render_select`, `render_boolean` — plus their data classes, harness rows,
   canonical fixtures and a pattern-library page. The §E.1 table grows
   11→14 rows; the manifest vocabulary never changes (a control is
   schema-derived from the settings schema at render time; the corpus
   validator consumes its own version re-stamp, nothing more).
2. **The corpus re-stamp** (this directory): the four schemas are 0.3.1
   byte-copies re-stamped 0.4.0 — `$id`, `contract_version` consts and
   titles; the cross-schema `$ref` URLs re-stamp with them (the 0.3.0→0.3.1
   shape, verified by sorted-key diff to be version strings only). The
   substance lives in the renderer, the gateway's layout-consumption arms,
   the SDK expander/ladder widening and this re-stamp.
3. **The class-reference family 0.2.0** (the same train): the layout
   vocabulary's `control.kind` enum widens `["button","numeric","rotary"]`
   → `["button","numeric","rotary","text","select","boolean"]`; everything
   else is the re-stamp.

## The wall payment (single-serving)

The served range slides narrow: `>=0.3.1,<0.4.0` → `>=0.4.0,<0.5.0`. A pin to
0.3.1 is OUT of the carried set after this bump — the same one-live-object
rule as every plugin-ui bump (the normative bundle row lists the live code
object in every carried version's row, so single-serving is the only honest
posture; the manifest's policy note names the sanctioned narrow-range
crossing). Re-stamp 0.3.1 pins to 0.4.0: the documents are 0.4.0-valid
except `contract_version`, which the re-stamp updates; no previously-valid
0.3.1 document becomes invalid under its own frozen schema.

## Effect on consumers

- SDK `check-ui`/`check-preset`/`derive-ui`: unchanged mechanically — the
  SDK ingests this corpus by sync at its next release; a 0.3.1-stamped
  document refuses `unsupported_version` against this validator until
  re-stamped.
- The gateway's layout consumption (read-only, CON-5): a layout node of kind
  `text`/`select`/`boolean` renders the read-only disabled span (kind's
  class hook + the §C.2 `no-authority` label) — zero enabled controls, the
  L4 posture byte-for-byte.
- Class references: a reference whose `targets.plugin_ui` is `">=0.3.1"`
  stays satisfied by the active 0.4.0 (the comparator is per-parsed-
  operator, `>=` admits both).
- Layout blocks authored at 0.1.0: the 0.2.0 family schema pins
  `contract_version` 0.2.0, so an in-flight 0.1.0 block refuses
  `classref_layout_invalid`. Accepted deliberately (the design's §4
  consequence block): the only 0.1.0-block authors are the SDK expander
  (re-derives at 0.2.0), the SDK test fixtures and the class-capture page
  data, all re-derived in this train; no external block author exists.
