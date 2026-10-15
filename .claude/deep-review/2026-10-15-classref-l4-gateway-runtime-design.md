# L4 gateway-runtime landing — class-reference consumption, fallback, panels

**Date:** 15 October 2026
**Scope:** program-sequence slot L4 of the class-reference train (parent record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` §7A-L4, the D11-amended
gateway landing). Three capabilities: (a) the no-manifest fallback, (b) gateway
production-host consumption of the `plugin-ui-class-reference:layout` block, (c) the
panel-registration surface with the host-owned analyser `class_panel`. DESIGN ONLY.
**Branch:** `feat/classref-l4-gateway-design` (off `origin/main` at `28008680`).
**Dependency state:** L1 landed (PR #464, family corpus on main incl. `layout.schema.json`);
SDK v0.13.0 released (the class-reference pairing, `eff7e48e`); L2's host-consumption task
(#131) is MID-BUILD in the SDK worktree — every assumption about the SDK emission shape is
marked §9 and must be confirmed by its lane's report before the L4 build freezes.

## 0. Code reality this design extends (read, not assumed)

- **The composition path.** `compose_device_presentation` —
  `src/benchweave/interfaces/ui_presentation.py:385` — resolves the plugin's
  presentation attachment from ADMITTED documents (envelope by schema-suffix +
  descriptor digest, its manifest, the trusted catalogue, declared assets), validates it
  through `presentation.admission.validate_attachment`
  (`src/benchweave/presentation/admission.py:14`) against `_presentation_documents()`
  (active plugin-ui schemas joined with every carried OTDP version's documents, each
  corpus file digest-verified against its manifest row — the #446 SW-41 parity fix,
  already landed). Honest absence: no envelope → `absence="no-attachment"`
  (`ui_presentation.py:411`).
- **The render surface.** `ui_templates/device.j2` renders the state: absence
  paragraphs, per-page flat `bw-panel` sections, tiles through the package's §E.1
  partial, dataset pages as TEXT skeletons ("`{kind}: {channels}` — no plotted data"),
  configuration pages as preset-id lists. The G2 device page is READ-ONLY; tiles
  populate only from gateway-reported observations (GW-22 — today every value renders
  `Unavailable`: interface 0.1.0 carries no live observation read).
- **Panels today.** `SUPPORTED_PANELS: frozenset[str] = frozenset()`
  (`ui_presentation.py:78`) — the gateway declares NO custom panels; a manifest
  `class_panel` page is the validator's own `panel_unavailable` finding, rendered by
  `device.j2` as the SW-41 refusal (required) or unavailable note (optional). Grep
  across `src/benchweave/`: **no panel-registration surface exists anywhere** — this
  landing creates it.
- **The composition precedent.** `packages/ui-html` `patterns.py` `PATTERNS` (a frozen
  registry serving both the checkers' fixtures and the library pages — "no second mirror
  to drift") and `compositions.py` (`psu_scene()` → `render_workbench`) are the proven
  host-owned composition mechanisms; the G3 control surface
  (`ui_control.py:264` `ControlViews`, `:566` `register_control_routes`) is where
  authority-aware controls and the §C.1 confirm machinery already live.
- **The landed vocabulary.** `standards/plugin-ui-class-reference/0.1.0/layout.schema.json`
  on main: pages ≤16, sections ≤16 with `span` 1–12, nesting depth 3 by construction
  (`section`/`nested_section`/`deep_section`), `control {binding_id, kind:
  button|numeric|rotary, field?}`, `reading {binding_id, kind: reading-tile|data-table}`,
  `plot_ref {plot_index 0–15}`, `text {body ≤512}`; the block rides the manifest
  `extensions` seam under the key `plugin-ui-class-reference:layout`; the canonical
  validator is extension-blind.

## 1. Capability (a) — the no-manifest fallback

**Mechanism: read-time derivation + the SAME validation path.** When
`compose_device_presentation` finds no admitted envelope (`absence="no-attachment"`) and
the descriptor carries a class profile for which the family corpus holds a reference, a
new gateway module (`src/benchweave/presentation/classref.py`) derives the attachment
triple — envelope, manifest, binding catalogue — from (descriptor × reference) and the
composition validates it through the unchanged `validate_attachment` call. The derived
documents NEVER enter the admitted store: the fallback is a read-time composition over
already-admitted bytes (the descriptor) plus corpus bytes (the reference) — no
`ContentStore` write, no admission event, no mutation of the accountability boundary
(A07 untouched: admission stays a plugin-owned act; a derived presentation is visibly
host-derived, never masquerading as admitted plugin content — the page carries
`data-bw-presentation-derived` and a visible "default class presentation — derived, no
plugin attachment" disclosure beside the page title).

**Derivation rules** (the parent record §3 semantics, gateway-side):

| input | rule |
|---|---|
| reference selection | `descriptor.profiles` sorted bytewise; the first profile with a reference in `standards/plugin-ui-class-reference/0.1.0/` applies; multi-profile descriptors merge per parent §3.8 (first bare, later `{slug}-` prefixed) |
| lanes / groups / bindings / pages | parent §3.1–§3.2 exactly (lanes = channels where `role=digital_input`, groups of 8, decimal labels, LSB-first members) |
| effective schema | parent §3.7 (catalogue ∧ `input_constraints`; closed vocabulary, refuse-unknown) — the derived settings schema is the effective document |
| fail-closed | the same typed refusals, `classref_*:` — rendered as the honest refusal with the finding's code, never a partial page |
| **unknown class** (no profile with a reference; vendor-only; custom devices) | **fail-open to today's behaviour** — the `no-attachment` absence note, byte-identical to the pre-L4 render. The fallback never invents obligations the descriptor does not create (the parent's D14 posture); refusing would break working plugins to no protective end |

**Parity (REG-4 — the SDK is not a gateway dependency).** The gateway implements its own
derivation; agreement with the SDK expander is pinned by committed fixture documents: the
F1 (2-channel) and F2 (32-channel d-series) descriptors live in the gateway tests, both
sides derive over the same corpus reference bytes, and B8 asserts canonical-JSON byte
equality of the derived triples. Precedent: `tests/sdk/test_adapter_agreement.py`'s
cross-repo pinning shape — here full document equality is pinnable because both sides are
pure functions of committed bytes.

## 2. Capability (b) — layout-block consumption on the production host

**Mechanism: structure composition of §E.1 partials, mirroring the SDK host's L2
approach.** A layout-aware pass in the device-page composition (the `PresentationPage`
build in `ui_presentation.py`, feeding `device.j2`) reads the manifest's
`extensions["plugin-ui-class-reference:layout"]` block, validates it against the corpus
`layout.schema.json` (digest-verified through the same `_verify_corpus_pin` walk the
document set uses — the family schema joins `_presentation_documents()`'s key discipline
as a separately-served, separately-pinned document), and composes:

| block node | gateway render |
|---|---|
| `section`/`nested_section`/`deep_section` | `bw-panel` sections with the declared `surface` (`data-surface` raised/recessed), `span` as the CSS-grid span (the styleguide's grid rule), title as the panel title — declaration order |
| `reading` (reading-tile) | the package's tile partial, inside its declared section (the existing `_tiles_for_page` tiles re-homed to their declared positions) |
| `reading` (data-table) | the package's data-table partial over the bound target's variable set |
| `plot_ref` | the page's declared plot skeleton, PLACED at the referenced position (today's text skeleton upgraded to the §E.1 figure skeleton where the G2 surface has one; no draw claim without data — GW-22/D3 unchanged) |
| `text` | panel body text, verbatim, ≤512 chars (author data; the reference authors none) |
| `control` | the §E.1 control partial (button / numeric-input staging pair / rotary) rendered **disabled with reason `no-authority`** — the §C.2 enum's own mechanism: `data-bw-disabled-reason` + the visible label text, exactly the contract's disabled-control shape (see the scope line below) |

**The read-only scope line (recorded, not papered over):** the G2 device page carries no
control authority — leases, procedure dispatch, the armed-confirm machinery (§C.1) all
live on the G3 control surface. A layout `control` node on G2 therefore renders its
contract-honest DISABLED state; enabling it (staging under lease, procedure-backed
buttons, §C.1 confirms) is the G3 integration — row-call RC-L4-1, not a silent cut.
This keeps A04's spine intact: nothing on the read-only surface can dispatch anything.

**Degrade rules:** a manifest without the block composes exactly as today (zero
regression — B6); a block failing `layout.schema.json` renders the honest refusal naming
`classref_layout_invalid` with the finding, never a partial composition (the same
posture as the SDK gate's refusal; the gateway renders the finding list it already
renders for invalid attachments).

## 3. Capability (c) — the panel-registration surface

**Mechanism: a gateway-owned panel registry, `SUPPORTED_PANELS` derived from it.** New
module `src/benchweave/presentation/panels.py`:

```
PANELS: Mapping[str, Panel]   # panel_id -> {title, renderer, source corpus pin}
# panel_id shape: the manifest's own ^[A-Za-z0-9][A-Za-z0-9._-]*/[0-9]+\.[0-9]+\.[0-9]+$
# host panels are gateway-owned: benchweave/classref-logic-analyser/0.1.0
# SUPPORTED_PANELS becomes frozenset(PANELS) — registration and declaration
# structurally cannot drift (the empty frozenset at ui_presentation.py:78 is replaced
# by the derived value; the drift shape is unrepresentable)
```

Precedent: `patterns.py`'s frozen `PATTERNS` registry (one registry serving checkers and
pages — no second mirror) and the validator's own consumption of `supported_panels`
(`ui_presentation.py:447`). The panel RENDERER is a host-owned composition (the
`compositions.py` `psu_scene` → `render_workbench` shape): it receives the composed page
data (bindings, tiles, plot declarations, the layout block) and renders §E.1 partials —
**no plugin code ever executes** (A05/NFR-S9 unchanged; the validator's "never imports
or executes that panel" rule stays true: the registry maps ids to GATEWAY functions).

**The analyser class_panel** (`benchweave/classref-logic-analyser/0.1.0`): the host-owned
rendering of the class reference's capture page — lane rails skeleton, run-group panel,
grouped sections — composed from the same §E.1 partials the generic pages use, versioned
with the family reference version. A manifest page of `kind: class_panel` with this
`panel_id` now VALIDATES (the `panel_unavailable` finding disappears — the panel is
registered) and renders the composition. An unregistered `panel_id` keeps today's SW-41
refusal path unchanged.

**Registration is a code act, deliberately.** Panels are executable host surface; their
admission is a gateway release (A05's trusted-extension posture), not a registry-record
act. The registry cites each panel's corpus pin (the family reference version it
renders) so the panel and the corpus bytes it interprets move in one reviewable unit.

## 4. Invariant walks (gateway runtime code — the §11 disclosure honoured)

- **A04 (protection never depends on AI; no client-side silent promotion):** untouched —
  no control path changes; G2 control nodes render disabled (§2); no new authority.
- **A06 (evidence over assertion):** untouched — no transport, dispatch or run-state
  change; the fallback composes read-only state and fabricates nothing (tiles stay
  `Unavailable` until gateway-reported observations exist — GW-22's rule inherited).
- **A07 (audit failure constrains new work):** untouched — the derived presentation
  performs no actions and writes nothing; admission (the audited act) is unchanged.
- **CTL/STO:** untouched — no `control/` or `state/` bytes move.
- **CON-4:** no standards bytes move in L4 (the family landed at L1); the corpus schema
  the layout validation reads is served through the existing digest-verified corpus
  walk. **CON-5** (one core contract; adapters): the `/ui` adapter's composition surface
  gains capabilities behind its existing adapter boundary — the CON-5 amendment's G2
  clause (read-only projections) holds; the design record amends the adapter's
  composition inventory in review.
- **REG-4:** the SDK is read-not-imported; parity is fixture-pinned (B8).
- **NFR-S9 (plugin content is data):** holds — the layout block is validated data
  interpreted by host code; panels are host functions; nothing plugin-authored executes.

## 5. Acceptance rules (pre-committed; denominators + both kill directions)

| # | rule (ship if) | kill if |
|---|---|---|
| B1 | logic_analyser descriptor, NO admitted envelope: derived presentation renders — pages **N/N** per the reference (capture + configuration), lane-group skeleton counts equal the derived inventory (F1: **2** channel rows + **1** group row; F2: **32** + **4**), with the derived-marker present | any count off, or the marker absent (masquerade) |
| B2 | every derived triple passes `validate_attachment` (`valid=true`) at composition time — **every render** | a render that proceeds on an invalid derivation, or any partial page |
| B3 | unknown-class descriptor (no reference): the `no-attachment` note renders **byte-identical** to the pre-L4 output | any wording/structure drift in the fail-open arm |
| B4 | layout-bearing manifest: sections render as `bw-panel` with declared `data-surface` and spans — **N/N** sections; tiles render INSIDE their declared sections in DOM order; plot skeletons at `plot_ref` positions; text verbatim | any section mis-shelved, order lost, or text mutated |
| B5 | G2 `control` nodes render disabled: `data-bw-disabled-reason="no-authority"` + visible §C.2 label on **all** of them; **0** enabled controls on the device page | any enabled control (an authority breach) |
| B6 | no-block manifests compose **byte-identical** to pre-L4; a schema-invalid block renders the `classref_layout_invalid` refusal, never a partial page | either regression |
| B7 | registered panel: a `class_panel` page with `benchweave/classref-logic-analyser/0.1.0` validates (`panel_unavailable` gone) and renders the composition; an unregistered panel keeps the SW-41 refusal; `SUPPORTED_PANELS == frozenset(PANELS)` mechanically | a drift between registry and declaration, or the refusal path regressing |
| B8 | parity: gateway-derived triples canonical-JSON **byte-equal** to the committed SDK-expansion fixtures on **2/2** fixtures (F1, F2) | any byte divergence (the two derivations disagree) |

RED controls: B3 and B6 pin the no-regression arms against the pre-L4 tree; B8's RED is
the pre-parity state (the gateway derivation absent → no triple to compare).

## 6. Row-call candidates (standing protocol — owner decides every row)

| RC | what | structural reason or "effort only" | recommendation |
|---|---|---|---|
| RC-L4-1 | G3 control-surface integration of layout controls (enabled staging, procedure-backed buttons, §C.1 confirms under lease authority) | structural: a separate surface whose safety machinery (leases, armed-confirm, dispatch) lives in `ui_control`/`ui_staging`; bolting enabled controls onto G2 would bypass it | defer to the G3 lane's own increment; this record slots it |
| RC-L4-2 | live plot drawing on the device page (skeletons → rendered figures) | structural: interface 0.1.0 carries no live observation read (GW-22's own finding); there is no data feed to draw | defer to the observation-read lane |
| RC-L4-3 | class panels for the other 11 classes | effort only — the composition mechanism is one registry entry each | roll into the sweep landings L11–L21 (each class landing adds its panel) |
| RC-L4-4 | D14-style Device-features fallback for vendor-only descriptors gateway-side | effort only — the mechanism composes; only the vendor-catalogue resolution is new work | defer to the L6–L10 window (post-#460/#461, pre-sweep) |

## 7. Review tier + keyword scan

**Tier 3** — triggered by the keyword rule (the diff carries `sha256`/`hashlib` in the
digest-verified layout-schema service, the derived-envelope digests and the parity
tests); the path rules alone would say Tier 2 (`src/benchweave/interfaces/`,
`src/benchweave/presentation/`; no `standards/` bytes, no state migrations). No
standards-governor mandate (no corpus motion) — but the governor MAY be dispatched for
the registry's corpus-pin citations if review prefers it. Expected-diff scan estimates
(review re-derives): `sha256` ~15–25, `hashlib` ~3–5, `protection` 0, `threading` 0,
`asyncio` 0 (the composition is sync), `subprocess` 0, `migrate` 0, `recovery` 0.

## 8. Top risks (each with its falsifier)

- **R1 — parity drift** (the two derivations diverge silently). Falsified by B8's
  byte-equality on the fixture set; a divergence is a design failure of the
  data-only-reference claim, not a test nuisance.
- **R2 — derived masquerade** (an operator reads the derived page as plugin-authored).
  Mitigated by the visible disclosure + `data-bw-presentation-derived`; falsified by B1's
  marker assertion or review finding the marker insufficient.
- **R3 — the disabled-control reading** (operators read `no-authority` controls as
  broken). Mitigated by the §C.2 label semantics; an owner UX call if review disagrees.
- **R4 — registry/corpus version skew** (a panel rendering against reference bytes it
  was not built for). Mitigated by the registry's corpus-pin citation + the family
  version in the panel id; falsified by a version-mismatch render.
- **R5 — L2 emission-shape assumptions** (§9). If the SDK lane's block placement or
  derived-document shape differs, B4/B8 fixtures change — caught at fixture-freeze, not
  in review.

## 9. Assumptions the L2 report must confirm (before the L4 build freezes)

1. The layout block rides the manifest's `extensions` map under the exact key
   `plugin-ui-class-reference:layout` (per `layout.schema.json`'s description and parent
   §2.6 — assumed; task #131's report confirms).
2. The SDK expander's derived triple (envelope/manifest/catalogue) and its canonical
   serialization — B8's parity fixtures freeze against the v0.13.0 output (assumed
   stable within the release; a v0.13.x re-pin updates the fixtures mechanically).
3. The expectation-document arithmetic (parent §3.4) is NOT consumed gateway-side: the
   gateway census re-derives counts from the reference directly, so only the triple
   needs byte parity — assumed, confirmed by (2).

## 10. Landing mechanics

One PR on this branch after review (adversary lane per Tier 3; the parent record's
governor posture applies only if corpus bytes move — they do not). Sequence position L4:
after L3 (pointer + pattern page); no dependency on L3's docs beyond the corpus and the
SDK release (both on main). Tests live in `tests/interfaces/` (composition, fallback,
layout, panels) + `tests/presentation/` (the classref derivation module) with the F1/F2
parity fixtures committed under `tests/presentation/classref_fixtures/`.

## 11. Public-repo discipline

All fixture devices invented (the parent record's "Veridian LA-32" d-series and the F1
class descriptor); no bench, client, serial or corpus identifiers.
