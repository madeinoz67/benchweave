# UI standard, renderer-neutral component contract and safety-relevant definitions — design of record (issue #242)

**Date:** 2026-09-28
**Status:** Design complete — build may start on slice 1
**Issue:** madeinoz67/benchweave#242
**Scope of this record:** the split of `docs/internal/ui-styleguide.md` into a normative
renderer-neutral contract and implementation guidance, and the safety-relevant
definitions (issue items 1–6), as three serialized slices.
**Triage:** public-safe — no person, client, bench, DUT serial, commercial term, or
install-specific operational detail appears in this record or its numbers. All fixture
identities are invented (`DAQ-01`, `PSU-01` family). The colour measurements were taken
against this repository's own token values, not a real bench. Promoted to the public
directory deliberately on that basis.

**Branch plan:** `feat/issue242-*` off `main` @ `82f8dc9`. This record is committed in
the FIRST commit of slice 1's branch, before any acceptance test lands — that ordering is
what makes the acceptance rules in §6 provably pre-committed.

---

## 0. Verdict and headline decisions

BUILD, as three serialized slices. The issue's "one change" is honoured as one work (one
issue, serialized slices on the shared styleguide surface); it is not honoured as one PR,
because the diff would span docs, renderer behaviour, computed colour tokens, and a
two-repo pointer movement — unreviewable blast radius against this repo's own increment
rule (minimal, reviewable increments naming their deferrals). The issue closes after the
last slice merges.

Five headline decisions, each with its evidence section:

1. **The contract lives at `docs/internal/ui-contract.md` (unversioned docs), not under
   `standards/`.** Promoting it to a versioned standard would move standards bytes and
   take the full bump obligation set — under the active #203 hold window that slice would
   be HELD. The issue's WANTED wording ("splits `docs/internal/ui-styleguide.md`") places
   both halves in docs; a versioned home is deferred (row D1).
2. **`--bw-series-1` REPLACES the accent role in plots; it is not `--bw-accent`.** The
   issue's own non-confusion clause ("no series hue reusable as, or confusable with, a
   severity hue") is unachievable with the accent hue as series-1: measured ΔE00(accent,
   success) = **3.59** (light) / **3.13** (dark) under simulated tritanopia — an order of
   magnitude below any defensible non-confusion threshold (§7). The issue sanctions the
   escape ("equal to **or replacing** the accent role").
3. **Series-slot assignment is a pure function of (the plot's declared channel id set, the
   id) — canonical bytewise sort of the declared set.** Per-id-only binding cannot satisfy
   fixed assignment order plus 16-unique-style coverage (pigeonhole + collision, §4.3);
   set-relative canonical order is the minimal mechanism and is host-deterministic: the
   same declaration renders the same colours on every host.
