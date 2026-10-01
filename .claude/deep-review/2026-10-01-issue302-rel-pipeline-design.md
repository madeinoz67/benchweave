# Issue #302 (REL) — ui-html release pipeline and versioning machinery — design record

**Status:** DESIGN COMPLETE, both owner forks adopted 2026-10-01 (keep 0.1.0; no second changelog) · **Slice:** REL, the pipeline half of issue #302 — everything except the first release, which stays gated on G1e (#301) · **PRD:** docs/implementation-planning/12-gateway-web-ui-prd.md §8 NFR-P1–P4, §9 Q5, §11 dependency 4 · **Base read:** main at be294d3, 2026-10-01.

## 1. Premise (verified against the tree)

- `packages/ui-html/pyproject.toml` is landed: `benchweave-ui-html`, version **0.1.0**, hatchling, runtime deps exactly `jinja2>=3.1` + `markupsafe>=3.0`, pytest only in the `test` dependency-group, one `pytest11` entry point (`benchweave_ui_html.contract_harness.plugin`), wheel target `src/benchweave_ui_html`.
- Root `pyproject.toml`: uv workspace `members = ["packages/ui-html"]`; `benchweave-ui-html` is a **dev** dependency with `{ workspace = true }` source. The gateway's runtime dependency list does not include it — correct for G1 (only the contract harness is consumed at test time); it becomes a runtime dep when the G2 host renders partials. Not this slice.
- `.github/workflows/package.yml` builds and proves TWO wheels (gateway + SDK submodule) via `scripts/sdk_smoke.py` in a clean venv outside the checkout, matrix ubuntu+macos, `contents: read`. **No workflow anywhere builds the ui-html wheel** (verified in package.yml and ci.yml; OPEN-4 for the three unread workflows, none load-bearing here).
- `cliff.toml`: conventional commits, `tag_pattern = "v[0-9].*"`, skip patterns `chore(release): prepare for` / `chore(changelog)`.
- The SDK repo has `publish.yml` (release-published trigger; not re-read this session — OPEN-3). **No reference to `benchweave-ui-html` exists in the SDK repo today** (grep over pyproject + src, 2026-10-01): the pin target — the standalone distribution manifest — has no row for the wheel yet; the PRD 11 consuming slice creates it.

The gap REL closes: the package exists, but nothing proves it is (a) buildable as a standalone wheel, (b) installable alone with only its two declared deps, (c) covered by a written version policy that gives NFR-P2's "a contract change bumps the package" a mechanical meaning, or (d) reachable by the SDK repo through any documented path (Q5: "a package release and a pin bump in the SDK repository, never through a copied template").

## 2. Mechanism

### 2.1 CI proves the wheel without publishing (lands now)

Extend the **existing** `build` job in `.github/workflows/package.yml` with one step block after the sdk_smoke step — same job, same ubuntu+macos matrix, same `contents: read` permission (the job keeps zero publish capability by construction; acceptance A3 checks exactly this):

