# Issue #525 — the readings-class examples' readable parameters: design record

Gateway issue `madeinoz67/benchweave#525`. Written 2026-10-22 against
`origin/main` at `4b5b2646` (post-mirror: #526 merged at `ecdbfa2d`; the
recorded-state pin is `6d041a7b`; #528/#529 landed during authoring and
touch no `presentation/`, `standards/otdp/`, or `tests/presentation/`
path — verified by diff `910b1021..4b5b2646`). Every measurement below is
mine, run in a scratch worktree at that commit, unless attributed.

## 0. Verdict

**BUILD.** The defect is real, measured, and its cure is a four-file corpus
edit riding an OTDP PATCH bump (0.2.3 → 0.2.4), with the SDK sync / release /
pointer legs behind it. The wrong party is the examples, not the references
and not the derivation — evidence in §3. The fix is proven end to end on a
scratch corpus (§5): all eight committed pairs derive `valid=True` after the
edit, and only the four target classes change.

## 1. Root cause, traced to the line

Post-mirror derivation, `src/benchweave/presentation/classref.py` at
`origin/main` (1836 lines; mirrored from the SDK expander at v0.18.0):

1. `_resolve_parameters` (lines 826–874): a descriptor whose `parameters`
   carry no `ro`/`rw` row returns `{}` — the disclosed gateway-SDK divergence
   (the SDK refuses `classref_parameter_map` at authoring time; the gateway
   tolerates so the committed examples derive).
2. The readings expansion (lines 1427–1473): `parameter_rows.get(...)` is
   `None` for every (channel, quantity) → `continue` (line 1439) → **no
   observation targets, no observation bindings, no tiles**.
3. Page assembly (lines 1547–1559): a readings page admits `{"observation"}`
   binding kinds only (line 1550) → the `measure` dataset binding is filtered
   out → the readings page carries `bindings: []`.
4. Plot emission (lines 1606–1616): `time_series` with an empty
   `observation_ids_for_page` falls to the else branch — the plot binds
   `over_key` (the `measure` dataset binding), `y` = every (channel,
   quantity) variable id.
5. Validation, `src/benchweave/presentation/contracts.py::_plot_findings`
   (lines 514–528): `plot["binding_id"] not in page["bindings"]` → exactly
   one `Finding("invalid_plot", "pages.<id>.plots", "Plot axes are
   incompatible")`.

Measured at `origin/main` over the eight committed pairs (the run of §2):
the four readings classes each report exactly `[("invalid_plot",
"pages.<id>.plots")]`; the other four report none. This matches the #521
mirror slice's measurement and the `6d041a7b` pin's prose. Not a regression:
the same four pairs carried the same finding pre-mirror (the mirror record
says so; the pre-mirror `_assemble_documents` I read at my worktree base
`9a53ea8e` filters readings bindings identically).

## 2. Per-class scope table (measured, all eight pairs)

Derivation + `validate_attachment` for every `class-*.json` example against
the active family, `origin/main`. Plot page kind and plot kind are read from
each reference (`standards/plugin-ui-class-reference/0.3.0/class-<slug>.json`).

| class | plot page (kind) | plot kind | derivation at `origin/main` | scope |
|---|---|---|---|---|
| dc_psu | `output` (readings) | `time_series` | `valid=False`, exactly 1 × `invalid_plot` @ `pages.output.plots` | **FIX** |
| dmm | `readings` (readings) | `time_series` | `valid=False`, 1 × `invalid_plot` @ `pages.readings.plots` | **FIX** |
| electronic_load | `input` (readings) | `time_series` | `valid=False`, 1 × `invalid_plot` @ `pages.input.plots` | **FIX** |
| smu | `output` (readings) | `time_series` | `valid=False`, 1 × `invalid_plot` @ `pages.output.plots` | **FIX** |
| daq | `capture` (dataset) | `waveform` | `valid=True`, plot over the `capture` dataset binding | clean — control |
| oscilloscope | `capture` (dataset) | `waveform` | `valid=True`, same shape | clean — control |
| logic_analyser | `capture` (dataset) | `digital_lanes` | `valid=True` (the founding class) | clean — control |
| function_generator | none (configuration pages only) | — | `valid=True`, no plot at all | clean — untested by the plot arms, but derives |