4. **The pin is mechanical and two-sided.** A contract-internal fixture pin (rows cannot
   vanish) plus a generated renderer pin (the reference renderer must render every
   contract-required attribute) plus a contract↔CSS value-equality pin (the "executable
   mirror" rule made testable). No acceptance item rests on assertion.
5. **Three slices, not one PR.** Slice 1 is docs+tests only (single repo); slices 2–3 are
   two-repo (they change the built preview renderer, which is committed in the SDK).
   Items 1–4 land as definition rows in slice 1 and as enforced behaviour in slice 2; the
   plot-series values and sequences land in slice 3. The DONE WHEN ("a host can be built
   from the normative contract alone") is the issue-level criterion, reached when slice 3
   merges.

---

## 1. Mechanism

### 1.1 File layout

| File | Before | After |
|---|---|---|
| `docs/internal/ui-contract.md` | — | NEW. Normative, renderer-neutral contract (the split's (a)). |
| `docs/internal/ui-styleguide.md` | the guide (normative + guidance mixed) | implementation guidance for the reference React/Storybook renderer (the split's (b)); filename kept so inbound links (`README.md:59`) keep resolving |
| `docs/internal/ui-styleguide-workbench-design.md` | design authority | unchanged — design rationale, cited as history |
| `docs/internal/ui-styleguide-mockup.html` | portable visual reference | unchanged; stays a visual aid (aria-label pin as today) |
| `ui/src/storybook-coverage.test.ts` | pins guide sections + mockup labels | repointed: section assertions move to the contract; mockup assertions stay |
| `ui/src/contract-coverage.test.ts` | — | NEW. L1 fixture pins + contract↔`tokens.css`/`themes.css` value equality |
| `ui/src/contract-enforcement.test.ts` | — | NEW. L2 generated renderer assertions (per-component contract rows → rendered attributes) |

The guide's opening states the authority chain explicitly: `ui-contract.md` is normative
and self-contained; this file is how the reference renderer implements it;
`ui-styleguide-workbench-design.md` is the historical design rationale.

The contract's authoring rule (normative, stated in its preamble): definition and
component contracts are pipe tables with a fixed column schema; the enforcement test
parses those tables, so a table that does not parse is a pin failure, not a silent skip.

### 1.2 What the contract contains (items 1–6)

**§A Tokens.** The existing token tables (14 colour tokens × 2 themes, spacing, radius,
the two font tokens) move verbatim from the guide, and typography roles stay renderer
guidance; `tokens.css`/`themes.css` remain the executable mirror. Plus (slice 3) `--bw-series-1…8` × 2 themes, the dash sequence
(`dash-1` solid, `dash-2` fixed pattern) and the symbol sequence (8 framework-neutral
shapes). The mockup stays a visual reference and is not part of the equality pin.

**§B States and severity model.** The six severities with meanings and dismissal classes
(moved from the guide's alerts section), and the three state rules SR-B1 (placement and
persistence), SR-B2 (glow) and SR-B3 (acknowledgement).

**§C Safety rules (issue items 1–3), as definition rows:**

- **R-ENERGISE-1** — an action is *energy-sourcing* iff it closes a path for energy to
  reach the DUT: enabling an output, or changing a setpoint of a currently-energised
  output. An energy-sourcing action requires a confirmation step whose text states (i)
  the effect ("the output will be energised"), (ii) the exact values to be applied
  (value + unit), (iii) the target (which output/channel). The initial control stages
  only; the confirm is a second explicit action.
- **R-DEENERGISE-1** — an energy-removing action (output off) is ONE action, never
  confirmed, never gated. Nothing in the UI may stand between the operator and
  de-energising (A04).
- **R-PROTECT-1** — energy-sourcing actions are disabled with reason `protection-active`
  while a protective trip is active.
- **Disabled-reason enum** — 5 keys with required label text (fixed, machine-checkable;
  `device-state` carries one named-state slot):

  | key | required label text | parameter |
  |---|---|---|
  | `capability-absent` | `Not available on this device` | — |
  | `device-state` | `Device must be {state}` | the blocking state (canonical example: `idle`) |
  | `protection-active` | `Protection trip active` | — |
  | `invalid-staged-input` | `Staged value is invalid` | — |
  | `no-authority` | `No lease or policy authority` | — |

  The control carries `data-bw-disabled-reason="<key>"`; the label text renders visibly
  beside the control (`data-bw-disabled-label`), not aria-only. `no-authority` absorbs the
  old single "permission-disabled" story state.
- **Refusal mapping table** — one row per interface 0.1.0 error code (the full 14:
  `invalid_request`, `unauthenticated`, `forbidden`, `not_found`, `conflict`,
  `policy_denied`, `not_ready`, `gone`, `cursor_expired`, `event_gap`,
  `payload_too_large`, `rate_limited`, `unavailable`, `internal_error`) plus one
  **no-response** row. Columns: code → severity → required message elements (what
  happened / whether anything was sent / what the operator can do). For every interface
  code the "sent" element is **NO** — an error response means the operation was not
  accepted and nothing was dispatched; for the no-response row (transport failure or
  timeout, no interface answer) it is **UNKNOWN — the request may have been sent** (A06),
  with the operator action "do not retry blindly; reconcile via run identity/dedup".
  Claim-discipline note carried in the table: the "nothing was sent" claim is only as
  strong as interface 0.1.0's error semantics; a future code that can mean "accepted
  then failed" must not join this table without a distinct sent-status.
  `not_found` wording must not leak existence (interface contract: not_found is also the
  scope-invisibility answer) — "unavailable to this caller", never "does not exist".
  Severity defaults (owner-confirmable, §10): `not_found`/`not_ready`/`gone`/
  `cursor_expired`/`rate_limited` → advisory; the remaining refusals → warning;
  `unavailable` → critical (gateway loss = loss of the observation and protection
  channel); no-response → critical.

**§D ModeBanner (issue item 4).** A persistent, non-dismissible banner on every page,
first element of the page's main region. One entry per active mode, fixed wording, fixed
order. Absence of the banner asserts full-authority presentation. Tone advisory; element
`data-bw-mode-banner`, each entry `data-bw-mode="<mode>"`, region labelled "Presentation
mode". Modes and fixed wording (the `simulated` string is pinned by existing SDK
console/TUI/tests and must not drift):

| mode | fixed wording | fires when |
|---|---|---|
| `simulated` | `SIMULATED PRESENTATION DATA` | presentation data is simulated/preview |
| `no-gateway` | `NO GATEWAY · LOCAL PRESENTATION ONLY` | the host presents without a gateway behind it |
| `no-lease` | `NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED` | no bench authority exists behind actions |
| `no-policy` | `NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE` | no policy engine is configured |

The existing `SIMULATED` device badge (device-level fixture state) is a different
question and stays a device badge; unification is deferred (row D4).

**§E Per-component contracts (issue item 6).** One row family per component: element
structure, ARIA roles, state and severity attributes, `bw-*` class hooks, required text.
Components (row identifiers, pre-committed): `button`, `numeric-input`, `rotary-control`,
`reading-tile`, `alert-bubble`, `engineering-plot`, `data-table`, `panel` (slice 1),
`mode-banner`, `confirm-action` (slice 2). The `engineering-plot` row gains its
series-assignment sub-rows in slice 3. Mechanical pin covers attributes/roles/required
text; structural narrative and example HTML are prose (reviewer eye + example fixtures).

**§F Icon set.** Framework-neutral icon keys keyed by severity/state: 6 severity keys
(neutral/success/advisory/warning/critical/trip) + 3 state keys (busy/hidden/staged),
each with a shape description and a reference binding table to the lucide names the
reference renderer uses today (`CircleHelp`, `CheckCircle2`, `Info`, `TriangleAlert`,
`AlertCircle`, `ShieldAlert` from `ui/src/components/feedback/severity.tsx`). Any icon
set can bind from the shape descriptions.

### 1.3 Plot-series assignment (issue item 5)

For a plot with declared channel id set `Y` (plugin-ui `$defs/plot` `y`, `maxItems: 16`
— `standards/plugin-ui/0.2.0/ui-manifest.schema.json`, cited not restated):

1. Sort `Y` bytewise lexicographically (UTF-8 byte order) → index `i` (0-based).
2. colour = `--bw-series-((i mod 8) + 1)`; dash = `dash-1` if `i < 8` else `dash-2`;
   symbol = `symbol-((i mod 8) + 1)`.
3. Uniqueness across the 16-ceiling: (colour, dash) pairs distinct; (symbol, dash) pairs
   distinct — the second is the monochrome/dash-only reproduction arm (8 symbols × 2
   dashes = 16 unique styles with no colour at all).
4. Assignment is computed over the FULL declared set — hiding (`channel_hints.visible:
   false`) or reordering display never restyles any trace. Disclosed residual: adding or
   removing a declared channel re-derives the plot's slots (the set changed); the issue
   requires invariance only for hide/reorder, and set-relative binding is provably
   necessary for fixed order + 16-unique coverage (§4.3).
5. `channel_hints` compose on top via pass-2 hint bias, with the existing arbitration
   semantics preserved (`EngineeringPlot.tsx` `resolveStyles` pass 2 — earliest visible
   accent claim wins, muted releases its claim only when the muted token exists):
   `color_role: "accent"` → `--bw-series-1` (the plot's emphasis role — the "replacing"
   of the accent role; the hint means emphasis, not UI-chrome colour),
   `color_role: "muted"` → `--bw-text-muted`, `visible: false` → not drawn.
6. Severity hues remain legal in plots ONLY for elements that carry that severity
   meaning — today exactly the threshold mark line (which keeps its severity colour). A
   severity-neutral series may never resolve to a severity hue. Series-level severity
   declaration has no wire flag (plugin-ui `channel_hints` is a closed
   `accent|muted|visible` shape and is not touched) — deferred, row D3.

The current defect this replaces: `EngineeringPlot.tsx` `resolveStyles` pass 1 assigns
`color: index === 0 ? tokens.accent : tokens.alert` and `symbol`/`lineType: index % 2` —
traces 2+ all take the **alert severity colour** and only two styles repeat. Root cause
verified by reading the source (file `BenchWeave/ui/src/components/plots/EngineeringPlot.tsx`,
`resolveStyles`, pass-1 defaults); the issue's description of the defect is accurate.

### 1.4 The pin machinery (what makes it measurable)

- **L1 — contract-internal fixture pins.** `contract-coverage.test.ts` parses the
  contract's tables and asserts every row named in the §6 enumeration exists (definition
  rows, component rows, token rows, icon rows). RED on row removal.
- **L2 — generated renderer pins.** The same test generates one assertion per
  contract-required attribute/text of each *enforced* component row (enforced-row fixture
  grows slice by slice, enumerated in §6) and renders the reference component asserting
  the attribute/text is present. RED when the renderer drops a contract-required
  attribute. Row additions without implementation red by construction (the generated
  assertion appears the moment the row exists).
- **L3 — contract↔CSS value equality.** Every pinned token value in the contract's tables
  equals the computed value parsed from `tokens.css`/`themes.css` (both themes). The
  guide's existing prose rule ("the CSS files are their executable mirror; a change to
  either requires the other to change in the same commit") becomes a test.

---

## 2. Root cause

The issue states the mechanism correctly; verified against source:

- `ui/src/components/plots/EngineeringPlot.tsx` (`resolveStyles`, pass-1 defaults):
  `color: index === 0 ? tokens.accent : tokens.alert`, `symbol: index % 2 ? diamond :
  circle`, `lineType: index % 2 ? dashed : solid`. Confirmed: alert-colour fallback for
  traces 2+, two-style repeat. (`tokens.alert` is correct for the threshold mark line —
  only the series-defaults use is wrong.)
- The styleguide's only series rule ("charts use accent first, then severity colours only
  when the series itself has that meaning") leaves a severity-neutral second trace with no
  legal colour — confirmed in `docs/internal/ui-styleguide.md` (Colour palette closing
  rule).
- Disabled states: `DeviceWorkbench.tsx` renders `disabled={!requestEnabled}` with no
  reason; the guide's Required stories name only "permission-disabled". Confirmed.
- Confirmation: no confirm flow exists anywhere in `ui/` (`DeviceWorkbench` submits
  `onRequestSetPoint(stagedVoltage)` directly). Confirmed.
- Host-mode indicator: `PreviewApp.tsx` renders `SIMULATED PRESENTATION DATA`; no other
  mode is defined. Confirmed.

---

## 3. Slice plan

Slices share `ui-contract.md` and `ui-styleguide.md`, so they serialize: slice 2 parks at
review-complete and rebases once after slice 1 merges; slice 3 likewise (repo pipelining
rule). Each slice is independently landable and carries its own acceptance rule.

### Slice 1 — the split + contract skeleton + mechanical pin

**Repo shape:** main only (docs + `ui/` test files; no `ui/src` behaviour change, so the
built preview bundle is byte-identical — the renderer-freshness gate proves it).
**Tier:** Tier 2-equivalent (test tree + docs). The rubric's tier rules do not classify
`ui/` TypeScript (Tier 2 is Python-scoped, Tier 1 is docs-only) — recorded as finding
F1 / deferral D2.

Scope: `docs/internal/ui-contract.md` (new; items 1–6 as definition rows, component rows
for the 8 existing components, tokens moved verbatim); `docs/internal/ui-styleguide.md`
restructured to implementation guidance; `storybook-coverage.test.ts` repointed;
`contract-coverage.test.ts` (L1 + L3) and `contract-enforcement.test.ts` (L2 for the 8
existing components) new; `drift-and-obligations.md` row 12 amendment naming the contract
as the normative surface and these tests as its gate; `README.md` link addition;
`docs/device-developer-guide.md` presentation-section pointer update (obligation 12).

**Defers to slice 2:** ModeBanner/confirm/disabled-reason/refusal *behaviour* in the
renderer (their definition rows land here; their component rows and L2 enforcement land
with their implementations).
**Defers to slice 3:** series token values, assignment implementation, sequences.
**Defers to rows:** §11.

### Slice 2 — safety behaviours in the reference renderer (items 1–4 enforcement)

**Repo shape:** two-repo. `ui/src` changes (ModeBanner component; Button
`data-bw-disabled-reason` + visible label; confirm-action pattern in `DeviceWorkbench`
(Output on/off pair + setpoint-apply confirm stating values) and `PreviewApp`; refusal
rendering per the mapping table at the presentation boundary) → `build:preview` rebuilds
the committed `preview_assets` → **SDK PR first** (commit inside the standalone
`benchweave-sdk` checkout, push, open the SDK PR), **then** main-side pointer commit +
ui/tests + contract rows (AGENTS.md two-commit discipline, stacked PRs under one gateway
issue). Example proof fixtures: a bench PSU workbench page and a multi-channel DAQ page,
invented identities. New component rows (`mode-banner`, `confirm-action`) + enforcement
fixture growth land in the same change as the implementations (L2 reds otherwise).
Stories for every new state (guide rule 5). `docs/device-developer-guide.md` presentation
section moves again (obligation 12).

**Defers:** series tokens → slice 3; wording polish beyond fixed strings → rows.

### Slice 3 — plot-series tokens, assignment, sequences (item 5)

**Repo shape:** two-repo (same shape as slice 2).
Scope: `--bw-series-1…8` in `tokens.css` + `themes.css` (values chosen under the §6
constraints; the §7 candidate palette is the starting point; `ui/package.json` version is
NOT bumped in this increment — deferred to the next ui release train so no version string
moves under the hold-window tripwire); the assignment algorithm in `resolveStyles` pass 1
(index-derived defaults → id-set-derived slots; pass 2 preserved with its accent-token
binding moved to `--bw-series-1`); dash + symbol sequences (8 framework-neutral shapes;
where the chart library lacks a shape, the reference binding uses a custom SVG path —
implementation guidance, not contract); `engineering-plot` contract sub-rows + L2
enforcement (legend items expose their slot, e.g. `data-bw-series-slot`); the computed
colour-proof tests (T1/T2/T3, dual CVD models); the 16-ceiling uniqueness tests; the
hide/reorder invariance tests; the example-fixture proofs (6-channel DAQ draws 6 distinct
series tokens, zero invented colours; threshold mark line keeps its severity colour).
Existing `EngineeringPlot.test.tsx` arbitration expectations evolve only where they pin
the old index-based defaults — each change carries its RED witness.

**Defers:** series-level severity declaration (row D3); plot kinds beyond
time-series/waveform (already deferred by the guide); `ui/package.json` bump (row D5).

---

## 4. Precedent

1. **`ui/src/storybook-coverage.test.ts`** already reads `docs/internal/ui-styleguide.md`
   and asserts section presence and mockup aria-labels — the doc-pin precedent; L1 is
   this mechanism extended from section-headings to table rows, and L3 is the
   "executable mirror" prose rule made mechanical.
2. **CON-12/CON-13/CON-14** (`docs/internal/invariants.md`) — "X is a pure function of
   committed bytes" with a machine check (compatibility-matrix render; website version
   stamps; dependency resolution). The contract↔CSS↔renderer pin is the same shape
   applied to presentation: rendering is a pure function of committed contract + token
   bytes. No new invariant number is required; row 12 of the drift doc carries the
   obligation.
3. **Obligation 7's renderer-freshness gate** (`ci.yml` `ui` job: rebuild `build:preview`,
   `git -C packages/sdk diff --exit-code`) — the precedent for pinning a built surface to
   its source, and the reason renderer slices are two-repo.
