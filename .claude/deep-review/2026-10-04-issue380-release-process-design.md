# Issue #380 — a formal release process for the three-line repo family — design record

**Status:** DESIGN COMPLETE · **Slice:** the family process document + the cheap high-value guards (tag protection, local shadow-tag cleanup, one refusal pin) · **Owner doctrine (adopted input):** releases flow downstream ui-html → SDK → gateway; upstream never waits on a downstream cut; no locked-step; a breaking upstream release schedules downstream pairing work and no downstream cut happens inside that gap.
**Base read:** origin/main at `308ce13` (worktree `.wt/relproc-design-9217/`, branch `docs/release-process-family`), 2026-10-04.

**Verdict: BUILD** — with one premise correction that reshapes the gateway half of the work (§0), and the automation legs deferred (§4).

---

## 0. Premise correction — verified, with the evidence

The task framing ("gateway v* line: hand-cut tags to v0.3.1, NO GH release objects on v*") is **wrong about what those tags are**. Measured 2026-10-04:

- The gateway **remote carries zero `v*` tags**. `git ls-remote --tags origin` returns exactly `ui-html-v0.1.0` and `ui-html-v0.2.0` (annotated, `^{}` entries present). The eight local `v*` tags (`v0.0.1`…`v0.3.1`) exist only in the maintainer's clone.
- Those eight tags are **the SDK's release tags**, leaked into the local gateway checkout during the repo-split era: the gateway's `v0.2.0` and `benchweave-sdk`'s own `v0.2.0` point at the **same SHA** (`9910173`, `docs(website): selector claims v0.2.0 (latest) — the tag commit` — an SDK-repo commit, SDK-main-reachable, NOT gateway-main-reachable); the tag messages describe benchweave-sdk releases ("benchweave-sdk v0.2.0 — transport-provider conformance…"); the two repos' `main` branches have **no merge-base** (disjoint histories — the tag objects hang off nothing in gateway history); and PyPI serves `benchweave-sdk` at exactly `0.0.1…0.3.1, 0.4.1, 0.6.0` while **`benchweave` does not exist on PyPI at all** (404).
- The gateway root `pyproject.toml` `[project].version` is **0.1.0** — never moved by any tag; no tag was ever coupled to it.

Consequences the design carries:

1. **There is no gateway `v*` release line to formalize — there is a first one to define.** The gateway remote's tag namespace is clean; the first gateway release will be the first `vX.Y.Z` tag that remote has ever carried.
2. **"v0.3.2" is the wrong first number.** Tag-equals-pyproject-version is the machine-checked family invariant (the ui-html build job's fail-closed assert; the SDK's `scripts/verify_release_tag.py` in `publish.yml`), and `0.0.x–0.3.x` are the SDK product's numbers on PyPI. Continuing them on the gateway would assert a lineage the gateway does not have and invite permanent confusion between two products' release series. **Recommendation: the first gateway release is `v0.1.0`** — pyproject as-is, cut exactly like ui-html's first release (empty marker commit; that record's fork (c) precedent), no version-bump commit needed. Owner fork F1 (§10) can strike this for any other number; the procedure is number-agnostic.
3. **The eight local shadow tags are a live footgun.** A `git push --tags` from the maintainer's clone would push eight SDK tags to the gateway remote; `refuse_if_tagged` (`scripts/assemble_docs_site.py:418`) would then fire in every docs run and **brick docs CI on every open PR** until each remote tag is deleted. The loud refusal is the correct machine behavior — the cleanup (§2.6) removes the ammunition.

What the gateway first cut genuinely requires (all verified in-tree):

