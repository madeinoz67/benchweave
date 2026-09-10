# Development and CI

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

## GitHub workflows

- **CI** checks lint, formatting and types on Linux, and tests the pinned Python
  version on Linux, macOS and Windows. Its dedicated **Architecture contracts**
  job runs the [architecture validation suite](architecture-validation.md) on
  every push and pull request, including changes that affect only documents.
- **Package** builds an sdist and wheel, installs the wheel into an isolated
  environment, and checks the CLI and typing marker outside the checkout.

Both workflows run on pushes, pull requests and manual dispatch. They use
read-only repository permissions, pinned action commits, timeouts and
cancellation of superseded runs. They do not need repository secrets.
The uv integration follows the [official uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/).

These checks cover the current scaffold and architecture document contracts.
They do not establish runtime conformance or hardware qualification. Hosted runs require the repository to
be pushed to GitHub with Actions enabled.

## Documentation baseline

`docs/` retains architecture 1.5, OTDP 0.3.0, interface 1.1.0, registry 1.0.0,
execution 1.0.0, decisions, acceptance reviews and implementation planning.
Superseded versions and ZIP copies have been removed from the project.
Keep future documentation here and use Git history for superseded revisions.
