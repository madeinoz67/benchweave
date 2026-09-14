# BenchWeave UI style guide

**Status:** Initial executable vertical slice

**Design authority:** [UI style guide and workbench design](ui-styleguide-workbench-design.md)

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

Use CSS custom properties from `ui/src/styles/tokens.css` and `themes.css`. Components must not hard-code a colour or shadow that conveys product meaning.

This section is normative. The tables below define the design values; the CSS files are their executable mirror. A change to either requires the other to change in the same commit.

Token groups include:

- `--bw-space-*` for layout rhythm;
- `--bw-radius-*` for controls and panels;
- `--bw-font-ui` and `--bw-font-data`;
- `--bw-canvas`, `--bw-surface` and `--bw-surface-recessed`;
- `--bw-text`, `--bw-text-muted` and `--bw-border`;
- `--bw-shadow-raised` and `--bw-shadow-recessed`;
- `--bw-advisory`, `--bw-warning`, `--bw-critical`, `--bw-trip` and `--bw-success`.

Add a semantic token to both themes in the same change. Do not introduce a raw colour prop on a component.

### Colour palette

Theme changes luminance and contrast, not meaning. Use semantic names in components; hexadecimal values belong only in theme definitions, documentation and visual-test fixtures.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--bw-canvas` | `#e4ebef` | `#19252c` | Application background |
| `--bw-surface` | `#f5f8f9` | `#26363f` | Raised panel and control face |
| `--bw-surface-recessed` | `#dce5ea` | `#101a20` | Plots, tables, logs and wells |
| `--bw-text` | `#17242c` | `#eef5f7` | Primary text and values |
| `--bw-text-muted` | `#5b6a73` | `#aebbc2` | Labels, metadata and secondary text |
| `--bw-border` | `#c3cfd5` | `#40515b` | Neutral boundaries and dividers |
| `--bw-accent` | `#0b7181` | `#42cee2` | Selected state and primary action |
| `--bw-accent-contrast` | `#ffffff` | `#07161a` | Text/icons on accent |
| `--bw-focus` | `#087f8c` | `#59d9eb` | Keyboard focus ring only |
| `--bw-advisory` | `#2476b8` | `#62aee8` | Informative state requiring awareness |
| `--bw-warning` | `#a96608` | `#ffb342` | Attention required |
| `--bw-critical` | `#b63830` | `#ff6d63` | Immediate operator action |
| `--bw-trip` | `#a92858` | `#ff5d91` | Protective trip and inhibited control |
| `--bw-success` | `#177158` | `#67d8b2` | Confirmed successful outcome |

Severity colours are not general decoration. Normal state uses neutral surfaces; success is reserved for a confirmed transition or outcome. Charts use accent first, then severity colours only when the series itself has that meaning.

### Spacing and layout

The base unit is `0.25rem` (normally 4 px). Use only the defined steps for component padding and gaps.

| Token | Value | Typical use |
| --- | --- | --- |
| `--bw-space-1` | `0.25rem` | Tight label/value separation |
| `--bw-space-2` | `0.5rem` | Icon gaps and compact rows |
| `--bw-space-3` | `0.75rem` | Control groups and alert padding |
| `--bw-space-4` | `1rem` | Standard component padding |
| `--bw-space-5` | `1.5rem` | Panel and page-section gaps |
| `--bw-space-6` | `2rem` | Major composition separation |

Layout rules:

- page content maximum width: `90rem`;
- page gutter: `1.5rem`, reducing to `1rem` below 48rem;
- minimum supported viewport: `20rem`;
- reading grid minimum tile width: `13rem`;
- plot minimum useful height: `15rem` desktop and `12rem` compact;
- table rows: minimum `2.5rem` target height;
- use CSS grid for device/plugin panels so unknown plugin compositions wrap without absolute placement;
- breakpoints are content-driven, with reference points at 30rem, 48rem, 64rem and 90rem; do not branch component behaviour by device name.

