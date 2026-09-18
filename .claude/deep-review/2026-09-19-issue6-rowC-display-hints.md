# Issue #6 Row C — per-channel display hints in plugin-ui

Date: 2026-09-19
Status: design (no source mutated). Scope: the `measurement preset` bundle's row C —
optional per-channel display hints (colour preference, show/hide) carried in the plugin
presentation manifest, composited under host theme authority. Rows A (settings-as-presets)
and B (derived variables) are designed separately; D is deferred by the issue.

## Amendment 2026-09-19 — mechanism-critique fix wave (C1–C4)

Appended, not rewritten, per the invariants-file convention. The maintainer's
mechanism-critique pass ruled on four findings; the rulings sharpen §2.4 and
carry the same authority:

1. **C1 (accent arbitration).** §2.4's collision rule under-specified whose
   claim counts. Ruling: pass-1 index-0 accent is the FIRST claim — an accent
   hint on a non-index-0 trace loses silently to it, so uniqueness of the
   emphasis colour holds on every composition (pinned table-driven over all
   hint maps: visible accent-coloured series ≤ 1, count exactly 1 over
   non-empty visible sets). The sanctioned emphasis composition — mute index
   0, accent a later trace — keeps working and is pinned. Hints still never
   cascade: index 0 keeps its default when another trace's accent hint loses.
2. **C2 (threshold residual, closing the §2.4 rule-4 gap).** §2.4 said a hint
   may never touch the threshold mark line; it did not say what happens when
   every trace is presentation-hidden and the mark line's carrier series is
   filtered away. Chosen resolution: the threshold renders
   carrier-independently — with zero visible series an empty-data carrier
   series draws the mark line and nothing else. "No limit plotted" must never
   be launderable into "no limit configured".
3. **C3 (disclosure accessibility).** The struck-through legend row is now
   also an accessible disclosure: hidden rows carry an explicit accessible
   name naming the hidden state. The hidden trace itself stays excluded from
   the chart series, tooltip and accessible description (§2.4 rule 3,
   unchanged).
4. **C4 (token fallback).** §2.4 rule 5 implemented as written: a theme
   missing `--bw-text-muted` makes a muted hint fall back to the trace's
   pass-1 default. The interim implementation's `|| "#5b6a73"` literal —
   exactly the hardcoded-literal class the colour enum excludes — is gone.


Reading verified on `main` at `8bc83a5`. Every claim below cites the file and line it was
read at. **Review tier: Tier 3** — the change touches `standards/`, edits JSON Schema, and
advances the `packages/sdk` submodule pointer (three independent triggers of the rubric's
Step 1).

---

## 1. Problem and root framing

