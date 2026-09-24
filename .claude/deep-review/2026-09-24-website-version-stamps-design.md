# Design — issue #188: website version stamps derived from machine source

Date: 2026-09-24 · Increment designer · repo `madeinoz67/benchweave` at `bebf5d9`
Verdict: **BUILD** — the preferred fork (derivation at assembly) plus an adapted checker
arm. One fork in the issue's own mechanism statement is corrected with evidence (below).
No standards pinned bytes move; no SDK byte is needed.

---

## 1. Root cause (verified, with one correction to the stated mechanism)

Confirmed at the filed lines: `website/index.html` carries hand-stamped literals at
`:330`/`:332` (OTDP badge `v0.1.0` vs its own href `docs/standards/otdp/0.1.1/` vs
active `0.2.2`), `:335`/`:337` (registry), `:340`/`:342` (execution), `:345`/`:347`
(interface), `:350`/`:352` (plugin-ui), `:355`/`:357` (plugin-ui-preview), and `:414`
(tagline `SDK 0.0.2 · OTDP 0.1.0 baseline`). The issue's table is exhaustive: a
whole-tree `rg -o '\d+\.\d+\.\d+' website/` finds **14 semver occurrences on 13 lines,
all in `index.html`** (0.0.2 ×1, 0.1.0 ×10, 0.1.1 ×3); `website/assets/` is clean.

The correction — *why no gate ever caught this*, established rather than assumed:

- `website/` is the **source**, not an output. `scripts/assemble_docs_site.py` copies it
  verbatim (`copy_tree`, "copied verbatim to the artifact root", module docstring);
  there is no template and nothing re-renders it.
- The one gate that already touches the website — `verify_tree`'s "every relative
  `docs/` link on the static site must resolve in the assembled tree" — is
  **structurally blind to this defect class**: GOVERNANCE's copy-never-move rule keeps
  every superseded version directory in the tree, so a stale href like
  `docs/standards/otdp/0.1.1/otdp-specification.html` *resolves* and passes. The gate
  catches dangling links; it cannot catch stale-version links.
- Nothing else names `website/`: `matrix --check` gates `docs/compatibility-matrix.md`
  only (CON-12); the documents suite walks `DOCS` and `STANDARDS` only
  (`scripts/architecture/check_documents.py` roots; taxonomy rule 3); the bump trains'
  in-arc sweeps have no website row.

This is the same defect class CON-8 already closed for the identity block (issue #44:
"three doc surfaces carried a stale adapter API version with every gate green"). The
website is the remaining un-mechanised version-bearing surface.

## 2. The mechanism

**Shape: stamp tokens in the source, derivation at assembly (D1).** `website/index.html`
carries tokens, never versions; the assembled artifact is stamped from committed state;
the checker pins source hygiene so hand-stamps cannot come back.

### 2.1 Token sites — `website/index.html` (13 lines touched)

