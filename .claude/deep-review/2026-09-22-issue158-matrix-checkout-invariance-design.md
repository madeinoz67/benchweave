# Issue #158 — compatibility-matrix render must be a pure function of committed state

Status: DESIGN (increment-designer, dispatched 2026-09-22). Public-safe per the
deep-review triage rule: mechanism and measurements only; no person, client, bench, or
install identifiers. The issue reporter is referenced as "a contributor".

## 1. Root cause — verified, not assumed

`docs/compatibility-matrix.md` is a generated artifact gated by
`benchweave.standards matrix --check` (CI `gates` and `package` jobs via
`make check-sdk-standards`). The render, `render_matrix()` in
`src/benchweave/standards/matrix.py:28`, pulls **three** inputs from checkout-local
state, not from committed state:

1. **Sources column — main URL**: `_origin_url(root)` (matrix.py:91) runs
   `git config --get remote.origin.url` in the checkout root and normalises
   (`git@` → `https://`, strip `.git`). On a fork, origin is the fork, the committed
   matrix (correctly) names the upstream repos, `check_matrix()` (matrix.py:67)
   reports `stale_matrix` against a correct file. Regenerating on the fork bakes fork
   URLs into a committed artifact — which then fails upstream CI. This is the
   contributor-reported defect (issue #158).
2. **Sources column — SDK URL**: same call against the `packages/sdk` submodule
   working tree — fork-varied for the same reason.
3. **SDK version / main-project range / migration notes**: read from
   `packages/sdk/standards-lock.json` **in the submodule working tree**
   (`_read_lock`, matrix.py:118 — returns `{"standards": []}` when the submodule is
   not initialised, rendering `unknown`), which varies with submodule init state
   *and with which commit the submodule working tree happens to sit on*.

**Measured evidence — the defect is not fork-only.** On the maintainer's own upstream
clone at `main` (`8fe79b4`, 2026-09-22), with the submodule working tree sitting at
`v0.0.3-6-g16b3d6b` while the committed gitlink pins `e7b2065`:

```
$ git submodule status packages/sdk
+16b3d6b740e96c74428cc0c63b8442ad020d0f96 packages/sdk (v0.0.3-6-g16b3d6b)
$ uv run python -m benchweave.standards matrix --check
stale_matrix: docs/compatibility-matrix.md differs from the rendered matrix   (exit 1)
```

The pinned commit's lock (`git -C packages/sdk show e7b2065:standards-lock.json`)
carries `{"sdk": "0.0.4", "main_project": ">=0.1.0", "notes": null}` — exactly what
the committed matrix says. The committed file is **correct against committed state**;
the gate is red because the render reads the *moved working tree* (`sdk 0.0.2`). All
three variances are one defect class: **a staleness gate that renders from
working-tree/remote state instead of committed state reds on correct committed
files.** The consequence is broader than contributor friction — a gate that can be
red on correct state teaches everyone to ignore it or "fix" it by committing
checkout-state bytes.

Confirmed who runs the gate: `.github/workflows/ci.yml` (`gates` job, line 44) and
`.github/workflows/package.yml` (line 40) both check out with
`submodules: recursive`, so hosted CI always has the submodule at the pin — the reds
land on forks' own push-lane Actions runs (the workflow's `on: push: branches: [main]`
triggers on the fork) and on local checkouts, exactly as the issue reports. After this
fix no code path reads `remote.origin.url` at all, so the render is robust regardless
of how any lane configures remotes.

## 2. Grounding facts that shape the design

- **No committed home for repo identity exists today.**
  `standards/standards-manifest.json` carries only `manifest_version` and
  `standards[]` (versions, status, normative paths). `standards/corpus-manifest.json`
  has an `identity` block (keys: `adapter_api, architecture, execution, interface,
  mcp, note, otdp, registry`) that is **closed-world by design** —
  `manifest.py:IDENTITY_ALLOWED_KEYS` refuses unknown keys because "a new key is a
  standards-governance event" — and it is semantically *corpus* identity, not repo
  identity. `pyproject.toml` has **no `[project.urls]`** at all. The one committed
  repo URL that does exist: `.gitmodules` pins
  `https://github.com/madeinoz67/benchweave-sdk.git` for `packages/sdk` — present in
  any plain clone, init or not.
