# SDK Publishing — PyPI + Homebrew Tap

**Date:** 2026-09-15
**Status:** Approved design (brainstorm → this spec → implementation plan)
**Repos touched:** `madeinoz67/benchweave-sdk` (primary), `madeinoz67/benchweave-ui` (workflow slim), `madeinoz67/homebrew-tap` (new formula)

## Context

The SDK split made `benchweave-sdk` a first-class repo (`packages/sdk` submodule, self-sufficient since 2026-09-15). The remaining deliverable: developers must be able to **install** it easily — `pip install benchweave-sdk` from PyPI plus `brew install madeinoz67/tap/benchweave-sdk`. Today the SDK repo's `publish.yml` only *proves* publishability; distribution assets are attached to main-repo GitHub releases by `package.yml`.

**Verified grounding (2026-09-15):**

- `benchweave-sdk` name is **free on PyPI** (project JSON → 404).
- The SDK is **pure Python** (click, jsonschema, referencing, rfc3339-validator, rfc3987, rich, textual; hatchling build). No compiled dependencies — one universal `py3-none-any` wheel + sdist installs on every OS/arch combination.
- `macos-13` (last Intel-by-default image) retired 2025-12-04; `macos-15-intel` is the interim Intel lane (Intel support ends ~Fall 2027); `macos-latest` is arm64.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Publish auth | **A1 — PyPI Trusted Publishing (OIDC)** | No stored secrets; re-runnable. One-time publisher registration by the operator. |
| Artifacts | **Universal wheel + sdist** (`py3-none-any`) | Pure Python; platform tags would be theater. Cross-platform confidence comes from the install-smoke matrix, not the tags. |
| Brew source | **B1 — formula installs from PyPI** | One sdist URL + one sha256 per bump; `livecheck` on PyPI JSON. Matches the tap's pragmatic style (voice-server precedent). |
| License | **MIT for the SDK package only** | Public PyPI distribution needs granted rights; MIT matches the principal's other tools. Main gateway repo stays proprietary. |
| Dev releases | **None for now** | PyPI uploads are immutable — a devN lane never overwrites, it accumulates permanently (pollution). Project is not at RC stage. When wanted, RCs need zero redesign: a `vX.Y.ZrcN` tag publishes `X.Y.ZrcN` (PEP 440); devs opt in via `pip install --pre`. |

## Release Flow (SDK repo owns distribution)

1. Bump `version` in `packages/sdk/pyproject.toml` manually (no hatch-vcs — YAGNI).
2. Commit + push to SDK `main` (per the two-repo operating model, SDK-only changes go direct).
3. Tag `v<version>` on SDK main → publish the GitHub Release (operator action).
4. `publish.yml` (rewritten) runs:

**Job `build`** (ubuntu-latest): checkout (no submodules) → uv sync → `benchweave-sdk sync-standards --check` → `uv build` → upload wheel+sdist as workflow artifact.

**Job `smoke`** (needs `build`, matrix `fail-fast: false`):

| Runner | OS / arch |
|---|---|
| `ubuntu-latest` | linux x86_64 |
| `ubuntu-24.04-arm` | linux arm64 |
| `macos-latest` | macOS arm64 (Apple Silicon) |
| `macos-15-intel` | macOS x86_64 |

Each cell: download artifact → `uv venv /tmp/sdk-smoke` → `uv pip install dist/*.whl` → `benchweave-sdk --version` → `benchweave-sdk new /tmp/example --with-ui` → `benchweave-sdk check /tmp/example/src/example_plugin/descriptor.json` (same script the lane runs today).

**Job `publish`** (needs `smoke`, permissions `id-token: write` + `contents: read`): download artifact → **version guard** (tag minus leading `v` must equal `pyproject.toml` `project.version`, parsed with `tomllib` — fail fast on mismatch) → `pypa/gh-action-pypi-publish` (OIDC).

`workflow_dispatch` stays for retry runs: it takes a required `tag` input, checks out that tag, and the same version guard applies — a dispatch can never publish the default branch, only an existing tag that matches `project.version`.

## License Change (SDK repo)

- `pyproject.toml`: `license = { text = "Proprietary" }` → `license = "MIT"` (PEP 639 SPDX expression) + `license-files = ["LICENSE"]`.
- Add `LICENSE` (MIT, copyright madeinoz67).
- Scope: SDK package only. The main BenchWeave repo remains proprietary — this spec opens nothing else.

## Main Repo Change (`benchweave-ui`, working branch per the 2026-09-14 directive)

`package.yml`:

