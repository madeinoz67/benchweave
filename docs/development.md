# Development and CI

For integration authoring and hosting, see the [Device developer guide](device-developer-guide.md).

Use Python 3.13 (as pinned in `.python-version`) and uv. From the project
root:

```sh
uv python install
uv sync --locked --dev
uv run --no-sync ruff check .
uv run --no-sync mypy
uv run --no-sync pytest
uv run --no-sync benchweave
uv build
```

The trio of lint, type and test gates mirrors CI's main gate. The main gate
runs `uv sync`, `uv run ruff check .`, `uv run mypy`,
`uv run pytest -q -n auto -m "not timing and not browser"` and
`make check-sdk-standards`. `ruff format` is available
locally but is not part of that main gate; the one place CI enforces it is
`device-plugins.yml`, which runs `ruff format --check` inside the DPS-150
plugin project. When this page and the workflow disagree,
`.github/workflows/ci.yml` is the authority.

Add a dependency with `uv add` or `uv add --dev`. Commit both
`pyproject.toml` and `uv.lock`. `uv sync --locked --dev` enforces lockfile
freshness locally. The build resolves its dependencies in a separate step,
with the build-system requirements in `pyproject.toml`.

Coverage is measured but not gated: `uv run pytest --cov` produces a branch
coverage report for `src/benchweave`. The configuration lives under
`[tool.coverage.*]` in `pyproject.toml`. The report is informational. No
threshold is enforced locally or in CI.

## UI toolchain

The renderer is the `benchweave-ui-html` workspace member
(`packages/ui-html/`). It has Jinja partials, the `pytest11` contract gate,
and the vendored style assets pinned by the assets inventory. There is no
Node toolchain. The React reference renderer and its build lane were deleted
at the G1e cutover. The SDK's committed `preview_assets` bundle is FROZEN
at its last build (see drift-and-obligations row 7). Use these commands:

```sh
uv run pytest docs/internal/ui-contract.md   # the contract gate (also rides the default run)
uv run pytest tests/ui_html -q               # the ported proofs and harness arms
uv run pytest -m browser                     # the pattern-library axe + screenshot lane
```

## Standards synchronisation

The canonical standards live in `standards/standards-manifest.json`. The SDK
submodule (`packages/sdk`) pins them via `standards-lock.json` plus the
vendored tree under `src/benchweave_sdk/standards/`. Two make targets govern
the flow:

- `make sync-sdk-standards`: export the corpus, import it into the SDK, do a
  check of the standards tests, and run them. Changes stay uncommitted for
  review.
- `make check-sdk-standards`: non-mutating. It re-exports to a temp dir. It
  compares `standards-lock.json` and the vendored tree. It then regenerates
  the compatibility matrix. It fails when the committed file differs.

`sync` preserves the lock's `compatibility.notes` verbatim. The field is
operator-authored state (SDK STD-6). To set, update or clear it, you must
edit `standards-lock.json` by hand. `null` appears only when no note
existed. The check still halts with `compatibility_incomplete` while a
changed or deprecated standard has no migration note. That halt is the
prompt to author one, not an error to work around.

