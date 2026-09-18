# Plugin UI contracts 0.1.1 — validation report

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

The SDK-side sync (vendored 0.1.1 tree, lock, stamps, `validation.py` tuple,
scaffold contract_version literals), the pushed `feat/issue6-rowC-display-hints`
SDK branch, the submodule pointer commit and the post-pointer full-suite runs
are recorded in the commits following this report on the main-repo branch;
the scaffold-generated example's hinted/unhinted pair is measured there
(`tests/sdk/test_presentation_cli.py`), completing the acceptance rule's
fourth pair.
