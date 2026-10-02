# ui-html release and pin process

This page is the authoritative process for releasing the `benchweave-ui-html`
package (`packages/ui-html/`) and for pinning it as a standalone distribution
dependency elsewhere. It lives in this repository — beside the package, the tag
machinery and the contract it releases. The SDK repository gets a one-paragraph
pointer in its standalone distribution docs when the consuming slice creates
the manifest row for the wheel; that cross-link lands there, not here (nothing
in the SDK references the wheel today).

Design source: the issue #302 REL design record
(`.claude/deep-review/2026-10-01-issue302-rel-pipeline-design.md`). The CI half
of the pipeline — the package job proving the wheel standalone — is landed;
everything release-shaped below is **not landed yet**: the first release is
gated on G1e (issue #301), and this page is the written process it will follow.

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
  `v[0-9].*`. `cliff.toml`'s existing `tag_pattern` is expected to keep
  `ui-html-v*` out of the gateway changelog — verify with a dry run before the
  first tag exists (design record OPEN-2, at G1e).
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
   `chore(release): prepare for ui-html vX.Y.Z`.
4. **Tag** `ui-html-vX.Y.Z` on the bump commit; GitHub release with
   cliff-generated notes (the exact cliff command that generates them is
   pinned at G1e, riding the OPEN-2 tag-isolation dry run); the publish
   workflow fires on release published; verify PyPI by direct read.
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

## The publish path (designed; lands at G1e)

A new `.github/workflows/publish-ui-html.yml` in THIS repository, when the
first release happens: triggered on release published, filtered to
`refs/tags/ui-html-v*`; `id-token: write` for PyPI trusted publishing (no token
secret stored in the repository); build the member wheel, `uv publish`, then
verify by direct PyPI read. Version bumps trigger the release-review matrix
walk (standing rule); ui-html adds version-bearing surfaces, and the matrix
rows for it land with G1e in whichever surfaces carry the version.
