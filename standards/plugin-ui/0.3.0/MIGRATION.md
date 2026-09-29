# plugin-ui 0.2.0 → 0.3.0 migration note

From-predecessor note for the 0.3.0 MINOR bump (issue #244, the digital_lanes
train; VR-36/SM-5).

## What changed

- `$defs/plot.kind` gains `digital_lanes` — a logic-capture view kind with its
  own grammar (below). The analog kinds are unchanged.
- Per-kind caps via schema `if/then`: `digital_lanes` admits up to 64 `y`
  channel ids and up to 64 `channel_hints` items carrying `visible` ONLY
  (`color_role` is refused for this kind — colour carries nothing in a lanes
  view); `time_series`/`waveform` keep `maxItems: 16` on both and CANNOT
  declare `lane_groups` or `decoder_lanes`.
- New optional `lane_groups` (≤16 items, each `{id, label?, member_ids
  (2..64), radix? ("hex" default, "decimal" opt-in), default_collapsed?}`).
- New optional `decoder_lanes` (≤8 items, each `{id, label?, decoder
  (1..64 chars), settings? (free-form object, disclosed verbatim),
  source_channel_ids (1..4), binding_id}`); `binding_id` names a manifest
  binding whose target is the decode action's `event_log` dataset target.
- The x-derivation authoring rule (README): for a digital capture the
  catalogue's `x` variable names the dataset's regular time axis
  (t_i = start + i·step); the trigger marker is `trigger.time_relative_s`.

## The range consequence (coordinator ruling VR-43/G-3)

The served range slides narrow: `>=0.2.0,<0.3.0` → `>=0.3.0,<0.4.0`. A pin to
0.2.0 is OUT of the carried set after this bump. The narrow slide is forced by
the one-live-object rule: plugin-ui's normative bundle row lists the live code
object (`src/benchweave/presentation/contracts.py`) in every carried
version's row, so carrying 0.2.0 beside 0.3.0 would serve 0.3.0 code bytes
under a 0.2.0 pin — single-serving is the only honest posture until deferral
D2 closes (the manifest's F1/D2 policy note sanctions the below-floor range).
Re-stamp 0.2.0 pins to 0.3.0 (the documents are 0.3.0-valid except
`contract_version`, which the re-stamp updates); no previously-valid 0.2.0
document becomes invalid under its own frozen schema.

## Interim renderer state

The reference renderer does NOT draw `digital_lanes` in this train's first
slice: it renders a visible unsupported-kind refusal note (never a silent
blank) until the renderer slice lands. The wire grammar is final in 0.3.0 — no
second plugin-ui bump results from this issue.
