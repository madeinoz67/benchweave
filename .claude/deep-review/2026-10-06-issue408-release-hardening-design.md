# Issue #408 — release-pipeline hardening: the bump carries its blast radius

**Design record, 2026-10-06.** Gateway issue
[`madeinoz67/benchweave#408`](https://github.com/madeinoz67/benchweave/issues/408)
(owner directive 2026-10-05). Scope shaped by the issue's field-research comment
(verified primary sources; its preference order — structurally impossible >
regenerated-by-bump > gated-on-release-PR, discipline in no exemplar — is a
design constraint here, not a suggestion) and the team lead's scope note
(four items, branches `feat/issue408-release-cut` SDK and
`feat/issue408-declared-pin` gateway).

**Not retrofitted onto the v0.8.0 train.** The v0.8.0 gateway pairing is in
flight on the `feat/issue393-adc-highrate` branch family under the current
exact-equality lane and is green now that the tag exists. The exit gate is the
NEXT SDK release: green-first-time end to end.

---

## 0. Root causes, established from the code (not assumed)

Four incident classes, each traced to its line:

**(a) Scaffold byte-parity fixtures redden on the bump.** The fixture trees
under `tests/fixtures/scaffold_expected/{base,ui}/` are a pure function of
(template, SDK version, OTDP version) — the answers/descriptor/pyproject pins
carry those versions *by design* (`tests/test_scaffold_copier.py:1-28`, the
regeneration docstring). Detection exists (the byte-parity suite); **motion
does not** — nothing binds the bump commit to the fixture regen, so v0.8.0
needed a separate repair commit (`c4fd9cd` "regenerate the scaffold fixtures
at 0.8.0") after CI reddened. The defect is the missing *declared-surface
registry*, not a test gap.

**(b) Docs-bucket registration ordering.** `scripts/assemble_docs_site.py`
builds each version's bucket **from that version's own tag** and refuses any
release tag absent from the working tree's `great-docs.yml` `versions:` list
(`main()`: the `missing` refusal; `release_tags()` reads local tags at
`:115`, `yml_version_tags()` at `:134`; `isolated_build()` renders
`--from-repo … --branch <tag>`). Therefore the tag's own tree must already
contain its registration — registration and tag-creation are two operator
actions held together only by documented ordering
(`docs/internal/release-review-matrix.md:23-32`, the v0.0.4 receipt: a tag
missing itself builds zero buckets). The two-phase walk (phase 1 = release
PR, phase 2 = tag commit) is the correct shape; what is missing is a machine
that **owns both phases as one transaction** and lets CI **rehearse phase 2
before the tag exists**.

**(c) The gateway `sdk-drift` lane is structurally red on legitimate
branch-tip gitlinks.** `scripts/check_sdk_submodule_drift.py` `evaluate()`
compares the committed gitlink against the SDK remote's **latest `vX.Y.Z`
tag deref with exact equality**. Any gitlink that is not exactly the latest
tag — the era-bind mid-train mounts (gitlinks at bundle-matching non-tag
commits), or the post-merge/pre-tag window — is red. The CI map's own row
admits it: "between an SDK release tag landing and this repository's pointer
bump the lane is RED and every open PR is unmergeable"
(`docs/internal/drift-and-obligations.md` CI map, `sdk-drift` row). The
freshness law keys a local fact (the gitlink) to a remote-controlled moving
target (the latest tag). That is the coupling the owner's directive kills.

**(d) The lock anchor is written by release machinery but verified only
gateway-side.** `standards-lock.json` `compatibility.sdk` must equal the
release's own `pyproject.toml` version pre-tag (the #187 fork (a) ruling;
CON-12's amendment chain: `pyproject@pin → lock → mirror`, enforced by the
gateway's `make check-sdk-standards` → `sdk_version_unanchored`). The SDK's
own self-check does NOT cover it: `benchweave-sdk sync-standards --check`
runs `_verify_self_consistency` → `_verify_state` → `_verify_tree` +
`_verify_marker_mirror` (`src/benchweave_sdk/standards_sync.py`) — lock ↔
vendored tree ↔ marker mirror, **no pyproject read**; and `sync(bundle=None)`
without `--check` is refused outright (`cli.py:356-373`,
`bundle_required`). So v0.7.0's skipped anchor was invisible SDK-side until
the gateway pairing reddened, forcing the v0.7.1 re-tag. The gap: no
SDK-side, PR-time check of anchor parity.

**The common root:** every version-bearing surface is *discovered by red CI
at bump time* instead of being *part of the bump*. All four fixes make the
release transaction own its blast radius.

---

## 1. The field-research mapping (constraint, decided)

Per the issue's research comment, adopted as constraints:

1. Fixtures that intentionally pin versions → **regenerated-by-bump**
   (declared in the transaction, cargo-release-style occurrence-validated
   substitution). Masking is rejected — our fixtures' job IS pinning bytes.
2. Registration ordering → the tool **owns both phases as one command**
   (the mike/Docusaurus same-transaction property, at tool level because
   git_ref assembly forces two commits).
3. Drift lane → the **declared-pin** pattern (OTel `*-pin`: pin + gitlink
   move in the same commit; CI checks pointer-vs-pin; releases freeze what
   the pin declares). Any exemption renders as an **always-run check exiting
   0 with a visible annotation** — never a skipped job (a skipped required
   check stays Pending and blocks merge).
4. Anchor parity → **release-PR CI**, not a tag-time gate (cargo-release's
   pre-release-hook shape, moved to the PR).
5. Dynamic versioning **rejected** (the research's late-adoption pitfalls
   buy nothing for deliberately pinned surfaces). This is a decision, not a
   deferral.

---

## 2. Slice map (three PRs, two repos, SDK first)

| Slice | Repo / branch | PR | Contents |
|---|---|---|---|
| S1+S4 | SDK `feat/issue408-release-cut` | PR-A | `scripts/release_cut.py` + `Makefile` wrapper + `tests/test_release_cut.py`; the test-surface census rows in the release-review matrix; skill walk update |
| S2 | gateway `feat/issue408-declared-pin` | PR-B | declared-pin drift lane + `.gitmodules` pin + test rewrite + family/obligations/AGENTS amendments |
| S3 | SDK, stacked on PR-A | PR-C | `release-preflight.yml` (the release-PR rehearsal job) + plan-consumption docs |

Two-repo discipline: PR-A and PR-C are SDK-side (SDK PRs open first, stacked
where dependent); PR-B is the gateway side and also carries the
`docs/internal/release-process-family.md` motion that S1/S3 owe under
obligation 28 (a release-machinery change, any line, moves the family doc —
folding both motions into one gateway PR avoids a docs-only second train).

---

## 3. S1 — `make release-cut VERSION=x.y.z`: one transaction (SDK)

### 3.1 Where it lives

`scripts/release_cut.py` is the mechanism (argparse, `--verify` mode,
`--phase2-only` regen mode); the SDK **Makefile is new and three lines**
(`release-cut: ; uv run python scripts/release_cut.py $(VERSION)` plus the
same `UV_PROJECT_ENVIRONMENT := venv` pin the gateway Makefile carries). The
SDK repo has no Makefile today (verified — root listing); adding a minimal
one is justified because the issue's own interface is `make release-cut
VERSION=x.y.z` and the wrapper costs nothing. **Owner fork F1** (script-only
vs Makefile wrapper) — recommendation: ship both; the script is the
testable surface.

### 3.2 The declared-file registry — shape decision

**A `DECLARED_SURFACES` registry inside `scripts/release_cut.py`** (a typed
list of entries), not inline annotations in the target files and not a
separate JSON manifest. Precedent: `scripts/count_version_literals.py`'s
`REGISTER` — the in-tree "exemption list with teeth" where each row carries
its reason and its exact expected count, and a new site fails the gate until
the row is edited (a visible editorial diff). Declare-once is satisfied: the
registry is the single declaration; `--verify` and the CI preflight (S3)
consume the same list. Inline annotations are rejected because they pollute
published surfaces (README, `website/index.html` ships to the public site).
A separate data file is rejected because the entries carry regexes and
counts — code-adjacent data — and the REGISTER precedent keeps such data in
the script beside its tests.

Each entry: `path`, `kind` (substitution | regen | derived), `reason`
(matrix row reference), and for substitutions a list of
`(pattern, expected_count)` where pattern anchors on the OLD version.
**Occurrence validation is the cargo-release discipline**: a pattern must
match exactly `expected_count` times or the cut aborts naming file, pattern,
expected and found counts.

### 3.3 The registry's initial content — the v0.8.0 ground truth

Derived from the actual v0.8.0 transaction (`343d4a9` walk commit +
`c4fd9cd` fixture commit + `ca34b3f` phase-2 tag commit, verified via
`git show --stat`):

| # | Surface | Kind | Pattern (expect) | Evidence |
|---|---|---|---|---|
| 1 | `pyproject.toml` | subst | `^version = "<OLD>"` (1) | `343d4a9` |
| 2 | `uv.lock` | subst | root-package block `name = "benchweave-sdk"\nversion = "<OLD>"` (1) | `343d4a9` (2-line diff) |
| 3 | `README.md` | subst | `SDK <OLD>` baseline sentence (1) — `README.md:5` | `343d4a9` |
| 4 | `website/index.html` hero | subst | `SDK <OLD> ·` status line (1) — `:66` | `343d4a9` |
| 5 | `website/index.html` tagline | subst | `Compatibility: SDK <OLD> against` (1) — `:441` | `343d4a9` |
| 6 | `standards-lock.json` | subst | `"sdk": "<OLD>"` in `compatibility` (1) | `343d4a9` (the lock anchor) |
| 7 | `tests/fixtures/scaffold_expected/` | **regen** | render both arms, rewrite answers `_src_path`/`_commit` to the canonical pin | `c4fd9cd` |
| 8 | `docs/internal/release-review-matrix.md` | derived | append the result-record scaffold | `343d4a9` |
| 9 | `great-docs.yml` + selector | **phase-2 patch** | see 3.5 | `ca34b3f` |

Row 1b (user-guide sentence) is currently n-a (glob since #102) and stays a
walk row, not a registry row — the registry holds surfaces that MOVE at every
release; the matrix holds surfaces that MIGHT.

### 3.4 The transaction (what it does, in order)

1. **Preflight**: repo root; clean tree (`git status --porcelain` empty);
   `VERSION` parses as `X.Y.Z` and is strictly greater than the current
   pyproject version; previous tag discovered (`git tag -l` + semver sort —
   same ordering discipline as `latest_release()`).
2. **Occurrence-validated substitutions** over rows 1-6. Any mismatch aborts
   the whole cut with the named pattern and counts — nothing is written
   before all patterns validate (two-pass: validate every pattern, then
   write).
3. **Fixture regeneration** (row 7): render `base` and `ui` arms via the
   Python API (`create_project` / `create_ui_resources` — no shell), under a
   **resolved** tempdir. The `/var` symlink gotcha is designed in:
   `tempfile.mkdtemp()` then `Path.resolve()` before rendering, because the
   scaffold's path validation rejects symlinked roots on macOS (`/var/folders`
   → `/private/var/folders`; the docstring procedure and the 2026-10-05
   receipt both name it). Then rewrite each answers file's `_src_path`/
   `_commit` to the canonical pin (`v<NEW>` + the canonical template URL,
   matching `_expected_answers` in `tests/test_scaffold_copier.py`).
4. **Anchor verification**: run `uv run benchweave-sdk sync-standards
   --check` — proves the edited lock is still self-consistent (lock ↔ tree ↔
   mirror). The anchor *parity* itself (row 6's substitution) is re-proved by
   `--verify` (3.6) because the SDK's own `--check` does not read pyproject
   (root cause d).
5. **Matrix record scaffold** (row 8): append `## Result record — vX.Y.Z
   (<date>)` with every row pre-filled: rows 1/2/4/5 "updated → X.Y.Z by
   release-cut (occurrence-validated)", row 3/6 "PHASE-2 — patch staged at
   `.release/phase2-vX.Y.Z.patch`", row 7 the computed contributor window
   (`git log <prev>..HEAD`, authors minus owner/bots, empty-is-a-result),
   row 8 the recorded note, row 9 computed from the lock diff vs the previous
   tag (byte-compare `standards-lock.json` minus `compatibility` → "n-a" or
   the served-set class). The walk CONFIRMS; it no longer discovers.
6. **Phase-2 patch generation** (row 9): compute the tag-commit diff —
   insert the new `versions:` block at the head of `great-docs.yml:551`
   (`tag`/`label`/`latest: true`/`git_ref`), flip the existing single
   `latest: true` → `false` (validated: exactly one exists today), insert
   the new selector `<option value="docs/">vX.Y.Z (latest)</option>` as the
   first option and strip ` (latest)` from the old first option
   (`website/index.html:342`). Emit:
   - `.release/phase2-vX.Y.Z.patch` (unified diff, **committed with the
     release PR** — the preflight applies it), and
   - `.release/plan.json` (`version`, `prev_tag`, `base_sha`, `surfaces`)
     — the machine-readable plan S3 consumes.
   The v0.8.0 exemplar is `ca34b3f`: 2 files, +7/−2. The patch touching
     anything other than those two files is refused at generation.
7. **Post-cut smoke** (always): re-run every occurrence check expecting the
   NEW version; run `uv run pytest tests/test_scaffold_copier.py -q` — the
   byte-parity suite green on the cut tree is the in-transaction proof that
   the regen swept everything.

### 3.5 What the command REFUSES

No `git commit`, no tag creation, no push, no publish, no network. Its only
git verbs are read-only (`status`, `tag -l`, `log`, `rev-parse`). The cut
leaves the working tree staged-for-review; the operator commits. `--help`
states this. It also refuses: a non-increment VERSION, a dirty tree, any
occurrence mismatch, a missing declared file, a phase-2 patch that would
touch a third file, and a re-cut over an already-cut tree (pyproject already
at NEW) without `--force`.

### 3.6 `--verify` mode (ships in S1; consumed by S3)

Read-only: given the working tree, assert (i) every substitution pattern
matches `expected_count` times against the CURRENT version, (ii) the anchor
— `standards-lock.json` `compatibility.sdk` == pyproject `version` (closes
root cause d SDK-side), (iii) `.release/phase2-vX.Y.Z.patch` exists and
`git apply --check` succeeds, (iv) the patch's file set is exactly
`{great-docs.yml, website/index.html}`. Exit 0/1. This is the release-PR
gate's script half.

---

## 4. S2 — the declared-pin drift lane (gateway)

### 4.1 The pin

`.gitmodules` gains one key beside the gitlink's own metadata:

```
[submodule "packages/sdk"]
	path = packages/sdk
	url = https://github.com/madeinoz67/benchweave-sdk.git
	pin = v0.8.0
```

The pin carries EITHER `vX.Y.Z` (the normal, released state) OR a 40-hex SHA
(the declared-train state — the era-bind mounts, the post-merge window). The
pin IS the declaration: writing a SHA is how a train declares itself.

**Placement decision (owner fork F2).** `.gitmodules` recommended: it is the
submodule's metadata home; the existing checker already reads it
(`configured_remote()` — the governor-F1 single-home precedent); unknown
`submodule.<name>.*` keys are inert to git tooling; `render_matrix` reads
only the `url` for Sources, so CON-12's purity is untouched (the matrix
parity tests stay green). Rejected: `standards/standards-manifest.json`
(standards surface — governor dispatch + Tier-3 path motion for a mount
fact; semantic mismatch) and a standalone file (a new drift surface for no
gain).

### 4.2 The check — new exit contract

`scripts/check_sdk_submodule_drift.py` is rewritten around a three-input
`evaluate(gitlink, pin, ls_remote_output) -> (code, message)`:

- **exit 0 — green**: `gitlink == pin` (SHA pins: local string compare; tag
  pins: pin resolved to its peeled commit via the existing deref machinery —
  `latest_release()`'s peeled-line handling is reused verbatim). Emits a
  `::warning::` annotation when the pin trails the latest release tag
  (`pin vX.Y.Z trails latest vA.B.C — pairing pending`) or names a non-tag
  SHA (`non-tag pin <sha> — declared train or unpaired mount`), and a
  `::notice::` when freshness is unknowable (fetch failed — the annotation
  degrades, the verdict does not).
- **exit 1 — red**: `gitlink != resolved(pin)`. The pin and gitlink move in
  the same commit, **enforced** — a pin disagreeing with the mount is red.
- **exit 2 — indeterminate**: no gitlink at HEAD, pin key absent/malformed
  (an undeclared mount fails closed — every pointer PR must carry the pin),
  tag-pin resolution failed (network; identical sensitivity to today, never
  worse), undecodable bytes (the existing decode-raise arms keep their
  contract).

**What improves structurally**: the red decision is local for SHA pins
(mid-train pushes stay green even offline — today they are red by
construction), and network failure can no longer produce a red-or-green
verdict in the SHA-pin case at all. The freshness signal moves from
hard-red to annotation — the honest trade, see Risks.

### 4.3 The lane

`.github/workflows/ci.yml`'s `sdk-drift` job (run step `:286`) is unchanged
in wiring — same script path, same always-run posture (no `if:` skip; the
GitHub skipped-required-check constraint). The job comment block is rewritten
to the new contract. `tests/unit/test_check_sdk_submodule_drift.py` moves
with it: the pure-parse arms (annotated/lightweight/semver-order/prerelease)
survive unchanged; the verdict arms rebase onto `evaluate(gitlink, pin,
ls_remote)`; the black-box `_repo_pair` fixture gains a `.gitmodules` pin
writer; new arms: pin≠gitlink → 1; SHA-pin + older latest tag → 0 with
warning text asserted; pin absent → 2; trailing tag-pin → 0 with warning.

### 4.4 The pairing motion (unchanged) and its proof

The gateway pairing PR still advances gitlink + regenerated SDK lock +
`sdk_compatibility` mirror + re-rendered matrix in one merge (obligation 7),
now also editing the pin in the same commit — one more line in a motion that
already moves together, enforced red-by-construction on omission.

### 4.5 Docs that move with S2 (obligation 28 + the CI map)

- `docs/internal/release-process-family.md`: the SDK→gateway edge clause
  ("red lane … on every pull request") is rewritten to the declared-pin
  edge; gateway-cut readiness condition 2 and walk row 6 become
  "`sdk-drift` green **and no trailing-pin annotation**" (green alone no
  longer proves the window closed — that is the intent change, disclosed);
  setup item 4's required-checks note gains "compatible with the always-run
  annotation shape".
- `docs/internal/drift-and-obligations.md`: obligation 7's mount-staleness
  clause + the CI-map `sdk-drift` row (its "Cost accepted at review (#347)"
  admission is repealed — the cost this design removes).
- `AGENTS.md` (gateway): the order rule — SDK PRs merge → release cut →
  gateway pointer PR — named beside the two-repo discipline section.

---

## 5. S3 — publish pre-flight as release-PR checks (SDK)

### 5.1 Which pre-flight steps run on the PR path

A new `.github/workflows/release-preflight.yml`, `on: pull_request`
(**always runs, exits 0 fast with a `::notice::` "not a release PR" when
`.release/plan.json` is absent** — never condition-skipped; the research's
GitHub constraint). When present:

1. `uv run python scripts/release_cut.py --verify` — occurrence parity,
   anchor parity (the v0.7.0 class dies here), patch applicability,
   patch-surface assertion.
2. `uv run benchweave-sdk sync-standards --check` — lock ↔ tree ↔ mirror
   (the build job's existing step, run at PR time).
3. `uv build` — `hatch_build`'s vendored-tree-vs-lock verification rides the
   build (the publish `build` job's step, PR-time).
4. `uv run python scripts/verify_release_tag.py vX.Y.Z --pyproject
   pyproject.toml` — the tags↔pyproject parity the publish job enforces at
   tag time, proven against the tag that WILL be cut.
5. **The phase-2 rehearsal** (the ordering class dies here): apply the
   staged patch (`git apply`), make a synthetic commit with a runner-local
   identity, `git tag vX.Y.Z` locally, then
   `uv run python scripts/assemble_docs_site.py --repo-url "$PWD" --dest
   "$RUNNER_TEMP/site"`. The local `--repo-url` is load-bearing: the
   assembly's `isolated_build` fetches per-tag refs from the repo URL, and
   the simulated tag exists only locally (`release_tags()` reads local tags;
   `ref_has_config()` resolves them locally; prior tags resolve from the
   fetched history). `verify_tree` then asserts the new bucket, the selector
   honesty, and the `(latest)` label — the exact tag-time behavior,
   rehearsed.
6. Assert the simulated tag commit's diff is exactly the staged patch
   (registration-only, structurally).

Not moved to the PR path: the 5-OS smoke matrix, PyPI publish, tap, and
changelog jobs — they are release-triggered by nature and unchanged.

### 5.2 The theorem and its residual

A green release PR means: the tree that will be tagged passes build,
parity, anchor, and (via the rehearsal) registration — so the tag commit is
registration-only, the class that cannot fail. **Disclosed residual**: the
preflight proves the STAGED patch is sufficient, not that the operator
applies exactly it at tag time; the tag-time docs build remains the backstop
(it fails loudly on any divergence — the v0.0.4 behavior). Mitigation: the
release-review skill's step 2 points at `.release/phase2-vX.Y.Z.patch` as
the tag commit's content. Second residual: if main moves between PR-merge
and tag-cut, `git apply --check` fails loudly; the answer is
`release-cut --phase2-only` regenerated against the new base (named in the
skill), not hand-editing.

CI cost: one always-run job — ~5 s on non-release PRs (marker check + uv
cache probe), ~4 min on release PRs (sync + build + assembly). No new
scheduled work.

---

## 6. S4 — census extension: version-bearing TEST surfaces (SDK)

The matrix gains a **"Test surfaces" section** (same file, same walk — a
sibling census file would be a second instrument to forget; one walk is the
discipline):

| # | Surface | Machine truth | Motion / classification |
|---|---|---|---|
| T1 | `tests/fixtures/scaffold_expected/base/**` | `create_project` render at the pinned version | release-cut regen step (R-2); tripwire = the byte-parity suite |
| T2 | `tests/fixtures/scaffold_expected/ui/**` | `create_project(with_ui=True)` + `create_ui_resources` | same |
| T3 | `tests/test_scaffold_copier.py` | consumes T1/T2; its docstring carries the regen procedure | docstring moves only when the procedure changes — now points at `make release-cut` as the procedure |
| T4 | `tests/test_scaffold_update.py` synthetic `v0.8.0` tags | scratch-repo fixtures fabricating "some released tag" | **inert by design** — no bump motion; the row exists so the walk never wonders (the honest-negative row) |

Closing clause mirroring the gateway's obligation 18: a new bump-sensitive
TEST surface is a defect — register it here AND in `DECLARED_SURFACES`, or
make it derived. The registry is the enforcement (an unregistered
bump-sensitive surface is by construction one release-cut does not sweep —
the mutation arm m3 proves the tripwire catches exactly that). The gateway's
obligation-18 census is untouched (different repo, doc surfaces; no
overlap).

---

## 7. Invariants, drift, and surfaces

- **No CTL/STO/CON/REG invariant changes.** CON-12 is untouched: the render
  purity, the manifest mirror, and the `pyproject@pin → lock → mirror`
  anchor chain all stand; the drift lane was never a CON-12 subject.
  CON-13 untouched (website stamps — the SDK's website hero is not the
  gateway's `{{stg-*}}` token surface; the SDK repo has its own
  stamp hygiene outside these invariants).
- **Gateway `docs/internal/drift-and-obligations.md`**: obligation 7
  amendment (mount-staleness → declared-pin; pairing motion + one pin line)
  and the CI-map `sdk-drift` row rewrite — both in S2.
- **Gateway `docs/internal/release-process-family.md`**: moved by S2 (edge
  clause, readiness condition, walk row 6) — and this motion also discharges
  obligation 28 for S1/S3's SDK-side machinery changes (single family-doc
  train).
- **Gateway `AGENTS.md`**: order rule (S2).
- **SDK**: `docs/internal/release-review-matrix.md` (census + scaffold
  mechanics), `.claude/skills/release-review/SKILL.md` (the walk gains:
  run `make release-cut`, confirm scaffolded rows, apply the staged patch at
  the tag commit).
- **On-disk formats**: `.gitmodules` gains one config key (inert to git);
  `.release/plan.json` is a new small CI-consumed format (defined and
  consumed within this design's slices; not runtime-persisted state).
  Disclosed for the tier call below.
- **Standards corpus**: zero bytes move. `standards-lock.json`
  `compatibility.sdk` moves as the certified-version field it already is
  (the #189 pairing shape, machine-written by release machinery since the
  #187 fork (a) ruling). The standards-governor dispatch for the SDK slices
  is a build-time convention call — recommended ON for PR-A (the lock is
  standards-adjacent and the conservative reading of the mandate covers it);
  named in the PR body either way.
- **SDK surfaces owed by S1**: none beyond those listed (no README
  instruction-section changes — `make release-cut` is operator-facing, the
  skill is its doc).

---

## 8. Review tier and the Step-1 keyword scan (#254)

Tier rules: `docs/internal/review-rubric.md` Step 1 — Tier 3 if the diff
text contains any of `threading, asyncio, subprocess, sha256, hashlib,
migrate, recovery, protection`; Tier 2 for other `.github/`, `scripts/`,
`tests/` changes; Tier 1 docs-only.

**Per-slice call (max tier across the design: 3):**

- **S1+S4 (PR-A): TIER 3** — keyword `subprocess`. Scan over the expected
  diff (new `scripts/release_cut.py` ~5 occurrences by design — one import,
  three read-only git call sites, one docstring mention; new
  `tests/test_release_cut.py` ~4 — black-box CLI arms; Makefile, matrix,
  skill: 0): **subprocess ≈ 9; threading 0; asyncio 0; sha256 0; hashlib 0;
  migrate 0; recovery 0; protection 0.** (Counts over the expected-diff
  inventory; the review re-derives the scan on the actual diff — the
  #254 record rule.)
- **S2 (PR-B): TIER 3** — keyword `subprocess`. Measured on the files the
  rewrite carries (whole-file rewrite ⇒ the diff carries current bytes):
  `scripts/check_sdk_submodule_drift.py` **subprocess 8**;
  `tests/unit/test_check_sdk_submodule_drift.py` **subprocess 10**; plus
  new pin-resolution code ~2 and test additions ~3; `.gitmodules` +1 line,
  `ci.yml` comment rewrite, three docs, `AGENTS.md`: 0. **Total subprocess
  ≈ 23; all other keywords 0.**
- **S3 (PR-C): TIER 2** — `.github/` path rule; keyword scan over the
  expected workflow + docs diff: **all eight keywords 0.** (`plan.json`
  format disclosed in §7; if the reviewer reads a new CI-consumed format as
  a persisted-format surface, the slice escalates to Tier 3 — stated so the
  review can make the call mechanically rather than discover it.)
- **S4**: rides PR-A (Tier 3 by S1); standalone it would be Tier 2
  (test-tree docstring + docs).

Tier 3 ⇒ the two-lane adversary standing order applies to PR-A and PR-B.

---

## 9. MEASURABLE proof — the dry-run harness (pre-committed)

A throwaway harness (never committed, never a CI job — the one-off benchmark
rule): a scratch clone of the SDK repo replaying the v0.8.0 bump against the
new tooling, plus mutation arms. Runs once; numbers + verdict recorded on
#408.

### 9.1 The replay (AR-1)

Setup: scratch clone at `343d4a9^` (the pre-bump tree); copy
`scripts/release_cut.py` + `Makefile` + registry in from the branch; run
`make release-cut VERSION=0.8.0`.

- **R1 (set equality)**: the resulting `git status --porcelain` file set
  must EQUAL the historical transaction set — `343d4a9`'s six files ∪
  `c4fd9cd`'s fixture files ∪ the tool's own emits (matrix scaffold content,
  `.release/phase2-v0.8.0.patch`, `.release/plan.json`). Any ± file is a
  finding, adjudicated before ship (a miss = under-declared registry; a
  surplus = over-declaration to justify or remove).
- **R2**: `uv run pytest tests/test_scaffold_copier.py -q` GREEN on the
  replayed tree (the fixture class cannot recur via a complete cut).
- **R3**: `uv run benchweave-sdk sync-standards --check` GREEN (the anchor
  was swept).
- **R4**: `uv run python scripts/release_cut.py --verify` exit 0.
- **R5 (phase-2 fidelity)**: apply the generated patch; parse
  `great-docs.yml` + the selector; assert semantic equality with `ca34b3f`'s
  versions list and selector options/labels (parsed-compare, not byte —
  historical whitespace is not the claim).

### 9.2 The mutation arms (AR-2) — each must FAIL loudly

- **m1** registry row removed (website tagline) → cut or `--verify` fails
  naming the stale surface.
- **m2** expected-count doctored (README 1→2) → cut aborts at validation.
- **m3** fixture-regen step dropped from the registry → post-cut
  byte-parity suite RED (the tripwire catches what the tool skipped — proves
  the census/registry split has teeth and the byte-parity tests remain the
  backstop).
- **m4** pin ≠ gitlink → drift check exit 1 (unit).
- **m5** pin = SHA, latest tag older → exit 0 AND the `::warning::`
  annotation text present (unit).
- **m6** pin key absent → exit 2 (unit).
- **m7** anchor skipped (compatibility.sdk left at OLD — the v0.7.0 defect
  replayed) → `--verify` RED.
- **m8** phase-2 patch missing the selector edit → the simulated assembly's
  `verify_tree` RED (the v0.0.4 class replayed).

### 9.3 The acceptance rule (pre-committed BEFORE any tooling is built)

Metric: zero red lanes attributable to the bump, on the replayed v0.8.0
scenario, with all eight mutations red.

- **SHIPS if**: R1 set-equal (every ± adjudicated), R2-R5 green, m1-m8 all
  red-as-specified.
- **DIES if**: the replay cannot produce the historical set without
  registry edits that amount to re-implementing the release (the tool is the
  wrong shape); any mutation m1-m3/m7/m8 stays green (the guard is
  theater); m4-m6 disagree with the exit contract.
- **UNDERPOWERED, not conclusive, if**: the registry passes the replay only
  because it was derived FROM the v0.8.0 diff (circularity — the registry
  then encodes one release's shape). Mitigations, also pre-committed: the
  registry is cross-checked against the matrix rows and the census closing
  clause (not just the one diff), m1-m3 probe generalization, and the FIELD
  CONFIRMATORY RUN is #408's own exit gate — the next SDK release,
  green-first-time. If that release reddens on a surface neither registry
  nor census names, the measurement was underpowered and the miss becomes a
  new census row with its motion mechanism — that outcome is a recorded
  result, not a pass.

Sample size, stated honestly: one replayed historical scenario, eight
mutation arms, two replayed historical defects. The historical baseline for
contrast: the real v0.8.0 run produced ≥2 red classes (fixtures; the drift
window) plus the v0.7.0 anchor re-tag and the v0.0.4 ordering failure in the
family's history.

---

## 10. Top risks, each with its falsifier

1. **The freshness trade is a real weakening** (trailing pins become
   annotated-green, not red). Falsifier: a gateway cut shipping over a
   trailing pin unnoticed. Mitigations: the family-doc readiness condition
   now reads the annotation; the walk row names it; the annotation is
   visible on every run of the lane. If a cut ships over a trailing pin
   anyway, the walk row was the wrong enforcement point — reopen with a
   "trailing by >1 release is red" rule (accepting network dependence in
   that arm only). **Owner fork F3**: whether the annotation gates the
   gateway cut (recommended: as a walk row, not a machine gate).
2. **Registry circularity / next-release novelty** (§9.3's underpowered
   case). Falsifier: the next release reddens on an uncensused surface.
   Answer: the miss becomes a census row + registry entry; the exit gate
   holds until a release goes green-first-time.
3. **The simulated-tag rehearsal diverges from real tag-time behavior**
   (local `--repo-url` builds differ from remote fetches — submodule
   semantics, shallow context). Falsifier: R5/verify_tree green in
   rehearsal but the real tag-time build red. Mitigation: the rehearsal
   runs the SAME assembly entry point with the same verify; the tag-time
   build remains the backstop; if they diverge, the divergence is itself a
   filed defect (the rehearsal's `--repo-url` is the only delta and is
   named).
4. **`great-docs.yml` comment preservation** under programmatic edit (the
   file carries inline comments; a naive writer could eat them).
   Falsifier: the phase-2 patch diff shows comment loss vs `ca34b3f`'s
   shape. Mitigation: line-anchored insertion + single-key flip (no
   re-serialization); R5 compares against the exemplar.
5. **The `.gitmodules` pin key collides with future git semantics** for
   `submodule.<name>.*`. Falsifier: a git release assigns meaning to
   `pin`. Unlikely (unlike `path/url/branch/update/shallow/ignore/
   fetchRecurseSubmodules`); if it happens, the key renames in one commit —
   the check reads it by name in one place.
6. **Operator bypass** — hand-editing around the tool (the discipline
   trap). Falsifier: a release PR without `.release/plan.json` (the
   preflight degrades to notice — cannot force the tool's use). This is the
   disclosed residual of the whole design: the tool makes the right path
   the easy path; the walk + preflight make the un-tooled path visible
   (a release PR that skips the marker carries no rehearsal evidence —
   reviewable at a glance). Not solvable without required-checks adoption
   (family doc item 4, the owner's standing call).

---

## 11. Deferrals (named)

- **D1**: bot automation of the gateway pairing PR (Renovate submodule
  shape) — the pin makes such PRs green whenever they arrive; automation is
  convenience, not correctness.
- **D2**: required-status-checks adoption — unchanged, owner's call (family
  doc setup item 4); the always-run/exit-0 design is compatible with it.
- **D3**: extending release-cut to the gateway line's own cut — the gateway
  has no release yet (#380's premise correction); revisit at the first
  gateway cut.
- **D4**: ui-html line integration — that line keeps its own authority doc.
- **D5**: `.release/` artifact cleanup post-tag (the patch + plan stay as
  the tag commit's provenance record; deletion is optional tidiness).
- **D6**: CONTRIBUTING.md release section — the skill + matrix are the
  operator surfaces; a contributor-facing rewrite is a docs train of its
  own.
- **D7**: `release-cut` handling a MINOR-vs-PATCH class decision — the
  class is asserted by the sync machinery (`sdk_bump_class_invalid:`) and
  the walk records it; the tool refuses to GUESS a class (row 9 reports).
  Class automation deferred with the served-set machinery it would wrap.

---

## 12. What the maintainer must decide (owner forks)

- **F1**: `release-cut` home — Makefile wrapper + script (recommended; the
  issue's own interface is `make release-cut`) vs script-only.
- **F2**: pin-field placement — `.gitmodules` (recommended; §4.1) vs
  standards-manifest vs standalone file.
- **F3**: does the trailing-pin annotation gate the gateway cut? —
  recommended: family-doc walk row + readiness condition (procedural,
  visible), not a machine gate; the machine-gate alternative accepts
  network-dependent red.
- **F4**: standards-governor dispatch on PR-A (recommended ON — the lock
  motion is standards-adjacent; conservative reading of the mandate).


---

## Addendum (2026-10-06, fold wave 2 — the section-8 keyword-scan correction)

Section 8's S2 scan estimated the checker's `subprocess` occurrences at 8
over the expected diff; the shipped checker carries 5 (the rewrite
consolidated the three readers' subprocess plumbing into one `_run_git`
entry point — fewer call sites than the pre-rewrite whole-file estimate
assumed). The test file's count (10) held. Measured on
feat/issue408-declared-pin at the fold-wave tip; the section-8 text above
is frozen as written — this addendum is the correction of record. The
tier call (Tier 3 via the `subprocess` keyword) is unaffected: the keyword
is present at any count.


---

## Addendum 2 (2026-10-06, wave 3 — the release-cut referee's two corrections of record)

**Section 9.2, m1's failure modes (F7).** The m1 spec — "registry row
removed -> cut or --verify fails naming the stale surface" — is met only
at the committed-test layer (the pattern-level census arm). At RUNTIME,
with the website-tagline pattern removed, cut AND --verify both exit 0
(referee-captured, independent of this branch's own m1 finding): the
tool cannot see what it does not declare, and its post-cut smoke
validates the same (now smaller) registry. The runtime hole stands
disclosed; the census arm is the tripwire that makes the REMOVAL loud.

**Section 9.3, the underpowered-case disclosure (F4).** "A miss becomes
a new census row with its motion mechanism" assumed a miss REDDENNS
something. The OPEN-WORLD class never reddens anything: a NEW
version-bearing file, or an unpatterned version mention inside a
registered file, passes every current gate permanently
(count_version_literals scopes src/ only; the census covers TEST
surfaces only; the registry covers declared files' declared patterns).
This addendum corrects the disclosure — the failure mode for this class
is SILENT PASS, and the carrier (a tree-wide version-literal census
gate) is filed as its own issue.
