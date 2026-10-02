# Issue #224 — Slice 2: catalogue and search on the public website — design record

**Status:** Design (builder-ready) · **Tracking:** madeinoz67/benchweave#224 (sub-issue of #209, slice 2 of 6)
**Authority above this record:** `docs/implementation-planning/10-contributor-publishing-design.md` §3.4 + §4 "Slice 2" + §5 (CON-13 amendment text) — the acceptance with kill directions lives there and is restated verbatim in §5 below; `docs/implementation-planning/07-contributor-publishing-prd.md` §9 rulings (Q1–Q21) are fixed parameters, especially Q5 (published-releases-only catalogue), Q7 (static client-side search over one generated JSON index), Q8 (catalogue is the single public advisory point; origin status/lifecycle files remain the mechanism).
**Evidence baseline:** gateway `main` at `3f4ad11` (read in the primary checkout); registry repository `origin/main` at `c38e7f5` (read via `git show origin/main:` — the local clone's `main` is stale at its initial commit; every registry citation below is a committed-byte citation). Registry slice 1 (#223) is merged: `index.json`, `scripts/generate_index.py` with `--check`, `records/index.schema.json`, `.github/workflows/records.yml`, and the dogfooded DPS-150 release all exist. Every number below carries its denominator. Shapes marked *Direction (non-binding)* are refinable by the builder; everything else is load-bearing.

**Verdict up front: BUILD.** The premise holds, with two evidence-based corrections to the design record's own sketch, both recorded in §1.2 because they change mechanism, not scope: (1) slice 1 already built the index generator and its `--check` arm, so slice 2's registry half is the *sync workflow, the mirror-drift refusal, and the generator's yank arm* — not the generator; (2) the panel's generated markup must be **committed**, not assembly-injected, or B2's third plant is vacuous — there would be no committed panel markup to hand-edit and tamper-pin.

---

## 1. Problem, restated from code

### 1.1 What exists (verified this session)

**Registry repository** (`benchweave-registry`, `origin/main` `c38e7f5`):

- `index.json` — one generated row today, the dogfooded DPS-150 release; row shape settled by `records/index.schema.json` (`additionalProperties: false`, 22 required row fields: `registry_id, package_id, version, kind, publisher, manifest_sha256, signature_state, timestamp, timestamp_recommended, display_name, summary, licence_spdx, compatibility{otdp_versions, adapter_api_versions, stg_versions}, evidence[], maintenance, advisories[], capabilities{network_egress, subprocess_or_native_library, filesystem_writes_beyond_evidence_retention}, transport_triples[], source_revision, gateway_ref, firmware_attestation, unverified_markers[]`).
- `scripts/generate_index.py` — pure/offline over `records/` + `releases/`; walks `releases/<registry-id>/<publisher>/<plugin>/<version>/manifest.json`; folds slice-1 review fixes (path identity, signed-submission reconciliation, duplicate rows); `--check` refuses drift with `index_drift:` — the CR-21 self-consistency arm **already shipped**. Its module docstring: "the website slice RENDERS this index and never reshapes it."
- `.github/workflows/records.yml` — `validity` job (validate_records + `generate_index --check` + pytest) and a `drift` job that only **warns** when `gateway-ref` falls behind gateway main. The #223 owner rework removed publish-time replay/enumeration gates: "the registry STATES AND ADVERTISES — it does not enforce admission at publish time."
- `AGENTS.md` §2: "A later slice that adds the website/catalogue UI CONSUMES this index and renders it; it never reshapes the records schema or the index format." §4 hard-binds the web surface to the gateway's `docs/internal/public-site-styleguide.html`.

**Gateway** (`main` `3f4ad11`):

- `website/index.html` — five panels (`panel-home|standards|docs|sdk|builtwith`), nav buttons switched by `showPanel`, hash deep-links via `PANEL_INDEX` in `website/assets/site.js:3` (`{home:0, standards:1, docs:2, sdk:3, builtwith:4}`). Standards panel renders spec-cards whose badges/hrefs carry one `{{stg-*}}` token twice.
- `scripts/assemble_docs_site.py` — `copy_website` (copies `website/` wholesale to the artifact root, so a mirror placed under `website/` rides along with zero new assembly code), `stamp_website` (assembly-copy-only substitution; bidirectional fail-closed coverage `stamp_unmapped_token:`/`stamp_unused_key:`), `verify_tree` (sweeps **every** copied static-site file for `{{` residue, probes required files, resolves every relative `docs/` link).
- `tests/contract/test_website_stamps.py` — the guard class this slice extends: T2 `_class11_literal_hits` refuses `\d+\.\d+\.\d+` over **every file under `website/` plus `index.qmd`**; `_website_brace_violations` refuses any `{{` outside well-formed tokens in `index.html`; tamper arms (T5a–d, F1 vehicles) operate on copies, never the committed source.
- `docs/internal/invariants.md` CON-13 (website stamps are a pure function of committed state), CON-12/CON-4 amendment ("the mirror is a derived copy whose authority stays with the lock" — the `sdk_compatibility` precedent this slice follows), CON-4's two-sided `make check-sdk-standards`.
- `.github/workflows/docs.yml` — installs Playwright chromium (the #300 pattern-library precedent for browser verification in the docs lane).
- `standards/registry/0.1.1/release-status.schema.json` — the served `status.json` `lifecycle` enum: `published | deprecated | yanked | revoked`.

### 1.2 What is missing, and two corrections to the sketch

Missing entirely: any gateway mirror of `index.json`; any Plugins panel; any search; the sync path; the two-sided drift refusal; the CON-13 amendment; the honesty-sentence update (the "Where it stands" text still says "the registry service … do not exist" — true of a *service*, stale about the repository of record slice 1 created).

**Correction 1 — slice 2's registry half is narrower than §3.4 reads.** The index generator, its schema, and the local `--check` falsifier are slice-1 landed bytes. Slice 2's registry side = (a) the generator's **yank arm** (see §2.3 — today a yank changes nothing in the index: the generator reads `status.json` only for `advisories` and collects only `op == "publish"` lifecycle records, so a yanked release's row would survive a refresh, which would fail B1's yank arm and CR-25's "no stale rows survive a yank"), (b) the **sync workflow**, (c) the **mirror-drift refusal**.

**Correction 2 — the panel block is committed generated markup, not an assembly-time injection.** §3.4 sketches "rendering at assembly from the committed mirror," and §5's amendment says "renders at assembly from a committed generated mirror." But acceptance B2's third plant is "hand-edited panel markup (render guard red)," and §3.4's own gate sentence is "the panel render test regenerates the panel markup from the committed mirror and byte-compares — a hand-edited mirror row **or hand-edited panel row** is refused." One test can catch both plants only if there is committed panel markup to compare against; an assembly-only render has no committed markup, and a hand-edit to the renderer's template is self-consistent by construction. So the panel's rows live as a **generated block inside `website/index.html` between machine markers**, rewritten by a committed regen tool with `--check` — exactly the git-cliff CHANGELOG discipline this repo already runs (machine-rendered committed file, regenerate-don't-hand-edit). "Renders at assembly" is satisfied in substance: the catalogue the assembled site serves is the committed generated mirror rendered through committed generated markup — no runtime service, no runtime catalogue fetch beyond the static JSON. The amendment text in §4 below is worded to the mechanism as built.

