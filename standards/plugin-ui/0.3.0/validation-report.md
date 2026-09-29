# Plugin UI contracts 0.3.0 — validation report

Evidence record for the digital_lanes train's slice 1 (issue #244; design
`.claude/deep-review/2026-09-29-issue244-digital-lanes-design.md`, committed on
the branch before any acceptance test landed, with its pre-committed
acceptance rules §6 — amended before the record's first commit per the
governor ruling of 2026-09-29). The 0.2.0 increment's evidence record remains
in `standards/plugin-ui/0.2.0/validation-report.md`, digest-frozen with its
tree. The same train bumps plugin-ui-preview 0.1.1 → 0.2.0 (one increment,
one merge, per GOVERNANCE).

## What moved

plugin-ui 0.2.0 → 0.3.0 and plugin-ui-preview 0.1.1 → 0.2.0, both MINOR: a
new enum member plus new per-kind grammar plus normative renderer behaviour
(slice 2's edge-preserving decimation) is new normative capability. Copy,
never move: the new corpus rows cite the predecessor paths as `source`,
digests moved only by `benchweave.standards repin` (2 rows re-pinned after
the grammar edits; 6 new rows total), predecessor trees untouched.

Grammar (`ui-manifest.schema.json` `$defs/plot` + the preview wire's
`plot_view`): `kind` gains `digital_lanes`; per-kind caps via `allOf`
if/then — 64 `y`/`channel_hints`/`channels` for the lanes kind, 16 for the
analog kinds (the caps live ONLY in the kind branches: a base `maxItems`
would intersect, not relax, so a 17-lane lanes plot would have been
refused — caught by the A1.1 boundary vector); `channel_hints` items for
lanes carry `visible` only (`color_role` refused); `lane_groups` (≤16,
members 2..64, radix hex default / decimal opt-in) and `decoder_lanes` (≤8,
sources 1..4, `binding_id` naming a dataset binding). The analog kinds
cannot declare the lanes fields.

Validator semantics (`src/benchweave/presentation/contracts.py`): the
`digital_lanes` branch of `_plot_findings` refuses non-dataset targets and
non-string/scalar `y` axes (`invalid_plot`), resolves group members,
decoder sources and decoder bindings against the plot's `y` and the page's
bindings (`unresolved_reference`), enforces one identifier space across
`y` ∪ group ids ∪ decoder lane ids (`invalid_document`) and one group
claim per channel (`invalid_plot`). The ≥2-member floor is a SCHEMA shape
rule (`member_ids` `minItems: 2` → `invalid_document`): item counts are
the schema's job in the corpus, and `_checked_document` fails closed on
schema findings, so a semantic floor would be unreachable — the design's
§1.2/A1.1 named `invalid_plot` there; corrected per the prose-defers-to-
machine-source rule (see the design record's §1.2 resolution note).

Version sweep: all THREE version-literal sites in the corpus-owned code
row move 0.2.0 → 0.3.0 (the path-shaped `SCHEMA_ROOT` literal and the two
bare `contract_version` consts); the zero-literal register row's
`expected_sites` stays 3 (three sites move, count unchanged), its reason
text records the motion and the fired D2 trigger.

Range motion (coordinator ruling VR-43; OBLIGATION-ONLY reference): the
governor split the design's "slide narrow, both" claim. plugin-ui slides
narrow `>=0.2.0,<0.3.0` → `>=0.3.0,<0.4.0` — FORCED by the one-live-object
rule (the normative bundle row lists `contracts.py` in every carried
version's row, so carrying 0.2.0 beside 0.3.0 would serve 0.3.0 code bytes
under a 0.2.0 pin) plus the manifest's F1/D2 policy note; below the
two-release floor by design. plugin-ui-preview moves floor-compliant
`>=0.1.0,<0.2.0` → `>=0.1.1,<0.3.0` (carries 0.1.1 + 0.2.0, the two most
recent released versions; a narrow slide would drop 0.1.1 and violate the
support-window floor). 0.1.0 leaves the window; 0.2.0-pinned plugin-ui
packages re-stamp to 0.3.0.

Migration notes (SM-5; grandfathering ended, both bumps judged): one per
standard, from-predecessor, repo-relative pointers in the dependency-policy
block. The D2 reopen trigger named in the zero-literal register ("the
first plugin-ui bump after the arc") FIRED with this bump; D2 stays open
with narrower reopen conditions (the design record's D-1).

## Evidence (design §6, slice 1)

- **A1.1 vectors.** Exactly 12 valid vectors (minimal 2-lane; the 64-lane
  boundary exactly; groups hex/decimal/collapsed; decoder lanes with and
  without settings; visible-only hints; integer x; two groups; combined)
  and 14 invalid vectors naming their codes
  (`tests/unit/test_presentation_digital_lanes.py`). The reproduced
  refusal delta: the frozen 0.2.0 schema refuses a digital_lanes plot at
  the kind enum while 0.3.0 admits the same plot — pinned as a permanent
  test (#62 evidence shape). RED arm (PR body): with the kind enum
  neutralized to the predecessor's, 22 of 28 vector tests fail with
  kind-enum `invalid_document`.
- **A1.2 semantic RED.** With the two `elif lanes` branches dead (the
  base `not lanes` guard kept), 9 semantic vectors pass wrongly —
  non-string type, group-outside-y and decoder-unresolved among them;
  restored, all 28 pass.
- **Const-sweep RED.** With the two bare consts reverted to "0.2.0"
  (one-site-sweep simulation), 26 of 28 fail with `unsupported_version`.
- **A1.3 copy-never-move.** 0.2.0's and 0.1.1's corpus rows and directory
  bytes unchanged (frozen-row tests + repin verify); the new rows' digests
  verified against file bytes after the repin.
- **A1.4 gates.** SM-5 RED arm: removing the plugin-ui migration-note row
  fires `migration_note_missing:`. Zero-literal gate green over the edited
  register row. Train-window clear (last version-dir creations 2026-09-19
  / 2026-09-21 vs landing 2026-09-29). Served set after the motions:
  plugin-ui {0.3.0}, plugin-ui-preview {0.1.1, 0.2.0}.

## Honest interim

Slice 1 admits the kind; the renderer does not draw it until slice 2 —
compositions render the visible unsupported-kind refusal note (§E.2.3
precedent), never a silent blank. The wire grammar is final in 0.3.0 /
0.2.0: no second bump results from this issue.