- The manifest is **not self-pinned**: `corpus-manifest.json` rows cover `standards/`
  corpus files (144 rows), not `standards-manifest.json` itself — editing the
  manifest moves no pins and needs no `repin`.
- Other `standards-manifest.json` readers parse known keys only
  (`control/documents.py:101` reads `manifest["standards"]`; `export.py` builds its
  own bundle document), so an additive top-level key is inert everywhere except where
  this design makes it load-bearing.
- The SDK lock's `compatibility` block (`sdk`, `main_project`, `notes`) is authored
  SDK-side at sync time; `check.py:_compare_compatibility` already enforces its
  completeness when versions change. `run_check` (the `standards check` lane of the
  same make target) **already requires an initialised submodule** — it compares the
  SDK's committed lock and vendored tree, which is its job.
- Committed matrix bytes today: Sources cell =
  `[main repo](https://github.com/madeinoz67/benchweave) · [sdk repo](https://github.com/madeinoz67/benchweave-sdk)`,
  SDK version `0.0.4`, range `>=0.1.0` — every value is derivable from committed
  sources listed below, byte-for-byte.
- Decisions A01–A14: none govern the matrix gate (A09 is OTDP device-class
  compatibility, a different surface). No decision is re-proposed.

## 3. The mechanism

**Principle: the render reads only committed files; every authority that lives
outside the plain checkout is mirrored into one, and every mirror is equality-enforced
by the existing initialized-checkout gate.**

Field-by-field data sources after the fix:

| Rendered field | Today (checkout-dependent) | After (committed source) |
|---|---|---|
| Standard id/version/status/supersedes | `standards-manifest.json` (committed) | unchanged |
| SDK version | submodule working-tree lock | `standards-manifest.json` **`sdk_compatibility.sdk`** (new mirrored block) |
| Main-project range | submodule working-tree lock | `sdk_compatibility.main_project` |
| Migration notes | submodule working-tree lock | `sdk_compatibility.notes` (nullable, mirrors lock semantics) |
| Sources — main URL | `remote.origin.url` of root | `pyproject.toml` **`[project.urls] Repository`** (new) |
| Sources — SDK URL | `remote.origin.url` of submodule | `.gitmodules` `submodule.packages/sdk.url` |

Concrete changes:

1. **`standards/standards-manifest.json`** gains a top-level mirrored block,
   byte-equivalent to the pinned lock's compatibility block at `e7b2065`:
   `"sdk_compatibility": {"main_project": ">=0.1.0", "notes": null, "sdk": "0.0.4"}`.
2. **`manifest.py`** gains `load_sdk_compatibility(root)` — reads the block,
   fails closed (`StandardsError`, `sdk_compatibility_invalid:`) when the block is
   absent, not an object, or `sdk`/`main_project` are missing or empty. This follows
   the established per-block loader precedent (`load_identity` reads the
   corpus-manifest identity block; `load_manifest` reads standards rows — a named,
   fail-closed loader per document block). `load_manifest` itself is untouched, so no
   other consumer's contract moves.
3. **`pyproject.toml`** gains
   `[project.urls] Repository = "https://github.com/madeinoz67/benchweave"` — the
   Python-ecosystem standard home for repo identity, and an in-tree precedent away
   (`check.py:main_version` already reads `[project] version` from pyproject via
   `tomllib` for exactly this class of fact).
