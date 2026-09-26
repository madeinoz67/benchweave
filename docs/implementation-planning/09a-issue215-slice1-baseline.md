# Issue #215 slice 1 — A1 baseline measurement (committed before the mechanism)

**Status:** Measurement record · **Tracking issue:** madeinoz67/benchweave#215 ·
**Design:** `docs/implementation-planning/09-standards-dependency-design.md` §4 Slice 1, acceptance rule A1.

The design's kill direction for A1 requires the 23/26 baseline to reproduce
across three runs at this slice's merge base BEFORE any mechanism lands. This
file is that measurement, committed on the branch ahead of the first mechanism
commit. All figures below are this run's own measurements (the PRD §1.2 figures
are the contributor's report; A1 re-measures — design §9, third bullet).

## Environment

- Gateway merge base: `403c061` (origin/main at run time; submodule pin
  `packages/sdk` = `3b14d0e`).
- SDK under test: wheel built from `git archive 3b14d0e` of the standalone SDK
  checkout (never a clone-and-edit), `benchweave_sdk-0.3.0-py3-none-any.whl`,
  477,244 bytes, sha256
  `4251827438eb0826f7f2b4506f52a196fc601a614385b9fbd4fd6a724c42e36f`.
- Plugin under test: `parkview/benchweave` at `de132a292040415f9935b93b424ce15b9980843d`
  (pre-restamp), installed from `git archive` bytes into a clean `uv venv`
  (Python 3.13.13) — the fork root project `benchweave-adc` 0.1.0 non-editable,
  dev group deps pinned by the fork's own pyproject (pytest, pytest-timeout,
  httpx, benchweave-sdk>=0.1.0 satisfied by the wheel above).
- Network disabled at run time by a sitecustomize socket guard in the venv
  (connect/connect_ex/create_connection/getaddrinfo/gethostbyname raise); zero
  socket attempts were made by the suite (any attempt would have surfaced as a
  guard RuntimeError, none did).

## Conformance lane

The lane is `tests/adc/test_adapter_conformance.py` — the SDK-conformance
surface (imports `benchweave_sdk.conformance`/`testing`/`validation`). It
collects 26 tests at this commit. The wider `tests/adc` tree (105 tests) also
runs green-for-the-same-reason elsewhere; the 26-test conformance lane is the
PRD §1.2 denominator and is what A1 pins.

## Baseline matrix (three runs, network blocked)

| Run | Collected | Passed | Failed |
|---|---|---|---|
| 1 | 26 | 23 | 3 |
| 2 | 26 | 23 | 3 |
| 3 | 26 | 23 | 3 |

