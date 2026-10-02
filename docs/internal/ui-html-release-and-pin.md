# ui-html release and pin process

This page is the authoritative process for releasing the `benchweave-ui-html`
package (`packages/ui-html/`) and for pinning it as a standalone distribution
dependency elsewhere. It lives in this repository — beside the package, the tag
machinery and the contract it releases. The SDK repository gets a one-paragraph
pointer in its standalone distribution docs when the consuming slice creates
the manifest row for the wheel; that cross-link lands there, not here (nothing
in the SDK references the wheel today).

Design sources: the issue #302 REL pipeline record
(`.claude/deep-review/2026-10-01-issue302-rel-pipeline-design.md`) and the
first-release record
(`.claude/deep-review/2026-10-02-issue302-first-release-design.md`). The
pipeline is landed: the package job proves the wheel standalone (including
the resource census), `cliff.toml`'s tag pattern is anchored, and
`.github/workflows/publish-ui-html.yml` publishes on release published. What
remains is the first release itself — the release-time arms (pending
publisher, marker commit, tag + release, the workflow run, the pinnable
proof) are walked below; none of them needs further repo machinery.

## Version policy

**Single source.** `packages/ui-html/pyproject.toml` `[project].version` is the
only version declaration. There is no `__version__` attribute today; if one is
ever added, a test pins it to `importlib.metadata` (the SDK precedent is
`scripts/sdk_smoke.py`'s installed check). The package job enforces the rule at
the artifact: the installed version must equal the pyproject version.

**Bump semantics (pre-1.0).**

- A **contract change** bumps the **minor** position (`0.x.0`).
- An **implementation change** bumps the **patch** position (`0.1.x`).

Why minor-for-contract: this repository already treats tightening as the
breaking class and bumps MINOR for it (the issue #64 ruling); the UI NFR wants
the version to carry "the contract moved", and reserving the minor position
for exactly that makes a pin bump decidable from the version alone.

**Contract change defined:** ANY byte motion in `docs/internal/ui-contract.md`,
or in the token assets the contract's pins assert against
(the package's vendored `assets/tokens.css` and `assets/themes.css` —
re-pointed from `ui/src/styles/` at G1e, per this page's own pre-committed
re-point note), is a contract
change. This is flat by design: the harness fail-closes on heading/table
structure, so "this prose edit changed nothing the harness sees" is expensive
to prove and cheap to skip. Accepted cost: prose-only contract edits burn a
minor bump — noise-level pre-1.0, revisit at 1.0.

**Implementation change:** everything else in the package (partial internals,
harness mechanics, fixtures) with those two surfaces byte-identical.

**Who pins what.** The gateway never pins a released version of its own
workspace member — it is a workspace path dependency and moves in the same
commit by construction. A standalone distribution that consumes the wheel pins
**exact** versions (`==`), never ranges: a range would let a contract change
reach standalone consumers without the pin-bump pull request, which is exactly
what the standalone-distribution requirement forbids (a package release and a
pin bump in the SDK repository, never a copied template).

## Tag, changelog and commit conventions

- **Tag scheme:** `ui-html-vX.Y.Z` for this package; gateway tags stay
  `v[0-9].*`. `cliff.toml`'s `tag_pattern` is **anchored** (`^v[0-9].*`,
  first-release slice): unanchored, the first `ui-html-v*` tag matched the
  pattern as a substring and became the gateway changelog's newest release
  boundary — swallowing the whole Unreleased section (measured; the dry
  run's RED arm). With the anchor, a `ui-html-v*` tag — lightweight or
  annotated, marker commit in history or not — leaves the full render
  byte-identical (OPEN-2 resolved; re-proven at the slice).
- Work commits ride the gateway changelog as today; scope them
  `feat(ui-html)` / `fix(ui-html)` so release-notes selection is trivial.
- At release time, the version-bump commit is named
  `chore(release): prepare for ui-html vX.Y.Z` — riding the **existing**
  git-cliff skip pattern verbatim; no `cliff.toml` edit. Release notes for the
  ui-html tag are cliff-generated at release time. There is **no second
  committed changelog file** for this package (owner fork, adopted).

## The release-and-pin steps

1. **Change lands in this repository** — conventional commit; `ui-html` scope
   where relevant.
2. **Version decision** per the policy above: minor if and only if the contract
   surface moved (the single list defined above: `docs/internal/ui-contract.md`
   plus the two token assets).
3. **Bump** `packages/ui-html/pyproject.toml`, run `uv lock`, commit as
   `chore(release): prepare for ui-html vX.Y.Z`. **At an unchanged version —
   the first release — the commit is an EMPTY marker commit**
   (`git commit --allow-empty`): `uv lock` is a no-op at an unchanged
   version (`uv lock --check` exits 0 — the runner re-runs it and pastes it),
   the message already rides the cliff skip pattern verbatim so it renders
   nowhere, and every release tags a prepare-commit — no "the first release
   is special" branch to misremember. The anchored tag pattern keeps the
   changelog regeneration at the marker push byte-identical (proven through
   the release-day composite render: anchored config + annotated tag + the
   marker commit in history), so `changelog.yml` produces no bot commit.
4. **Tag** `ui-html-vX.Y.Z` on the bump commit; GitHub release with
   cliff-generated notes — the pinned commands (paste the command's output
   as the release body; run at the tagged commit):

   - first release:
     `git-cliff -c cliff.toml --strip header --unreleased --tag ui-html-vX.Y.Z --include-path 'packages/ui-html/*'`
   - later releases:
     `git-cliff -c cliff.toml --strip header --tag ui-html-vX.Y.Z --include-path 'packages/ui-html/*' ui-html-v<PREV>..ui-html-v<NEW>`
     (the range form is dry-run-proven; re-verify at the second release)

   The publish workflow fires on release published (the publish path,
   below); its verify job reads PyPI back and asserts BOTH the wheel and the
   sdist serve the exact built bytes. The release-time walk below is the
   human half.
5. **Pin-bump pull request in the SDK repository:** raise
   `benchweave-ui-html==X.Y.Z` in the standalone distribution manifest (exact
   pin). Never a copied template.
6. **Both hosts green:** gateway CI (workspace path — the same commit), and
   SDK standalone CI against the **published** wheel — never a local path
   override in CI.
7. **Guard (designed; lands with the consuming slice):** the SDK repository
   vendors the contract census — table count, row count, and the sha256 digest
   of every file in the contract-surface list at the pinned release's tag — and
   standalone CI runs the pinned wheel's own harness against that vendored
   copy. The guard's file set derives from the SAME single-constant list as the
   contract-change definition above — one list, three paths
   (`docs/internal/ui-contract.md`, the package's vendored
   `assets/tokens.css`, `assets/themes.css`) — so the definition and the census cannot
   diverge. Interim, until the guard lands: the pin-bump pull request body
   records the sha256 digest of each file in that list at the release tag (one
   command per path — `git show ui-html-vX.Y.Z:<path> | shasum -a 256` —
   checkable by any reviewer).

The census guard (step 7) is the mechanically checkable core of "both hosts
move together": the same contract bytes enforced by both hosts, or the pin
pull request cannot go green.

**Disclosed residual, until the guard lands:** nothing yet FORCES a minor bump
when `ui-contract.md` moves — the harness forces the partials to move with it,
but not the version. The release-time walk in steps 2–3 is the check; the guard
mechanizes it later. Procedural and disclosed, not hidden.

## The publish path (landed)

`.github/workflows/publish-ui-html.yml` in THIS repository, release-triggered
only. Four jobs, every one guarded by
`if: startsWith(github.event.release.tag_name, 'ui-html-v')` — the guard is
the tag-namespace element because a `tags:` filter is not a valid construct
under the `release` event (actionlint refuses it), and without the guard a
gateway `v*` release would fire a ui-html publish:

- **build** — checkout pinned to the release tag (never the default branch),
  tag-matches-pyproject assert (fails closed on any divergence), `uv build`
  of the member, artifact upload refusing an empty dist.
- **smoke** (ubuntu + macos) — fresh venv outside any checkout, the
  installed-wheel asserts and the resource census, re-proven at the tag.
- **publish** — PyPI trusted publishing via OIDC: the repository's ONLY
  `id-token: write`, job-scoped to this one job; no token secret anywhere.
- **verify** — PyPI JSON read-back asserting the version serves BOTH the
  wheel and the sdist with digests equal to the built artifacts' (a short
  retry loop absorbs index lag; a found-but-mismatched digest stops the
  line — by the digest argument it can only be real, never a false alarm).

Runs are serialized (`concurrency: publish-ui-html`, no cancel). v1 has no
`workflow_dispatch` arm — the missed-event recovery is re-publishing the
release object; the first missed/dropped release event is the named trigger
to add it (a small diff mirroring the SDK's input shape).

One-time operator setup (out-of-repo, below) configures the pending
publisher; the first publish auto-creates the PyPI project.

## The release-time walk (ui-html)

Every row records a result — updated / correct-as-is / n-a; an empty window
is a recorded result, not a skipped step.

| # | Surface | Machine truth | Stale pattern |
|---|---|---|---|
| 1 | tag `ui-html-vX.Y.Z` vs `packages/ui-html/pyproject.toml` `[project].version` | pyproject (single source) | tag ≠ `ui-html-v` + version (also refused by the workflow's build-job assert) |
| 2 | the GitHub release body | the pinned cliff command's output (step 4) | hand-written notes, or notes including non-`packages/ui-html` commits |
| 3 | PyPI project page | the verify job's read-back | version absent, files missing, digest ≠ built artifact |
| 4 | the publish workflow run | the run's own conclusion | any red/skipped job between release-published and verify |
| 5 | contributor window (the notes range) | `git log <range> --format='%an'` minus bots + owner | unacknowledged new human contributor; empty window = recorded result |
| 6 | gateway `uv.lock` | n/a — workspace member, same-commit motion | (recorded n-a, so the walk never wonders) |

The version-bearing surfaces are all in THIS repository, the tag, the GitHub
release, and PyPI — none in the SDK repository (nothing there references the
wheel). The SDK repository's pointer paragraph rides the PRD 11 consuming
slice, as already planned.

## One-time operator setup (out-of-repo)

On pypi.org → account settings → Publishing → **add a pending publisher**:
project `benchweave-ui-html`, owner `madeinoz67`, repository `benchweave`,
workflow filename `publish-ui-html.yml`, environment name **blank** (v1; a
GitHub-environment binding is named deferred hardening — the trigger to add
it is a second maintainer with write access or an owner ruling), default
branch `main`. The first publish auto-creates the project. Nothing in the
repository can do this; these settings are the whole implementable surface.

Optional hardening (not required for v1): a GitHub tag-protection rule for
`ui-html-v*`.
