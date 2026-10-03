# Issue #367 — the normative-seam sweep (D1): route every runtime normative-row resolver through the canonical load discipline

- **Date:** 2026-10-03
- **Issue:** gateway #367, row D1 (deferred from #238's design record §10)
- **Base read:** worktree off `origin/main` @ `c183db4`; the #238 refusal is landed
  (`15c3293`, verified: `_check_normative_row_path` at
  `src/benchweave/standards/manifest.py:177` with both addendum predicates).
- **Verdict:** **BUILD** — one minimal slice (D1 only). D2 stays deferred with an
  **amended-trigger recommendation** (owner fork 1): its exposure window opens the
  moment a head-opening train MERGES, so "lands on main" fires one train too late.
- **Standards bytes:** NONE move. `git diff origin/main...HEAD -- standards/` stays
  empty; no version strings touched; the export bundle is byte-identical.

The record is written without the eight Step-1 vocabulary words so §8's stated counts
are true by construction, not gamed after the fact (the #238 lane-A lesson).

## 1. Root cause — the seam, verified line by line

The #238 refusal lives at ONE boundary: `load_manifest`
(`src/benchweave/standards/manifest.py:223`), which applies
`_check_normative_row_path` to every active row (:246-250) and — via `_load_dev_head`
(:386) — to every dev row. Two RUNTIME gateway sites resolve normative rows by parsing
`standards-manifest.json` themselves and never cross that boundary:

1. **`src/benchweave/control/documents.py:657` `_otdp_normative_path`** — the ACTIVE
   descriptor-schema resolver. Raw `json.loads` of `(corpus /
   "standards-manifest.json")` (:669), selects the otdp entry's rows by
   `Path(relative).name == document_name`, then resolves
   `corpus / matches[0].removeprefix("standards/")` (:681). Reached from
   `_descriptor_validator(version=None)` (`documents.py:571`, via
   `_otdp_versioned_path` :602 — the None arm at :612) on every ACTIVE-path descriptor
   validation.
2. **`src/benchweave/control/provider_settings.py:133`
   `provider_contract_validator`** — the vendored provider-contract schema resolver.
   The identical shape at :148-160 (raw parse, basename exactly-once, prefix strip,
   join), cached in `_VALIDATORS`. Reached from `load_transport_settings` (:338) and
   `documents._validate_provider_contract` (`documents.py:1057`).

**What gets through today** (hand-corrupted manifest — the same reachability premise
and class as #238; no in-tree writer produces these rows):

- **Interior `..`, platform-independent.** A row
  `standards/otdp/0.2.2/../0.2.2-dev/otdp-device-descriptor.schema.json`:
  the basename matches on every host, the prefix strip fires, and
  `corpus / "otdp/0.2.2/../0.2.2-dev/..."` resolves through the EXISTING
  `0.2.2` directory into the dev tree. In a checkout with an open dev head the file
  exists — the ACTIVE descriptor validator and the provider-contract validator are
  then built on **dev-head bytes**, unpinned by any digest check at either site.
- **Clean `-dev` segment (the D2 form).** `standards/otdp/0.2.2-dev/<name>` passes
  every lexical check everywhere — that is D2's own row, still deferred (§10).
- **The backslash form fails loudly here, not silently** — unlike the export surface
  #238 closed, these sites join the row to the CORPUS root after stripping
  `standards/`, so a `standards\otdp\...` row resolves to
  `<standards>/standards\otdp\...`, which does not exist: a raw `FileNotFoundError`
  from the schema read, untyped. A crash, not a laundering — but the same
  missing-lexicon evidence, and the wrong refusal class for an import-time-capable
  path (`provider_contract_validator` runs inside settings load).

Wheel-side exposure is absent for the dev-tree forms (the wheel excludes `-dev`
directories — `hatch_build.py` lexical skip, pinned by
`tests/integration/test_wheel_dev_exclusion.py`), but the wheel's packaged manifest
sits at the corpus root (`vendoring.corpus_root`, `vendoring.py:62-80`), which is why
the fix must be a CORPUS-rooted loader twin, not a repo-rooted call.

**Sweep completeness (the issue asked for "every site").** Repo-wide survey of every
non-test read of `standards-manifest.json`:

| Site | Shape | Classification |
|---|---|---|
| `control/documents.py:657` `_otdp_normative_path` | raw parse, resolves rows | **RUNTIME SEAM — in scope** |
| `control/provider_settings.py:133` `provider_contract_validator` | raw parse, resolves rows | **RUNTIME SEAM — in scope** |
| `control/documents.py:1746` `_route_execution_contracts` | `is_file()` presence check only, classification via the corpus twins | verified: resolves no rows |
| `control/documents.py:309,341` `_corpus_state_token` | digests the manifest BYTES as a state token | verified: parses nothing |
| `vendoring.py:104` `declared_dev_family` | loads through `load_manifest` | the good precedent (§9) |
| `standards/manifest.py` twins (`active_version_from_corpus` :457, policy/dev twins) | `_read_corpus_manifest` + per-field parse | resolve no rows; possible later unification (§10 D3) |
| `standards/matrix.py:206`, `standards/export.py:50`, `repin.py` | through `load_manifest` | covered by #238 |
| `standards/promotion.py` (:252, :690, :815) | reads at historical git SHAs | different authority (object store); out of scope by design |
| `scripts/adc_conformance_control.py:81` `_otdp_policy_facts` | raw parse, policy block | dev/CI tooling — boundary held (§10 D2b) |
| `scripts/architecture/_validation_report.py` (:33 `active_standard_version`, :128 `_declared_dev_head`) | raw parse, version/dev-block | dev/CI tooling — boundary held (§10 D2b) |
| `scripts/standards/count_version_literals.py:940` | raw read, ids only | resolves no rows |
| `tests/**` | fixture construction | by design |

Open sibling PRs #371/#372 (UI fold rows) touch `interfaces/` + `packages/ui-html/`
only — no file collision with this slice (pre-flight, rubric step 0/#181 R2).

## 2. The mechanism

Three moves, all extending proven in-tree mechanisms (§9); nothing new is invented.

**(a) Extract the parse core.** `load_manifest`'s body from the
`manifest_version` check through `return StandardsManifest(...)` moves verbatim to a
private `_entries_from_document(document) -> StandardsManifest` in
`src/benchweave/standards/manifest.py`. `load_manifest(root)` becomes: its existing
raw read (unchanged — no error-class change for any current caller) + the core.
Pure code motion; the #238 arms and `_load_dev_head`'s ordering are untouched.

**(b) The corpus-rooted twin.**

```python
def load_manifest_from_corpus(corpus: Path) -> StandardsManifest:
    """The canonical load discipline over a corpus directory (the wheel's
    packaged root): every structural and row-lexicon refusal of
    load_manifest, same words, read through _read_corpus_manifest's
    corruption wrap (the corpus-twins precedent)."""
    return _entries_from_document(_read_corpus_manifest(corpus))
```

Named exactly after `load_dependency_policy_from_corpus` — the family's established
idiom (`manifest.py:563`). This is also D2's landing point: because the dev-segment
predicate would live in the shared core, D2 becomes one predicate covering
repo-rooted and corpus-rooted loads alike (§10).

**(c) The one resolver both sites call.**

```python
def normative_path_from_corpus(
    corpus: Path, standard_id: str, document_name: str
) -> Path:
    """The corpus-joined path of the exactly-once normative row named
    ``document_name`` in ``standard_id``'s entry, under the full load
    discipline. Reads nothing from disk; refuses typed.
    """
    manifest = load_manifest_from_corpus(corpus)
    entry = next((e for e in manifest.standards if e.id == standard_id), None)
    if entry is None:
        raise StandardsError(
            f"standards_entry_absent: {standard_id} (the manifest carries no "
            "entry for this standard; absence is corruption, not an empty answer)"
        )
    matches = [
        relative
        for relative in entry.normative
        if PurePosixPath(relative).name == document_name
    ]
    if len(matches) != 1:
        raise StandardsError(
            f"normative_document_unresolved: {standard_id}: {document_name} "
            "is not named exactly once in the entry's normative list"
        )
    row = matches[0]
    if not row.startswith("standards/"):
        raise StandardsError(
            f"normative_row_not_corpus: {standard_id}: {row} (this resolver "
            "serves corpus rows; a non-corpus row is not resolvable here)"
        )
    return corpus / row[len("standards/"):]
```

Decisions inside it, each with its reason:

- **`PurePosixPath(...).name`** (not `Path`): the basename convention becomes
  host-blind. Post-discipline, backslash rows are unreachable here anyway; this makes
  the idiom itself carry that.
- **Entry-absent refusal reuses the twins' vocabulary**
  (`standards_entry_absent`, `active_version_from_corpus`'s own words —
  "same words on both surfaces").
- **`normative_document_unresolved:`** replaces the two sites' private prefixes
  (`otdp_document_unresolved`, `provider_schema_unresolved`). One mechanism, one
  vocabulary; the message names the standard and the file, so each lane stays
  matchable. No test pins either old prefix (verified: zero hits repo-wide in
  `tests/`). Disclosed as owner fork 3.
- **The `standards/`-prefix refusal on the MATCHED row** is new behavior at both
  sites: today a hypothetical non-corpus otdp row would mis-resolve silently
  (`removeprefix` no-ops, the join addresses a nonexistent path). The parity
  live-source row lives in the plugin-ui entry (`src/benchweave/presentation/
  contracts.py` — the tree's single non-corpus row), never selected by these
  otdp-scoped sites; the loader still ADMITS such rows (the #238 discrimination arm
  `test_non_standards_parity_shaped_row_still_loads` stays green) — the refusal is
  this resolver's, stating honestly that it serves corpus bytes only.

**Site edits (the whole production diff at each site is a delegation):**

```python
# documents.py :: _otdp_normative_path — body becomes:
return normative_path_from_corpus(_otdp_corpus(), "otdp", document_name)

# provider_settings.py :: provider_contract_validator — the parse/match block becomes:
schema_path = normative_path_from_corpus(
    contract_family("otdp").parent, "otdp", PROVIDER_SCHEMA_NAME
)
schema = json.loads(schema_path.read_text(encoding="utf-8"))
```

`documents._otdp_corpus()` (:269) and the `_VALIDATORS` cache stay as they are. Both
sites keep their per-call manifest re-read cadence (the parse adds only the row checks
over ~60 rows — no caching complexity, no staleness questions introduced).

**Behavior deltas, disclosed:**

1. Refusal classes at the two sites change from raw (`KeyError`, `JSONDecodeError`,
   `FileNotFoundError`) to typed `StandardsError` — a strict improvement on paths
   that already expect typed refusals (`provider_settings` raises `StandardsError`
   today for the unresolved-name case; `interfaces/operations.py:221` catches
   `StandardsError` by class).
2. The sites now enforce the WHOLE load discipline (manifest_version, entry
   validity, pure-semver active, duplicate ids, row lexicon) — not just the lexicon.
   A manifest with a malformed UNRELATED entry that happens to resolve fine at these
   sites today now refuses there. Intended: one document, one discipline — the same
   stance `load_manifest` already takes for every consumer that crosses it.

## 3. Minimal first slice

Production: (a)+(b)+(c) and the two site delegations — roughly 45 lines in
`manifest.py`, 2 in `documents.py`, 4 in `provider_settings.py`. Tests (all in
established planted-tree idioms — `tests/control/test_corpus_seam.py:35`
`_standards_tree`/`_packaged_root`, `tests/control/test_run_pins.py:331`
`monkeypatch.setattr(documents_module, "_otdp_corpus", ...)`):

1. `test_documents_site_refuses_a_traversal_normative_row` (control) — planted
   corpus with real `standards/otdp/0.2.2/` dir + a `0.2.2-dev/` sibling carrying
   DIFFERENT bytes under the descriptor name; otdp's active normative names the
   `../`-form row. Expect `StandardsError` matching `normative_path_escape` from
   `_descriptor_validator()`. RED today = DID NOT RAISE (and pre-fix the validator is
   demonstrably built on the dev-tree bytes — the laundering the arm's docstring
   narrates).
2. `test_provider_site_refuses_a_traversal_normative_row` (unit/provider) — same
   planted shape around `PROVIDER_SCHEMA_NAME`; monkeypatch `vendoring._PACKAGED_ROOT`
   (miss) + `vendoring._REPO_ROOT` (planted root); reset `_VALIDATORS`; expect
   `normative_path_escape` from `provider_contract_validator()`.
3. `test_resolver_refuses_a_backslash_row` (standards) — direct resolver call; the
   lexical refusal is host-portable.
4. `test_resolver_refuses_a_leading_dot_row` (standards) — the `./`-form class the
   #238 lane-B fold closed at load, pinned through the new API.
5. `test_resolver_resolves_and_discriminates` (standards, green on arrival) — clean
   tree resolves to `corpus/otdp/<v>/<name>`; twice-named →
   `normative_document_unresolved`; entry absent → `standards_entry_absent`; a
   matched NON-corpus row → `normative_row_not_corpus` while
   `load_manifest_from_corpus` still loads the same document (the two-level
   discrimination: the loader admits the parity shape, the resolver declines to
   serve it).
6. `test_sites_resolve_a_clean_tree_unchanged` (control, green before AND after) —
   both sites over a clean planted corpus return validators over the planted bytes;
   the no-over-broad-refusal discrimination at site level.

Planted manifests need no digest fields — the resolver judges ROW trust, not byte
trust (§10 D4) — which also keeps the §8 vocabulary budget honest.

Docs: the CON-7 amendment (§5) and this record. **Zero bytes under `standards/`**
(the tripwire stays empty; the #238 D4 governance-sentence deferral is untouched).

## 4. The negative proof — no legitimate bytes or callers break

- **Committed manifest** (read whole at `c183db4`): 6 entries, 60 normative rows, all
  canonical posix, zero `-dev` SEGMENTS (segment-level scan — a substring scan
  false-positives on `otdp-device-descriptor.schema.json`, whose "device" contains
  the dev marker; repin's `.parts` idiom at `repin.py:184` is the correct form and
  the one D2 will extend), one non-corpus row in plugin-ui's entry only.
- **No test pins the two old site prefixes** (zero repo-wide hits), so the vocabulary
  merge breaks nothing pinned.
- **Both sites' real-corpus behavior is unchanged**: the committed manifest passes the
  full discipline (it must — `load_manifest` already enforces it for export/check),
  so every existing test exercising the real tree keeps resolving identically. The
  full battery is the dynamic proof.
- **The parity row stays loadable** — arm 5 pins the loader/resolver split explicitly.

## 5. Invariant and cross-surface impacts

- **CON-7 amendment** (extends the 2026-10-03 #238 amendment, same file
  `docs/internal/invariants.md`): the load boundary gains a corpus-rooted twin
  (`load_manifest_from_corpus`) so wheel-packaged consumers cross the same
  discipline, and the two runtime normative-name resolvers route through it — the
  refusal family (`normative_path_escape` and the structural set) now covers every
  runtime row resolution, not only the repo-rooted load. Amendment text written
  within the §8 vocabulary budget.
- **No other invariant moves.** No CTL/STO/REG surface; no persisted run/document
  SCHEMA changes (the documents.py touch is a resolver delegation, though it is what
  makes the slice Tier 3 — §8); no MCP tool, REST/openapi shape, CLI surface, or
  operator-doc change; no SDK repo motion (no submodule pointer; bundle
  byte-identical); fixture lattice untouched.
- **Obligation walk** (`docs/internal/drift-and-obligations.md`): rows 1-5 checked —
  none fire (no tool/API/operator-visible surface motion; the typed-refusal
  improvement rides existing error styling).
- **CI cost:** +6 test arms in existing lanes; Tier-3 review depth (two adversary
  lanes per the standing Tier-3 rule); fast lane per commit, full battery once
  before push. No new jobs.

## 6. Acceptance — pre-committed

Metric: deterministic pytest outcomes on the named arms; counts from junitxml
attributes or exit codes, never an output-filter summary line. The RED run IS the
measurement; this record precedes it.

**RED (site delegations withheld, tests present) — each must fail DID NOT RAISE on
the named prefix, not for an unrelated reason:** arms 1-4.

**GREEN (sweep applied):** arms 1-6, plus the FULL battery (`uv run pytest`;
`tests/faults/` included — control/ work), zero failures, with every #238 arm green
(the parse-core motion is behavior-neutral for `load_manifest` — if any reddens, the
motion was not pure; stop and repair, do not rebalance tests).

**Toggle-off:** revert ONLY the two site delegations (twin + resolver kept) → arms
1-2 RED again, arms 3-6 green. That separation is the proof the SITE wiring (not
just the library) carries the fix.

**SHIP if:** arms 1-4 red→green exactly as named; battery green; tripwire empty;
arm 5's loader-half green (the parity shape still loads).

**KILL if:** any pre-existing test reddens with a resolver/load prefix where it
expected a resolution — the discipline is over-broad at the sites; rescope per the
test's shape rather than widening exemptions. Or any RED arm fails under a different
prefix (a planted-tree shape error) — repair the arm before reading anything into it.

**UNDERPOWERED if:** the provider-site arm cannot plant its corpus without
refactoring that module's corpus derivation — drop that arm honestly, keep arms 1,
3-6, and record that the provider site is then pinned only at the resolver level
(the delegation is two lines, reviewed rather than RED-proven). Do not tune the
fixture until it passes.

## 7. Top risks, each with its falsifier

1. **The discipline is broader than the sites' old behavior** (unrelated-entry
   corruption now refuses at sites that ignored it). Falsifier: the battery — any
   planted-manifest test that relies on the sites' old lenience reddens, and the
   KILL branch fires.
2. **Vocabulary merge hides a consumer.** The two old prefixes are unpinned in
   tests; a UI/error-rendering literal could still match them. Falsifier: repo-wide
   text search in the same review (only the raise sites matched at design time).
3. **Cache masking a false green.** A provider arm that forgets to reset
   `_VALIDATORS` reads the real validator and passes vacuously. Falsifier: the
   toggle-off check — with the delegation reverted the arm MUST go red; if it stays
   green the arm is broken, not the fix.
4. **The honest residual (what this sweep does NOT catch):** a clean posix
   `-dev`-segment row still resolves into an open head at both sites and at load —
   D2, deferred with an amended trigger (§10, fork 1). Also uncaught: on-disk byte
   drift of the ACTIVE schema at runtime (row trust, not byte trust — §10 D4).
5. **Parse-core motion disturbing #238 ordering pins.** Pure motion, but the arms
   are order-sensitive by construction. Falsifier: the battery's #238 arms.

## 8. Review tier and the Step-1 keyword scan (#254)

**Tier 3.** Trigger: the persisted-format path rule — the rubric names
`src/benchweave/control/documents.py` explicitly ("the run/document schema"), and
the diff edits that file; first match wins, line count irrelevant. Consequences
accepted: mandatory second adversarial lane (the standing Tier-3 two-lane rule),
full suite, G6 independent second pass. No other Tier-3 rule fires (no `standards/`
bytes, no committed schema file, no registry surface, no fixture lattice, no
dependency motion, no submodule pointer).

**Keyword scan over the whole expected diff** (manifest.py core+twin+resolver,
two site delegations, six test arms, the CON-7 amendment, this record — docs and
code alike, added lines):

`threading` 0 · `asyncio` 0 · `subprocess` 0 · `sha256` 0 · `hashlib` 0 ·
`migrate` 0 · `recovery` 0 · `protection` 0

The record and the amendment are written within that budget (digest vocabulary, not
algorithm names; no planted fixture needs a digest field — §3). The only
occurrences of the eight words in this diff's text are the reporting line above
itself (the #238 convention: the scan statement is the report, not a hit); a fold
wave that adds a genuine hit re-states the count honestly at that point. The review re-derives
the counts over the ACTUAL diff; a fold wave that adds a hit re-fires the tier
question at that point.

## 9. Precedent

- **`vendoring.declared_dev_family`** (`src/benchweave/vendoring.py:104`) — the
  runtime resolver that already routes through `load_manifest` so "every dev-block
  shape refusal the loader enforces... is this resolver's refusal too, with the
  loader's own message (same words on both surfaces)". This slice is that pattern,
  corpus-rooted, for normative ROWS. It is not merely precedent — it is the design's
  template, and the reason Option B (scattering lexicon calls at each site) was
  rejected: a resolver that carries its own copy of the discipline is one forgotten
  call away from re-opening the seam; a resolver that CROSSES the boundary cannot
  forget it.
- **The corpus-twins family** (`_read_corpus_manifest` `manifest.py:438`,
  `active_version_from_corpus` :457, `load_dependency_policy_from_corpus` :563) —
  the corpus-rooted read idiom and naming scheme the twin extends.
- **`_check_normative_row_path`** (`manifest.py:177`, landed `15c3293`) — the
  lexicon this sweep propagates; the sweep adds no new path rule of its own.
- **Test idioms** — `_standards_tree`/`_packaged_root` (`test_corpus_seam.py`) and
  the `_otdp_corpus` monkeypatch (`test_run_pins.py:331`).

## 10. Deferrals (each with carrier and reopen trigger)

| id | deferred | carrier | reopen trigger |
|---|---|---|---|
| D2 (carried from #238) | The clean posix `-dev`-segment laundering form: an ACTIVE row naming an open head's directory passes every check and pins against the head's own corpus row. Mechanism (pre-specified): refuse `-dev`-suffixed SEGMENTS in ACTIVE rows inside `_entries_from_document` — `any(part.endswith("-dev") for part in PurePosixPath(row).parts)`, repin's lineage idiom (`repin.py:184`) — segment-level by construction (the `otdp-device-descriptor` substring false-positive is why substring scans are wrong here). Committed bytes verified clean at segment level (§4). D1's core extraction makes it ONE predicate covering both load roots plus both runtime sites. | issue #367 row D2 | **AMENDED (fork 1): the next head-opening train's MERGE — the refusal lands WITH or BEFORE it, checked by the governor lane that already gates every `standards/` touch** (the original "lands on main" wording fires after the exposure window opens); or the owner calls for it now (fork 2) |
| D2b | The scripts seam: `scripts/adc_conformance_control.py:81` and `scripts/architecture/_validation_report.py` (:33, :128) still direct-parse. Cheap later — `load_dependency_policy_from_corpus` and `active_version_from_corpus` are near drop-ins. Held at the issue's own boundary wording: dev/CI tooling, not the gateway surface. | this record | the next edit of either script; or a refute lane demonstrating runtime reachability of a script parse |
| D3 | Unifying the version-only corpus twins on `load_manifest_from_corpus` (they resolve no rows today; unification is a refactor with wide planted-fixture impact) | this record | the next manifest-parse change that touches the twins anyway rides it |
| D4 | Runtime BYTE-pin on the ACTIVE resolution (verify on-disk schema bytes against the corpus row at read time, as `_versioned_schema_path` already does per-pin at `documents.py:617`). Deliberately not in scope: D1 judges ROW trust (what the manifest names); byte trust at runtime is a different trust model — today the installed tree is trusted at runtime and the checker verifies pins at check time | this record | an owner ruling changing the runtime byte-trust model, or a runtime byte-drift finding |

## 11. Owner forks

1. **Amend D2's trigger** to the head-opening train's MERGE (the exposure-window
   argument above). Recommendation: amend — the current wording reactivates D2 one
   train late, and the governor lane on the head-opening PR is the natural carrier.
2. **Land D2 now as a rider** on this slice (one predicate, committed bytes clean).
   Recommendation: keep it deferred — the issue's own trigger discipline, no dev head
   in tree to exercise the legit-block coexistence outside planted fixtures, and the
   amended trigger closes the window. The owner may prefer the stronger pin now; the
   #238 coordinator's original defer-call stands unless overridden.
3. **Vocabulary merge at the two sites** (`otdp_document_unresolved` /
   `provider_schema_unresolved` → `normative_document_unresolved` + the shared
   prefixes). Recommendation: one vocabulary for one mechanism, as designed;
   unpinned, so either call is cheap now and only expensive later.