Issue #6 row C (maintainer-verified definition): an optional per-channel hint — colour
preference, show/hide — kept strictly in the presentation layer and composited under host
theme authority, such that a display choice can never change what the device does. The
renderer constraint is already fixed by the merged `feature/ui` work (PR #7):
`EngineeringPlot` (`ui/src/components/plots/EngineeringPlot.tsx:55-64`) assigns trace
styling host-side from CSS theme tokens, deterministically by trace index — index 0 takes
`--bw-accent`, every other index takes the threshold-severity token; symbol
(`circle`/`diamond`) and line style (solid/dashed) alternate on `index % 2`. Traces carry
only `{id, label, unit, values}`. Hints must bias within that model, never override it.

Two acceptance properties are pre-committed by the issue and this design treats them as
gates, not aspirations:

- **P1** — hints are optional and ignored without error by hosts that don't support them;
- **P2** — omitting them changes no validation result;
- **P3** — hint validation rides the existing plugin-ui validation seam.

### The interpretation fork the maintainer must see

P1 has two readings, and they select different mechanisms:

1. **Within-contract-version reading (selected).** A host running the same contract
   version but with no hint-consuming renderer feature must validate and render the
   document without error — hints are inert data. Cross-version tolerance is NOT claimed:
   a 0.1.0 host meeting a 0.1.1 document gets the contract's existing loud refusal.
2. **Cross-version reading (rejected).** A 0.1.0 host must swallow a hint-bearing document
   without error. The only mechanism for that in the current corpus is the manifest-level
   `extensions` escape hatch (`ui-manifest.schema.json:16`: namespaced keys, unconstrained
   values), because every structured object in the schema is `additionalProperties: false`.

Reading 2 is rejected on principle, not convenience: it would put a normative, validated
field inside a non-normative escape hatch — unvalidatable by schema (extensions values are
schema `{}`), addressed by fragile index paths into the `pages` array, and silently
droppable by hosts that don't know the convention. That is silent substitution where the
project discipline requires loud degradation. The 0.1.0 contract already fixes the
cross-version posture: "Version matching is exact. Unsupported manifest versions … disable
that UI contribution with a clear diagnostic"
(`docs/superpowers/specs/2026-09-12-plugin-ui-contract-design.md:52`), and the validator
implements it (`src/benchweave/presentation/contracts.py:258-259`,
`unsupported_version`). If the maintainer intended reading 2, this design does not build
that; say so and a different design is needed.

---

## 2. Mechanism

### 2.1 Where hints attach: the plot object, keyed by plotted variable

The hint is authored in the **ui-manifest** (plugin-authored presentation), attached to the
**plot**, keyed by the **variable ids the plot's `y` array already names**. Not the binding
catalogue: the catalogue is trusted *host* metadata (`standards/plugin-ui/0.1.0/README.md:54`)
and a plugin-author preference has no authority there — this preserves the existing
authority split. Not the binding: bindings don't own display, and the same variable may be
plotted in several plots with different hints.

Naming: the field is `variable_id`, not `channel_id` or `channel`, because `channel_id` is
an existing, different catalogue concept (descriptor channels,
`ui-manifest.schema.json:59` `$defs.target.channel_id`) while the hinted things are the
y-axis **variables** that `_plot_findings` resolves against the bound target
(`contracts.py:379-380`). "Per-channel" in the issue means "per plotted channel", i.e. per
`y` variable; conflating the two names would create exactly the unresolved-reference class
the validator exists to refuse.

Exact schema addition (in the copied 0.1.1 `ui-manifest.schema.json`, `$defs.plot`):

```json
"channel_hints": {
  "type": "array",
  "maxItems": 16,
  "items": {
    "type": "object",
    "additionalProperties": false,
    "required": ["variable_id"],
    "properties": {
      "variable_id": {"$ref": "#/$defs/id"},
      "color_role": {"enum": ["accent", "muted"]},
      "visible": {"type": "boolean"}
    },
    "anyOf": [{"required": ["color_role"]}, {"required": ["visible"]}]
  }
}
```

- `maxItems: 16` matches `y`'s own `maxItems` (`ui-manifest.schema.json:32`) — you cannot
  hint more channels than you can plot.
- `anyOf`-at-least-one forbids the vacuous hint `{variable_id: "x"}` — an object that
  carries no preference is noise the closed-world schema should refuse.
- Colour is a **role**, never a literal. `accent` and `muted` map to existing theme tokens
  (`--bw-accent`, `--bw-text-muted` — `ui/src/styles/themes.css:10,8` light,
  `:30,27` dark; both themes carry both tokens). The enum deliberately **excludes the
  severity roles** (`warning`, `critical`, `trip`, `advisory`, `success`): the threshold
  mark line owns severity colouring (`EngineeringPlot.tsx:64`), and a trace painted
  severity-coloured by a plugin preference would fake alarm semantics in the presentation.
  It also excludes any hex/rgb shape: a literal colour would override theme authority,
  break dark/light switching, and pose contrast problems the host cannot verify.

### 2.2 Version decision: PATCH bump 0.1.0 → 0.1.1

Governance class (`standards/GOVERNANCE.md:26-27`): *additive machine errata,
backwards-compatible* → **PATCH of that standard** — "new optional field, nothing removed
or retyped" (the interface `approver_token` pattern is the named precedent). This change
adds one optional property to `$defs.plot` and touches nothing else structurally.

Bump mechanics follow the in-tree existence proof, OTDP 0.1.0 → 0.1.1:

- `standards/plugin-ui/0.1.1/` is a **copy** of `0.1.0/` with edits only in the copy:
  `$id` URLs, `title`s and the four `contract_version` consts (root manifest, `$defs.envelope`,
  `$defs.preset`, `$defs.catalogue`) move to `0.1.1`; `channel_hints` is added to `$defs.plot`;
  the README prose companion is updated in the copy (prose is not digest-pinned —
  `GOVERNANCE.md:24-25`).
- `standards/plugin-ui/0.1.0/` stays in place, untouched, digest-frozen, both trees side
  by side (`GOVERNANCE.md:41-44`; the OTDP pair `standards/otdp/0.1.0/` + `0.1.1/` with
  both versions' rows in `standards/corpus-manifest.json` proves the pattern passes every
  current gate).
- New corpus rows cite the old corpus path as `source`
  (`source: "standards/plugin-ui/0.1.0/<file>"`), exactly as the OTDP 0.1.1 rows do.
- `standards/standards-manifest.json`: the plugin-ui entry becomes version `0.1.1`,
  `supersedes: "0.1.0"`, normative list repointed at the 0.1.1 schema paths
  (`src/benchweave/presentation/contracts.py` stays in the normative list at its
  unchanged path — it is already a normative file of this standard, manifest line 99).
- Digest pins move only via `uv run python -m benchweave.standards repin` — edit → repin →
  export (`GOVERNANCE.md:37-39`, invariants CON-7).
- **No identity-block event**: `plugin-ui` is not an identity key
  (`src/benchweave/standards/manifest.py:13` — `IDENTITY_STANDARD_KEYS` covers
  otdp/registry/execution/interface only), so `corpus-manifest.json`'s identity block and
  the CON-8 derivation chain are untouched. `tests/contract/test_baseline.py`'s identity
  pins (`:106-108`) name registry/execution/interface only.

Consequences of the version-const flip (deliberate, matching OTDP precedent): a document
declaring `contract_version: "0.1.0"` is refused `unsupported_version` by the upgraded
validator. Existing plugin-ui documents must re-declare `0.1.1` and re-pin their manifest
digest in the envelope (byte change → sha256 change). In-tree that is synthetic specimens
and scaffold output only, all moved in the same arc; for external authors the
compatibility matrix renders "Supersedes 0.1.0" automatically from the `supersedes` field
(`src/benchweave/standards/matrix.py:80-82`). The alternative — dual-active versions in
the bundle/vendored tree — is not the established pattern (the SDK loads exactly one
version per standard, `packages/sdk/src/benchweave_sdk/validation.py:26-28`) and doubles
the synced surface for no measured need.

### 2.3 Semantic validation: rides the existing seam, no new diagnostic codes

`src/benchweave/presentation/contracts.py` changes:

1. `SCHEMA_ROOT` → `"https://benchweave.dev/contracts/plugin-ui/0.1.1/"` (line 20).
2. The two version equality checks (`:166`, `:258`) accept `"0.1.1"`.
3. `_plot_findings` (`:369-399`) grows the hint checks, inside the existing per-page loop:
   - every `channel_hints[].variable_id` must be a member of **this plot's `y`** (not
     merely a variable of the target — hints are per-plot) → otherwise
     `Finding("unresolved_reference", "pages.<id>.plots.channel_hints", ...)`;
   - duplicate `variable_id` within one plot's `channel_hints` →
     `Finding("invalid_document", ..., "Duplicate identifiers")`, mirroring the
     `_unique_rows` behaviour (`:269-273`).

