# Plugin UI contracts 0.4.0 — validation report

Evidence record for the L5 §E.1 input trio bump (gateway issue #463; design
`.claude/deep-review/2026-10-16-classref-l5-plugin-ui-0-4-0-design.md`,
committed on the branch before any build, whose §9 carries the pre-committed
acceptance rules and whose §5 sanctions this corpus motion in writing). The
0.3.1 increment's evidence record remains in
`standards/plugin-ui/0.3.1/validation-report.md`, digest-frozen with its
tree.

## What moved

plugin-ui 0.3.1 → 0.4.0, MINOR (the D4 amendment's one sanctioned wall
payment), and plugin-ui-class-reference 0.1.0 → 0.2.0 in the same train.
Copy, never move: 4 new corpus rows citing `standards/plugin-ui/0.3.1/*` as
`source` and 3 new rows citing `standards/plugin-ui-class-reference/0.1.0/*`,
digests moved only by `benchweave.standards repin` (7 rows re-pinned, zero
rewrites among the 275 frozen predecessor rows — the command's own
frozen-row gate ran over them); the predecessor trees are untouched.

The schema delta is re-stamp only, verified by sorted-key JSON diff: the
four 0.4.0 schemas differ from their 0.3.1 sources in `$id`, `title`,
`contract_version` consts and the cross-schema `$ref` URLs — 12 diff lines
in `ui-manifest.schema.json`, all carrying version strings; zero other
delta. The family's `layout.schema.json` carries the one widening:
`control.kind` `["button","numeric","rotary"]` →
`["button","numeric","rotary","text","select","boolean"]` (11 diff lines,
all version strings or the three new kinds); `class-logic_analyser.json`
re-stamps with exactly one line changed.

## Version sweep

- All THREE version-literal sites in the corpus-owned code row moved
  0.3.1 → 0.4.0 (the path-shaped `SCHEMA_ROOT` literal and the two bare
  `contract_version` consts); the zero-literal register row's
  `expected_sites` stays 3, its reason text records the motion.
- The family's authored provenance literals moved in the same arc:
  `classref.FOUNDING_FAMILY_VERSION` and the classref panel's
  `corpus_pin` (the panel render path derives the served version and
  refuses the composition on mismatch, so a stale pin breaks the panel —
  the readiness audit's H2). Register value tuples moved ("0.1.0" →
  "0.2.0", one site each), reason texts record the motion.

## RED-first evidence (junitxml counts, this worktree)

- **The ZERO gate as the register arc's RED.** With the classref.py and
  panels.py literals moved but the register rows unedited:
  `gateway: 0 outside register (5 sites, 111 files scanned, FAILED)` —
  `register value pin failed: ... classref.py expects ['0.1.0'], found
  ['0.2.0']` and the identical panels.py row, exit 1. Register rows
  edited (values + motion notes): `gateway: 0 outside register (5 sites,
  111 files scanned, ok)`, exit 0.
- **The widening's schema RED.** A `select`-kind control node validated
  against the frozen 0.1.0 layout schema: `valid=False` (refused); the
  same node against the 0.2.0 schema: `valid=True`. The suite's trio
  arms (`test_control_kinds_widen_to_the_input_trio`, parametrized 3/3)
  pin it.
- **The validator-const RED.** With `contracts.py` moved and the unit
  fixtures still stamped 0.3.1:
  `tests/unit/test_presentation_{manifest,presets,profiles,specimens,
  digital_lanes}` + `tests/contract/test_sim_scope_plugin`:
  tests=142 failures=78 (every failure a 0.3.1-stamped document refused
  `unsupported_version` by the moved const). After the fixture sweep
  (and the sim_scope document re-stamp with its digest chain re-derived):
  tests=142 failures=0.
- **The corpus-pin-guard RED (H2).** The corpus moved with
  `panels.corpus_pin` still "0.1.0": the classref panel suite reds on the
  pin guard (served 0.2.0 ≠ pin 0.1.0 refuses the composition). The
  literal move in the same arc greens it.