4. **`matrix.py`**: `render_matrix(root)` **loses its `sdk_root` parameter** — with no
   SDK path in scope, reading the lock is structurally unrepresentable (the same
   move that made duplicate manifest ids unrepresentable past `load_manifest`).
   `_origin_url` is deleted. `_main_repo_url(root)` reads pyproject `[project.urls]`
   and **fails closed** when `Repository` is absent (degrading to an unlinked
   "main repo" cell would be a silent substitution of explicit configuration — the
   current no-origin degradation is a defect, not a feature). `_sdk_repo_url(root)`
   reads `.gitmodules` via `git config --file <root>/.gitmodules --get
   submodule.packages/sdk.url` (fixed-argv subprocess, the exact `# noqa: S603 —
   fixed argv` pattern already used by `submodule_sha` in check.py; parses git-config
   format exactly; needs the git *binary* but no `.git` and no submodule), strips the
   `.git` suffix, fails closed when absent. The `or "unknown"` fallbacks in the
   render die — the loader's fail-closed guarantee makes them unreachable, and a
   block that cannot render honestly must refuse, not render `"unknown"`.
   `check_matrix(root)` loses `sdk_root` identically.
5. **`check.py`**: `run_check` gains `_compare_mirror(root, lock)` — the manifest's
   `sdk_compatibility` must equal the SDK lock's `compatibility` block key-for-key
   (`sdk`, `main_project`, `notes`; empty-string and null normalise equal), else
   `sdk_compatibility_drift: manifest <key>=<v> vs SDK lock <key>=<v>; update
   standards-manifest.json sdk_compatibility`. **The lock remains the authority; the
   mirror is a derived copy that CI refuses to let rot.** Every CI run
   (`gates` + `package`, both `submodules: recursive`) executes this comparison, so a
   lock compatibility change can never merge without the mirror moving — the mirror
   cannot drift between releases.

The bump-time workflow becomes: SDK sync changes the lock's compatibility block →
main-side PR advances the pointer, updates `sdk_compatibility`, regenerates the
matrix. Miss any of the three and a named mechanical check fails (pointer: existing
CI checkout-by-SHA; mirror: `sdk_compatibility_drift`; matrix: `stale_matrix`).

## 4. Why this shape wins

- **Repo-identity softening (issue's fix 2 — skip/compare-except-Sources when
  `github.repository` differs)** — rejected as primary: it softens a gate by
  *where* it runs rather than fixing *what* it reads, leaves local fork clones red,
  does nothing for the moved-submodule variance (measured in §1), and adds a
  repository-identity branch that must itself be tested per lane. The constraint set
  by the dispatch prefers full-strength everywhere; canonical sources achieve it.
- **Hardcode URLs in matrix.py** — rejected: embeds an operational fact in code so a
  repo move becomes a code edit; pyproject/.gitmodules are the data homes for repo
  identity, and `main_version` is the in-tree precedent for reading them.
- **Read the lock at the committed pin** (`git cat-file <gitlink>:standards-lock.json`)
  — structurally impossible in a plain clone: submodule objects are not fetched until
  `submodule update --init`, so the objects simply are not there. Verified against
  git's clone model; this is why the values must be mirrored main-side.
- **CI-only fix (init submodules in more lanes / document the prerequisite)** —
  CI already inits; the defect is the render's inputs, and contributors' local runs
  stay red. Rejected.
- **Drop the Sources or SDK columns** — loses published information the constraint
  explicitly keeps ("the committed Sources column remains accurate and stable");
  rejected.
- **Chosen: canonical Sources + mirrored compatibility block** — the only shape under
  which the render is byte-stable across *every* checkout (upstream clone, fork,
  no-submodule, moved submodule) while every authority keeps a single mechanical
  enforcement point.

## 5. Minimal first increment — and what it defers

**In scope (one slice, one mechanism):** matrix.py render/check signature + sources;
manifest.py loader; check.py mirror comparison; the `sdk_compatibility` block;
pyproject `[project.urls]`; tests (§9); GOVERNANCE.md "Identity and homes" sentence
+ drift-and-obligations.md obligation-6 extension + the new invariant entry
(§7). **Zero SDK-repo bytes move** — the bundle document, the SDK lock, the sync flow,
and the submodule pointer are untouched; no corpus bytes, no version dirs, no `repin`.