No fifth class carries the finding: the dataset-page classes admit dataset
bindings on their plot pages by construction (classref.py:1548), and
function_generator authors no plot page. Every class that authors a readings
page carries it, and only those. The arms are census-driven
(`_plot_classes` walks the ACTIVE family), so a ninth readings class joins
the scope by itself.

Untested surface, disclosed: `function_generator`'s pair is in no derivation
arm (it authors no plot; the mirror arms parametrize over plot authors only).
It derives clean today and after the fix (measured both sides) — adding an
arm for it is deferred (§10).

## 3. The wrong party: the examples

Three candidates, decided on evidence:

- **The references are right.** A readings class is meant to show readings;
  the reference authors `reading-tile` layout children counted by
  `{n_reading_tiles}` (`class-dmm.json` 0.3.0: `expect.components.reading-tile
  = {count: "{n_reading_tiles}", per_page: "readings"}`), the page binds the
  `measure` dataset slot, and the plot is `time_series` with
  `series: "numeric_variables"`. Every one of those authoring moves is
  consumable by a descriptor that declares what it can read — the f6-smu
  parity fixture (parameters-carrying, `TestParityB8`'s validator arm)
  derives and validates clean byte-for-byte against the SDK expander at the
  v0.18.0 pin. Dropping readings pages from four references to match
  parameter-less examples would delete the class contract the whole
  0.3.0 family exists to publish.
- **The derivation's expectation is right.** The observation-expansion rule
  (one observation target per (channel, quantity), the tile's `parameter_id`
  naming a declared readable parameter) is the SDK expander's own convention
  mirrored at the pin; the `parameter_names` positional map is the
  descriptor's own channel-level mapping (OTDP 0.2.3 descriptor schema,
  `channels.items.properties.parameter_names`). The gateway's only liberty —
  tolerating the zero-parameter shape instead of refusing — is the disclosed
  divergence that kept these examples derivable at all.
- **The examples are incomplete.** All eight declare `parameters: []` and
  every channel `parameter_names: []` while declaring `quantities` — a DUT
  that declares measurable quantities but no readable parameter. The in-tree
  parameter-carrying precedents (`reference-psu`, `reference-controller`,
  `reference-hid-meter`) all declare `ro` measurement parameters bound to
  their quantities, plus `operations.read`; the schema makes exactly that
  shape legal (`otdp-device-descriptor.schema.json` `$defs.parameter`:
  ro → `read_policy` required; float → `unit` required; the adapter binding
  is `{kind: adapter, key}`). The f6-smu fixture is the direct convention:
  six `{chN}_{quantity}` ro float parameters, positional `parameter_names`,
  `capabilities` including `read`, `operations.read` declared.

The issue's own framing ("the class is correct; the example is incomplete")
is confirmed by the code, not taken on faith.

## 4. The fix — the four examples' declaration (the whole production change)

Per class in scope, in the 0.2.4 copy (§5), nothing else:

- One `ro` `float` `measurement` parameter per (channel, quantity), named
  `{channel_id}_{quantity}` (dc_psu/smu/electronic_load: 6 each — V, A, W;
  dmm: 2 — V), each with `description`, `unit`, `binding {kind: adapter,
  key: <name>}`, `read_policy {max_age_ms: 0, destructive: false}` — the
  f6-smu fixture's rows verbatim in shape.
- `channels[].parameter_names`: the positional names over `quantities`.
- `capabilities` gains `"read"`; `operations.read` =
  `{timeout_ms: 2000, side_effect: "none", retry: "never", cancellable:
  false, completion: "acknowledged"}` — the `reference-psu`/`reference-hid-meter`
  verb row. (No `side_effect: state_change` anywhere, so S20's verb-maximum
  forces nothing.)
