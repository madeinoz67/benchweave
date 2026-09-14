# Development and CI

For integration authoring and hosting, see the [Device developer guide](device-developer-guide.md).

Use Python 3.13 (as pinned in `.python-version`) and uv. CI pins uv 0.11.16.
From the project root:

```sh
uv python install
uv sync --locked --dev
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync pytest
uv run --no-sync benchweave
uv build
```

Add dependencies with `uv add` or `uv add --dev`, and commit both
`pyproject.toml` and `uv.lock`. CI rejects a stale lockfile. Build dependencies
are resolved separately using the build-system requirements in `pyproject.toml`.

## UI toolchain

The `ui/` directory holds the Layered Precision workbench style guide and the
renderer bundled into the SDK wheel. It uses Node 22 (engines pin `>=22 <23`)
with a committed `package-lock.json`; run everything from `ui/`:

```sh
npm ci
npm run typecheck
npm run lint
npm test
npm run build-storybook
npm run build:preview   # rebuilds packages/sdk/src/benchweave_sdk/preview_assets
```

`build:preview` regenerates the vendored renderer the SDK wheel ships; commit
the rebuilt `preview_assets/` together with the `ui/` source change. CI's
**ui** job runs the same commands and fails if the committed renderer is stale.

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

When a synchronisation changes or deprecates a standard, `sync` writes the
lock's `compatibility.notes` as `null` — fill it in before committing: the
check deliberately halts with `compatibility_incomplete` until the migration
note is present. That halt is the operator prompt, not an error to work
around.

`docs/compatibility-matrix.md` is generated (never hand edited) from the
manifest and the SDK lock; regenerate with
`uv run python -m benchweave.standards matrix`. It carries versions, status
and migration guidance but no commit SHAs — `python -m benchweave.standards
versions` prints the live main/SDK/standards combination.

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

- **CI** runs the Python gates (ruff, config-driven mypy, pytest) plus a
  **systemd** template-verification job and a **ui** job (typecheck, lint,
  unit tests, Storybook build, renderer freshness gate, `npm audit`) on Linux.
- **Device plugins** checks independent manufacturer/model plugin projects in
  their own locked environments.
- **Package** builds sdists and wheels for the gateway and SDK, installs them
  into isolated environments on Linux and macOS, and runs the installed-wheel
  smoke (`scripts/sdk_smoke.py`), including an external example plugin built
  and tested outside the checkout.

The workflows run on pushes and pull requests. They use
read-only repository permissions, pinned action versions, timeouts and
cancellation of superseded runs. The fixture-signing keys used by the
registry tests are repository secrets materialised at job start.
The uv integration follows the [official uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/).

These checks cover the current scaffold and architecture document contracts.
They do not establish runtime conformance or hardware qualification. Hosted runs require the repository to
be pushed to GitHub with Actions enabled.

## Documentation baseline

`docs/` retains architecture 1.5, OTDP 0.3.0, interface 1.1.0, registry 1.0.0,
execution 1.0.0, decisions, acceptance reviews and implementation planning.
Superseded versions and ZIP copies have been removed from the project.
Keep future documentation here and use Git history for superseded revisions.