**Explicitly deferred:**
1. **Main-side authorship of the compatibility block** (lock's block becomes
   bundle-generated, mirror direction reverses) — the deeper GOVERNANCE "Direction"
   shape; touches the SDK repo, lock schema and sync flow. Defer; revisit if the
   two-sided authorship of one block ever causes a real miss.
2. **`versions` output init-independence** (`version_lines` prints no sdk rows and
   `unknown` submodule SHA on a plain checkout) — honest diagnostics, not a gate;
   defer.
3. **Makefile split** (a contributor-facing `check-matrix` target) —
   `uv run python -m benchweave.standards matrix --check` already works in a plain
   checkout after this fix; defer ergonomics.
4. **`manifest_version: 2`** — see §7 governance fork; default is additive block +
   fail-closed loader at version 1.
5. **SDK-side release-review cross-references** to `docs/compatibility-matrix.md`
   (the SDK repo's release-review skill) — committed matrix bytes are unchanged by
   this increment, so no SDK consumer can drift; verify at review, no edit expected.

Out of scope by design: making the `standards check` lane (`run_check`) pass without
an initialised submodule. Its comparison target *is* submodule content; making it
"pass" uninitialised would delete its checking power. The contract this design states:
`matrix --check` is checkout-invariant everywhere; `standards check` is an
initialized-checkout gate (CI and `make sync-sdk-standards` — which inits — cover it).
If the maintainer wants the whole `make check-sdk-standards` target init-free, that is
a different decision about weakening `run_check`, recommended against.

## 6. Precedent

- **Per-block fail-closed loaders over governed documents**: `load_identity` /
  `validate_identity` over `corpus-manifest.json` (manifest.py) — the mirrored block
  gets the same treatment over `standards-manifest.json`.
- **Fixed-argv git subprocess for read-only facts**: `submodule_sha` (check.py) and
  the outgoing `_origin_url` both carry `# noqa: S603 — fixed argv`; `.gitmodules`
  reading reuses the pattern.
- **pyproject as the machine source for project identity**: `main_version`
  (check.py) reads `[project] version` via `tomllib`; repo URL joins it. The repo's
  "prose defers to machine sources" standing rule makes pyproject the natural
  authority for a URL that docs render.
- **Derived mirrors equality-enforced at the gate**: the corpus identity block is
  "a declaration that is verified, never trusted" (CON-8) — `sdk_compatibility`
  gets precisely that posture toward the SDK lock.

## 7. Invariant and cross-surface impacts

- **New invariant (proposed CON-12; final numbering is the maintainer's):**
  *"The compatibility-matrix render is a pure function of committed state — no remote
  URL, no submodule init or working-tree state enters it; the manifest's
  `sdk_compatibility` mirror equals the SDK lock's `compatibility` block on every
  initialized checkout (CI both lanes), and the render fails closed rather than
  degrading when a committed source is absent."* Anchored `src/benchweave/standards/
  matrix.py:render_matrix` + `check.py:run_check`, pinned by the §9 tests. CON-4's
  drift-refusal sentence gains a cross-reference; CTL/STO/REG families untouched.
- **Tier 3 (review rubric): an on-disk governed schema changes** —
  `standards-manifest.json` gains a required-at-consumption top-level block.
  Additive; no corpus rows, no version dirs, no digests. **Governance fork for the
  maintainer:** keep `manifest_version: 1` with the block fail-closed at consumption
  (the identity-block precedent: additive keys with validator enforcement, no
  version bump) — **recommended**, since `manifest_version` gates only the loader's
  document shape and no in-tree consumer constructs a manifest without the block
  after this slice — or bump to `manifest_version: 2` for an explicit schema
  boundary. Either way it is a standards-governance event named in the PR, per
  GOVERNANCE's own framing; the GOVERNANCE.md prose edit is a "prose clarification"
  (no bump) under the change-class table.
- **drift-and-obligations.md**: obligation 6 extends — the `sdk_compatibility` mirror
  moves with the SDK lock's compatibility block (`run_check` refuses drift);
  `matrix --check` is checkout-invariant and fork-safe. CI map rows unchanged (same
  make target, same jobs).
- **Other surfaces**: MCP/REST/openapi/CLI-operator surface untouched (the matrix CLI
  keeps its exact commands and exit codes). Operator/README docs don't document the
  gate today (verified), so no doc surface moves. `docs/compatibility-matrix.md`
  bytes are expected **unchanged** — that is an acceptance criterion, not a hope.
- **CI cost:** zero new jobs; new tests are unit/CLI-subprocess class in
  `tests/standards/`, same family as existing ones.

## 8. Detection power — the gate stays full strength

The stale classes, before → after:

| Stale class | Caught before | Caught after |
|---|---|---|
| Manifest row change (bump/status/supersedes) without matrix regen | every checkout | every checkout — unchanged |
| Matrix hand-edit | every checkout | every checkout — unchanged (byte compare) |
| Lock compatibility change without matrix regen | every *initialized* checkout | initialized checkouts + CI via `sdk_compatibility_drift` (mirror must move with the lock) **and** `stale_matrix` (mirror must regenerate the matrix) — two refusals instead of one |
| Mirror edited without lock change | n/a (no mirror) | **new**: every initialized checkout + CI |
| Fork regenerates the matrix | poisons the file (fork URLs baked) | renders byte-identical upstream bytes — **nothing to poison with**; the vector closes |

The one detection that moves: a lock compatibility change is no longer visible to a
*plain* (uninitialised) checkout — but it can never merge, because any lock change is
a submodule pointer advance and every CI lane initialises submodules and compares
mirror↔lock. Detection at the merge boundary is unchanged; detection outside CI is
unchanged on initialized checkouts and strictly better than before on the poisoning
class. No softening branch on repository identity exists anywhere.

## 9. Measurable proof — pre-committed acceptance rule

**RED controls (must fail on current `main`, before the fix):**

- R1 Fork simulation, CLI level: copy the repo tree (no `packages/sdk` contents, no
  `.git` remotes needed) to a temp dir, `git init` + set
  `remote.origin.url = git@github.com:example/benchweave.git`, run
  `python -m benchweave.standards matrix --check` → **exit 1 today** (fork URLs +
  `unknown` cells). Equivalently measurable right now: the maintainer's own checkout
  red per §1 (measured 2026-09-22, exit 1).
- R2 New pytest arms, named RED: `test_render_is_pure_of_checkout_state` (render in a
  non-git temp copy == render in a git-init'd fork-remote copy == committed file
  bytes — fails today on both the Sources cell and the `unknown` cells);
  `test_check_matrix_green_without_submodule_and_with_fork_origin` (CLI exit 0 in the
  simulated fork — fails today); `test_run_check_refuses_mirror_lock_drift`
  (synthetic sdk lock with `compatibility.sdk` ≠ manifest mirror →
  `sdk_compatibility_drift` — no such check exists today).

**GREEN criteria (all must hold on the fix branch, before any number is admired):**

- G1 **Byte-identity on main**: `git diff --stat docs/compatibility-matrix.md` on the
  branch is **empty** — the renderer was swapped, the rendered bytes were not. (Every
  new source value was verified equal to the committed cell: pyproject URL ==
  upstream URL; `.gitmodules` URL minus `.git` == SDK URL; mirror == pinned lock's
  block at `e7b2065`.)
- G2 **Checkout invariance, 3-for-3**: in simulated checkouts (a) upstream clone with
  initialised submodule at pin, (b) fork remote with initialised submodule, (c) fork
  remote with no submodule directory at all — `matrix --check` exits 0 in all three
  AND `render_matrix` returns byte-identical output across all three (assert
  pairwise equality). Binary outcome, sample = the full 3-checkout scenario set, run
  once locally and once via the committed pytest arms (which encode (b) and (c)).
- G3 **Detection power permutation (the anti-softening control)**: in the *plain*
  checkout (c), mutate a committed input — bump one manifest standard's `version`
  string — without regenerating: `matrix --check` **must report `stale_matrix`**
  (exit 1). A second permutation: hand-edit one row of the committed matrix →
  `stale_matrix`. Both permutations green-after-fix = the gate still bites on
  committed-state changes with no submodule and a fork remote.
- G4 **Mirror enforcement**: synthetic lock with each of `sdk`/`main_project`/`notes`
  differing → three distinct `sdk_compatibility_drift` failures; equal blocks → none.
- G5 Suite: `uv run ruff check .`, bare `uv run mypy`, focused
  `uv run pytest tests/standards/` green with the collected count read from
  junitxml/exit codes (never a filtered summary line); `test_cli_matrix_check_clean_
  on_real_repo` passes **in this checkout** (it is red today per §1 — the moved
  submodule no longer affects it).

**Pre-committed acceptance rule.** SHIP iff G1–G5 all hold with R1–R2 shown RED on
main first (the effect is binary; the "sample size" is the enumerated scenario set
above — there is no threshold to tune).

- **KILL (design wrong, not measurement weak):** G1 fails — the committed bytes must
  change (means a source value disagrees with the published cell; do not merge
  without the maintainer re-ratifying the Sources/SDK cell format); or either G3
  permutation goes green (the gate was softened, which this design exists to avoid);
  or any G2 checkout still reds (incomplete fix).
- **UNDERPOWERED (measurement, not design):** a RED control that fails to fail on
  main — e.g. R1 exits 0 in the simulated fork — means the simulation does not
  reproduce the reported defect and must be fixed and re-run before any conclusion is
  drawn; it is not evidence the design works.

## 10. Top risks, each with its falsifier

1. **Mirror rot between releases** — a lock compatibility change merges without the
   mirror. Structurally guarded: every CI lane initialises submodules and runs the
   comparison. Falsified only by a CI lane dropping `submodules: recursive`
   (ci.yml:17 and package.yml:31 today) — the review checks both.
2. **Forks that edit `.gitmodules`** (repointing the SDK remote at their fork) render
   a different Sources cell and see `stale_matrix`. This is *correct* behavior, not
   residual hostility: they changed a committed input, the gate keys on committed
   inputs, and the diff is upstream-reviewable. If the maintainer wants even that
   case green, only hardcoding URLs in code achieves it — rejected in §4.
3. **Fail-closed tightenings change error behavior** — an absent
   `[project.urls] Repository` or `.gitmodules` entry now raises instead of rendering
   an unlinked cell. No in-tree flow relied on the degradation (the repo carries both
   files). Falsifier: any suite arm that constructs a root without pyproject/.gitmodules
   and expects a render — the new tests copy both files, matching reality.
4. **`sdk_root` parameter removal breaks a caller** — in-repo callers are
   `__main__.py` (bare) and the tests (updated in-slice); mypy catches any straggler.
   Falsifier: `uv run mypy` red — then the straggler is updated, not re-parameterised.
5. **Test-fixture churn hides a behavior change** — `_repo_copy` must now copy
   `pyproject.toml` and `.gitmodules` beside `standards/`; `_deprecated_repo` builds a
   manifest-with-mirror instead of a synthetic sdk lock. All rewritten arms stay
   within `tests/standards/` and are pinned by G1–G4, so any accidental behavior
   shift surfaces as a RED mismatch, not a silent pass.

## 11. Verdict

**BUILD** — as specified in §3/§5. The defect is verified at the line level and
measured on the maintainer's own checkout; the mechanism reuses four proven in-tree
patterns; the gate gains a refusal (`sdk_compatibility_drift`) rather than losing
strength; no standards corpus bytes, no SDK-repo bytes, and no CI jobs move; and the
acceptance rule is binary and fluff-proof (byte-identical committed matrix, 3-for-3
checkout invariance, anti-softening permutations, RED controls). The one governance
fork the maintainer must call at review: `manifest_version` 1-additive (recommended)
vs 2.
