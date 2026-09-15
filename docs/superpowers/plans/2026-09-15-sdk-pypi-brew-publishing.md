# SDK PyPI + Homebrew Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish `benchweave-sdk` to PyPI via Trusted Publishing (universal wheel + 4-OS/arch smoke matrix), flip the SDK to MIT, slim the main repo's `package.yml` to gate-only, and add a PyPI-sourced Homebrew formula to `madeinoz67/homebrew-tap`.

**Architecture:** The SDK repo (`packages/sdk`, own repo `madeinoz67/benchweave-sdk`) becomes the single distribution owner: release tag → `publish.yml` builds once, smoke-installs the wheel on ubuntu/amd64, ubuntu/arm64, macos/arm64, macos/amd64, then pushes to PyPI with OIDC. Main repo keeps its build gate but stops attaching SDK assets to gateway releases. The tap installs the published sdist into a `python@3.13` venv.

**Tech Stack:** uv + hatchling (PEP 639), GitHub Actions (`actions/checkout@v4`, `astral-sh/setup-uv@v5`, `pypa/gh-action-pypi-publish@release/v1`), Homebrew `virtualenv_install_with_resources`, pytest, actionlint.

**Spec:** `docs/superpowers/specs/2026-09-15-sdk-pypi-brew-publishing-design.md`

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-15-sdk-pypi-brew-publishing-design.md` (main repo, local-untracked).
- All SDK-repo work happens in `/Users/seaton/Documents/src/benchweave-ui/packages/sdk` and commits **directly to its `main`**, pushed to `origin/main` after each task clears its gates (two-repo operating model).
- Main-repo work (Task 8) goes on a working branch — **no commits to main** (2026-09-14 directive); merge is the principal's call.
- Every `uv` invocation in the SDK repo/subagent shells must set `UV_PROJECT_ENVIRONMENT=venv` (non-dot venv; stray `.venv/` is a known failure).
- Gates before every commit: `uv run ruff check .` (line length 100) and `uv run mypy` (config-driven, never explicit path args). Workflow files additionally pass `actionlint`.
- Commit style matches SDK history: `feat(scope):`, `fix(scope):`, `docs:`, `ci:`.
- No secrets in any repo file. PyPI auth is OIDC only (Trusted Publishing) — no tokens anywhere.
- Dev releases: none. Stable tags only; `pip install git+...` is the documented bleeding-edge channel.
- gortex-first for source edits; this plan's file paths are repo-relative (`packages/sdk/...` = benchweave-ui view).

---

### Task 1: Tag–version guard script (TDD)

**Files:**
- Create: `packages/sdk/scripts/verify_release_tag.py`
- Test: `packages/sdk/tests/test_verify_release_tag.py`
- Modify: `packages/sdk/.github/workflows/ci.yml` (add pytest lane)

**Interfaces:**
- Consumes: nothing (stdlib only — `tomllib`, `argparse`).
- Produces: CLI `verify_release_tag.py <tag> --pyproject <path>` → exit 0 when `tag.removeprefix("v") == project.version`; exit 1 mismatch; exit 2 unreadable pyproject. Task 3's publish job invokes exactly this.

- [ ] **Step 1: Write the failing tests**

Create `packages/sdk/tests/test_verify_release_tag.py`:

```python
"""Verify the release-tag guard used by the publish workflow."""

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_tag.py"
PYPROJECT = ROOT / "pyproject.toml"


def run(tag: str, pyproject: Path = PYPROJECT) -> subprocess.CompletedProcess[int]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), tag, "--pyproject", str(pyproject)],
        capture_output=True,
        text=True,
        check=False,
    )


