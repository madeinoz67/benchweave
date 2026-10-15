# L5 — plugin-ui 0.3.1→0.4.0: the §E.1 input trio (text, select, boolean)

**Date:** 16 October 2026
**Slot:** L5 of the class-reference train (parent gateway issue #463; program record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` — §7A row L5, §8's
RC-9/D-10 row, the D4 amendment for this row only).
**Branch:** `feat/classref-l5-design` (design record only; no build in this slot).
**Worktree:** `.wt/l5-design-4b7f/`, off `origin/main` `6d94ade0`; submodule at `201c343`
(SDK v0.14.0). SDK source checkout: `~/Documents/src/benchweave-sdk` at `bceccc5`
(main, carries #154/#155 post-v0.14.0 fixes).
**Evidence baseline:** gateway `6d94ade0` (post-L4 #474, post-Windows-core #477), SDK
v0.14.0 pinned (`201c343`) with main at `bceccc5`, plugin-ui 0.3.1 both sides,
plugin-ui-class-reference 0.1.0 both sides, `benchweave-ui-html==0.2.1`.
**Binding design points:** the program record D1–D14 (esp. D4 **as amended for RC-9
only**, §8 lines 878–883; D10/RC-9, line 897; §2.5's census + ladder, lines 344–392;
§2.6's vocabulary-closure note, lines 470–474), the record's A1–A12 acceptance rules
(held unchanged), and the owner rulings of 2026-10-14/15 (batched-release cadence;
merge order at L5 = release → pointer → #465).

## 0. Summary and design thesis

L5 ships the three §E.1 input components the program record names — **text-input,
select, boolean-input** — as a plugin-ui contract bump 0.3.1→0.4.0 (the D4 amendment's
one sanctioned wall payment), widens the class-reference family's layout vocabulary and
the reachability ladder to use them, and pays the single-serving wall (contracts.py
literals + every carried pin) exactly once. The design thesis in one line:

> The trio is a **render-side capability** — the manifest vocabulary never changes, the
> canonical validator's only consumption is its own version re-stamp, and the three
> things that actually move are (a) the corpus re-stamp + family layout-schema widening
> (gateway), (b) the renderer partials + contract rows (ui-html 0.3.0), (c) the SDK
> expander/ladder/census/render-lane widening (SDK 0.15.0).

Three grounding facts fix this thesis, each verified in the landed tree, not assumed:

1. **The manifest carries no control vocabulary.** `ui-manifest.schema.json` 0.3.1's
   `$defs` are id/title/hash/path/ids/reference/asset/binding/plot/page/envelope/preset/
   variable/variables/target/catalogue/lane_group/decoder_lane — controls derive from
   the settings schema (`schema_asset_id`) at render time. A text/select/boolean input
   is schema-derived; nothing in the manifest names it. (Read from
   `standards/plugin-ui/0.3.1/ui-manifest.schema.json`, `$defs` census.)
2. **The canonical validator carries no component vocabulary** — zero component/render
   references in `src/benchweave/presentation/contracts.py` (grep census; the only hit
   is an unrelated `event_log`/renderer note at line 603). RC-9's "validator
   consumption" is therefore the D4 amendment's own named cost: the version-literal
   re-stamp (`SCHEMA_ROOT` line 20, guards lines 247 and 372, all confirmed at those
   lines) — the validator consumes the 0.4.0 schema set, nothing more.
3. **A plugin-ui bump's schema delta can be version-re-stamp only.** The 0.3.0→0.3.1
   diff is `$id`/`const`/`title` strings across all four schemas, nothing else (verified
   by sorted-key diff). The 0.3.1 substance (the commissioned-firmware gate, #444) lived
   in the validator. L5 follows the same shape: schema delta = re-stamp; substance in
   the validator's re-stamp, the renderer, and the SDK.

The mechanism per surface, then the reconciliation of the two competing L5 scope
claims (§1), the exact corpus bytes (§4), the version arithmetic (§3), the merge order
(§5) — and the acceptance rules are written before any build (§9).

## 1. Reconciliation — the record's L5 vs the handoff's five-item "cannot-express" backlog

The two lists are **different scopes**, and the record is authoritative per the
dispatch. Reconciled:

**The record's L5** (four independent anchors, none of which names a display idiom):
- §7A row L5 (line 859): "§E.1 text/select/boolean input components; contracts.py
  edited once; the layout vocabulary and ladder widen to use them".
- §8 RC-9/D-10 (line 897): "plugin-ui 0.3.1→0.4.0: §E.1 text/select/boolean input
  components and their validator consumption".
- §2.5 (lines 367–374): "The §E.1 inventory has no text-input, select or boolean
  component (verified census: button, numeric-input, rotary-control, reading-tile,
  alert-bubble, engineering-plot, digital-lanes, data-table, panel, mode-banner,
  confirm-action). That vocabulary gap ships in the train's Landing 5".
- §2.6 (lines 470–474): the §6.1 items with no §E.1 component (tabs, splits, sliders,
  switches, selectors, keypads, text inputs) "stay OUT of the vocabulary until §E
  components exist for them (Landing 5 adds the input trio — text, select, boolean —
  under the D4 amendment scoped to that row; tabs, splits and sliders join only if the
  same bump adds §E components for them)".

**The handoff's five items** (group bracket, annotation chips, on-axis markers,
derived frequency, position badges) are **not input components** — they are the
styleguide's class-generic capture-view **display idioms**
(`docs/internal/ui-styleguide.md:268`): "the grouped label column with brackets, the
annotation-chip rows for bus values and decode overlays, the cursor and trigger
markers with their readout, the capture-context strip, and the position badges".
The handoff's list is itself a permutation/subset of that idiom set (four of the five
match; "derived frequency" is not in the styleguide list; the styleguide's
"capture-context strip" is not in the handoff's five). The handoff's "Closes #465"
note refers to the merge-order ruling (release → pointer → #465), not to scope.

**Verdict and the split:**

- **L5 = the input trio only.** Four record anchors name the trio; none names an idiom.
  The idioms emerged from the sweep-era styleguide rule (styleguide:268, committed
  text), which is a build rule for L11–L21, not L5 scope.
- **The five idioms defer to the sweep (L11–L21)** under their existing governing text
  (styleguide:268) — each sweep landing that needs an idiom builds it class-generic;
  the analyser-specific part keeps riding the existing digital-lanes component.
- **Batching rule for the wall:** any §E.1 contract rows the idioms eventually need
  batch into ONE contract bump — the next wall-payment event after L5 — exactly the
  D4 amendment's own batching logic ("Tabs, splits and sliders join only if the same
  bump adds §E components for them"). Idioms that are pure host compositions of
  existing §E.1 components (the cursor/trigger markers already have contract surfaces
  — `data-bw-trigger`, `data-bw-cursor` on the digital-lanes row, ui-contract.md:303)
  need no bump at all.
- **Trigger:** the first sweep design record that needs an idiom names it in its scope
  and calls the bump.

What deliberately does **not** change hands: no §6.1 recipe item (tabs/splits/sliders)
joins — the D4 amendment admits them only if "the same bump adds §E components for
them", and it does not; that clause stays as written.

## 2. The component contracts (§E.1 rows 12–14)

The §E.1 table (`docs/internal/ui-contract.md:291`, schema
`Component | Root element | Required attributes | Required roles | Required class
hooks | Required text | Notes`) grows 11→14 rows. The three new rows follow the
inventory's conventions (div-rooted, BEM hooks, staging disclosure, A02
bound-honesty):

**`text-input`** — root `div`; required attributes `type=text` (on the field input) ~
`aria-describedby` ~ `for`; bounds (`minlength`/`maxlength`) exposed **only when the
effective schema declares them** — an absent bound renders the absent attribute, never
an invented limit (A02; the numeric row's own rule); required roles —; required class
hooks `bw-text ~ bw-text__label ~ bw-text__field ~ bw-text__help`; required text
`Staged value; use Apply to request the change` (the numeric row's staging line — a
text field stages intent exactly as a numeric does); notes: renders schema-derived
from a `type: string` field without a pattern (D13: a free string admits every string
value, so a text control can never offer an unadmitted value; a **pattern-narrowed**
string is NOT this component — §6/RC-L5-4).

**`select`** — root `div`; required attributes `for` ~ `aria-describedby`; required
roles —; required class hooks `bw-select ~ bw-select__label ~ bw-select__field`;
required text `Staged value; use Apply to request the change`; notes: options are the
effective-schema intersection's enum (a closed option set; D13 by construction — every
option is admitted); a `const` (or single-option enum) renders the **read-only fixed
display**, never an editable offer (the record §3.7 rule; the F3a shape). Census keys
on `bw-select`.

**`boolean-input`** — root `div`; required attributes `role=switch ~ aria-checked` on
the control element, labelled via `for`-association or `aria-labelledby`; required
roles `switch`; required class hooks `bw-boolean ~ bw-boolean__label ~
bw-boolean__control`; required text `Staged value; use Apply to request the change`
(identical to the trio's one staging sentence). Notes: renders schema-derived from `type: boolean`; stages intent; the
staging/Apply lane stays the one submit path (no new submit surface); energy-removing
actions never take any staged input pattern (§C.1 R-DEENERGISE-1 unchanged — the trio
are `type=staged`, never the energy-removing action's control, which stays one action,
never confirmed, never gated).

All three rows' notes carry the §E.1 row-notes convention: the family's staging
disclosure line, the A02 bound-honesty clause, and the never-between-operator-and-de-energising
clause by reference.

**Naming convention note:** `text-input` and `boolean-input` follow the inventory's
`*-input` convention (numeric-input precedent); `select` is its own name (no
`select-input`). Census keys map: `text-input`→`bw-text`, `select`→`bw-select`,
`boolean-input`→`bw-boolean`.

## 3. The version arithmetic

| surface | from → to | bump class | why MINOR |
|---|---|---|---|
| plugin-ui (standards family) | 0.3.1→**0.4.0** | MINOR | new §E.1 components (additive contract surface); the schema delta is re-stamp only (§0.3) |
| plugin-ui-class-reference (standards family) | 0.1.0→**0.2.0** | MINOR | layout vocabulary widening (control kinds + text/select/boolean); copy-never-move; multi-serving family (both versions stay servable) |
| benchweave-ui-html | 0.2.1→**0.3.0** | MINOR | new renderer partials (additive; contract surfaces extended, none changed) |
| benchweave-sdk | 0.14.0→**0.15.0** | MINOR | new derivation/census capability; corpus sync; pin advance |
| gateway pointer | v0.14.0→**v0.15.0** | pairing | gitlink + `.gitmodules` pin + `sdk_compatibility` mirror in ONE commit; matrix render as its own commit (CON-12, the L1 shape `eff7e48e`/`c796ea30`) |

Copy-never-move: the 0.3.1 dir and its four corpus rows stay digest-frozen; the 0.1.0
family dir and its three rows stay digest-frozen. New rows cite the predecessors as
`source` (the founding-convention chain visible in the corpus manifest:
`plugin-ui/0.3.1/*` rows cite `0.3.0` paths; `plugin-ui-class-reference/0.1.0/*` cite
the `docs/` authoring paths).

**Cross-constraints row (RC-5's landed row must move WITH the bump):** the landed row
(`standards/cross-constraints.json`) reads `plugin-ui-class-reference 0.1.0 requires
plugin-ui >=0.3.1,<0.4.0`, evidence citing the program record. When plugin-ui serves
0.4.0 only, that known-good window is dead — a dead window standing reads as
known-good, which is dishonest. The row amends IN PLACE to `0.2.0` / `>=0.4.0,<0.5.0`,
evidence re-cited to THIS design record. One row, not a second row (the file's own
note: rows are honest windows; add a row only with its citation).

## 4. The corpus-motion census (exact bytes)

Gateway repo, `standards/`:

- **Added** `standards/plugin-ui/0.4.0/`: `ui-manifest.schema.json`,
  `binding-catalogue.schema.json`, `configuration-preset.schema.json`,
  `presentation-envelope.schema.json` — each a 0.3.1 byte-copy with `$id`, the
  `contract_version` const(s), and titles re-stamped 0.4.0 (the 0.3.0→0.3.1 shape,
  verified zero other delta). Plus unpinned prose: `MIGRATION.md` (0.3.1→0.4.0: the
  trio, the wall, re-stamp guidance), `README.md` (trio note in the authoring prose),
  `validation-report.md`.
- **Added** `standards/plugin-ui-class-reference/0.2.0/`:
  `class-reference.schema.json` (re-stamp only), `layout.schema.json` (the widening:
  `control.kind` enum `["button","numeric","rotary"]` → `["button","numeric","rotary",
  "text","select","boolean"]`; `contract_version` const 0.2.0; `$id` 0.2.0), and
  `class-logic_analyser.json` (contract_version re-stamp to 0.2.0 only — zero content
  change; the reference targets `>=0.3.1`, still satisfied by active 0.4.0; the D2
  census holds: "0.2.0" is a dotted version string, not a pure numeric).
- **Changed** `standards/standards-manifest.json`: plugin-ui entry version 0.4.0
  (supersedes 0.3.1, released = bump date, `normative` = the 0.4.0 schema paths +
  `src/benchweave/presentation/contracts.py`); classref entry version 0.2.0 (supersedes
  0.1.0, `normative` = the 0.2.0 rows).
- **Changed** `dependency_policy.standards."plugin-ui"`: range `>=0.3.1,<0.4.0` →
  `>=0.4.0,<0.5.0`; `versions` map gains the 0.3.1 migration row; note updated (0.3.1
  pins re-stamp to 0.4.0; single-serving posture unchanged until deferral D2 closes).
- **Changed** `dependency_policy.standards."plugin-ui-class-reference"`: range
  `>=0.1.0,<0.2.0` → `>=0.1.0,<0.3.0` (multi-serving widens; both versions servable).
- **Added** `standards/corpus-manifest.json`: exactly **7 rows** —
  `plugin-ui/0.4.0/ui-manifest.schema.json`,
  `plugin-ui/0.4.0/binding-catalogue.schema.json`,
  `plugin-ui/0.4.0/configuration-preset.schema.json`,
  `plugin-ui/0.4.0/presentation-envelope.schema.json` (sources = the 0.3.1 paths) and
  `plugin-ui-class-reference/0.2.0/class-reference.schema.json`,
  `plugin-ui-class-reference/0.2.0/layout.schema.json`,
  `plugin-ui-class-reference/0.2.0/class-logic_analyser.json` (sources = the 0.1.0
  paths). Digests written **only** by `benchweave.standards repin` (CON-7).
- **Changed** `standards/cross-constraints.json`: the row amendment named in §3.
- **Layout-block compatibility consequence (design decision):** `validate_layout_block`
  (`src/benchweave/presentation/classref.py:1495`) validates against the ACTIVE
  family version unconditionally. Post-bump, in-flight 0.1.0-authored blocks
  (`contract_version: "0.1.0"` const) would fail `classref_layout_invalid`. Accepted,
  deliberately: the only 0.1.0-block authors today are the SDK expander (re-derives at
  0.2.0), the SDK test fixtures (re-stamp in the same train), and the ui-html
  class-capture page data (regenerates in the same train — its drift guard re-points
  from `tests/ui_html/test_classref_page.py:18`'s 0.1.0 path to the 0.2.0 path). No
  external block author exists (the family is two days old in-tree at L5's branch
  point). The alternatives (const accepting two values, or per-block version routing)
  are refused: the first breaks the closed-const convention, the second is new
  architecture where re-derivation is the precedent (principle 9).

Gateway repo, code:

- `src/benchweave/presentation/contracts.py`: three literals (line 20 `SCHEMA_ROOT`,
  lines 247 and 372 guards) 0.3.1→0.4.0. **No other validator change** — the component
  census in §0.2 is the evidence. The version-literal ZERO gate's provenance rows
  register the motion (the 0.3.1 precedent shape in
  `scripts/standards/count_version_literals.py:535-550`).
- `src/benchweave/interfaces/ui_presentation.py` `compose_layout_sections`
  (line 954) / `_section_children` (line 989): three new arms mirroring the
  numeric/rotary arm (lines 1045–1060) — a `bw-classref-control` span with the field
  label + the disabled `no-authority` label, per new kind. The gateway page is
  read-only (B5/CON-5: zero enabled controls); the trio render **disabled with reason
  `no-authority`**, never enabled — no control authority crosses the read-only
  boundary (CON-5/L4 amendment's "no control authority" line holds byte-for-byte).
- `tests/presentation/test_classref_derive.py` + `tests/ui_html/test_classref_page.py`:
  corpus-path re-points (0.1.0→0.2.0 literals at lines 286/324/335 and line 18) and
  the 9 committed parity fixtures (`tests/fixtures/classref/fixture-{f1,f2,f1-da}-
  {envelope,manifest,catalogue}.json`) regenerate byte-level (the manifest/envelope
  contract_version stamps move to 0.4.0; the embedded layout block to 0.2.0).
- `packages/ui-html` (**PR-1**, §5): three partials `render_text_input` /
  `render_select` / `render_boolean` + data classes (`TextInputData`, `SelectData`,
  `BooleanInputData` in `data.py`) + templates + `contract_harness` rows + canonical
  fixtures (the harness reds until fixtures exist — the mechanism at styleguide:260)
  + a pattern-library composition page exposing the trio (the census rule: every
  component state carries fixture+row+page). Version 0.3.0.

SDK repo:

- `src/benchweave_sdk/standards/` + `standards-lock.json`: the sync ingests 0.4.0 +
  0.2.0 (lock rows carry `active` markers: plugin-ui@0.4.0 active, family@0.2.0 active,
  predecessors retained rows).
- `src/benchweave_sdk/classref.py`:
  - `_field_rows` (line 463): new modes — `type: string` without pattern → mode
    `"text"`; `type: boolean` → mode `"boolean"`; enum rows already emit mode "enum"
    (the widening teaches the layout/render lanes to consume it); **pattern-narrowed
    strings emit no row** (inexpressible — RC-L5-3/4 defer both sides).
  - `_ladder_level` (line 497): the L2 test widens from all-required-numeric to
    all-required-in-{numeric, text, enum, boolean}, with the expressibility test
    per-field: const present, or enum present, or numeric, or (string without
    pattern), or boolean. Host-supplied subtraction unchanged (line 511).
  - `_build_layout` (line 1245) + `_insert_ladder_numerics` (line 1387): the
    `mode == "numeric"` gates become per-mode kind mapping (numeric→`"numeric"`,
    text→`"text"`, enum→`"select"`, boolean→`"boolean"`; const still emits no node).
  - `derive_ui`'s expectation derivation (line 1241): the per-action field counts
    gain the trio (counts derive — no expect-expression vocabulary change, RC-L5-2).
- `src/benchweave_sdk/classref_gate.py`: `census_map` (lines 159–168) gains
  `text-input`→`bw-text`, `select`→`bw-select`, `boolean-input`→`bw-boolean`; the
  census walker (lines 64–82) counts the three hooks.
- `src/benchweave_sdk_server/web.py` `node_html` (lines ~457–576): three arms for the
  new layout kinds rendering the 0.3.0 partials with the effective schema's
  bounds/options (today those kinds return `""` at line 576 — the widening makes the
  census countable).
- `tests/fixtures/classref/`: the 9 parity fixtures regenerate; **new fixture F5**
  (`descriptor-f5-trio.json` + a vendor catalog `vendor-catalog-trio.json`): an
  invented vendor action (`com.veridian-labs.auto-band/1.0.0`) whose input schema
  requires a free string (`label`), an enum (`band_class`), and a boolean
  (`holdoff_enable`) — the widening's proof surface (the existing vendor fixture is
  all-numeric and proves nothing about the trio).
- `pyproject.toml`: version 0.15.0; `[server]` extra `benchweave-ui-html==0.3.0`;
  `uv.lock` moves with it (obligation 10: dependency motion disclosed).
- `standards-lock.json`: `compatibility.sdk = "0.15.0"` (the lock-anchor ritual, INSIDE
  the SDK repo before tagging — the v0.7.0→v0.7.1 precedent; #473's lesson extends the
  release-review walk to version literals inside tests, the #155 shape already on
  main).

## 5. The merge-order choreography (L1-proven shape)

**Owner-fixed landing order: SDK release → gateway pointer → #465.** The structural
constraint set: `check-sdk-standards`'s served-set comparison is bidirectional and
exact (`src/benchweave/standards/check.py:276-288` — `served_set_drift` fires both
ways; `pinned_sdk_incompatible` at lines 296-299 for an id absent from the lock);
`make release-cut` publishes from main; the SDK's `[server]` pin resolves from PyPI.
The L1 PR (#464) is the in-tree proof of the resolution: its branch carried the
pointer advance itself (PR diff `packages/sdk b4cb491e..fa945019` — pointer + corpus
in ONE gateway PR), so no served-set window is observable on any branch CI sees.
Choreography:

1. **Gateway PR-1** (`feat/classref-l5-renderer`, from main): the ui-html trio
   (partials, data classes, templates, harness rows, fixtures, pattern-library page) +
   `ui-contract.md` §E.1 11→14 + `ui-styleguide.md` rows (+ device-developer-guide
   prose via the document-writer agent, STE register). **No standards motion, no
   pointer motion** — green in isolation (Tier 2). Merge; cut release `ui-html-v0.3.0`
   from main → `publish-ui-html` pipeline → PyPI. (The publish job's guard skips
   non-`ui-html-v` releases — the gateway `v*` releases publish nothing.)
   - The wincore ratchet needs no motion: the core set is keyed on W1 platform units
     (`tests/win_core_manifest.json` — cli/, interfaces/supervision, state/hold,
     supervision.py; no ui_html files).
2. **Gateway branch PR-2** (`feat/classref-l5-corpus`, rebased on post-PR-1 main):
   gateway-side authoring — the corpus motion (§4) + contracts.py + the consumption
   arms + test re-points + fixture regenerations + the class-capture page data
   regeneration + cross-constraints row + CON-5 amendment + drift-doc row. **During
   this phase the branch is red on `served_set_drift`** — a disclosed, branch-internal
   window; the branch never merges in this state (red-main doctrine: nothing merges
   while its own lanes are red).
3. **On PR-2's branch:** submodule init; `make sync-sdk-standards` ingests the branch
   corpus into the vendored tree + lock; submodule commits pushed; **SDK PR opened
   NOW** (stacked on nothing; body notes the gateway issue #463; no SDK-side issue by
   design): the SDK widening (§4 SDK side) + pin `==0.3.0` + version 0.15.0 + the
   lock-anchor ritual + docs + the release-review walk (enumerating version literals
   INSIDE tests — #473). Merge when green.
4. **`make release-cut VERSION=v0.15.0`** in the SDK repo → tag → SDK CI green.
5. **PR-2 gains the pointer-advance commit** (gitlink → the v0.15.0 tag commit;
   `.gitmodules` `pin = v0.15.0`; `sdk_compatibility` mirror 0.15.0; matrix render as
   its own commit) → branch green on all lanes → **PR-2 merges** (corpus + pointer in
   one PR — the L1 shape; zero observable window).
6. **PR #465** (`chore/classref-nit-folds`, parked at `.wt/classref-gw-c7k2` — its
   worktree stands, untouched by this train) rebases onto post-L5 main and merges.

**The standards tripwire fires BY DESIGN on PR-2**: `git diff origin/main...HEAD --
standards/` is non-empty (the 0.4.0 + 0.2.0 motion). This record is the owner-worded
sanction: the bump is the row's named content (D4 amended for RC-9 only). Nobody
treats the tripwire hit as a leak; the governor pass is mandatory (rubric Step-1).

## 6. Invariant and drift impacts

- **CON-5** gains an amendment row: the G2 read-only device surface's layout
  consumption gains three disabled-control arms (the trio at `no-authority`) — same
  read-only posture, no control authority, the amendment names
  `ui_presentation._section_children`'s trio arms. (The L4 landing omitted its promised
  CON-5 amendment — the B4-fold adversary finding; this slice lands its amendment WITH
  the change, not after.)
- **CON-7** unchanged mechanically (repin writes the 7 new rows only;
  verifies-but-never-rewrites the frozen predecessor rows — the acceptance rule B5
  asserts the row-level diff).
- **CON-13** (version stamps a pure function of committed state): the matrix render
  commit follows the pointer; website stamps regenerate mechanically.
- **Version-literal ZERO gate**: the moved contracts.py literals + the corpus $id
  strings register provenance rows (the 0.3.1 precedent). The gate runs all five
  scopes in `gates` (CI map) and the SDK scope in `make check-sdk-standards`.
- **Obligation rows moved:** obligation 6 (vendored contract bytes ↔ corpus-manifest
  pins — the 7 new rows); obligation 10 (dependency change: SDK pyproject + uv.lock
  together); the adapter-agreement test's version triplet (obligation 8) moves with
  the SDK version; operator/device-developer docs via document-writer (STE register);
  the ui-styleguide + ui-contract surfaces (§2); the fixture lattice is untouched
  (fixtures/registry/ — no registry motion in L5).
- **No new invariant needed.** The trio inherit the existing staging/§C.1 rules; the
  layout consumption stays a read-only projection (CON-5 L4 amendment's terms).

## 7. Review tier and Step-1 keyword scan (#254)

**Tier call (per slice):**
- **PR-1 (renderer): Tier 2** — rule: "Any other change to production or test code
  under ... `packages/ui-html/` (code, config, and manifests: the renderer package,
  its templates and vendored assets — including the contract-gate harness)"
  (rubric:47-49). Docs-only paths would be Tier 1, but the diff spans Tier-2 code
  paths; first match wins at the path rule.
- **SDK PR: Tier 3** — rules: diff text carries `sha256`/`hashlib` (lock/fixture
  digests, sync tests); adds/re-pins a dependency (`pyproject.toml` + `uv.lock` — the
  0.3.0 pin).
- **PR-2 (corpus): Tier 3** — rules: touches `standards/` + JSON Schema files;
  advances the `packages/sdk` submodule pointer; diff text carries `sha256`/`hashlib`
  (corpus rows, repin-adjacent tests, this record). Maximum across slices = **Tier 3**;
  two-lane adversary per the Tier-3 rule (retro R3: two independent lanes,
  deliberately) on the SDK PR and PR-2; standards-governor mandatory on PR-2 (and on
  the SDK PR's vendored-tree/lock touch per the mandate's "plugin contract locks, SDK
  vendored tree" arm).
- **#465**: parked nit-fold branch; its review ran at park time; rebase + merge under
  the standing orders; its rebase delta (if any) re-runs the fast lane.

**Step-1 keyword scan over the expected diff** (all three PRs, docs and code alike;
estimates — the review re-derives on the real diff):

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~20–35 | 7 new corpus rows (`sha256` key each), sync/lock tests, fixture digests, this record |
| `hashlib` | ~3–6 | gateway classref/repin-adjacent tests, SDK sync tests |
| `protection` | ~2–4 | this record's §C.1/A04 prose; zero in code (no new protective surface — the trio's staging posture is disclosed via the required-text line, not a protection literal) |
| `threading` | 0 | — |
| `asyncio` | 0 | the gate's ASGI client stays sync httpx |
| `subprocess` | 0 | in-process render; the check lane is in-process |
| `migrate` | 0 | no state/format migration (the manifest re-stamp is derivation, not migration) |
| `recovery` | 0 | — |

## 9. Acceptance rules (pre-committed — written before any build output)

Deterministic census on the fixed fixture set (F1/F2/F1-da parity trio, F3a/F3b, the
refusal fixtures, F5 — the §3.5 set plus F5). Denominators are the named fixture
counts; both kill directions stated; the underpowered branch named. **These rules bind
the build agent; tuning them after seeing data is the failure this project guards
against hardest.**

- **B1 — the mandated no-regression arm (byte-parity over the landed L4 surfaces).**
  (a) The 9 committed parity fixtures regenerate to byte-equality **9/9** on BOTH
  repos (gateway derivation ≡ committed SDK fixtures; the only deltas are the
  re-stamped version strings). (b) The L4 layout-consumption and parity tests pass
  UNMODIFIED except corpus-path literals (the test-file diff = path re-points only);
  (c) a re-stamped 0.2.0 block whose kinds ⊆ {button, numeric, rotary, data-table,
  reading-tile} renders `compose_layout_sections` output containing **zero**
  `bw-text`/`bw-select`/`bw-boolean` occurrences, byte-equal to its pre-widening
  rendering. Kill: any byte divergence beyond the version re-stamp, or a test file
  changed beyond path literals, or the old-kind rendering gaining a trio hook.
  RED check (mechanism load-bearing): neutralize the trio arms in `_section_children`
  → B1 stays green (the old path untouched) while B2 reds; revert the expander
  widening → B2 reds. Underpowered, not conclusive: if the parity fixtures cannot
  regenerate byte-equal for reasons OUTSIDE the version re-stamp (a derivation change
  smuggled in), the arm is instrument-broken — report, don't pass.
- **B2 — the trio renders (SDK host).** F5's vendor action derives **L2** with exactly
  **3** layout nodes (text/select/boolean, one per field); the SDK host's page renders
  census `bw-text` **1/1**, `bw-select` **1/1**, `bw-boolean` **1/1**; gate PASS with
  the derived expectation's trio counts 1/1/1. Kill: any census 0/1, a doubled control
  (which would also catch the L4 open row F3's doubling if that defect is live on the
  trio path — the acceptance structurally folds F3 there), or a kind/kind mismatch.
- **B3 — the ladder widens and narrows correctly.** F5's action derives L2 (was L0
  pre-widening — RED against unmodified v0.14.0 code); `decode` **stays L0** (protocol
  enum becomes expressible; `line_map`/`settings` objects keep it inexpressible); 
  `trigger` **stays L1** (its only required field `acquisition_id` is host-supplied —
  catalog bytes at `standards/otdp/0.2.3/device-profile-catalog.json`, verified); 
  `arm` stays L2; `configure` stays L3. Kill: any level flip among the stays, or F5
  deriving L0 with the widening in place.
- **B4 — the record's A-rules survive the bump.** A1, A9, A10 re-run green on the
  re-stamped corpus (0.2.0 family / 0.4.0 plugin-ui): trigger button **1/1**,
  partial group **1/1**, 7/7 coverage with 2 declared deviations. Kill: any A-rule
  count off — which would falsify this design's catalog-grounded claim that the
  widening leaves the class fixture's derived levels unchanged (the falsifier
  pre-named in the record's own R2).
  Known-honest text correction inside B4: the record §2.5's stated reason for
  decode's birth deviation ("enum settings inexpressible") narrows post-L5 — protocol
  becomes expressible; the objects keep decode at L0. The F3b fixture's declared
  reason text updates to name the objects (honest prose; the deviation itself is
  unchanged).
- **B5 — corpus and version gates.** `benchweave.standards check` clean (served-set
  agreement incl. the new lock rows); `matrix --check` clean; `repin` wrote **exactly
  the 7 new rows** (row-level diff: 7 added, 0 rewritten among frozen predecessors);
  version-literal ZERO gate clean with the provenance rows registered. Kill: any
  frozen-row rewrite, any unregistered literal, any served-set disagreement.
- **B6 — the harness and the census coverage rule.** §E.1 rows **11→14**; the contract
  harness collects the 3 new rows with their fixtures (**3/3** fixture'd rows) and the
  pattern-library census shows fixture+row+page for each trio component (**3/3**).
  Kill: a row without a fixture (the harness reds by construction — that red IS the
  arm working), or a component without a page.
- **B7 — the coverage arm stays honest.** The gate's D14 coverage arm passes F5
  (every declared action rendered-or-declared: the trio action reachable at L2);
  deleting F5's layout emission (a permutation control: neutralize the kind mapping)
  reds `classref_gate_uncovered` for the trio action. Kill: an undeclared action
  passing, or the control not reddening when neutralized.
- **B8 — release/version gates.** The lock anchor (`compatibility.sdk = "0.15.0"`)
  verified in the SDK repo BEFORE the tag; gitlink ↔ `.gitmodules` pin same-commit;
  the #408 order held (SDK PR merge → release cut → pointer commit → PR-2 merge →
  #465); PR-2's `standards/` diff non-empty WITH this record cited as the sanction.
  Kill: an anchor landed after tagging (the v0.7.1 forced-patch precedent), a pin
  disagreeing with the gitlink (`sdk-drift` exit 1), or an order inversion.

**Underpowered branch (global):** if the census cannot key the trio on
contract-pinned surfaces (the 0.3.0 harness rows are the authority; a renderer change
that moves them reddens the harness first), that is a measurement-instrument failure —
reported, not a pass/fail on the increment (the program record §6's own clause).

## 10. Top risks, each with its falsifier

- **R1 — the layout-block version const breaks in-flight 0.1.0 blocks.** Accepted and
  bounded (§4's consequence block): the only 0.1.0-block authors are the expander,
  test fixtures, and the class-capture page data, all re-derived in-train. Falsified
  if an external block author surfaces mid-train (then the const must accept the
  declared version's schema — a design amendment, not a silent tolerate).
- **R2 — the widening shifts a pre-committed A-rule level.** Grounded against catalog
  bytes (§4/§9 B3/B4): trigger stays L1 (host-supplied), decode stays L0 (objects),
  configure L3 by slot-kind, arm L2. Falsified if B4's A-rule re-run flips any count —
  then this design's catalog reading was wrong and the widening is re-scoped (the
  record's own R2 falsifier).
- **R3 — ui-html publish ordering.** The SDK pin resolves from PyPI; if the
  `publish-ui-html` pipeline fails or lags, the SDK PR cannot merge. Falsified if the
  wheel is absent at SDK-CI time (then the release re-cuts; the pin does not float —
  an exact pin never floats).
- **R4 — the Served-set window on PR-2's branch.** Disclosed branch-internal red
  (§5.2) during authoring; never merged red. Falsified if a branch CI observation is
  demanded mid-window (then the corpus commits and the SDK sync must interleave
  tighter — the L1 interleave is the remedy, not a gate change).
- **R5 — F3's vendor-control doubling live on the trio path.** If the L4 open row's
  doubling defect is live in the widened `_build_layout`, B2's census (1/1/1) reds —
  the acceptance catches it structurally. Falsified if B2 passes with visible doubled
  controls (a census keying gap — the instrument rule).
- **R6 — A02 pressure via the trio.** The trio are staging components whose bounds
  render from the effective schema's intersection; a bound invented at render time
  (an absent bound rendering a default limit) is the A02 breach class. Falsified by
  B2's bound-honesty assertion (absent bound → absent attribute — assert the ABSENCE
  literal).

## 11. Row-calls (numbered; the principal alone decides; none written by default)

- **RC-L5-1 — the five display idioms (group bracket, annotation chips, on-axis
  markers, derived frequency, position badges).** DEFER to the sweep (L11–L21) under
  the styleguide:268 rule; any §E.1 rows they need batch into the next contract bump
  after L5 (the wall-payment event). Why it can't land in-slice: the record's L5 row
  names the input trio only; absorbing five display idioms doubles the increment for
  no record anchor. Recommendation: ACCEPT the deferral; the batching rule honors the
  D4-amendment logic. Reopen trigger: the first sweep design record that needs an
  idiom.
- **RC-L5-2 — reference-authored trio assertions (widening §3.4's closed expression
  vocabulary).** DEFER. The gate asserts the DERIVED trio counts (the expectation
  document carries them from the widened `_field_rows`); no reference needs to author
  trio expectations for L5's fixtures. Reopen trigger: a class reference that must
  assert or forbid trio counts (e.g. forbid text inputs where free text is
  unacceptable).
- **RC-L5-3 — catalog-side pattern→finite-alternation select derivation** (the
  program record §3.7's literal-alternation rule). DEFER. No L5 fixture needs it (the
  catalog's string patterns sit on non-required or object-nested fields — verified);
  a string-with-pattern emits no row (inexpressible, D13-safe) until this lands.
  Reopen trigger: a real class whose required top-level string fields carry
  finite-alternation patterns.
- **RC-L5-4 — constraint-side `pattern` admission** (adding `pattern` to
  `input_constraints`' closed intersection vocabulary). DEFER — it stays refused
  (`classref_constraint_unsupported`) per the landed closed vocabulary (record §3.7's
  own list excludes it); widening a D13 surface wants its own adversarial pass.
  Reopen trigger: a descriptor whose constraints must narrow a string field by
  pattern.
- **RC-L5-5 — the expect-expression `n_text_fields`-style names.** Merged into
  RC-L5-2 (the same mechanism, named separately only if the principal splits it).

## 12. Precedent map (principle 9)

| L5 surface | in-tree precedent | why it fits |
|---|---|---|
| plugin-ui 0.4.0 re-stamp-only schema delta | 0.3.0→0.3.1 ($id/const/title-only diff, verified) | the substantive change lives in the live code row + renderer, exactly the 0.3.1 shape |
| family 0.2.0 layout widening via copy-never-move | plugin-ui-preview 0.1.0→0.1.1→0.2.0 chain (rows cite predecessors) | same multi-serving data-only family shape (no code row) |
| trio §E.1 rows | the 11 existing rows' schema (div-rooted, BEM hooks, staging line, A02 bound honesty) | the inventory's own conventions |
| gateway disabled-control arms | `_section_children`'s numeric/rotary arm (ui_presentation.py:1045-1060) | same read-only posture, new kinds |
| SDK render-lane arms | `web.py node_html`'s numeric arm (lines 511-534) | same per-kind derivation from the effective schema |
| partials + harness rows + fixtures + page | the 11 components' own machinery (fixtures.py, contract_harness) | the coverage census rule (styleguide:260) |
| cross-constraints row amendment-in-place | the RC-5 row's own citation rule (the file's note) | one honest window, re-cited |
| pointer-in-the-corpus-PR | L1 PR #464 (diff `packages/sdk b4cb491e..fa945019`) | the zero-window shape, proven in-tree |
| lock-anchor ritual | #91 shape (v0.6.0); v0.7.1 forced patch is the counter-precedent | structural satisfiability of the tag |

## 13. Appendix — evidence and disclosures

**Gortex refusal (quoted):** first `mcp__gortex__read` of
`src/benchweave/presentation/classref.py` — error text exactly as returned:
`repository not tracked: /Users/seaton/Documents/src/BenchWeave`. Same failure class
as the 2026-10-15/16 run ledger ("gortex refused ALL .wt worktree paths all session —
'repository not tracked'"), now also refusing the primary checkout (the filed
upstream issue pattern, gortex #831). **GORTEX UNAVAILABLE for this session; every
source read in this design is a disclosed native fallback** (Read/Bash on indexed
paths), per the dispatch's disclosed-fallback rule. The one hook interception (a
`find -name "*classref*"` symbol-match block) was routed around per the hook's own
regex-metacharacter suggestion; no daemon restart, no store deletion.

**Commands cited for this record's measurements** (all on the worktree or named
checkouts, `UV_PROJECT_ENVIRONMENT=venv` posture): the sorted-key schema diff
(`diff <(python3 -m json.tool --sort-keys ...)` over the four 0.3.0/0.3.1 pairs), the
manifest census (`python3 -c` json reads of standards-manifest/corpus-manifest/
cross-constraints/win_core_manifest), the grep censuses (contracts.py component
vocabulary: zero hits; OTDP catalog action schemas; §E.1 rows; styleguide idioms), the
git archaeology (#464's diff and CI rollup via `gh pr diff 464 --name-only`,
`gh pr checks 464`, `gh run view --job 116182637180 --log`, the pointer commits
`eff7e48e`/`c796ea30`/`616d73d0`), and the CI history query (main runs
2026-10-14→15, all green; no window observed).

**Correction to the dispatch's framing, recorded for the build agent:** the program
record's §7A table and §8's RC-9 row are the scope authority; the session handoff's
"L5 = the 5 cannot-express items" line is **superseded by this record's §1
reconciliation** (the handoff conflated the record's L5 with the sweep-era idiom
backlog). The handoff's "component backlog" phrase should not appear in the build
brief for L5; the five idioms' deferral rows (RC-L5-1) carry forward instead.

**Interfaces this design leaves untouched on purpose:** the MCP tool surface (no tool
change — the trio ride existing manifest/render lanes), REST/openapi (no operation
change), the CLI (`derive-ui`/`verify-ui` names and flags unchanged), the vendored
standards corpus identity block (CON-8 closed world unchanged — the two families sit
outside it), the device-developer guide's structure (prose rows only, via
document-writer/STE).
