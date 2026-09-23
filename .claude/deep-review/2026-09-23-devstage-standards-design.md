# The mutable `-dev` standards stage — successor to #97's withdrawn item

- Date: 2026-09-23
- Status: design (pre-implementation; this record is committed as commit one if built)
- References: gateway issue #97 (evidence comment 5748545727, re-scope/withdrawal comment
  5748876078, close comment 5749907395), issue #147 (the contested firing; parked
  `wip/147-0222` NOT touched by this design), the origin idea
  (`mutable-dev-standards-stage-range-pinned-manifest-with-generated.md`, 2026-09-20),
  `standards/GOVERNANCE.md` §Bump window / §Bump mechanics
- Severity / rubric tier: **Tier 3** — `standards/standards-manifest.json` gains an
  optional on-disk field (a schema-bearing change); standards-governor review is mandatory
  for any `standards/` touch and this one rewrites governance doctrine
- Anchors cited are on `main @ 3305b7f`; symbol names are authoritative over line numbers

> **Amended 2026-09-23, same day, before any build (§13):** the single-operator
> premise is void — the project now has three developers and is expected to grow.
> F1 is re-called (exclusion wins), F4–F6 are new owner calls, and the concurrency,
> authority, and operational analysis is in §13. The mechanism of §4 and the
> acceptance rule of §9 are unchanged; §4.2's invisibility table was re-verified
> against `main @ baeb179` (post-#158, post-floor-change) — it holds, see §13.0.
> The "48h" mentions in §4.5/§11 are historical (written against the pre-`b92e0fb`
> tree, where the floor was 48h); the floor at HEAD is 24h and the design is
> number-agnostic.

---

## 1. Owner summary

**Verdict: BUILD-WITH-CALLS.** The mechanism is small (one manifest field + two
function-level extensions + one GOVERNANCE paragraph), it extends only proven in-tree
machinery, and every consumer gate stays green during dev accumulation **by construction,
verified against the code, not assumed**. Three calls are the owner's; none blocks the
first increment.

**Fork calls needing the owner:**

- **F1 — wheel carriage.** `pyproject.toml:63-65` force-includes the *whole* `standards/`
  tree into the gateway wheel, so a dev directory ships in any wheel built while a head is
  open (verified: nothing at runtime can address it — `vendoring.contract_family` resolves
  only manifest-derived `<id>/<version>` paths — and no test enumerates the vendored
  contracts tree). Call: accept + add a release-review row "no release cut while a dev
  head is open" (recommended; right-sized for single-operator pre-1.0), or pay for a hatch
  exclusion now.
- **F2 — floor size under `-dev`.** Recommendation: keep 48h unchanged, on promotions
  only, with #97's own reopen triggers standing ("revisited after three windows";
  "a contested firing reopens the floor-size argument"). The alternative — dissolve the
  floor because promotions become rare — gives up the only bound on consumer-visible
  churn and is not needed for the velocity win.
- **F3 — dev-proof lane timing.** The validator-suite override that proves dev bytes
  *before* promotion (increment 2 below) can be deferred to first need or built with
  increment 1. Recommendation: defer, with the stated reopen trigger.

**Slice shape, five lines:**

1. Increment 1 (RED-first): the `dev` head on `standards-manifest.json` entries +
   `load_manifest`/`validate_manifest` rules + `repin`'s regenerable classification +
   a pure-semver guard on active versions + the GOVERNANCE paragraph.
2. Deferred increment 2: the family-script `--corpus` override (dev-tree proof lane).
   *Promoted into increment 1 post-build, §13.8 — the deferral trigger fired same-day.*
3. Promotion is **not new code**: today's bump flow verbatim with the dev dir as copy
   source, plus the dev field/dir/row teardown — forgetfulness caught structurally.
4. Deferred: the F1 release-review row; SDK repo needs **zero changes**.
   *Superseded in-arc, §13.3: exclusion shipped inside increment 1 (the hook-owned
   wheel mapping), so the release-review row's residual is the post-exclusion
   verification, not an open deferral.*
5. Acceptance: the #147 fold replayed on a scratch branch with mechanical controls
   (SDK stillness, train-window RED control, edit-without-repin refusal).

---

## 2. The withdrawal, named and argued

Issue #97's re-scope (comment 5748876078) withdrew, verbatim: *"Range pins, a resolver,
lock formats, a mutable `-dev` stage, forward-compat tolerance. None of it reduces churn
by a single bump — that is dependency management."*

**That judgment stands and this design does not contest it.** The `-dev` stage does not
reduce the number of promotions a given set of semantic changes requires. Nothing in this
record argues otherwise. Three of the four withdrawn companions — range pins, the
resolver, the generated lockfile — **stay withdrawn** here: they are dependency
management, the SDK lock's exactness is CON-4's substrate and is untouched, and #59's
recorded rejection of cross-version tolerance still governs.

What changed after the ruling is the ruling's own pre-registered reopen condition fired.
The close comment (5749907395) registered two triggers: *"the 48h floor revisit —
ratified in GOVERNANCE as 'revisited after three windows, not silently'"* and *"a
contested firing reopens the floor-size argument."* On 2026-09-22 the window fired for
the first time on real work — the #147 fold — and it was contested in exactly the sense
that comment means: a same-day errata heal on bytes whose incorrect version was already
SDK-released could neither re-vendor (refused, §4.3) nor bump (window closed for ~34.7h).
The churn measurement behind #97 counted bumps and correctly priced the *release ledger*;
it could not see the *authoring* cost the ratified window creates once it exists — that
axis only became measurable when the window bit. The owner's 2026-09-20 idea and the
2026-09-23 ruling to design it reopen the question **through** #97's registered gate, not
around it.

The separability was flagged at origin: the idea document itself describes a second,
separable proposal (range-pinned manifest + generated lockfile) beside the stage concept.
This successor takes only the stage.

---

## 3. Root cause, verified

The idea doc's diagnosis — identity, pointer and pin fused into one artifact, so every
ticket-level edit is forced to become a release — is correct, and the code shows exactly
where the fusion binds:

