.PHONY: sync-sdk-standards check-sdk-standards hooks

# One source of truth for uv's project environment (non-dot venv/, per the
# repo convention). := deliberately: an ambient value must not reintroduce
# a stray .venv/ on any target in this file. make 3.81 (macOS CLT) rejects
# the single-line target-specific `export` shape (`target: export FOO :=`
# doubling as the rule); the two-line form parses, but the pin is
# file-scoped anyway — broader than forced, deliberately: it also covers
# future bare `uv run` lines outside the two sdk-standards targets.
export UV_PROJECT_ENVIRONMENT := venv

# Export the canonical corpus, import it into the SDK submodule, verify the
# result and run the standards test surface. Changes are left uncommitted.
sync-sdk-standards:
	@if [ -d packages/sdk/.git ] && [ "$$(git -C packages/sdk rev-parse HEAD)" != "$$(git ls-files -s packages/sdk | awk '{print $$1}')" ]; then \
		echo "submodule HEAD differs from the committed pointer; commit the pointer first" && exit 1; \
	fi
	git submodule update --init --recursive
	@test -z "$$(git -C packages/sdk status --porcelain)" || (echo "submodule tree dirty; commit first" && exit 1)
	uv run python -m benchweave.standards export
	uv run --project packages/sdk benchweave-sdk sync-standards .standards-bundle
	uv run python -m benchweave.standards check
	uv run pytest -q tests/sdk tests/standards
	@uv run python -m benchweave.standards versions

# Non-mutating: re-export to a temp dir and compare lock + vendored tree,
# then gate the committed compatibility matrix on a fresh render, and hold
# the SDK tree's zero-literal gate (#203 slices 1+7 — this target's name is
# its scope: the sdk tree, at the submodule pin). The gateway, plugins and
# docs scopes gate through the pytest suite (test_zero_literal_gate) and
# the device-plugins lane, whose checkouts always have their trees; a bare
# default-scope invocation here would refuse in submodule-absent worktrees
# (fold row 1).
check-sdk-standards:
	uv run python -m benchweave.standards check
	uv run python -m benchweave.standards matrix --check
	uv run python scripts/standards/count_version_literals.py --scope sdk

# Install the name-screen git hooks (issue #518): .githooks/pre-commit and
# .githooks/pre-push, wired to .claude/hooks/name-screen.mjs, PLUS the chain
# shims (post-commit/post-merge) that forward to a GLOBAL hooksPath when one
# is configured — a bare local core.hooksPath override would silence the
# global hooks (the gortex post-commit/post-merge on the owner machine).
# Run from the PRIMARY checkout: core.hooksPath is one setting shared across
# every worktree of this repository family.
hooks:
	chmod +x .githooks/pre-commit .githooks/pre-push .githooks/post-commit .githooks/post-merge
	git config core.hooksPath .githooks
	@echo "name-screen hooks installed (core.hooksPath=.githooks; chain shims forward post-commit/post-merge to a global hooksPath when set)"
