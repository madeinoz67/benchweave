# Standards dependency management — design record

**Status:** Design (builder-ready) · **Tracking issue:** madeinoz67/benchweave#203 ·
**Requirements:** `docs/implementation-planning/08-standards-dependency-management-prd.md` (Draft v0.2, merged via PR #213)
**Evidence baseline:** gateway `main` at `d29c01d`; SDK pinned at gitlink `e948fd5` (SDK 0.3.0), read through the submodule object store (`.git/modules/packages/sdk`) — the working tree is deinitialized. Every number below carries its denominator; shapes marked *Direction (non-binding)* are sketches a builder may refine, everything else is load-bearing.

**Owner working parameters (2026-09-26, post-challenge corrected rulings; they supersede the PRD's embedded "Coordinator review and rulings" section wherever the two differ).** Two supersessions to name up front because the PRD's embedded text says otherwise:

- **Q1 — no new tool.** The PRD's embedded answer names a standalone `benchver` tool. The owner's corrected ruling: **no new tool** — `list`/`pin`/`upgrade` land as siblings of `repin`/`versions` in the `benchweave.standards` family, the dependency-agreement lane extends the existing `check` subcommand, and the DPS-150 plugin lock keeps its name and path (`contracts/lock.json`).
- **Q10 — 0.2.1 is yanked, not served.** The PRD's embedded answer serves 0.2.1 ("all retained in-range versions" = {0.2.0, 0.2.1, 0.2.2}). The corrected ruling keeps the served-set rule **served = retained ∧ in-range ∧ ¬yanked** and exercises the yank state exactly once, now: **OTDP 0.2.1 stays retained, digest-frozen, in-interval, but is yanked from the served set and from resolver auto-selection; explicit pins to it stay conforming with a deprecation warning naming 0.2.2 as the move-to.** This is the template for every future yank.

---

## 1. Problem, restated from code

A device plugin declares `otdp_version` in its descriptor; that pin is enforced by a `const`
inside the ONE schema version the runtime serves, so every corpus bump invalidates every pin
whether or not the plugin's standard moved:

- Gateway admission resolves one ACTIVE descriptor schema from the vendored standards manifest
  (`src/benchweave/control/documents.py` `_otdp_normative_path` / `_descriptor_validator`,
  cache keyed by filename alone) and validates every descriptor against it. The schema's
  `properties.otdp_version` is a `const` (`standards/otdp/0.2.2/otdp-device-descriptor.schema.json:5`).
- The SDK serves one version per standard from its wheel: `OTDP_VERSION = "0.2.2"` and
  `ADAPTER_API_VERSION = "1.1"` at `packages/sdk` pin `e948fd5`
  (`src/benchweave_sdk/__init__.py:13-14`), plus five literal schema paths in
  `src/benchweave_sdk/validation.py` (`:46` `("otdp", "0.2.2")`; `:166`, `:188`, `:439`, `:909`).
- The export bundle carries one entry per standard id (`src/benchweave/standards/export.py:34,53-75`,
  one `_entry` per manifest entry), and the SDK sync writes one lock row per id
  (SDK `src/benchweave_sdk/standards_sync.py`, `_sync_tree` lock assembly; SDK lock at pin:
  6 rows, otdp@0.2.2 with 29 files).
- The in-tree dialect test forces `lock == descriptor == active`
  (`tests/contract/test_plugin_descriptor_dialect.py:53-76`), which is precisely the forced-restamp
  invariant this lane retires (VR-45).

The out-of-tree break (the PRD's §1.2 case: a contributor plugin pinned 0.2.0 scoring 23/26
against SDK 0.2.x — the contributor's reported run, re-measured at each merge base) is the
acceptance driver for slice 1.

## 2. Recorded ruling artifact — VR-47 points 1 and 2 (one artifact, linked from #203)

Points 1 and 2 are mutually load-bearing — the reopen (point 1) exists to make the CON-10
amendment (point 2) buildable — so they are recorded as ONE ruling, carried here, to be lifted
verbatim into `standards/GOVERNANCE.md` and `docs/internal/invariants.md` by the FIRST design PR
(the PR #169 pattern: doctrine and mechanism land together). Framed as fresh supersession on new
evidence under the recorded-ruling rule (`standards/GOVERNANCE.md:208`, "Rulings are recorded
artifacts"); the executed precedent for revisiting a ratified figure by owner ruling is the
bump-floor history at `GOVERNANCE.md:68-71`.

**Ruling text (verbatim carrier):**

> **R-1 (reopen, VR-47.1).** Issue #97's withdrawal of "range pins, a resolver, lock formats, a
> mutable `-dev` stage, forward-compat tolerance" is superseded in part. REOPENED: range pins,
> the resolver, lock formats, and multi-version serving of retained versions — the out-of-tree
> breakage axis (a plugin outside the tree cannot move in-arc with a bump) post-dates the #97
> closure and is new evidence. The `-dev` record's "Not in scope, ever" (issue #97, the dev-stage
> row) is superseded for the serving/pinning question only, on the same evidence, joining the
> earlier sanctioned reopen of the mutable `-dev` stage (#168/#169). NOT reopened: cross-version
> tolerance (PR #59's rejection stands — serving retained versions EXACTLY is the only tolerance;
> ranges never fuzzy-match) and external standards indexes (the PRD's non-goal, unchanged).
>
> **R-2 (CON-10 amendment, VR-47.2).** CON-10 keeps what it protects — one shared authority
> (the retained corpus and its manifests), one descriptor dialect, one projection — and drops
> what it never needed: the singularity of the served pointer. A descriptor validates against
> exactly one OTDP version — its own pin — resolved from the retained corpus, digest-verified.
> PR #174's rejection of version-matched schema resolution is superseded on both its stated
> grounds together: multi-version serving answers the single-version-tree ground (the manifest,
> export, sync and wheel now carry every served version), and wheel-bundling of the served set
> answers the "structurally unbuildable" SDK leg (the SDK validates offline against the pinned
> version's bundled bytes; PRD VR-32, owner Q8). The one-entry-per-id manifest shape is
> undisturbed; the equivalence census extends across the served set. CON-1's #63 amendment and
> CON-8 each gain the dated amendments in §5. Nothing in PR #59 moves (VR-47.5): per-plugin
> exactness relocates one global gate to N per-pin gates; out-of-range stays non-conforming,
> unretained stays refused.

The remaining VR-47 points ride as working parameters already ruled by the owner (2026-09-26):
point 3 (dev bytes may be pinned under content addressing — the GOVERNANCE replacement text is
§5, item G-1), point 4 ("Version matching is exact" keeps both halves: out of scope for gateway
ranges; one clarifying sentence in the NEXT OTDP version copy — never an in-place edit; the
sentence is tier-2 prose with no corpus-manifest rows, `standards/otdp/0.2.2/extension-contract.md:15`,
so the freeze on it is governance, not digest), point 5 (PR #59 stands).

## 3. The mechanism, end to end

### 3.1 One committed authority: the dependency-policy block

A new top-level block in `standards/standards-manifest.json`, beside `sdk_compatibility`
(the exact precedent — a governance block read by its own loader,
`src/benchweave/standards/manifest.py` `load_sdk_compatibility`). *Direction (non-binding) shape:*

```json
"dependency_policy": {
  "policy_version": 1,
  "standards": {
    "otdp":     { "range": ">=0.2.0,<0.3.0", "yanked": {"0.2.1": {"reason": "superseded re-roll of the #171 fold; see #174", "since": "2026-09-26"}}, "retired": ["0.3.0"] },
    "registry": { "range": ">=0.1.0,<0.2.0", "yanked": {}, "retired": ["1.0.0"] },
    "execution":{ "range": ">=0.1.0,<0.3.0", "yanked": {}, "retired": ["1.0.0"] },
    "interface":{ "range": ">=0.1.0,<0.2.0", "yanked": {}, "retired": ["1.1.0", "1.1.1"] },
    "plugin-ui":{ "range": ">=0.2.0,<0.3.0", "yanked": {}, "retired": [] },
    "plugin-ui-preview": { "range": ">=0.1.0,<0.2.0", "yanked": {}, "retired": ["1.0.0"] }
  }
}
```

Rules, all machine-enforced by a new `load_dependency_policy` + `validate_dependency_policy`
in the `manifest.py` family, wired into `export_bundle` behind `validate_manifest`
(the `validate_identity` wiring precedent, `src/benchweave/standards/export.py:26-29`):

- **Range syntax is explicit half-open intervals only** (`>=X.Y.Z,<X.Y.Z`, inclusive lower,
  exclusive upper). Caret sugar (`^0.2`) is AUTHORING input, expanded by the resolver before
  anything is stored (§3.4) — a caret stored in any committed file refuses
  (`constraint_syntax_unexpanded:`).
- **Retired identifiers** are enumerated from the 2026-09-16 reset commit `ea70c6a5`
  (machine-enumerated, not hand-typed): the pre-reset version directories at `ea70c6a5^` are
  otdp 0.3.0; registry 1.0.0; execution 1.0.0; interface 1.1.0 and 1.1.1;
  plugin-ui-preview 1.0.0 (7 identifiers across 5 standards; `git ls-tree -r --name-only
  ea70c6a5^ standards/` cut to version dirs). plugin-ui 0.1.0 is NOT retired — the live tree
  re-owns that number (post-reset plugin-ui started at a live 0.1.0; the owner's Q9 ruling).
  The record is "used and dead": those numbers shipped in real wheels (SDK v0.0.1/v0.0.2
  vendored pre-reset OTDP 0.3.0), never to be reissued. OTDP's next MINOR skips 0.3.0 and goes
  to 0.4.0. Retired and yanked are DISTINCT statuses sharing this one carrier; the registry
  standard's release-status lifecycle (`revoked`/`yanked` in
  `standards/registry/0.1.1/release-status.schema.json`, enforced at
  `src/benchweave/registry/admission.py` `_gate_lifecycle`) is the semantic precedent being
  extended, not reinvented.
- **Cross-checks (fail-closed):** every range bound names a version shape but need not be
  retained (a lower bound below the oldest retained version is legal); a `yanked` or `retired`
  entry naming a version with no retained directory refuses (`policy_entry_unresolved:`);
  a retired identifier that IS the live active version refuses (`policy_retired_active:`);
  the yanked set must be disjoint from retired (`policy_status_conflict:`).
  [ERRATUM (#215): the sentence above is self-contradictory as written — every retired
  identifier by construction names no retained directory, so the literal rule refuses the
  seed policy block itself. The implemented rule splits it: a YANKED entry must name a
  retained in-range version (`policy_entry_unresolved:`); a RETIRED entry must name NO
  retained directory and never the active version (`policy_retired_active:` /
  `policy_status_conflict:`). See the slice measurement record's deviation 3
  (`docs/implementation-planning/09a-issue215-slice1-baseline.md`).]
- **Range changes are coordinator decisions (VR-43):** the drift-check lane refuses a
  `dependency_policy` diff in a PR whose body carries no ruling reference
  (`policy_change_unruled:` — the linked-ruling scan the PR-description gate family already
  practices; mechanical half reads the PR body via the existing check harness pattern).

**Seed ranges** follow the owner's window rule (a declared range covers at least the two most
recent released versions of each standard, measured in releases; the 24-hour train floor at
`GOVERNANCE.md:55-74` stays the only clock). Denominators — retained version directories per
standard at `d29c01d`: otdp {0.1.0, 0.1.1, 0.1.2, 0.2.0, 0.2.1, 0.2.2} (6); registry {0.1.0, 0.1.1}
(2); execution {0.1.0, 0.2.0} (2); interface {0.1.0} (1); plugin-ui {0.1.0, 0.1.1, 0.2.0} (3);
plugin-ui-preview {0.1.0, 0.1.1} (2). One deliberate deviation, flagged as Fork F1 (§8):
**plugin-ui declares `>=0.2.0,<0.3.0`**, below the two-release floor, because one of its
normative rows pins LIVE SOURCE (`src/benchweave/presentation/contracts.py` is a corpus-manifest
row of the plugin-ui standard) — a non-active plugin-ui version's schema bytes can be served,
but its code row cannot (the file is one object and it is the active version's). Serving 0.1.1
schemas beside 0.2.0 code creates renderer/manifest skew the corpus-owned-code deferral (D2)
owns. The recommendation is the narrow range now, floor compliance when D2 closes; the owner
may overrule to serve 0.1.1's schemas immediately.

### 3.2 The served set and its plumbing (gateway → SDK)

- **Served set = retained ∧ in-range ∧ ¬yanked**, derived, never hand-listed. At the seed:
  otdp {0.2.0, 0.2.2} (0.2.1 yanked-in-interval); registry {0.1.0, 0.1.1}; execution {0.1.0, 0.2.0};
  interface {0.1.0}; plugin-ui {0.2.0}; plugin-ui-preview {0.1.0, 0.1.1} — 9 served versions
  across 6 standards (denominator: the 16 retained directories listed above).
  [ERRATUM (#215): the per-id enumeration above sums to 10, not 9 — the per-id sets are the
  load-bearing rules; the total follows. Corrected in the slice measurement record's
  deviation 1 (`docs/implementation-planning/09a-issue215-slice1-baseline.md`).]
- **Export (`export.py`)**: the bundle gains one entry per SERVED (id, version) — bundle paths
  are already version-shaped (`otdp/0.2.2/...`), so multi-version is additive rows, no layout
  change —
  [ERRATUM (#215): the riding set is the CARRIED set (retained ∧ in-range, yanked versions
  marked), not the served set — the design's own wheel-payload enumeration, the Q10 ruling and
  the A1 anti-gaming arm all require the yanked version's bytes offline; every consumer
  re-derives the served set (¬yanked) from the markers. Corrected in the slice measurement
  record's deviation 2.] plus the `dependency_policy` block verbatim (PKG-1: the range travels to the SDK via
  committed artifacts, never by reading the gateway checkout; the owner's Q8). The ACTIVE entry
  keeps its marker (`"active": true`) so consumers that want one version (matrix stamps,
  identity derivation) still get it structurally.
- **SDK sync + lock**: the sync writes every served version into
  `src/benchweave_sdk/standards/` (the existing `VENDORED` layout gains sibling version dirs)
  and the SDK lock (`standards-lock.json`) gains one row per served (id, version) with the
  active marker, plus a mirrored `dependency_policy` block. Wheel payload delta, measured at
  `d29c01d` by `du -sk`: the six additionally-served version directories total ≈1,604 KB
  block-inflated (otdp/0.2.0 652 + otdp/0.2.1 688 + execution/0.1.0 128 + registry/0.1.0 72 +
  plugin-ui-preview/0.1.0 12 + plugin-ui 0.1.1 not served under F1) — the exact file-byte sum is
  re-measured and committed with slice 1. Two-sided gate (owner Q8): the served-set change bumps
  the SDK per the 0.3.0 precedent with a gate asserting the bump class (PATCH: served set grows
  inside the declared range; MINOR: the declared range changes) — a new release-review-matrix
  row SDK-side plus a MAIN-side check (the `check.py` extension below), closing the one-day
  window class where SDK and main disagreed (#166).
- **`make check-sdk-standards` / `benchweave.standards check` extension**: `_compare_lock` and
  `_compare_tree` (`src/benchweave/standards/check.py`) compare the SERVED SET and the mirrored
  policy block across manifest ↔ export ↔ SDK lock ↔ vendored tree, offline on both sides
  (VR-50/VR-51 — the #166 ruling: the SDK leg runs from its own lock and vendored bytes, no
  gateway checkout). Existing failure prefixes keep their meanings; new ones:
  `served_set_drift:`, `policy_mirror_drift:`.
- **SDK per-pin validation**: `benchweave_sdk.validation` resolves every schema path as
  `<standard>/<pinned-version>/<file>` from the descriptor's own pin, loaded from the vendored
  served set, digest-checked against the SDK lock row. `OTDP_VERSION`/`ADAPTER_API_VERSION`
  become derived (read from the lock's active row / the pinned schema's const) — the five
  `validation.py` literals and the two `__init__.py` constants retire in slice 1 as a
  CONSEQUENCE of the mechanism, not a separate sweep.

### 3.3 Gateway per-pin admission

`_descriptor_validator()` becomes `_descriptor_validator(version)` — cache keyed by
(corpus directory, schema filename), the existing per-corpus cache pattern
(`documents.py::_validator`, which already keys ACTIVE and DEV_HEAD compositions apart).
`_project_full_form` resolves the version from the descriptor's `otdp_version` BEFORE schema
validation and classifies (the owner's Q6 taxonomy):

| Pin state | Class | Behavior |
|---|---|---|
| served (retained ∧ in-range ∧ ¬yanked) | **conforming** | validated against the pin's own bytes (VR-13) |
| retained ∧ in-range ∧ yanked | **conforming + deprecation warning** | validates; warning names the move-to (derived: highest served non-yanked version ≥ pin) |
| retained ∧ out-of-range | **non-conforming** | full operation with flagged results, validated exactly against the pin's own retained bytes; loaded only after a recorded per-device operator acknowledgement owned by the admission record (VR-14/16/18) |
| not retained (unknown or retired identifier) | **refused** | no bytes exist to validate against; named error (VR-15) |

Every refusal and classification carries the VR-37 fields: standard, pinned version, supported
range, nearest move-to, migration-note pointer. New stable prefixes (VR-38 — existing prefixes
unchanged): `version_not_served:`, `retired_identifier:` (distinct from
`version_unknown:` — retired means "used and dead, never reissued"; unknown means "this gateway
has never carried it"), `standard_nonconforming:`, `operator_ack_required:`. The warning channel
reuses the deprecation-cell vocabulary already in the matrix (`matrix.py::_guidance`,
"migration guidance pending" at `src/benchweave/standards/matrix.py:91`).

**Mixed pins on one bench (owner Q11, pairwise):** a committed side table
`standards/cross-constraints.json` — one row per released version of a standard that constrains
others; frozen corpus bytes cannot gain rows, so the table lives OUTSIDE the corpus like the
policy block, coordinator-governed. *Direction (non-binding):*
`{"rows": [{"standard": "execution", "version": "0.2.0", "requires": {"otdp": ">=0.2.0,<0.3.0", "adapter_api": "1.1"}, "evidence": "PR #201 prose: preserves the OTDP 0.2.0 and adapter API 1.1 runtime interfaces"}]}`.
Retrofit rows for already-released versions are authored at adoption (execution 0.2.0's row
cites #201) so VR-31's fixture is buildable on day one. Admission enforces it PAIRWISE: each
device's OTDP pin must sit inside the bench's execution version's declared range — device A on
0.2.0 and device B on 0.2.2 share a bench; a device outside the execution contract's range
refuses with `cross_constraint_violation:` naming both versions and the row's evidence.

**Q6 identity comparison, defined:** when the gateway must confirm that bytes it holds ARE the
pinned version's bytes across a version transition (the census across served versions; the
SDK-lock ↔ manifest agreement on a re-synced tree), identity is **version-normalized subtree
comparison**: canonical-JSON the subtree, replace every occurrence of the subtree's OWN version
string with a fixed placeholder, then compare. Raw digest equality can never hold across
versions — 0.2.1→0.2.2's descriptor schema differs in exactly four version-string lines
(const, `$id`, title, description — verified by diff at `d29c01d`) — so a raw-digest gate is
not designed and its failure is pinned as a control (slice 2, B6).

**Adapter API (owner Q12):** no independent range, resolver axis, or constraint syntax this
arc. The adapter API version is a RESOLVED FACT in the per-plugin lock, read from the pinned
OTDP version's own descriptor schema `$defs.adapter.properties.api_version` const (the same
derivation `validate_identity` performs for the active version,
`src/benchweave/standards/manifest.py` `validate_identity` — relocated from active-schema to
pinned-schema under multi-version admission; that relocation is the GOVERNANCE G-2 amendment,
§5). `required_features` stay exact-match per identifier as the extension contract rules them.

### 3.4 The resolver, plugin constraints, and the plugin lock

Three carriers, three jobs (owner Q5, authority chain: constraint → resolution → lock → validation):

1. **The pin** stays in the descriptor (`otdp_version`, exact). The const stays and becomes the
   exactness engine: validation selects the pinned version's schema, whose const then confirms it.
2. **The requirement** is authored data, `contracts/constraints.json`, sibling of the lock.
   *Direction (non-binding):* `{"constraint_version": 1, "standards": {"otdp": "^0.2", "plugin-ui": ">=0.2.0,<0.3.0"}, "opt_in": {}}`.
   Caret accepted at AUTHORING time; expanded to intervals by the resolver before anything is
   stored. Per-standard dev/RC opt-in lives here (§3.6) — explicit, per-plugin, never ambient.
3. **The resolved pin** is generated `contracts/lock.json` — the DPS-150 shape EXTENDED, name
   and path unchanged (owner Q1): existing keys kept verbatim (`repository`, `revision`,
   `directory`, `otdp_version`, `adapter_api_version`, `sha256` file map —
   `plugins/fnirsi/dps150/contracts/lock.json` today), gaining `lock_version: 2` with:
   a resolved row per pinned standard (`{version, stage ∈ released|dev, files}` or a
   digest-of-digests), the resolved `adapter_api_version` (Q12), and for dev rows the content
   identity (§3.6).

**Resolver mechanics** (a new `src/benchweave/standards/dependency.py`, same package as
repin/check/export — no new tool):

- Deterministic, offline, pure over (committed bytes, constraints): the same inputs give
  byte-identical locks (canonical JSON, the `admission.py::_canonical` precedent; VR-26).
- **Minimal motion (VR-27):** resolution prefers already-locked versions; an explicit
  `upgrade <standard> --precise <version>` moves exactly one standard's row; every other row
  stays byte-identical.
- **Pre-release exclusion (VR-28):** dev/RC heads never auto-select; only an explicit
  content-addressed opt-in in constraints can pin one (§3.6).
- **Auto-selection never picks yanked** (the 0.2.1 rule); an explicit pin to a yanked version
  resolves with the deprecation warning.
- **Retired identifiers refuse** with `retired_identifier:` carrying the VR-37 fields and the
  re-target hint (OTDP: "0.3.0 is retired; the next minor is 0.4.0").
- **Yanked/retired/unknown are three answers, one comparator.**
- `--locked` mode (VR-30): verify constraints ↔ lock ↔ served set with zero network; drift
  refuses. The only fetch path (VR-49, deferred — nothing publishes standards externally today,
  PRD non-goal) will verify digests against the exported bundle manifest.

**The CLI surface (owner Q1, VR-48)** — subcommands of `python -m benchweave.standards`
(family today: export/check/matrix/versions/repin, `src/benchweave/standards/__main__.py`):
`list` (available/supported/served/yanked/retired per standard, from the policy block + tree),
`pin` (resolve constraints → write/extend a package's `contracts/lock.json`; `--package <dir>`),
`upgrade` (one standard, precise target, minimal motion, prints the migration-note pointer), and
the constraint↔lock↔range lane EXTENDS the existing `check` (it is the drift family; the
subcommand name is already taken by SDK-pairing check and existing prefixes must keep their
meanings — VR-38).

**Inter-standard constraints at resolve time (VR-31):** resolution consults
`cross-constraints.json` and refuses a lock combining conflicting standards with
`cross_constraint_violation:` — the same rows admission enforces pairwise at the bench
(§3.3), single-sourced.

### 3.5 Upgrade, soft roll-forward, evidence

- Support window in releases (owner Q3): a range covers at least the two most recent released
  versions; deprecation warnings during the window name the removal point (the range's next
  lower bound after narrowing); narrowing never alters a run in progress (VR-19 — stored run
  records keep their recorded classification; the next admission applies the new one).
- Migration notes (VR-36/SM-5): each release carries a from-predecessor note (machine-readable
  pointer in the policy block's per-version row, walked by the release-review matrix);
  a gate refuses a MINOR bump without one. VR-36a (one-step upgrade incl. URN/digest restamp)
  is exactly `upgrade --precise` + revalidation — the ADC restamp was five mechanical values;
  the command owns them.
- Evidence locks move only when the plugin's pin moves (VR-45): the dialect test's
  `lock == descriptor == active` becomes `lock == descriptor == a-served-pin` — DPS-150 passes
  while the active version advances past it. Run evidence records each device's validated
  versions and conformance class (VR-46).
- Matrix (VR-52): one row per retained version — stage, range membership, yank, deprecation,
  migration note — rendered from committed state only (CON-12's purity clause unchanged; new
  inputs are the policy block and promotion records).

### 3.6 Dev heads, RC, and promotion records

- **Pinning a dev head (VR-20/29, owner VR-47.3):** a plugin opts in per-standard in
  `contracts/constraints.json` with a CONTENT-ADDRESSED pin:
  `"otdp": "0.3.0-dev@<git-sha>"`. Resolution (repo checkout only — a wheel physically cannot
  resolve a dev head; the devstage wheel exclusion keeps its force, `vendoring.py` docstring
  and `declared_dev_family`) verifies the manifest-declared head exists, checks out the bytes
  at the recorded sha from the object store (the `_pinned_sdk_package_version` git-show
  precedent in `check.py`), and writes the lock row with `stage: dev`, the sha, and per-file
  digests. Editing the dev head after locking breaks revalidation on the changed file's digest
  — the label is mutable, the pin is not. Every coupled guard keeps its force: one head per
  standard, window promise (dev edits are not bumps), wheel exclusion, promotion deletes dev bytes.
- **RC (owner Q4):** no RC directory (the 2026-09-23 rejection stands). An RC is the advisory
  `candidate` flag on the dev block (`manifest.py` `DevHead.candidate`); an RC PIN is that head
  frozen by content — the same sha+digest lock row. Reproducibility is the pin's digest check.
  The identifier namespace refuses `rc.N` shapes (`version_shape_invalid:` — the
  `standards_entry_version_invalid` posture extended to pins); VR-6's ordering test covers
  dev < release and namespace refusal, never an rc.N comparator.
- **Promotion records (owner Q7):** a new committed file `standards/promotion-records.json`
  (governance data outside the corpus, like the policy block; no corpus-manifest rows; repin
  untouched — CON-7 unamended). One record per promotion: standard, target version, dev-head
  name, `dev_edit_sha`, `dev_tree_digest` (sha256 over the sorted normative path+digest list of
  the final dev state — written at PR time), `landing_sha` (the squash/merge commit on main —
  filled by an immediate post-landing append, since the landing commit does not exist when the
  promotion PR is authored; until filled the record is `pending`). Gates, run by the standards
  suite: (a) `dev_tree_digest` equals the digest of the dev tree at `dev_edit_sha` read through
  the object store; (b) **sweep-aware**: the diff between the dev tree at `dev_edit_sha` and the
  promoted directory on main contains ONLY lines carrying the version transition tokens (the
  `<target>-dev` string, the target version, the pre-dev active version) — any other changed
  line refuses with `promotion_sweep_violation:`; (c) a `pending` record refuses once a
  SUCCESSOR version of the same standard exists on main (pendingness must not outlive a train);
  the drift-check lane prints pending records as a warning line on every run. A branch tip is
  never required to be an ancestor of main (squash landings are the practice — VR-8's accept as
  amended by the owner's Q7).

### 3.7 No hard-coded versions (VR-21..25, SM-2)

A committed counting script (the gate's counter, not a hand count) enumerates executable
version literals outside the resolver and its declared data files, in ratchet mode from slice 1
(count cannot rise; baseline committed at the merge base) and zero-mode when the debt clears.
Gateway-side the removals are derivations, each with its precedent: `documents.py:48`
`contract_family("execution/0.2.0")` → active-entry derivation (the `_otdp_normative_path`
pattern already in the same file); `interfaces/mcp.py:52` and `interfaces/validation.py:37`
(`interface/0.1.0`) → same derivation (interface stays gateway-wide single-version — VR-5's
table: per-plugin pins are otdp/plugin-ui/adapter API; execution/interface/registry are
gateway-wide or per-document); `registry/schemas.py:22` (`registry/0.1.1`) → same;
`presentation/contracts.py:247,358` (plugin-ui `!= "0.2.0"`) → active-entry comparison via the
policy block (D2 owns the deeper corpus-owned-code question); comments/docstrings via VR-24's
docs gate extending the site hygiene pin. Baselines: 13 executable gateway sites at `ef969af`
(PRD §1.5 hand count; #201 re-versioned values but removed none — re-measured by the script at
each merge base); 17 SDK sites at pin `1b2cc74` (PRD; the five `validation.py` paths and two
`__init__.py` constants retire as a consequence of slice 1's mechanism, the remaining ten —
scaffold/presentation/fixtures — are slice 7).

## 4. Slice map (dependency order)

Each slice names what it BUILDS (a concrete new mechanism), its precedents, its standards-byte
and invariant impacts, its pre-committed acceptance rule (metric, effect size, sample, BOTH
kill directions), and its CI cost. Copy-never-move (`GOVERNANCE.md` "Bump mechanics") governs
every slice: no retained bytes move; every corpus change is a new version directory whose rows
cite `source`; this lane adds NO corpus bytes in slices 1–6 (governance data files only), and
slice 7's only corpus-adjacent motion is the OTDP clarifying sentence riding the NEXT organic
OTDP bump, never a dedicated bump (owner VR-47.4: do not bump for this).

### Slice 1 — builds multi-version serving end to end (the ADC-class fix)

Two-repo landing, ONE increment (the owner's correction of the PRD's "SDK only" label): SDK PR
(vendored served set, lock rows, per-pin validation, derived constants) + gateway PR (policy
block + loader/validator, multi-version export, check-lane served-set/policy comparison,
ratchet script, §2 ruling artifact + §5 amendment appendix lifted into GOVERNANCE and
invariants) + submodule pointer commit, in the AGENTS.md two-commit order.

**Precedents extended:** `load_sdk_compatibility` (manifest.py) for the policy block reader;
`export_bundle` staging/collision refusal (export.py:26-46) for multi-entry export; SDK
`standards_sync._sync_tree` lock assembly for served rows; `check.py::_compare_lock/_compare_tree`
for the two-sided gate; `_otdp_normative_path` (documents.py) for pin-derived schema resolution.
**Standards bytes: none move; none added.** The policy block is governance data (moves no
corpus rows, needs no repin — the `sdk_compatibility` precedent, GOVERNANCE "Identity and homes").
**Invariant impacts:** CON-1, CON-4, CON-8, CON-10 gain the §5 amendments; CON-14 is appended;
GOVERNANCE gains the §5 G-items. Website stamps: no new claims (D4).

**Acceptance rule A (pre-committed; baseline outputs committed BEFORE the mechanism lands):**
- **A1 — the ADC control (C1 as corrected).** The out-of-tree ADC plugin at its pre-restamp
  commit (the PRD §1.2 snapshot), installed from `git archive <sha>` into a clean venv with the
  slice's BUILT SDK wheel forced over the checkout's own SDK pin (explicit
  `uv pip install <wheel>` after `uv sync`, or a pip-only venv — the bypass is the point: the
  checkout's uv.lock pins the old SDK and would test the wrong thing), then its conformance
  suite run with the network disabled. SHIP: 26/26 pass (26 = the suite's full count at that
  commit; baseline 23/26 with the three named failures — the contributor's reported figure,
  re-measured at this slice's merge base and committed). KILL: any result < 26 that requires
  editing ADC bytes (that is the defect this slice exists to remove); if the baseline itself
  does not reproduce 23/26 across 3 runs, the measurement is underpowered — stop and re-baseline
  before building. ANTI-GAMING ARM: a third in-range pin — the same suite's 0.2.1-pinned
  variant (descriptor pin flipped, yank warning expected, suite still green) — defeats any
  dispatch table hard-coding exactly {0.2.0, 0.2.2}.
- **A2 — per-version content specificity (C2, corrected).** Discriminating element named BEFORE
  building: `transport.provider` in `$defs.customTransport` (present in the 0.2.1/0.2.2
  descriptor schemas; `additionalProperties: false` on the def) — a provider-bearing descriptor
  whose `otdp_version` correctly names its pin in BOTH arms is ACCEPTED pinned 0.2.2 and
  REFUSED pinned 0.2.0 (the 0.2.0 schema rejects the unknown key; the const cannot produce
  this — both documents' pins are self-consistent). Reverse arm: one descriptor body with the
  pin flipped 0.2.1↔0.2.2 validates only against its own pin's bytes (the two schemas differ
  only in version strings — this arm proves serving-by-pin, not serving-by-active). SHIP: all
  four cells behave as stated. KILL: any cell that passes via the ACTIVE schema regardless of
  pin (run with active=0.2.2, pin=0.2.0, provider present — must refuse).
- **A3 — refusal quality (C3).** A 0.3.0-pinned descriptor is refused with a stable prefix
  naming: pinned version, supported range, nearest move-to (0.2.2), retired status distinct
  from `version_unknown:`. SHIP: all five VR-37 fields present, prefix tests green. KILL: a
  raw const dump or `unknown_contract_schema` path (today's behavior — the RED baseline).
- **A4 — ratchet (C4).** The committed script at the merge base reports the gateway count ≤ the
  committed baseline (13 at `ef969af`, re-measured); a planted literal fails CI. KILL: the
  script's count is non-reproducible (two runs differ) — fix the script before trusting it.
- **A5 — no regression (C5).** All in-tree descriptors (4 of 4: sim_psu, sim_controller,
  sim_scope, dps150) admit unedited; every existing refusal-prefix test byte-unchanged; the
  yank warning on 0.2.1 pins appears in SDK `check` output naming 0.2.2. KILL: any existing
  prefix test edited to pass (prefix stability is VR-38 — an added class, never a meaning change).
- **A6 — two-sided served-set gate.** A planted SDK-lock served-row disagreement fails BOTH
  repos' CI (main-side `check`, SDK-side offline check). KILL: either side green with the plant.

**CI cost:** +1 clean-venv ADC control on the `package` lane (one venv + one pytest run,
~1–2 min); the counting script and check-lane extensions are sub-second local jobs. SDK wheel
grows by the served-set payload (≈1.3 MB of the ≈1.6 MB du figure — exact byte sum committed
with the slice).

### Slice 2 — builds the resolver surface and the plugin constraint/lock carriers

`dependency.py` (intervals, caret expansion, minimal motion, yank/retired/dev handling,
`--locked`), `contracts/constraints.json` schema + authoring rules, `contracts/lock.json`
v2 writer (extends the DPS-150 shape; the registry lock-writer precedent —
`registry/admission.py::_lock_document`, canonical bytes validated through a schema loader
before writing), `cross-constraints.json` + loader + retrofit rows, and the VR-48 CLI siblings
(`list`, `pin`, `upgrade`; the agreement lane extends `check`). Rides slice 1's landed policy
block. **Standards bytes: none.** DPS-150 gains `contracts/constraints.json` (authored data,
not corpus). **Invariant impacts:** CON-14 gains its resolution clauses (already appended in
slice 1; this slice makes them true); no CON row re-amends.

**Acceptance rule B:** B1 determinism — resolve the DPS-150 constraints twice, locks
byte-identical (n=2 runs, diff empty; KILL: any diff). B2 minimal motion — `upgrade otdp
--precise 0.2.2` leaves every non-otdp row byte-identical (control: `upgrade plugin-ui` moves
only the plugin-ui row; KILL: any collateral row motion). B3 caret — `^0.2` expands to
`>=0.2.0,<0.3.0` at READ time; a caret stored in constraints or lock refuses
`constraint_syntax_unexpanded:` (RED: plant a caret — today nothing refuses it). B4 retired —
`retired_identifier:` ≠ `version_unknown:` on both fixtures, VR-37 fields on both (RED: 0.3.0
today yields a const dump). B5 offline/drift — a hand-edited constraint fails `--locked`; a
served-version cache removed yields a named offline error with ZERO network calls (monkeypatched
socket fixture asserts the attempt count is 0). B6 raw-digest control (the Q6 RED) — the
version-normalized comparator admits the 0.2.1↔0.2.2 schema pair (version-strings-only diff)
while a raw-digest comparator on the same pair FAILS; and the normalized comparator REFUSES the
0.2.0↔0.2.2 pair (the provider element — the control has teeth; it is not "everything equals").
SHIP: all six. KILL (any): B1 diff non-empty; B2 collateral motion; B6 admitting 0.2.0↔0.2.2.
CI cost: negligible (pure-function tests).

### Slice 3 — builds per-pin gateway admission and the cross-served-version census

`_descriptor_validator(version)`, the Q6 classification table + VR-37/38 prefixes, the
pairwise cross-constraint admission check, census extension (parametrize the corpus-example
sweep arm over served versions — `tests/sdk/test_descriptor_equivalence.py` `EXAMPLES` today
hard-pins `standards/otdp/0.2.2/examples`; the 28-cell mutation matrix stays ACTIVE-version,
clean cells + named faults per served version join), and the dialect-test rewrite (VR-45).
**Standards bytes: none.** **Invariant impacts:** the CON-10 census-amendment clauses become
true here (appended in slice 1, landed here — the amendment text names this); CON-1's
per-pin clause same.

**Acceptance rule C:** C1 mixed bench — two plugins pinned 0.2.0 and 0.2.2 admit in ONE
gateway process, each validated against its own bytes, run record carries both pins + classes
(VR-46; RED: impossible today — the active-only validator refuses the non-active pin). C2
census — served-version sweep green on both lanes (gateway `admit_documents` ↔ SDK `check`,
in-process, the existing `_admit`/`_sdk_check` harness); a planted disagreement (SDK accepts a
provider-bearing 0.2.0 pin the gateway refuses) fails the census (the sweep has teeth). C3
dialect — DPS-150 passes with its 0.2.2 pin while a fixture manifest advances active past it;
the OLD test's assertion (`== active`) is shown RED against the fixture before the rewrite is
merged (the VR-45 control). C4 classification — 0.1.2 fixture: non-conforming, full operation
with flagged surfaces, no ack → refusal, ack recorded → admission (VR-14/16/18); 0.3.0:
refused. KILL: non-conforming silently treated as conforming anywhere (admission record, API
view, run record — all three surfaces must show it). CI cost: census grows by
(4 corpus descriptors × served versions) clean cells + per-version fault arms ≈ +30–40 test
cells, seconds-scale.

### Slice 4 — builds dev-head pinning and promotion records

Content-addressed dev pins (constraints opt-in, sha+digest lock rows, wheel refusal),
`promotion-records.json` + its three gates (digest, sweep-aware diff, pending-successor),
versions-list dev surfacing. **Standards bytes: none.** GOVERNANCE G-1 (the `:137-140`
replacement) already landed in slice 1's appendix; this slice builds the mechanism it licensed.
**Invariant impacts:** CON-14's dev clauses become true here.

**Acceptance rule D:** D1 side-by-side — a dev-pinned plugin and a released-pinned plugin admit
on one bench (VR-20); a WHEEL install refuses the dev pin by name, never falling back to active
(the `dev_head_unresolvable` posture, `vendoring.py::declared_dev_family`). D2 content
addressing — lock a dev pin, edit the head, revalidate: the changed file's digest is named in
the refusal (VR-29; RED-shaped: the pre-edit lock passes, the post-edit run fails). D3 promotion
gates — a promotion fixture with no record refuses; a record whose `dev_tree_digest` does not
match the sha's tree refuses; a planted non-version edit between dev tree and promoted tree
refuses `promotion_sweep_violation:`; a pending record with a successor version refuses. D4 —
no `merge-base --is-ancestor` requirement on any branch tip (the squash-landing amendment; a
fixture whose dev-edit sha is unreachable from main still passes the record gate via the
landing-sha + object-store checks). KILL (any): a dev pin resolving from wheel bytes; a
sweep-violation passing. CI cost: negligible.

### Slice 5 — builds soft roll-forward surfaces and evidence-class recording

Operator acknowledgement persistence (per-device, admission-record-owned), VR-19
range-narrowing immutability of stored classifications, VR-46 run-record conformance class,
matrix per-version rows (VR-52), migration-note gate + release-matrix walk (VR-36/SM-5).
**Standards bytes: none** (matrix + records are derived/governance surfaces). **Invariant
impacts:** CON-12 amendment (matrix inputs) lands here with the rework.

**Acceptance rule E:** E1 — narrow a fixture range mid-run: the stored run record's
classification is byte-unchanged; the NEXT admission classifies under the new range (both
halves asserted; KILL: either half failing). E2 — SM-5 gate: a MINOR bump fixture without a
from-predecessor note refuses; with one, passes and the release-review walk lists it. E3 —
matrix renders one row per retained version (16 rows at the seed) from committed state only
(the CON-12 fork-injection control: a working-tree-only policy edit does not change the render).
KILL: the render reading any non-commmitted state. CI cost: negligible.

### Slice 6 — builds the execution per-document pin (procedure-author story)

Execution documents declare their execution version (an additive corpus change: an optional
`execution_version` field on the bench document is a PATCH-class execution bump — the ONLY
corpus motion in this arc's slices, riding its own train under the 24h floor); admission
validates the lattice against the pinned served execution version via the pin-derived
validator (the documents.py `contracts` parameter already threads a corpus directory —
`admit_documents(contracts=...)` — the DEV_HEAD seam's mechanism reused per-pin). Serves the
PRD's procedure-author story; execution 0.1.0/0.2.0 both served since slice 1. **Invariant
impacts:** CON-1's amendment text already covers per-document selection; no new amendment.

**Acceptance rule F:** F1 — a lattice written for execution 0.1.0 validates unedited while the
gateway's active execution version is 0.2.0 (RED: today the module literal forces 0.2.0). F2 —
a lattice declaring an unserved execution version refuses with the VR-37 fields. KILL: any
in-tree lattice needing edits. CI cost: negligible. **This slice may land late or be re-sequenced
by the owner — it is independent of slices 4–5.**

### Slice 7 — builds the zero-literal end state (SM-2 = 0) and flips the ratchet

Gateway derivations for interface/registry/plugin-ui literals (§3.7), SDK scaffold/
presentation/fixtures literal removals (10 sites at `1b2cc74`), docs/comment gate (VR-24),
ratchet → zero-mode. **Standards bytes: none.** **Invariant impacts:** obligation 18's closing
clause ("a new version-bearing literal anywhere is a defect — make it a derived surface or
register it here") gains its enforcement: the registered-exception list lives in the counting
script's declared data files (the resolver's own inputs).

**Acceptance rule G:** G1 — the committed script reports 0 executable literals outside the
declared data files across gateway src/, SDK src/, and in-tree plugins (denominator: the three
trees; baseline 13 + 17 + plugin-count, plugin count re-measured at slice 1). G2 — a planted
literal in each tree fails CI (three plants, three red lanes). G3 — corpus-owned code
(presentation/contracts.py) either follows VR-21 or carries its registered exception with the
D2 pointer (VR-25). KILL: any plant passing; any count that cannot be reproduced twice.
CI cost: negligible (the script already runs in ratchet mode from slice 1).

### Dependencies between slices

1 → 2 → 3 (policy block → resolver → admission consume each other); 4 depends on 1 (policy
block) and 2 (lock rows); 5 depends on 3 (classification vocabulary); 6 depends on 1 (served
execution bytes) only; 7 depends on 1 (script + ratchet) and completes last. Each slice is one
increment PR (or the slice-1 two-repo set) against a #203 sub-issue; each merged PR opens
exactly one follow-on issue listing its deferrals (the PRD §8 convention).

## 5. Invariant and GOVERNANCE impacts — the amendment appendix (append-with-evidence, never rewrite)

All text below is carried verbatim by the FIRST design PR (slice 1), each item an APPEND to
the named row or section with its evidence line, exactly as prior amendments did
(CON-1's 2026-09-19/20/23 chain is the format precedent — the original assertion text is never
edited):

- **CON-1 amendment (2026-09-26, issue #203 slice 1/3):** descriptor admission selects the
  vendored schema of the version the descriptor's own `otdp_version` names, resolved from the
  served set (retained ∧ in-range ∧ ¬yanked) and digest-verified — the pin's bytes, not the
  active's. A pin outside the served set refuses `version_not_served:` carrying the five VR-37
  fields; a retired identifier refuses `retired_identifier:` (distinct from
  `version_unknown:`); a yanked pin validates with a deprecation warning naming the derived
  move-to. Exact-byte decode, digest pins, and every existing prefix unchanged.
- **CON-8 amendment (2026-09-26, issue #203):** the identity block's authority and active-entry
  derivation are UNCHANGED. `validate_manifest` additionally admits the served set: every
  served version's normative files exist and match corpus pins, and the dependency-policy block
  is cross-checked against the retained tree (unresolved yank/retired entries, retired-active
  conflicts, and status conflicts refuse with `policy_*` prefixes). Declarations verified,
  never trusted — unchanged.
- **CON-10 amendment (2026-09-26, issue #203):** "the active vendored OTDP schema" reads "the
  vendored OTDP schema of the descriptor's pinned served version" wherever admission resolves
  it; the projection itself is unchanged; the equivalence census extends across the served set
  (clean cells + named faults per served version; the 28-cell mutation matrix remains
  active-version); the sanctioned gateway-stricter cells are unchanged and re-pinned per served
  version where they are version-sensitive (the strict-UTF-8 and duplicate-key decode cells are
  version-independent by mechanism).
- **CON-4 amendment (2026-09-26, issue #203):** the round-trip gate additionally refuses
  served-set disagreement (`served_set_drift:`) and dependency-policy mirror disagreement
  (`policy_mirror_drift:`) across manifest ↔ export ↔ SDK lock ↔ vendored tree, offline on both
  sides.
- **CON-12 amendment (2026-09-26, issue #203 slice 5):** the matrix renders one row per
  retained version from the policy block and promotion records; the purity clause (committed
  state only, no checkout/remote reads) is unchanged and extends to the new inputs.
- **CON-14 (new row, 2026-09-26, issue #203):** dependency resolution is a pure function of
  committed bytes plus authored constraints; locks are canonical-JSON and byte-identical on
  re-resolution; single-standard upgrade moves exactly one row; pre-releases never
  auto-select; dev pins are content-addressed (git sha + per-file digests), opt-in per plugin,
  and never resolve from a wheel; retired identifiers never resolve; cross-standard constraint
  rows are committed side-table data enforced pairwise at bench admission.
- **GOVERNANCE G-1 (the `:137-140` replacement, a recorded supersession):** "The SDK never
  consumes `-dev` bytes" is replaced by: consumers may pin a dev head under three conditions —
  explicit per-plugin opt-in in the plugin's constraints; the lock row records content identity
  (git sha plus per-file digests); every coupled guard keeps its force (one head per standard,
  the window promise, wheel exclusion, promotion deletes dev bytes). Immutability still starts
  at release; a dev PIN is immutable by content, not by label.
- **GOVERNANCE G-2 ("Deliberately versioned elsewhere", adapter paragraph):** "its authority
  is the active OTDP descriptor schema's `$defs.adapter.properties.api_version` const" gains:
  under multi-version admission the authority is the PINNED version's const; the identity
  block's active-declared value is unchanged (CON-8).
- **GOVERNANCE G-3 (dependency policy):** the `dependency_policy` block is governance data
  beside `sdk_compatibility`; range changes are coordinator decisions requiring a linked ruling
  reference; yank and retirement are recorded statuses with the 0.2.1 yank and the
  `ea70c6a5`-enumerated retired identifiers as the founding entries.
- **Unamended, and why:** CON-2 (fixture lattice — untouched), CON-3 (MCP tools — untouched),
  CON-5 (transport parity — untouched), CON-6 (auth — untouched), CON-7 (repin — no corpus
  rows move; promotion records and policy blocks are non-corpus governance files),
  CON-9 (derivation — untouched), CON-11 (validation reports — superseded versions' reports
  stay frozen historical evidence; the policy block adds no reports), CON-13 (website stamps —
  no new claims this arc; D4 owns the served-set/range site row), REG-1..4 (untouched; the
  registry standard's lifecycle vocabulary is the precedent consumed, not changed).

**On-disk formats/schema inventory (Tier-3 in the review rubric):** `standards-manifest.json`
(additive top-level block), `standards/promotion-records.json` (new), `standards/cross-constraints.json`
(new), plugin `contracts/constraints.json` (new authored), plugin `contracts/lock.json`
(additive v2 keys, existing keys verbatim), SDK `standards-lock.json` (additive served rows +
policy mirror), export `bundle-manifest.json` (additive served entries + policy block). All
additive with version fields; all readable-and-refusing (never silently tolerated) by loaders
that predate them where coexistence is possible.

## 6. Deferrals (each with a named carrier and a REOPEN TRIGGER)

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| D1 | Network fetch for upgrades (VR-49's fetch half) — nothing publishes standards externally today (PRD non-goal) | `benchweave.standards upgrade` resolves offline from served bytes; the fetch design rides the publishing lane (#209) | The first externally published standards artifact (the #209 registry service standing up) |
| D2 | Corpus-owned code under VR-21 (`presentation/contracts.py` as a plugin-ui corpus row; multi-serving plugin-ui's code row) | Registered exception in the counting script's declared files + Fork F1's narrow plugin-ui range | The first plugin-ui bump after this arc, or the owner's F1 call to serve 0.1.1 schemas |
| D3 | Yank designed whole (VR-44's general mechanism beyond the 0.2.1 template) | The 0.2.1 entry in the policy block IS the template; general tooling (`benchweave.standards yank`) deferred | The first genuinely defective released version |
| D4 | Website range/served-set stamps (VR-50's website surface) | `website/index.html` claim sites stay token-based, no new claims this arc; CON-13's gate unchanged | The first range change after slice 1 lands |
| D5 | VR-40 "why" query (constraint→locked-version explanation) | The resolver's deterministic order makes it derivable; no surface yet | First user confusion report naming an unexpected resolution, or the SDK docs request |
| D6 | Per-version migration notes for ALREADY-RELEASED versions (SM-5 is "from adoption") | Policy-block note pointers exist only for post-adoption releases | A support request pinned to a pre-adoption version hitting a refusal |
| D7 | Interface multi-version serving (older interface versions for API clients) | Interface declares its range and serves its single released version; the named-refusal requirement (VR: API client story) is met by VR-37 errors | The first interface bump with live external clients |
| D8 | The counting script's plugin-tree CI lane (device-plugins workflow integration for the zero-mode gate) | Ratchet mode runs in `gates`; plugin-side zero-mode lands with slice 7 | Slice 7 |

## 7. Top risks — and what an adversary attacks first

1. **Lock forgery / trust laundering.** A plugin lock is generated data in the plugin's own
   tree — a malicious plugin authors a lock claiming bytes it does not have. MITIGATION:
   the lock is never TRUSTED — every consumer re-derives: admission digest-verifies the pinned
   version's bytes against the CORPUS manifest (CON-1's exact-byte discipline, unchanged), and
   the SDK against its own lock row. The plugin lock is a claim checked against machine
   authority, the same posture as the corpus identity block (CON-8: "verified, never trusted").
   FALSIFIER: a fixture lock naming wrong digests must refuse with the digest prefix, not warn.
2. **Resolver rollback via high-water interplay.** The registry resolver's high-water
   monotonicity (`registry/admission.py` `_gate_lifecycle`) governs release SEQUENCES; the
   standards resolver has no sequences — its "rollback" is auto-selection landing on an older
   version than a previously locked one. MITIGATION: minimal-motion (VR-27) is the guard; an
   upgrade can still DOWNGRADE deliberately (`--precise` names any served version) but never
   silently. FALSIFIER: a re-resolve with unchanged constraints moving any row.
3. **Range-sugar confusion.** `^0.2` meaning `>=0.2.0,<0.3.0` (0.x caret semantics) vs the
   naive `>=0.2.0` read; a stored caret silently widening. MITIGATION: caret never persists
   (B3), and the expansion is one pure function with a table-driven test including the 0.x
   boundary (`^0.2` ≠ `>=0.2.0,<1.0.0`). FALSIFIER: a persisted caret anywhere.
4. **Retired-id bypass.** A plugin pinning 0.3.0 (pre-reset OTDP) on a gateway whose tree
   happens to... nothing — no bytes exist; the attack is confusing `retired_identifier:` with
   `version_unknown:` so an operator "fixes" it by serving the number. MITIGATION: distinct
   prefixes, distinct remediation text (retired: re-target, the ladder skips the number;
   unknown: publish or widen). FALSIFIER: B4's two fixtures sharing a prefix.
5. **Served/supported drift.** The gateway serves a set the SDK does not (the #166 class) or
   the range says one thing on two surfaces. MITIGATION: the two-sided gate (A6) + one
   committed authority + derived mirrors; the CON-12 purity posture extended to the policy
   block. FALSIFIER: A6's plant passing either side.
6. **Sweep-laundry at promotion.** A promotion that smuggles byte changes past copy-never-move
   under cover of the version sweep. MITIGATION: the sweep-aware diff gate (D3) — only
   version-token lines may differ between the recorded dev tree and the promoted tree.
   FALSIFIER: the planted non-version edit.
7. **The census quietly shrinking.** Extending the census across versions while dropping
   active-version cells would weaken CON-10's pin. MITIGATION: the 28-cell matrix is named
   load-bearing and stays; the extension is additive parametrization; the review rubric's
   claim-discipline gate (G4) reads the census module docstring's cell census.
8. **Underpowered ADC control.** The 26/26 result could pass because the built SDK happens to
   equal the checkout's pinned SDK (testing nothing). MITIGATION: the explicit wheel-over-pin
   bypass in A1 plus the 0.2.1 third-pin arm; the baseline triple-run before building.

## 8. Forks for the maintainer

- **F1 (plugin-ui's range).** Declared `>=0.2.0,<0.3.0` (below the two-release floor) because
  plugin-ui's corpus-owned code row cannot multi-serve — RECOMMENDED, with the floor deviation
  recorded in the policy block's note and D2 owning the fix. Alternative: serve 0.1.1's four
  schema files now and accept renderer/manifest skew with a recorded warning. The working
  parameters did not address the code-row case; this is the one place they underspecify.
- **F2 (slice 6 timing).** Execution per-document pinning is independent of 4–5; it can move
  earlier (serving is ready after 1) or later. Recommendation: after 5, as mapped.
- **F3 (`check` absorbing the dependency lane).** VR-48 lists a `check` capability; the
  subcommand name is taken by SDK-pairing check. Recommendation as designed (extend `check`,
  keep prefixes stable); alternative is a `verify` sibling if the owner prefers separation.

## 9. DISCLOSED UNVERIFIED

- **SDK working-tree state beyond the pin.** All SDK reads are `git show e948fd5:<path>`
  through `.git/modules/packages/sdk` (the object store is present; the working tree is
  deinitialized). The SDK remote's main may be AHEAD of the pin — unverified; slice 1's SDK PR
  rebases onto whatever is current and re-verifies the five `validation.py` sites and the
  sync-writer shape at its own merge base.
- **CI runtime behavior.** The clean-venv ADC control's wall-clock cost (~1–2 min) and the
  `package` lane's wheel-size sensitivity are estimates, not measurements; both are measured
  and committed with slice 1.
- **The PRD's ADC figures** (23/26, the three failure names) are the contributor's reported
  run, not this design's measurement; A1 re-measures at its merge base and commits the output
  before the mechanism lands (the coordinator's attribution note, honored).
- **The `.prd203-review.workflow.js` file** at the repo root is the coordinator's review
  harness; its contents were not treated as rulings — only the owner's working parameters were.

---

*Design record for issue #203. Slices file as sub-issues of #203; each merged slice opens
exactly one follow-on issue listing its deferrals. No standards bytes move in this arc's
slices 1–5 and 7; slice 6's optional execution field is the only corpus motion, under the
ordinary bump rules.*