1. **The only mutable, validated place for corpus bytes is the active version's
   directory.** `repin._regenerable_paths` classifies as repin-mutable *only* paths named
   in the active manifest entries' `normative` lists; every other pinned row is frozen
   (`frozen_row_changed`). `validate_manifest` hash-checks the same active set
   (`normative_hash_mismatch`). To edit bytes anywhere and keep every gate green, the
   bytes must be the active version's — and the active version is what exports, syncs,
   and releases.
2. **The active version is the export unit.** `export.export_bundle` builds the bundle
   from `manifest.standards` entries via `_entry(root, entry, sources)` walking
   `entry.normative` — there is no code path that exports anything else. So any byte the
   SDK will ever see is, at the moment of editing, an active-version byte.
3. **The window prices version-directory additions.** `train_window._VERSION_PATH` is
   `^standards/([a-z0-9-]+)/(\d+\.\d+\.\d+)/` — pure semver only, counted from
   `--diff-filter=A` git history, enforced by
   `tests/standards/test_train_window.py::test_real_tree_post_anchor_sequence_is_clean`
   in the `gates` job (`ci.yml:15` `fetch-depth: 0`).
4. **Release is immutable.** SDK-side, `standards_sync.sync` refuses same-version content
   change: `standards_version_required: <id> content changed without a standards version
   increment` (`standards_sync.py:94-98` in the SDK checkout).

Consequence, measured on #147: a 3-rewording fold (provider-schema `description` scoping
+ two prose sites) arriving hours after 0.2.1's SDK release required restoring 0.2.1 to
its released bytes (3 files, 6 lines) and re-rolling the fold as a full 0.2.2 bump —
commit `587f716`, **39 files, +21274/−3**, the wholesale copy — and then parked on
`wip/147-0222` because the window (0.2.1 landed `b0a41f3` 2026-09-22 02:11:18 UTC)
refuses a 0.2.2 directory until 2026-09-24 02:11:18 UTC. The finisher preserved
everything and stopped correctly; the hold at park time was ~34.7h.

The defect is not any single guard — each is right. The defect is that **authoring and
releasing share one ledger**. The `-dev` stage splits the ledgers: edits accumulate on a
staging directory that no consumer gate can see; promotion is the only event that touches
the release ledger.

---

## 4. The mechanism

### 4.1 Manifest shape — active stays released, dev is a separate head on the entry

`StandardEntry` gains one optional field:

```json
{
  "id": "otdp",
  "version": "0.2.1",
  "status": "stable",
  "released": "2026-09-22",
  "supersedes": "0.2.0",
  "normative": ["standards/otdp/0.2.1/..."],
  "dev": {
    "version": "0.2.2-dev",
    "normative": ["standards/otdp/0.2.2-dev/..."]
  }
}
```

**Why this shape and not `active: "0.2.2-dev"`** — decided against the alternative on
mechanical evidence, not preference. If the active entry's version became `0.2.2-dev`,
then `export._entry` would export dev bytes with that version, and Gate 4's
`check._compare_lock` would fire `sdk_version_mismatch` (manifest `0.2.2-dev` vs SDK lock
`0.2.1`) on **every** dev edit until the SDK re-synced — the `gates` job red for the
whole accumulation window, and the SDK lock churning per edit. With active-stays-released
and the dev head carried as a field *outside* the version/status/normative spine, every
consumer iterates its existing active fields and the dev bytes are invisible to all of
them (§4.2). A second `standards[]` entry for the same id is structurally impossible
(`standards_entry_duplicate` at load), so "one entry + optional head" is also the only
shape that keeps one-id-one-entry.

Structural rules, all enforced at `load_manifest`/`validate_manifest` (new prefixed
refusals joining the machine-matchable family):

- `dev.version` must match `^(\d+\.\d+\.\d+)-dev$`; its target must be **strictly greater**
  than `entry.version` (`dev_head_stale` / `dev_target_not_greater`). This is what makes
  a forgotten dev-field teardown after promotion unrepresentable: post-promotion,
  target ≤ active, load refuses.
- Every `dev.normative` path must live under `standards/<id>/<target>-dev/`
  (`dev_path_outside_head`). At most one head per standard (one field — structural).
- `entry.version` (active) must be pure semver (`standards_entry_version_invalid`). The
  `-dev` suffix is legal only in the head. Without this, the train window could be dodged
  by suffixing a real release directory — the collector's regex would not count it. This
  closes the one evasion the stage otherwise opens.