Both findings use **existing** codes from the closed README list; no new diagnostic
vocabulary is introduced (adding codes would be a second normative change riding along
uninvited). Structure, enum, boolean shape, item counts and at-least-one-field are the
JSON Schema's job in the copied 0.1.1 corpus; reference resolution and duplicates are the
Python seam's job — the same split `_plot_findings` already draws for axes
(schema checks shape; Python checks resolution against catalogue variables).

### 2.4 Renderer composition: theme authority, two passes, stable indices

`EngineeringPlot` grows one **optional** prop:

```ts
export interface TraceHint { colorRole?: "accent" | "muted"; visible?: boolean }
hints?: ReadonlyMap<string, TraceHint>  // keyed by trace id
```

Composition contract (what a hint may and may not do):

1. **Pass 1 — index-derived defaults, unchanged.** Over the FULL ordered trace list:
   index 0 → accent token; other indices → severity/alert token; symbol and line style on
   `index % 2`; threshold mark line on index 0 with severity colour. This is byte-for-byte
   today's behaviour (`EngineeringPlot.tsx:55-64`).
2. **Pass 2 — hint bias.** A trace with `colorRole: "accent"` takes the accent token;
   `colorRole: "muted"` takes the text-muted token. **Collision rule:** if more than one
   trace hints `accent`, the earliest in trace order wins and the others revert to their
   pass-1 default — uniqueness of the emphasis colour is a host invariant (today exactly
   one trace is accent), and hints bias, never multiply.
