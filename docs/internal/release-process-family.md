# The family release process

This page is the umbrella for releasing the BenchWeave repository family —
the three release lines, the order they release in, and the standing
rulings that bind all three. It is also the **cut authority for the
gateway line** (the `benchweave` package at this repository's root). The
other two lines keep their own authorities; this page points at them, it
never duplicates them (the single-home rule):

| Line | Repo | Tag scheme | Version source | Authority for the cut procedure |
|---|---|---|---|---|
| ui-html | gateway (`packages/ui-html`) | `ui-html-vX.Y.Z` | `packages/ui-html/pyproject.toml` | `docs/internal/ui-html-release-and-pin.md` |
| SDK | benchweave-sdk | `vX.Y.Z` | the SDK repository's `pyproject.toml` | the SDK repository's `docs/internal/release-review-matrix.md` + its `release-review` skill |
| gateway | gateway (root) | `vX.Y.Z` | root `pyproject.toml` | **this document** |

Design source: the issue #380 design record
(`.claude/deep-review/2026-10-04-issue380-release-process-design.md`),
including its premise correction: the gateway has never had a `v*`
release. The gateway remote has carried exactly the two `ui-html-v*` tags
and nothing else, `benchweave` does not exist on PyPI, and the local
clone's stray `v*` tags are the SDK's release tags leaked during the
repo-split era (the one-time setup below removes them). There was no
gateway release line to formalize — there is a first one to define.

**The family invariant.** A release tag equals `prefix + the line's
version source` — `ui-html-v` + the ui-html version, `v` + the SDK's, `v`
+ the root pyproject's — checked as a plain string compare, no PEP 440
rounding, no normalisation. Machine-checked wherever a publish workflow
exists (the ui-html build job's fail-closed assert; the SDK's
`scripts/verify_release_tag.py` inside its publish job), and row 1 of
every release-time walk everywhere else.

**Where release records live.** No repo-family release-event record class
exists registry-side and none is created — the registry repository's
records tree is plugin publishing-lane records only. Each line's walk
rows, recorded on its tracking issue, are the release record.

## The order rule and gap windows

Releases flow downstream **ui-html → SDK → gateway**.

- **Upstream never waits on a downstream cut.** ui-html may cut regardless
  of both lines below it; the SDK may cut while the gateway pointer lags
  (it has — a trailing downstream is a recorded state, not an anomaly).
  Nothing is locked-step. The cost of the trailing state is the signal,
  not a block.
- **A breaking upstream release opens a gap window** — the time between
  that release and the landing of its downstream pairing (the pairing
  procedures are below). **No downstream cut happens inside that window.**
- **Breaking-for-the-downstream is defined per edge, from the lines' own
  machine classes**, not by fresh judgement at cut time:
  - ui-html → SDK: a ui-html **contract-minor** — any byte motion in
    `docs/internal/ui-contract.md` or the two token assets (the ui-html
    version policy's contract-change definition) — is breaking for the
    SDK.
  - SDK → gateway: an SDK **range-change MINOR+** — the served-set bump
    class (`sdk_bump_class_invalid:`) — is breaking for the gateway.
  - PATCH releases pair on schedule and open no window.
- **Which edge is enforced how — stated honestly, because the two edges
  are not symmetric, and neither machine-blocks today:**
  - **SDK → gateway: a declared pin, enforced in THIS repository's CI,
    held by the merge discipline, not by branch protection.** The
    `sdk-drift` lane compares the committed `packages/sdk` gitlink
    against the DECLARED pin in `.gitmodules` (`pin = vX.Y.Z`, or a
    40-hex SHA while a train declares itself) and is red when the two
    disagree — the pin and the gitlink move in the same commit, so the
    pointer PR carries its own declaration and no window reddens it.
    The freshness signal is an annotation: a pin trailing the latest
    release renders `::warning::` (`pairing pending`) on every run of
    the lane. The lane does not machine-block the merge:
    main's branch protection requires zero status checks (measured —
    the classic protection endpoint 404s; the active ruleset sets
    squash-only and zero approvals with an empty required-checks list,
    and red-lane merges have happened operationally). What refuses to
    merge over red is the standing merge discipline —
    `scripts/merge-verified.sh` reading the full checks rollup, zero
    fail and zero pending asserted, under the merge-on-green orders.
    Procedural, and stated as procedural. The mechanical upgrade —
    adding `sdk-drift` and the core lanes to required status checks —
    is a one-time owner decision, named in the setup section below.
  - **ui-html → SDK is procedural + signal.** The SDK repository's
    `ui-html-pin-freshness` lane (`.github/workflows/pin-freshness.yml`)
    WARNs while the `[server]` extra's exact `benchweave-ui-html` pin
    trails the PyPI index. The WARN is the window's visible edge; closing
    it is the pin-bump pull request. The trailing-pin state itself is
    deliberate per-train pin advance (warn-only until an escalation
    policy exists — issue #294's deferral); this page's gap-window clause
    is the procedural half that says the window is not closed until the
    pin bump lands.

## Immutability and stable-only

**Released versions are immutable.** A defect in a release is fixed by a
NEW release — never a moved tag, never an in-place byte edit. The
in-tree guards hold the byte half: repin's superseded-row freeze and
verify-but-never-rewrite (CON-7), copy-never-move (standards
GOVERNANCE), the version-incrementing-PATCH heal
(`standards_version_required` refusing a same-version re-vendor —
obligation 15's measured shape), and PyPI's own no-reupload. The tag
half is tag protection (below) plus this clause for admin action: an
owner moving a tag remains mechanically possible and is forbidden here —
the honest residual, stated rather than hidden. Yank semantics: a yanked
release is withdrawn from installs but never deleted (PyPI's yank
matches the standards policy block's native shape).

**Stable-only on the index.** No pre-releases. Both PyPI projects' serve
histories are entirely stable releases, pins are exact `==`, and a
pre-release on the index would disorder the freshness lanes, which
compare the pin against the index. Reopen trigger: a genuine
field-testing need — a large breaking change wanting external validation
reopens this ruling; it does not bypass it.

## The downstream pairing procedures

**After a ui-html release** — the SDK pin-bump pull request in the SDK
repository: raise `benchweave-ui-html==X.Y.Z` in the `[server]` extra
(exact pin, never a range); both hosts green — gateway CI at the same
commit (the workspace path dependency moves in the same commit), SDK
standalone CI against the **published** wheel, never a local path
override in CI; the contract census digest rows in the pull request body
until the designed guard lands. This is
`docs/internal/ui-html-release-and-pin.md` steps 5–7 verbatim — that
page is the authority; the only thing this page adds on top is the
gap-window clause above.

**After an SDK release** — the gateway pairing pull request here:
advance the `packages/sdk` gitlink to the release tag, regenerate the
SDK lock, move the `sdk_compatibility` mirror, re-render
`docs/compatibility-matrix.md`, one merge (obligation 7's loop).
`make check-sdk-standards` is the mechanical half; `sdk-drift` exiting
green is the proof the window closed.

**After a gateway release** — nothing. The gateway is the sink: no line
consumes it as a released dependency today (deployed from checkout; a
publish workflow is a named deferral below).

## Tag protection (required family setup)

Tag creation bypasses branch protection entirely — branch rules never
see a pushed tag. At the design read neither repository had any
tag-protection rule (the API returned 404 on both; recorded there). This
is required one-time setup — promoted from the ui-html page's original
optional-hardening stance, which this promotion supersedes:

- **gateway repository:** patterns `v*` and `ui-html-v*`, each
  restricting create/update/delete to admins.
- **SDK repository:** pattern `v*`, same restriction.

Honest limits: on a personal-account repository the owner IS the exempt
role — the protection's real value is against automation mistakes and
leaked credentials, and the tag↔version walk row remains the semantic
gate. If the legacy protection endpoint refuses on a given plan,
rulesets are the fallback; if neither mechanism can express it, the
absence is recorded loudly here and this clause rests on procedure.

## One-time operator setup (out-of-repo)

Nothing in either repository can perform these; naming them is the whole
implementable surface (the pending-publisher precedent):

1. **Tag protection** per the section above. Verification: `gh api
   repos/madeinoz67/benchweave/tags/protection` — and the SDK
   repository's equivalent — returns the configured rules.
2. **Local shadow-tag cleanup** in the maintainer's gateway clone:
   delete the stray `v*` tags there — SDK release tags leaked during the
   repo-split era, reachable from no gateway history. The set is named
   by a mechanism, not a hand list: `git tag -l 'v*'` in that clone
   lists exactly the tags to `git tag -d`; the read-back shows only the
   `ui-html-v*` pair. Until this runs, a `git push --tags` from that
   clone would push SDK tags to the gateway remote, and
   `refuse_if_tagged` would then fire in every docs run — bricking docs
   CI on every open pull request until each remote tag is deleted. The
   loud refusal is the correct machine behavior; this step removes the
   ammunition. Disclosed residual: the deletion is local to that clone —
   another clone could still carry the tags; the remote is clean and a
   stray push is recovered by deleting the remote tag.
3. **PyPI pending publishers** for the two publishing lines already
   exist (both projects are live) — nothing to do; recorded n/a.
4. **Required status checks — NOT configured at this writing; owner's
   call, and this page does not assume it.** Adding `sdk-drift` (and
   the core lanes) to main's required status checks would upgrade the
   SDK→gateway gap window from procedural to machine-enforced — a red
   drift lane would then block the merge outright. Measured at this
   page's landing: the active main ruleset carries squash-only and
   zero approvals and requires ZERO status checks (the classic
   branch-protection endpoint 404s). Until the owner configures
   required checks, the order rule's SDK→gateway edge rests on the
   merge discipline, exactly as its clause says — if this item is
   executed, that clause and the erratum in the design record move
   with it. The required-checks shape is compatible with the declared
   pin's always-run annotation posture (issue #408): the lane exits 0
   with `::warning::` rather than skipping, so a required check never
   sits Pending.

## The gateway line's cut procedure

**Readiness conditions — all three hold before the marker commit:**

1. **The versioned-docs port has landed.** It has: the assembly is now
   two-regime (`scripts/assemble_docs_site.py`) — zero `vX.Y.Z` tags is
   today's unversioned tree, one or more tags is per-tag `docs/v/<tag>/`
   buckets with the latest at the `docs/` root, the `versions:` list and the
   site selector generated from the registered releases. The former
   `refuse_if_tagged` gate is retired: its demand is satisfied by the port.
   What must still land before the first tag is the **pre-tag registration
   ordering constraint** — at every release including the first, the
   `versions:` entry is committed and merged BEFORE the tag is pushed,
   because the tag's own `great-docs.yml` is what its bucket build filters
   (the SDK's v0.0.4 lesson). The assembly mechanizes both halves of that
   constraint (`check_registration`: completeness, tag self-registration,
   inverse, and regime consistency), so a violated ordering refuses the docs
   lane loudly instead of failing at bucket-build time.
2. **The SDK pairing is current** — `sdk-drift` green **and no
   trailing-pin annotation** (green alone no longer proves the window
   closed: the lane greens a trailing pin with `::warning::`, and the
   annotation is the window's visible edge — owner fork F3: the walk
   row reads it, the machine does not). No gateway cut inside an open
   SDK gap window.
3. **The release-time walk below is walked** between the marker commit
   and the tag, rows recorded on the tracking issue — the SDK matrix's
   row discipline, adopted per its skill's own scope note.

**Procedure:**

1. **Version decision** — pre-1.0 baby steps; the family invariant binds
   the number to the version source (tag = `v` + root pyproject
   version). First cut: pyproject as-is, an EMPTY marker commit
   `chore(release): prepare for gateway vX.Y.Z` — the message rides the
   existing cliff skip pattern verbatim, so every release tags a
   prepare-commit and there is no first-release special case to
   misremember. A bump, when wanted, is its own commit first.
2. **Pre-tag registration** — add the release's entries to `great-docs.yml`'s
   `versions:` list and merge them BEFORE the tag is pushed. The
   registration is TWO entries, not one: the release entry
   (`- tag: vX.Y.Z` / `label:` / `latest: true` / `git_ref: vX.Y.Z`) AND the
   `dev` entry (`- tag: dev` / `label: dev` / `prerelease: true`) — the
   parent assembly's `--versions dev` build filters against this same list,
   and a block without the dev entry fails it with
   `Multi-version build: 0 version(s)`. The tag's own `great-docs.yml` is
   what its bucket build filters against, so a registration that lands
   after the tag is cut produces a zero-version build (the SDK's v0.0.4
   lesson). The assembly enforces every direction (`check_registration`):
   a tag with no registration refuses naming the tag; a tag whose own yml
   does not list itself as `latest: true` refuses naming the tag-self rule;
   a block without the dev entry refuses; two `latest: true` entries (or a
   latest naming an older release) refuse. This step is why the marker
   commit below stays empty — the registration is its own commit.
3. **Changelog boundary dry run** — in a disposable clone: the anchored
   config plus a scratch tag at the marker commit; inspect the full
   render. Never run in the real repository. The first main-reachable
   `v*` tag becomes `CHANGELOG.md`'s first release boundary
   (`cliff.toml`'s `tag_pattern` is anchored; the long Unreleased
   section collapses into that release section at the next
   regeneration) — the dry run is how the boundary is chosen, not
   discovered.
4. **Gates** — the marker commit merges green (full battery). It rides
   main directly per the release-flow exception — the no-direct-commits
   directive targets work commits; process uniformity beats a per-line
   special case (the issue #302 risk disclosure, adopted for this line).
5. **Tag + GitHub release** — tag on the marker commit; release object
   with cliff-generated notes pasted as the body (the gateway has no
   workflow to replace the body — the paste IS the notes). The gateway
   commands — a FULL-repository render, matching the changelog boundary
   the dry run inspected; the ui-html page's pinned commands carry
   `--include-path 'packages/ui-html/*'` and would render ui-html-only
   notes, wrong in direction for this line:

   - first release:
     `git-cliff -c cliff.toml --strip header --unreleased --tag vX.Y.Z`
   - later releases:
     `git-cliff -c cliff.toml --strip header --tag vX.Y.Z v<PREV>..v<NEW>`

   Both forms require the anchored `tag_pattern` in `cliff.toml`, for
   the same reason the ui-html page's commands do — and a `vX.Y.Z` tag
   MATCHES the anchored pattern, so the render's section becomes the
   changelog boundary at the next regeneration (walk row 4).
6. **Post-verify** — the walk's rows below. The changelog boundary
   renders at the next `changelog.yml` run on main (tags do not trigger
   it — the boundary's arrival is named, not assumed).

**The gateway release-time walk.** Every row records a result — updated
/ correct-as-is / n-a; an empty window is a recorded result, not a
skipped step.

| # | Surface | Machine truth | Stale pattern |
|---|---|---|---|
| 1 | tag `vX.Y.Z` vs root `pyproject.toml` version | pyproject (single source) | tag ≠ `v` + version |
| 2 | the GitHub release body | the pinned cliff command's output at the tag | hand-written notes; non-gateway commits included |
| 3 | the docs site | the versioned assembly's bucket + selector; `check_registration`'s four arms | version absent from the selector; registration missing pre-tag (the assembly refuses it); a `versions:` entry naming no real tag |
| 4 | the changelog boundary | `CHANGELOG.md` after the next regeneration (or the dry-run paste) | Unreleased still carrying post-tag commits; boundary at the wrong tag |
| 5 | contributor window | `git log <range> --format='%an'` minus bots + owner | unacknowledged new human contributor; empty = recorded result |
| 6 | the SDK pairing | `sdk-drift` green AND no trailing-pin annotation on the lane; the compatibility matrix render | cut made over a red gitlink; a cut shipped over a trailing pin whose warning went unread |
| 7 | ui-html workspace member | same-commit motion (path dependency) | (recorded n/a — the row exists so the walk never wonders) |

## The family check (cross-line rows, every cut, whichever line)

Two rows only — the per-line walks stay in their homes:

- **Gap check** — is any upstream gap window open for the line being cut?
  (ui-html cut: never — it is the source; SDK cut: the ui-html pin
  window; gateway cut: both.)
- **Pairing-pending check** — does a downstream pairing from a prior
  upstream release remain unlanded? Recorded and scheduled — it does not
  block an upstream cut; it is the window's bookkeeping.

## Named deferrals

- **A gateway publish workflow** — deferred. The gateway is not on PyPI
  and deploys from checkout; `package.yml` is build-proof only
  (`permissions: contents: read`, no publish machinery), and every job in
  `publish-ui-html.yml` is guarded
  `startsWith(github.event.release.tag_name, 'ui-html-v')`, so a gateway
  release today publishes nothing and fires nothing. Trigger: the first
  consumer that installs the gateway package from an index.
- The rest of the deferral ledger — the SDK-side family registration, the
  ui-html `workflow_dispatch` arm and environment binding, the
  pin-freshness escalation policy, the ui-html contract census guard —
  lives in the design record's deferral section, each entry with its
  home and its reopen trigger.