4. **`standards/interface/0.1.0/interface-contract.md`** — a normative contract document
   with machine artefacts alongside; our contract is the docs-internal analogue (no
   schema artefacts; the pipe tables are the machine-readable shape).
5. **plugin-ui `$defs/plot` `y.maxItems: 16`** — the 16-trace ceiling is cited from the
   standard, never restated as our own number.

---

## 5. Invariant and cross-surface impacts

- **Decisions touched:** A02 (missing requirements block control → `capability-absent` /
  `no-authority` disabled reasons are the presentation of a blocked control, never a
  silently-defaulted one); A04 (protection and completion never depend on continued AI
  judgement → R-DEENERGISE-1 is absolute; the confirm pattern may slow an energise but
  must never stand between operator and de-energise; energise is blocked while protection
  is active); A06 (evidence over assertion → the refusal table's "whether anything was
  sent" element, and the no-response row's UNKNOWN, are the UI face of dispatch-state
  honesty). A13 (one core contract behind REST and MCP → the UI contract is the one
  renderer-neutral face behind any host renderer).
- **Invariants:** no new CTL/STO/CON/REG number. The pin is a test, not an invariant
  statement; if the contract is later promoted to standards (row D1), CON-3-style
  vendored-exact pinning applies there.
- **Drift-and-obligations:** row 12 amended (contract named as the normative surface for
  plugin-visible rendering behaviour; `contract-coverage`/`contract-enforcement` named as
  its gates). Row 7 (renderer freshness) fires for slices 2–3. Row 4 (operator-visible
  behavior) does not fire — no operator-facing behaviour changes. The device-developer
  guide's presentation section (`docs/device-developer-guide.md` around the
  `channel_hints` / presentation-envelope text) moves in slices 1–2 (obligation 12).