- `validate_manifest` extends to the head's paths exactly as it treats active paths:
  existence (`missing_normative_file`), pin presence
  (`normative_not_in_corpus_manifest`), pin match (`normative_hash_mismatch`) for
  `standards/` paths; non-`standards/` paths carry existence only (the existing
  "no second authority" rule for the parity-validator shape). Reusing the existing
  prefixes is deliberate — a stale dev pin is the same defect class as a stale active
  pin, and both `python -m benchweave.standards check` (via `export_bundle`'s validate)
  and `test_validation_passes_on_the_canonical_corpus` catch it.
- `repin._regenerable_paths` adds the head's `standards/` paths to the regenerable set.
  Dev rows become repin-mutable like active rows; superseded-row freeze is untouched.
  Row creation/deletion and `source` remain hand-authored under governance review, as
  today.

**Dev-open** (documented manual flow, no new tooling): copy
`standards/<id>/<active>/` → `standards/<id>/<target>-dev/`; author corpus rows for the
dev files citing the active path as `source` (coverage demands it — `_check_coverage`
fails closed on any unpinned `standards/**/*.json`); add the `dev` block; `repin`; edit →
repin per change. The copy is ADD-wholesale once per batch; **every subsequent edit is a
git MODIFY on a tracked path** — the review artifact the idea doc correctly identifies as
lost under copy-per-edit, recovered for everything after the open.

**Dev-close without promotion** (abandonment): delete the dev directory and its rows,
remove the block. Coverage and load stay consistent; nothing else ever knew it existed.

### 4.2 What each gate sees — the invisibility table

Every consumer gate was read; each iterates the manifest's active spine, so a head
carried as a field is invisible to all of them simultaneously:

| Surface | Reads | Sees the dev head? |
|---|---|---|
| Gate 4 `check.run_check` → `export_bundle` | `manifest.standards` active entries | No — dev never exports; `_compare_lock`/`_compare_tree` compare SDK against active bytes only |
| SDK sync (`standards_sync.sync`) | the exported bundle | No — no bundle ever carries dev bytes |
| Identity block (`validate_identity`) | active versions, active descriptor's `api_version` const | No — identity declares active versions only; no identity churn during dev |
| Compatibility matrix (`matrix.render_matrix`) | `manifest.standards` | No — matrix unchanged during dev; regenerates at promotion (version cell), as today |
| Annotation guard (`_annotation_offenders`) | active entries' normative | No — stale version strings inside the dev copy are not judged until promotion makes them active, at which point a forgotten sweep **fires** |
| Train window (`train_window.collect_bump_entries`) | pure-semver version-dir additions in git history | No — `0.2.2-dev` fails `_VERSION_PATH`; the promotion's `0.2.2/` is what counts |
| Report pins (CON-11), family scripts, fixtures | manifest-active derivations (`CONTRACT_DIR`/`OUT`, report paths) | No — all follow the active entry; they move at promotion exactly as in today's bump |
| Gateway runtime (`vendoring.contract_family`) | manifest-derived `<id>/<version>` paths | No — nothing derives a `-dev` path |
| Wheel packaging (`pyproject.toml:63-65`) | force-include of the whole `standards/` tree | **Yes — see F1**: dev bytes ship in wheels built while a head is open (unreachable, unpinned by any test; disclosed) |

The one row that sees the head is packaging, and it is the F1 call.

### 4.3 Does the SDK ever consume `-dev` bytes? No — and the alternative is mechanically refuted

Recommendation: **never**. Promotion is the sync event; dev bytes are proven pre-promotion
main-side (increment 2's lane; until then, at promotion itself, which re-validates final
bytes exactly as today's bump does). Consequences of "no": the SDK lock moves once per
promotion (status quo), the SDK repo needs zero changes for this whole design, and the
`compatibility` block trigger (`_compare_compatibility`) fires only at promotion.

The alternative fails on the SDK's own guard, not on preference: `standards_sync.sync`
refuses same-version content change (`standards_version_required`). A lock pinned at
`0.2.2-dev` re-synced after any dev edit is exactly that refusal — so SDK dev consumption
would force a lock-version churn **per dev edit** (`0.2.2-dev.1`, `.2`, …) or an
exemption carved into the immutability guard. The first recreates the churn this project
already measured and banned, on the ledger that matters most (released lock bytes); the
second weakens the anchor that makes release mean something. The same guard is also what
vindicates the stage's boundary: *immutability starts at release* is already the
enforced law; `-dev` is the pressure valve on the other side of it.

### 4.4 Promotion — the bump event, verbatim

Promotion is today's bump flow with the dev directory as the copy source, plus a
teardown. Class rules apply unchanged; the batch is whatever the head accumulated
(highest class governs). Steps, all existing mechanics:

1. Copy `standards/<id>/<target>-dev/` → `standards/<id>/<promoted>/` (the class rule
   may promote higher than the head's named target — the head's version is intent, the
   content's class governs; GOVERNANCE notes this).
2. Version sweep in the copy ($ids, consts, titles/descriptions, urns, catalog refs) —
   the existing sweep; forgetfulness is caught by the annotation guard, the F2-style
   const tests, and `validate_identity`, exactly as in today's bumps.
3. Author the promoted version's corpus rows citing **the dev path** as `source` and
   the pre-dev active version's corresponding paths as `lineage` (the resets section's
   rule — "never a path that did not produce the bytes" — the dev path produced them;
   it lives in git history after teardown, the same status as any retired corpus — a
   status attaching to the dev path ALONE: the predecessor edge is carried by
   `lineage`, not buried in git). Delete the dev rows and directory; remove the `dev`
   block.
   *Amended 2026-09-23 by the governor re-check ruling (§13.10): the lineage field is
   REQUIRED — orphaning the predecessor was rejected.*

4. Flip the active entry (version/released/supersedes/normative), `repin`, regenerate
   the validation report via its writer (`--write-report`, refuses on red — CON-11),
   `export`, SDK sync, pointer commit, matrix regen, docs rows, test/fixture stamp
   cascade — the full existing in-arc obligation set (drift-and-obligations 6/7/8/13).

**Forgetfulness is structurally caught, not remembered:** a leftover `dev` block after
promotion fails `dev_target_not_greater` at load; a leftover dev directory without rows
fails `_check_coverage` (`corpus_file_unpinned`); dev rows without the block classify
frozen and refuse the next edit (`frozen_row_changed`).

### 4.5 What the window still protects

The collector's definition of a bump — a pure-semver version-directory addition — is
already "a promotion". **Zero collector changes.** The 48h floor therefore keeps binding
the release ledger: how often consumers (SDK lock, vendored tree, compatibility notes,
stamp cascades) see motion. What stops being priced is pre-release authoring, which no
consumer can see and which the churn measurement never counted. The floor's purpose
survives intact; its domain narrows to the thing it was always about. Per F2, the number
stays 48h and #97's reopen triggers (three windows; any contested firing) continue to
apply to it.

---

## 5. Standards touched, bump implications

- `standards/GOVERNANCE.md` — new **Dev stage** paragraph (draft below). Tier-2 prose,
  not digest-pinned (measured: 0 of 42 `standards/` md files are corpus rows) — lands
  without a bump, as #97's paragraph did.
- `standards/standards-manifest.json` — schema gains the optional `dev` block. This is
  the Tier-3 surface. No corpus bytes move; no existing rows change; `manifest_version`
  stays 1 (the field is optional and additive — an old reader ignores it, and this repo
  is the only writer).
- No standard bumps. The six standards' versions are untouched by increment 1. The first
  *use* of the stage will be whichever fold opens the first head (the owner's call; the
  #147 fold replay is the acceptance vehicle, on a scratch branch, not the parked chain).

GOVERNANCE paragraph draft:

> **Dev stage (`-dev`).** A standard may carry at most one dev head: an optional `dev`
> block on its standards-manifest entry naming a version (`<target>-dev`, target
> strictly greater than the active version) and a normative path set under
> `standards/<id>/<target>-dev/`. The dev directory is staging, not a version: it is
> created by a copy of the active version (its corpus rows cite the active path as
> `source`), edited in place across any number of changes — each edit follows the
> edit → repin loop, and validate treats dev pins exactly like active pins — and it
> never appears in the exported bundle, the SDK lock, the vendored tree, the
> compatibility matrix, or the identity block. The bump window does not see it (the
> collector counts pure-semver version directories only); the promotion is the bump
> event. Promotion is a bump in every existing respect — copy the dev directory to the
> released version (its rows cite the dev path as `source`), apply the version sweep,
> delete the dev directory and its rows, remove the `dev` block, repin, regenerate the
> validation report, export and sync — under the change-class rules with the batch
> being everything the head accumulated; the head's version names the intended target,
> the class rule governs the promoted version. Immutability starts at release: a
> version directory with no `-dev` suffix is frozen exactly as before, and the active
> entry's version must be pure semver — a `-dev` suffix is legal only in a dev head,
> so the window cannot be dodged by suffixing.

---

## 6. Minimal first increment, and what it defers

**Increment 1** (one RED→GREEN slice):

1. Commit 1 — this design record.
2. Commit 2 — RED: `tests/standards/test_manifest.py` + `tests/standards/test_repin.py`
   arms — dev block loads; `dev_target_not_greater` on stale/leftover head;
   `dev_path_outside_head`; active-version pure-semver guard (the dodge refusal);
   dev pin mismatch refused (`normative_hash_mismatch` on a dev path — the
   edit-without-repin honesty arm); repin mutates dev rows (planted tree); frozen rows
   still frozen. Watched failing collection, then failures.
3. Commit 3 — GREEN: `manifest.py` (`DevHead`, load rules, validate extension,
   active-semver guard), `repin.py` (`_regenerable_paths` extension), GOVERNANCE
   paragraph. Gates: `ruff`, bare config-driven `mypy`, `pytest -q`,
   `make check-sdk-standards` — all green on a tree with **no** dev head present
   (the field is optional; the canonical corpus must pass unchanged).

**Deferred, each with its reopen trigger:**

- **D-i — the dev-proof lane** (increment 2): a `--corpus <dir>` override on the
  `scripts/architecture/check_<suite>.py` family, refusing any directory that is not the
  manifest-declared dev head for its standard, so the census/falsifier run proves dev
  bytes before promotion. Reopen trigger: the first dev head held open more than one
  working session, or the first promotion failure traceable to bytes that were never
  validated in place — whichever comes first. Until then, promotion's own
  validate-then-report flow (which runs on final bytes) is the floor, identical to
  today's bump.
  *Promoted 2026-09-23, same day, post-build (§13.8): the trigger fired and the lane
  shipped inside increment 1 — this row is history, not a deferral.*
- **D-ii — the F1 release-review row** ("no release cut while a dev head is open"):
  rides the next walk of the release-review matrix (the SDK repo's
  `docs/internal/release-review-matrix.md` is the named matrix in the operator rules;
  the main-repo equivalent surface, if any, is located by the builder when adding the
  row).
  *Superseded in-arc, §13.3: F1 was re-called to exclusion and the exclusion shipped
  inside increment 1, so this row's standing constraint ("no release while a head is
  open") no longer applies — what rides the matrix walk is the wheel-listing
  verification the exclusion's own pin test now carries.*

- **D-iii — wheel exclusion machinery** (only if F1 is decided against acceptance).
  *Shipped in increment 1 (§13.3's re-call): hatch_build.py owns the contracts
  mapping per unit, `-dev` directories get no row. Moot as a deferral.*
- **D-iv — dev-open/promotion tooling** (any automation beyond documented steps).

Not in scope, ever, per §2: range pins, resolver, generated lockfile, forward-compat
tolerance.

---

## 7. Precedent

Every piece extends a proven in-tree mechanism; the design invents no architecture:

- The dev-row class reuses `repin`'s existing regenerable/frozen split (the active-row
  path, one more loop) — `repin.py::_regenerable_paths`.
- Head validation reuses `validate_manifest`'s existing normative checks (same prefixes,
  one more loop) — `manifest.py::validate_manifest`.
- The closed-world, refuse-early load discipline is `load_manifest`'s own shape
  (`standards_entry_duplicate` is the precedent for "make the bad state unloadable").
- Promotion is the existing bump flow — GOVERNANCE §Bump mechanics, obligation set
  6/7/8/13 — with a different copy source and a teardown.
- The window needs nothing: `train_window`'s pure-semver regex already counts exactly
  promotions. The new active-semver guard extends the same "the ledger cannot be dodged"
  posture the anchor/first-arrival logic already enforces.

The one genuinely new artifact is the optional manifest field and its GOVERNANCE
paragraph. The precedent that justifies even that: GOVERNANCE already recognizes
non-version states (admission, deprecation-as-status, reset-class) — the dev head is the
missing pre-release state, and its absence is precisely the fusion the idea doc
diagnosed.

---

## 8. Invariant and drift impacts

- **CON-7 — amendment required** (new row lifecycle class): corpus rows now have three
  fates — active (repin-mutable), superseded (verified-frozen), and **dev**
  (repin-mutable until the head is promoted or abandoned, then deleted with its
  directory). The "machine-rewritten only by repin" clause and the superseded-row freeze
  are untouched; the amendment names the dev class so the freeze guarantee stays
  truthful about what exists. Append-with-evidence per the invariants doc's own rule.
- **CON-2/CON-4/CON-8/CON-11 — unchanged, and the design's proof obligation is exactly
  that they stay green during accumulation** (controls B and E, §9). The pin lattice
  *extends* to dev bytes (they are pinned and verified like active bytes) rather than
  weakening anywhere.
- **GOVERNANCE.md** — new paragraph (§5). **invariants.md** — CON-7 amendment.
  **drift-and-obligations.md** — obligation 6's loop wording ("edit → repin → export")
  already covers dev edits; a one-line note that promotion carries the full bump
  obligation set can ride increment 1 or the first promotion's PR (builder's walk).
- **Surfaces that must move in increment 1:** `standards/standards-manifest.json`
  (schema), `src/benchweave/standards/manifest.py`, `src/benchweave/standards/repin.py`,
  `tests/standards/{test_manifest,test_repin}.py`, `standards/GOVERNANCE.md`,
  `docs/internal/invariants.md`. **SDK repo: nothing.** CLI/REST/MCP/operator docs: the
  `versions` output and matrix are unchanged (dev is invisible to both by design);
  `docs/doc-taxonomy.md` names the `standards/<id>/<version>/` placement — the builder
  adds the dev-dir row to the taxonomy when touching it (walk the list; low risk).
- **CI cost:** zero new jobs or legs. The new tests live in the existing standards
  suite; `fetch-depth: 0` is already set for the window test. No on-disk migration
  (optional field; no existing bytes change).

---

## 9. Measurable proof — pre-committed acceptance rule

Written before any number is looked at. The vehicle is the #147 fold (the three
rewordings, exactly as parked on `wip/147-0222`'s parent state) **replayed on a scratch
branch off `main`**; the parked chain itself is untouched.

Metric arms:

- **A (velocity, directional):** the fold is authored, repinned, and committed into a
  `0.2.3-dev`-shaped head (target chosen per the replay's base) within one working
  session, gates green at each commit.
- **B (SDK stillness, conclusive):** across all dev commits, `git diff` on
  `packages/sdk` is empty (lock and pointer), and `make check-sdk-standards` exits 0 at
  the final dev state.
- **C (review artifact, conclusive):** `git show` on the fold commit records MODIFY on
  the dev files — not ADD-wholesale.
- **D (RED control, conclusive):** the same fold replayed as a version-directory bump
  inside a closed window fires `train_window_violation: otdp` with the exact prefix;
  the identical history with the change in a dev head is clean. Technique: the existing
  scratch-repository family (pinned committer dates) — no wait on real time.
- **E (honesty control, conclusive):** a dev byte edited without repin makes
  `uv run python -m benchweave.standards check` exit 1 naming the dev path
  (`normative_hash_mismatch`), and fails `test_validation_passes_on_the_canonical_corpus`
  on the scratch tree.

**Ship if** A–E all hold on the replay. **Kill directions:** B fails → the manifest
shape leaks; kill the separate-head shape, do not patch symptoms. C shows ADD → the
open/edit split is misdesigned; redesign, do not ship. E fails → `validate_manifest`
does not cover the head; the honesty gate is missing — fix before any promotion is
allowed. D's control does not fire → the measurement is **underpowered, not
conclusive** (the window was not actually closed in the replay); re-run D against a
synthetic closed window and treat only that run as evidence. A failing alone (session
overrun) with B–E green is an operator-availability artifact, not a mechanism verdict —
the mechanism is proven by B/D/E; A is the directional claim the owner is ruling on.

Sample size: one replay plus the synthetic controls. For a mechanism whose proof is
mechanical (gates either see the head or do not), n=1 differential with a RED control is
the honest size; padding it would be theater.

---

## 10. Top risks, each with its falsifier

1. **The wheel carries dev bytes** (verified property, F1). Falsifier:
   `unzip -l dist/*.whl | grep -- '-dev/'` on a wheel built during accumulation — it
   will list them. Mitigation as called: release-review row, or exclusion. Residual if
   accepted: unreleased normative text present-but-unreachable in interim artifacts;
   named here so nobody discovers it as a surprise.
2. **Window evasion via the suffix** (the hole the stage opens). Closed by the
   active-pure-semver load guard; falsified by attempting to load a manifest with
   `version: "0.2.3-dev"` on an active entry — must refuse
   (`standards_entry_version_invalid`). The RED arm in commit 2.
3. **Dev heads rot open** (opened, never promoted; the standard's next head is blocked
   one-per-entry). Not gate-able without inventing a clock on authoring — which is the
   conflation this design removes. Disclosure: the governor review sees head age at each
   `standards/` touch; the reopen trigger D-i also surfaces it.
4. **Promotion to a different version than the head names** (class escalation) leaves
   the head's directory name divergent from the promoted version mid-flight. Benign —
   rows cite the dev path regardless — but the GOVERNANCE sentence ("the head's version
   names the intended target") is what keeps it from being read as an error. Falsifier:
   a promotion batch containing a breaking change must bump per class rule with the
   teardown refusals still firing correctly.
5. **The invisibility table is wrong somewhere untested.** The falsifier is the whole
   acceptance rule — any gate that turns on the head during accumulation (B failing) is
   exactly this risk materializing, with kill direction stated.

---

## 11. The #147 case study, resolved

Under the dev stage, the evening of 2026-09-22 runs differently at each named blocker:

- **`standards_version_required` refused the same-version sync** — never encountered:
  the fold never touches 0.2.1. 0.2.1 stays at its SDK-released bytes; no restore
  commit (`587f716`'s 6-line 0.2.1 rollback half disappears); PR #44's release stands
  untouched.
- **The train window refused the 0.2.2 bump** — never encountered for the *authoring*:
  the fold opens `standards/otdp/0.2.2-dev/` (one ADD-wholesale copy) and lands as
  MODIFY diffs (~6 lines across 3 files + repinned rows) the same evening. Gate 4 green
  (§4.2); SDK lock and pointer byte-identical; `train_window` green (no pure-semver dir
  added). PR A can open and merge carrying the head — nothing in the merge result
  releases anything.
- **What still waits:** the promotion. 0.2.2 becomes legal at 2026-09-24 02:11:18 UTC
  and the promotion is a full bump (sweep, repin, report, export, sync, stamp cascade —
  including the test cites and fixtures `0f523d1` was holding). That is the intended
  division: the window still prices the consumer-visible motion; it no longer prices the
  edit. For this fold specifically — prose and description text, no schema semantics —
  nothing on the SDK side needed the folded text urgently, so deferring its release to
  the next promotion costs nothing; had it been a correctness-critical machine errata,
  the existing contested-firing reopen (§2) is the sanctioned emergency path, unchanged.

Net: ~34.7h of hard blocking on authoring/merge → 0h, at the cost of one extra copy
(the dev-open) per batch and the F1 disclosure. The parked `wip/147-0222` branch is the
owner's to land when the window opens (2026-09-24 10:11 AWST) or to replay under the
stage — this design requires nothing of it.

---

## 12. DON'T-BUILD check

Run twice, both resolved:

1. *Is this the withdrawn dependency-management idea returning under a new name?* No —
   §2 takes only the stage; the manifest/lock machinery stays withdrawn, and the stage's
   justification is the contested-firing reopen, not a re-litigation of the churn
   measurement.
2. *Is the velocity problem better solved by shrinking the window?* A smaller floor
   still prices authoring by the clock (a 12h floor still blocks an evening fold to the
   next morning), keeps the same-version trap (a fold after SDK release still cannot
   re-vendor), and abandons the ratified anti-churn bound. The stage removes the
   conflation structurally — edits off the release ledger — which is the idea's actual
   diagnosis, verified in §3. Build.


---

## 13. Amendment (2026-09-23, pre-build): three developers and growing

The record above was designed against "single-operator, pre-1.0, multi-arc-per-day
velocity is the design target." The owner has ruled that premise void: three developers
now, growth expected, and the owner is actively probing multi-author scenarios
(overlapping same-standard work, emergency patches). Per the invariants file's own
convention, §1–12 stand as written and this amendment carries the new analysis with its
evidence.

### 13.0 What the premise change does and does not touch

**The mechanism survives unchanged.** The manifest shape (§4.1), the invisibility table
(§4.2), the SDK no-consumption refutation (§4.3), promotion-as-bump (§4.4), the repin and
validate extensions, and the acceptance rule (§9) are author-count-agnostic: gates judge
bytes and structures, not people. What the premise change re-opens is ownership (who
decides), packaging (F1), the window's justification (§4.5), and the operational rules
around shared mutable state.

Re-verified against `main @ baeb179` (the record was drafted at `3305b7f`; main has since
merged the #158 matrix work and the floor change):

- `manifest.py` gained a **top-level `sdk_compatibility` mirror block** with a fail-closed
  loader (`load_sdk_compatibility`) — `StandardEntry` itself is unchanged, and the mirror
  is fresh in-tree precedent for exactly the additive, fail-closed manifest growth the
  `dev` block follows. Precedent strengthened.
- `check.py` gained `_compare_mirror` + `_submodule_state_failures` — both read the
  manifest's mirror block and the SDK lock, which are promotion-scoped; the dev head
  remains invisible to Gate 4. Invisibility table holds at HEAD.
- `matrix.py` renders rows from the manifest plus the mirror, Sources from committed
  `pyproject.toml`/`.gitmodules` (CON-12) — still no disk enumeration of `standards/`;
  dev invisible.
- `train_window.py` changed its **docstring only** (48h → 24h); the collector is
  untouched. Zero-collector-changes claim holds at HEAD.
- The floor is **24 hours** as of `b92e0fb` ("bump-window floor revisited 48h -> 24h
  (owner ruling)", 2026-09-23) — the #97 "revisited after three windows, not silently"
  trigger exercised the same day this record was drafted. §4.5/§11's "48h" mentions are
  historical; the design is number-agnostic and this amendment inherits 24h (§13.4).

### 13.1 Concurrency model: head-per-author vs head-per-standard vs head-per-train

**Head-per-author** (`<target>-dev@<author>`, or a per-author directory) is analyzed
seriously and **rejected on two mechanical grounds**, not on taste:

1. **The window already serializes what it would promise to decouple.** Two heads of one
   standard still cannot promote independently — `train_window` binds promotion-to-
   promotion per *standard*, regardless of head count. Per-author heads decouple nothing
   the release ledger permits to be decoupled; the only thing they decouple is
   authoring, and git branches already decouple authoring. The headline benefit is
   illusory by law.
2. **Promoting multiple heads is a merge of separately-copied lineages.** Each head was
   copied from the active version independently; their union at promotion re-creates the
   ADD-wholesale review problem (conflicts between two copied trees surface at promotion
   — the highest-pressure moment, with the window open — and the governor diffs neither
   lineage cleanly). Cross-head consistency is also unverified until that merge: two
   heads each individually green can still collide semantically on the same schema
   property.

Add the schema cost (`dev` becomes a list with per-head ownership fields, one more
closed-world surface) and a per-author stale/orphan policy, and the variant pays real
complexity for a benefit the window forbids anyway.

**Head-per-standard** (as designed in §4.1, at most one) has the right structure but an
incomplete ownership story at N authors: one contributor's unfinished item sits in the
head that others need promoted — the release-lane coupling. **Head-per-train** is
head-per-standard with the ownership made explicit, and is the recommendation:

- The head is **train-shared state**: one `standards/<id>/<target>-dev/` carried on the
  train's working branch, owned by no author, named for the target version (no author
  suffix — authorship lives in git history and PR review where it already is).
- Contributors edit it through the ordinary PR flow; two authors' overlapping edits are
  ordinary MODIFY-vs-MODIFY merges resolved in review — which is precisely the review
  artifact the idea document wanted and §4.1 preserves.
- The coupling complaint is the batching rule working as ratified: a train holds until
  its batch is complete or incomplete items are backed out. The cure is process, and the
  dev stage makes the cure **cheap**: back-out is a revert of named MODIFY diffs + repin,
  against today's restore-commits-and-re-roll (the `587f716` dance). The batch-highest-
  class rule already governs whatever the head holds at promotion.

**Emergency patches on a standard with an open head** (the owner's probe): two sanctioned
paths, no second head —

- *Strip and promote:* revert the head's unfinished items out (cheap MODIFY reverts),
  promote the remainder early under a recorded window exception (§13.2). This is the
  structural improvement over today: an emergency no longer re-rolls a version directory;
  it trims a staging directory and burns an exception.
- *Priority claim:* the emergency claims the head; other work pauses and re-lands after
  promotion. Cheaper in governance tokens (no exception), slower for the paused work.
  The coordinator names which path; GOVERNANCE records that both exist.

**Head lifecycle** (who opens/closes): OPEN is a PR adding the block + directory + rows —
the standards-governor lane is already mandatory for any `standards/` touch, and that
review *is* the gate; no separate pre-approval. EDIT is a PR to the head-carrying branch
(governor lane + second-human review, §13.5). CLOSE is either promotion (§4.4) or
abandonment — the coordinator deletes the directory, its rows, and the block through the
same PR flow. **Stale heads** (open, idle, target still open): a coordinator ruling, not a
gate — the head's presence in the manifest makes its age machine-readable so the governor
review sees it on every `standards/` touch; a clock on authoring is the conflation this
design removes, and it stays removed. **Orphan heads** (author unavailable): identical to
abandonment; the coordinator's call, named in GOVERNANCE before it is needed.

### 13.2 Authority model — GOVERNANCE must vest rulings explicitly before a second human touches a head

Today GOVERNANCE vests rulings in the owner implicitly (a single-operator repo never had
to say it). With three developers, authority that is not written is authority that is
discovered in a dispute. The dev-stage GOVERNANCE paragraph should name three roles:

- **Contributor** — any developer; opens and edits heads through PRs; bound by the
  governor lane and second-human review.
- **Reviewer** — a human other than the author, required for any merge touching corpus
  bytes or corpus-manifest rows (§13.5). Single-operator self-merge was the old normal;
  three developers makes it no longer defensible for normative bytes, and the rule should
  exist before the first multi-author head, not after the first bad merge.
- **Standards coordinator** — promotes batches (the timing/batching call), rules window
  exceptions and emergency early-promotions, closes stale and orphaned heads. The owner
  holds the role as ratified; delegating it is itself a GOVERNANCE amendment, never a
  comment or a habit.

Rulings are **recorded artifacts**: a window exception or early promotion is written into
the promotion PR body, and it carries the same obligation #97 registered for contested
firings — it reopens the floor-size argument. The 48h→24h move (`b92e0fb`, same day as
this record) shows that mechanism working: ruled, recorded, not silent. Floor changes:
coordinator proposes, owner ratifies, in GOVERNANCE.

The principle extends the repo's own split — mechanical gates judge everything judgeable;
humans decide exactly the timing/batching/exception calls, and those decisions live in
reviewable records. Nothing here vests authority in an agent: the governor lane reviews,
it does not rule.

### 13.3 F1 re-called: with heads open most of the time, exclusion wins

The original F1 recommendation (accept carriage + a release-review row) was sized for a
single operator who cuts releases rarely. With three developers, a dev head is open most
of the time, and "no release cut while a head is open" becomes a standing constraint —
a rule that always fires either stops releases outright or gets trained into being
ignored; both outcomes are worse than exclusion. **Re-call: exclusion.**

- Implementation is a builder task with one verification: whether hatch's `sources`
  table can exclude `*-dev*` from the packaged contracts copy, or whether a small build
  hook copies `standards/` minus dev directories into `_vendored/contracts`. Either way
  it is a Tier-3 packaging change with a named cost: the wheel-identity contracts in
  `tests/integration/test_poc_acceptance.py` pin today's force-include byte-identity and
  move with any packaging change.
- **Interim control until exclusion lands** (and it must be mechanical, not remembered,
  precisely because it will fire often): pre-tag pre-flight — `unzip -l dist/*.whl` must
  list no `-dev/` entries. An always-on mechanical check survives; an always-on review
  note does not.
- SDK side unaffected: the SDK packages only what sync writes from exported bundles, and
  dev never exports (§4.2).

### 13.4 The window under real concurrency — and the 24h floor

#97's root cause was that sequential merges made the train definition vacuously
satisfied: every bump was trivially its own train. Genuinely concurrent PRs from three
developers **make trains real by themselves**. Two effects, opposite signs:

- **Justification strengthens on the risk side.** Churn exposure scales with authors:
  N developers each pressing for same-day promotions is the measured 4.8h/2.92h
  otdp-pair pattern at team scale. The floor is the bound that keeps the release ledger
  deliberate, and with the dev stage absorbing authoring churn the floor now prices
  only what consumers actually see — so it can afford to be strict.
- **The floor's mechanism gets lighter.** The clock was a *substitute for real trains* —
  it manufactured the falsifiable condition when merges were serial. With concurrent
  PRs, the train rule ("one bump per (standard, release train)") binds naturally again,
  and the floor's residual job narrows to bounding train *frequency* across sequential
  trains.

Net: **keep the floor; it is more justified than before, not less.** The freshly-set 24h
figure is inherited as-is — this design has no evidence to move the number, and bundling
a number change with a mechanism change without evidence is exactly the post-hoc-tuning
failure this project exists to refuse. **Fold, don't patch twice:** the dev-stage
GOVERNANCE paragraph is written against the current 24h text and lands in the same edit
as the window paragraph's presentation, so the doctrine reads once; future floor changes
go through #97's standing triggers (three windows; contested firing), not through a
second patch to adjacent sentences.

### 13.5 Multi-author operational rules

- **Normative-byte edits:** the standards-governor agent lane runs per PR and is
  mechanically N-author-safe — unchanged. Added for multi-author: **second-human review
  (reviewer ≠ author) required for any merge touching corpus bytes or corpus-manifest
  rows**, per §13.2. The repo's existing PR discipline (working-branches-only, linked
  issue before merge) already carries the rest.
- **Pre-flight discipline between concurrent branches:** the head is shared mutable
  state. Before opening or editing a head, a contributor re-reads the manifest's `dev`
  block — the machine-readable shared-state token — and rebases on the head-carrying
  branch. The small-scale preview already happened: the 2026-09-22 #147 collision
  (gateway issue comment 5776821899), where two of the owner's own sessions produced
  rival design records and the second ratified fork calls *blind* — root cause, deciding
  without reading shared state. The `dev` block makes that state machine-readable; this
  rule makes reading it mandatory. Cheap mechanical aid, deferred one-liner: extend
  `python -m benchweave.standards versions` to list open heads (the shared-state glance
  in one command); rides increment 1 or 2 at the builder's call.
- **Acceptance rule unchanged (§9), with one note:** the controls are author-count-
  agnostic, and arm B (SDK stillness across dev commits) doubles under multi-author as
  the tripwire for a contributor accidentally syncing dev bytes — it covers the many-
  hands case by construction.

### 13.6 New owner calls (beyond the original F1–F3)

- **F1 (re-called):** wheel carriage — exclusion over accept-and-review-row (§13.3).
- **F2 (stands):** floor — keep 24h on promotions only; standing triggers govern.
- **F3 (stands, trigger tightens):** dev-proof lane deferral — under three authors the
  reopen trigger (first head held over a working session, or first promotion failure
  from unvalidated dev bytes) will fire sooner; treat it as live, not eventual.
  *Superseded 2026-09-23, same day, post-build: see §13.8 — the trigger fired and the
  lane was promoted into increment 1.*
- **F4 (new):** head cardinality/ownership — recommend one shared head per
  (standard, train), coordinator-promoted (§13.1); the per-author variant is documented
  and rejected on the window-serialization and lineage-merge grounds. Overturning F4
  costs a schema change (`dev` as a list with owner fields) and re-opens §13.1's two
  mechanical objections.
- **F5 (new):** authority delegation — GOVERNANCE names the standards-coordinator role
  now (§13.2); the owner holds it, and any delegation is a future amendment.
- **F6 (new):** second-human review for normative-byte merges — recommended effective
  immediately (before the first multi-author head), since heads are exactly the surface
  that invites parallel edits. *Superseded 2026-09-23, same day, post-build: see §13.7 —
  single human reviewer, not an additional second human, with a coordinator self-review
  carve-out and a 2027-03-23 re-review date.*

The verdict is unchanged — **BUILD-WITH-CALLS** — with the call count now six and the
build still gated on nothing but the owner's word.

### 13.7 Post-build owner ruling (2026-09-23): F6 superseded — single reviewer, coordinator carve-out, six-month re-review

Three rulings arrived after the increment-1 build landed on its branch, amending
F6 before any PR opened (the loud-ruling pattern the floor revisit set):

1. **Single reviewer, not a second additional human.** Corpus-byte merges
   (any merge touching corpus bytes or corpus-manifest rows) require ONE human
   reviewer who is not the author — §13.2/§13.5's "second-human review"
   phrasing is superseded by this ruling. Framing: "single reviewer until
   further notice" — restorable to the second-human requirement by a future
   owner ruling, the same recorded-ruling mechanism that moved the floor.
2. **Coordinator self-review carve-out.** The standards coordinator (the
   maintainer holding the F5 role) MAY be the author and the reviewer of
   their own corpus-byte merges; non-coordinator contributors always need a
   ≠-author human reviewer. The carve-out recognizes that the coordinator is
   exactly who promotion batches and emergency folds will author.
3. **Re-review by 2027-03-23** (six months, set at ruling time). The rule
   carries its own review trigger — the #97 pattern — so nobody needs to
   remember to remember; the date rides in the GOVERNANCE text itself.

The GOVERNANCE "Roles and authority" section carries the amended rule verbatim;
no machinery changed (review discipline is doctrine, not code).

### 13.8 Post-build owner ruling (2026-09-23): F3 promoted to increment 1 — trigger fired

D-i's reopen trigger ("the first dev head held open more than one working session, or
the first promotion failure traceable to bytes that were never validated in place —
whichever comes first") fired the same day the increment landed: the owner will test
against dev bytes pre-promotion as a regular workflow, which is the first condition
in exactly the form ruled on. The dev-proof lane therefore ships **inside increment 1**
rather than as deferred increment 2; §6's D-i row and §1's slice shape carry inline
pointers so the tables stay truthful as history.

Specification = D-i's own text (the `--corpus <dir>` override on the four
standards-tree family scripts — devices/registry/execution/interface — refusing any
directory that is not the manifest-declared dev head for that script's standard),
plus the constraints ruled at promotion:

- **Read-only for SDK state.** The override never mutates the SDK's vendored
  tree, lock, or submodule pointer — it changes only the invoking process's
  view of the corpus root. Acceptance arm B's stillness proof extends to
  cover the override run: the lock bytes are byte-identical across it.
- **Default is today's behavior.** Without `--corpus`, the scripts resolve the
  manifest-active released tree exactly as before (no flag, no changed path,
  byte-identical derivation).
- **Not a report lane.** `--corpus` and `--write-report` are mutually
  exclusive (refused loudly): the machine-written reports are a property of
  released versions — their paths and pins derive from the ACTIVE manifest —
  and a dev run is a check, not a report.
- **Cross-standard reads stay active.** A suite's cross-standard contract
  reads (execution reading otdp's active descriptor, closure's manifest
  reads) follow the manifest's active entries regardless of the override;
  the lane overrides the script's OWN standard's corpus only.

### 13.9 Post-build owner ruling (2026-09-23): the RC candidate marker — named candidate, promoted into increment 1

The RC discussion's "named candidate" option was taken. The dev block gains an
OPTIONAL boolean `candidate`: absent/false is the authoring state; `true` is the
standards coordinator's believed-ready declaration. Same pattern as the F3
promotion — an RC-related deferral row moves into increment 1 by owner ruling,
landed as a follow-up commit while the review battery runs.

Semantics, ruled minimal:

- **Pure declaration, machine-readable.** The manifest carries it; the
  `versions` head glance renders it ("release candidate" on the head line).
- **Advisory — changes no enforcement.** No gate keys on it; testing runs
  through the `--corpus` lane regardless of the marker; promotion is
  unchanged. A non-boolean value refuses at load (`dev_block_invalid` naming
  `candidate` — a truthy string or 1 is not a declaration), and the marker
  weakens no shape requirement (a candidate block still requires `opened`).
- **RC-as-separate-released-dir stays rejected** per the design discussion:
  a release candidate is a state of the head, never a second directory the
  window could price or the corpus could pin.

### 13.10 Governor re-check ruling (2026-09-23): row-3 amendment COMPLIANT; the lineage citation is required

The re-review approved the -dev-terminal amendment as-is and ruled the orphan seam a
defect, not a residual: GOVERNANCE as merged would prescribe a promotion flow its own
derived-dir gate refuses at first use, and normative text shipping a known defect fails
the docs-coverage duty. The contour, implemented verbatim:

- Promoted rows cite the dev path as `source` (unchanged, the resets rule) AND the
  pre-dev active version's corresponding paths as `lineage` — an optional string field
  on corpus rows.
- The derived corpus-dir guard seeds its walk from BOTH edges (per row and per cited
  row); the -dev terminal applies to lineage identically; repin refuses a lineage
  naming a `-dev` path outright (field confusion — the dev edge is what source carries).
- `repin`'s row shape widens for exactly the optional string `lineage` under the
  existing lexical rules; the ripple was traced to that one site (`_corpus_pins` maps
  path→sha256 only; the SDK never sees corpus rows).

The ruling's rationale for the shape, recorded for the PR body: rows-citing-paths is
the #78-vetted retention mechanism (principle 9 — extend proven in-tree mechanisms);
an entry-level lineage list would re-introduce the hand-list shape #78 replaced; and a
manifest-supersedes derivation was traced and REJECTED (one hop patches one promotion
and re-orphans the next generation).
