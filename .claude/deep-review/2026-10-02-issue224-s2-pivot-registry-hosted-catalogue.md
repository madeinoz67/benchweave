# Issue #224 — Slice 2 PIVOT: registry-hosted catalogue — design record (addendum)

**Status:** Design (builder-ready) · **Tracking:** madeinoz67/benchweave#224 (sub-issue of #209, slice 2 of 6)
**Relation to the prior record:** this record ADDENDS and partially supersedes `.claude/deep-review/2026-10-02-issue224-s2-catalogue-search-design.md` (frozen; never edited). Superseded: §2.1's mirror/pin/committed-panel-block as the catalogue home, §2.3's sync workflow + mirror-drift refusal, §2.4's three-gate lattice, §3's PR shapes and order, §5's B2/B4 operationalization as written, §7 risks 1/2/3/5, §8 fork 1. Carried forward verbatim-in-substance: §2.5 search (dimensions, truth table, two proof lanes), §2.6 honesty (CR-23), the CR-20/CR-22/CR-37 field and default-view rules, the styleguide token discipline, all six deferrals D-S2a–f (homes adjusted below).
**Evidence baseline:** the four refute/advisory lanes of 2026-10-02 (gate-lattice, search+honesty ×2, mechanism-critic, governance walk) against gateway `feat/issue224-plugins-catalogue` @ `c90f9f3` and registry `feat/issue224-catalogue-sync` @ `1ea651f`. Every folded finding cites its lane. Verdicts: gate-lattice NOT-DEFENDED (tautology test), search DEFENDED-with-findings, coherence NOT-DEFENDED (vacant against wrongly-read authority), pivot mechanism MODEL-DEFECTIVE as originally claimed (repaired here).

---

## 1. The pivot

**Decision (owner, 2026-10-02):** the plugin catalogue is served from the **registry repository**, deployed by GitHub Pages today, moving to `registry.benchweave.dev` when a hosted registry service is real. The gateway website keeps a static teaser panel linking out. The cross-repo sync apparatus (mirror, pin, sync workflow, both drift gates, the class-11 exemption) is deleted in its entirety.

**Rationale.** The registry repository is the authority for the index; generating the catalogue where the records live removes the entire staleness-propagation problem the sync existed to solve. The styleguide does not block this: measured against the bytes, the hold is two narrow clauses — the mark-glyph gate (`docs/internal/public-site-styleguide.html:217/226` on main: "don't ship either until told that property is real") and the Sub-brands section gating the *separate-property framing* (custom domain included). A catalogue page in plain language under the main wordmark — including the registry repo's `github.io` Pages URL today — is not gated. The gated events are the domain cutover and the glyph's first standalone use. The prior record's §2.2 paraphrase ("no `registry.benchweave.dev` shape … is binding") overstated the hold; this record's reading is the byte-verified one (lane B, governance walk).

**Honesty posture unchanged (CR-23):** until a hosted service exists, the catalogue says what is true — "the catalogue of published releases, rendered from the registry repository of record" — and never claims a registry service.

## 2. What dies, what survives, what relocates

**Dies (gateway side):** `website/plugins-index.json`, `website/plugins-index.ref`, `scripts/website/check_mirror_authority.py`, `scripts/website/check_catalogue_served.py`, the committed panel block and its markers, the T2 one-file `GENERATED_MIRROR` exemption (T2 returns to **zero exemptions**), the CI authority-pin step, and the CON-13 lockstep amendment text as drafted (replaced by §6 below).

**Dies (registry side):** `.github/workflows/sync-index.yml`, the `mirror-drift` job in `records.yml`, `scripts/check_mirror_drift.py` and its tests, the manual-sync README appendix.

**Survives unchanged:** the yank arm's row-drop reading; the search predicate, fixture, truth table, node spec; the CR-20 seven-field contract, CR-37 marker map (unknown ids verbatim), CR-56 kind tagging, the no-JS/fetch-failure degradation posture; the registry `index.json` + `--check` (`index_drift:`) discipline, re-proven discriminating by two lanes.

**Relocates gateway → registry:** the renderer (as the page generator, with the §4.1 fix), `website/assets/plugins.js` (predicate + wiring), the fixture + truth table + `run_search_spec.mjs` + their pytest wrappers, the browser-arm pattern, the styleguide token discipline (§6.3).