3. **Visibility is a filter applied AFTER style resolution.** `visible: false` removes the
   trace from the rendered series, the chart's accessible description, and the tooltip —
   but the plot's HTML legend keeps a struck-through row (`data-hidden="true"`) disclosing
   that the channel exists and is hidden by presentation preference. **Indices never
   shift**: styling is resolved over the full list, then hidden traces are filtered from
   rendering. Hiding channel b must not change the colour/symbol/line of channels a or c.
   This is the load-bearing answer to the issue's trace-index-determinism question.
4. **A hint may never:** supply a literal colour; touch the threshold mark line or any
   severity mapping; alter axis, grid or tooltip theming; change another trace's style
   (no cascade); introduce a trace not declared in `y`; or change any validation result.
5. **The host keeps final say.** Hints are preferences, not commands: the component/theme
   remains free to disregard them (a future high-contrast mode may ignore `muted`; a theme
   missing the token falls back to pass-1 default). With the `hints` prop absent, the
   component's behaviour is identical to today — pinned by test, not by assertion in prose.

Display never reaches device behaviour, structurally: hints live in the ui-manifest; the
validator's output is a `ValidationReport` that "conveys compatibility, never permission"
(`contracts.py:100-101`); `validate_attachment` "grants no execution authority"
(`src/benchweave/presentation/admission.py:25`); the renderer has no request path except
explicit user actions through approved procedures (README "Ownership and execution"). No
new path from presentation data to control is created; the only additions to the request
surface are none.

### 2.5 Ignore-without-error proof (P1/P2)

- **P2, formal.** The ui-manifest 0.1.1 schema is 0.1.0 plus one optional property on
  `$defs.plot` plus version consts. JSON Schema evaluation of a document that omits
  `channel_hints` hits exactly the same constraints as 0.1.0 evaluation of that document:
  the property is not in any `required`, no `allOf/if-then-else` branch names it (the page
  gates on `kind` vs `plots`, `ui-manifest.schema.json:37-40`), and `additionalProperties:
  false` is satisfied by absence. Therefore: same document, hints omitted vs well-formed
  hints present ⇒ identical findings (both valid), for any feature/panel sets.
