# plugin-ui-preview 0.1.1 → 0.2.0 migration note

From-predecessor note for the 0.2.0 MINOR bump (issue #244, the digital_lanes
train; VR-36/SM-5). This wire bumps in the same increment as plugin-ui 0.3.0
per GOVERNANCE "different standards may share a merge only when they are one
increment".

## What changed

- `plot_view.kind` gains `digital_lanes`; per-kind `channels` caps via schema
  `if/then` (64 for `digital_lanes`, 16 otherwise).
- `plot_view.lane_groups` / `plot_view.decoder_lanes` mirror the plugin-ui
  0.3.0 manifest structures (the preview wire mirrors manifest structure; it
  carries no capture data — lane activity in the preview is a labelled
  synthetic pattern, the mode-banner honesty posture).
- The wire's `channel` keeps `visible`; `color_role` is refused for
  lanes-kind views.
- `fixture.schema.json` version-sweeps to 0.2.0 (`contract_version` const).

## The range consequence (coordinator ruling VR-43/G-3)

The served range moves to the floor-compliant `>=0.1.1,<0.3.0` (from
`>=0.1.0,<0.2.0`) — NOT a narrow slide: the support-window floor (PRD Q3)
requires a declared range to cover at least the two most recent released
versions, and after this bump those are 0.1.1 and 0.2.0. **0.1.1 pins stay
served** (multi-serving is this wire's established shape; there is no live
code row to protect). 0.1.0 drops out of the window as the older-than-floor
release — 0.1.0 pins re-stamp to 0.1.1 or 0.2.0; no previously-valid document
becomes invalid under its own frozen schema.

## Interim renderer state

The preview renderer refuses the lanes kind visibly (a status note naming the
condition) until the renderer slice lands — the wire grammar is final in 0.2.0.