- **CI map:** no new jobs. Slices 2–3 add SDK CI load (preview_assets commit + SDK gates)
  and main-repo `ui` job work (build:preview ~unchanged). Colour-math tests are pure
  computation (hundreds of ΔE00 evaluations — milliseconds).
- **SDK / plugin-ui blast radius:** `packages/sdk` is touched ONLY as committed
  `preview_assets` (built renderer bytes) in slices 2–3. No standards corpus, manifest,
  contract lock, `standards-lock.json`, or `benchweave_sdk/standards/` byte moves. The
  plugin-ui and plugin-ui-preview schemas are untouched (`channel_hints` enum stays
  `accent|muted`). The SDK PRs note the cross-repo gateway issue (single issue stream).
- **Finding F1 (durable, defect pattern):** `docs/internal/review-rubric.md` Step 1's
  tier rules leave `ui/` TypeScript unclassified — Tier 2 names Python paths, Tier 1 is
  docs-only, so a renderer change silently matches no tier rule. This increment is the
  first to depend on the classification. Filed as the one follow-on issue candidate
  (§11 row D2).

---

## 6. Pre-committed acceptance rules

Written before any build measurement. The row/token/component enumeration below IS the
pre-commit: the L1/L2 fixtures must cover AT LEAST this set (superset allowed; subset is
a kill). A reviewer checks the test fixtures against this enumeration.