- **P1, within-version.** Hints are never a `required_ui_features` entry — the 0.1.1
  README states a host MUST NOT declare or require a feature for hint consumption; a host
  with `supported_features=frozenset()` and `supported_panels=frozenset()` validates a
  hint-bearing document identically (this is the tested form of "hosts that don't support
  them"). On the renderer side, a host that doesn't pass `hints` gets today's exact
  behaviour.
- **Cross-version:** governed by the existing exact-version gate
  (`contracts.py:258`, `unsupported_version`) and its established degradation (plugin
  remains usable through its descriptor; README line 3). Loud, by design — see §1.

---

## 3. Precedent (principle 9)

| Mechanism reused | Precedent |
| --- | --- |
| Copy-never-move version bump with frozen old tree + `source`-cited corpus rows | OTDP 0.1.0 → 0.1.1 (`standards/otdp/` both dirs present; corpus rows cite old paths) |
| Additive-optional-field PATCH class | interface `approver_token` pattern, named in `GOVERNANCE.md:27` |
| Per-plot semantic checks resolving ids against the bound target's variables | `_plot_findings` (`contracts.py:369-399`) |
| Duplicate-id refusal via existing `invalid_document` code | `_unique_rows` (`contracts.py:269-273`) |
| Theme-token resolution from CSS custom properties with fallback | `EngineeringPlot.tsx:44-48` |
| Optional-degradation without error for unconsumed metadata | `unavailable_pages` / `unsupported_feature` posture (README "Optional plotting and panels") |
| Standards flow main-side first → export → SDK sync → pointer | `GOVERNANCE.md:75-77`, Makefile `sync-sdk-standards` |

New architecture invented: none. The only genuinely new decision is the closed two-role
colour vocabulary, justified in §2.1.

---

## 4. Cross-surface sync list (everything that moves)

**Main repository** (one working branch; commits land main-side first):

1. `standards/plugin-ui/0.1.1/` — new: 4 schemas + README + validation-report (copied,
   edited in copy).
2. `standards/plugin-ui/0.1.0/` — untouched (verify by corpus pin, not by eye).
3. `standards/standards-manifest.json` — plugin-ui → 0.1.1, `supersedes`, normative paths.
4. `standards/corpus-manifest.json` — via `repin` only: +4 machine rows (schemas; README
   and validation-report are unpinned prose per GOVERNANCE).
5. `src/benchweave/presentation/contracts.py` — SCHEMA_ROOT, version consts, `_plot_findings`
   hint semantics.
6. Tests updated to the active version: `tests/unit/test_presentation_manifest.py`
   (fixture reads `standards/plugin-ui/0.1.0/*.schema.json` at `:30` and asserts `"0.1.0"`
   consts at `:49,54,84`), `tests/unit/test_presentation_specimens.py`,
   `tests/unit/test_presentation_presets.py`, `tests/unit/test_presentation_contracts.py`,
   `tests/architecture/test_plugin_ui_contracts.py` (`:12,29,40`),
   `tests/contract/test_corpus_revision.py`, `tests/standards/test_scenarios.py`.
7. New tests (see §7).
8. `docs/compatibility-matrix.md` — regenerated (`benchweave.standards matrix`); CI's
   `matrix --check` fails until it is.
9. Version-claim prose sweep: `docs/compatibility.md`, `docs/device-developer-guide.md`,
   `docs/develop-your-device.md`, `docs/plugin-sdk.md` (machine-truth directive,
   2026-09-16).
10. `.standards-bundle/` — regenerated transiently by export; **not a committed surface**
    (0 files tracked) — correcting the assumption in the tasking that listed it as one.

**SDK repository** (`packages/sdk` — commit and PUSH there first, then the pointer here;
obligation 7):

11. Vendored tree via `benchweave-sdk sync-standards .standards-bundle` (generated):
    `src/benchweave_sdk/standards/plugin-ui/0.1.1/*`, updated `contracts.py`, stamps,
    `standards-lock.json`.
12. `packages/sdk/src/benchweave_sdk/validation.py:28` — `("plugin-ui", "0.1.1")`.
13. `packages/sdk/src/benchweave_sdk/presentation.py` — `create_ui_resources` writes
    `contract_version` at `:341,357,363`: bump to `"0.1.1"` (scaffold must never generate
    what `check-ui` rejects — SDK principle 6). `_preview_fixture`'s `"0.1.0"` at `:227`
    is the plugin-ui-preview fixture document (a different standard, stays 0.1.0) — verify
    at build time, do not bulk-sed.
14. SDK tests + `user_guide/plugin-sdk.qmd` / website copies if they pin the version.
15. `packages/sdk/preview_assets/` — the renderer freshness gate (ui CI job) rebuilds
    `build:preview` and fails on any diff: the `EngineeringPlot.tsx` change forces a
    committed renderer refresh here, in the same arc.
16. Main repo: submodule pointer commit after the SDK push.

**Obligations walk** (`docs/internal/drift-and-obligations.md`): #3 yes
(device-developer guide — plugin-visible presentation behavior), #6 yes (vendored bytes +
repin + `make check-sdk-standards`), #7 yes (pointer push-first + renderer freshness);
#1/#2 no (no MCP tool, no openapi — plugin-ui is not the interface standard); #5 no
(registry fixture lattice untouched); #8 no (adapter surface untouched).

**CI cost:** no new jobs. `gates` gains nothing new (repin/export/check already run);
`ui` runs the freshness gate that already exists; the SDK repo's three sync-check lanes
run as today.

---

## 5. Minimal first increment — and what it DEFERS

