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

The lint/type/test trio mirrors CI's main gate, which runs `uv sync`,
`uv run ruff check .`, `uv run mypy`,
`uv run pytest -q -n auto -m "not timing and not browser"` and
`make check-sdk-standards`. `ruff format` is available
locally but is not part of that main gate; the one place CI enforces it is
`device-plugins.yml`, which runs `ruff format --check` inside the DPS-150
plugin project. When this page and the workflow disagree,
`.github/workflows/ci.yml` is the authority.

Add dependencies with `uv add` or `uv add --dev`, and commit both
`pyproject.toml` and `uv.lock`; `uv sync --locked --dev` enforces lockfile
freshness locally. Build dependencies
are resolved separately using the build-system requirements in `pyproject.toml`.

Coverage is measured but not gated: `uv run pytest --cov` produces a branch
coverage report for `src/benchweave` (configured under `[tool.coverage.*]` in
`pyproject.toml`). The report is informational — no threshold is enforced
locally or in CI.

## UI toolchain

The renderer is the `benchweave-ui-html` workspace member
(`packages/ui-html/`) — Jinja partials, the pytest11 contract gate, and the
vendored style assets pinned by the assets inventory. There is no Node
toolchain: the React reference renderer and its build lane were deleted at
the G1e cutover, and the SDK's committed `preview_assets` bundle is FROZEN
at its last build (see drift-and-obligations row 7). The working commands:

```sh
uv run pytest docs/internal/ui-contract.md   # the contract gate (also rides the default run)
uv run pytest tests/ui_html -q               # the ported proofs and harness arms
uv run pytest -m browser                     # the pattern-library axe + screenshot lane
```

## Standards synchronisation

The canonical standards live in `standards/standards-manifest.json`; the SDK
submodule (`packages/sdk`) pins them via `standards-lock.json` plus the
vendored tree under `src/benchweave_sdk/standards/`. Two make targets govern
the flow:

- `make sync-sdk-standards` — export the corpus, import it into the SDK,
  verify and run the standards tests; changes stay uncommitted for review.
- `make check-sdk-standards` — non-mutating: re-export to a temp dir and
  compare lock + vendored tree, then regenerate the compatibility matrix and
  fail when the committed file differs.

`sync` preserves the lock's `compatibility.notes` verbatim: the field is
operator-authored state (SDK STD-6), and hand-editing the lock is the only way
to set, update or clear it — `null` appears only when no note existed. The
check still halts with `compatibility_incomplete` while a changed or
deprecated standard has no migration note; that halt is the prompt to author
one, not an error to work around.

`docs/compatibility-matrix.md` is generated (never hand edited) from the
manifest and the SDK lock; regenerate with
`uv run python -m benchweave.standards matrix`. It carries versions, status
and migration guidance, plus the per-version Retained-versions table
(stage with promotion provenance, range membership, yank, and each
release's from-predecessor migration note — VR-52), all rendered from
committed state only; no commit SHAs — `python -m benchweave.standards
versions` prints the live main/SDK/standards combination.

### Standards dependency resolution (issue #216, #203 slice 2)

Each in-tree package authors its requirements in
`plugins/<manufacturer>/<model>/contracts/constraints.json` (explicit
half-open intervals; caret sugar is accepted only at the CLI boundary and
refuses wherever it is found stored) and resolves them into
`contracts/lock.json` — canonical JSON, re-derived, never hand-edited; the
in-tree example is `plugins/fnirsi/dps150/contracts/`. The command family
(`python -m benchweave.standards …`):

- `list` — per standard: the declared range, the derived retained /
  carried / served sets, every yank (reason, since) and the retired
  identifiers.
- `pin [--package <dir>] [--set ID=INTERVAL] [--locked]` — resolve the
  constraints and (re)write the package lock; `--set` authors one interval
  (`^0.2` accepted, expanded before anything is stored); `--locked`
  verifies only, refusing `plugin_lock_drift` when the committed lock is
  not the resolution.
- `upgrade <standard> --precise <version> [--package <dir>]` — move
  exactly one standard's row; every other row stays byte-identical.
- `why [--package <dir>]` — explain the current resolution: per standard,
  the authored interval, the prior locked row, the rung that fired
  (dev-opt-in / prior-retained / auto-highest-served) and the selected
  version, then the drift section naming each row that moved since the
  prior lock and the cross-constraint verdict (rendered only when clear —
  a violation surfaces as the family's typed error, never a rendered row).
  A precise override is a call-time arm of `pin`/`upgrade`; once the
  upgraded lock is committed, why honestly names the row prior-retained.
  Read-only; reuses the resolver's refusals verbatim.
- `check` — the SDK-pairing lanes plus the dependency lane: every in-tree
  package's constraints are re-resolved and byte-compared against its
  committed lock.

Resolution is offline and deterministic: the same committed inputs give
byte-identical locks, a prior pin holds while it still satisfies its
authored interval, and auto-selection never picks a yanked version or a
pre-release.

Change propagation, end to end:

1. Change the canonical specification in the main repo.
2. Increment the applicable standards version when normative content changes.
3. Validate and export (`make sync-sdk-standards`).
4. Open a reviewed SDK change containing the synchronised resources.
5. Run SDK conformance, packaging and documentation gates.
6. Release the SDK when the standards change requires a new SDK version.
7. Update the main project's submodule pointer to the released SDK commit.
8. Run main-project integration and compatibility gates.
9. Record the final main / SDK / standards version combination
   (compatibility matrix row): regenerate and commit the matrix.

## GitHub workflows

- **CI** runs the Python gates (sync, ruff check, config-driven mypy,
  `pytest -q -n auto -m "not timing and not browser"` — including the 196
  contract-gate items collected from `docs/internal/ui-contract.md` via
  `testpaths` since the G1e cutover) and the standards sync check
  (`make check-sdk-standards`), plus a **timing** job that runs the
  real-paced, marker-selected set (`pytest -q -m timing`) serialized on its
  own fresh VM, a **browser** lane over the pattern library, and a
  **systemd** template-verification job on Linux. The former **ui** Node
  job was deleted at the G1e cutover with the React renderer it gated.
- **Device plugins** checks independent manufacturer/model plugin projects in
  their own locked environments.
- **Package** builds sdists and wheels for the gateway and SDK, installs them
  into isolated environments on Linux and macOS, and runs the installed-wheel
  smoke (`scripts/sdk_smoke.py`), including an external example plugin built
  and tested outside the checkout. The same job also builds the
  `benchweave-ui-html` workspace member's wheel and proves it standalone in a
  fresh venv outside the checkout: import, version equality with its
  `pyproject.toml`, the `pytest11` contract-gate entry point, and an installed
  set of exactly the package plus its two declared runtime dependencies.

The workflows run on pushes and pull requests. They use
read-only repository permissions, pinned action versions, timeouts and
cancellation of superseded runs. The fixture-signing keys used by the
registry tests are repository secrets materialised at job start.
The uv integration follows the [official uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/).

These checks cover the current scaffold and architecture document contracts.
They do not establish runtime conformance or hardware qualification. Hosted runs require the repository to
be pushed to GitHub with Actions enabled.

## Documentation baseline

`docs/` retains architecture 1.5, OTDP 0.2.2, interface 0.1.0, registry 0.1.2,
execution 0.2.0, decisions, acceptance reviews and implementation planning.
Superseded versions and ZIP copies have been removed from the project.
Keep future documentation here and use Git history for superseded revisions.
