# Issue #401 — Published-link move off GitHub Pages onto the project domains (design of record)

**Date:** 2026-10-05
**Status:** Design of record (pre-implementation). A documentation/config sweep — no mechanism, no standards bytes, no behavior change. Mapping per issue #401 **as corrected by the owner in-session 2026-10-05 (the issue body's `www.benchweave.com` was a typo)**: `https://madeinoz67.github.io/benchweave/` → `https://www.benchweave.dev/`; `https://madeinoz67.github.io/benchweave-sdk/` → `https://sdk.benchweave.dev/`; paths unchanged. Labels `sdk`+`gateway`; single tracker stream (#401 links every PR; SDK PRs note no SDK-side issue by design).
**Parallel-lane guard:** the #394 build is in flight (gateway + SDK `feat/issue394-mock-bytestream`; the #394 builder owns the SDK standalone checkout's live working tree). This lane touches none of those branches and works in its OWN worktrees (§6).

---

## 1. Execution-time census method

Design-time census below (§8); the lane re-runs the same forms at execution time on its own branch HEAD — the issue's filing list is explicitly not exhaustive. Forms, both repos, tracked files at HEAD:

```
git grep -n "madeinoz67.github.io" HEAD            # the only old host we own
git grep -n "github.io" HEAD                        # superset; catches bare/schemeless forms
git grep -n "github.io/benchweave-sdk\|/benchweave/docs/" HEAD   # path forms without our owner prefix
```

Plus the surfaces grep misses by design: rendered HTML buckets (checked post-deploy, §5), CI badge text (`.github/**` — census: zero hits both repos), and release notes (CHANGELOG.md — census: zero hits both repos; future entries inherit whatever URLs their commits carry, no back-edit).

