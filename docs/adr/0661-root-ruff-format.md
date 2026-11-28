# 0661. Enforce the root Ruff formatter after a Python baseline

- **Status:** Accepted
- **Issue:** BenchWeave #661
- **Decision:** The repository owner approved the baseline and CI enforcement on Orca item 42.

## Context

A clean snapshot at 4e375e3f fails Ruff 0.17.4 with 374 files reported. The lock is in `uv.lock`. Root CI runs lint in `.github/workflows/ci.yml`, and `scripts/gate.py:GATE_NAMES` and its Ruff command also cover lint. The Orca worker brief additionally names root formatting through `issue_flow.ts:REPO_GATES` and `buildBrief`. The DPS-150 workflow already uses a separate project and formatter check.

## Decision

Use a dedicated migration PR in a low-overlap merge window, followed by CI enforcement. Restrict the root format check to Python source and stubs. Exclude standards and the separately gated DPS-150 project from the root format check. Retain the existing root exclusions and lint config.

| Option | Trade-off |
| --- | --- |
| Accepted: clean baseline and enforce root format | Catches every in-scope regression after one coordinated rebase window. |
| Keep root formatting optional | Aligns the worker brief with current CI and avoids churn. The project would give up a root formatting regression signal. |

## Contract and tasks

1. **F1, establish scope.** In the migration PR, document one root command using the existing pinned environment. A tested candidate is `uv run --locked ruff format --config pyproject.toml --config 'include = ["*.py", "*.pyi"]' --config 'format.exclude = ["standards", "plugins/fnirsi/dps150"]' --check .`. Inline overrides apply only to this formatter invocation. Explicit root config fixes its scope independently of nested package configs. The existing root config supplies the exclusions for docs and packages/sdk. The scope probe at 4e375e3f reported 341 Python failures and zero paths under standards, DPS-150 or the SDK. Probe failing and ignored fixtures before locking the command.
2. **F2, baseline.** After F1, run the same command with `--check` removed. Keep generated formatting in its own commit and review the file list and formatter output. The check must exit zero. Require lint, mypy and pytest to pass, and an empty diff for standards, Markdown and the SDK submodule pointer. Compare the final mechanical file set with open PRs before landing. Re-run the check after rebasing to the merge base.
3. **F3, enforce.** After the baseline is on main, use that exact locked command in root CI and update the development guide. Align the local gate wrapper and Orca worker brief with the approved root command. The wrapper must expose format failures as a failing verification result. The root workflow must pass on the clean baseline and fail with exactly one reported path when given one newly unformatted in-scope Python file. Verify that Markdown snippets and standards fixtures remain outside the command and that the independent DPS-150 gate retains its current command.
4. **F4, verify alignment.** Compare the documented formatter command, CI, gate wrapper and generated worker brief. The separate Orca brief change can be prepared in parallel with F3 after F2, then enabled alongside CI. Review existing gate-name selection and results consumers before changing the wrapper.

## Stability and rollback

Preserve standards bytes, Markdown, SDK ownership, DPS-150's independent checks, the lint rule set, and application behaviour. Revert enforcement and the corresponding worker-brief requirement together if the CI rollout needs rollback. Keep the mechanical baseline unless a regression requires reverting it. Revert enforcement first if the baseline must be reverted.
