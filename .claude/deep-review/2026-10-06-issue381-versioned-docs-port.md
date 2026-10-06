# Issue #381 — the versioned-docs port — design record

**Status:** DESIGN COMPLETE · **Slice:** one slice — the versioned assembly (script + contract tests + workflow pin + website selector scaffold + family-doc amendment) · **Carrier:** the gateway first-release train (a `v0.4.0`-class cut under the owner ruling of 2026-10-04; the port is the train's named prerequisite).
**Base read:** origin/main at `0adf2d86` (worktree `.wt/design381-a17f/`, branch `feat/issue381-versioned-docs`), 2026-10-06. Pre-flight: `git fetch origin` clean; zero open PRs on the gateway tracker; no remote branch names docs-versioning work (`feat/issue359-docs-truth`, `feat/issue317-website-status`, `feat/website-deferrals` are stale feature branches with no open PRs — verified `gh pr list` returns `[]`).
**Port source:** the SDK repository at `~/Documents/src/benchweave-sdk`, main `6fbc07e`. All SDK citations are that tree.

**Verdict: BUILD** — with one structural divergence from the SDK mechanism forced by the gateway's own staging design (§1.2), and the linear per-tag CI cost accepted with a named mitigation deferral (§2 Q5, D3).

---

## 0. Root cause and port source read

**The defect this port retires is deliberate.** `refuse_if_tagged`
(`scripts/assemble_docs_site.py:418`) lists tags via `git tag --list v*` and filters
through `TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")` (`:90`); any exact `vX.Y.Z`
match aborts assembly with "port the SDK's per-tag snapshot assembly before publishing
a released gateway's docs". The docs workflow checks out with `fetch-depth: 0` — full
history, tags included (`.github/workflows/docs.yml`, the checkout step's own comment
names `refuse_if_tagged` as the reason) — so the push of the first gateway `vX.Y.Z` tag
turns every docs run (every PR, every main push) red until this port lands. That is
readiness condition 1 of `docs/internal/release-process-family.md` ("The gateway line's
cut procedure"), quoted verbatim in the issue: the port must deliver "per-tag `v/<tag>/`
buckets, a `versions:` list, the site selector, and the pre-tag registration ordering
constraint the SDK's own port learned the hard way". The refusal is correct behavior for
an unreleased repo; this port is what converts it into versioned serving.

**What the SDK implementation actually does** (`benchweave-sdk/scripts/assemble_docs_site.py`,
read in full; the gateway assembly is its documented sibling — the gateway's module
docstring says so at `scripts/assemble_docs_site.py:7`):

1. **Per-tag buckets.** `release_tags()` (`:115-119`) — the same `git tag --list v*`
   glob + the same anchored `TAG_RE` as the gateway's refusal, sorted by version tuple.
   For every tag whose ref carries a `great-docs.yml` (`ref_has_config`, `:122-131`,
   via `git cat-file -e`), an **isolated build** runs
   `great-docs build --from-repo <url> --branch <tag> --versions <tag>` (`:205-221`) and
   the output is lifted into `docs/v/<tag>/` (`bucket_source`, `:187-202`, tolerating
   both the bucket and the flat-root render shapes); the **latest** tag's build also
   replaces the `docs/` root outside `v/` (`replace_root`, `:224-233`, invoked at
   `:651-653`). `main` renders to `docs/v/dev/`.
2. **The `versions:` list.** A static, complete, descending list in `great-docs.yml`
   (`- tag: / label: / latest: / git_ref:` per entry, exactly one `latest: true` —
   the SDK's `great-docs.yml:552-592`). It is derived nowhere; it is REGISTERED by
   hand at release time, and the assembly **refuses** any release tag absent from it
   (`:613-618`). Because the list is static and complete, every bucket's in-docs
   version widget lists all versions known at that ref.
3. **The selector.** Two surfaces. The in-docs navbar widget comes from `versions:`
   itself (with a 0.17.0 doubled-`v` trigger bug the assembly un-doubles in every
   generated `version-selector.js` — `fix_version_selector_trigger`, `:377-404`, with
   drift WARNs). The static front door hard-codes a `<select class="version-select">`
   whose options the assembly **parses back** (`website_version_options`, `:444-460`)
   so `verify_tree` can fail the drift — a selector advertising a version with no
   bucket, or the wrong "(latest)" (`:486-496`).
4. **The pre-tag registration ordering constraint — the lesson.** The great-docs
   per-tag build reads the **tag's own** `great-docs.yml` and filters its `versions`
   list against the requested version. Registering a release after cutting its tag
   therefore fails the build with "Multi-version build: 0 version(s)" — observed on
   the SDK's v0.0.4 (tag `06891a7` cut pre-registration; repaired by re-pointing onto
   `6f482ef`; v0.0.3 never failed because its registration landed four minutes before
   its tag). The machine half the SDK owns is the current-tree completeness refusal
   (`:613-618`); the tag-self half was only ever caught by the build failing. The
   gateway port mechanizes both halves (§1.3).

Not ported, with reasons: the **pre-site approximation machinery** (`:621-636`,
in-process buckets for tags predating the site config — v0.0.1/v0.0.2-class). The
gateway has no pre-port tags by construction (the port precedes the first cut — that
ordering is the issue's whole point), so the class is empty; if a stray pre-port tag
ever appears (the shadow-tag push class the family doc names), the port's registration
checks refuse it loudly rather than approximating it. Also not ported:
`reorder_reference_sections` (`:324-374`) — the gateway config is `reference: false`;
and the SDK's PR preview-comment job — the gateway workflow has none today.

---

## 1. The mechanism

### 1.1 The regime switch — the port's key divergence from the SDK

The SDK assembly refuses to run at all with zero release tags
(`:609-610` — "no release tags found — nothing to assemble"). The gateway port lands
**before any tag exists**, so it must not: the zero-tag path stays alive and produces
exactly today's tree. The ported script has two regimes, derived from one scan:

- **Zero `vX.Y.Z` tags (port landing → first cut):** the assembly is byte-for-byte
  today's behavior — one unversioned build of the current tree at `docs/`, no `v/`
  tree, no aliases, no `versions:` key, the front-door selector showing a single
  `dev` option (§1.4). This is what keeps every PR's Build Docs lane green through
  the port's own merge.
- **One or more tags (first cut onward):** versioned serving. `docs/` root = the
  latest tag's bucket; `docs/v/<tag>/` per tag; `docs/v/dev/` = the current tree;
  `v/latest/` and `v/stable/` alias redirects; the in-docs widget and the front-door
  selector populated from the registered versions.

The regime boundary is one function — `release_tags()` ported verbatim from the SDK
(`:115-119`) — and the existing namespace discrimination travels with it unchanged:
the `git tag --list v*` glob plus the anchored `TAG_RE` (`scripts/assemble_docs_site.py:90`)
already excludes `ui-html-vX.Y.Z` (the `^v` anchor cannot match a prefixed tag; pinned
today by `tests/contract/test_docs_site_refuse_if_tagged.py` arms R2/R2b). The refusal
pin's own docstring names the contract — "**`ui-html-v*` tags must never trip the
gateway's [tag scan]**" — and that contract survives the mechanism's replacement by
moving into the new contract test (§3, file 2).

### 1.2 Per-tag buckets: the tag's own assembly builds its own bucket

The SDK's isolated build (`great-docs --from-repo`) **cannot work for the gateway**,
and the design does not pretend otherwise: the gateway's docs tree is a two-phase
build. The assembly stages `user_guide/` (flat, H1-lifted, link-rewritten —
`USER_GUIDE` map, `stage_pages`) and `standards_pages/` (mirroring `standards/<id>/<version>/`)
as **gitignored build-time trees** because the doc taxonomy forbids a second checked-in
copy of any guide (rule 1) and Great Docs only reads user-guide pages from a flat
root directory. An isolated `--from-repo` build of a gateway tag checks out the tag
and runs Great Docs directly — it finds no staged `user_guide/`, no
`standards_pages/`, no generated standards-CLI page, no pattern library: an empty or
refusing build. The SDK never had this problem because its docs sources are in-tree.

So the gateway's bucket mechanism generalizes the SDK's own principle — *the tag's own
configuration is what the bucket build reads* — one level up: **the tag's own assembly
script is what the bucket build runs.** Concretely, per release tag:

1. `git clone --shared <REPO> <staging>/<tag>-tree` (local object-sharing clone; no
   worktree metadata in the user's repo — the multi-agent worktree discipline stays
   untouched), then `git -C <tree> checkout --detach <tag>`.
2. `git -C <tree> submodule update --init` (the `packages/sdk` gitlink at that tag's
   pinned SHA; the workspace itself is root + `packages/ui-html` only —
   `pyproject.toml [tool.uv.workspace]` — so the SDK submodule is the sole fetch).
3. `uv run --project <tree> python scripts/assemble_docs_site.py --bucket <tag>
   --dest <staging>/<tag>-out --great-docs <parent's resolved great-docs binary>` —
   the **tag's own script**, in the **tag's own environment** (`uv run --project`
   syncs the tag's `uv.lock`; `UV_PROJECT_ENVIRONMENT` is set explicitly to a path
   inside the scratch tree so the parent's non-dot-venv convention cannot leak).
   The tag's staging, standards manifest, stamps, generated standards-CLI page
   (captured from the tag's own `python -m benchweave.standards --help`), pattern
   library, and corpus copy all derive from the tag's tree through the tag's code —
   no cross-version re-derivation, the anti-pattern a foreign-logic build would be.
4. Lift `<tag>-out/docs` into the parent's `docs/v/<tag>/` (`replace_dir` port); if
   the tag is latest, also `replace_root` it over `docs/` outside `v/` (SDK `:651-653`).

**`--bucket <tag>` mode is today's `main()` verbatim** — stage → build → repairs →
`verify_tree` — with exactly three deltas, each forced:

- `refuse_if_tagged` is not called (the refusal guarded an unversioned MAIN assembly
  under a released gateway; a bucket build of a tag's own snapshot is precisely the
  thing it demanded). The skip is the mode's documented purpose, not a quiet bypass.
- the Great Docs invocation passes `--versions <tag>` (the tag's own yml registers
  itself, so the filtered render is exactly this tag's pages; `bucket_source`'s
  two-shape tolerance is ported so a mis-marked registration still lifts — see §1.3's
  third check for why that shape should never occur).
- `add_site_home_link` and its `verify_tree` arm are omitted in bucket mode. The link
  is depth-relative (`../` per directory below the docs root), so a link injected at
  bucket depth is wrong after lifting one level deeper — and the parent's pass skips
  marker-carrying pages, which would ship the wrong link. The SDK's isolated buckets
  are link-free for the same reason: its `add_site_home_link` runs parent-side only,
  after lifting (`:695`). The parent's pass covers every page including bucket pages.

The parent's own render in the tagged regime is the in-process current-tree build with
`--versions dev` (SDK invocation shape, `:627-629`) producing `docs/v/dev/`. Everything
else the SDK repairs parent-side is ported parent-side: `fix_alias_stubs` +
`site_path_prefix` (the gateway's `site_url: https://www.benchweave.dev/docs/` yields
the `/docs/` prefix; `url=/` stubs would redirect one level too high on the project
path), `complete_favicons`' per-bucket copy, `fix_version_selector_trigger` over every
generated `version-selector.js` including buckets'.

### 1.3 The pre-tag registration ordering constraint, mechanized

Three checks in the parent assembly, all loud, all RED-first (§6 A3):

1. **Completeness** — every release tag must appear in the current tree's
   `great-docs.yml` `versions:` block, else refuse naming the missing tags. This is
   the SDK check ported verbatim (`:613-618`; parse via the SDK's `yml_version_tags`
   regex, `:134-140`).
2. **Tag self-registration** — the tag's OWN `great-docs.yml` (read via
   `git show <tag>:great-docs.yml`) must list the tag itself and mark it
   `latest: true` (at its own ref a correctly-registered tag is always the newest
   release). This is the v0.0.4 lesson turned into a machine check the SDK never
   had: the SDK detects a pre-registration tag only when the build fails; the
   gateway detects it before building anything, and the refusal message names the
   ordering rule ("register the release in great-docs.yml and merge BEFORE pushing
   the tag — the tag's own yml is what its bucket build filters").
3. **Inverse** — every `versions:` entry must be a real release tag (a stale
   registration for a deleted or never-pushed tag refuses), closing the direction
   the SDK's check leaves to build failure.

The `versions:` key itself does NOT land in this slice: the gateway's yml is
unversioned today and must stay so while zero tags exist (adding an empty `versions:`
list is a Great Docs behavior change no run has pinned). The key lands with the FIRST
release's registration — one entry, pre-tag, per the constraint above. The machinery
that parses and enforces it lands now and is vacuous-green until then (check 1 with
no tags; checks 2-3 with no list — the regime consistency below closes the loop).

**Regime consistency check** (cheap, both directions): tags exist ⟺ the yml carries a
`versions:` block. A list with no tags is a stale registration; tags with no list is
check 1's failure. This is what makes the vacuous-green window honest.

### 1.4 The site selector: generated, not hand-coded

The SDK's front-door selector is hard-coded HTML whose options carry three-component
version literals (`v0.8.0 (latest)`, …) — which is exactly why the SDK needs
`website_version_options` to parse its own website back and fail drift in CI. The
gateway cannot copy that shape, and should not: **`tests/contract/test_website_stamps.py`
refuses any three-component version literal anywhere under `website/`**
(`SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")`, the class-11 ban, `test_source_carries_no_version_literals`)
— a hand-coded selector would REDDEN the existing hygiene pin at the port's own merge.

So the gateway's selector extends its own proven mechanism instead of the SDK's
weakness — the `{{stg-*}}` stamp discipline (`website_stamp_map`/`stamp_website`,
CON-13): `website/index.html` carries a **selector scaffold** — the
`<select class="version-select" onchange="gotoVersion(this)">` with a single
`{{stg-versions}}`-family token placeholder and **zero option rows** — and the
assembly **generates the rows** into the assembly copy from `release_tags()`:

- tagged regime: one row per tag in descending order, the newest labelled
  `(latest)` with value `docs/` (the root serves latest), older tags valued
  `docs/v/<tag>/`, then the final row `dev` valued `docs/v/dev/`;
- zero-tag regime: the single row `dev` valued `docs/` (the root is the current
  tree's build).

This is the SDK's `website/index.html:341-355` option grammar verbatim (values and
labels), with the rows derived rather than typed. `gotoVersion` itself is three
lines in `website/assets/site.js` (the SDK's shape, `site.js:55-57`:
`if (select.value) window.location.href = select.value;`). Fail-closed both
directions, mirroring `stamp_website`: a scaffold without its token refuses (the
selector was hand-edited away), a token the generation cannot fill refuses, and the
existing `{{`-delimiter residue sweep in `verify_tree` covers the new token for free.
CON-13's letter already governs the selector ("claim sites in `website/index.html`
carry `{{stg-*}}` tokens and never [literals]") — no amendment needed; the selector
conforms by construction. The parse-back drift guard becomes an **output** check:
`verify_tree` reads the ASSEMBLED copy's selector and asserts every option value
resolves to a real directory in the tree, and that exactly one row is labelled
`(latest)` iff tags exist (zero such rows in the zero-tag regime — a "(latest)"
label with no releases is a lie).

### 1.5 `verify_tree` — merged arms

The existing gateway arms all survive untouched (static-site files, docs root,
`reference/cli`, `standards/`, the active OTDP runtime schema, changelog page,
pattern pages, `llms.txt`, stamp residue, website link resolution, home links). The
website-link arm extends to `<option value="docs/…">` attributes (options are
values, not hrefs). The versioned arms are conditional on regime, ported from the
SDK's `verify_tree` (`:463-563`): per-tag `docs/v/<tag>/index.html`; `docs/v/dev/`;
both alias stubs; selector honesty (§1.4); no doubled-`v` labels in any
`gd-version-map` meta, `_version_map.json`, or `version-selector.js` copy.

### 1.6 Workflow shape

`.github/workflows/docs.yml` changes exactly twice, both small:

- **Pin the toolchain**: `uv pip install "great-docs[svg]==0.17.0"`. Today the
  gateway installs unpinned; the port adds 0.17.0-specific markup workarounds
  (alias stubs, selector trigger), and an unpinned future great-docs breaking old
  buckets is precisely the SDK's #397 failure class. The SDK's own comment is the
  precedent: "Pinned: scripts/assemble_docs_site.py's markup workarounds are written
  against great-docs 0.17.0 — bump the pin and the workarounds together"
  (SDK `docs.yml:60-63`).
- Comment updates only otherwise: the checkout's `fetch-depth: 0` reason line
  (`refuse_if_tagged` → release-tag detection + bucket sources), the header's
  "unversioned until the first release tag" wording. No new steps, no new tokens
  (no `--from-repo` network builds; submodule fetches use the checkout's existing
  credentials), no trigger or concurrency changes.

---

## 2. The five design questions, answered against the pinned code

**Q1 — Tag-scope discrimination.** Yes, and the port keeps it. The scan is
`git tag --list v*` (glob excludes `ui-html-v*` upstream) filtered by
`TAG_RE = ^v(\d+)\.(\d+)\.(\d+)$` (`scripts/assemble_docs_site.py:90`, scan at
`:419`) — the anchored `^v` cannot match `ui-html-v0.2.1`. The remote carries
exactly `ui-html-v0.1.0/0.2.0/0.2.1` and zero `v*` (measured this session:
`git ls-remote --tags origin`; the local clone matches — the family doc's one-time
shadow-tag cleanup has run). `release_tags()` (SDK `:115-119`) is the same glob +
the same regex; the namespace contract's pin arms (R2, R2b, R3, R4 of
`tests/contract/test_docs_site_refuse_if_tagged.py`) transfer to the new contract
test over the ported scan, injection technique included (synthetic listings at the
`run` helper — xdist-safe, no git subprocess in tests, and downstream-of-the-glob so
the filter is held in isolation).

**Q2 — Pre-tag registration ordering.** What must land before the first `v*` tag:
(a) this port (the whole point — the first cut's readiness condition); (b) at every
release including the first, the `versions:` registration entry committed and merged
BEFORE the tag is pushed, because the tag's own yml is what its bucket build filters
(the v0.0.4 lesson). Machine enforcement: the three checks of §1.3 plus the regime
consistency check — all in the assembly, all failing the docs lane on violation.
Procedural home: the cut procedure in `docs/internal/release-process-family.md`
gains the registration step, and its walk row 3 already carries the stale patterns
("version absent from the selector; registration missing pre-tag").

**Q3 — What serves at the site root.** SDK precedent: the latest stable tag's build
at `docs/`, current-tree content at `docs/v/dev/`, `v/latest` + `v/stable`
redirecting to the `/docs/` prefix. The gateway follows exactly. Divergence, named:
the SDK refuses the zero-tag state outright (`:609-610`); the gateway keeps it alive
serving today's shape (current tree at `docs/`, dev option valued `docs/`), because
the port lands before any tag and its own merge must stay green. The regime switch
is automatic at the first tag.

**Q4 — CI shape and the green-throughout proof.** The docs lane's only tag-sensitive
path today is `refuse_if_tagged` — a refusal that is a no-op on a tag-less repo.
The port replaces it with a scan whose zero-tag branch produces the same tree
through the same calls, so on a tag-less repo the diff is behaviorally inert by
construction; every PR between port-merge and first cut exercises exactly that
branch in real CI (the continuous control). The tagged branch cannot be exercised
by CI before a real tag exists — that window is closed by the fake-tag E2E (§6 A2)
and disclosed as the port's honest gap: the first release's docs run is the first
real-tags CI exercise, and walk row 3 reads it. The workflow's other changes are
§1.6's pin and comments. The builder also re-verifies the PR-lane claim the
mechanical way: the port branch's own CI run IS a tag-less Build Docs run.

**Q5 — Where the versioned build runs, and its cost.** In-job, from the workflow's
existing full-history checkout: per tag, one local `--shared` clone + checkout +
submodule init + one `uv run --project` env (wheels served from the job's shared uv
cache) + one Great Docs build + the tag's own assembly repairs. Cost = one full
assembly per tag per docs run (PR and main alike): zero at port time, +1 at the
first release, linear thereafter — the SDK's #397 cost class (a broken tagged tree
reddens every PR until a fixed release; the SDK's incident was a tag whose tree
referenced a retired page). The gateway accepts the class on the SDK's precedent,
with two structural mitigations already in the design — every bucket is built by
its own tag's own green-at-release script under a PINNED toolchain (so a bucket
breaks only on environmental drift, not on main's motion), and the failure is loud
at the bucket's own `verify_tree` — and one named deferral (D3: bucket caching,
reopen on a measured lane-time trigger). The alternative — building the versioned
overlay only on main — is rejected: PRs must exercise the machinery, or a versioned
regression reddens main instead of the PR that caused it.

---

## 3. The first increment — files, then deferrals

One slice, one PR (gateway repo only; no SDK-side motion — the SDK's implementation
is the port source, not a moving dependency):

1. `scripts/assemble_docs_site.py` — the port: `release_tags`, `yml_version_tags`,
   the three registration checks + regime consistency, the bucket driver
   (clone/checkout/submodule/`uv run --project`/lift), `--bucket` mode with its
   three documented deltas, `bucket_source`/`replace_dir`/`replace_root`,
   `site_path_prefix`/`redirect_page`/`fix_alias_stubs`, selector generation +
   output verification, `fix_version_selector_trigger`, per-bucket favicon copy,
   merged `verify_tree` arms; `refuse_if_tagged` deleted (its docstring's demand is
   satisfied by this port); module docstring rewritten (unversioned-by-design → the
   two regimes).
2. `tests/contract/test_docs_site_refuse_if_tagged.py` → **replaced** by
   `tests/contract/test_docs_site_versioned.py`: the namespace arms survive
   (ui-html-only listings pass and produce no buckets/selector rows; mixed listings
   name only the gateway tag; pre-release-suffixed tags pass; the exact
   `['git', 'tag', '--list', 'v*']` command literal), plus registration-refusal arms
   (all three checks + regime consistency, each with its mutation control), zero-tag
   regime arms, and selector-generation arms (rows from tags, `(latest)` iff tags,
   value targets, token bidirectionality). The refusal pin's namespace contract is
   the load-bearing transfer — a replaced test whose arms die with the old mechanism
   is how the ui-html exclusion gets lost.
3. `website/index.html` — the selector scaffold (token placeholder, zero literal
   rows) · `website/assets/site.js` — `gotoVersion`.
4. `.github/workflows/docs.yml` — the pin + comment updates (§1.6).
5. `great-docs.yml` — header comment update only (the `versions:` key is NOT added;
   §1.3).
6. `docs/internal/release-process-family.md` — readiness condition 1 amended (the
   port has landed; the refusal is retired; the versioned assembly is the mechanism),
   the cut procedure gains the pre-tag registration step, walk row 3 sharpened to
   name the machine checks.
7. `docs/doc-taxonomy.md` row 11 — the class-11 guard list gains the versioned
   assembly arms.
8. `.gitignore` — `/.docs-assembly/` (root-anchored, per the file's own anchored-rule
   lesson at lines 108-110).
9. `README.md` — one sentence where the site is described: docs serve versioned
   per-tag snapshots (`docs/v/<tag>/`) with latest at the root.

**Deferrals** (home uniform: documentation here, in this record's table, except
D1/D3 which name their follow-on homes):

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | Per-bucket pattern-library screenshots (buckets ship the pattern HTML their tag staged; the workflow's capture step remains parent-root-only, so bucket pattern pages render without their PNGs) | follow-on issue (filed at land) | a bucket pattern page is viewed missing its captures — the first consumer report, or the owner's explicit call at the first release walk |
| D2 | `check_docs_links.py` port (the SDK's built-tree link-integrity step; the gateway's `verify_tree` link arms cover website links + selector values meanwhile) | documentation here | a shipped-site link-rot incident on any page class `verify_tree` does not already sweep |
| D3 | Bucket caching (`actions/cache` keyed by tag SHA so repeated docs runs skip unchanged buckets) | documentation here | the Build Docs lane's measured wall time on the first multi-tag release exceeds 2× the port-landing lane time recorded in §6 |
| D4 | The SDK's PR preview-comment job (`great-docs ci pr-comment`) | documentation here | the owner asks for PR docs previews on the gateway tracker |
| D5 | A `--skip-buckets` local-preview flag (the zero-tag regime is the cheap path until the first cut) | documentation here | the first release lands (after which local full assembly costs one build per tag) |
| D6 | Alias semantics beyond `latest`/`stable` (per-major aliases, a `dev` alias) | documentation here | a consumer asks for a stable deep link the pair cannot express |

---

## 4. Invariant and drift impacts

- **CON-13** (version stamps; `docs/internal/invariants.md`, the website-stamps row):
  unchanged — the selector is a new claim site family that conforms by construction
  (tokens in source, values only in the assembly copy, residue sweep covers the new
  token). No amendment needed; the record states the conformance so the next reader
  does not re-derive it.
- **CON-12** (sdk_compatibility authority chain): untouched — `stg-sdk` stamping is
  unchanged and remains current-tree-only.
- **The tag-namespace contract** (the refusal pin's docstring): TRANSFORMS, not
  dropped — `ui-html-v*` must never be treated as a gateway release tag (no bucket,
  no refusal, no selector row). Its arms move with the mechanism into the new
  contract test (§3 file 2). This is the one invariant-bearing motion of the slice.
- **CTL/STO/REG**: none touch the docs site (verified against the invariants doc's
  groups; the docs-site rows are the CON-13 family only).
- **Standards tripwire**: `git diff origin/main...HEAD -- standards/` stays empty —
  the port reads each tag's corpus, moves no standards bytes; the
  standards-governor mandate is NOT triggered (no `standards/`, no SDK vendored tree,
  no standard-version strings — selector labels derive from gateway release tags,
  and `{{stg-*}}` stamps are untouched).
- **On-disk formats / schemas**: none — site output is build output (gitignored),
  not a persisted format; the Tier-3 trigger here is the keyword rule, not a format.
- **Drift obligations walked** (`docs/internal/drift-and-obligations.md`): the
  website token-motion row (mechanism unchanged, extended by the selector token);
  the standards-cli capture row (buckets regenerate the page from the tag's own
  `--help` — per-tag CLI verbs are the tag's own, strictly better than any
  current-tree render); the CI map row for the docs lane (shape unchanged).
- **CI cost**: zero new lanes; the docs lane's cost grows by one assembly per
  release tag per run (§2 Q5), mitigated structurally (§2 Q5) and by D3.

## 5. Review tier and the Step-1 keyword scan (#254)

**Tier 3** — keyword rule, first match: the expected diff text contains
`subprocess` (the port's `probe`/`run-ok` helper for `git cat-file -e` existence
checks and `git show <tag>:great-docs.yml` reads — returncode-semantics calls the
raising `run()` helper cannot express — plus the tier statement itself in this
record, which is part of the diff). Scan over the whole expected diff (this record +
the nine files of §3), keywords and counts:

- over this record's own text, excluding this scan-result list itself (it names
  every keyword once by construction — the rubric's interplay note about rule text
  self-firing extends to the tier statement): `subprocess` 2 (the §2 Q1 injection
  note; this section's trigger sentence), `threading` 0, `asyncio` 0, `sha256` 0,
  `hashlib` 0, `migrate` 0, `recovery` 0, `protection` 0
- over the expected code half of the diff (the nine files of §3): `subprocess`
  expected 2-3 (the `probe` helper's body — new git invocations otherwise go
  through the existing raising `run()` helper, which adds no keyword occurrences),
  all other keywords expected 0 — final counts restated by the builder over the
  real diff, as the rubric's independent re-derivation requires

Path rules alone would say Tier 2 (`scripts/`, `tests/`, `.github/`, website
assets); the keyword fires first. Consequences the slice accepts: two independent
adversary lanes (the Tier-3 standing), the cold full suite (also forced by the
`.github/workflows/` change), G6 cross-vendor comparison.

## 6. Acceptance rule — pre-committed

Written before any measurement below was run. All arms are deterministic
file-presence/HTML-content assertions on assembled trees; "sample size" is therefore
a determinism check, not a statistical one: **every E2E arm runs twice on
independent fresh clones**; disagreement between runs is an UNEVALUATED verdict, not
a pass. The fake tag is `v0.4.0` (the owner ruling's example number; the mechanism
is number-agnostic).

- **A1 — tag-less repo unchanged.** On the real repo (zero `v*` tags), run the
  ported assembly twice. SHIP iff: `site/docs/` contains no `v/` directory; the
  assembled selector is exactly one `dev` option valued `docs/`; every existing pin
  is green (`test_website_stamps`, `test_docs_site_standards_cli`,
  `test_assemble_docs_site`, the zero-literal scripts scope, ruff, fresh-cache
  mypy); and the docs-tree file set equals the pre-port assembly's file set (diff
  the two manifests — timestamps excluded). KILL iff any new path appears under
  `docs/` or any existing pin reddens.
- **A2 — fake-tag E2E.** Scratch clone of the repo; commit a `versions:`
  registration (`v0.4.0`, `latest: true`) on a scratch branch; tag `v0.4.0`; run
  the assembly. SHIP iff the output tree has `docs/v/v0.4.0/index.html`, the
  `docs/` root file set equals the bucket's, `docs/v/dev/index.html`,
  `v/latest/` + `v/stable/` redirects targeting `/docs/`, the assembled selector
  rows are exactly [`v0.4.0 (latest)` → `docs/`, `dev` → `docs/v/dev/`], and no
  `vv` label exists in any `_version_map.json` or `version-selector.js`. KILL iff
  any named artifact is missing or the root is not the bucket's content.
- **A3 — registration refusals, RED first.** Two scratch clones: (a) tag without
  registering — the assembly refuses naming the tag; (b) register in the current
  tree but tag a commit whose own yml lacks the entry — the assembly refuses
  naming the tag-self-registration rule. RED control: with each check's code
  reverted in place (test kept), the corresponding arm fails to refuse — the
  unproven-guard failure. KILL iff any refusal cannot be shown RED-then-GREEN.
- **A4 — namespace discrimination, E2E.** Scratch clone carrying
  `ui-html-v0.2.1`-class tags and no `v*`: assembly is green, zero buckets, zero
  selector rows beyond `dev`. Same clone plus fake `v0.4.0`: exactly one bucket,
  selector rows per A2, refusal nowhere. KILL iff any ui-html tag yields a bucket,
  a selector row, or a refusal.

**Underpowered/unevaluated clause:** any arm that cannot execute end-to-end (docs
toolchain, Quarto, network for submodule/index resolution unavailable) is
UNEVALUATED — the acceptance fails closed; local reasoning cannot mark an arm green.
Measurements are the builder's, recorded on the tracking issue; nothing in this
record was measured beyond the tag inventories and file reads cited.

## 7. Top risks, each with its falsifier

- **R1 — Great Docs `--versions` semantics for a guide-only config** (the gateway is
  `reference: false`; the SDK's filtered builds all carried API references).
  Falsified or confirmed by A2 directly; the fallback is flat-build-then-place,
  which `bucket_source`'s two-shape tolerance already covers.
- **R2 — per-tag environment resolution** (`uv run --project` against each tag's
  lock; resolver or index flake in CI). Falsify: the port branch's CI + A2 timing;
  the shared job-level uv cache is the mitigation.
- **R3 — submodule SHA availability at old tags** (a bucket needs the `packages/sdk`
  gitlink its tree pins; an unreachable SHA reddens every docs run — the accepted
  #397 residual). Falsify: the first multi-tag release's CI; no cheap mitigation
  exists short of vendoring, which the two-repo discipline forbids.
- **R4 — great-docs 0.17.0 markup drift** (the alias-stub and selector-trigger
  workarounds are written against its exact output; the pin holds the version, and
  the drift WARNs hold the detection). Falsify: any great-docs bump — pin and
  workarounds move together, per the SDK precedent comment.
- **R5 — the zero-tags CI gap**: between this port's merge and the first cut, real
  CI never exercises the tagged path (A2's fake tag is the only end-to-end
  evidence). The first release's docs run is the first real exercise; walk row 3
  reads it. Falsify: nothing — this is a disclosed window, not a claim.
- **R6 — a stray pre-port `v*` tag on the remote** (shadow-tag push): pre-port it
  bricked CI via the refusal; post-port it is refused by the registration checks
  (an unregistered tag cannot build) — same loudness, different message, no silent
  wrong publish. The family doc's tag rules remain the outer defense.

## 8. Owner forks

- **F1 — the dev-only selector on the live front door.** The port ships the selector
  scaffold now with a single `dev` row (it must exist before the first tag, or the
  first release introduces two changes at once). Alternative: hide the scaffold
  until the first tag (site.js or CSS). Recommendation: visible — one honest option
  is the truthful state of an unreleased site.
- **F2 — the linear CI cost.** Accept (this design, with D3) or require bucket
  caching in-slice. Recommendation: accept — the trigger is measured and named.
- **F3 — the toolchain pin rides this slice.** The great-docs pin is a workflow
  behavior change bundled with the workarounds that need it (SDK precedent: pin and
  workarounds move together). Alternative: a separate micro-PR first. Recommendation:
  bundled — an unpinned port ships its own #397 exposure.