Exclusions the census must NOT sweep (§3 and the kill rule): the third-party `posit-dev.github.io/great-docs/` references (Great Docs' own documentation — not our Pages host) and the contract identifier family `https://benchweave.dev/contracts/**` (`$id` values in `src/benchweave_sdk/standards/**` — identifiers, not links; rewriting them is a standards-bytes motion and a hard kill).

## 2. Surface map — SOURCE vs GENERATED

**SOURCE (hand-edited, this sweep's targets):**

| Repo | File:line | URL count | Notes |
|---|---|---|---|
| gateway | `README.md:20` | 2 | site + SDK-site links |
| gateway | `docs/plugin-sdk.md:3` | 1 | the issue's named hit |
| gateway | `great-docs.yml:17,20` | 2 | `site_url`/`base_url` — machine-consumed by the Quarto render (canonical URLs of the rendered site) |
| gateway | `index.qmd:25` | 1 | |
| gateway | `website/index.html:72,434,481` | 3 | |
| gateway | `scripts/assemble_docs_site.py:613` | 1 | `write_llms_txt` base — machine source for `llms.txt` |
| SDK | `README.md:37,69` | 3 | |
| SDK | `CLAUDE.md:5` | 1 | |
| SDK | `great-docs.yml:100,105` | 2 | render config, as gateway |
| SDK | `pyproject.toml:66,67` | 2 | `[project.urls]` Homepage/Documentation — machine-consumed by PyPI metadata at the next release; `Repository` (the only URL CON-12's matrix render reads) is a github.com URL and is NOT touched |
| SDK | `template/AGENTS.md.jinja:71` | 1 | renders into every generated plugin project (`docs/v/v{{ sdk_version }}/`) |
| SDK | `tests/fixtures/scaffold_expected/{base,ui}/AGENTS.md:71` | 2 | lockstep fixtures pinning the template |
| SDK | `tests/test_agent_assets.py:337`, `tests/test_getting_started.py:86` | 2 | the pins — move WITH their sources, in the same change |
| SDK | `website/index.html:442,452` | 2 | includes the gateway-site link (→ `https://www.benchweave.dev/`; §4's gate lifted under the corrected mapping, 2026-10-05) |

The `packages/sdk` submodule mirrors the SDK list (README:82, great-docs.yml:100,105, pyproject:57,58, website:440,450) — the SDK-side PR IS that motion; the gateway pointer advance carries it into this tree (§7).

**GENERATED (never hand-edited; regenerate at the next deploy):**

- SDK `site/docs/v/{dev,v0.0.1,v0.0.2}/**` and `great-docs/_site/**` — **untracked** build outputs (`git ls-files` empty); rendered by the great-docs build configured by the tracked `great-docs.yml` over the repo's docs sources; the `.well-known/skills/**/SKILL.md` pages (the "Full documentation" link) render through the same build — no tracked carrier outside the build config (census-verified: `git grep "Full documentation"` outside `site/`/`great-docs/` = 0 hits). Fixing `great-docs.yml` + sources re-renders them at deploy.
- Gateway assembled site (including its `llms.txt`) — built at deploy by `.github/workflows/docs.yml` + `scripts/assemble_docs_site.py` from the tracked sources above; nothing assembled is committed.
- Deploy mechanism untouched: no `.github/**` file carries any `github.io` literal (census both repos); the custom-domain serving setup is an operator/Pages-settings matter, not a repo-bytes matter.

## 3. Current-vs-historical rule, operationalized

**KEEP original URLs (frozen history — editing them is a kill condition):**

- `.claude/deep-review/**` (both repos) — design records are committed history by this directory's own convention.
- `docs/implementation-planning/**` (gateway) and `docs/superpowers/**` (SDK tracked plans, e.g. `docs/superpowers/plans/2026-09-16-sdk-docs-site.md:371–373` — historical verification commands; gateway `docs/superpowers/` is untracked by convention).
- `CHANGELOG.md` history (both repos) — machine-rendered from git history by git-cliff; never hand-edited, never regenerated to rewrite old entries.
- Git history and commit messages — untouchable.
- Disclosed cost: if the old Pages hosts ever stop serving (no redirect), historical links rot as history. That is accepted by this rule; the issue's mapping says nothing about retiring the old hosts, and the liveness gate (§4) checks the NEW hosts only.

**MOVE (current user-/operator-facing surfaces):** every SOURCE row in §2 — READMEs, CLAUDE.md, guides, the two `website/index.html` files, `index.qmd`, `docs/plugin-sdk.md`, the two `great-docs.yml` configs, `scripts/assemble_docs_site.py`'s llms base, SDK `[project.urls]`, the scaffold template + its lockstep fixtures and pin tests.

## 4. Liveness verification BEFORE swap (design-time result recorded)

Probe per mapping: each root plus one docs path, `curl -s -o /dev/null -w "%{http_code}" --max-time 10`.

**Design-time (2026-10-05, this record):**

| URL | Result |
|---|---|
| `https://sdk.benchweave.dev/` | **200** |
| `https://sdk.benchweave.dev/docs/` | **200** |
| `https://sdk.benchweave.dev/docs/user-guide/plugin-sdk.html` | **200** |
| `https://www.benchweave.com/` | **000 — NXDOMAIN** (`dig +short` returns no record; curl "Could not resolve host") |
| `https://benchweave.com/` (apex) | **000 — NXDOMAIN** |

The issue's premise ("the project sites now live on proper domains") is true for the SDK domain and **was, at design time, false for the gateway domain as written** — because the written form was a typo.

**Correction (2026-10-05, same day, pre-implementation):** the owner confirmed the gateway domain is `www.benchweave.dev`, not `.com`. Re-probe under the corrected mapping:

| URL | Result |
|---|---|
| `https://www.benchweave.dev/` | **200** |
| `https://www.benchweave.dev/docs/` | **200** |
| `https://benchweave.dev/` (apex) | **301 → `https://www.benchweave.dev/`** (the `/contracts/**` identifier paths keep their apex form; identifiers are untouched by this sweep either way) |

The liveness gate is satisfied under the corrected mapping: **both phases proceed**. The gate mechanics survive the correction — each phase's PR re-probes its target at merge time, and a dead domain at merge time still holds the landing:

- **Phase 1 (SDK repo):** target live; proceeds, and now also carries the SDK repo's gateway-site URLs (`website/index.html:442` and any README link pointing at the gateway site) since the corrected target is live.
- **Phase 2 (gateway repo):** proceeds — the gateway SOURCE rows of §2 sweep onto `https://www.benchweave.dev/`.

## 5. Verification rule (post-sweep, pre-committed)

1. **Zero stale forms on current surfaces:** `git grep -c "madeinoz67.github.io" HEAD` over each repo, minus the §3 historical paths = **0**; the bare `github.io` superset returns only the third-party allowlist (`posit-dev.github.io` references and great-docs example comments) — none of ours.
2. **Pins prove the sweep:** SDK `tests/test_agent_assets.py` and `tests/test_getting_started.py` move in the SAME change as their sources and pass — a source edit without its pin reds, a missed pin reds at CI. That lockstep is this sweep's RED control (no separate mechanism to disable).
3. **Batteries green:** SDK suite (scaffold suites included — `scaffold_expected/{base,ui}` move in lockstep with `template/AGENTS.md.jinja`); gateway fast lane + focused contract tests (`tests/contract/test_website_stamps.py`, the docs-site tests).
4. **Release-review-matrix walk** (`docs/internal/release-review-matrix.md` in benchweave-sdk): every version-bearing surface checked against its machine source; prose-defers-to-machine-sources — this sweep adds no version claims, and the walk confirms none was disturbed (CON-13's stamp machinery is untouched; CON-12's matrix reads `[project.urls] Repository`, which does not change).
5. **Post-deploy leg (after the Pages deploy of each phase):** `curl` the new domain's rendered root and one docs page and grep the served HTML for `madeinoz67.github.io` — catches a half-rendered bucket the repo census cannot see.

**KILL:** any current surface still carrying an old form; any `benchweave.dev/contracts/**` `$id` rewritten; any §3 historical record edited; Phase 2 landed against a dead domain; a pin test silenced instead of moved. **UNDERPOWERED → DEFER:** probes unable to run in the executing environment (never land on unverified liveness).

## 6. Serialization with the in-flight #394 lane

- **File-level disjoint at design time.** #394 (SDK side) touches `transport.py`, `session.py`, `template/{vectors,protocol,CLAUDE.md}`, `scaffold_expected/ui` content files, `user_guide/plugin-sdk.qmd`, its fixture tree, its tests. #401 touches `template/AGENTS.md.jinja`, `scaffold_expected/*/AGENTS.md`, `README.md`, `CLAUDE.md`, `great-docs.yml`, `pyproject.toml`, `website/index.html`, its two pin tests. The feared shared file — `user_guide/plugin-sdk.qmd` — carries **zero** old-host hits (census: `git grep "github.io" HEAD -- user_guide/ .github/` = 0), so #401 does not edit it; if #394's new guide section adds an old-form URL, the execution-time census catches it and this lane takes it in the rebase (the guard, not a collision).
- Adjacent directories (`template/`, `scaffold_expected/ui/`) — different files, so a clean rebase is expected; both lanes run in **own worktrees** (`.wt/<lane>-<nonce>/` under each repo root per the standing rule — the #401 SDK lane uses a worktree of the SDK repo, never the standalone checkout's live tree the #394 builder owns; shared-stash discipline applies).
- **Park-at-review-complete + single rebase:** whichever SDK PR merges second rebases once onto the merged main before its own merge; no park-and-iteratively-rebase.

## 7. Repo / PR layout

1. **SDK PR** (from this lane's own worktree of `/Users/seaton/Documents/src/benchweave-sdk`, branch `docs/issue401-domains`): all SDK SOURCE rows incl. its `website/index.html` gateway-site links (§4's corrected-target probe passed 2026-10-05; the merge-time re-probe still applies). Conventional commit references #401.
2. **Gateway PR** (own worktree of `/Users/seaton/Documents/src/BenchWeave`): the gateway SOURCE rows + this record as the slice's first commit + the submodule pointer advance carrying the SDK PR's merge (pointer advances only at the SDK release tag per the sdk-drift law — if the SDK PR rides no release before Phase 2, the pointer advance waits for the next release event; the gateway's OWN link edits do not wait for it, only the pointer row does). Phase-2 liveness gate applies to the merge, not the branch.
3. Issue #401 closes only when both phases' PRs are merged AND both post-deploy legs (§5.5) are clean.

## 8. Design-time census hit list (for the record; re-run at execution)

- Gateway tracked: `README.md:20` (×2), `docs/plugin-sdk.md:3` (×1), `great-docs.yml:17,20` (×2), `index.qmd:25` (×1), `website/index.html:72,434,481` (×3), `scripts/assemble_docs_site.py:613` (×1) — **10 URLs / 6 files**, plus third-party `docs/internal/public-site-styleguide.html:588` (out of scope).
- SDK tracked: `README.md:37,69` (×3), `CLAUDE.md:5` (×1), `great-docs.yml:100,105` (×2), `pyproject.toml:66,67` (×2), `template/AGENTS.md.jinja:71` (×1), `tests/fixtures/scaffold_expected/{base,ui}/AGENTS.md:71` (×2), `tests/test_agent_assets.py:337` (×1), `tests/test_getting_started.py:86` (×1), `website/index.html:442,452` (×2) — **15 URLs / 10 files**; historical `docs/superpowers/plans/2026-09-16-sdk-docs-site.md:371–373` (keep); third-party `great-docs.yml:2` + example comments (out of scope); `benchweave.dev/contracts/**` `$id`s (identifiers — untouched).
- Untracked generated buckets carrying the old forms today (regenerate, never hand-edit): SDK `site/docs/v/**` + `great-docs/_site/**` `.well-known` skill pages (§2).

## 9. Review tier + Step-1 keyword scan (#254 design-time call)

**Tier 2.** Path rules: `scripts/` (the gateway assembler's llms base), `tests/` (the SDK pins), and root config `pyproject.toml` (SDK `[project.urls]`) — all Tier-2 paths; no Tier-3 rule fires (no `standards/`, no schema, no persisted-format surface, no registry seam, no fixture-digest lattice, no dependency add/remove/re-pin — a `[project.urls]` edit is not a dependency pin — no submodule-pointer authoring here beyond the release-gated advance in §7, which carries its own Tier-3 review at that PR). Keyword scan over the whole expected diff (both repos' rows in §2 + this record), counts as written:

| keyword | count |
|---|---|
| `threading` | 0 |
| `asyncio` | 0 |
| `subprocess` | 0 |
| `sha256` | 0 |
| `hashlib` | 0 |
| `migrate` | 0 — deliberate vocabulary: this record and the commits say "move"/"repoint"/"sweep", never the token; review re-derives both the tier and the scan from the actual diff |
| `recovery` | 0 |
| `protection` | 0 |

No mandatory second lane at Tier 2; the resident code-reviewer pass plus the §5 verification rule govern. Builder obligations: `author: Stephen Eaton` header on any new file (none expected — edits only); fast lane at every commit; counts from true exit codes / junitxml.