**Increment 1 ships:**

1. The contract: plugin-ui 0.1.1 (schema + prose + validator semantics), full sync list
   §4 items 1-9, both repos green.
2. The renderer primitive: `EngineeringPlot` hints prop, two-pass composition, stable
   indices, hidden-legend disclosure row — with component tests and a Storybook story.
3. One multi-y specimen fixture exercising hints end-to-end at the validation level
   (hinted + unhinted pair).

**Explicit deferrals (each named, none silent):**

- **Manifest-driven plot rendering in the preview/host UI.** Today no renderer consumes
  manifest `plots` at all — the preview workbench builds traces from observations
  (`ui/src/compositions/fixtures.ts:67`) and passes `pages` through opaquely
  (`packages/sdk/src/benchweave_sdk/fixtures.py:322`). Wiring plugin plots (hinted or not)
  into `EngineeringPlot` is the separate plot-rendering feature; Row C lands the contract
  and the component capability it will compose with. This mirrors the 0.1.0 plugin-ui
  posture ("rendering … follow separately").
- **End-to-end hint transport in the preview document** — needs either the browser to see
  the catalogue (it doesn't today) or a `plugin-ui-preview` standard bump to carry
  projected hints; both are sprawl for increment 1 and are named here so they are chosen,
  not discovered.
- Legend re-show interaction (hidden rows are disclosed but not clickable in increment 1).
- Per-user / persisted visibility overrides (the 0.1.0 design's "presentation preferences
  remain frontend state" — user state outranking author hints is a later increment).
- Widening the colour-role vocabulary beyond `{accent, muted}` (requires a richer host
  trace palette first — the host model itself has two trace colours today).
- Row A/B interactions (preset-hint interplay, derived-variable hints).

---

## 6. Invariant impacts

- **CTL/STO/REG: untouched.** No control, state, or plugin-lifecycle code changes.
- **CON-2** (pin lattice): corpus rows for 0.1.1 added by repin with correct `source`
  provenance; registry fixture lattice untouched; the frozen 0.1.0 rows remain — pinned by
  `tests/standards/test_repin.py`'s superseded-row verification.
- **CON-4** (packaged-first vendoring): SDK lock/tree/stamps move only through
  sync-standards; `make check-sdk-standards` stays green.
- **CON-7** (repin is the only pin writer): no hand-spliced digests anywhere in this flow.
- **CON-8**: no identity event (plugin-ui is not an identity key — verified §2.2).
- **No new invariant row is proposed.** The "display never reaches device behaviour"
  property is already structurally enforced (non-activating validation, §2.4) and the
  renderer-side guarantees that ARE new (index stability, no-cascade) are pinned as ui
  component tests rather than prose invariants — they guard one component, not a
  cross-cutting mechanism.

---

## 7. Measurable proof — pre-committed acceptance rule

Written before any number below was looked at. All counts are this design's own
commitments, measured by the named tests.

**Metric 1 — validation equivalence (P1/P2).** Over the specimen corpus — the three
existing specimens plus the scaffold-generated example, each in a hinted/unhinted pair —
`validate_presentation` must return identical, finding-free reports for both members of
every pair, at `supported_features=frozenset()` AND at a non-empty feature set.
**Ship:** 4/4 pairs identical-and-valid in both feature conditions (16 validations).
**Kill:** any pair differs in findings. **Underpowered, not conclusive:** if the corpus
contains no multi-y plot at measurement time, equivalence is unproven for the only case
hints exist for — add the multi-y specimen (§5 item 3) and re-measure before shipping;
do not declare success on single-channel pairs.

**Metric 2 — hint validation catches (seam rides, P3).** Six malformed variants — unknown
`variable_id` (not in `y`), variable of the target but not of this plot's `y`, duplicate
`variable_id` within one plot, unknown `color_role`, empty hint object, 17th hint on a
16-channel plot — must each yield a finding, with codes drawn from the existing closed
list (`unresolved_reference` / `invalid_document` / schema-path `invalid_document`).
**Ship:** 6/6 produce exactly one finding each. **Kill:** any variant validates clean.
**Underpowered:** a variant failing for the wrong code (e.g. duplicate caught by schema
shape rather than the semantic check) is a wrong-mechanism finding — fix, don't rationalise.

**Metric 3 — renderer RED checks (both directions demonstrated before GREEN).**
(a) *Hint bias:* hinted trace receives the hinted token, other traces keep pass-1 styles.
RED: delete only the pass-2 bias application → assertion (a) fails while the no-hint
control still passes. (b) *Index stability:* traces [a, b, c] with `visible: false` on b —
a and c keep exactly the styles they have in the no-hints control. RED: change style
resolution to run over the visible subset → assertion (b) fails. (c) *Inertness:* `hints`
prop absent ⇒ style assignment identical to today's implementation, asserted against
literal expectations (accent for index 0, severity token otherwise, `index % 2` symbol and
line type). **Ship:** all three RED directions shown to fail for the stated reason, then
GREEN. **Kill:** any RED direction that cannot be made to fail means the test is not
testing the mechanism — the measurement, not the feature, is broken.

**Test files to create (RED-first build):**

- `tests/unit/test_presentation_manifest.py` — extend: hint pair-equivalence, the six
  malformed variants (metrics 1-2). The bundle fixture at `:26-71` already carries a plot
  with `y: ["value"]`; extend it and/or the specimens to multi-y.
- `tests/unit/test_presentation_specimens.py` — the multi-y hinted specimen pair.
- `tests/architecture/test_plugin_ui_contracts.py` — 0.1.1 `$id`/const sweep already
  re-pins itself via `DIRECTORY`; add `channel_hints` shape assertions (closed-world: an
  unknown key inside a hint object must fail).
- `ui/src/components/plots/EngineeringPlot.test.tsx` — metrics 3(a)-(c); the echarts mock
  at `:4-7` must capture `setOption` calls so style assignment is asserted on the real
  option payload, not on rendered pixels.
- `ui/src/components/plots/EngineeringPlot.stories.tsx` — hinted/hidden stories for review.

---

## 8. Top risks, each with its falsifier

1. **The P1 interpretation is wrong (maintainer meant cross-version tolerance).**
   Falsifier: maintainer review of §1. If reading 2 is wanted, this design is DON'T-BUILD
   as written — the extensions-route redesign must be commissioned explicitly, accepting an
   unvalidatable-by-schema hint shape.
2. **The version-const flip orphans external 0.1.0 plugin-ui documents.** Real but bounded:
   in-tree only synthetic/scaffold documents; matrix renders "Supersedes 0.1.0"; the
   scaffold and specimens move in-arc so the SDK never generates what it rejects. If
   external-plugin breakage proves larger than acceptable, the fallback is dual-version
   acceptance in the validator plus keeping 0.1.0 schemas in the bundle — a deliberate
   governance change, not a patch to this one.
3. **Two-role vocabulary is too narrow to be worth a version bump.** Falsifier: nothing
   measured — it is a scope judgement. The counter-weight: the host model itself exposes
   exactly two trace colours today; shipping a richer hint vocabulary than the host can
   render would be schema promising behaviour the renderer doesn't have.
4. **A future renderer recomputes styles over filtered traces, breaking stability.**
   Pinned by metric 3(b); the risk is regression, and the test is the guard.
5. **Sync-list incompleteness** (a missed version literal in docs/tests). Mitigated by
   `make check-sdk-standards`, `matrix --check`, the SDK's three sync lanes, and a
   repo-wide grep for `plugin-ui/0.1.0` at review time; the census in §4 was made by that
   grep on `8bc83a5`.
6. **Renderer freshness gate trips late** — the preview_assets refresh (§4 item 15) is
   discovered in CI rather than in the arc. Named here so it is committed with the SDK
   change, not after a red `ui` job.

---

## 9. DON'T-BUILD assessment

Not triggered. The mechanism extends three proven in-tree patterns (PATCH bump, per-plot
semantic checks, theme-token styling), touches no control path, is measurable with
non-gameable RED checks, and its cost is dominated by the governed version bump the
corpus's own governance model prescribes for exactly this change class. The one genuine
stop-condition is risk 1: if the maintainer's "ignored without error" means cross-version
tolerance, do not build this — build the extensions-route design instead, with its eyes
open.
