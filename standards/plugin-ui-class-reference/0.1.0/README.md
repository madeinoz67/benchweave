# plugin-ui-class-reference 0.1.0

One reference presentation per device class, written as **data** in this
standards family. One class reference is the single source for three
consumers: the pattern-library class page, an SDK expander that turns a
class-conformant descriptor into a normal plugin-ui 0.3.1 manifest set, and
an SDK gate that renders the result through the real preview host and
compares the rendered component inventory against the reference's `expect`
block. The gateway application is untouched.

Design record: `.claude/deep-review/2026-10-14-classref-logic-analyser-design.md`
(gateway issues #463 rows 1–2, #462 rows 1–2).

## Files

| File | What it is |
|---|---|
| `class-reference.schema.json` | The class-reference document schema: slots, page templates, expectations, declared gaps |
| `layout.schema.json` | The namespaced layout block vocabulary that rides the plugin-ui 0.3.1 `extensions` seam under the key `plugin-ui-class-reference:layout` |
| `class-logic_analyser.json` | The founding reference for the `otdp.logic_analyser/1.0.0` class |

## The structure rule (D2)

The reference authors **structure, not data**. It may name page ids and
titles, slot keys, binding ids, the group label pattern, section ids and
titles, and the layout spans. It may author only these structural numbers:
`group_size` 8, `plot_index` (a placement index), and layout spans (at most
12). It authors no values, units, thresholds, voltage or rate limits,
channel names, or parameter names. Every data item resolves at expansion
time from the descriptor and the OTDP action schemas. The schema carries no
data-bearing field: no `default`, no `value`, no `unit`, no numeric bound
fields. An author who reaches for a data field gets a schema refusal, not a
silently-carried value.

## Class reference documents

A reference document binds one OTDP profile (`profile_id`) and speaks the
plugin-ui vocabulary it targets (`targets.plugin_ui`, for example
`">=0.3.1"`).

**Slots** map roles to derivation inputs. A `channels` slot resolves an
ordered lane list from the descriptor's declared channels with the named
role. An action slot (`dataset`, `configuration`, `procedure`) binds an
OTDP action URN; `when_declared: true` marks an optional action — it binds
only when the descriptor declares that action. `host_supplied` names the
input fields the host owns (the OTDP acquisition lifecycle assigns
`acquisition_id` and the active `configuration_id` to host ownership) —
field names, never values (D2-clean). The `vendor_actions` slot is the
D14 coverage hook: it covers every declared action URN that no named slot
claims.

**Pages** are page templates. `binding_slots` lists the slot keys a page
binds; optional-action slots bind only when the descriptor declares them.
A `binding_slots` entry that names no key in the reference's `slots`
refuses at expansion (`classref_unknown_slot:`). `vendor_features: true`
marks the page that hosts the Device-features section. The `plot` block
declares the page's `digital_lanes` plot: the dataset slot it runs over,
group of 8 with label pattern `D{first}-D{last}`, radix `hex` (default)
or `decimal`. Labels are decimal positional always; the radix formats
rendered values, never labels.

**Expect** declares the gate's assertions. `components` maps a component
name to a `count` — an integer or a closed expression (`{n_lanes}`,
`{n_groups}`, `{n_decoders}`, `{n_run_actions}`, `{n_configure_fields}`,
`{n_pages}`, integer literals, `+`); `attribute` maps a
`"name=value"` selector to a count expression; the selector set is closed:
the three `data-bw-lane-kind` selectors (channel, group, decoder) and
nothing else. `per_page` names a page id, or `*` for every page.
`controls` maps a class action URN to its reachability level: `button`
(L1, no required inputs after host-owned fields), `staging` (L2, required
numeric inputs), `preset` (L3, configuration-shaped), `deviation`
(a declared deviation at the reference level). `forbid` names the gate's
closed check set: `confirm-wrapped-run-action` (D7 — the de-energising
action is one action, never confirmed), `color-role-hint-on-lane` (belt
over the manifest schema's own refusal), `untraceable-lane-label` (every
lane label traces to the descriptor or the group pattern).

**cannot_derive** rows name what a class reference must not know (A02:
qualification is per bench). The expander prints them into its output and
into the generated AI-GUIDE, so the author learns where they supply the
missing item.

## The layout vocabulary

A layout block composes the §E components the renderer already ships:
sections (panel composition), controls (`button`, `numeric`, `rotary`),
reading tiles and data tables, text bodies (author capability only — the
class reference authors no text nodes), and plot references that place a
page's declared plot.

Bounds: at most 16 sections per page and 16 children per section, section
nesting depth at most 3 (by construction), grid span at most 12, text
bodies at most 512 characters. The per-page node ceiling of 64 is a
gate-time census: the schema bounds each array, never the page total — a
block the schema admits can still fail the gate census. One vocabulary,
two writers: a class reference may author structure-only layouts (its
`layouts` entries ride the same `layout.schema.json` through the family
schema's cross-file `$ref`), and an author may hand-write the same block
into a manifest's `extensions` map under
`plugin-ui-class-reference:layout`. Identical validation (A11).

The canonical plugin-ui validator is extension-blind: it validates a
manifest carrying the block exactly like one without it. This family
schema is the block's only validation authority. A host that does not know
the namespace ignores the block and serves the manifest's plain pages —
degrade by ignoring, never an error.

## The deviation ledger contract

A project declares conformance state in an author-owned
`ui/class-reference.json`: the reference the project follows (`profile_id`
and family version) and the declared-deviation ledger
`deviations: [{expectation_id, reason}]`. An `expectation_id` outside the
reference's expect vocabulary is refused (`classref_unknown_expectation:`) —
an unknown id cannot launder a divergence. A declared deviation downgrades
exactly that expectation's failure to a REPORTED row in the gate output;
an undeclared divergence FAILS the gate. D7-class expectations are
non-downgradable: a deviation may never name an energy-removing action's
reachability — the ledger refuses (`classref_deviation_forbidden:`);
nothing may stand between the operator and abort.

## Authoring path and provenance

Founding-family convention: the family's founding bytes were staged at
`docs/plugin-ui-class-reference-v1/` on the admitting branch, the corpus
rows cite that authoring path as `source`, and the staging directory was
removed in the same pull request. Provenance lives in git history and in
the corpus manifest's `source` fields — the plugin-ui-preview founding
families' own shape.

## The plugin-ui floor (cross-constraints)

The family's cross-constraints row names the plugin-ui floor:
`plugin-ui >=0.3.1,<0.4.0`. The row is vacuous while plugin-ui serves a
single version, and the family goes to review at every plugin-ui bump —
a plugin-ui bump carries vocabulary the reference may silently
mis-derive, so the reference re-proves its derivation per bump (design
record R2).

## Names

All fixture names are invented. "Veridian" and the `d0`..`d33` channel
naming are fixture vocabulary, not real products, vendors, or benches.