**Gateway keeps:** a teaser panel (§3.4), the home-panel honesty sentence update (CR-23 — still true post-pivot), the nav button pointing at the Pages URL.

## 3. The mechanism

### 3.1 Deploy-time generation (the critic's repair — staleness made unrepresentable)

The catalogue page is **not a committed artifact**. The Pages workflow, on every push to `main`: checks out the exact commit → runs `generate_index.py` (records → index bytes, identical to the committed `index.json` by the standing `--check`) → renders the catalogue page from those bytes → deploys. A deploy of commit X serves X's catalogue by construction; there is no committed page to hand-edit, no sync window, and no stale-commit deploy path. The committed tree carries the *generator and template*, both reviewable.

**Provenance stamp (A06):** the generated page footer carries the generating commit SHA (`generated from <sha>`) so any third party can verify currency against the repo. The served surface never silently claims freshness it does not have.

**Pages workflow posture (named, per the critic's Q8):** builds from `main` only; deploy job depends on the `validity` job (a red validity never deploys); a build failure leaves the previous deployment serving with a visible failed-action status — disclosed, not hidden; cache fidelity is GitHub's Pages pipeline (immutable per-deploy URLs; no app-level cache to lie).

### 3.2 The yank arm, hardened (four-lane convergence — fix before merge)

- **Polarity flip:** the generator refuses any `status.json` whose `lifecycle` is present and outside the enum — `index_status_invalid: <value>` — instead of silently keeping the row. Absent `status.json` → row present (unchanged, tested).
- **Authority validity gated independently (lane B-2's vacancy):** the `validity` job validates every `releases/**/status.json` against the release-status enum as its own step, independent of the regenerate-and-compare — so a wrongly-read authority cannot be self-consistent by construction. The enum source is a **digest-pinned copy of `release-status.schema.json` in the registry repo** (additive, citing the gateway's vendored 0.1.1 as `source`; the two constants become one linked by a test that pins the copy against its origin digest).
- **Typed refusals on the crash arms:** malformed JSON / non-object status → `index_status_unparseable:` (no bare tracebacks; lane B-2's LOW folds here).
- **Boundary table:** an 11-value test matrix (`yanked`, `revoked`, `published`, `deprecated`, `Yanked`, `yank`, `retired`, `null`, `["yanked"]`, malformed, absent) asserting the fail-closed polarity per row — the exact matrix three lanes executed as repros.

### 3.3 The catalogue page (registry repo)

Vanilla, no build chain, static after generation. The relocated renderer's row shaping carries the CR-20 slots, kind tags (structural, `data-bw-slot="kind"` on every card), marker map, maintenance/advisory badges, explicit "none" arms. Search: the relocated pure predicate `filterRows` + DOM wiring over the generated index (one same-origin fetch; B4's substance unchanged — Pages *is* the plain file server). Default view: `admitted-release` + `signed-valid` only; everything else behind explicit filters, always kind-tagged; in-flight submissions structurally absent.

### 3.4 The gateway teaser (R4 adopted)

Timeless prose + one outbound link to the Pages URL. **Zero catalogue-derived data** — no counts, no names, no versions (a count is a mini-mirror with its own staleness clock and no gate). Dead-link degradation is honest (a link either resolves or it doesn't). Text is string-pinned with the same discipline as the honesty sentence.

## 4. The fold — every lane finding and its disposition

| # | Finding (lane) | Sev | Disposition in this rebuild |
|---|---|---|---|
| 1 | Card opening tag never closed — 13/15 slots outside the card in a real browser, duplicates, missing kind tags, all 53 tests green (B-2, HIGH) | HIGH | One-character renderer fix (`{attrs}>`) + a **DOM-containment companion test**: parse the generated page, assert every `data-bw-slot` descends from its card. Substring containment checks are insufficient and are not reintroduced. |
| 2 | Yank fails open on out-of-enum lifecycle; enum enforced nowhere; `decode_release_status` zero callers (A, B-1, critic, B-2) | HIGH | §3.2 in full. |
| 3 | Pivot claim unenforced: no Pages workflow, human-carried clock, no served provenance (critic) | HIGH | §3.1 — deploy-time generation + provenance stamp + named workflow posture. The deletion of the sync gates lands **in the same PR set** as the mechanism that replaces them, never before it. |
| 4 | `'all'` facet sentinel applied to free text — searching "all" returns everything (B-2) | MED | Sentinel-set per dimension: text box no-filter = `undefined/null/''` only; selects keep `'all'`. A truth-table arm for `text:'all'` is added (B1's KILL now fires on this class). |
| 5 | Coherence gate blind to a wrongly-read authority (B-2) | MED | §3.2's independent validity step. |
| 6 | Render guard must relocate or staleness returns intra-repo (B-1) | MED | Mooted differently by §3.1: there is no committed page to drift. The equivalent discipline is the DOM-containment + browser arm running in CI against the generated artifact (§5 B2′). |
| 7 | Advisory vanishes with the yank — the single public advisory point goes silent for the releases most likely to carry advisories (B-1, critic) | MED | Deferred-with-pin: a fixture release `lifecycle: yanked` + advisory, asserting the advisory appears on **no** catalogue surface — making the gap a documented reading, not an accident; reopen trigger named in the test docstring (slice 4 / #226). |
| 8 | Renderer's literal refusal bricks the whole render on any version substring in free text — 4/4 repros (B-1) | MED | **Decided:** the refusal narrows to the structural slots the renderer stamps; row-derived free text (`display_name`, `summary`, advisory ids, `source_revision`) is data and is exempt from the ban. Per-row refusal names the offending row. The registry repo adopts **no website-style literal gate at all** — the index legitimately carries version strings; the page is a deploy-time artifact, not hand-authored website bytes (§6.2). |
| 9 | Style authority goes cross-repo (B-1) | MED | Digest-pinned vendored copy of `public-site-styleguide.html` in the registry repo + a CI arm asserting every `var()` the page's CSS references resolves in the token block. The two declared component shapes (filter bar, catalogue meta line) are declared in that copy. |
| 10 | Honesty pin scans only the panel section while the sentence lives on the home panel (B-2, superseded→transfers) | MED | The registry catalogue's honesty pin scans **the whole generated page** (lede, footer, prose); the gateway's teaser pin scans the teaser + home sections it lives on. |
| 11 | Design record described a sync that never shipped (bot vs the built manual-only) and now describes a deleted architecture (A, B-1, critic) | MED | This record is the dated addendum; it carries the surviving acceptance verbatim (§5). |
| 12 | Obligation-20 census prose mismatch — prose said 18, gate pins 20 (critic, S1) | MED | Refreshed to the machine count in the same commit that reshapes `scripts/website/`; the prose always states the gate's own number, never a hand count. |
| R1 | Multi-capability AND/OR unpinned (B-2) | LOW | **Adopted:** AND is the intent; a two-capability truth-table arm pins it. |
| R2 | Truncation constant `12` duplicated Python/JS, no twin pin (B-1, critic) | LOW | Named constant both sides + a twin-equality pin (the `MARKER_DISPLAY` pattern). |
| R3 | Non-atomic `write_bytes` in the generator (critic) | LOW | Accepted-risk, disclosed: bounded by git + CI `--check`; revisit only if the generator ever writes outside a commit boundary. |
| R4 | Teaser rule (critic) | LOW | Adopted at §3.4. |
| R5 | Emergency-yank window on the push lane (critic) | LOW | Disclosed in the registry README: the PR lane lands status + regen in one commit (window zero); a direct push to main carries the window until the next regen — the documented path is a PR. |
| — | Gate-2 tautology (`--expected` = the mirror itself) (A) | pattern | Superseded with the machinery; the constraint is encoded in §5 B2′: **no offline test may claim to verify an authority it does not fetch; derivation is always from records via the generator.** |
| — | GOVERNANCE.md class-11 sentence staleness under the exemption (critic S2) | — | Void: the exemption dies with the pivot; the sentence returns to truth unchanged. |

## 5. Acceptance rule (pre-committed)

Arms are deterministic; every arm carries a binary kill. The truth table and fixture relocate unchanged (their C1 ancestry — `bd93b1a` before `33f86e8` — is preserved by building on the existing branches).

**B1′ — search truth (unchanged in substance):** every dimension arm over the 10-row fixture returns the exactly-correct set (node spec against the committed truth table), **plus** the new `text:'all'` arm (expects the empty-result set, not the full catalogue) and the two-capability AND arm. Nonexistent query → ∅. **KILL: any wrong row in any arm.**

**B2′ — generation discipline, reshaped:** (a) records edit without regen → `index_drift:` RED (re-proven); (b) out-of-enum or malformed `status.json` → the independent validity step RED with a typed prefix, **and** the generator refuses (`index_status_invalid:`/`index_status_unparseable:`) — proven on the 11-value boundary matrix; (c) hand-edited page → structurally unrepresentable (no committed page); the plant class is void and the DOM-containment test is the standing guard. Every guard RED-sanity-checked by reverting only the guard. **KILL: any plant passing, or any boundary-matrix row misclassified.**

**B3′ — honesty:** the catalogue page in plain language, no "registry service" claim anywhere on the page (whole-page scan), no Registry mark glyph, no `registry.benchweave.dev` URL; the provenance stamp present; the teaser carries zero catalogue-derived data and its text is string-pinned; non-default kinds absent from the default view and always kind-tagged when revealed. **KILL: any failing.**

**B4′ — static deploy:** from the Pages-style artifact (generated page + index served as static files), the browser arm proves the DOM-containment property (every slot inside its card, no orphan cards, kind tags on revealed rows), the default rows render before JS, a matching query keeps the dogfooded row, a non-matching query empties the list with the honest-empty state, and the only search-originated request is the same-origin index fetch — **scoped across the whole session, load included** (the load-window scope gap is closed). **KILL: any non-static dependency, or any containment failure.**

**Underpowered discrimination:** a harness failure (node absent, malformed fixture) blocks; only a wrong result kills.

## 6. Governance

**6.1 Gateway standards bytes: none move** (tripwire `git diff origin/main...HEAD -- standards/` stays empty). The T2 exemption deletion restores the literal gate to its pre-slice shape; `tests/standards/test_zero_literal_gate.py` returns to main's form. The CON-13 amendment is rewritten to the built truth: *the catalogue is generated and served from the registry repository; the gateway website carries no registry-derived bytes.* Obligation 18's registration moves to the registry repo's own docs (below); the gateway row is retired in the same commit.

**6.2 Registry repo hygiene stance:** the registry repository adopts **no class-11 literal gate** — its index and page are generated artifacts whose version strings are data. The discipline is generation, not scanning: `index.json` stays `--check`-pinned; the page is deploy-time; the generator's refusal covers structural slots (§4.8). This stance is recorded in the registry repo's README so the next agent does not reinvent a website gate there.

**6.3 Style authority:** digest-pinned styleguide copy in the registry repo (additive file citing the gateway doc as source); CI asserts token resolution. The gateway's `public-site-styleguide.html` remains the authored authority; the registry copy is a vendor, repinned by the same digest discipline as any vendored standard.

**6.4 The registry-side deferral home:** deferrals D-S2a–f carry forward with homes adjusted to this record and the registry README; two new rows: the **sub-brand mark / domain cutover** (carrier: the styleguide's Sub-brands section; trigger: the hosted registry service being real) and the **advisories-only surface** (carrier: slice 4 / #226; trigger: its design pass).

## 7. Tier and review slate

**Tier 3 stands** (keyword rule: `sha256`, `subprocess` present in the expected diff text — the boundary matrix, digest pins, and workflow prose carry them). The rebuilt PRs get the full four-lane slate afresh on the new bytes; this record's folded findings are the baseline those lanes re-verify, not a substitute for them. The two-PR shape returns (registry first — the catalogue must exist before the teaser links to it; gateway second, deleting the machinery and adding the teaser), both linked to #224, `registry` label on the registry-side PR per the family taxonomy.

## 8. Builds on

Gateway branch `feat/issue224-registry-hosted-catalogue` (off `feat/issue224-plugins-catalogue` @ `c90f9f3` — ancestry preserved, then the void machinery deleted in dedicated commits). Registry branch continues on `feat/issue224-catalogue-sync` @ `1ea651f`. RED-first throughout; per-commit FAST lane, full battery before push; truth-table and fixture commits precede any relocated search code (C1 already holds and must still hold at the new tips).