**Common to all slices (gate doctrine):**
- Every acceptance item carries a RED witness in the PR: the mechanism disabled (row
  deleted / attribute dropped / token value changed) turns the check red before the fix.
  A check without a RED witness is a failed check (fluff cannot pass).
- Gates run with true exit codes (unpiped / `PIPESTATUS` / output-to-file), `uv run mypy`
  bare with fresh cache, `uv run ruff check .` bare; focused `uv run pytest` + `ui`: bare
  `npm test` exit code, and counts read from junitxml attributes or exit codes, never
  from a filtered summary line.
- Standards-hold tripwire at design AND push: `git diff origin/main...HEAD -- standards/`
  empty and no standards version-string touches. For two-repo slices the SDK diff must be
  limited to `src/benchweave_sdk/preview_assets/`.
- Kill directions are binary per row; the "underpowered" direction is named per slice
  below and means the measurement cannot decide the claim — it is never a pass.

### Slice 1

| # | Metric | Effect size (N) | Pass (ship) | Kill | Underpowered |
|---|---|---|---|---|---|
| S1-A1 | L1 fixture rows present in `ui-contract.md` | enumeration below (D-rows 5+15+4+3+3+6+9 = 45 definition rows; C-rows 8 component rows; T-rows 14 colour × 2 themes + 6 spacing + 2 radius + 2 fonts; I-rows 9 icon rows) | 100% present, parsed from the contract's tables | any enumerated row missing or unparsable | if the fixture were editable to shrink with the doc — controlled by this enumeration; reviewer verifies fixture ⊇ this list |
| S1-A2 | L3 contract↔CSS equality | 14 colour tokens × 2 themes + 6 spacing + 2 radius + 2 fonts | all values equal the parsed `tokens.css`/`themes.css` values | any mismatch in either direction | if a token exists in CSS but not in the contract enumeration — the enumeration is the floor; an extra unpinned token is a review finding, not a pass |
| S1-A3 | L2 renderer enforcement for the 8 existing components | 8 rows × their required-attribute sets (attributes, roles, required-text strings as the contract states them) | every required attribute/text present on the rendered component | any required attribute absent from the rendered output | if the contract row were weakened to match the renderer — controlled by S1-A1's enumeration and the RED witnesses |
| S1-A4 | Slice shape | standards/ diff empty; SDK pointer unmoved; bundle byte-identical (renderer-freshness gate green) | all three hold | any fails | — |
| S1-A5 | RED-sanity | every S1 check has a witnessed mutation that reds it | 5/5 witnesses in the PR message | any check without a witness | — |