Machine-derived rows and failure texts: `issue215-baseline/baseline-matrix.json`
(generated from the three runs' junitxml; host paths and timestamps removed).

Identical failure set in all three runs (names and first lines verbatim from
the junitxml messages):

1. `test_descriptor_is_schema_valid` — `ValueError: Contract validation
   failed: '0.2.2' was expected` (the ACTIVE schema's `otdp_version` const
   dump; the descriptor pins 0.2.0).
2. `test_lifecycle_is_quiet` — same const-dump shape, same pin.
3. `test_capture_sequence_configure_arm_events_fetch_abort` —
   `ValueError: unknown_contract_schema: otdp/0.2.0/otdp-runtime.schema.json`
   (the SDK vendors one OTDP version; the suite resolves schema paths from the
   descriptor's own pin via `OTDP_SCHEMAS = f"otdp/{DESCRIPTOR['otdp_version']}"`).

This is exactly the PRD §1.2 snapshot: two "'0.2.2' was expected" failures and
one `unknown_contract_schema: otdp/0.2.0/otdp-runtime.schema.json`, 23/26. The
baseline reproduced on all three runs, so A1's re-baseline kill direction does
not fire and slice 1 proceeds.

## Wheel-size baseline (for the served-set payload delta)

Merge-base wheel (one served version per standard, 6 lock rows):
477,244 bytes. The post-slice wheel (9 served versions across 6 standards)
delta is re-measured from a wheel built the same way and committed with the
mechanism.

## Post-slice results (same build path, SDK commit `7d580e1`, 0.3.1)

- **A1 post-run**: 26/26 (junit: 26 collected, 0 failures, 0 errors) with
  the network blocked, the built wheel installed into a clean venv over the
  checkout pin, the plugin installed from the same unmodified archive.
- **Anti-gaming arm** (descriptor pin flipped to the yanked 0.2.1 in a
  copy): 26/26, and `benchweave-sdk check` prints the yank warning naming
  both the pin and the move-to 0.2.2.
- **Wheel**: `benchweave_sdk-0.3.1-py3-none-any.whl` = 624,791 bytes
  (sha256 `ffd6d40e...551719`; INFORMATIONAL, not rebuild-reproducible —
  uv wheel bytes are timestamp-dependent unless SOURCE_DATE_EPOCH is set,
  so a fresh build needs the same byte total, never the same sha) —
  **+147,547 bytes (+144.1 KiB, +30.9%)**
  over the 477,244-byte baseline. The REPRODUCIBLE wheel identity
  (re-measured locally at the fix-wave tip against a freshly built wheel,
  matching the Forge audit's figure): all **134** lock-row files
  digest-match `standards-lock.json`, and the wheel's standards tree
  carries **zero** unrecorded files. The post-slice lock carries 11 CARRIED
  rows (10 served + the yanked-marked otdp/0.2.1) across the 6 standards —
  corrected here from the design's "9 served versions" slip (deviation 1
  below) and from this section's own earlier "served" mislabel of what
  rides the wheel (deviation 2: the CARRIED set rides, yanked marked).
  Uncompressed file-byte sums of the five newly carried version
  directories: otdp/0.2.0 475,076 + otdp/0.2.1 490,955 + registry/0.1.0
  29,904 + execution/0.1.0 67,376 + plugin-ui-preview/0.1.0 7,437 =
  1,070,748 bytes; `du -sk` of the four non-yanked additions totals 664 KB
  (the design's "≈1,604 KB" figure counted otdp/0.2.1's du — 688 KB — which
  the corrected Q10 ruling carries as yanked-marked, and pre-dated the F1
  exclusion of plugin-ui 0.1.1; see the deviations below).
- **CI control wall-clock (#215 fold row 15)**: the committed ADC control
  (`scripts/adc_conformance_control.py` — fetch + wheel build + venv + both
  suite runs + the installed-vs-archive byte assertion) completes in
  4.5–6.1 s wall on the development host (three local full runs: 6.12 s,
  4.79 s, 4.51 s; warm uv caches — the CI lane's cold-cache number will be
  higher and is the lane's own to report). This is the measurement half of
  the design's CI-cost disclosure for the `package` lane's clean-venv
  control.

## Design-record deviations found during the build (evidence in the tests)

1. **"9 served versions" is an arithmetic slip.** The design §3.2's own
   per-id enumeration (otdp {0.2.0, 0.2.2}, registry {0.1.0, 0.1.1},
   execution {0.1.0, 0.2.0}, interface {0.1.0}, plugin-ui {0.2.0},
   plugin-ui-preview {0.1.0, 0.1.1}) sums to 10. The per-id sets are the
   load-bearing rules; the total follows (pinned in
   `tests/standards/test_dependency_policy.py`).
2. **The CARRIED set, not the served set, rides the export/lock/wheel.** The
   design's §3.2 "one entry per SERVED (id, version)" (served = ¬yanked)
   contradicts its own wheel-payload enumeration (which includes
   otdp/0.2.1), the Q10 ruling (explicit pins to a yanked version stay
   conforming — they need the yanked version's bytes offline), and the A1
   anti-gaming arm (a 0.2.1-pinned suite, green). Resolution: the bundle,
   lock and wheel carry retained ∧ in-range (yanked included, marked
   `"yanked": true`); the served set (¬yanked) is re-derived by every
   consumer from the markers plus the mirrored policy block. Pinned in
   `test_bundle_carries_one_entry_per_carried_version`.
3. **The §3.1 cross-check "a yanked or retired entry naming a version with
   no retained directory refuses" is self-contradictory as written**: every
   retired identifier by construction has no retained directory (they are
   the pre-reset enumeration), so the literal rule refuses the seed policy
   block itself. Resolution: yanked entries must name retained in-range
   versions (`policy_entry_unresolved:`); retired entries must name NO
   retained directory and never the active version
   (`policy_retired_active:` / `policy_status_conflict:`). Pinned in
   `test_retired_entry_naming_a_retained_version_refuses`.
4. **§3.2's payload figure and slice-1's scope label name `standards_sync
   _sync_tree`** — no such symbol exists at the merge base (the writer is
   `_write_vendored` + `sync`); names only, the cited mechanisms were
   extended as designed.
5. **A5's "every existing refusal-prefix test byte-unchanged" was
   overstated (#215 fold row 2).** Four meaning-preserving edits touched
   existing tests on this slice (same refusals and behavior pinned against
   the derived values; no prefix changed meaning):
   1. `tests/test_manifest_guards.py` — the duplicate-row refusal's match
      text (`duplicate standard id` → `duplicate standard row`; the message
      gained the multi-version row vocabulary, the refusal is the same);
   2. `tests/test_standards_sync.py` and `tests/test_manifest_guards.py` —
      multi-version report labels (`("otdp",)` → `("otdp@0.2.0",)` /
      `("otdp@1.0.0",)`: same classification, the label now names the row);
   3. the "exactly one otdp document" lookups in
      `tests/test_conformance_lifecycle.py`, `tests/test_validation_checks.py`,
      `tests/test_capture_writer.py`, `tests/test_transport_providers.py`
      and `tests/test_out_of_package_fallbacks.py` — now filtered by the
      derived ACTIVE version (the exactly-one assumption held one version
      per standard; the tree now carries every retained in-range version);
   4. `tests/test_transport_providers.py` — the census call
      `_corpus_known_otdp_features()` now threads the active version.
   The PR body must not repeat the byte-unchanged claim; "no existing
   prefix test changed meaning" is the accurate form.
6. **G-2's landed wording rephrases the design's edit instruction (#215
   fold row 18 — wording deviation, accepted).** The design §5's G-2 item
   was written as an edit instruction ("gains: under multi-version
   admission the authority is the PINNED version's const..."); the landed
   GOVERNANCE text rephrases it as standing doctrine rather than applying
   the instruction's exact phrasing to the prior sentence. The substance
   (pinned-version authority under multi-version admission, active-declared
   value unchanged) is intact; the deviation is stylistic and recorded
   here rather than re-editing governance text.

## Fix wave (#215) — the Tier-3 refute fixes (F1-F6) and the folded LOW/NIT rows

Same branches (`feat/issue215-multi-version-serving`, both repos), RED-first
for every behavior change; the two-commit order held (SDK pushed first, then
the gateway fixes, then the submodule pointer). All RED evidence below is
verbatim from the runs.

### The six refute fixes

**F1 (HIGH) — per-pin validation is digest-blind.** Design §3.2's
"digest-checked against the SDK lock row" was a claim, not a mechanism: the
load path (`contract_documents`) computed no digest, and a planted trailing
newline in
`src/benchweave_sdk/standards/otdp/0.2.0/otdp-device-descriptor.schema.json`
(parsed identically, digest-different) validated clean against a
0.2.0-pinned descriptor — the design §7 risk-1 falsifier, undefended.
RED (SDK): `test_planted_vendored_byte_refuses_per_pin_validation` —
`Failed: DID NOT RAISE ValueError`. Post: every served document is
sha256-checked against its lock row at load
(`served.lock_file_digests` + `validation._load_verified_document`);
unrecorded and tampered files both refuse `vendored_digest_mismatch:` by
name. The prefix joins this slice's enumerations (the CON-4 amendment
family in `docs/internal/invariants.md`, obligation 19); the check CLI and
both A1 arms stay green on clean bytes.

**F2 (MEDIUM) — malformed pins crashed classification.**
`classify_pin('0.3.0-dev','otdp')` (also 'abc', '1.x') raised a raw
`ValueError: invalid literal for int()` from `_tuple()` inside `_move_to`,
and `_resolve_otdp_pin` runs before schema validation, so the traceback
reached callers. RED (SDK): three parametrized failures with frames in
`served.py:149 _move_to`, and the end-to-end arm
`AssertionError: Regex pattern did not match` (the raw parse error surfaced
instead of `version_not_served:`). Post: unparsable pins classify as
unserved under `version_not_served:` with the five VR-37 fields (move-to =
highest served by semver) and a detail naming the parse failure; pins that
parse keep the range detail, so the schema's own const errors stay
reachable (guard test green both ways).

**F3 (MEDIUM) — an extra SDK lock row killed package import.** Planting a
fake otdp@0.2.3 row (no vendored directory) made `import benchweave_sdk`
die during module-level `ADAPTER_API_VERSION` derivation — RED (SDK,
subprocess arm, verbatim): `AssertionError: Traceback (most recent call
last): ... benchweave_sdk/__init__.py", line 26, in <module> ...
contract_documents()[...]` — before the CLI could dispatch, so
`sync-standards --check` could never report the drift. Post: the constants
derive lazily (PEP 562 `__getattr__`); import does no lock/tree I/O; the
load path refuses `served_set_drift: otdp@0.2.3 is carried by the standards
lock but the vendored tree has no such directory` (typed `ServedStateError`,
in-process arm RED was the raw `FileNotFoundError` from
`validation.py:121 visit`).

**F4 (MEDIUM) — `sdk_bump_class_invalid` was mutation-unpinned.** Replacing
`_verify_bump_class` with a pass-through left the full SDK suite green
(504 passed at 7d580e1). Two refusal tests now pin it in EACH repo.
Mutation proof (cp-backup neutralization, both sides, verbatim):
SDK — `2 failed`, each `Failed: DID NOT RAISE ValueError` (and the full
suite under the plant: 517 collected, exactly the two gate tests plus
nothing else red); gateway — `tests: 2, failures: 2`, both
`Failed: DID NOT RAISE ValueError`; green on restore in both repos.
Assertions: carried-set growth inside an unchanged range with an unmoved
SDK version refuses; a declared-range change with only a PATCH motion
refuses.

**F5 (MEDIUM) — the sync report laundered dropped carried versions.** A
range-narrowing train (range >=0.2.1,<0.3.0, active 0.2.2 -> 0.2.3,
otdp/0.2.0 leaving the carried set under copy-never-move) printed
`changed=('otdp@0.2.3',)` with `removed=()` — the succession branch
consumed the one remaining same-id prior row whatever it was. RED (SDK):
`AssertionError: assert () == ('otdp@0.2.0',)`. Post: the branch consumes
only the id's prior ACTIVE row (marked, else the highest same-id version
for the unmarked legacy shape); the narrowing scenario reports
`removed=('otdp@0.2.0',)`, `added=('otdp@0.2.3',)`, `changed=()` — pinned
in both repos. One pre-existing pin moved with the mechanism (the
stale-lock reclaim test's one-row bundle now reports `changed` with the
non-active priors under `removed` — honest where the drop was previously
unreported); comment updated in place.

**F6 (MEDIUM, CI-blocking, fixed first) — stale committed uv.lock.** At
7d580e1 `pyproject.toml` said 0.3.1 while `uv.lock` pinned benchweave-sdk
0.3.0. Evidence: `uv lock --check` exit 1 on pristine bytes ("error: The
lockfile at `uv.lock` needs to be updated, but `--check` was provided");
after `uv lock` (one row, 0.3.0 -> 0.3.1) exit 0, and the ci.yml lane's
`uv sync --locked --extra test` passes on pristine `git archive HEAD`
bytes (exit 0 in a scratch extraction).

### The folded LOW/NIT rows (owner row-call: fold all 25)

| # | Disposition |
|---|---|
| 1 | BEHAVIOR (SDK): `_move_to` picks max by semver tuple. RED (lexical implementation restored via cp backup, corrected fixture): `assert '0.2.0' == '0.10.0'` failure shape; green after. {0.2.0, 0.10.0} test pinned. |
| 2 | TEXT (09a deviation 5 above): A5's "byte-unchanged" corrected; the four meaning-preserving test-edit classes enumerated. |
| 3 | TEXT (SDK obligation 5 + `__init__` docstring): the lazy derivation contract documented; fail-closed kept; no redesign. |
| 4 | BEHAVIOR (gateway): yank `since` gated like the dev-head `opened` field (shape + `date.fromisoformat`). RED: six parametrized `Failed: DID NOT RAISE StandardsError` across the non-ISO and impossible-calendar arms. |
| 5 | TEXT: check.py docstring + both drift messages + export.py `_entry` docstring now say CARRIED (yanked marked); the served set is named as re-derived. |
| 6 | TEXT: CON-8 amendment gains its prescribed first sentence verbatim ("the identity block's authority and active-entry derivation are UNCHANGED."). |
| 7 | TEXT: the R-1/R-2 ruling artifact lands VERBATIM in invariants.md (bytes extracted from GOVERNANCE.md, both blocks); the paraphrase is now a pointer. |
| 8 | TEXT: G-3 and obligation 19 say the CARRIED set is mirrored (served re-derived); check.py wording above. |
| 9 | TEXT: CON-12's amendment gains the lands-with-slice-5 marker in CON-14's disclosure style. |
| 10 | TEXT: obligation 19's retired-entry rule un-inverted — yanked must name retained in-range (`policy_entry_unresolved:`); retired must name NO retained dir and never the active (`policy_retired_active:`/`policy_status_conflict:`); retired-with-no-dir is the correct seed state. |
| 11 | TEXT: ERRATUM pointers at the three superseded design spots (§3.1 cross-check, §3.2 "9 served", §3.2 served-rides-export) + 09a indexed in the planning README. |
| 12 | TEXT: the wheel section above now says 11 carried rows (10 served + the yanked mark) and names the deviations it corrects. |
| 13 | TEST: `test_a_planted_literal_fails_the_ratchet_in_a_scratch_copy` — scratch copy of the real tree + one planted literal: count rises to baseline+1, exit 1, `--json` names the site. The ratchet test's citation now points at a committed demonstration. |
| 14 | DELETED with proof: `served_version_unresolved:` was defensively unreachable — `retained_versions` enumerates retention FROM corpus rows (a retained version has >=1 row by construction), and `export_bundle` reaches `_entry` only through `carried_versions` (retained ∧ in-range), so the empty-enumeration branch could not fire from loader-reachable state (the only theoretical divergence is a mid-export edit of corpus-manifest.json — outside the committed-bytes model every other check shares). Branch deleted; the proof lives in `_entry`'s docstring and here. No enumeration ever listed the prefix. |
| 15 | MEASURED: the CI control's wall clock committed above (4.5-6.1 s local, warm caches; the lane's cold-cache number is the lane's own). |
| 16 | BEHAVIOR (gateway): `_lock_active` refuses unmarked multi-row and multi-marked locks as `lock_invalid` (parity with the SDK's `served.active_version`) instead of picking rows[0]. RED: both new tests failed with the lock accepted (no `lock_invalid` in prefixes); green after. |
| 17 | TEXT+ASSERTION (ADC control): docstring says unmodified-by-construction and names the real installed-vs-archive byte assertion now wired in (`assert_installed_matches_archive`, per-file sha256); the third-party fetch dependency and its failure mode are named in a comment at `ADC_REPO`; the external repo stays unvendored. |
| 18 | TEXT (09a deviation 6 above): the G-2 sharpened wording recorded as an accepted wording deviation. |
| 19 | TEXT: CON-12's original row line restored byte-exact (trailing asterisk); the amendment moved to its own paragraph. |
| 20 | TEXT (count script docstring): the 13-to-12 delta is now regenerable — this definition counts the SAME 12 sites at `ef969af` and `403c061` (verified by re-running the definition on both trees), so the hand count's extra site was prose-classified; the hand count's worksheet was never committed, so WHICH prose site is unnameable from evidence — recorded as such rather than invented. |
| 21 | TEXT: this slice's citations normalized to #215 naming #203 as parent (invariants amendment attributions, CON-14 row body, GOVERNANCE G-3 and its pointer line, obligation 19). |
| 22 | TEXT (count script register): `scripts/adc_conformance_control.py`'s YANKED_PIN/MOVE_TO literals registered with their motion mechanism (flip with the yank policy block, same arc as the policy row); the A4 denominator unchanged — scripts/ was never inside the counted tree. |
| 23 | TEXT (SDK release-review matrix rows 2 and 5): machine truth names the ACTIVE row of the multi-row lock (the constants derive lazily from it; the active row governs the badges). |
| 24 | TEST: `test_two_carried_plugin_ui_versions_dedupe_the_parity_code_row` — synthetic plugin-ui/0.2.1 corpus rows put two carried versions under the narrow range; the export succeeds, both rows list the parity code row, one copy ships. Green on landing (the branch existed untested; pinned, not fixed). |
| 25 | BEHAVIOR (SDK): the yank warning moved to `validate()` — the one path every entry point shares — so envelope validation (`validate_request`/`validate_result` with a pinned yanked version) and explicit-key validation warn too. RED: both new path tests `DID NOT WARN. No warnings of type ... were emitted`; served-pin control silent; the A1 anti-gaming arm's warning text unchanged (re-proven at close-out). |

## Late Forge folds (#215) — the cross-vendor audit findings on the fix tips

Folded into the same branches under the owner's fold-all posture; items 1-2
RED-first, 3 wording-only, 4 record-only. RED evidence verbatim.

**Late fold 1 (MEDIUM) — the F1 digest gate's coverage hole.** The gate
wired in F1 covered only what `contract_documents` enumerated —
('otdp','registry','plugin-ui') — and `fixtures` read the vendored fixture
schema directly, so plugin-ui-preview (and execution/interface) rows rode
the lock and wheel outside the verified loader. RED (the executed
falsifier): tampering
`src/benchweave_sdk/standards/plugin-ui-preview/0.1.1/fixture.schema.json`
('required'->'xrequired', parse-valid) loaded clean on the fixture path —
the test's refusal never fired and the run proceeded to `_target_index`;
the coverage arm RED: `AssertionError: lock-recorded documents outside the
verified loader: ['execution/0.1.0/bench.schema.json', ...]`. Fix: the
loader enumerates EVERY carried standard the lock names, and the fixture
schema load rides it (`fixtures._fixture_schema` through
`contract_documents`; `_schema_path` deleted, its fallback-trust tests
consolidated onto the loader's own pin). Envelope and explicit-key paths
already loaded through the same gate, so runtime JSON-document coverage
now equals lock coverage and the claim texts ("every document at load" —
CON-4 amendment, obligation 19, the F1 note above) are true as written.
One runtime path deliberately stays OUTSIDE the JSON-document gate and is
named here so claim and mechanism agree: `presentation` IMPORTS the
vendored plugin-ui contracts module (a .py code row, deferral D2's
registered exception) — not a document load; the whole-tree sweep
(`verify_vendored_digests`, every lock row including .py) covers it at
check time.

**Late fold 2 (LOW) — the bump-class gate was blind to active re-points.**
An active re-point inside an unchanged carried set with an unmoved SDK
version (rollback 0.2.2 -> 0.2.0 inside the range) passed sync self-check
and the gateway check while `OTDP_VERSION`/`ADAPTER_API_VERSION` derive
from the active row. RED: `Failed: DID NOT RAISE ValueError` (the refusal
test) and `AttributeError: 'SyncReport' object has no attribute
'active_changes'` (the report half). Fix: the gate refuses an active
re-point on an unmoved version (`sdk_bump_class_invalid:` naming both
ends — one SDK version never covers two derived-constant states);
`SyncReport.active_changes` names the pair (`otdp@0.2.2->0.2.0`) in the
report, the CLI summary and the check-mode drift refusal. Gateway twins
landed and mutation-proofed (neutralized gate: the refusal twin 1/1 red,
`Failed: DID NOT RAISE ValueError`; restored: green).

**Late fold 3 (NIT, wording).** The move-to label now reads as what the
pinned derivation computes — "move-to {v} — the highest served version,
the recommended re-target" — in `refusal_for` and the yank warning. The
VR-37 field names and the A3-pinned semantics are unchanged (the
derivation is max(served) on both arms, so "highest served" is exact);
"nearest" is retired as overpromising an adjacency nothing computes.

**Late fold 4 (NIT, record).** The wheel section above now carries the
reproducible identity (all 134 lock-row files digest-match
`standards-lock.json`; zero unrecorded files in the wheel tree —
re-measured locally at the tip, matching the audit's figure) and
annotates the byte total/sha as informational: uv wheel bytes are
timestamp-dependent without SOURCE_DATE_EPOCH.