`docs/compatibility-matrix.md` is generated, never hand-edited, from the
manifest and the SDK lock. Regenerate it with
`uv run python -m benchweave.standards matrix`. It carries versions, status
and migration guidance, plus the per-version Retained-versions table (VR-52
covers stage with promotion provenance, range membership, yank, and each
release's from-predecessor migration note). The matrix renders from
committed state only. The output has no commit SHAs. `python -m
benchweave.standards versions` prints the live combination of the main, SDK
and standards versions.

### Standards dependency resolution (issue #216, #203 slice 2)

Each in-tree package declares its requirements in
`plugins/<manufacturer>/<model>/contracts/constraints.json`. The intervals
are explicit and half-open. Caret sugar is accepted only at the CLI
boundary. Caret sugar is refused wherever it is found stored. Each package
resolves its requirements into `contracts/lock.json`. That lock is canonical
JSON, re-derived, and never hand-edited. The in-tree example is
`plugins/fnirsi/dps150/contracts/`. The command family
(`python -m benchweave.standards …`):

- `list`: per standard, the declared range; the derived retained, carried
  and served sets; every yank (reason, since); and the retired identifiers.
- `pin [--package <dir>] [--set ID=INTERVAL] [--locked]`: resolve the
  constraints and (re)write the package lock. `--set` writes one interval
  (`^0.2` accepted, expanded before anything is stored). `--locked` does a
  check only. It refuses with `plugin_lock_drift` when the committed lock
  is not the resolution.
- `upgrade <standard> --precise <version> [--package <dir>]`: move exactly
  one standard's row. Every other row stays byte-identical.
- `why [--package <dir>]`: explain the current resolution. Per standard, it
  shows the authored interval, the prior locked row, the rung that fired
  (dev-opt-in, prior-retained or auto-highest-served) and the selected
  version. Then it shows the drift section. The drift section names each
  row that moved since the prior lock, and the cross-constraint verdict.
  The verdict renders only when clear. A violation surfaces as the
  family's typed error, never a rendered row. A precise override is a
  call-time arm of both `pin` and `upgrade`. Once the upgraded lock is
  committed, why honestly names the row prior-retained. The command is
  read-only. It reuses the resolver's refusals verbatim.
- `check`: the SDK-pairing lanes plus the dependency lane. It re-resolves
  every in-tree package's constraints. It byte-compares them against the
  committed lock.

Resolution is offline and deterministic. The same committed inputs give
byte-identical locks. A prior pin holds while it still satisfies its
authored interval. Auto-selection never picks a yanked version or a
pre-release.

Change propagation, end to end:

1. Change the canonical specification in the main repo.
2. When normative content changes, increment the applicable standards
   version.
3. Validate and export with `make sync-sdk-standards`.
4. Open a reviewed SDK change containing the synchronised resources.
5. Run SDK conformance, packaging and documentation gates.
6. When the standards change requires a new SDK version, release the SDK.
7. Update the main repo's submodule pointer to the released SDK commit.
8. Run the main repo integration and compatibility gates.
9. Record the final combination of the main, SDK and standards versions
   (the compatibility matrix row).
10. Regenerate and commit the matrix.

## GitHub workflows

- **CI** runs the Python gates and the standards sync check
  (`make check-sdk-standards`). The Python gates are sync, ruff check,
  config-driven mypy, and `pytest -q -n auto -m "not timing and not
  browser"`. The pytest run includes the 196 contract-gate items collected
  from `docs/internal/ui-contract.md` via `testpaths` since the G1e
  cutover. A **timing** job runs the real-paced, marker-selected set
  (`pytest -q -m timing`) serialized on its own fresh VM. A **windows** job
  runs the gates selection on windows-latest as an evidence lane
  (issue #207). In slice 1, a test red is carried by the warning
  annotation, the job summary and the junitxml artifact. It does not block
  merges. Setup reds block. A **systemd** template-verification job runs on
  Linux. The former **ui** Node job was deleted at the G1e cutover with
  the React renderer it gated.
- **Device plugins** checks independent plugin projects per manufacturer
  and model, in their own locked environments.
- **Package** builds sdists and wheels for the gateway and SDK. It installs
  them into isolated environments on Linux and macOS. It runs the
  installed-wheel smoke (`scripts/sdk_smoke.py`). The smoke includes an
  external example plugin built and tested outside the checkout. The same
  job also builds the `benchweave-ui-html` workspace member's wheel and
  proves it standalone in a fresh venv outside the checkout. It proves
  import, version equality with its `pyproject.toml`, and the entry point
  for the `pytest11` contract gate. It proves an installed set of exactly
  the package plus its two declared runtime dependencies.

The workflows run on pushes and pull requests. They use
read-only repository permissions, pinned action versions, timeouts and
cancellation of superseded runs. The fixture-signing keys used by the
registry tests are repository secrets materialised at job start.
The uv integration follows the [official uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/).

These checks cover the current scaffold and architecture document contracts.
They do not establish runtime conformance or hardware qualification. Hosted
runs need the repository on GitHub, with Actions enabled.

## Documentation baseline

`docs/` retains architecture 1.5, OTDP 0.2.2, interface 0.1.0, registry 0.1.2,
execution 0.2.0, decisions, acceptance reviews and implementation planning.
Superseded versions and ZIP copies were removed from the project.
Keep future documentation here. Use Git history for superseded revisions.
