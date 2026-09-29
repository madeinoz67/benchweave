# BenchWeave UI style guide

**Status:** Implementation guidance for the reference renderer

**Normative contract:** [UI renderer-neutral component contract](ui-contract.md) — tokens,
severity model, safety definitions and component contracts are defined there. This file
is how the reference React/Storybook renderer implements that contract.

**Design history:** [UI style guide and workbench design](ui-styleguide-workbench-design.md)

**Portable visual reference:** [Layered Precision light/dark mock-up](ui-styleguide-mockup.html)

This guide is the implementation reference for humans and AI agents extending the BenchWeave UI. Storybook is the executable source of truth. `ui/src/styles/` owns tokens, `ui/src/components/` owns reusable behaviour, and `ui/src/compositions/` demonstrates supported product use.

The first slice establishes the Layered Precision design language and representative operator and administrative compositions. The approved design contains the full target inventory; absence from this initial slice does not authorise a one-off substitute.

## Non-negotiable rules

1. Reuse a semantic token and an existing component before adding a local variant.
2. Keep observation, staged input and committed action visibly separate.
3. Use severity names, icons, labels and messages; never encode state with colour or glow alone.
4. Keep plugin rendering host-owned and declarative.
5. Add tests and stories for every new component state.
6. Label simulation and evidence quality honestly.
7. Do not infer physical safety, permission or applied state from presentation success.

## Local commands

Run commands from `ui/`:

```sh
npm install
npm run storybook
npm test
npm run typecheck
npm run lint
npm run build
npm run build-storybook
```

The supported project runtime is Node.js 22 LTS. Dependency versions are exact in `package.json` and `package-lock.json`.

## Tokens