### Slice 2

| # | Metric | Effect size (N) | Pass (ship) | Kill | Underpowered |
|---|---|---|---|---|---|
| S2-A1 | L2 enforcement for `mode-banner`, `confirm-action`, disabled-reason, refusal rows | 2 new component rows + 5 disabled-reason labels + 15 refusal rows' required text elements | 100% rendered | any missing | as S1-A1 |
| S2-A2 | Example-fixture proof (PSU + DAQ, invented identities) | 5 properties: (a) energise confirm text states the exact values+unit+target; (b) de-energise is one action with NO confirm step; (c) energise disabled with `protection-active` while a trip is active; (d) ModeBanner present with exact fixed wording on every page; (e) every disabled control carries its reason's required visible label | 5/5 on both fixtures | any property failing | if a fixture could pass vacuously (e.g. no energise action present) — the fixtures must each contain an energy-sourcing and an energy-removing action; enumerated in the fixture definitions |
| S2-A3 | RED witnesses | the confirm, the protection guard, the disabled-reason label, the ModeBanner wording each have a mutation that reds S2-A1/A2 | 4/4 | any missing | — |
| S2-A4 | Cross-surface | preview_assets committed in the SDK (PR open, pushed) + main pointer advanced + standards/ diff empty + device-developer-guide presentation text updated | all hold | any fails | — |

### Slice 3

| # | Metric | Effect size (N) | Pass (ship) | Kill | Underpowered |
|---|---|---|---|---|---|
| S3-A1 | T1 contrast on the actual token values (parsed from CSS) | 8 tokens × 2 themes = 16 contrast ratios vs `--bw-surface-recessed` | all ≥ 3.0:1 | any < 3.0 | if the parser mis-reads a value — pinned by S1-A3's equality against the contract table |
| S3-A2 | T2 severity non-confusion | 8 tokens × 5 severity hues × 4 viewing conditions × 2 themes = 320 ΔE00 values | all ≥ 10.0 | any < 10.0 | if the two CVD models disagree on any pair's verdict (both models must pass; disagreement = inconclusive for that pair → escalate the threshold or redesign the slot before merge) |
| S3-A3 | T3 adjacency | 7 adjacent slot pairs × 4 conditions × 2 themes = 56 ΔE00 values | all ≥ 8.0 | any < 8.0 | dual-model disagreement as S3-A2 |
| S3-A4 | Assignment pin | fixed order (sorted set → slots exactly per §1.3); hide/reorder invariance (sibling style objects deep-equal after hide or reorder) | both hold; the 16-ceiling test shows 16 declared ids → 16 distinct (colour,dash) and 16 distinct (symbol,dash) pairs | any restyling of a sibling under hide/reorder; any duplicate style pair below the ceiling | — |
| S3-A5 | Severity-hue discipline | the DAQ fixture's severity-neutral series never resolve to a severity hue; the threshold mark line retains its severity colour | both hold | any severity hue on a neutral series; threshold recoloured | — |
| S3-A6 | RED witnesses | token value perturbed (contrast red), series hue swapped with a severity hue (T2 red), assignment switched back to index (S3-A4 red) | 3/3 | any missing | — |
| S3-A7 | Cross-surface | as S2-A4; plus `ui/package.json` version unchanged | all hold | any fails | — |

**Pre-committed thresholds (stated before the §7 computation was run, and unchanged
after):** T1 ≥ 3.0:1 (WCAG 2.2 non-text contrast); T2 CIEDE2000 ≥ 10.0 per pair per
viewing condition {normal, deuteranopia, protanopia, tritanopia}; T3 CIEDE2000 ≥ 8.0 for
adjacent slots. CVD model: Machado et al. 2009 severity-1.0 matrices; the robustness arm
runs a second independent model (Viénot 1999 for prot/deut, Brettel for trit) and both
must agree. Colour distance: CIEDE2000 on CIELAB (D65).

---

## 7. Colour feasibility — measured evidence and one honest negative

Computed 2026-09-28 against this repository's own token values
(`ui/src/styles/themes.css`), script archived at `/tmp/bw-series-feasibility.py`
(deliberately not committed; the build's tests are the durable artefact). Thresholds as
§6.

**Negative result (first-class): `--bw-accent` cannot be `--bw-series-1`.**

| pair | min ΔE00 over 4 conditions (light) | min ΔE00 (dark) | worst condition |
|---|---|---|---|
| accent vs success | **3.59** | **3.13** | tritanopia |
| accent vs advisory | 6.77 | 7.45 | tritanopia |

The issue's requirement set — series-1 equal to the accent role AND no series hue
confusable with a severity hue — is over-constrained in both themes. Under tritanopia the
teal accent and the mint success hue collapse to within ΔE00 ≈ 3.5, far below any
non-confusion threshold. The issue's own "or replacing" clause is the resolution:
`--bw-series-1` is a new token taking over the accent's plot role. (Accent still
satisfies T1 — 4.45 light / 9.37 dark — so this is purely a severity-confusion failure.)