- **Keep** the `build` matrix job (installed-gateway + SDK proof on ubuntu/macos) — it is a gate, not a distribution step.
- **Move** `make check-sdk-standards` from the `release-sdk` job into `build` (before the smoke step) so the standards-sync release gate survives.
- **Delete** the `release-sdk` asset-attach job. PyPI + SDK-repo releases become the single distribution truth; gateway releases stop carrying SDK wheels.

## Brew Formula (tap repo)

`Formula/benchweave-sdk.rb`:

```ruby
class BenchweaveSdk < Formula
  desc "Offline authoring and conformance tools for BenchWeave OTDP device plugins"
  homepage "https://github.com/madeinoz67/benchweave-sdk"
  url "https://files.pythonhosted.org/packages/source/b/benchweave-sdk/benchweave-sdk-<VERSION>.tar.gz"
  sha256 "<SDIST_SHA256>"
  license "MIT"

  livecheck do
    url "https://pypi.org/pypi/benchweave-sdk/json"
    regex(/"version":\s*"?(\d+(?:\.\d+)+)"?/i)
  end
  depends_on "python@3.13"

  def install
    virtualenv_create(libexec, "python3.13")
    virtualenv_install_with_resources
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/benchweave-sdk --version")
  end
end
```

- One formula serves macOS arm64, macOS Intel, and Linuxbrew (pure-Python venv; no arch blocks).
- Dependencies resolve from PyPI at `brew install` time — accepted for a personal tap (B3 resource-pinning rejected as high-maintenance).
- Upgrade procedure: `brew livecheck` → bump `version`/`url` → refresh sdist sha256 → commit to tap.

## Documentation Surface

Docs-coverage duty: installation docs must gain the published paths once they exist. Enumerated surfaces (verified 2026-09-15):

- SDK repo `README.md`:
  - **New "Installation" section** — stable: `pip install benchweave-sdk`, `uv tool install benchweave-sdk`, `brew install madeinoz67/tap/benchweave-sdk`; bleeding-edge: `pip install git+https://github.com/madeinoz67/benchweave-sdk.git` (the documented dev channel — best practice instead of PyPI dev builds); from-source fallback retained.
  - **Rewrite "Distribution rights" section** (currently written for the proprietary license) for MIT.
- SDK repo `docs/plugin-sdk.md` (the plugin-author guide): add the published install paths to its getting-started prerequisites.
- Both repos: implementation sweeps for install-adjacent passages (`grep -ri "benchweave-sdk" README* docs/`) so no doc still tells developers to clone-and-sync when a published artifact exists; main-repo docs link to the SDK README rather than duplicating.

## Operator Prerequisites (one-time, outside CI)

1. PyPI account with 2FA; register Trusted Publisher: repository `madeinoz67/benchweave-sdk`, workflow `publish.yml`, default environment.
2. First GitHub Release on the SDK repo (`v0.1.0` or `v0.2.0` — whichever the first published version is).

## Failure Modes

| Failure | Behavior |
|---|---|
| Standards lock stale | `hatch_build.py` refuses at `uv build` (existing invariant) — nothing reaches PyPI. |
| Tag ≠ pyproject version | Version-guard step fails before publish. |
| Duplicate version on PyPI | PyPI rejects; workflow fails visibly; fix = bump version + new tag. |
| Publish job flaked post-release | Re-run via `workflow_dispatch` (Trusted Publishing allows re-runs). |
| Intel lane retired (~Fall 2027) | Drop `macos-15-intel` from the matrix — nothing else changes. |
| PyPI name squatted before first publish | Re-evaluate name (`benchweave-sdk` vs alternatives) — registration happens at first publish, so publish soon after merge. |

## Verification (first release is the verification event)

1. Green `publish.yml` run on the release tag: 4/4 smoke cells + PyPI upload.
2. Post-publish: clean-venv `pip install benchweave-sdk` on the Mac + one Linux box; `benchweave-sdk --version`.
3. `brew install ./Formula/benchweave-sdk.rb` → `brew test benchweave-sdk` → `benchweave-sdk --version`.
4. Main repo: `package.yml` build job green on a PR touching it; confirm no release-attach job remains.

## Out of Scope

- Main-repo (gateway) distribution changes beyond the `package.yml` slim.
- Signing (Sigstore) of PyPI artifacts; can be added later as a publish step.
- Automation of the tap bump (manual two-line bump accepted).
- Dev/nightly builds from main (rejected 2026-09-15: PyPI immutability means each devN is permanent — pollution with no overwrite benefit).
- Windows smoke (wheel is universal; Windows untested and unsupported as today).