### 1.3 The constraint that shapes everything

`test_website_stamps.py` T2 scans **every file under `website/`** for three-component version literals. The mirror — a byte-copy of `index.json` — necessarily carries them (`"version": "0.1.0"`, `"otdp_versions": ["0.2.2"]`). The design record already ruled the resolution: "the gateway's `website/plugins-index.json` mirror is class 11 with its generator named." This slice implements that as a **one-file, named-generator exemption** in the hygiene arm, pinned closed by three independent gates (§2.4) so the exemption cannot launder a hand-edit — the same argument #188's fold F2 used, inverted for a derived surface with a motion mechanism: hand-stamped claims no train moves are defects; the mirror's contents are moved by the sync train and byte-pinned against the authority.

---

## 2. The mechanism

### 2.1 Gateway: the committed mirror, the pin, the generated panel block

**Files (new):**

- `website/plugins-index.json` — the mirror. A **byte-identical copy** of the registry repository's `index.json` (canonical bytes; never hand-edited; class 11, generator = the registry's `scripts/generate_index.py`).
- `website/plugins-index.ref` — one line: the registry-repository commit SHA the mirror was synced from. The gateway-side authority anchor (the CON-12 gitlink-pin shape: compare against an *immutable pinned ref*, not a moving branch — this keeps every gateway PR offline-deterministic and immune to the sync window).
- `scripts/website/render_plugins_panel.py` — the renderer/regen tool (new `scripts/website/` home; stdlib only: `json`, `re`, `argparse`, `pathlib` — it must run inside the registry repo's sync workflow from a bare gateway checkout). Three modes: `render_panel_rows(mirror_bytes) -> str` (pure), `--write` (rewrites the block between the markers in `website/index.html`), `--check` (refuses drift with `panel_drift:`). Fail-closed properties: unknown `kind`, an unparseable mirror, or output containing `\d+\.\d+\.\d+` or `{{` refuses with machine prefixes (`panel_input_invalid:`, `panel_literal_refused:`, `panel_braces_refused:`) — the class-11 ban holds at *generation* time, not only test time.
- `website/assets/plugins.js` — vanilla, no build chain, no dependencies. Split in two: a **pure predicate** `filterRows(rows, query)` (data in, data out, no DOM; exported to CommonJS behind a `typeof module` guard so node can require it — one line, no toolchain) and the DOM wiring (fetch `plugins-index.json` same-origin; decorate each committed row's version/compat/digest slots from the row data; drive the filter controls; render non-default rows on demand; result count; honest empty states). On fetch failure the committed static rows stand untouched and a small inline notice appears — loud degradation, never a blank panel.

**The generated block** inside `website/index.html`:

```
<!-- bw:plugins-panel begin (generated from website/plugins-index.json by
     scripts/website/render_plugins_panel.py — regenerate, do not hand-edit) -->
…rows…
<!-- bw:plugins-panel end -->
```

**Default-view rule (CR-22, load-bearing):** the static block contains exactly the rows with `kind == "admitted-release"` AND `signature_state == "signed-valid"`. Everything else (`unsigned`, `in-tree-fixture`, `community-shared` — the kinds slice 5 will populate) is absent from the static bytes and reachable only through explicit client-side filters, which render them **with their kind tag** (CR-56: never rendered without the tag). In-flight submissions are structurally absent everywhere: the index is generated from `releases/` and a submission only becomes a release at publish. When the index has zero default rows the renderer emits an honest-empty sentence ("No published releases yet") — never an empty panel.

**Seven contract fields per row (CR-20 — "rendered or explicitly 'none'"):** publisher (mono, static); immutable release id — `registry_id` + `package_id` (static) + version and the manifest digest (JS-filled from the index; digest truncated with the full value in the `title` attribute); compatibility — otdp/adapter/stg version lists (JS-filled, verbatim per CR-19, no re-derivation); licence/provenance — `licence_spdx` + `source_revision` as a GitHub tree link at that revision (static text, data-driven URL); test evidence — level+result badge + `report_path` (mono, static) + link to the registry repo's release directory; maintenance — badge (`badge-success` maintained / `badge-warning` maintenance_only / `badge-danger` unmaintained / muted unknown); advisories — `badge-danger` per advisory id, or the explicit "no advisories". Unverified markers (CR-37/NFR-S1) render as fixed badge-warning strings via a committed marker→display map (the two slice-1 markers), and any **unknown** marker id renders verbatim — forward-honest, never dropped. The no-JS degradation shows the static subset (fewer fields, none false) — stated, accepted, progressive enhancement.

**Panel scaffolding (hand-written, outside the markers):** `<section class="panel" id="panel-plugins">`, page-head (h1 "Plugins", lede naming the registry repository of record and stating the honesty posture), the filter bar, the result-count line, and the empty-state slots. Nav gains a sixth button "Plugins" — *Direction:* second position (`PANEL_INDEX` becomes `{home:0, plugins:1, standards:2, docs:3, sdk:4, builtwith:5}`; the DOM button order must agree — `openFromHash` indexes buttons by position). Rationale: the catalogue is the site's primary "find a plugin" surface; the builder may re-order with the PANEL_INDEX agreement as the only constraint.

### 2.2 Gateway: the styleguide constraint (owner-hard)

The panel renders **only** against `docs/internal/public-site-styleguide.html` tokens and the site's existing `styles.css` implementation of them — no new colors, fonts, radii, shadows, or a fourth font family; sentence case throughout including badges; Lucide available but not required here (deferred, D-S2f-adjacent).

- Rows reuse the standards panel's idiom: `spec-grid` + `spec-card`, `badge badge-version|badge-success|badge-warning|badge-danger|badge-info`, `mono` for values, `text-muted` small/13.5px body — all existing classes.
- **Two new component shapes, both token-only extensions, both declared here per the styleguide's "say so rather than improvising" rule:** (1) a **filter bar** — text input + `select` controls styled from `--bg-inset`, `--border`, `--radius-sm`, IBM Plex Sans, with the accessibility floor's 2px Signal Blue `:focus-visible` ring; (2) a **catalogue meta line** on each card — mono 13px publisher·licence·maintenance run. One small CSS block is appended to `styles.css` using exclusively existing custom properties; both themes come free because every value is a theme variable (the styleguide's dark-first/light-parity principle).
- The styleguide's **"Registry isn't here yet" sub-brand hold is binding**: no Registry stack-glyph mark, no `registry.benchweave.dev` shape, no "registry service" language — the panel is a page of the main site under the standard wordmark, because what exists is a git-native repository of record, not a hosted service (CR-23/B3).

### 2.3 Registry: the yank arm, the sync workflow, the mirror-drift refusal

**Generator yank arm** (`scripts/generate_index.py`, behavior extension — zero format motion): when a release directory carries `status.json` with `lifecycle ∈ {yanked, revoked}` (the vendored `release-status.schema.json` enum), the row is **dropped** — "gone", the design record's own alternative ("flagged-or-gone"), chosen because the index schema is frozen (`additionalProperties: false`, and the registry constitution §2 forbids this slice reshaping the format) and because gone is the strongest honest reading of CR-25 ("no stale rows survive a yank or unlist") — a yanked release is already refused at admission, so discovery must not offer it; the record and git history retain it (CR-32's floor is history, not the catalogue). Absent `status.json` or `lifecycle: published|deprecated` → row present (today's dogfood, unchanged). `status.json` is the single authority for this read — it is the same origin state file stock gateways consult (Q8: "origin status/lifecycle files remain the mechanism"); if slice 3's lifecycle ops ever write records without updating the served `status.json`, reconciling that is slice 3's C2 problem, named here so it is not rediscovered.

**Sync workflow** (`.github/workflows/sync-index.yml`, new): triggers on pushes to main touching `records/**`, `releases/**`, `index.json`. Steps: regenerate in-place and assert `--check` green → checkout the gateway repo at its default branch → write `website/plugins-index.json` (the fresh canonical bytes) → run the gateway's own committed `scripts/website/render_plugins_panel.py --write` from that checkout (dependency-free by design) → write `website/plugins-index.ref` = the registry commit SHA → commit all three to the fixed branch `sync/plugins-index` (force-push; one open sync PR at a time) → open/refresh the gateway PR via `gh` authenticated by a `GATEWAY_SYNC_TOKEN` repository secret. **No secret configured → the job fails loudly** (`sync_token_absent:`), never skips; the documented manual path (run the same three commands from a maintainer checkout) is the fallback, and the mirror-drift refusal below keeps registry main red until a sync lands — the honest intermediate the design record already accepts ("a red drift gate is the honest intermediate — degrade loudly").

**Mirror-drift refusal** (`records.yml`, new `mirror-drift` job — **push to main only**, never `pull_request`: during any records PR's review the gateway mirror is necessarily behind, so a PR-scoped arm would be red on every correct submission): regenerate the index in memory, fetch the gateway mirror's main bytes raw (`https://raw.githubusercontent.com/madeinoz67/benchweave/main/website/plugins-index.json` — CI has network; the *site* never does), byte-compare, refuse `mirror_drift:` on mismatch or fetch failure (one retry; a network failure is indistinguishable from a missing mirror — fail closed). This is the registry-side half of "a records change without regeneration fails CI both sides," and it is the arm that catches a *coherent* gateway-local hand-edit of mirror + panel together (the one edit class the gateway render guard cannot see). Detection is asynchronous — it fires on the next registry push — and the gateway-side authority pin (§2.4) closes the synchronous half.

### 2.4 The three gateway-side gates (and where they run)

1. **Render guard** (pytest, fast lane + full battery): the committed block in `website/index.html` byte-equals `render_panel_rows(committed mirror)`. Catches: hand-edited panel row, hand-edited mirror row *that changes rendered content*. Refusal `panel_drift:`. Plus the block-shape pins: no `{{` in the block, no three-component literal in the block, marker pair present exactly once.
2. **Authority pin** (CI step in the `gates` job — network, fail-closed): fetch `https://raw.githubusercontent.com/madeinoz67/benchweave-registry/<SHA from website/plugins-index.ref>/index.json` (a commit SHA is immutable; contrast CON-12's gitlink pin) and byte-compare against the committed mirror; refuse `mirror_authority_drift:` on mismatch, on a 404 (a rewritten or mistyped ref), or on fetch failure. Catches synchronously, at every gateway PR: a hand-edited mirror (even a non-rendering field), a mirror advanced without its pin, a pin advanced without its mirror.
3. **Class-11 exemption + controls** (pytest): `_class11_literal_hits` in `tests/contract/test_website_stamps.py` excludes exactly `website/plugins-index.json` (a named `GENERATED_MIRROR` frozenset with the generator named in a comment — the registration). Control arms pin the exemption's boundary: a planted `\d+\.\d+\.\d+` in any other website file — **including inside the panel block** — still reddens T2; a planted literal in the exempted file's *neighbor* (`plugins-index.ref`, which legitimately carries no versions) still reddens.

Together with the registry-side `mirror_drift:` these make the mirror/panel/ref triple a lockstep lattice in the CON-4 sense: any PR that touches fewer than all three files it needs (or touches one inconsistently) reddens on at least one side. Tool-version skew self-heals: the sync workflow renders with gateway main's tool, and the gateway PR's render guard re-verifies with the PR tree's own tool — a mismatch reds and regeneration follows.

### 2.5 Search: the pure predicate, the truth table, the two proof lanes

CR-24's dimensions — name, publisher, device class/capability, standard version, status — plus CR-58's kind, all against the settled row fields:

- **name** — substring (case-insensitive) over `display_name` + `package_id` + `summary`;
- **publisher** — exact facet over `publisher` (distinct values from the index);
- **device class/capability** — the index carries **capability declarations** (the CR-45 booleans), not device class; this slice reads CR-24's "device class/capability" as the capability facet (three boolean filters), stated here as the accepted reading because the frozen index has no device-class field (deferred D-S2a with the reopen trigger);
- **standard version** — facet over the distinct values of `compatibility.stg_versions` ∪ `compatibility.otdp_versions` (rendered labeled by family; verbatim values, no re-derivation — CR-19);
- **status** — facets over `signature_state` (signed-valid/unsigned), `maintenance` (four values), advisories (present/none). Yanked/revoked is not a status facet — those rows do not exist in the index (§2.3);
- **kind** — facet (default: admitted releases only; "all kinds" opt-in reveals tagged non-default rows).

**Truth table first:** `tests/contract/fixtures/plugins-index.fixture.json` — a 10-row synthetic index (CR-24's own denominator), invented names only (e.g. publishers `northwind-instruments`, `copperleaf-labs`, `harborline-systems`), covering: 3 publishers; kinds admitted-release ×7, community-shared ×2, in-tree-fixture ×1; signature signed ×8 / unsigned ×2; all four maintenance values; stg_versions {1.4, 1.5} and otdp_versions {0.2.1, 0.2.2} spread; all eight capability boolean combinations across ≥3 rows; advisories on ≥2 rows; two rows sharing a publisher and name prefix (disambiguation arm). `tests/contract/fixtures/plugins-search.truth-table.json` — hand-derived **before any search code is written**: for every dimension arm, the query and the exactly-expected set of package ids; plus a nonexistent query → ∅; plus one combined-query arm. Committed first, and validated for internal consistency (every expected id exists in the fixture) by its own test — the C1 "hand-derived truth table committed first" discipline.

**Lane 1 — predicate proof (node):** `tests/contract/run_search_spec.mjs` requires `website/assets/plugins.js` (the CommonJS guard export), runs the pure `filterRows` over the fixture against the full truth table. Driven from `tests/contract/test_website_plugins_search.py`, which asserts node's presence and **fails loudly if node is missing** (never skips — a skip would be a silent hole); node is preinstalled on the GitHub-hosted ubuntu runner (the standing no-self-hosted-runners posture keeps that true). This is the design record's "small vanilla search test": no framework, no npm, seconds of CI.

**Lane 2 — wiring proof (browser, docs lane):** post-assembly in `.github/workflows/docs.yml` (the #300 pattern-screenshot precedent — chromium is already installed there): serve the assembled `--dest` with `python -m http.server` (a static file server **is** the static deploy; "no service" means no search backend, B4/CR-26), then with Playwright: (a) the static default rows are present in the served DOM before/without JS decoration; (b) a matching query keeps the real dogfooded row and a non-matching query empties the list with the honest-empty state; (c) the only network request search issues is the same-origin `plugins-index.json` (scoped assertion — the page's unrelated star-count fetch to the GitHub API is pre-existing and out of scope). Dimension breadth is lane 1's job; lane 2 proves the wiring on the real assembled artifact with the real mirror.

### 2.6 Honesty sentence (CR-23)

The home panel's "Where it stands — Next" paragraph currently claims "the registry service and a device-install command do not exist." Updated to state exactly what exists after this slice: a git-native registry repository of record with published, signed releases, whose generated catalogue this panel renders; **no hosted registry service**; installation remains local admission (REG-3 — publication never authorizes control). The panel's own lede carries the same posture. The exact sentence is string-pinned by the B3 arm so a future drift back to a service claim reddens.

---

## 3. Minimal first increment

**One slice, two PRs, one landing order** (linked issue #224 on both; the `registry` label per the family taxonomy):

**PR A — gateway** (`feat/issue224-plugins-catalogue`): `website/plugins-index.json` + `website/plugins-index.ref` (bootstrapped by the documented manual sync commands from the registry commit named in the PR body — the bootstrap *is* the acceptance's observed sync executing the identical command path the workflow will run); `scripts/website/render_plugins_panel.py`; the panel block + scaffolding + nav + `PANEL_INDEX` + `website/assets/plugins.js`; the `styles.css` token-only block; the T2 one-file exemption + controls in `test_website_stamps.py`; `tests/contract/test_website_plugins_panel.py` (render guard + plants + shape pins + honesty arms); the fixture + truth table + node spec + pytest wrapper; `verify_tree` probes for `plugins-index.json` and `assets/plugins.js`; the `gates` authority-pin step in `ci.yml`; the browser arm in `docs.yml`; docs amendments (§4).

**PR B — registry** (`feat/issue224-catalogue-sync`): the generator yank arm + its tests (fixture release trees with `status.json` lifecycle ∈ {yanked, revoked, published, absent}); `.github/workflows/sync-index.yml`; the `mirror-drift` job in `records.yml`; the manual-sync documentation (README or AGENTS appendix — the registry repo's own home for it).

**Order:** PR A first (the mirror must exist and be byte-correct before the drift arm can compare against it), PR B second. PR B's own merge is a scripts/workflows-only change — `generate()` output is unchanged, so its `mirror-drift` run is green by construction; the first *records*-touching event after that exercises the autonomous sync path (named a post-merge watch item in §5, not a gate).

**Explicitly deferred (each with its carrier and reopen trigger):**

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| D-S2a | Device-class as a search dimension (index carries capabilities only; a device-class facet needs an index v2 field — a format motion this slice is forbidden) | This record §2.5; the frozen `records/index.schema.json` | The first index-format train that adds a device-class field, or slice 5's kind work if it needs one |
| D-S2b | Per-row detail surface (dialog/subpage with transport triples, capability table, firmware attestation) — everything CR-20 names renders in-row today | This record §2.1 | Row-density feedback from a real catalogue (>15 rows), or the first publisher asking for it |
| D-S2c | Deep-linkable search state (query params in the URL hash) | This record | The first user request or analytics evidence of shared searches |
| D-S2d | Auto-merge of sync PRs (bot-merged when green) — default stays the owner's merge-on-green human flow | This record §2.3 | Owner call, if the honest-red window proves annoying in practice |
| D-S2e | Registry-side scheduled staleness sweep (a cron `mirror-drift` run catching a stale mirror without waiting for the next registry push) | This record §2.3 | The first observed stale-mirror incident, or slice 5's higher traffic |
| D-S2f | Icons in the panel (Lucide is the approved set; the panel ships text-only) and any a11y work beyond the floor (labels, focus rings, contrast — all in scope; screen-reader audit beyond that is not) | This record §2.2 | The first a11y audit or a design pass that wants them |
| D4 (design §6, restated) | Website-claims posture: no unverified claim renders — `unverified_markers` ride every row (CR-37); this is **in scope**, listed to close the issue's deferral pointer | CR-37 + the renderer's marker map | N/A — implemented, not deferred |

Not deferred because they do not belong to this slice: management surfaces, lifecycle CLI, yank *tooling* (all slice 3, #225); response reach (slice 4, #226); community-shared *records* (slice 5, #227 — the kind already renders correctly if such rows appear).

---

## 4. Invariant and governance impacts

**Standards bytes: none.** Both PRs run the tripwire (`git diff origin/main...HEAD -- standards/` empty, no version-string touches). The gateway touches no `src/benchweave/` package, no fixture lattice path, no schema.

**CON-13 amendment (append-with-evidence, lands in PR A beside the mechanism):**

> Amendment (2026-10-02, issue #224, parent #209): the plugin catalogue panel is a sixth website panel whose rows are a **committed generated block** in `website/index.html` (machine-delimited, rewritten only by `scripts/website/render_plugins_panel.py`), rendered from the committed mirror `website/plugins-index.json` — a byte-copy of the registry repository's generated `index.json`, whose authority stays with that repository's generator (the CON-4 `sdk_compatibility` derived-copy precedent). The mirror and its pin `website/plugins-index.ref` are class 11 with their generator named; the mirror is the **one** file exempt from the class-11 literal scan (a derived surface with a motion mechanism — the sync PR), and the exemption is pinned by three gates: the render guard (`panel_drift:` — panel block equals render(mirror)), the authority pin (`mirror_authority_drift:` — mirror equals the registry index at the ref's commit), and the registry-side refusal (`mirror_drift:`). Versions and digests render from the served index client-side — no three-component literal exists in the panel block or in any non-exempt website file, and the panel block carries no `{{` at all (both pinned; the residue and token-grammar guards extend to the block by exactly this means). A records change without regeneration fails CI both sides: registry-side regenerate-and-compare against the committed index and the gateway mirror's main bytes, gateway-side the render guard over the committed mirror.

**Taxonomy amendment (class-11 row / rule 6, append):** the catalogue mirror, its pin, and the generated panel block are class-11 **generated** artifacts (generators named: the registry's `scripts/generate_index.py`; `scripts/website/render_plugins_panel.py`) — derived copies whose authority stays with the registry repository's generator, not a second home for the registry's records (rule 6's "renders, does not copy" reads them as presentation inputs, the `sdk_compatibility` shape).

**Obligation 18 registration (new clause, PR A):** the plugin-catalogue mirror + pin + generated panel block — derived; motion mechanism: the registry sync PR (regenerate → mirror + ref + panel block in lockstep); gates: render guard + authority pin gateway-side, `mirror_drift:` registry-side. This satisfies 18's closing clause ("a new version-bearing literal anywhere is a defect — make it a derived surface or register it here with its motion mechanism").

**REG-5 clause turning true:** "the generated index is never hand-edited on either side" (design §5, slice-1 row with clauses becoming true per slice) becomes mechanically true this slice — the three gates above are the evidence.

**Untouched, and why:** CTL-1..9 and STO-1..6 (no control or store path changes anywhere — both PRs are website/CI/tooling); CON-1/2/5/6/8..12 (no corpus, interface, transport, or matrix motion); REG-1..4 (no registry-package code path); CR-13 (no admission semantics; the yank arm changes what the *catalogue* offers, never what admission enforces — stock gateways already refuse yanked releases at `admission.py`'s lifecycle gate).

**Surfaces that move:** MCP tools — none; REST/OpenAPI — none; CLI — none (no gateway CLI surface; the SDK repo is untouched by this slice); operator docs — none beyond the invariants/obligations/taxonomy amendments; device-developer guide — one sentence pointing plugin authors at the catalogue panel (the CR-33 adoption-guidance seed; the full guidance is slice 3's); vendored standards — zero bytes; fixture lattice (`fixtures/registry/`, `catalogue.json`, `scripts/registry/`) — untouched (the new script deliberately lives at `scripts/website/`, which is *not* the lattice path, and the fixture + truth table live in `tests/contract/fixtures/`, outside every literal gate's denominator); the version-literal counter's **scripts-scope census** gains the new `scripts/website/` files (a visible same-commit census refresh, obligation 20's own mechanism — the files carry zero literals, so no register rows).

**On-disk formats/schema:** the gateway mirror is a byte-copy of an existing generated format (no new format); the pin file is a one-line text file; no persisted gateway state. The registry's index schema is untouched. **This is therefore Tier 3 by keyword, not by the format rule** — see §6.

**CI cost:** gateway — ~18–24 pytest arms (seconds, fast + full lanes), the node spec (~1–2 s), one authority-pin network step (~2 s, `gates`), the browser arm (~5–10 s, `docs.yml`, chromium already installed); registry — the yank-arm tests (~8, seconds), `mirror-drift` (~30 s incl. checkout + uv sync), `sync-index.yml` (~1–2 min, records-touching pushes only). No new dependencies, no new runner classes, no npm anywhere.

---

## 5. The measurable proof — pre-committed acceptance rule

The authority is design record §4 "Slice 2 — Acceptance rule B"; it is restated here verbatim-in-substance with the mechanical operationalization. **The truth table, the fixture, and these kill directions are committed before any search or render code is written** — that ordering is part of the rule. All arms are deterministic structural tests; the effect size is *exactness*, so every arm carries a binary kill.

**B1 — search truth (CR-24, sample = the 10-row fixture × 6 dimensions + 1 negative + 1 combined):** every dimension arm (name, publisher, capability, standard version, status, kind) returns the exactly-correct filtered set for all 10 rows, evaluated by the node spec against the committed truth table; a nonexistent query returns 0 rows. **Yank arm, end-to-end:** a fixture release tree whose `status.json` carries `lifecycle: yanked` (a) disappears from the regenerated index (registry test), (b) is therefore absent from the rendered panel block and unreachable by search (gateway test on the mirrored consequence), and (c) one **real** sync is observed — the gateway bootstrap executing the documented sync command path, or the workflow's first autonomous firing on a records change (post-merge watch item, disclosed as such, not silent). **KILL: any wrong row in any dimension arm, or the yanked row surviving any refresh.** *Underpowered discrimination:* a harness failure (node absent, fixture/truth-table malformed, internal-consistency test red) is neither pass nor kill — it blocks until the harness is fixed; only a *wrong set* on a working harness kills.

**B2 — generation discipline (CR-21, three plants, each RED-proven by reverting only the guard):** (1) a records edit without index regen → registry `generate_index --check` red (slice 1's arm, re-proven on this slice's fixture trees); (2) a hand-edited mirror row → gateway render guard red (`panel_drift:`) **and** the authority-pin step red (`mirror_authority_drift:`); (3) a hand-edited panel row → render guard red. Plants operate on sandbox copies; the committed trees are never written (the `test_website_stamps.py` discipline). **KILL: any plant passing.** *Anti-gaming:* each plant is shown red against the guard-disabled tree (G3 RED-sanity — a plant that passes both ways proves nothing and blocks the merge).

**B3 — honesty (CR-22/23):** a fixture row with `kind: community-shared` (and one `unsigned`) is absent from the default static block and appears only under explicit filters, **with its kind tag**; a submitted-not-accepted submission fixture produces no index row at all (generator-level, structurally); the updated honesty sentence is string-pinned; the words "registry service" appear nowhere on the panel (string-scan of the panel section + the pinned sentence). **KILL: either failing.**

**B4 — static deploy (CR-26):** from a clean `--dest` assembly served by a plain static file server, the browser arm proves the static rows render and search works over the served index, with the only search-originated network request being the same-origin `plugins-index.json`. **KILL: any non-static dependency for catalogue or search.**

**Ongoing (not gates):** the sync-window red on registry main is the accepted honest intermediate; its expected duration (bot path, minutes once the token exists) is disclosed, not measured, at merge.

---

## 6. Review tier — the design-time call (#254)

**Tier 3, both PRs, by the keyword rule** (`docs/internal/review-rubric.md` Step 1: "the diff text contains any of: `threading`, `asyncio`, `subprocess`, `sha256`, `hashlib`, `migrate`, `recovery`, `protection`"). No Tier-3 *path* rule fires on the gateway side (`website/`, `scripts/website/`, `tests/contract/` are not in the path list — `scripts/registry/` deliberately untouched); the registry side touches no schema file and no Tier-3 path either. The tier is bought by text, exactly the rubric's "the deep lane is bought by what the text carries."

**Step-1 keyword scan over the expected diff text.** The full expected diff = this record + the PR A files + the PR B files. The mechanical scan over this record's own committed bytes (word counts, `grep -o | wc -l`):

| keyword | this record | provenance |
|---|---|---|
| `sha256` | 10 | substantive — the row field `manifest_sha256` (§1.1), the digest display, the gate prose — plus §6's rubric quote and this table |
| `subprocess` | 7 | substantive — the capability field name (§1.1), test-invocation patterns — plus the quote and this table |
| `hashlib` | 4 | the registry fixture digest construction mention, the code-diff inventory below, the quote, this table |
| `protection` | 4 | substantive — push protection (§7) and gate prose — plus the quote and this table |
| `threading` | 2 | §6's rubric quote + this table (self-fire, intended by the rubric's keyword-rule interplay note) |
| `asyncio` | 2 | same |
| `migrate` | 2 | same |
| `recovery` | 2 | same |

Expected code-diff inventory (per file, from §2's mechanism): `scripts/website/render_plugins_panel.py` — `sha256` ×1 (reads `manifest_sha256`); `tests/contract/test_website_plugins_panel.py` — `sha256` ×2–3 (row-field asserts), `subprocess` ×2 (tool invocation, the slice-1 registry test pattern); `tests/contract/test_website_plugins_search.py` — `subprocess` ×1–2 (node invocation); registry `tests/test_generate_index.py` additions — `sha256` ×2–3 and `hashlib` ×1–2 (fixture manifest digests), `subprocess` ×2 (the existing `_run` pattern); workflows and docs amendments — 0. Aggregate expectation across the whole diff: **`sha256` ≈ 18, `subprocess` ≈ 13, `hashlib` ≈ 7, and each of the remaining four at this record's count alone.** First-match-wins fires on `sha256` by itself; the counts are recorded so the review's independent re-derivation has numbers to check against, not a bare "was run."

**Consequences of Tier 3:** the refute runs **two independent adversary lanes** (the standing two-lane doctrine for Tier-3 increments). The standards-governor dispatch is *not* triggered — no `standards/` byte moves, and the governor mandate is scoped to corpus/manifest/vendored/standard-version surfaces, none touched — but the G4 contract check walks CON-12/13 against the live code, and the G5 obligation walk covers the new obligation-18 clause in the same change that creates it.

---

## 7. Top risks — and what falsifies this design

1. **The T2 exemption reopens the #188 fold-F2 argument** (a literal anywhere in `website/` was ruled a defect; this slice admits one file). Falsifier/control: the exemption is one named file, generated, whose bytes are pinned to an immutable authority by two independent gates the exemption cannot influence; the control arms prove a literal in any other file — including the panel block and the pin file — still reddens. If a reviewer can exhibit a hand-edit to the mirror that passes all three gates, the design is wrong.
2. **The sync-window honest red teaches devs to ignore a red lane.** Mitigation: the refusal message names the exact sync command; the bot path shrinks the window to minutes; D-S2d leaves auto-merge as the owner's escalation. Falsifier: a sync window that routinely exceeds a working day with the token configured.
3. **Cross-repo credentials** (`GATEWAY_SYNC_TOKEN`) — scoping, rotation, and the failure mode of an absent token silently disabling sync. Mitigation: absent token fails the job loudly; the token is fine-grained (contents+PRs write on the gateway repo only); secret scanning with push protection is already on in both repos. Residual: a *mis-scoped* token fails at first use — discovered at the first sync, which the acceptance observes.
4. **Predicate/wiring drift** — the node-tested pure predicate and the DOM wiring diverge (the predicate is right, the page is wrong). Mitigation: lane 2 exercises the real wiring on the real assembled artifact; the predicate is the only logic-bearing unit and the wiring is declarative. Falsifier: a browser-arm green with a node-arm red, or vice versa, on the same truth table.
5. **Registry history rewrite invalidates the pin's fetch** (force-push makes the pinned SHA 404). Mitigation: fail-closed (a 404 is `mirror_authority_drift:` red, not a warning); the registry constitution is append-only with rulesets. Residual accepted: the registry's own governance is the structural guarantee, not this gate.
6. **The yank-by-row-drop reading could be wrong** (a future need to show yanked releases flagged rather than gone — e.g. an incident-response page). This record chose "gone" from the design's own "flagged-or-gone" disjunction because the schema is frozen and CR-25 says no stale rows survive. Falsifier: a slice-4/#226 requirement to render yanked state publicly — then an index v2 field is that slice's train, not a retrofit here.
7. **Panel-block merge conflicts** with concurrent hand edits to `website/index.html`. Mitigation: the block is contiguous and tool-rewritten; conflict resolution is "re-run the tool." Falsifier: none structural — this is friction, not correctness.
8. **The one-JS-file CommonJS guard** could be read as a build step in disguise. It is one line behind a `typeof module` check, no bundler, no npm — the record names it so the review judges it as what it is.

---

## 8. Forks for the maintainer

1. **Sync automation posture:** bot PRs via `GATEWAY_SYNC_TOKEN` (this record's default — minutes-latency, loud on absence) vs manual-only sync forced by the drift gates (zero credentials, longer honest-red windows). The gates make either posture safe; the choice is operational. Requires the owner to mint the token if the bot path is taken.
2. **Nav position for the Plugins button** (Direction: second). Cosmetic; the only constraint is `PANEL_INDEX`/DOM agreement.
3. **The two new styleguide component shapes** (filter bar, catalogue meta line) are declared here as token-only extensions per the styleguide's own instruction to say-so-rather-than-improvise; if the owner wants them added to `docs/internal/public-site-styleguide.html` as first-class components (the guide is versioned "v0.2 draft"), that doc edit rides PR A — recommended, since the guide is the panel's authority.

---

*Design record for issue #224 (slice 2 of 6, parent #209). One standards bump in the whole arc (registry 0.1.2, spent in slice 1); this slice moves no corpus bytes on either side. Slice 2 unblocks #227 (rendering precedes sharing) and runs parallel to #225 once #223 lands — it depends on nothing between them.*