Token grammar: `{{stg-<key>}}`, `key` ∈ manifest entry ids ∪ `{sdk}` (prefix matches the
project's `stg_v1` idiom). One token per claim, so badge and href carry the *same*
string and agreement is structural, not policy:

| Site | Today | Becomes |
|---|---|---|
| 6 badges (`:330,:335,:340,:345,:350,:355`) | `v0.1.0` / `v0.1.1` | `v{{stg-otdp}}`, `v{{stg-registry}}`, `v{{stg-execution}}`, `v{{stg-interface}}`, `v{{stg-plugin-ui}}`, `v{{stg-plugin-ui-preview}}` |
| 5 local hrefs (`:332,:337,:342,:347,:352`) | `…/<id>/<x.y.z>/<page>.html` | version segment → `{{stg-<id>}}` |
| 1 GitHub href (`:357`) | `…/plugin-ui-preview/0.1.1` | `…/plugin-ui-preview/{{stg-plugin-ui-preview}}` |
| Tagline (`:414`) | `SDK 0.0.2 · OTDP 0.1.0 baseline` | `SDK {{stg-sdk}} · OTDP {{stg-otdp}} baseline` |

### 2.2 Derivation and stamping — `scripts/assemble_docs_site.py`

Extend the existing class-11 build transform family (`rewrite_links`, `add_site_home_link`
already transform built HTML); three additions, stdlib + one existing package import:

```python
STAMP_TOKEN_RE = re.compile(r"\{\{stg-([a-z0-9-]+)\}\}")

def website_stamp_map(root: Path) -> dict[str, str]:
    """Committed state -> the website's version claims (invariants CON-13).
    <id> -> active version via load_manifest; 'sdk' -> load_sdk_compatibility().sdk."""

def stamp_website(dest_index: Path, stamps: dict[str, str]) -> None:
    """Substitute {{stg-*}} in the ASSEMBLY COPY only. Refusals (SystemExit,
    machine prefixes): stamp_unmapped_token:, stamp_unused_key:."""
```

- `website_stamp_map` calls `benchweave.standards.manifest.load_manifest` +
  `load_sdk_compatibility` (`src/benchweave/standards/manifest.py`) — one authoritative
  parse, inheriting `standards_entry_duplicate` / `standards_entry_version_invalid` /
  `sdk_compatibility_invalid` fail-closed behaviour for free. The assembler runs under
  `uv run` with `uv sync` done in `docs.yml`, so the import costs nothing new.
- `copy_website` calls `stamp_website(dest / "index.html", website_stamp_map(REPO))`
  after its copytree. Source file never written (guard_dest posture).
- Coverage is bidirectional and fail-closed: any `{{stg-*}}` token with no map entry
  refuses (`stamp_unmapped_token:`); any map key with zero occurrences refuses
  (`stamp_unused_key:`) — the standards panel cannot silently omit a standard.

### 2.3 Assembly fail-closed — `verify_tree` gains a residue arm

`stamp_residue:` failure if `STAMP_TOKEN_RE` matches anything in `dest/index.html` — an
unstamped token is a loud scar, never a shipped lie. Composed with the *existing* link
resolution sweep, the guard matrix closes (see §5).

### 2.4 Checker pin — new `tests/contract/test_website_stamps.py`

(the `tests/standards/test_matrix.py` derived-surface-pin shape; tmp copies for mutations)

- **T1 derivation pin** — `website_stamp_map(ROOT)` equals `{f"stg-{e.id}": e.version for
  e in load_manifest(...).standards} | {"stg-sdk": load_sdk_compatibility(...).sdk}`.
  Catches a map that hardcodes.
- **T2 source hygiene (the RED vehicle for the issue itself)** — `website/index.html`
  contains **zero** `r"\d+\.\d+\.\d+"` matches. On today's main this fails with exactly
  the 14 filed occurrences.
- **T3 coverage** — tokens-in-source == map keys (both directions).
- **T4 per-card agreement** — each `<div class="spec-card">` block contains exactly one
  token, exactly twice (badge + link). Catches the issue's "badge disagrees with its own
  href" shape within a card.
- **T5 tamper vehicles (4, each must be detected)** — (a) substitute a badge token with a
  literal `0.1.0` → T2 fails; (b) swap one card's badge token for another standard's →
  T4 fails; (c) inject `{{stg-nope}}` → T3 fails; (d) restamp a whole card with the wrong
  standard's token (×2) → T3's unused-key arm fails.
- **T6 stamped output** — run `stamp_website` on a tmp copy of the real source: zero
  residue; the 7 claim-sites read exactly the manifest actives + `sdk_compatibility.sdk`;
  all stamped `docs/` hrefs resolve against the in-tree `standards/` (the frozen-history
  check, mechanised against the active versions).

### 2.5 CI wiring — zero new jobs

Pins ride `gates`'s existing `uv run pytest -q` (`ci.yml`); stamping rides the existing
"Assemble the site" step (`docs.yml`). `make check-sdk-standards` untouched and must stay
green (acceptance rule K3).

## 3. Decisions taken (the named fork and the smaller calls)

**Fork 1 — derive at assembly (D1) vs checker-only (minimal) vs writer+check (D2).**
**D1 + adapted checker** ("both", as leaned), with the issue's option-2 checker assertion
*adapted*: under derivation there are no literals left to compare to the manifest, so the
checker asserts placeholder hygiene + coverage + per-card agreement instead.
- Why not checker-only: it makes every bump train hand-edit the site again (the sweep
  that already failed); drift blocks instead of vanishing.
- Why not D2 (a repin-style writer that stamps the committed file, `--check` compares):
  it keeps version literals in `website/` — failing the issue's own criterion ("no
  hand-stamped versions remain") and taxonomy rule 6 — adds a writer invocation every
  bump (re-drifts by omission, the exact failure mode of the sweep lists), and its
  missed-site failure is a silent stale value where D1's is a loud token. D2 is the named
  fallback if raw-source preview parity becomes a stated requirement (see risks).
- Badge/href disagreement becomes **unrepresentable at the value level** (one token, two
  sites, one substitution) — the project's "make bad states unrepresentable" principle,
  versus policy-checking two independent literals.

**Fork 2 — checker home.** The issue names a documents-suite arm. **Rejected on
evidence:** `tests/contracts/test_architecture.py`'s harness injects exactly
`{DOCS, STANDARDS}` (`load_suite`, init_globals), `pristine_trees` copies only those two
trees, and `test_validation_is_read_only` snapshots only those — a third-tree arm's
mutation vehicles can never reach the suite (a tmp run would check the real website while
the vehicle mutates a copy). Widening the injection contract of a 44 KB hard-won harness
for one arm is sprawl; a dedicated pytest module gets working vehicles trivially and
matches the `test_matrix.py` precedent. The assembly-side residue arm stays in
`verify_tree` (class 11's declared regime).

**Fork 3 — the SDK-version machine source (the named design input).** An in-repo source
**exists**: `standards/standards-manifest.json` → `sdk_compatibility.sdk` (today `0.2.0`),
the mirror of the SDK lock's `compatibility` block, drift-gated against the lock at the
pinned gitlink by `check.run_check` (`sdk_compatibility_drift`, CON-12). Both tagline
numbers derive from the manifest (`sdk` from the mirror, OTDP from the active `otdp`
entry) — the stamp stays a pure function of committed state (CON-12's lesson from #158:
never make a render depend on submodule/working-tree state). Semantics named: the tagline
is a **compatibility claim** (what this tree's corpus pairs with), not "latest release";
latest-release semantics have no in-repo source and a network fetch at assembly is
refused by the same principle. Residual: the mirror is hand-maintained SDK-side (risk R2).

**Deferrals (carrier + reopen trigger):**

1. **`Python 3.13+` in the tagline stays literal** — two-component, outside the
   `x.y.z` ban pattern. Carrier: none (prose). Reopen: the floor ever stated as
   three-component, or first observed drift from `pyproject.toml` `requires-python` →
   derive from `requires-python`.
2. **`verify_tree`'s `standards/otdp/0.2.0/otdp-runtime.schema.json` probe literal**
   — a tree-shape probe of a *frozen* version dir; copy-never-move makes it permanently
   resolvable and it claims nothing about "active". Carrier: the assembler. Reopen:
   GOVERNANCE ever permitting version-dir deletion, or the probe generalising to an
   active-derived path.
3. **SDK sibling site stamps** (`packages/sdk/website/index.html`:66 status line
   `SDK 0.2.0 · OTDP 0.2.2 · adapter API 1.1`, `:342-347` version selector, `:426-428`
   standards badges) — same drift class, currently correct by hand sweep, unguarded. No
   SDK byte in this increment (TWO-1 order is owner-gated). Carrier: the SDK's next site
   train, mirroring this mechanism (its `adapter API` claim derives from the CON-8
   identity/const chain). Reopen: first observed SDK-site stamp drift, or the next SDK
   docs-site train.
4. **A D2-style writer flavour** — rejected alternative, recorded. Reopen: raw `website/`
   preview parity becomes a stated requirement.
5. **Two-component version claims in site prose** (`Architecture v1.5`) — out of pattern;
   named residual of T2, not a task.

## 4. Precedent (extended, not invented)

- **`src/benchweave/standards/matrix.py` `render_matrix` (CON-12)** — the exact pattern:
  a doc surface whose version cells derive from the manifest + the `sdk_compatibility`
  mirror, pure function of committed state, with a `--check`/pin family. The website
  stamps are the same medicine on class 11.
- **`benchweave.standards.manifest.load_manifest` / `load_sdk_compatibility`** — the
  authoritative parse (CON-8's closed-world refusals).
- **`assemble_docs_site.py`'s own build transforms** (`rewrite_links`,
  `add_site_home_link`, `verify_tree`) — class-11's existing transform + fail-loud regime.
- **Pin + tamper-arm test shapes** — `tests/contracts/test_architecture.py`
  (`test_validation_report_tampering_is_detected`, `test_contract_regressions_are_detected`)
  and `tests/standards/test_matrix.py`.
- **The defect precedent** — issue #44 / CON-8: version drift across doc surfaces with
  every gate green; the fix was derivation + machine equality, same as here.

## 5. Invariant and drift impacts

- **New invariant CON-13** (append to `docs/internal/invariants.md`, anchored on
  `scripts/assemble_docs_site.py` `website_stamp_map`/`stamp_website`):
  *Website version stamps are a pure function of committed state — `website/index.html`
  carries `{{stg-*}}` tokens, never version literals; `website_stamp_map` derives from
  the standards manifest and the `sdk_compatibility` mirror (CON-12's authority chain);
  substitution happens only in the assembly copy and `verify_tree` refuses residue —
  pinned by `tests/contract/test_website_stamps.py`. The badge/href pair of a card carries
  one token twice, so a claim/link version disagreement is unrepresentable at the value
  level.* (CON-12's #158 lesson applied to the public site.) No CTL/STO/REG change.
- **`docs/internal/drift-and-obligations.md` — new row 18, the version-bearing-surface
  inventory** (the issue's requested row): every surface that declares a corpus/SDK
  version and its motion mechanism under a bump —
  (a) `standards/standards-manifest.json` (authority; moves with the bump itself);
  (b) `docs/compatibility-matrix.md` (derived; `matrix --check`);
  (c) `docs/README.md` validation-report rows (derived paths; the family pin tests);
  (d) `website/index.html` stamps (derived at assembly — **zero bump motion**; tokens
  only; the hygiene pin refuses a literal; a NEW claim-site gets a token + map coverage,
  never a literal);
  (e) the adapter-identity touch-set (obligation 8 — hand-carried, in-arc);
  (f) `verify_tree`'s frozen-version corpus probe (copy-never-move keeps it valid; not
  active-claiming).
  Closing clause: a new version-bearing literal anywhere is a defect — make it a derived
  surface or register it here with its motion mechanism.
- **`docs/doc-taxonomy.md`** — class 11 "Validated by" cell gains the stamp hygiene pin;
  rule 6 gains one clause ("version stamps render from the standards manifest at
  assembly; `website/` carries tokens, never versions").
- **`standards/GOVERNANCE.md`** — one pointer sentence in the bump-mechanics section:
  derived version surfaces (matrix, README rows, website stamps) are not swept — their
  mechanisms derive from the manifest; the inventory lives in drift-and-obligations.
  **Constraint check:** GOVERNANCE.md is not digest-pinned (zero rows in
  `standards/corpus-manifest.json` and in the SDK `standards-lock.json`; GOVERNANCE's own
  change-class table: "Prose is not digest-pinned"), so this edit moves no pinned bytes —
  and acceptance K3 cuts it if `check-sdk-standards` says otherwise.
- **Surfaces that do NOT move:** MCP/REST/openapi, operator + device-developer guides,
  vendored standards, fixture lattice, SDK repo — nothing interface- or corpus-shaped is
  touched. **No on-disk format or schema is involved**, so the rubric's Tier-3
  format trigger does not fire; review weight sits on GOVERNANCE prose + the new CON row.
- **Guard composition** (state it, per claim discipline): source literal-ban (T2) closes
  the reintroduced-literal path; token coverage (T3) closes the omitted-standard and
  wrong-token-card paths; per-card agreement (T4) closes the mixed-token card path;
  assembly residue (`verify_tree`) closes the unresolved-token path; existing link
  resolution closes wrong-path hrefs *with* active-derived versions (the frozen-history
  loophole that made stale links invisible is closed by tokenisation — the residual is
  page-kind choice, e.g. linking a specification vs a validation report: editorial, not
  version drift).
- **CI cost:** +0 jobs, +0 workflow lines; ~6 tests + 4 vehicles (seconds on `gates`).

## 6. MEASURABLE proof — PRE-COMMITTED acceptance rule

(written before any build number is looked at; this is a deterministic conformance check,
so the honest metric is detection completeness over a fully enumerated defect set — no
statistical test, no correlation, no shuffle null: those would be padding.)

**Sample (complete enumeration at design time, not a sample):** 14 semver occurrences on
13 lines of `website/index.html` — `rg -o '\d+\.\d+\.\d+' website/index.html` →
`0.0.2` ×1, `0.1.0` ×10, `0.1.1` ×3 — at 7 claim-sites (6 spec cards + SDK tagline).

**RED (the checker proves the filed issue):** the T2 hygiene check run against today's
`main` (`bebf5d9`) fails naming exactly these **14/14 occurrences** (effect size:
complete detection). This is the first watched failing test.

**GREEN (ship criteria, all four):**
1. T1–T6 pass; the 4 tamper vehicles are detected **4/4**, each by its named prefix
   (`stamp_unmapped_token:`-family / the hygiene / coverage / per-card failures).
2. Stamped output: zero `{{stg-` residue; the 7 claim-sites read exactly
   `otdp 0.2.2 · registry 0.1.1 · execution 0.1.0 · interface 0.1.0 · plugin-ui 0.2.0 ·
   plugin-ui-preview 0.1.1 · sdk = sdk_compatibility.sdk`; every stamped `docs/` href
   resolves (existing `verify_tree` sweep green).
3. Gates: `UV_PROJECT_ENVIRONMENT=venv uv run ruff check .` clean; bare `uv run mypy`
   clean; `uv run pytest -q` green; `make check-sdk-standards` green (zero pinned
   standards bytes moved).
4. The design record is in git history before the measurement ran (pre-commit proof).

**Kill directions (both, pre-committed):**
- **K1 — RED does not fail on today's main** (or fails naming fewer than 14/14 filed
  occurrences): the checker cannot see the defect class → **KILL** the increment (do not
  ship a checker that is green on the drifted tree).
- **K2 — any tamper vehicle survives** (kill threshold: detection < 4/4): **KILL** the
  checker scope and redesign before shipping; no "known gap" notes.
- **K3 — `make check-sdk-standards` reddens from the GOVERNANCE.md edit:** the
  "prose is unpinned" premise is wrong for that file → **CUT** the GOVERNANCE sentence
  from the increment (inventory row lives only in drift-and-obligations); record the cut,
  do not work around the gate.

**Underpowered direction (measurement inconclusive — redesign, do not conclude):**
if the `x.y.z` ban cannot separate corpus-version claims from legitimate three-component
non-version strings in `website/` (e.g. a future URL/SRI fragment matching the pattern)
so the T2 failure set becomes ambiguous — fails on non-claims or misses claims — the run
is **underpowered**: re-scope the ban to claim-site elements and re-run; no ship/kill
conclusion from the ambiguous run.

## 7. Top risks and falsifiers

| # | Risk | Falsifier / check | Threshold |
|---|---|---|---|
| R1 | Token leaks to the published site | `verify_tree` residue arm + T6 | any residue = fail (never ship) |
| R2 | `sdk_compatibility.sdk` lags the SDK's real release (it is a hand-maintained compatibility claim) | human cross-check of the stamped tagline against the SDK's published release at review; disagreement routes to the SDK lock's maintenance | any disagreement = wording becomes "compatibility" or the mirror is fixed SDK-side — not silently re-stamped here |
| R3 | The unused-key coverage arm over-couples (a new standard admission reds docs until a card exists) | design question, resolved fail-closed; if the maintainer rules the no-card state legitimate, drop to token⊆map only | one ruling either way, recorded in the design record |
| R4 | Spec-card markup refactor silently weakens T4's scan | T5 vehicle (b) uses the same scanner; the scanner must assert it found ≥1 card and every card a token pair | any scanner miss = test red, not silent pass |
| R5 | Raw `website/` preview shows tokens | README/comment names the preview path (`assemble_docs_site.py --dest /tmp/site-preview`); if unacceptable, revive D2 | maintainer call; D2 stays the named fallback |

## 8. What the maintainer must decide

1. **R3's call** (coverage arm strictness) — fail-closed on a missing standard card
   (recommended) vs token⊆map only.
2. **R5's call** (raw-source preview parity) — accept tokenised source with the assembler
   as the preview path (recommended) or revive D2.
3. **Deferral 3 elevation** — the SDK sibling site carries the same drift class
   (currently correct); schedule the mirror mechanism on the SDK's next site train, or
   leave it at the reopen trigger.