The token inventory and every token value are normative in the contract ([§A](ui-contract.md#a-tokens)). Implementation rules for the reference renderer:

- consume the CSS custom properties from `ui/src/styles/tokens.css` and `themes.css` — those files are the executable mirror of the contract tables, and the contract↔CSS value-equality pin in `ui/src/contract-coverage.test.ts` refuses drift in either direction;
- components must not hard-code a colour or shadow that conveys product meaning;
- a new semantic token is added to both themes in the same change, and to the contract table in the same change;
- hexadecimal values belong only in theme definitions, documentation and visual-test fixtures — never on a component.

Layout constants for the reference renderer:

- page content maximum width: `90rem`;
- page gutter: `1.5rem`, reducing to `1rem` below 48rem;
- minimum supported viewport: `20rem`;
- reading grid minimum tile width: `13rem`;
- plot minimum useful height: `15rem` desktop and `12rem` compact;
- table rows: minimum `2.5rem` target height;
- use CSS grid for device/plugin panels so unknown plugin compositions wrap without absolute placement;
- breakpoints are content-driven, with reference points at 30rem, 48rem, 64rem and 90rem; do not branch component behaviour by device name.

### Borders, elevation and shadows

Component boundaries use the standard border `1px solid var(--bw-border)`. Keyboard focus uses the focus outline `0.125rem solid var(--bw-focus)` offset by `0.125rem`. The raised and recessed shadows compose `--bw-shadow-dark`/`--bw-shadow-light` exactly as `tokens.css` defines them — the composition values are implementation, the colour inputs are contract tokens. The focus ring (`--bw-focus-ring`) and the standard transition (`--bw-transition-fast`) are likewise implementation tokens in `tokens.css`, not contract-pinned. The abnormal glow is `0 0 1.5rem` of the state colour at 32%, on the affected reading only (contract §B.2 SR-B2).

Elevation has three levels: canvas (0), recessed (-1) and raised (+1). Dialogs and menus may use +2 by strengthening the raised shadow once. Do not create arbitrary elevation levels or nest strong shadows.

### Typography

UI text uses `var(--bw-font-ui)`. Numeric readings, timestamps, identifiers and source evidence use `var(--bw-font-data)` with tabular numerals. Both stacks are contract tokens ([§A.4](ui-contract.md#a4-typography-fonts)); the role table below is implementation guidance.

| Role | Size / line height | Weight | Treatment |
| --- | --- | --- | --- |
| Page title | `2rem / 1.2` | 700 | Sentence case |
| Section title | `1.25rem / 1.3` | 700 | Sentence case |
| Panel title | `1rem / 1.35` | 700 | Sentence case |
| Body | `0.875rem / 1.5` | 400 | Sentence case |
| Control label | `0.875rem / 1.25` | 700 | Sentence case |
| Metadata | `0.75rem / 1.4` | 400–600 | Sentence case |
| Eyebrow/quantity | `0.7rem / 1.2` | 700 | Uppercase, `0.08em` tracking |
| Primary reading | `clamp(1.65rem, 4vw, 2.35rem) / 1.1` | 650 | Data font, tabular |
| Unit/quality | `0.75rem / 1.3` | 400–600 | Data font where numeric |

Do not use more than three text sizes in one compact panel. Uppercase is limited to short quantity labels, state labels and eyebrows; never use uppercase for instructional paragraphs.

### Controls, icons and targets

- standard control minimum height: `2.5rem`;
- compact control minimum height: `2rem`, limited to dense desktop tables;
- touch-first or safety-significant action minimum target: `2.75rem` square;
- button horizontal padding: `0.9rem`; vertical padding: `0.55rem`;
- standard icon: 16–18 px; status icon: 16 px; empty-state illustration maximum: 48 px;
- use Lucide icons with `1.75px`–`2px` stroke and `aria-hidden="true"` when adjacent text supplies the name; the icon keys and reference bindings are normative in the contract ([§F](ui-contract.md#f-icon-set));
- destructive and protective actions always include a text label; icon-only is not allowed;
- a rotary control is paired with a precise numeric field and explicit Apply action.

### Motion

The standard interaction transition is `120ms ease`. Hover may lift a raised control by `1px`; active may move it down by `1px` and use the recessed shadow. State changes must not pulse continuously. Critical or trip indication may animate once on entry, then remain static.

When `prefers-reduced-motion: reduce` is active, animation and transition duration is `0.01ms`, iteration count is one, and smooth scrolling is disabled.

## Layered Precision surfaces

Depth communicates function:

- use a raised `Panel` for an actionable group or a bounded information module;
- use a recessed `Panel` for plots, waveforms, tables, logs and other dense data;
- use raised controls for explicit user action;
- use pressed depth only while a control is active;
- keep the application canvas below all panels.

Do not stack multiple strong raised shadows. A reading tile may sit inside a flat composition region; avoid placing a raised tile inside another strongly raised panel.

## Choosing a component

The component inventory and each component's required attributes, roles, class hooks and text are normative in the contract ([§E](ui-contract.md#e-per-component-contracts)).

| Need | Use |
| --- | --- |
| Explicit request | `Button` with the appropriate semantic variant |
| Energy-sourcing action | `ConfirmAction` — the initial control stages, the confirm states effect, value and target |
| Presentation-mode marking on a page | `ModeBanner` — first element of the main region |
| Precise bounded value | `NumericInput` |
| Coarse or stepped set-point | `RotaryControl` paired with `NumericInput` |
| Live or retained scalar | `ReadingTile` |
| Contextual state message | `AlertBubble` |
| Interface refusal at the presentation boundary | `RefusalMessage` — severity and message elements per the contract's §C.3 mapping |
| Time-series or waveform | `EngineeringPlot` |
| Structured channel or event data | `DataTable` |
| Actionable group | raised `Panel` |
| Plot, table or dense result | recessed `Panel` |

If the need is not covered, check the approved component inventory before designing an extension. New components require a concrete user need, accessibility behaviour, light/dark states, tests and stories — and a contract row.

## Observation and control

Readings report gateway observations. Controls stage intent. Buttons submit explicit requests.

- A reading does not become "verified" merely because it rendered.
- A knob, dial, slider or field does not emit device commands while dragged or typed.
- The staged value must be labelled as staged.
- Precise keyboard entry must remain available beside a dial or knob.
- Applying a value must state that authority, policy and device verification still apply.
- Do not optimistically copy a requested value into an applied reading.
- Permission, lease, policy, transport and device rejection remain distinct outcomes — rendered per the refusal mapping (contract §C.3).

**Announcement honest scope (contract §B.3/§B.4):** the reference renderer
implements the PRESENCE arm of the announcement rules — a `status` live region
mounts with the limiting state and with the stale verdict (the mount is the
coalesced entry announcement; unmount is the silent exit), and the pins assert
presence-with / absence-without. What stays unimplemented, disclosed: the
once-and-coalesced TIMING across repeated entries (a re-entry within the same
mount does not re-announce in every host — the mount/unmount lifecycle is the
reference's coalescing approximation) and per-tile announcement ordering
between sibling tiles. Those timing behaviours stay story + browser-review
(the jsdom boundary), the same disclosed class as the CSS-hidden-label
residual in §C.2's enforcement.

**Reading states, the setpoint triad, staleness (contract §B.3/§B.4/§E.3):** a
limiting reading (a limit, not the set-point, constrains the value) renders the
state icon and its `Limiting` label in `--bw-limiting` — never a severity, never
an alert bubble, never glow. The setpoint triad keeps the three roles apart:
measured is the tile's primary, the gateway-observed set value renders adjacent
as `Set {value} {unit}`, and staged lives only in the staging input. Staleness
is computed arithmetic (ST-2: `freshness_ms > 2 × cadence_ms`, strict), the
cadence always the descriptor's own committed value; no cadence ⇒ no verdict
(ST-3's honest negative), and a computed stale marker never touches the
device-declared quality string. The reference renderer's `ReadingTile` carries
the `set`/`state`/`stale` props and the pure `staleness.ts` predicate is the
ST-2 mechanism.
- Energy-sourcing actions confirm; energy-removing actions never stand behind a confirmation (contract §C.1).

**The reference renderer's disabled-reason reach (honest scope):** the contract's §C.2 keys are normative for every host, but this reference composition emits only two of the five. `no-authority` fires whenever the simulated authority state blocks energising actions, and `protection-active` while a protective trip is active. `invalid-staged-input` is never emitted here because `NumericInput` clamps staged values to the declared bounds (`bounds.ts`) — a clamped value is always in range, so the reference renderer cannot stage an invalid one; a host whose inputs can be invalid emits the key. `capability-absent` and `device-state` have no emitting mechanism in the reference composition (it renders one device with all capabilities and no state gate) — they exist for hosts that have partial-capability devices or required idle states.

## Alerts and message persistence

The severity model — meanings, dismissal classes and live regions — is normative in the contract ([§B](ui-contract.md#b-states-and-severity-model)); the reference implementation lives in `ui/src/components/feedback/severity.tsx`. A transient toast is limited to neutral, success and advisory confirmation; warning, critical and trip information must remain present in the affected context. Dismissal is not acknowledgement.

**Label authority (decided with the safety-behaviours slice, issue #242 slice 2):** the contract pins severity KEYS, meanings, dismissal classes and live regions — not display labels. The reference renderer's label map (`severityLabels` in `severity.tsx`) renders the `success` key with the user-facing word "Normal"; that wording is the reference renderer's choice, kept for continuity with its pinned tests, and a host renderer may label severities in its own voice. The key, never the label, is the machine-checkable identity.

## Numbers and units

- Use tabular monospaced numerals for readings and precise inputs.
- Keep the unit adjacent to the value and available to assistive technology.
- Apply engineering prefixes consistently.
- Do not display more precision than the source evidence supports.
- Preserve the full source value and provenance when a compact tile rounds for display.
- Show bounds and steps on editable values.
- Reject non-finite values at the presentation boundary.

## Plots

`EngineeringPlot` exposes a closed host-owned interface. Do not pass arbitrary ECharts options from a plugin.

- Label every axis and unit.
- List every trace in a visible legend.
- Use line form or markers as well as colour for multi-trace identity.
- Label threshold lines with their meaning and severity.
- State the time basis: receipt time, source time or relative acquisition time.
- Keep freshness and partial-data state visible outside the chart canvas.
- Respect reduced motion.
- Supply a textual chart description for assistive technology.

The initial plot supports time series and waveforms. Spectrum, digital traces, sweeps and polar/Smith charts belong to the complete-catalogue follow-on and must retain these same rules. Series tokens and their assignment are normative in the contract ([§E.2](ui-contract.md#e2-series-assignment-engineering-plot-sub-rows)): slots derive from the bytewise-sorted declared id set — the emphasis (accent) hint binds to `--bw-series-1`, and `ui/src/series-colors.test.ts` carries the computed colour proofs (contrast, severity non-confusion under dual CVD models, adjacency) on the actual token values.

**Thresholds as convention (disclosed):** the series thresholds (T1 contrast ≥ 3:1, T2 severity non-confusion ΔE00 ≥ 10, T3/census pair separation ≥ 8) are pre-committed conventions in the design record §6, chosen in the conservative direction — a proxy for "distinguishable as trace identity at plot line width", not a perceptual guarantee at every size. **The dual-model residual:** requiring BOTH CVD models to pass catches model-specific errors, but cannot catch defects shared by the whole pipeline — a bug in the shared CIEDE2000 implementation moves both arms identically, and a constant typo in the permissive direction can pass both arms. The countermeasures are the Sharma reference table, the constant-identity pins (row sums, anchor fixed points, the arms-differ reference vector); the residual counter-class is a same-direction error in a shared constant.

## Administrative consistency

Operator and administrative surfaces share tokens and components. Administrative mutations remain visually distinct from ordinary controls, but they do not invent a separate design language.

Use the same states for pending, approved, warning, critical, revoked, stale and failed. Normal administrative cards do not glow. A rejected admission, revoked package or policy conflict may use the relevant alert severity.

Always show the affected scope of an administrative change. Never imply that a controller identity can approve its own change.

## Accessibility

- Target WCAG 2.2 AA for implemented flows.
- Preserve native HTML behaviour where it provides the required semantics.
- Provide visible focus on raised and recessed surfaces.
- Name every control and expose numeric value, bounds and unit.
- Keep keyboard operation equivalent to pointer operation.
- Honour reduced-motion and increased-contrast preferences.
- Do not announce every live sample; coalesce updates and announce actionable state changes.
- Keep warning, critical and trip text present even when visual effects are unavailable.

## Required stories

Each applicable component must include:

- light and dark theme coverage through the Storybook toolbar;
- default, hover, focus, active and disabled states;
- loading or busy state;
- permission-disabled state for controlled actions — presented as the contract's `no-authority` disabled reason once the safety-behaviours slice lands;
- empty, stale, partial and error states for data components;
- warning, critical and trip states where relevant;
- keyboard interaction and accessible-name checks.

Use these top-level Storybook groups:

1. Foundations
2. Actions
3. Inputs
4. Instrument controls
5. Readings and state
6. Plots and datasets
7. Feedback and recovery
8. Operator compositions
9. Administrative compositions

## Plugin presentation

Plugins declare pages, bindings, plots and exact registered panel identifiers. The host renders them. A plugin manifest cannot supply JavaScript, arbitrary CSS, permission, polling or a raw device command.

Custom devices outside the current OTDP classes will use a separately versioned, bounded component-recipe contract. Until that contract lands, do not encode a private component tree in plugin UI 0.1.0 extension fields.

## Exceptions

An exception proposal must record:

- the user need;
- why existing tokens and components are insufficient;
- operator, safety and accessibility impact;
- plugin and panel compatibility scope;
- light and dark behaviour;
- tests and Storybook stories;
- the owner and review decision.

Keep exceptions narrow. A visual preference alone is not a reason to fork state semantics or component behaviour.