- `otdp_version` → `0.2.4`; contracts rows re-stamped to
  `urn:otdp:profile-catalog:0.2.4` / `urn:otdp:measurement:0.2.4` with the
  0.2.4 digests — the exact 0.2.2→0.2.3 re-stamp shape
  (`git diff 05354b4b:...class-dmm.json 1f27c92d:...class-dmm.json`: 5 lines).

## 5. The corpus motion — OTDP PATCH 0.2.3 → 0.2.4, copy never move

Governance ruling, from `standards/GOVERNANCE.md` and the tree's own history:

- **Bump class: PATCH** (change-class table: "additive machine errata →
  PATCH"). The examples are digest-pinned machine files, not prose.
- **In-place is NOT sanctioned here.** The in-place authoring precedents
  (the 0.2.3 train #445/#447; the classref 0.3.0 sweep L11–L17) all predate
  their version's SDK leg closing. `standards/otdp/0.2.3/` has zero commits
  after its train close (`831dd49f`), and the classref 0.3.0 family has zero
  commits after the v0.17.0 pointer (`30c33d7b`) — both froze when the SDK
  vendored their bytes. Editing 0.2.3 now would change bytes that the
  released SDK v0.18.0 vendors and pins; copy-never-move exists for exactly
  this. (An attempt to edit 0.2.3 in place was refused by the session's own
  permission layer during design — correctly.)
- **G-5 permits the bump:** the SDK lock at the pin (v0.18.0, `3fa10c75`)
  already carries otdp 0.2.3 (verified by `git ls-tree` of the pin). No
  stacked bump; no train conflict.
- **`plugin-ui-class-reference` does NOT bump** — the references are
  untouched; the family stays 0.3.0.

The motion, in order (the edit → repin → export loop; rows hand-authored,
digests by `python -m benchweave.standards repin` only):

1. `cp -R standards/otdp/0.2.3 standards/otdp/0.2.4`; inside 0.2.4 only: the
   four examples' fix (§4), the version-literal sweep the 0.2.2→0.2.3 bump
   also made (internal `"otdp_version"` fields, the measurement schema's
   `$id`/title, catalog/schema/spec strings — my scratch sweep found every
   one of these must move or pinned resolution fails), and every example's
   contracts rows re-stamped to the 0.2.4 catalog/measurement digests.
2. `standards/corpus-manifest.json`: +36 rows under `otdp/0.2.4/`, each
   citing its `otdp/0.2.3/...` counterpart as `source`; 0.2.3 rows untouched.
   Repin fills the digests; repin's frozen-row verification is the
   mechanical proof no retained byte moved.
3. `standards/standards-manifest.json`: otdp row → `version: 0.2.4`,
   `supersedes: 0.2.3`, released date, normative paths → 0.2.4. The
   dependency-policy otdp range `>=0.2.0,<0.3.0` already admits 0.2.4 — no
   range change, so no VR-43 coordinator ruling.
4. Validation report regen: `scripts/architecture/check_devices.py
   --write-report` for 0.2.4 (refuses on a failing run) + the `docs/README.md`
   report row (the exactly-once link assert catches a forgotten row).
5. In-arc sweep of active-version literals outside the corpus: the
   `tests/ui_html/test_classref_*.py` `DESCRIPTOR`/`CATALOG` path literals
   (four readings classes + the other classes' — daq, oscilloscope,
   function_generator carry them too), the `tests/presentation/` fixtures
   stay frozen (their descriptors pin 0.2.3/0.2.2 → retained-resolution,
   the multi-version-serving pattern proven in-tree by
   `fixtures/execution/descriptor-sim-*.json` at 0.2.2 and by the SDK's own
   tests pinning 0.2.2). `src/` carries zero otdp version literals (the
   VR discipline — verified by census). Pre-flight: the version-surface
   readiness census over every version-bearing surface before the bump legs
   run (the standing applied proposal).

**Proven on a scratch corpus.** I built `/tmp/corpus-root` (a copy of the
standards tree, 0.2.4 activated, fixed examples, repinned) and ran the
derivation + `validate_attachment` over all eight pairs with the document
set built from the scratch corpus (`_presentation_documents_cached` +
`_pin_scoped_documents`'s scoping, which reads the repo corpus internally —
the honest way to scope it):

- All eight: `valid=True`, zero findings.
- The four fixed pairs: readings pages carry their observation bindings
  (dmm: 2; the others: 6), and the plot is
  `{kind: "time_series", binding_id: "measure-ch1-voltage", x: "time",
  y: ["ch1-voltage"]}` — byte-shape-identical to the f6-smu oracle fixture's
  plot row (the SDK expander's own convention, already pinned).
- The four controls: derivations identical to the pre-fix run (same plots,
  bindings, y sets) — the motion changes nothing outside the four files.

Scratch artifacts disclosed: two intermediate scratch states produced
`capability_mismatch`/`unresolved_reference` findings — both traced to my
scratch's inconsistent pin stamping (contracts digests, the measurement
schema's `$id`) and to `_pin_scoped_documents` resolving against the repo
corpus rather than the scratch; neither is a property of the fix. The final
consistent scratch state is the evidence above.

## 6. Release legs (two repos, one issue, #408 order)

1. **Gateway corpus PR** (branch off `origin/main`): the bump + fix + test
   motion (§7) + report regen + sweep. Self-contained green — the
   derivation tests read the gateway's own corpus, not the SDK's vendored
   copy. The SDK pointer does not move in this PR; the pin still names
   v0.18.0, so `sdk-drift` is green with the `::warning::` pairing-pending
   annotation. `gates`' `make check-sdk-standards` checks the pin's internal
   consistency, not gateway-equality — the gateway-ahead window is the L11
   precedent ("the SDK's own vendored corpus carries 0.2.0 until the batched
   promotion leg re-stamps its side"). If that lane reds anyway, the fallback
   shape is stacked branches with the pointer PR last — the #408 order is
   preserved either way.
2. **SDK PR**: `make sync-sdk-standards` (refuses a dirty submodule tree) —
   vendored 0.2.4 tree + lock carried rows (+0.2.4, 0.2.3 stays carried).
   `OTDP_VERSION` is derived (issue #203), so no SDK literal moves. SDK-side
   tests pin retained versions (0.2.2) — unaffected. PR body notes the
   single-issue-stream rule (no SDK-side issue, by design).
3. **SDK release cut**: `make release-cut VERSION=...` in the SDK repo.
   Proposed 0.19.0 (MINOR — a new active OTDP version becomes
   consumer-visible through the SDK, the same class of motion as the 0.17.0
   classref-0.3.0 sync); the release-review matrix at cut time owns the
   final number.
4. **Gateway pointer PR**: gitlink + `.gitmodules` `pin` in the SAME commit;
   `sdk-drift` green without the trailing warning closes the pairing window.

The SDK expander's authoring-time `classref_parameter_map` refusal is
unchanged by all of this — post-sync its vendored examples finally satisfy
it (today the SDK refuses 4 of its own 8 vendored class examples at
authoring time; after the sync, zero).

## 7. The gate — arm names, RED shape, the deliberate pin move

Owning module: `tests/presentation/test_classref_derive.py`. The mirror
slice's census-driven arms (the module derives its sample by walking the
ACTIVE family) are the gate.

- **`_assert_pair_validates` (lines 350–397) — the recorded-state pin moves.**
  The readings branch asserts
  `[(row.code, row.path)] == [("invalid_plot", f"pages.{page_id}.plots")]`
  — `6d041a7b`'s recorded pre-existing state, ruled "pinned, not blessed",
  with the fix assigned to #525. This slice replaces the readings branch
  with the clean expectation (`report.valid`), collapsing it into the
  dataset branch, and the docstring cites #525's closure with the ruling's
  own words. Not a weakening: the assertion strictens (a finding now fails
  the arm; before, its absence did).
- **`test_a_time_series_reference_derives_the_time_series_plot` (421–452) —
  the y/binding assertions become page-kind-aware.** Post-fix the readings
  pair's plot binds the page's FIRST observation with `y == [that
  observation's value id]` (classref.py:1606–1611, the f6 convention), not
  the dataset binding with every variable id (the fallback the arm asserted
  via the zero-parameter state). The arm derives its expectation from
  `_plot_page_kind(reference)` — dataset-page pairs keep today's assertion
  for the day a ninth class authors one (post-fix no committed pair
  exercises that branch; see the mutation arm below).
- **New mutation arm — the guard's pin (replaces the committed-corpus
  coverage of the zero-parameter tolerance).** Strip `parameters`/
  `parameter_names` from a FIXED example in memory (no corpus byte touched),
  derive, and assert the disclosed-divergence shape: the derivation succeeds
  (does not refuse), the plot binds the dataset slot, and validation
  reports exactly the one `invalid_plot` finding — `6d041a7b`'s recorded
  state, now a pinned BEHAVIOR of `_resolve_parameters`'s tolerance rather
  than a state of the committed corpus. Its docstring names the SDK's
  refusal as the authoring-time counterpart.
- **Unchanged arms that guard the motion:** `TestParityB8`'s five fixtures
  (byte-frozen; their descriptors pin retained versions), the waveform arm
  (daq/oscilloscope — dataset pages, untouched), the ceiling arm, and the
  `tests/ui_html/test_classref_*.py` mockup census (tile counts derive from
  channels × quantities, which the fix does not touch — parameters add
  bindings, not tiles; the sweep moves only their path literals).

RED shape, per the G3 procedure: write the flipped assertions first, run
against `origin/main` — the readings branch reds with the actual
`invalid_plot` finding in the assertion diff, the y assertion reds with
`['ch1-voltage'] != ['ch1-voltage', 'ch1-current', ...]`-shaped output;
apply only the corpus bump — both green. `no tests ran` is a failed check;
collect the count.

## 8. Tier statement (Step 1, #254) and keyword scan

**Tier 3**, first match on "anything under `standards/`" (corpus files +
`corpus-manifest.json` + `standards-manifest.json`); also the keyword rule
fires (`sha256` below). The standards-governor mandate (#69) applies
mandatory on every leg touching `standards/`, the vendored tree, or version
strings; the Tier-3 second adversarial reviewer applies to the gateway
corpus PR and the pointer PR.

Keyword scan over the expected diff, design-time, 2026-10-22:

- This record as written, counted 2026-10-22 by grep over the saved file:
  `sha256` 3 (§4's contracts re-stamp and §5's repin discussion, plus this
  list), `threading` 2, `asyncio` 1, `subprocess` 2, `hashlib` 2,
  `migrate` 1, `recovery` 2, `protection` 2 — every occurrence outside
  `sha256` is this §8 paragraph's own enumeration of the eight keyword
  names (the list self-fires by construction, intended and counted as the
  design's own statement, the mirror record's convention), plus §8's
  second bullet naming `hashlib` in the same breath. No protective,
  concurrency, migration or recovery CONTENT is carried anywhere in the
  record; the tier rides the `standards/` path rule regardless.
- Expected corpus/code diff (0.2.4 copy + four examples + manifests + report
  + test motion): `sha256` — every corpus-manifest row and every example's
  contracts rows carry the field name (36 new manifest rows + 8 contract
  rows + the repin's digest column): ≥44; the other seven keywords 0 by
  design (no threading/async/subprocess/migration/recovery/protection
  content; `hashlib` appears in no edited line — digests move through
  `repin`, never hand-spliced).

The build leg re-runs the scan over the actual committed diff; the review
re-derives the tier.

## 9. Pre-committed acceptance rule (written before any arm ran)

Metric: the derived-and-validated state of the committed class pairs
(`derive_attachment` + `validate_attachment`, the census arms' own
procedure), and byte-stability of every surface the motion must not move.
Sample: the full active family (8 classes — a census, not a sample).

**SHIPS if all hold:**
1. RED→GREEN (G3): the flipped arms (§7) RED on `origin/main` with the
   finding/dataset-binding shapes, GREEN on the bumped tree with only the
   corpus change applied.
2. 8/8 pairs `valid=True`, zero findings (was 4/8 with one `invalid_plot`
   each; the effect is the finding's disappearance on exactly the four).
3. The four controls' derived triples are IDENTICAL pre/post (compared
   manifest bytes) — the motion's only behavioral delta is the four.
4. `TestParityB8` fixtures f1/f2/f1-da/f5-trio/f6-smu byte-frozen (the arms
   are their own proof).
5. `check_devices.py --write-report` for 0.2.4 passes all checks (the four
   amended examples validate against the descriptor schema — the
   `reference-*` precedents already prove the parameter shape schema-legal).
6. FAST lane + full battery + both standards tripwires green; the version
   census found no stranded active-version literal at merge-result time.
7. The SDK legs land in #408 order and `sdk-drift` closes the pairing
   window (green without the trailing warning).

**KILLS if any of:**
- (a) a control class's triple moves — the corpus edit leaked beyond the
  four files; find the leak or re-scope.
- (b) a flipped arm cannot go green without weakening another live
  assertion (a mockup count, a fixture byte, a validator rule) — the
  examples cannot honestly carry what the references author; owner
  escalation, never a tuned test.
- (c) `check_devices` refuses an amended example — the parameter shape is
  schema-invalid as authored; fix the rows against the schema, or the
  design's §4 shape is wrong.
- (d) the SDK sync/expander diverges over the fixed examples at the new pin
  (parity break beyond the f6 convention) — mirror first, per the
  mirror-discipline rule.

**UNDERPOWERED, not conclusive:** the only red is a docs/report annotation
(row link, report title) or a CI plumbing failure — says nothing about the
mechanism; fix and re-run before judging. Likewise a ui_html render-polish
failure (the mirror record's §5c class) is not evidence about the corpus
fix.

Falsifier for the scope itself (the lead's ask): a class excluded above that
carries the finding. Measured: none of the four controls report any finding
at `origin/main` (§2). The living falsifier is a ninth class landing in the
family before the fix — the census arms widen by themselves and it would
join the RED set uninvited.

## 10. Deferrals (explicit)

- A derivation arm for `function_generator` (no plot page; derives clean,
  untested by the plot arms) — a composition-tier arm, not this slice.
- A NEW B8 parity fixture generated from a fixed committed pair (the f6-smu
  fixture already pins the exact convention byte-for-byte; redundancy
  deferred).
- Serve-path end-to-end arm for a readings-shaped device (the mirror
  record's own deferral (b)).
- The `time_series`-over-dataset branch regaining committed-pair coverage
  (needs a dataset-page time_series author in the family; the mutation arm
  holds the branch's behavior until then).
- The ui_html DESCRIPTOR literals' migration from path literals to
  active-version derivation (the sweep re-points them; deriving is the
  better end state, a separate sweep).

## 11. Top risks, each with its falsifier

1. **The gateway-ahead window reds a lane** (corpus at 0.2.4, SDK pin at
   v0.18.0). Falsifier: `make check-sdk-standards` or `gates` red on leg 1.
   Mitigation: stacked branches, pointer PR last — the L11 shape.
2. **The in-arc sweep misses an active-version surface** (91 files carried a
   `0.2.3` literal at census; most are retained-pin fixtures that must NOT
   move). Falsifier: a merge-result CI red naming a version. Mitigation: the
   version-surface census pre-flight + CI's merge-result testing.
3. **The recorded-state ruling is misread as a weakened gate.** The move
   strictens the assertion; the PR body must cite `6d041a7b`'s own
   "the fix belongs there" sentence. Falsifier: the owner's review.
4. **The report regen shifts check counts** (717 → N). A count shift is the
   writer's business; a FAILING check is kill (c). Falsifier: the regen's
   own refusal.
5. **The mockup census breaks anyway** — would mean the readings expansion
   emitted tiles beyond the authored ones. Falsifier: the ui_html arms
   (counts derive from channels × quantities; the fix touches neither).

## 12. Maintenance note

The commit carrying this record onto the fix branch is the build lane's
first commit, before any measurement in §9 runs — the pre-committed rule
must be in git history before the arms do.
