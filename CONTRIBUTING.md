# Contributing to BenchWeave

Thanks for considering a contribution. This project follows the
[Contributor Covenant](CODE_OF_CONDUCT.md); by participating you agree to
uphold it.

## Getting set up

- Python 3.13+ with [uv](https://docs.astral.sh/uv/).
- Clone with submodules — the SDK is its own repository:

  ```sh
  git clone --recurse-submodules https://github.com/madeinoz67/benchweave.git
  ```

- This repo keeps a non-dot `venv/`; keep uv pointed at it so it does not
  create a stray `.venv/`:

  ```sh
  UV_PROJECT_ENVIRONMENT=venv uv sync
  ```

## Before you open a PR

All gates must pass locally — the same commands CI runs:

```sh
uv run pytest -q
uv run ruff check .
uv run mypy          # config-driven; also covers packages/sdk/src
make check-sdk-standards
```

A handful of registry tests sign fixtures with private keys that are not in
the repository (CI materialises them from secrets); on a fresh clone those
tests **skip** with a named reason — skips there are expected, failures are
not.

Bug fixes ship test-first: a failing test that reproduces the bug lands in
the same change as the fix.

## Workflow

- Work on a feature branch; `main` only receives merges via pull request.
- Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, …) — the
  changelog is generated from them by git-cliff.
- `packages/sdk` is a separate repository ([benchweave-sdk](https://github.com/madeinoz67/benchweave-sdk)).
  Changes under it are committed and pushed **there first**, then the advanced
  submodule pointer lands as a second commit here.
- Keep commits small — one logical change each.

## Reporting bugs

Open an issue with the version, your Python version, and a minimal
reproduction. Security issues follow [SECURITY.md](SECURITY.md) — never an issue.
