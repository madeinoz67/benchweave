## What

<!-- One or two sentences: what does this PR change? -->

## Why

<!-- The problem or motivation. Link issues as `Fixes #123`. -->

## Gates

All run locally before review:

- [ ] `uv run pytest -q`
- [ ] `uv run ruff check .`
- [ ] `uv run mypy`
- [ ] `make check-sdk-standards` — if `packages/sdk` or the standards bundle is touched

## Notes for reviewers

<!-- Anything non-obvious: design trade-offs, follow-ups, evidence pointers. -->

- [ ] Every deferral named in this PR body cites an open issue (created at PR-open
      time if absent) — orphan deferrals block merge, reviewer-enforced (#69).
