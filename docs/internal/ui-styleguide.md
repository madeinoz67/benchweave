# BenchWeave UI style guide

**Status:** Initial executable vertical slice

**Design authority:** [UI style guide and workbench design](ui-styleguide-workbench-design.md)

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

Token groups include:

- `--bw-space-*` for layout rhythm;
- `--bw-radius-*` for controls and panels;
- `--bw-font-ui` and `--bw-font-data`;
- `--bw-canvas`, `--bw-surface` and `--bw-surface-recessed`;
- `--bw-text`, `--bw-text-muted` and `--bw-border`;
- `--bw-shadow-raised` and `--bw-shadow-recessed`;
- `--bw-advisory`, `--bw-warning`, `--bw-critical`, `--bw-trip` and `--bw-success`.

Add a semantic token to both themes in the same change. Do not introduce a raw colour prop on a component.

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