- **The versioned-docs port.** `refuse_if_tagged` refuses assembly once any `vX.Y.Z` tag exists — "port the SDK's per-tag snapshot assembly before publishing a released gateway's docs" (`scripts/assemble_docs_site.py:24`, `great-docs.yml:11`). CI checks out with `fetch-depth: 0` (tags included; `.github/workflows/docs.yml:37`), so the very push of the first gateway tag turns docs.yml red until the port lands. The port (per-tag `v/<tag>/` buckets, a `versions:` list, the static-site selector, the pre-tag registration ordering constraint the SDK learned the hard way — its matrix's "ordering constraint" section) is **named engineering work, deferred with its own home** (§4 D1); the process doc's gateway-line readiness gate names it as a hard prerequisite so the cut cannot be attempted blind.
- **The changelog boundary.** `cliff.toml`'s `tag_pattern` is anchored `^v[0-9].*` (the issue-#302 anchor). The first main-reachable `v*` tag becomes the gateway changelog's first release boundary: at the next `changelog.yml` regeneration, the long `## [Unreleased]` section collapses into the release section. The process doc names the effect and pins a pre-tag dry run (the issue-#302 P3 pattern: anchored config + scratch tag in a disposable clone, full render inspected) so the boundary is chosen, not discovered.

---

## 1. Verified inventory — what exists per line, and the gaps

Evidence read 2026-10-04 at `308ce13` (gateway) and SDK main `e762676` / tag `v0.6.0`.

### The ui-html line (package `benchweave-ui-html`, gateway repo, tag scheme `ui-html-vX.Y.Z`) — FORMAL

| Capability | State | Evidence |
|---|---|---|
| Publish pipeline | **Exists** — release-published trigger, 4 jobs (build/smoke×2/publish/verify), all guarded `startsWith(tag,'ui-html-v')` | `.github/workflows/publish-ui-html.yml` |
| Tag↔version coupling | Machine-checked, fail-closed string compare | build job assert, same file |
| Post-verify | PyPI JSON read-back, wheel AND sdist digest equality | verify job, same file |
| Version policy + walk + runbook | **The authority doc** — version policy, bump semantics, marker commit, pinned cliff commands, 6-row release-time walk, operator PyPI setup | `docs/internal/ui-html-release-and-pin.md` |
| Proven live | Two releases cut under it (0.1.0, 0.2.0), second-release re-verify done | `gh release list` |
| Gaps | `workflow_dispatch` arm (deferred, named trigger); environment binding (deferred); tag protection treated as "optional hardening" (§2.5 promotes it) | issue #302 record §3 |

### The SDK line (package `benchweave-sdk`, own repo, tag scheme `vX.Y.Z`) — FORMAL, cut is hand-driven by design

| Capability | State | Evidence |
|---|---|---|
| Publish pipeline | **Exists** — release-published **plus a `workflow_dispatch` tag arm**; build (standards self-check, hatch build-time verification) → 5-OS smoke → publish (tag-match verify) → tap (homebrew, continue-on-error) → changelog (cliff notes replace the release body; CHANGELOG.md commit) | `benchweave-sdk/.github/workflows/publish.yml` |
| Pre-tag walk | **The authority** — 9-row matrix + per-release result records, walked between "code merged" and "tag pushed"; ordering constraint (registration precedes the tag) | `benchweave-sdk/docs/internal/release-review-matrix.md` |
| Skill | `release-review` walks the matrix; "the gateway can adopt this skill/matrix pair when its own releases need the same gate" (its own Scope section names this gap) | `benchweave-sdk/.claude/skills/release-review/SKILL.md` |
| Downstream-freshness signal | The gateway-side `sdk-drift` lane (gitlink vs the SDK's latest release tag; red until paired) + `ui-html-pin-freshness` lane in the SDK repo (pin vs PyPI index; WARN when trailing) | gateway CI map; `pin-freshness.yml` |
| Gaps | **No tag protection** (`gh api …/tags/protection` → 404, 2026-10-04); no written version-selection policy (implicit in the matrix's row 9 + commits); no family-doc registration (its process lives only in its own repo) | measured; §4 D3 |

### The gateway line (package `benchweave`, this repo, tag scheme `vX.Y.Z`) — DOES NOT EXIST YET

| Capability | State | Evidence |
|---|---|---|
| Any release ever | **None.** No `v*` tag on the remote, no GH release object, no PyPI project | `git ls-remote --tags origin`; `gh release list`; PyPI 404 |
| Publish workflow | **None, deliberately** — `package.yml` is build-proof only (`permissions: contents: read`), and `publish-ui-html.yml`'s job guard skips everything for non-`ui-html-v` releases ("a gateway `v*` release fires this workflow but skips all four jobs") | `.github/workflows/package.yml`; publish workflow header comment |
| Docs-site versioning | **Designed-for but not built** — assembly is "unversioned by design until the first `vX.Y.Z` release tag", and `refuse_if_tagged` refuses to run once one exists; `changelog:` page disabled ("reads GitHub Releases only; the gateway has none yet") | `scripts/assemble_docs_site.py:418`; `great-docs.yml` |
| Changelog | `changelog.yml` regenerates on main pushes; the anchored tag pattern means the first reachable `v*` tag becomes the first release boundary | `cliff.toml`; `.github/workflows/changelog.yml` |
| Version source | Root `pyproject.toml` `version = "0.1.0"`, static, no consumer asserts it | `pyproject.toml` |
| Tag protection | **None** (404) | measured |

### Cross-line facts the process must encode

- **The SDK's `[server]` extra still pins `benchweave-ui-html==0.1.0` while 0.2.0 is live on PyPI** — measured 2026-10-04. This is the current live instance of the downstream-pairing gap: deliberate per-train pin advance (warn-only until an escalation policy exists — issue #294 deferral D-3), and exactly the state the family order rule must name rather than pretend is impossible.
- **`sdk-drift` goes red between an SDK release tag and the gateway pointer bump** — "every open PR is unmergeable" (accepted cost, issue #347). The SDK→gateway gap window is therefore **machine-enforced**; the ui-html→SDK window is **procedural with a WARN signal**. The doc states which is which — an order rule that implies symmetry where none exists would be prose lying about machine state.
- **Registry:** the registry repo (`benchweave-registry`) carries plugin publishing-lane records only (`records/` = submissions/lifecycle/releases per plugin namespace; REG-5). **No repo-family release-event record class exists there** — the family process has nothing to reference registry-side, and creates nothing there. Verified by walking `records/` and the drift doc's obligation 27.

---

## 2. The mechanism — the process document skeleton

One new file, `docs/internal/release-process-family.md`, is the family umbrella and the **gateway line's authority**. The ui-html and SDK lines keep their existing authorities (the doc points, never duplicates — the single-home rule). Skeleton below; the builder renders it in the repo's engineering register (internal record — ASD-STE100 does not apply; no operator/user-facing published text moves in this slice).

### 2.1 The three release lines (opening section)

Repo map, tag schemes, and the per-line authority table:

| Line | Repo | Tag scheme | Version source | Authority for the cut procedure |
|---|---|---|---|---|
| ui-html | gateway (`packages/ui-html`) | `ui-html-vX.Y.Z` | `packages/ui-html/pyproject.toml` | `docs/internal/ui-html-release-and-pin.md` |
| SDK | benchweave-sdk | `vX.Y.Z` | SDK `pyproject.toml` | `benchweave-sdk/docs/internal/release-review-matrix.md` + its `release-review` skill |
| gateway | gateway (root) | `vX.Y.Z` | root `pyproject.toml` | **this document** |

Plus the family invariant every line already machine-checks where a publish workflow exists, and the walk checks everywhere: **a release tag equals `prefix + the line's version source`** (fail-closed compare, no PEP 440 rounding — publish-ui-html build assert; SDK `verify_release_tag.py`).

### 2.2 The order rule and gap windows

- Releases flow downstream **ui-html → SDK → gateway**. Upstream never waits on a downstream cut; nothing is locked-step.
- **A breaking upstream release opens a gap window** — the time between the upstream release and the landing of its downstream pairing (§2.4). No downstream cut happens inside that window.
- Breaking-for-the-downstream, defined per edge (from the lines' own machine classes, not a new judgment): a ui-html **contract-minor** (its version policy: any byte motion in `ui-contract.md` or the two token assets) is breaking for the SDK; an SDK **range-change MINOR+** (the served-set bump class, `sdk_bump_class_invalid:`) is breaking for the gateway. PATCH releases pair on schedule but open no window.
- Which edge is machine-enforced, stated honestly: **SDK → gateway is mechanical** (the `sdk-drift` lane is red until the pointer pairs — no gateway cut can merge inside the window even if the process is skipped); **ui-html → SDK is procedural + signal** (the SDK's `ui-html-pin-freshness` lane WARNs weekly while the exact pin trails the index — the WARN is the window's visible edge; closing it is the pin-bump PR).
- Upstream cuts are never blocked by a trailing downstream: the SDK may cut while the gateway pointer lags (it has — its own docs note the lag), ui-html may cut regardless of both. The cost of the trailing state is the signal, not a block.

### 2.3 Immutability and stable-only (the two standing rulings)

- **Released versions are immutable.** A defect in a release is fixed by a NEW release; never a moved tag, never an in-place byte edit. The in-tree guards that hold the byte half: repin's superseded-row freeze and verify-but-never-rewrite (CON-7), copy-never-move (standards GOVERNANCE), the version-incrementing-PATCH heal (`standards_version_required` refusing same-version re-vendor — obligation 15's measured shape), PyPI's own no-reupload. The tag half is tag protection (non-admin writes) + this clause for admin action (an owner moving a tag remains possible and is simply forbidden here — the honest residual, stated in the doc). Yank semantics: yanked ≠ deleted (the standards policy block's native shape; PyPI yank matches).
- **Stable-only releases on the index.** No pre-releases: both PyPI projects' histories are 100% stable (measured — every served version of both packages), pins are exact `==`, and a pre-release on the index would disorder the freshness lanes (which compare the pin against the index). Reopen trigger: a genuine field-testing need (a large breaking change wanting external validation) — that reopens this ruling, not bypasses it.

### 2.4 The downstream pairing procedures (after an upstream release)

- **After a ui-html release:** the SDK pin-bump PR — `benchweave-ui-html==X.Y.Z` in the `[server]` extra (exact pin, never a range); both hosts green (the SDK against the **published** wheel, never a local path override in CI); the contract census digest row in the PR body until the designed guard lands. This is ui-html-release-and-pin.md steps 5–7 verbatim — the family doc cites it, adds only the gap-window clause above.
- **After an SDK release:** the gateway pairing PR — the PR #189/#154 shape: advance the `packages/sdk` gitlink to the release tag, regenerate the SDK lock, move the `sdk_compatibility` mirror, re-render `docs/compatibility-matrix.md`, one merge (obligation 7). `make check-sdk-standards` is the mechanical half; `sdk-drift` exiting green is the proof the window closed.
- **After a gateway release:** nothing — the gateway is the sink.

### 2.5 Tag protection (promoted from "optional hardening" to required family setup)

Tag creation bypasses branch protection entirely — the gap the owner named. Measured 2026-10-04: **no tag-protection rules exist on either repo** (the API 404s; recorded as the finding). The doc's one-time operator setup (§2.6) configures, on the gateway repo: patterns `v*` and `ui-html-v*`; on the SDK repo: pattern `v*` — each restricting create/update/delete to admins (on a personal-account repo: the owner). Honest limits, stated in the doc: it does not stop the admin (the owner) — the tag↔version walk rows remain the semantic gate; and the legacy protection API's availability on a given plan is itself verified by the read-back, with rulesets as the fallback if the endpoint refuses (degrade loudly: if neither works, the doc says so and the clause rests on procedure).

### 2.6 One-time operator setup (out-of-repo, named exactly)

1. Tag protection per §2.5; verification = `gh api repos/<owner>/<repo>/tags/protection` returning the rules (the 2026-10-04 404s are the recorded "before").
2. **Local shadow-tag cleanup** (the maintainer's gateway clone): delete the eight SDK-shadow `v*` tags locally so the namespace is unambiguous and no `--tags` push can leak them — `git tag -d v0.0.1 … v0.3.1` (the exact list; read-back `git tag -l` shows only the `ui-html-v*` pair). Disclosed residual: another clone could still carry them; the remote is clean (verified), a stray push would brick docs CI loudly (`refuse_if_tagged`), and deleting a remote tag is the recovery.
3. The PyPI pending-publisher entries for the two publishing lines already exist (both projects are live) — nothing to do; recorded as n/a.

### 2.7 The gateway line's cut procedure (this doc's real new content)

**Readiness conditions (all must hold before the bump/marker commit):**

1. The **versioned-docs port has landed** (`refuse_if_tagged` answered — the assembly serves `v/<tag>/` buckets, the selector, the `versions:` registration; the port's own issue is the prerequisite's home, §4 D1). Until it lands, the gateway line has no cut — this clause is what makes the loud refusal a planned gate instead of an incident.
2. **The SDK pairing is current** — `sdk-drift` green (the gitlink at-or-after the SDK's latest release tag). No gateway cut inside an open SDK gap window.
3. The **release-review walk** (below) is walked between the marker commit and the tag, rows recorded on the tracking issue — the SDK matrix's discipline, adopted per its skill's own Scope note.

**Procedure:**

1. **Version decision** — pre-1.0 baby steps; the family invariant binds the number to the version source (tag = `v` + root pyproject version). First cut: pyproject as-is, **empty marker commit** `chore(release): prepare for gateway vX.Y.Z` (the issue-#302 fork-(c) shape: the message rides the existing cliff skip pattern verbatim; every release tags a prepare-commit; no first-release special case). A bump, when wanted, is its own commit first.
2. **Changelog boundary dry run** — in a disposable clone: anchored config + a scratch tag at the marker commit; inspect the full render (the boundary you are about to create). Never run in the real repo.
3. **Gates** — the marker commit merges green (full battery; it rides main directly per the release-flow exception, the issue-#302 risk-5 disclosure — the owner may strike fork F3 for tag-the-tip).
4. **Tag + GH release** — tag on the marker commit; release object with cliff-generated notes pasted as the body (the pinned command shape from the ui-html doc; the gateway has no workflow to replace the body — the paste IS the notes).
5. **Post-verify** — the walk's rows below; the changelog boundary renders at the next `changelog.yml` run on main (tags do not trigger it — the boundary's arrival is named, not assumed).

**The gateway release-time walk** (row discipline as the SDK matrix: every row records updated / correct-as-is / n-a):

| # | Surface | Machine truth | Stale pattern |
|---|---|---|---|
| 1 | tag `vX.Y.Z` vs root `pyproject.toml` version | pyproject (single source) | tag ≠ `v` + version |
| 2 | the GitHub release body | the pinned cliff command's output at the tag | hand-written notes; non-gateway commits included |
| 3 | the docs site | the versioned assembly's bucket + selector (post-port) | version absent from the selector; registration missing pre-tag |
| 4 | the changelog boundary | `CHANGELOG.md` after the next regeneration (or the dry-run paste) | Unreleased still carrying post-tag commits; boundary at the wrong tag |
| 5 | contributor window | `git log <range> --format='%an'` minus bots + owner | unacknowledged new human contributor; empty = recorded result |
| 6 | the SDK pairing | `sdk-drift` green; the compatibility matrix render | cut made over a red/trailing gitlink |
| 7 | ui-html workspace member | same-commit motion (path dependency) | (recorded n/a — the row exists so the walk never wonders) |

### 2.8 The family check (the cross-line rows every cut walks, whichever line)

Two rows only — the per-line walks stay in their homes: (a) **gap check** — "is any upstream gap window open for the line I am cutting?" (ui-html cut: never; SDK cut: the ui-html pin window; gateway cut: both); (b) **pairing-pending check** — "does a downstream pairing from a prior upstream release remain unlanded?" (recorded, scheduled — it does not block an upstream line, it is the window's bookkeeping).

---

## 3. The encoding plan — where every clause lands

| Clause | Home | Notes |
|---|---|---|
| The whole process doc (§2 skeleton) | NEW `docs/internal/release-process-family.md` | Engineering register; `docs/internal` is an EXCLUDED dir in the docs-literal ratchet (`DOCS_EXCLUDED_DIRS`, `scripts/standards/count_version_literals.py`) — zero version-literal constraints, no `--refresh-docs-baseline`. Placeholder convention (`vX.Y.Z`) kept anyway — the doc states rules and cites machine sources, never numbers (the prose-defers doctrine). |
| ui-html pointer | one sentence in `docs/internal/ui-html-release-and-pin.md` | Naming the family doc as the umbrella; the ui-html doc stays the line's authority. |
| The new obligation row | `docs/internal/drift-and-obligations.md` | "A release-machinery change (any line's publish workflow, cliff config, tag scheme, version source, or the family process doc itself) moves `docs/internal/release-process-family.md` in the same change." **Collision flag:** the i308-design lane may touch this file — park-and-rebase at PR time (declared, per brief). |
| The refusal pin | NEW `tests/contract/test_docs_site_refuse_if_tagged.py` | Pins the gateway tag-namespace contract: an exact `vX.Y.Z` tag list refuses; `ui-html-v*` tags pass (they share the repo and must never brick the gateway's docs assembly); a pre-release-suffixed `v*` tag passes (TAG_RE is exact-match). Monkeypatch the `run` helper — no tag is ever created in the working tree (xdist-safe). |
| Tag protection + shadow-tag cleanup | the process doc's §2.6 (out-of-repo steps, named exactly) | Nothing in-repo can perform them; the doc naming the settings is the whole implementable surface (the pending-publisher precedent). |
| SDK-side registration | NOT this increment | §4 D3 — the SDK repo gets its pointer paragraph on its own train. |
| Workflows | NOT this increment | No `.github/` bytes move. The existing guard (`startsWith(tag,'ui-html-v')`) already makes a gateway release a no-op for the publish pipeline — verified by the workflow's own header comment. |

**ASD-STE100 ruling:** the process doc is an internal engineering record (like its two siblings in `docs/internal/`) — the documentation register applies to published operator/user/developer text, and none moves in this slice. No `document-writer` dispatch needed; no operator-guide/README motion (a release process is maintainer-facing, not operator-visible behavior).

---

## 4. Minimal first increment — and the deferrals

**IN (this slice):** the process doc (§2, full skeleton rendered); the ui-html-doc pointer sentence; the drift-and-obligations row (collision-flagged); the refusal-pin test; this record. Out-of-repo operator steps EXECUTED and evidenced (tag protection both repos; local shadow-tag cleanup) — they are acceptance arms, not diff content.

**OUT — each with identifier, deferred thing, home, reopen trigger:**

- **D1 — the gateway versioned-docs port** (per-tag snapshot assembly, `versions:` registration, selector, the ordering constraint; enabling the changelog page). Home: its own gateway tracker issue, filed with this increment's PR (it is the named prerequisite inside the doc's readiness gate). Trigger: the decision to cut the first gateway release (the #308-window or any later).
- **D2 — a gateway publish workflow.** Home: the family doc's deferral row + the tracker. Trigger: the first consumer that installs the gateway package from an index (none exists — not on PyPI, deployed from checkout/systemd; the ui-html pipeline exists precisely because PRD 12's standalone host consumes that wheel).
- **D3 — SDK-side pointer to the family doc + a written SDK version-selection paragraph.** Home: the SDK repo, its next docs train. Trigger: the next SDK release walk after this doc lands (its matrix result records gain the family pointer).
- **D4 — ui-html `workflow_dispatch` arm; D5 — environment binding on publish jobs.** Carried unchanged from the issue-#302 record §3 (triggers already named there: the first missed/dropped release event; a second maintainer with write access or an owner ruling).
- **D6 — pin-freshness escalation policy** (issue #294 D-3). The family doc's gap-window clause is the procedural half; the policy remains deferred at its home. Trigger: unchanged.
- **D7 — the ui-html contract census guard.** Rides the #309 consuming slice, unchanged.

---

## 5. Precedent

Every element extends a proven in-tree mechanism: the issue-#302 two records (the release-pipeline + first-release pattern — marker commit, pinned cliff commands, walk rows, operator setup, acceptance arms R1–R6) are the direct template for the gateway line; the SDK matrix + `release-review` skill (row discipline, the ordering constraint, result records) are the walk's precedent — and the skill's own Scope section pre-invited exactly this adoption ("the gateway can adopt this skill/matrix pair when its own releases need the same gate"); `refuse_if_tagged` is the existing, in-tree, loud namespace guard the doc cites rather than replaces; the drift-and-obligations row shape is obligation 19/22's. No new architecture — the one new artifact is a document.

## 6. Invariant and drift impacts

- **Hard invariants: none touched, none amended.** No `src/benchweave`, no `standards/`, no state, no registry, no fixtures. CTL/STO/CON/REG untouched.
- **Version-literal zero gate:** untouched by construction — `docs/internal` is an excluded dir (verified: `DOCS_EXCLUDED_DIRS`); `.claude/` and `tests/` are outside every gated scope (obligation 20's denominator boundary). The process doc carries zero version literals regardless (review arm A1).
- **Standards tripwires:** expected clean — no `standards/` bytes, no standard-version strings in any operative file (package-version numbers in the record's evidence tables are not standard versions; the process doc uses placeholders). The standards-governor mandate does not fire for the operative diff.
- **Surfaces that move:** `docs/internal/` (one new, one edited), `docs/internal/drift-and-obligations.md` (one row), `tests/contract/` (one new small test), `.claude/deep-review/` (this record). No MCP tools, REST/openapi, CLI, operator docs, vendored standards, fixture lattice, SDK-repo bytes, pyproject/uv.lock, submodule pointer, `.github/`.
- **CI cost:** one new test file (~seconds). No new jobs. The tag-protection and cleanup steps are out-of-repo.

## 7. Tier and keyword scan (#254 design-time call)

**TIER 3.** Rules that fire: (1) the Step-1 **keyword rule** — the expected diff text contains `protection` well above threshold (the phrase "tag protection" is the GitHub feature's own name; contorting the prose to dodge the word would weaken the doc, the exact dodge the #254/#302 records reject), plus `sha256` (the pairing section cites the digest-row convention) and `recovery` (the record's citations of the missed-event recovery deferral). First match wins; the docs-only path rule (Tier 1) is overridden by the text it carries — the rubric's own "keyword-rule interplay" paragraph. (2) Independently, `tests/` is a Tier-2 path floor. **Exact counts, measured (python word-boundary scan) over this record + the §2 skeleton text — the doc's final prose derives from the skeleton by rendering, so the counts carry; enumeration mentions inside this scan statement itself are disclosed per #254 and not counted:** `protection` = 23, `recovery` = 3, `sha256` = 1, `threading` = 0, `asyncio` = 0, `subprocess` = 0, `hashlib` = 0, `migrate` = 0. The two small edits (pointer sentence; obligation row) and the test file carry none of the eight. The builder re-derives the count over the actual diff; the tier does not change under any plausible count of `protection` ≥ 1. **Consequences accepted:** cold full battery + the two-lane G6 refute (the honest depth for a text that defines protective-adjacent procedure; lane 2 should probe: does any stated machine signal not actually exist; does the order rule contradict a gate; does the walk omit a version-bearing surface).

## 8. Measurable proof and the pre-committed acceptance rule

**On the PR (pre-commit):**

- **A1 DOC-EXISTS + CITATION SWEEP:** the process doc exists under `docs/internal/`, carries zero three-component version literals (grep over the file), and **every machine mechanism it names exists at merge HEAD** — the sweep list: `publish-ui-html.yml`, `package.yml`, `changelog.yml`, `cliff.toml` (anchored `tag_pattern`), `refuse_if_tagged` in `scripts/assemble_docs_site.py`, `scripts/check_sdk_submodule_drift.py`, the `sdk-drift` and `ui-html-pin-freshness` CI rows, `great-docs.yml`, the SDK's `pin-freshness.yml` + `release-review` skill. Reviewer pastes the sweep result (the doc-rot control — a doc that cites a dead mechanism fails here).
- **A2 REFUSAL PIN + MUTATION CONTROL (the RED arm):** the new test green on the real function; then the control — weaken `TAG_RE` to a prefix match in a scratch copy and the `ui-html-v*`-passes arm FAILS (proves the pin bites; the exact shape an anchor regression would take). A pin that passes both ways proves nothing — the mutation is the falsifier.
- **A3 GATES:** fast triple per commit; Tier-3 cold full battery before push; tripwires clean.

**Out-of-repo, evidence pasted to the tracking issue:**

- **A4 TAG PROTECTION (machine-observable flip):** `gh api repos/madeinoz67/benchweave/tags/protection` and the SDK equivalent return the configured rules, where the same reads returned **404 on 2026-10-04** (recorded above). Before/after pasted. **Degrade path:** if the endpoint refuses on this plan and rulesets cannot express it, record the limitation in the doc (degrade loudly) — the arm dies, the increment does not.
- **A5 SHADOW-TAG CLEANUP (count flip):** `git tag -l` in the maintainer's gateway clone drops from 10 to 2 tags; commands + read-back pasted.

**The live run (the self-hosting proof; the issue-close condition):**

- **A6 FIRST CUT UNDER THE DOC:** the first release of ANY line after this doc lands executes under it — its walk's result rows recorded on the tracking issue (the doc's checklist IS the audit trail). If that first cut is the gateway's, its readiness gate must show the versioned-docs disposition (landed prerequisite, or the cut correctly did not happen). Which line fires first is not ours to choose — all three are legal first runners.

**SHIP if** A1–A3 green + A2's mutation control red + A4/A5 flips pasted. The issue stays open until A6 runs.
**KILL (an arm):** A4 unconfigurable on both mechanisms (recorded loudly; doc ships with the absence); A2's mutation control cannot be made to fail (the test leg is dropped as unprovable, disclosed — a pin that cannot bite is worse than no pin).
**KILL (the design):** the order rule as documented contradicts a machine signal (a gate the doc claims blocks something nothing blocks, or vice versa) — fix the doc against the machine before ship; prose defers to machine sources, always.
**UNDERPOWERED:** A6 cannot run because no line cuts within the window — the increment ships on A1–A5 with A6 open, reported as underpowered-with-named-trigger (the next cut of any line); never silently closed.

## 9. Risks and falsifiers

1. **Doc rot vs machine state** — the standing risk of any process doc. Falsified at review by A1's citation sweep; held over time by the new obligation row (a release-machinery change must move the doc) and by the doc's own rule that it cites machine sources, never numbers. A rotted row discovered later is fixed against the machine, never the reverse.
2. **Tag protection does not stop the admin** — on a personal-account repo the owner IS the exempt role; the protection's real value is against automation mistakes and leaked credentials. The walk's tag↔version row remains the semantic gate; the residual is stated in the doc, not hidden.
3. **The ui-html→SDK gap window is procedural** (WARN-only signal) — a breaking ui-html release followed by an SDK cut before the pin-bump is possible if the process is skipped. Mitigations: the weekly WARN, the doc's clause, and D6's escalation policy as the named future fix. Falsifier for the doc: the SDK cutting a release whose server extra pins a ui-html version older than a contract-minor — that would be the window violated, and the record of it lands on the tracking issue.
4. **The gateway first cut is blocked on D1** (the versioned-docs port) — if the window arrives without it, the readiness gate correctly refuses the cut (`refuse_if_tagged` enforces loudly). The risk is schedule disappointment, not correctness; the doc makes the prerequisite impossible to miss.
5. **Shadow-tag deletion is local-only** — another clone may carry the eight tags. The remote is clean (verified); a leak bricks docs CI loudly and is recovered by deleting the remote tag. Disclosed in §2.6.
6. **The `v0.1.0` recommendation collides with the LOCAL shadow tag `v0.1.0`** until cleanup runs — sequencing note: A5 precedes any gateway cut (the readiness gate's implicit step 0; called out in the doc's §2.6).

## 10. Forks for the owner (adopt-with-recommendation unless struck)

- **F1 — the gateway first-release number.** RECOMMEND `v0.1.0` (pyproject as-is, empty marker commit — the family invariant and the issue-#302 fork-(c) precedent; nothing was ever released as gateway 0.0.x–0.3.x, so no promise is broken). The "v0.3.2 continuation" framing is REJECTED on the evidence in §0. Alternative: any owner-chosen number via a bump commit — the procedure is unchanged.
- **F2 — tag protection promoted to required setup.** RECOMMEND adopt (§2.5's reasons: tags bypass branch protection; a stray tag has three loud-but-costly effects — bricked docs CI, a fired publish pipeline for `ui-html-v*`, changelog-boundary corruption pre-anchor; cost is one settings page per repo).
- **F3 — the marker-commit-on-main exception extends to the gateway line.** RECOMMEND adopt (the issue-#302 risk-5 disclosure verbatim: the directive targets work commits; process uniformity beats a per-line special case). Strike = tag-the-tip, documented as the alternative.
- **F4 — stable-only index policy.** RECOMMEND keep (§2.3's evidence; reopen trigger named).

## 11. Coordination

- Concurrent lane `i308-design` (SDK-shim design, `.wt/i308-design-*`) may touch `docs/internal/drift-and-obligations.md` — my encoding touches it too (one row). Files otherwise disjoint; park-and-rebase at PR time per the brief.
- The brief's "gateway v0.3.2 window after #308's pointer lands" is preserved as a WINDOW, not a number: if that window fires with D1 landed, it becomes the doc's first gateway live run (A6) at whatever number F1 settles.
- No SDK-repo bytes move in this slice; D3's pointer paragraph rides an SDK train.
