.PHONY: sync-sdk-standards check-sdk-standards

# One source of truth for uv's project environment (non-dot venv/, per the
# repo convention). := deliberately: an ambient value must not reintroduce
# a stray .venv/ on any target in this file. make 3.81 (macOS CLT) rejects
# target-specific `export` lines, so the pin is file-scoped instead.
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
# then gate the committed compatibility matrix on a fresh render.
check-sdk-standards:
	uv run python -m benchweave.standards check
	uv run python -m benchweave.standards matrix --check