**Positive result: the replacing reading is comfortably achievable.** With series-1
free, a search over LCh hues (L bands 30–58 light / 52–82 dark, C 15–70, H 0–355 step 5)
found **342** (light) and **479** (dark) candidate hues clearing T1+T2 simultaneously; a
greedy 8-slot set exists in BOTH themes at T3 = 8.0 with worst adjacent pair ΔE00 = 12.43
(light) / 14.48 (dark). The palette is not knife-edge. Candidate slot sets (starting
point for the build, not mandated values):

- light: `#9b7882, #055043, #003dac, #940000, #858360, #7e1f62, #70839b, #eb3b70`
- dark: `#9f7074, #009c3b, #aed7f4, #a7810a, #f6c1ee, #756ce5, #c4db8f, #709892`

Caveat carried forward: ΔE00 ≥ 10 admits slots whose hue ANGLE is near a severity hue
(e.g. a dark-red slot near critical red) — colourimetrically distinguishable, not
hue-family-clean. The tests enforce the computed properties; hue-family hygiene when a
slot has freedom is build-time guidance (row D6). If a reviewer can narrate a plausible
operator misread on a passing slot, the threshold escalates (severity can go up, not
down) — that is an S3 kill path.

**Monochrome reproduction:** dash alone gives 2 groups; dash-only reproduction of 16
traces is impossible. The symbol sequence is therefore load-bearing, not decorative: 8
symbols × 2 dashes = 16 monochrome-unique styles. The issue's suggestion to let symbols
carry CVD uniqueness is adopted — T3 (adjacency) is the only hue constraint relaxed from
pairwise-all-pairs to adjacent slots, and only because (colour, dash, symbol) give three
independent identity channels. T2 (severity non-confusion) is NOT relaxed anywhere: a
series mistakable for a trip/critical marker is the safety property.

---

## 8. Top risks

| Risk | Falsifier / mitigation |
|---|---|
| **R1 — the contract tables are the machine interface and markdown parsing is fragile.** A table format drift could silently skip a row. | L1's fixture fails closed: a row the parser cannot find is a missing row (kill), not a skip. The contract's preamble normatively fixes the column schema. Falsified if a parse failure can present as a pass — the build must show a parse-failure RED witness. |
| **R2 — two-repo slices (preview_assets + SDK pointer) can desync** and ship a stale renderer or a pointer to an unpushed commit. | Obligation 7's renderer-freshness gate is mechanical (CI reds on any diff); AGENTS.md's two-commit order (SDK push → pointer) is the procedure. Falsified if CI can go green with the committed bundle differing from `ui/` sources — the gate is `diff --exit-code`, which cannot. |
| **R3 — the enforcement fixture and the contract could be edited together to stay green (the gaming channel).** | The §6 enumeration is committed in this record before the tests; review checks fixture ⊇ enumeration; every check carries a RED witness that must not depend on the fixture. Falsified if a reviewer cannot reproduce a red from a stated mutation. |
| **R4 — accent-hint → series-1 remap diverges from #59's "existing theme tokens" intent.** | plugin-ui README (0.1.1/0.2.0): "a host composites them under its own theme authority" — the token binding is host-authority, not standards-pinned; the enum bytes do not move. Owner-confirmable (§10). Falsified if any standards byte names the accent token — none found (searched). |
| **R5 — EngineeringPlot's 18 KB of existing tests pin arbitration semantics that the pass-1 rewrite could break.** | Pass 2 is preserved verbatim; only pass-1 defaults change. Each evolved expectation carries its RED witness. Falsified if an arbitration semantic (accent-claim, muted-claim, threshold carrier) changes without an intentional, witnessed test change. |
| **R6 — the no-response refusal row outruns interface 0.1.0's semantics** (claiming "may have been sent" where the gateway guarantees non-dispatch). | The row is about the NO-RESPONSE case (no interface answer at all), where A06 already mandates UNKNOWN. The table's claim-discipline note bounds the "nothing sent" claim to interface codes. Falsified if interface 0.1.0 documents transport-level dispatch guarantees — it does not (the contract preserves ambiguity). |
| **R7 — build mechanics: `build:preview` writes into `packages/sdk/...` while the local submodule is deinitialized** (standing rule), so a builder can pollute the main checkout or fail mid-slice. | The design fixes the END STATE (SDK repo carries preview_assets bytes; main carries the pointer) and the ordering; the builder arranges the build output into the standalone `benchweave-sdk` checkout (a worktree of main with the submodule populated, or a copy of the built `site/` + `inventory.json`). Guard-first commit discipline catches stray untracked files. Falsified if a green slice-2 PR shows untracked preview output in main. |