def write_pyproject(tmp_path: Path, version: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8")
    return path


def test_tag_with_v_prefix_matches() -> None:
    assert run("v9.9.9", write_pyproject(Path("/tmp"), "9.9.9")).returncode == 0


def test_bare_tag_matches() -> None:
    assert run("1.2.3", write_pyproject(Path("/tmp"), "1.2.3")).returncode == 0


def test_pre_release_tag_matches() -> None:
    assert run("v0.2.0rc1", write_pyproject(Path("/tmp"), "0.2.0rc1")).returncode == 0


def test_mismatch_fails_with_message(tmp_path: Path) -> None:
    result = run("v0.2.0", write_pyproject(tmp_path, "0.1.0"))
    assert result.returncode == 1
    assert "does not match" in result.stderr


def test_missing_pyproject_is_config_error(tmp_path: Path) -> None:
    assert run("v1.0.0", tmp_path / "nope.toml").returncode == 2


def test_real_pyproject_tag_matches() -> None:
    version = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert run(f"v{version}").returncode == 0
```

(Note: the two `write_pyproject(Path("/tmp"), ...)` calls are stateless — the script reads only the file passed; they may use any existing dir. If `/tmp` offends, switch those two to `tmp_path` fixtures by adding the pytest arg.)

- [ ] **Step 2: Run tests, verify they fail**

```sh
cd packages/sdk && UV_PROJECT_ENVIRONMENT=venv uv sync --extra test && UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/test_verify_release_tag.py -v
```
Expected: collection ERROR — `scripts/verify_release_tag.py` does not exist.

- [ ] **Step 3: Implement the script**

Create `packages/sdk/scripts/verify_release_tag.py`:

```python
"""Verify a release tag equals project.version before publishing to PyPI."""

import argparse
import sys
import tomllib
from pathlib import Path


def tag_matches(tag: str, version: str) -> bool:
    return tag.removeprefix("v") == version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, e.g. v0.1.0")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args(argv)
    try:
        version = tomllib.loads(args.pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        print(f"verify_release_tag: cannot read project.version from {args.pyproject}: {exc}", file=sys.stderr)
        return 2
    if not tag_matches(args.tag, version):
        print(f"verify_release_tag: tag {args.tag!r} does not match project.version {version!r}", file=sys.stderr)
        return 1
    print(f"verify_release_tag: tag {args.tag} matches project.version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests, verify pass + full suite health**

```sh
UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/test_verify_release_tag.py -v && UV_PROJECT_ENVIRONMENT=venv uv run pytest -q
```
Expected: new tests 6/6 PASS; full suite passes (repo convention is gate-clean — if unrelated failures appear, STOP and report rather than committing).

- [ ] **Step 5: Add the pytest lane to SDK ci.yml**

In `packages/sdk/.github/workflows/ci.yml`, change `run: uv sync` to `run: uv sync --extra test` and insert after the Lint step:

```yaml
      - name: Tests
        run: uv run pytest -q
```

- [ ] **Step 6: Lint, type, actionlint**

```sh
UV_PROJECT_ENVIRONMENT=venv uv run ruff check . && UV_PROJECT_ENVIRONMENT=venv uv run mypy && actionlint .github/workflows/ci.yml
```
Expected: ruff clean, mypy clean, actionlint no findings.

- [ ] **Step 7: Commit and push**

```sh
git add scripts/verify_release_tag.py tests/test_verify_release_tag.py .github/workflows/ci.yml
git commit -m "feat(publish): tag-version guard with tests and a pytest CI lane"
git push origin main
```

---

### Task 2: MIT license flip

**Files:**
- Create: `packages/sdk/LICENSE`
- Modify: `packages/sdk/pyproject.toml` (license fields)
- Modify: `packages/sdk/README.md` (intro line 5 + "Distribution rights" final section)

**Interfaces:**
- Consumes: nothing.
- Produces: `license = "MIT"` + `license-files = ["LICENSE"]` metadata in every built artifact; Task 5's PyPI page and Task 7's formula `license "MIT"` depend on it.

- [ ] **Step 1: Write the LICENSE file**

Create `packages/sdk/LICENSE` (year 2026, holder matching the principal's public handle):

```text
MIT License

Copyright (c) 2026 madeinoz67

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Flip pyproject license fields**

In `packages/sdk/pyproject.toml` replace:

```toml
license = { text = "Proprietary" }
```
with:
```toml
license = "MIT"
license-files = ["LICENSE"]
```

- [ ] **Step 3: Update README intro + Distribution rights**

In `packages/sdk/README.md`:

Replace the intro sentence (line 5) `... it is not yet published to a package index.` with `... published to PyPI as benchweave-sdk.` (keep the version baseline wording intact).

Replace the entire final "## Distribution rights" section with:

```markdown
## Distribution rights

The SDK package is distributed under the [MIT licence](LICENSE). The vendored OTDP, registry and presentation contract sets and the generated templates are part of this package and carry the same grant. Plugin authors choose their own licence; generated examples contain no licence grant and make no claim on plugin code written with them.
```

- [ ] **Step 4: Build and verify metadata carries MIT + the file**

```sh
rm -rf dist && UV_PROJECT_ENVIRONMENT=venv uv build && unzip -p dist/*.whl '*.dist-info/METADATA' | grep -iE '^(License|License-File)' && tar -tzf dist/*.tar.gz | grep -x 'benchweave-sdk-0.1.0/LICENSE' ; unzip -l dist/*.whl | grep LICENSE
```
Expected: `License: MIT`, `License-File: LICENSE`; LICENSE present in the sdist listing and the wheel.

- [ ] **Step 5: Gates, commit, push**

```sh
UV_PROJECT_ENVIRONMENT=venv uv run ruff check . && UV_PROJECT_ENVIRONMENT=venv uv run mypy
git add LICENSE pyproject.toml README.md
git commit -m "docs(license): relicense the SDK package MIT for PyPI distribution"
git push origin main
```

---

### Task 3: publish.yml — build → 4-way smoke → Trusted-Publish

**Files:**
- Modify: `packages/sdk/.github/workflows/publish.yml` (full replacement)

**Interfaces:**
- Consumes: `scripts/verify_release_tag.py` from Task 1 (exact CLI above).
- Produces: on a published GitHub Release (or a `workflow_dispatch` with `tag` input), artifacts `dist/*.whl` + `dist/*.tar.gz` on PyPI. Nothing publishes from the default branch or an unmatched tag.

- [ ] **Step 1: Replace publish.yml with the full pipeline**

Overwrite `packages/sdk/.github/workflows/publish.yml`:

```yaml
name: publish

on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      tag:
        description: "Existing tag to publish (must match project.version)"
        required: true
        type: string

permissions:
  contents: read

jobs:
  build:
    name: Build sdist and universal wheel
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
        with:
          # Pin to the release tag / dispatch tag: never build the default branch.
          ref: ${{ github.event.release.tag_name || inputs.tag }}
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"
      - run: uv sync
      - name: Standards self-check
        run: uv run benchweave-sdk sync-standards --check
      - name: Build wheel and sdist
        # hatch_build verifies the vendored standards tree and preview assets
        # against the lock during the build, so a stale tree cannot reach PyPI.
        run: uv build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
          if-no-files-found: error

  smoke:
    name: Installed wheel (${{ matrix.os }})
    needs: build
    runs-on: ${{ matrix.os }}
    timeout-minutes: 15
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, ubuntu-24.04-arm, macos-latest, macos-15-intel]
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"
      - name: Install smoke (wheel outside any checkout)
        run: |
          set -euo pipefail
          uv venv /tmp/sdk-smoke
          uv pip install --python /tmp/sdk-smoke/bin/python dist/*.whl
          /tmp/sdk-smoke/bin/benchweave-sdk --version
          /tmp/sdk-smoke/bin/benchweave-sdk new /tmp/example --with-ui
          /tmp/sdk-smoke/bin/benchweave-sdk check /tmp/example/src/example_plugin/descriptor.json

  publish:
    name: Publish to PyPI (Trusted Publishing)
    needs: smoke
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.release.tag_name || inputs.tag }}
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"
      - name: Tag must match project.version
        run: uv run --no-project python scripts/verify_release_tag.py "${{ github.event.release.tag_name || inputs.tag }}" --pyproject pyproject.toml
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist
      - uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 2: actionlint**

```sh
cd packages/sdk && actionlint .github/workflows/publish.yml
```
Expected: no findings.

- [ ] **Step 3: Commit and push**

```sh
git add .github/workflows/publish.yml
git commit -m "ci(publish): build once, smoke the wheel on 4 os/arch lanes, publish to PyPI via Trusted Publishing"
git push origin main
```

- [ ] **Step 4: Negative dispatch test (proves the guard without publishing)**

```sh
gh workflow run publish --repo madeinoz67/benchweave-sdk -f tag=v0.0.0-does-not-exist && sleep 20 && gh run list --repo madeinoz67/benchweave-sdk --workflow=publish --limit 1
```
Expected: a run appears and **fails at the build job's checkout** (`ref` v0.0.0-does-not-exist not found) — proving dispatch pinning works and no publish path can run for a bogus tag. This run failing red is the pass condition; note the run URL in the task ledger.

---

### Task 4: Docs — Installation section, Five-steps, plugin-sdk.md

**Files:**
- Modify: `packages/sdk/README.md` (new "Installation" section after "Sister repository"; step 1 of "Five steps")
- Modify: `packages/sdk/docs/plugin-sdk.md` (`## 1. Install the SDK and generate your project`)

**Interfaces:**
- Consumes: Task 2's MIT relicense (licence wording) and Task 5's published package (URLs live once released).
- Produces: the documented install channels: stable `pip`/`uv`/`brew`; bleeding-edge `git+`.

- [ ] **Step 1: Add README Installation section**

Insert after the "Sister repository" section in `packages/sdk/README.md`:

```markdown
## Installation

Stable releases are on PyPI:

```sh
pip install benchweave-sdk
# or as an isolated CLI tool
uv tool install benchweave-sdk
# or via Homebrew (macOS and Linux)
brew install madeinoz67/tap/benchweave-sdk
```

For bleeding-edge work before a release, install straight from the default branch:

```sh
pip install git+https://github.com/madeinoz67/benchweave-sdk.git
```

To hack on the SDK itself, clone the repository and `uv sync --extra test`.
```

- [ ] **Step 2: Reword Five-steps step 1**

Replace step 1 (`Install the built SDK wheel in your development environment (`uv pip install path/to/benchweave_sdk-0.1.0-py3-none-any.whl`).`) with:

```markdown
1. Install the SDK from PyPI (`uv pip install benchweave-sdk`, or see [Installation](#installation)).
```

Also update the paragraph after the five steps that says `while unpublished, install the built SDK wheel explicitly before resolving that extra` → `the plugin test extra pins the SDK version from PyPI`.

- [ ] **Step 3: Update plugin-sdk.md section 1**

In `packages/sdk/docs/plugin-sdk.md`, prepend to `## 1. Install the SDK and generate your project` the install commands (mirroring README Installation, minus the Homebrew line, ending with a pointer: "Full channel list: see the README Installation section"), keeping the existing scaffold instructions below.

- [ ] **Step 4: Sweep for stale install instructions**

```sh
grep -rn "uv pip install path/to" . --include='*.md' ; grep -rn "not yet published" . --include='*.md'
```
Expected: zero hits (the wheel-path and unpublished phrasings are gone).

- [ ] **Step 5: Commit and push**

```sh
git add README.md docs/plugin-sdk.md
git commit -m "docs: installation section with PyPI, brew and git channels"
git push origin main
```

---

### Task 5: Release v0.1.0 → PyPI (operator-gated)

**Files:**
- None created; operates on git tags + GitHub UI/API in `packages/sdk`.

**Interfaces:**
- Consumes: Tasks 1–4 pushed to SDK `main`; the principal's one-time PyPI setup.
- Produces: `benchweave-sdk==0.1.0` on PyPI — Task 6 and Task 7 consume it.

**OPERATOR GATE (principal, before the tag):** register the Trusted Publisher at pypi.org → Publishing: project name `benchweave-sdk`, owner `madeinoz67`, repository `benchweave-sdk`, workflow filename `publish.yml`, environment `(none)`. Without this the publish job 403s.

- [ ] **Step 1: Confirm version/tag equality**

```sh
cd packages/sdk && git status --short && grep -n '^version' pyproject.toml
```
Expected: clean tree; `version = "0.1.0"` (first PyPI release ships as 0.1.0).

- [ ] **Step 2: Tag, push tag, create the GitHub Release**

```sh
git tag v0.1.0 && git push origin v0.1.0 && gh release create v0.1.0 --repo madeinoz67/benchweave-sdk --title "benchweave-sdk 0.1.0" --notes "First PyPI release. Install: pip install benchweave-sdk"
```

- [ ] **Step 3: Watch the run go green**

```sh
gh run watch --repo madeinoz67/benchweave-sdk $(gh run list --repo madeinoz67/benchweave-sdk --workflow=publish --limit 1 --json databaseId --jq '.[0].databaseId')
```
Expected: build, all 4 smoke cells, publish — green.

- [ ] **Step 4: Verify the project exists on PyPI**

```sh
curl -fsSL https://pypi.org/pypi/benchweave-sdk/0.1.0/json | jq -r '.info.version, .info.license'
```
Expected: `0.1.0` and MIT.

---

### Task 6: Post-publish clean-env install proof

**Files:**
- None (verification only).

**Interfaces:**
- Consumes: PyPI artifact from Task 5.
- Produces: recorded evidence for the task ledger that a clean environment installs and runs the CLI.

- [ ] **Step 1: Clean tool install + run**

```sh
uv tool install benchweave-sdk==0.1.0 && benchweave-sdk --version && uv tool uninstall benchweave-sdk
```
Expected: prints `0.1.0` (or `benchweave-sdk, version 0.1.0`); exit 0.

- [ ] **Step 2: Confirm the wheel is universal**

```sh
curl -fsSL https://pypi.org/pypi/benchweave-sdk/0.1.0/json | jq -r '.urls[].filename'
```
Expected: exactly `benchweave_sdk-0.1.0-py3-none-any.whl` and `benchweave_sdk-0.1.0.tar.gz`.

---

### Task 7: Homebrew formula (tap repo)

**Files:**
- Create: `/Users/seaton/Documents/src/homebrew-tap/Formula/benchweave-sdk.rb`

**Interfaces:**
- Consumes: PyPI sdist from Task 5.
- Produces: `brew install madeinoz67/tap/benchweave-sdk` working on macOS arm64/Intel and Linuxbrew.

- [ ] **Step 1: Fetch the real sdist URL + sha256**

```sh
curl -fsSL https://pypi.org/pypi/benchweave-sdk/0.1.0/json | jq -r '.urls[] | select(.packagetype=="sdist") | .url, .digests.sha256'
```
Record both values; they fill the `<SDIST_URL>`/`<SDIST_SHA256>` slots below.

- [ ] **Step 2: Write the formula**

Create `Formula/benchweave-sdk.rb` (substitute the two recorded values, keep everything else verbatim):

```ruby
# frozen_string_literal: true

class BenchweaveSdk < Formula
  desc "Offline authoring and conformance tools for BenchWeave OTDP device plugins"
  homepage "https://github.com/madeinoz67/benchweave-sdk"
  url "<SDIST_URL>"
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

- [ ] **Step 3: Install, test, livecheck**

```sh
cd /Users/seaton/Documents/src/homebrew-tap && brew install --build-from-source ./Formula/benchweave-sdk.rb && brew test benchweave-sdk && benchweave-sdk --version && brew livecheck --formula ./Formula/benchweave-sdk.rb
```
Expected: install succeeds (deps resolve from PyPI into the venv), `brew test` passes, `--version` prints 0.1.0, livecheck reports `benchweave-sdk : 0.1.0`.

- [ ] **Step 4: Commit and push the tap**

```sh
git add Formula/benchweave-sdk.rb && git commit -m "benchweave-sdk 0.1.0 (PyPI-sourced venv formula)" && git push
```

---

### Task 8: Main repo — package.yml slim + submodule pointer

**Files:**
- Modify: `.github/workflows/package.yml` (fold standards check into `build`, delete `release-sdk` job and the `release:` trigger)
- Modify: submodule pointer `packages/sdk` → SDK `main` tip after Task 4
- Branch: `sdk-pypi-publish` off `benchweave-ui` `main`

**Interfaces:**
- Consumes: Tasks 1–4 pushed on SDK `main` (pointer target); existing `make check-sdk-standards` (Makefile:19).
- Produces: main repo with no SDK distribution duties; branch ready for review; merge is the principal's call.

- [ ] **Step 1: Branch and advance the pointer**

```sh
cd /Users/seaton/Documents/src/benchweave-ui && git checkout -b sdk-pypi-publish && git submodule update --init --recursive && git -C packages/sdk fetch origin && git -C packages/sdk checkout origin/main && git add packages/sdk
```
Note: after `git add packages/sdk`, do NOT run `submodule update` again — it silently reverts uncommitted pointer advances.

- [ ] **Step 2: Edit package.yml**

In `.github/workflows/package.yml`:

1. Delete the `release:` block from `on:` (leaves `push:`, `pull_request:`, `workflow_dispatch:`).
2. In the `build` job, after the `uv python install 3.13` step and before the build/smoke step, insert:

```yaml
      - name: Standards sync check
        # Gate moved from the deleted release-sdk job: refuse to build while
        # the vendored standards tree is out of sync with the lock.
        run: make check-sdk-standards
```

3. Delete the entire `release-sdk` job (from `release-sdk:` through the final `gh release upload` step).

- [ ] **Step 3: Verify**

```sh
actionlint .github/workflows/package.yml && make check-sdk-standards
```
Expected: actionlint clean; standards check passes against the advanced pointer.

- [ ] **Step 4: Main-repo docs sweep**

```sh
grep -rn "uv pip install path/to\|SDK wheel" README.md docs/ --include='*.md' | grep -v superpowers
```
Any hit that instructs installing the SDK from a wheel path gets the PyPI phrasing (link to the SDK README Installation section rather than duplicating).

- [ ] **Step 5: Commit, push branch, review**

```sh
git add .github/workflows/package.yml packages/sdk && git commit -m "ci(package): gate-only package lane; SDK distribution moves to PyPI" && git push -u origin sdk-pypi-publish
```
Then dispatch the repo's code-reviewer on the branch diff. **Merge to `main` = principal's call** (report the branch and review verdict; do not merge).

---

## Self-Review

- **Spec coverage:** A1 Trusted Publishing (Task 3 + Task 5 gate), universal wheel + 4-way matrix (Tasks 3, 6.2), MIT flip (Task 2), main package.yml slim (Task 8), brew formula B1 (Task 7), docs surfaces incl. Distribution rights rewrite (Tasks 2.3, 4), version guard (Tasks 1, 3), dispatch-tag semantics (Task 3.1 ref pinning + 3.4 negative test), no-dev-release decision (nothing implements one; constraints line records it). Spec's "Verification (first release is the verification event)" = Tasks 5–7. Gap check: none open.
- **Placeholders:** `<SDIST_URL>`/`<SDIST_SHA256>` in Task 7 are deliberate command-filled slots (Step 1 deterministically produces both) — not vague TODOs. No other placeholders.
- **Type consistency:** `verify_release_tag.py` CLI identical in Tasks 1 and 3; artifact name `dist` consistent across upload/download steps; tag expression `github.event.release.tag_name || inputs.tag` identical in all three jobs; formula `license "MIT"` matches Task 2 metadata.