### Radius, borders and elevation

| Token or rule | Value | Use |
| --- | --- | --- |
| `--bw-radius-control` | `0.5rem` | Buttons, fields, bubbles and compact controls |
| `--bw-radius-panel` | `0.875rem` | Panels, cards and instrument groups |
| Standard border | `1px solid var(--bw-border)` | Component boundary |
| Focus outline | `0.125rem solid var(--bw-focus)` | Keyboard focus |
| Focus offset | `0.125rem` | Separation from component edge |
| Raised shadow | `0.5rem 0.625rem 1.5rem` dark plus `-0.35rem -0.35rem 1rem` light | Panels/readings |
| Recessed shadow | inset `0.25rem 0.25rem 0.625rem` dark plus inset `-0.2rem -0.2rem 0.5rem` light | Plots, tables and wells |
| Abnormal glow | `0 0 1.5rem`, state colour at 32% | Affected reading only |

Elevation has three levels: canvas (0), recessed (-1) and raised (+1). Dialogs and menus may use +2 by strengthening the raised shadow once. Do not create arbitrary elevation levels or nest strong shadows.

### Typography

UI text uses `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`. Numeric readings, timestamps, identifiers and source evidence use `"SFMono-Regular", Consolas, "Liberation Mono", monospace` with tabular numerals.

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
- use Lucide icons with `1.75px`–`2px` stroke and `aria-hidden="true"` when adjacent text supplies the name;
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

| Need | Use |
| --- | --- |
| Explicit request | `Button` with the appropriate semantic variant |
| Precise bounded value | `NumericInput` |
| Coarse or stepped set-point | `RotaryControl` paired with `NumericInput` |
| Live or retained scalar | `ReadingTile` |
| Contextual state message | `AlertBubble` |
| Time-series or waveform | `EngineeringPlot` |
| Structured channel or event data | `DataTable` |
| Actionable group | raised `Panel` |
| Plot, table or dense result | recessed `Panel` |

If the need is not covered, check the approved component inventory before designing an extension. New components require a concrete user need, accessibility behaviour, light/dark states, tests and stories.

## Observation and control

Readings report gateway observations. Controls stage intent. Buttons submit explicit requests.

- A reading does not become “verified” merely because it rendered.
- A knob, dial, slider or field does not emit device commands while dragged or typed.
- The staged value must be labelled as staged.
- Precise keyboard entry must remain available beside a dial or knob.
- Applying a value must state that authority, policy and device verification still apply.
- Do not optimistically copy a requested value into an applied reading.
- Permission, lease, policy, transport and device rejection remain distinct outcomes.

## Alerts and message persistence

The severity model is defined in `ui/src/components/feedback/severity.tsx`:

| Severity | Meaning | Dismissal |
| --- | --- | --- |
| Neutral | Context or helper detail | Allowed |
| Success | Confirmed completion with no continuing risk | Allowed |
| Advisory | Non-urgent evidence or state note | Allowed |
| Warning | Attention required | Persistent until acknowledged or resolved |
| Critical | Immediate operator action | Persistent until resolved |
| Protective trip | Protective action and inhibited control | Non-dismissible while active |

`AlertBubble` may appear inline, anchored to a source, inside a panel or as a global banner. A transient toast is limited to neutral, success and advisory confirmation. Warning, critical and trip information must remain present in the affected context.

Glow is an additional cue. Advisory through trip may use localised glow around the affected reading or message. Normal and success readings do not glow. Every abnormal state also needs an icon, explicit label, border and text.

Dismissing a message is not acknowledgement of the underlying gateway or device condition. Model acknowledgement as a separately labelled authorised request.

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

The initial plot supports time series and waveforms. Spectrum, digital traces, sweeps and polar/Smith charts belong to the complete-catalogue follow-on and must retain these same rules.

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
- permission-disabled state for controlled actions;
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