---

## 9. Standards-involvement verdict: **CLEAN**

Checked both directions at design time:

- `standards/` embeds or derives nothing from the guide's tokens: the corpus has no
  styleguide reference; the plugin-ui schemas define `channel_hints` as a closed
  `accent|muted|visible` shape with NO token names; the plugin-ui README explicitly
  delegates token binding to "its own theme authority" (host-side). The 16-trace ceiling
  is READ from `plugin-ui/$defs/plot` `y.maxItems: 16`, not restated as our number.
- The interface error codes are READ from `standards/interface/0.1.0/interface-contract.md`
  (the mapping table cites the corpus; adding a code would be a standards change and is
  out of scope).
- No slice moves corpus bytes, either manifest, contract locks, standards version
  strings, or the SDK vendored standards tree (`benchweave_sdk/standards/`,
  `standards-lock.json`). Slices 2–3 move ONLY `src/benchweave_sdk/preview_assets/` in
  the SDK — a built renderer, not the standards vendoring — plus the main-side submodule
  pointer (a SHA, not a version string).
- `ui/package.json` is not bumped in any slice (row D5) so no renderer_version string
  moves either.
- Tripwire per slice: `git diff origin/main...HEAD -- standards/` empty; SDK diff limited
  to `preview_assets/`.

If row D1 (contract promotion to a versioned standard) is ever taken up, THAT train moves
standards bytes and holds under the #203 window until it lands.

---

## 10. Owner decision rows

One genuine fork; one confirmable default bundle.

| Row | Question | Default taken | Why | Kill/change path |
|---|---|---|---|---|
| O1 | Refusal severities for the two judgement calls: `not_ready` → advisory (retryable when ready, no continuing risk) and `unavailable` → critical (gateway loss = loss of observation + protection channel). Also: `channel_hints` accent → `--bw-series-1` (emphasis role) rather than `--bw-accent`. | as stated | advisory persistence semantics would clutter for transient refusals; critical is the conservative direction (severity may go up); accent→series-1 is forced by the §7 measurement and is standards-clean (R4) | owner may flip `not_ready` to warning or `unavailable` to warning by a one-line contract change + test update (row-level, no mechanism change); accent→series-1 has no flip path without violating T2 — it would need the honest-residual disclosure instead |
| O2 | Fixed ModeBanner wording for the three new modes (§1.D table). | as stated | matches the pinned `SIMULATED PRESENTATION DATA` register; British spelling matches the interface contract's voice | wording is contract-text level; a docs PR amends it (the fixed-wording pin moves with it) — not a fork, listed so the voice is confirmed before slice 2 |

Everything else in this record is decided with stated evidence.

---

## 11. Deferral table

One follow-on issue is permitted per merged PR; the chosen candidate is named per row.
All rows use the `.claude/deep-review/README.md` deferral-row contract (identifier /
deferred / home / reopen trigger).

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | Promoting `ui-contract.md` to a versioned standard (standards train under GOVERNANCE, with corpus pins + SDK lock) | documentation here (this record) | a second independent host renderer is admitted or published that consumes the contract — the arrival is observable on the tracker/registry |
| D2 | Review-rubric Step 1 tier rule for `ui/` TypeScript (finding F1) | follow-on issue #N filed from slice 1's PR (the one allowed) | the follow-on issue's own merge |
| D3 | Series-level severity declaration in the wire (`channel_hints` severity role or equivalent) so a severity-meaning series can be declared, not inferred | documentation here | a plugin-ui standards train opens that adds a severity role to the channel-hint shape |
| D4 | Unifying the device-level `SIMULATED` badge with the page-level ModeBanner | documentation here | the admin console (#210) or a second host defines device-simulation presentation — the scoping issue or PR is the arrival |
| D5 | `ui/package.json` version bump (and its `inventory.json` renderer_version) for this increment's component additions | documentation here | the next ui release train opens (a version-bump commit in `ui/package.json`) |
| D6 | Hue-family hygiene refinement of the series palette (avoiding severity hue ANGLES, not just ΔE00) within the §6 constraints | documentation here | a reviewer narrates a plausible operator misread on a passing slot, or a second CVD model disagrees on a boundary pair (S3's underpowered arm) |
| D7 | Spectrum / digital / sweep / polar plot kinds' series rules (guide already defers these plot kinds) | documentation here (guide §Plots) | the complete-catalogue plot follow-on lands — its PR is the arrival |

---

## 12. Finding summary (for the ledger)

1. **Accent cannot double as a plot series token** (measured: ΔE00 3.59/3.13 vs success
   under tritanopia; 342/479 replacement candidates exist; 8-set feasible at T3=8 with
   worst adjacency 12.43/14.48). Proposed to the memory ledger.
2. **The review rubric's tier rules leave `ui/` TypeScript unclassified** (Tier 2 =
   Python paths; Tier 1 = docs-only). Proposed to the memory ledger.
3. **`build:preview` writes into the `packages/sdk` submodule path** while the local
   submodule is deinitialized — renderer slices are structurally two-repo and their build
   output must be carried into the standalone SDK checkout. Proposed to the memory
   ledger.