- **The parity-fixtures RED (B8).** With the corpus at 0.2.0/0.4.0 and the
  committed SDK fixtures still carrying the 0.3.1/0.1.0 stamps:
  `test_f1_f2_triples_byte_equal_committed_sdk_fixtures` red. The 9
  fixtures regenerated (see provenance below): tests=68 failures=0 over
  `tests/presentation/` + `tests/interfaces_ui/test_ui_presentation.py` +
  `tests/ui_html/test_classref_page.py`.

## Parity-fixture provenance

The 9 committed parity fixtures regenerated from the SDK **v0.14.0**
derivation (the submodule pin at this branch's base, `201c343` — read,
never modified) against the NEW corpus: a scratch copy of the v0.14.0
package with the 0.4.0 + 0.2.0 directories vendored and the lock's active
markers moved (0.4.0/0.2.0 active; 0.3.1/0.1.0 retained). `derive_ui`
resolved actives from that lock: plugin-ui 0.4.0, family 0.2.0. The
derivation code is v0.14.0's UNMODIFIED — the expander/ladder widening
(the F2 ruling's select-node emission) is the SDK leg's work and emits
nothing for these fixtures (their fields are all numeric/button kinds).
Fixture diffs verified stamp-only: 15 inserted / 15 deleted lines across
the 9 files — version strings plus the three envelopes' manifest sha256
pins (derived, not content). B8 byte-parity (gateway derivation ≡
committed fixtures) green after regeneration.

## In-arc sweep (the #444 bump's own file-set convention)

The design record's §4 census names the corpus and the presentation
surfaces; the landed sweep additionally covers the surfaces the #444
bump commit (fc6a0d63) swept, per the obligations doc's in-arc rule:
the five validator unit suites' fixtures (0.4.0 stamps + the active-dir
globs), `tests/contract/test_sim_scope_plugin.py` and the five shipped
sim_scope presentation documents (byte-faithful re-stamp; preset bytes →
manifest asset pins → presentation manifest pin, the #444 chain),
`tests/standards/test_{export,scenarios,dependency,dependency_policy,
dev_pins,zero_literal_gate}.py` (carried-set/served-set/resolution
constants), the matrix denominator test (23 → 25 retained version rows:
plugin-ui 6 dirs, classref 2), the ui_presentation classref arms (active
paths + layout const + rendered pin), the derive/page suites' corpus
paths, and the ui-html module docstring's corpus pointer.

## Gates

- `benchweave.standards repin`: exactly 7 rows re-pinned, 0 rewritten
  among frozen predecessors (row-level diff: +35 lines, all new rows).
- Version-literal ZERO gate: gateway/plugins/docs/scripts scopes green
  with the register rows moved (5 sites, count unchanged); the sdk scope
  rides the pointer leg.
- `benchweave.standards check` and the `tests/standards/test_check`
  mirror/anchor lanes are red on this branch BY THE LANDING SPLIT (the
  0.3.1 validation-report's own disclosure, issue #408's rule): they
  compare a fresh export against the SDK submodule's lock and vendored
  tree, and the pointer does not move until the landing train's
  same-commit advance. The red family: 2× `served_set_drift` (the new
  actives absent from the v0.14.0 lock), 2× `sdk_version_mismatch`,
  1× `policy_mirror_drift`, 4× `stale_generated` + 7× `missing_asset`
  (the vendored tree lags), 2× `_GENERATED.txt` — 19 failures, one
  mechanical root, all cleared by the SDK sync + pointer commit.
- `matrix --check`: re-rendered `docs/compatibility-matrix.md` from the
  committed manifest in the same arc (CON-12 committed-state purity);
  clean at this report's commit.
- `scripts/ci/win_core_manifest.py --check`: refreshed with the
  architecture suite's total (74 → 81; the trio + retained-freeze arms).
