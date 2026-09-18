# Plugin UI contracts 0.1.1 — validation report

## Amendment 2026-09-19 — mechanism-critique fix wave (C1–C4)

Follow-up commits on the same branch (never rewritten history). RED first:
`EngineeringPlot.test.tsx` **12 collected / 5 failed** against the tip — the C1
ruling pin (`'#0b7181' to be '#a96608'`: an accent hint on a non-index-0 trace
must lose to index 0's default claim), the C4 fallback (`'#5b6a73' to be
'#a96608'`: a missing muted token must fall back to the pass-1 default), the
C1 invariant (`hints {"b":{"colorRole":"accent"}}: expected [ 'a', 'b' ] to
have a length of 1 but got 2`), the C3 disclosure (no accessible `listitem`
naming the hidden state), and the C2 carrier (`expected [] to have a length of
1 but got +0` with every trace hidden and a threshold configured). GREEN after
the fix wave: **12/0**.

- **C1**: `resolveStyles` arbitrates accent in trace order with pass-1
  index-0 accent as the first claim; pinned by the ruling test, the
  sanctioned mute-0+accent-N composition, the earliest-hint-wins collision
  (with index 0 muted), and a table-driven invariant over eight hint maps
  (exactly one visible accent series in each).
- **C2**: threshold renders on an empty-data carrier series when no visible
  series remains; pinned with all three channels hidden.
- **C3**: hidden legend rows carry an explicit accessible name
  ("… (hidden by presentation preference)") plus the visible struck-through
  `hidden` tag; pinned with `toHaveAccessibleName(/hidden/i)` and non-hidden
  rows asserted free of it.
- **C4**: `--bw-text-muted` absent ⇒ `tokens.muted` undefined ⇒ muted hints
  revert to the pass-1 default; pinned with the token stubbed present
  (token colour used) and absent (default colour used).

The design record's branch copy carries the four rulings as a dated
amendment.


Evidence record for the channel-hints increment (issue #6 row C; design
`.claude/deep-review/2026-09-19-issue6-rowC-display-hints.md`, accepted with its
pre-committed acceptance rule §7). The 0.1.0 increment's own evidence record
remains in `standards/plugin-ui/0.1.0/validation-report.md`, digest-frozen with
its tree.

## What moved

plugin-ui 0.1.0 → 0.1.1 (PATCH: additive machine errata — one optional
`channel_hints` array on `$defs.plot`, nothing removed or retyped). Bump
mechanics per `standards/GOVERNANCE.md`: copy-never-move, new corpus rows cite
`standards/plugin-ui/0.1.0/<file>` as `source`, digests moved only by
`benchweave.standards repin` (4 rows re-pinned), old tree untouched (verified
by `git status` empty under `standards/plugin-ui/0.1.0/` and by the frozen
0.1.0 corpus rows still matching their pinned digests in the focused suite).

Semantic checks ride the existing seam in
`src/benchweave/presentation/contracts.py` `_plot_findings`: hint
`variable_id` membership in the plot's own `y` (`unresolved_reference` at
`pages.<id>.plots.channel_hints`) and per-plot duplicate refusal
(`invalid_document`, mirroring `_unique_rows`). No new diagnostic codes; shape,
enum, boolean and item-count enforcement live in the 0.1.1 schema.

Renderer: `ui/src/components/plots/EngineeringPlot.tsx` gains an optional
`hints` prop — two-pass styling (index-derived defaults over the full ordered
trace list, then colour-role bias with earliest-accent-wins collision rule),
visibility filtered AFTER style resolution (indices never shift), struck-through
legend disclosure rows for hidden channels, threshold mark line riding the
first visible series.

## RED (pre-implementation, commit `9046a4a`)

Fixtures pointed at the not-yet-existing 0.1.1 corpus, so the suite failed for
the true reason (the standard version was absent):

- pytest (manifest + specimens + architecture contract files): **43 collected /
  34 failed** (junitxml) — dominated by `unsupported_version` and the missing
  `standards/plugin-ui/0.1.1/` schema files.
- vitest `EngineeringPlot.test.tsx`: **7 collected / 4 failed** —
  `expected '#a96608' to be '#0b7181'` (hint bias absent) and
  `expected [ 'a', 'b', 'c' ] to deeply equal [ 'a', 'c' ]` (no visibility
  filter).
- `tsc -b`: TS2305 (`TraceHint` not exported) / TS2353 (`hints` not a prop).

## Sabotage REDs (metric 3, mechanism proven both directions; cp backups)

- **(a) pass-2 bias disabled** (`if (hints === undefined || true) return
  defaults`): the three bias tests fail (`'#a96608' to be '#0b7181'` /
  `'#5b6a73'`) while the no-hints inertness control still passes — 7 collected /
  3 failed.
- **(b) styles recomputed over the visible subset** (`resolved[position]`
  instead of `resolved[traces.indexOf(trace)]`): only the index-stability test
  fails — 7 collected / 1 failed.
- **(c) inertness**: the no-hints control asserts literal pass-1 expectations
  and passed against the pre-change implementation in the RED run above — the
  same test green against both implementations is the byte-parity pin.
- **Python seam disabled** (`for hint in []:` in `_plot_findings`): the three
  semantic-variant tests fail (unknown variable, target-variable-outside-y,
  duplicate) while the schema-caught variants stay green — 32 collected /
  3 failed. Restored: 32/32 green.

## GREEN (focused, main repository)

- Presentation + architecture contract files: **67 collected / 0 failed**
  (junitxml), covering:
  - Metric 1 (P1/P2 equivalence): 16 validations in the main-repo suite — the
    manifest bundle pair, the configuration specimen pair (no plots: the pair
    is byte-identical, disclosed — hints have nowhere to attach), the waveform
    specimen pair (single-y hint), and the multi-y dataset specimen pair, each
    at `supported_features=frozenset()` AND a non-empty feature set, all
    finding-free and identical across pair members. The multi-y specimen is the
    case the design's underpowered clause requires.
  - Metric 2 (P3 catches): 6/6 malformed variants yield exactly one finding
    each — five in the manifest file (unknown `variable_id`;
    target-variable-outside-plot-y; duplicate; unknown `color_role`; vacuous
    object) and the 17th-hint-on-16-channel variant on the dataset specimen
    (observation targets carry exactly one value variable, so a 16-channel plot
    is structurally a dataset).
- tests/standards/ + tests/contract/test_baseline.py: **146 collected / 1
  failed** — the single failure is `test_real_tree_is_clean`
  (`sdk_version_mismatch: plugin-ui manifest 0.1.1 vs SDK lock 0.1.0`), which
  closes only when the SDK sync + submodule pointer land (design §4 order:
  main-side first). tests/sdk at the same point: **103 collected / 1 failed**
  (`test_sdk_wheel_rebuilt_from_sdist_contains_locked_standards_tree` — the
  gateway↔SDK validator byte-parity pin, same closure).
- ui: **35 collected / 0 failed** across the suite; `tsc -b` clean; eslint
  clean (`No issues found`).

## Gates (main repository, worktree `.worktrees/rowC`)

`uv run ruff check .` clean; bare config-driven `uv run mypy` clean (includes
`packages/sdk/src`). Matrix regenerated via `benchweave.standards matrix` (the
`matrix --check` lane is green once the file is committed).

## Two-repo completion

SDK branch `feat/issue6-rowC-display-hints` (standalone checkout, off its
origin/main `f7a8a47`): vendored tree re-imported from the canonical bundle
(`sync-standards`, plugin-ui 0.1.0 → 0.1.1 with lock and stamps),
`validation.py` loads plugin-ui at 0.1.1, `create_ui_resources` writes
`contract_version` 0.1.1 at its manifest/envelope/catalogue sites (the
plugin-ui-preview fixture at `:227` is a different standard and stays 0.1.0 —
verified line by line, not bulk-sed), website badge and README guide link
moved, preview
renderer refreshed via `build:preview` (hashed assets + inventory). SDK gates
on the branch: `uv run pytest` **16/0**, `uv run mypy` clean,
`uv run ruff check .` clean, `sync-standards --check` agrees, version smoke
`benchweave-sdk, version 0.0.2`. Pushed as `cd43001`.

Main repo after the submodule pointer advanced to the pushed `cd43001`:
`benchweave.standards check` clean (manifest, bundle, lock and vendored tree
agree), `matrix --check` clean, and the acceptance rule's fourth pair — the
scaffold-generated example with an author-added hinted plot vs its unhinted
twin, checked by `check-ui` at no-feature and one-feature hosts
(`tests/sdk/test_presentation_cli.py::test_scaffold_hint_pair_validates_identically`,
RED against the pre-pointer submodule: the hinted member was refused,
`assert 1 == 0`) — GREEN **8/8** in its file. Full suite with the pointer
staged: **1010 collected / 1 failed**, the single failure being
`test_submodule_head_matches_the_recorded_gitlink`, which compares the
submodule HEAD against the COMMITTED gitlink `HEAD:packages/sdk` and therefore
closes exactly when the pointer commit lands (this commit). Fixture-key note:
the registry suites require the gitignored signing keys
(`fixtures/registry/keys/*.pem`) that exist only in the maintainer's main
checkout; a fresh worktree without them fails 8 registry tests unrelated to
this change (verified: the same tests pass on the main checkout at the base
commit `8bc83a5`).