1. **Build:** `uv build --out-dir dist/packages/ui-html packages/ui-html` — same command shape as the SDK line; uv's default builds the wheel from the sdist, proving both distributions (OPEN-1 for the workspace-member invocation).
2. **Fresh venv outside the checkout** (`mktemp -d`, mirroring sdk_smoke's TemporaryDirectory isolation): `uv venv --python 3.13`; `uv pip install` the built wheel; then with `python -I`:
   - `import benchweave_ui_html` — the runtime namespace imports with no repo on `sys.path`;
   - `importlib.metadata.version("benchweave-ui-html")` equals the version in `packages/ui-html/pyproject.toml` (read via a tomllib one-liner — the single-source rule enforced at the artifact);
   - a `pytest11` entry point named `benchweave_ui_html` with value `benchweave_ui_html.contract_harness.plugin` is present in the installed metadata — the wheel carries the contract gate;
   - the installed distribution set is exactly `{benchweave-ui-html, jinja2, markupsafe}` (`uv pip list`; NFR-P1/UR-11 proven at the artifact — the control arm in §7 makes this assertion bite).

Deliberately NOT asserted: presence of templates/assets/partials in the wheel — G1b's layout is in flight, and the check is order-independent so REL can merge before or after G1b. Wheel resource-completeness becomes a G1e release-review item (§8.4).

### 2.2 Version policy (lands as the docs page; the numbers are already on main)

- **Single source:** `packages/ui-html/pyproject.toml` `[project].version`. No `__version__` attribute now; if one is ever added, a test pins it to `importlib.metadata` (SDK precedent: `scripts/sdk_smoke.py` `installed_check`).
- **Bump semantics (pre-1.0):** contract change → **minor** (`0.x.0`); implementation change → **patch** (`0.1.x`). Rationale: the repo already treats tightening as the breaking class and bumps MINOR for it (issue #64 ruling); NFR-P2 wants the version to carry "the contract moved", and reserving the minor position for exactly that makes a pin bump decidable from the version alone.
- **Contract change defined:** ANY byte motion in `docs/internal/ui-contract.md`, or in the vendored token assets the §A pins assert against (`tokens.css`, `themes.css`), is a contract change → minor. Flat by design: the harness fail-closes on heading/table structure, so "this prose edit changed nothing the harness sees" is expensive to prove and cheap to skip. Accepted cost: prose-only contract edits burn a minor bump — noise-level pre-1.0, revisit at 1.0.
- **Implementation change:** everything else in the package (partial internals, harness mechanics, fixtures) with those two surfaces byte-identical.
- The gateway never pins a released version of its own workspace member (workspace path dep — moves in the same commit by construction). The standalone distribution pins **exact** versions (`==`), never ranges: a range would let a contract change reach standalone without the pin-bump PR, violating Q5.

### 2.3 Tag, changelog and commit conventions (rides the existing git-cliff setup)

- **Tag scheme:** `ui-html-vX.Y.Z`; gateway tags stay `v[0-9].*`. `cliff.toml`'s existing `tag_pattern` is expected to leave `ui-html-v*` out of the gateway changelog — verify anchoring at G1e before the first tag exists (OPEN-2).
- Work commits ride the gateway changelog as today; scope them `feat(ui-html)` / `fix(ui-html)` so release-notes selection is trivial.
- At release time (G1e, NOT this slice): the version-bump commit is named `chore(release): prepare for ui-html vX.Y.Z` — riding the **existing** cliff skip pattern verbatim, no cliff.toml edit needed. Release notes for the ui-html tag are cliff-generated at release time. No second committed CHANGELOG file (fork §9b, adopted).

### 2.4 The publish path (designed to the line; lands at G1e)

New `.github/workflows/publish-ui-html.yml` in THIS repo at G1e: `on: release: types: [published]`, filtered to `refs/tags/ui-html-v*`; `id-token: write` for PyPI trusted publishing (no token secret in the repo); build the member wheel, `uv publish`, then verify by direct PyPI read. Version bumps trigger the release-review matrix walk (standing rule); ui-html adds version-bearing surfaces, and the matrix rows for it land with G1e in whichever surfaces carry the version.

### 2.5 The pin process document (lands now)

**Location:** `docs/internal/ui-html-release-and-pin.md` in THIS repo — authoritative, beside the package, the tag machinery and the contract it releases. The SDK repo gets a one-paragraph pointer in its standalone distribution docs when the PRD 11 consuming slice creates the manifest row (the cross-link lands there, not here; nothing in the SDK references the wheel today — verified §1).

The doc names its steps (acceptance A2 checks exactly this list):
1. Change lands in this repo (conventional commit; `ui-html` scope where relevant).
2. Version decision per §2.2 (minor iff the contract surface moved).
3. Bump `packages/ui-html/pyproject.toml`, `uv lock`, commit as `chore(release): prepare for ui-html vX.Y.Z`.
4. Tag `ui-html-vX.Y.Z` on the bump commit; GitHub release with cliff-generated notes; the publish workflow fires on release published; verify PyPI by direct read.
5. Pin-bump PR in the SDK repo: raise `benchweave-ui-html==X.Y.Z` in the standalone distribution manifest (exact pin). Never a copied template (Q5).
6. Both hosts green: gateway CI (workspace path — same commit), SDK standalone CI against the **published** wheel (never a local path override in CI).
7. **Guard (designed; lands with the PRD 11 consuming slice):** the SDK repo vendors the contract census — table count, row count, and the digest of `docs/internal/ui-contract.md` at the pinned release's tag — and standalone CI runs the pinned wheel's own harness against that vendored copy. Interim, until the guard lands: the pin-bump PR body records the contract digest at the release tag (one command, checkable by any reviewer).

The census guard is the mechanically checkable core of "both hosts move together": the same contract bytes enforced by both hosts, or the pin PR cannot go green. The gateway-side residual between now and G1e is honest and procedural: nothing yet FORCES a minor bump when `ui-contract.md` moves (the harness forces the partials to move with it, but not the version); the release-time walk in steps 2–3 is the check, and the guard mechanizes it later. Disclosed as a residual, not hidden.

## 3. Minimal first increment — scope and deferrals

**IN:** the package.yml step block (§2.1); `docs/internal/ui-html-release-and-pin.md` (§2.2/§2.3/§2.5, with the publish path §2.4 documented-not-landed); this record.
**OUT (deferred, each with its home):**
- The first release and ANY version motion of anything — G1e / #301 (REL bumps nothing: zero byte motion in `pyproject.toml`, `packages/ui-html/pyproject.toml`, `uv.lock`).
- `publish-ui-html.yml` — G1e.
- The census emitter + SDK-side vendored-contract guard — the PRD 11 consuming slice (it touches `packages/ui-html/src`, which is G1b's active territory).
- Wheel resource-completeness assertions — G1e release review.
- The SDK-side pointer doc — the slice that creates the manifest row.
- A second committed changelog file — recommended against (fork §9b, adopted).

## 4. Precedent

Every moving part extends a proven in-tree mechanism: `scripts/sdk_smoke.py`'s clean-venv installed-check (isolated venv outside the checkout, `python -I`, metadata asserts) is the import-smoke pattern; `package.yml`'s existing build job is the lane; the SDK repo's publish flow (release-published trigger + direct PyPI read-back) is the publish convention; `cliff.toml`'s skip patterns and tag handling are the changelog substrate; the workspace-member dev-dep wiring (landed by G1a) is the consumption precedent. No new architecture.

## 5. Invariant and drift impacts

- **Hard invariants:** none touched, none amended. No code under `src/benchweave`, no standards bytes, no state, no registry, no fixtures. Standards tripwire: `git diff origin/main...HEAD -- standards/` empty on the expected diff; no version-string touches of existing packages.
- **Surfaces that move:** `.github/workflows/package.yml` (CI), `docs/internal/` (one new page), `.claude/deep-review/` (this record). No MCP tools, REST/openapi, CLI, operator docs beyond the new page, vendored standards, fixture lattice, or SDK-repo bytes.
- **On-disk format/schema:** none → not format-Tier-3.
- **drift-and-obligations.md:** no new row in this slice. When the PRD 11 consuming slice creates the pin, THAT slice adds the obligation row (ui-html release ↔ SDK standalone pin; trigger: first standalone distribution release consuming the wheel). Named here so it is not lost.
- **CI cost:** one hatchling build of a tiny pure-Python package + one venv + three tiny installs, riding the EXISTING package.yml job and matrix — tens of seconds per OS, no new job, no new runner, no publish permission.

## 6. Tier and keyword scan (#254 design-time call)

**Tier 2.** Path rules that fire: `.github/workflows/` (Tier-2 list). No Tier-3 rule matches: no `standards/`, `contracts/`, `state/`, `registry/` or fixture-lattice path; no dependency add/remove/re-pin (`pyproject.toml` and `uv.lock` untouched — scope invariant A4); no submodule pointer motion.

Keyword scan over the whole expected diff (package.yml step block + the new docs page + this record): **subprocess 0 · threading 0 · asyncio 0 · sha256 0 · hashlib 0 · migrate 0 · recovery 0 · protection 0.** Convention disclosed: this scan-statement sentence itself names the eight Step-1 keywords once, as #254 requires; that sentence is not counted, otherwise no compliant record could ever state a clean scan. Every other occurrence in the expected diff is zero (the record and doc say "digest" throughout).

Disclosure: if the builder cannot express the venv checks in bash and adds a Python smoke helper, the helper's imports will carry first-match keywords and the slice re-tiers to Tier 3 — that is a fork back to the owner (§7 KILL), not a silent expansion.

## 7. Measurable proof and the pre-committed acceptance rule

- **A1 BUILD+INSTALL:** on the REL branch CI (PR run) and again on main after merge — 4 executions (2 OSes × 2 runs) — the step block produces `dist/packages/ui-html/benchweave_ui_html-<version>-py3-none-any.whl`, installs it into a fresh venv outside the checkout, and every §2.1 assertion passes (import; version equality with pyproject; pytest11 entry point; installed set exactly the three distributions).
- **A2 DOC:** `docs/internal/ui-html-release-and-pin.md` exists and names all seven steps of §2.5 plus the tag scheme, the exact-pin rule, the single-source rule and the minor/patch semantics. Missing or partial = FAIL.
- **A3 NOTHING PUBLISHES:** the diff contains no workflow with a publish trigger and no credential/permission motion; hits for publish-capable triggers exist only as prose inside the docs page and this record, zero in workflow YAML.
- **A4 NOTHING MOVES:** `git diff origin/main...HEAD -- pyproject.toml packages/ui-html/pyproject.toml uv.lock` is empty.
- **CONTROL (the arm fluff cannot pass):** the installed-set assertion run once against the **gateway wheel** (whose runtime set is nine distributions) must exit non-zero — pasted in the PR body by the builder. A dep-set assertion that passes against both wheels proves nothing.
- **SHIP if:** A1–A4 green on all 4 executions + control red + the tier/scan statement verified by review.
- **KILL if:** any A1 assertion false on any OS; or the block only works via a Python helper carrying the Step-1 keywords (escalate the tier fork, do not absorb); or building the member requires an invocation that touches the root lock or root pyproject (dependency-rule Tier 3 by accident, and A4 dies — redesign, likely building from inside the member directory).
- **UNDERPOWERED:** if the control arm cannot be executed locally by the builder, the green arm alone does not ship — hold and report.

## 8. Risks and falsifiers

1. `uv build` of a WORKSPACE member may need a different invocation or may try to build the whole workspace. Falsified fast (first CI run); fallbacks: build with cwd inside `packages/ui-html`, or `uv build --package benchweave-ui-html`. OPEN-1.
2. cliff `tag_pattern` anchoring: if it matches by substring, `ui-html-v0.1.0` would render into the gateway changelog as a duplicate entry. Falsified with a dry run before the first tag (G1e); mitigation: anchor the pattern (one-line cliff.toml edit at G1e). OPEN-2.
3. Version discipline is procedural until the census guard lands: a contract edit can merge without its minor bump and nothing reddens. Mitigation: the release-time walk (§2.5 steps 2–3) blocks the release; residual accepted and disclosed.
4. G1b layout drift: if vendored assets land outside `src/` (not packaged by the wheel target list), the first G1e resource-completeness check fails late. Forward guard: G1b's review checks assets sit inside `src/benchweave_ui_html` — relayed to the G1b lane.
5. Coordination collision: REL and G1b touch disjoint files except `packages/ui-html/pyproject.toml` if G1b adds test-group deps. The declared merge order makes any conflict visible, not a surprise.

## 9. Forks — both adopted by the owner's cadence rule, 2026-10-01

**a. Starting version: KEEP 0.1.0.** The first release carries the harness, partials, proofs and library — feature weight per the owner's own versioning rule; `0.x.0` reserved for contract motion from day one. **b. No second committed changelog** — cliff-generated release notes at tag time.

## 10. Coordination with the G1 lanes

- Shared surfaces with G1b: NONE in code by design — REL does not touch `packages/ui-html/src` or tests. Only possible file-level overlap: `packages/ui-html/pyproject.toml` (if G1b adds test-group deps); not semantic for either side.
- **Stacking:** REL branches off main; the merge order (G1b first if both are ready, else REL first) is declared in the PR body; every REL assertion is order-independent (§2.1).
- **Handoffs to G1e (#301):** the publish workflow (§2.4), the census emitter + guard (§2.5 step 7), the cliff tag-isolation dry run (OPEN-2), release-review matrix rows for the new version-bearing surfaces, and the wheel resource-completeness check.

## 11. Open items (marked, not searched)

- **OPEN-1:** exact `uv build` invocation for a workspace member (verify on the first CI run; fallbacks §8.1).
- **OPEN-2:** cliff `tag_pattern` anchoring semantics for `ui-html-v*` isolation (verify at G1e).
- **OPEN-3:** the SDK `publish.yml` exact shape is from release-run memory, not re-read this session; G1e verifies the trigger shape before `publish-ui-html.yml` is written.
- **OPEN-4:** `.github/workflows/changelog.yml`, `docs.yml`, `device-plugins.yml` were not read (not load-bearing for REL); read changelog.yml at G1e if the release-notes render needs its mechanics.
