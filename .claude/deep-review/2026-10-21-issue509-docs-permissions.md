# Issue #509 — docs.yml carries Pages and OIDC write grants at workflow level: narrow to job scope

**Date:** 2026-10-21 · **Tracker:** `madeinoz67/benchweave#509` · **Status:** design of record
**Base:** origin/main `05958386` (line anchors are as of that SHA; when they drift, re-locate by the
quoted structure, not the number)

**Review tier — design-time call (#254): Tier 2.** Rubric Step 1, second rule: the expected diff is
test code under `tests/` plus `.github/` and internal docs. No Tier-3 trigger matches: no `standards/`,
`src/benchweave/state/`, `contracts/`, or `fixtures/` motion, no dependency-file change, no submodule
pointer advance. **Step-1 keyword scan over the whole expected diff** (the §3 hunks plus this
record): `threading` 0 · `asyncio` 0 · `subprocess` 0 · `sha256` 0 · `hashlib` 0 · `migrate` 0 ·
`recovery` 0 · `protection` 0. Wording disclosure: the record says "branch ruleset" and "guard"
throughout — both GitHub's own current vocabulary, neither a Step-1 keyword; the zero counts above
are over the text as written. **Scan self-reference disclosure:** the eight words occur in the
expected diff ONLY inside this scan statement's own vocabulary — the #254 shape mandates naming each
keyword with its count, so the listing is self-referential by construction; over the diff text
EXCLUDING this paragraph, each keyword's count is 0. If the review's independent re-derivation rules
that the letter of the Tier-3 text match wins over that reading, the slice takes the Tier-3 lane —
stated here so any disagreement is visible rather than discovered.

---

## 1. Root cause — confirmed at source

The audit finding is confirmed line-for-line at `05958386`:

- `.github/workflows/docs.yml:16` — `pull_request:` trigger with no branch or path filter: every
  pull request runs `build-docs`.
- `.github/workflows/docs.yml:18-21` — workflow-level `permissions: contents: read`,
  `pages: write`, `id-token: write`. Every job without its own block inherits this set, including
  the PR-triggered build.
- `.github/workflows/docs.yml:32-34` — `build-docs` job header carries no job-level `permissions`
  block, so its effective token on PR runs includes Pages-write and OIDC token minting.
- `.github/workflows/docs.yml:101` — `publish-docs` guard
  `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` gates the DEPLOYMENT only.
  A guard on one job does not narrow the grant inherited by the other.
- The reachable attacker-shaped code path is real: `docs.yml:66` runs
  `uv run python scripts/assemble_docs_site.py` and `docs.yml:73-81` runs in-repo Python
  (`benchweave_ui_html.patterns`) — both from the PR head, both with the inherited grant. GitHub
  downgrades fork PRs to read-only; the exposure is same-repo branches and compromised contributor
  accounts, exactly as the finding scopes it.

This is **twin lag, not a decision**. `docs.yml:5` states "Same shape as the SDK repository's
docs.yml" — and the SDK twin has since moved on: `packages/sdk/.github/workflows/docs.yml` carries
workflow-level `contents: read` only (its lines 20-25 comment state the PR-scope reasoning
explicitly) and a job-level `pages: write` / `id-token: write` block on its own `publish-docs`,
with the comment "granted only here so the PR-triggered build and preview jobs never hold a
deploy-capable or OIDC token". The gateway deviation was even **named in-tree and left unfixed**:
`.github/workflows/publish-ui-html.yml:179-180` — "the docs.yml Pages deploy carries a separate
workflow-level one — refute lane B, F1" — a footnote recorded during the #302 first-release refute
lane. No A01–A14 decision governs CI token grants (the decisions record covers gateway semantics;
verified this pass), so nothing is being re-proposed or contradicted here.

## 2. Grant matrix — the narrowest grant that still ships

| Job | Runs on | Needs | Holds after this change |
|---|---|---|---|
| `build-docs` | push-to-main + **every PR** | `contents: read` (checkout `docs.yml:36`). It never calls the Pages API — configure/upload/deploy Pages all live in `publish-docs` (`docs.yml:111-122`). Its artifact uploads (`docs.yml:84`, `:91`) need **no write scope**, proven in-repo: `ci.yml:233-234` grants the windows job exactly `contents: read` and uploads artifacts green (`ci.yml:306-311`); `package.yml:11-12` workflow-wide `contents: read` over PR builds that `uv build` and install-assert (`package.yml:72-76`; no upload step exists in that file — builder-corrected at record-commit time: the first draft misread the ui-html build step as an artifact upload). | `contents: read` (inherited). **Neither `pages` nor `id-token` in any form.** |
| `publish-docs` | push-to-main only (`docs.yml:101`) | `pages: write` for `actions/configure-pages` + `actions/deploy-pages`; `id-token: write` for `deploy-pages`' OIDC-authenticated deployment (`docs.yml:120-122`). A job-level block REPLACES the workflow set entirely (unlisted scopes become none) — which is why the SDK twin's block lists exactly these two. | `pages: write`, `id-token: write` — job-scoped, on this job alone. |

`publish-docs` needs no `contents` scope (no checkout; `download-artifact` at `docs.yml:106` is a
same-run artifact read, proven live on the SDK twin under the identical action SHA set).

## 3. The increment — five surfaces, one commit after this record

1. **`.github/workflows/docs.yml`** — replace lines 18-21 with workflow-level `permissions:
   contents: read` (carrying a comment ported from the SDK twin: PR runs must not see Pages/OIDC
   scopes, cite #509), and add to `publish-docs`, between its `if:` (line 101) and `environment:`
   (line 102): a job-level `permissions:` block with exactly `pages: write` and `id-token: write`
   (comment citing #509 and the SDK twin). `build-docs` gains no block — inheritance from the
   now-read-only workflow set is the design. Triggers, concurrency, job ids, job display names,
   steps: untouched.
2. **`tests/contract/test_workflow_permissions.py`** (new) — the executable pin, §5.
3. **`.github/workflows/publish-ui-html.yml:178-184`** — comment amendment: after this change two
   jobs in the repo carry `id-token: write` at job scope; the distinguishing claim becomes "this
   repo's only trusted-publishing (PyPI) id-token grant", and the "docs.yml carries a workflow-level
   one" parenthetical becomes "the docs.yml Pages deploy carries the other, job-scoped to
   `publish-docs` since #509".
4. **`docs/internal/drift-and-obligations.md` CI-map row `publish-ui-html`** (line 683) — same
   amendment to "the repository's only job-scoped `id-token: write` grant — the Pages deploy in
   docs.yml carries a workflow-level one" (the row goes false the moment this lands).
5. **`docs/internal/ui-html-release-and-pin.md:163-164`** — "the repository's ONLY
   `id-token: write`" → scoped to trusted publishing, same parenthetical as above.

Commit shape: the record alone first (pre-measurement provability per the README), then this
five-file increment as one RED→GREEN commit carrying the §6 evidence in its message.

## 4. Precedent (all verified this pass)

- **Primary:** `packages/sdk/.github/workflows/docs.yml` — the same workflow (same two-job shape,
  same PR trigger, IDENTICAL action SHAs for checkout/setup-python/configure-pages/
  upload-pages-artifact/deploy-pages/download-artifact) already running the exact narrowed grant
  set in production for its live site. The port's mechanism is proven end-to-end on the sibling
  repository; the only untested delta is this repository's own Pages settings.
- In-repo job-level habits: `ci.yml:233-234`, `:327-328`, `:422-423` (`contents: read` floors);
  `codeql.yml:16-18` (job-level write scope, `security-events: write`); `publish-ui-html.yml:182-184`
  (job-level `id-token: write`). Job-scoped grants are the established register; `docs.yml` is the
  outlier.

## 5. The executable pin — what fails on the unfixed file

A stdlib-only, line-oriented reader plus one rule, in `tests/contract/test_workflow_permissions.py`
(no new script, no new CI lane; collected by the default suite in the `gates` lane; platform-neutral,
not `wincore`-marked, so the Windows core selection is untouched; strict-mypy-clean like the rest of
the tree; no new dependency — PyYAML is only a transitive lock entry today and declaring it would
make this a dependency-change diff).

**Reader contract** (fail-closed throughout; a shape it cannot structure is a refusal naming
`path:line`, never a silent skip):

- Parse every `.github/workflows/*.yml` at the repository root (NOT `packages/sdk` — the submodule
  owns its own twin and may be absent). Extract: the `on:` event set (block or flow form);
  workflow-level `permissions` mapping; per-job `id`, `if:` expression text, job-level
  `permissions` mapping.
- Recognized permission blocks are block mappings of `scope: read|write|none` lines. Flow maps or
  scalar forms (`read-all`) → refuse.
- `effective(job) = job block if present else workflow block` (replacement semantics, §2).
- `pr_reachable(job)` = workflow has `pull_request` AND the `if:` does not provably exclude PR
  events. Exclusion is proven only when EVERY top-level `||` alternative contains at least one
  recognized exclusion conjunct among: `github.event_name == 'push'`, `github.ref ==
  'refs/heads/main'`, `github.event_name != 'pull_request'`, `github.event_name == 'schedule'`,
  `startsWith(github.event.release.tag_name`. Anything else → reachable (over-approximation is the
  safe direction: a false "reachable" fails loudly and gets reasoned about; a false "unreachable"
  would hide a grant).

**The rule** (`test_no_pr_reachable_job_holds_pages_or_oidc_write`): for every workflow, every
PR-reachable job's effective map must not hold `pages: write` or `id-token: write`. The failure
message names workflow, job, scope, and whether the scope is inherited or job-declared.

**Expected RED at `05958386`:** exactly one offender — `docs.yml` / `build-docs` / both scopes,
inherited from the workflow block. Census at HEAD: seven workflow files; the other PR-triggered
ones (`ci.yml`, `codeql.yml`, `device-plugins.yml`, `package.yml`) hold only read scopes or
`security-events: write`, which is deliberately OUTSIDE the pinned scope set (GitHub documents it as
the legitimate PR-run write scope for SARIF upload). A second test arm pins the reader's own
refusals on embedded hostile snippets (flow-map permissions, `read-all`).

**Stated guard — what this check does NOT catch:** write scopes other than `pages`/`id-token` on
PR runs (`security-events`, `pull-requests` have legitimate PR uses); grants on push-, dispatch-,
release- and schedule-triggered runs; third-party action internals (the SHA-pinning discipline owns
that surface); the submodule's workflows; and the repo-default token posture for jobs that declare
no block anywhere (`ci.yml` jobs outside :233/:327/:422 rely on the repository default — disclosed
as D4 below, not silently missed).

## 6. Acceptance rule — pre-committed before any run

Deterministic structural property; binary observation per tree; no statistical sample applies. The
denominator is the reader's own census over all root workflow files, printed by the test.

- **C1 (RED, local):** at `05958386` plus the new test file only —
  `UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/contract/test_workflow_permissions.py -q`
  FAILS naming `docs.yml`/`build-docs`/both scopes; collected count ≥ 1 (exit 1, not pytest's
  nothing-collected exit 5).
- **C2 (GREEN, local):** with the docs.yml fix applied, C1's command passes; then the full battery
  cold (fast triple + full suite + standards tripwires) — mandatory for any `.github/workflows/`
  change (rubric G2; drift-and-obligations obligation 5's cold-run clause).
- **C3 (CI, build half):** this slice's own PR run executes `build-docs` on `pull_request` under
  the narrowed grant and goes green, both artifact uploads included — the live proof the build job
  needs no write scope.
- **C4 (CI, publish half):** the first push-to-main `CI Docs` run after merge completes
  `publish-docs` green — `actions/deploy-pages` succeeds under the job-scoped grant, the
  `environment: github-pages` gate unchanged.

**SHIP** = C1 ∧ C2 ∧ C3 ∧ C4.
**KILL** = C4 red with a deployment denial on the deploy step (403 / "Resource not accessible by
integration") → the ported grant set is wrong for this repository; roll back the job block alone and
re-derive from the actual failure. Restoring the workflow-level `pages`/`id-token` lines is NOT an
acceptable remediation at any point — it reopens #509.
**UNDERPOWERED (measurement invalid, not a pass)** = C1 green on the unfixed tree (the check cannot
see the grant — fix the check before any conclusion), or the reader refusing to structure any
existing workflow file (check bug, not a posture signal).

What only CI can prove: C3/C4 (a real OIDC mint and Pages deploy against THIS repository's
environment — the mechanism is otherwise already proven live on the sibling repo, §4). Everything
in C1/C2 is locally reproducible by the builder.

## 7. Scope and deferrals

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | The #501 port: `timeout-minutes` on `build-docs` and the guarded, bounded child-process runner in `scripts/assemble_docs_site.py` | follow-on issue #501 (already open, carries the full scope) | fires when #501's slice merges (issue closes); no motion of this slice can substitute |
| D2 | The SDK twin's per-job concurrency split (build grouped `docs-<ref>` with cancel; deploy in a `pages` group that is never cancelled) — not ported; the gateway's ref-keyed workflow group (`docs.yml:27-29`) already keeps PR builds out of the main deploy's group | documentation here | a gateway main deploy is cancelled or starved with the `docs.yml:23-26` comment's named signature ("higher priority waiting request for pages exists") in the run log |
| D3 | Widening the pin beyond `pages`/`id-token` (e.g. `contents: write` on PR runs) or adding a sanctioned-exception register (codeql's `security-events: write` today) | documentation here | the first PR-reachable job that legitimately needs a write scope outside the two pinned ones (the SDK twin's `preview-docs` pattern arriving here) |
| D4 | Explicit `contents: read` floors for `ci.yml` jobs that declare no permissions block anywhere (they ride the repository-default token today) | documentation here | the next diff that adds or re-scopes a job in `ci.yml` |

## 8. Invariant and drift impact

- **No CTL/STO/CON/REG invariant is touched** — every anchor in `docs/internal/invariants.md` sits
  under `src/benchweave/` (control, state, contracts, registry); none reaches CI workflow files.
  **No new invariant**: this is repository posture, carried by the §5 pin plus the amended rows, not
  gateway runtime behavior.
- **Obligations walked (G5):** 28 (release-machinery change) — walked; `docs/internal/
  release-process-family.md` documents `package.yml`'s and `publish-ui-html`'s grant posture but
  says nothing about docs.yml token grants (its docs.yml mentions are `great-docs.yml` content),
  so no family-doc edit is owed; the obligation's spirit is served by surfaces 3-5 in §3. 5 — the
  cold full-suite clause is baked into C2. 4 — README's docs-workflow paragraph (`README.md:20`)
  makes no grant claim; no operator-doc motion owed. The G0 secret scan: the diff adds no key
  material.
- **On-disk formats/schemas:** none. No persisted surface moves — confirmed Tier 2, not Tier 3.

## 9. CI cost

Zero new lanes. One fast test rides the existing `gates` suite (~negligible). The review-time cost
is the rubric's own rule: one cold full battery for the workflow change (C2). The slice's PR gives
C3 for free; C4 costs one merge's deploy observation.

## 10. Top risks (each with its falsifier)

1. **The deploy fails under the ported grant set** (C4 kill direction) — falsifies the
   SDK-parity premise; the SDK twin runs identical action SHAs with exactly these two scopes in
   production, so prior probability is low, and the kill path is bounded (roll back one block).
2. **The reader under-approximates PR reachability** and a future exposed job reads as
   unreachable — mitigated structurally: exclusion is only "proven" by the recognized-conjunct
   list, everything else defaults to reachable. Residual: a novel-but-correct exclusion form
   produces a visible false positive, never a silent hole.
3. **The pin blocks a legitimate future need** (a PR job that should hold one of the two scopes) —
   by design it blocks loudly; the resolution is D3's exception register, not weakening the rule.
4. **Keyword drift at review time** (a commit message or fold comment reintroducing a Step-1
   keyword, re-tiering the slice) — mitigated by the disclosed scan above; the review re-derives
   independently either way.

## 11. Interaction with #501 (open, same file, NOT absorbed)

None mechanical. #501 adds `timeout-minutes` to the same `build-docs` job header and bounds
child-process calls inside `scripts/assemble_docs_site.py`; this slice moves permission keys on
`publish-docs` and the workflow header. No shared lines; either order lands, the second rebases
trivially. The two findings complement: #509 removes the capability grant from PR builds; #501
bounds their resource consumption. #501's marker-watching port (its own acceptance shape, per its
issue text) stays entirely in its slice.
