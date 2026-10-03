# Issue #238 — load-boundary refusal for separator-spoofed normative rows

- **Date:** 2026-10-03
- **Issue:** gateway #238 (backslash-form ACTIVE normative rows load unrefused,
  laundering dev bytes past the export leak detector)
- **Base read:** local `main` @ `4dfaabf`; `git diff --stat 4dfaabf..origin/main` over
  `src/benchweave/standards/`, `tests/standards/`, and both manifests is EMPTY — the
  reads below are current for the touched files.
- **Verdict:** **BUILD** — one minimal slice, two named deferrals, one scope correction
  to the issue (the same hole admits traversal-form rows on every platform, not only
  the Windows backslash form; evidence below).

The record is written without the review rubric's eight Step-1 keywords so the
expected diff's keyword scan is stated honestly rather than dodged silently — the scan
counts are in §8.

## 1. Root cause — verified line by line, not assumed

The authority routing for a manifest normative row is a **string prefix test**, and the
prefix is dodgeable in more than one way. Three code facts compose into the gap:

1. **`load_manifest` applies no path lexicon check at all** —
   `src/benchweave/standards/manifest.py:177`. The active entry's rows pass exactly one
   check (`status not in VALID_STATUS or not normative` → `standards_entry_invalid`);
   the path strings themselves are never inspected. Dev rows ARE contained
   (`_load_dev_head`: `posixpath.normpath(relative).startswith(head_prefix)` →
   `dev_path_outside_head`), which is why the issue calls the posture asymmetric.

2. **`_check_normative_path` early-returns for rows not prefixed `standards/`**
   (`src/benchweave/standards/manifest.py:848`) — "non-standards paths (the parity
   validator) carry no second authority". That exemption is the one legitimate
   non-corpus row in the tree (`src/benchweave/presentation/contracts.py`, the
   plugin-ui parity live source). The early return fires AFTER only an `is_file()`
   check. A row `standards\otdp\0.2.0-dev\leak.json` does NOT start with `standards/`
   (backslash, not slash) → the digest-pin second authority is skipped entirely.
   On Windows, `root / "standards\otdp\..."` resolves through the real directory
   tree into the dev tree, so `is_file()` is True and the row sails through
   `validate_manifest`.

3. **`_entry`'s bundle-path mapping launders the bytes** (`export.py`, the
   `relative.removeprefix("standards/") if relative.startswith("standards/") else
   f"{entry.id}/{Path(relative).name}"` branch): a row that dodges the prefix maps to
   `<id>/<basename>` — on Windows, `otdp/leak.json` — and the active row's file set
   comes straight from `entry.normative` (`export_bundle` → `_entry`, active = True).
   The export leak detector's predicates in
   `tests/standards/test_export.py:204` (`test_export_carries_no_dev_head_bytes`) split
   bundle paths on `"/"` only, so a laundered basename carries no `-dev` segment, and
   the written-files set equals the listed set — both predicates hold while the bundle
   ships dev bytes. The detector is a planted-tree TEST pin, not a production guard:
   nothing in `export_bundle` inspects row shape.

**Scope correction to the issue (design-time finding):** the same early-return hole
admits a **traversal-form** row with no backslash anywhere —
`src/../standards/otdp/0.2.0-dev/leak.json`. `startswith("standards/")` is False
(it starts `src/`), `is_file()` resolves through the OS on every platform, and the
basename mapping presents `otdp/leak.json` over dev bytes **on POSIX too**. The
issue's proof shape (backslash, Windows) understates the class: it is
platform-independent for the `..` form. The chosen pin — mirror `_check_row_path`,
which refuses backslash AND `..` AND absolute/drive forms — closes both forms at once;
a backslash-only check would leave the platform-independent half open.

**Reachability (unchanged from the issue):** hand-corrupted manifest only; a hardening
gap in depth, not an active defect. No in-tree writer can produce these rows (§4).

## 2. The mechanism

One private helper in `src/benchweave/standards/manifest.py`, mirroring repin's
`_check_row_path` (`src/benchweave/standards/repin.py:201`, refusal at :217)
semantics for the standards-manifest surface, called at LOAD from both normative-row
loops:

```python
def _check_normative_row_path(entry_id: str, relative: str) -> None:
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if (
        not relative
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or "\\" in relative
        or ".." in posix.parts
    ):
        raise StandardsError(
            f"normative_path_escape: {entry_id}: {relative} "
            "(manifest rows are '/'-separated repo-relative paths, #138; a "
            "backslash, drive, absolute, or ../ traversal form dodges the "
            "'standards/' prefix that routes a row to the corpus-pin authority)"
        )
```

- **Call site 1 — active rows:** in `load_manifest`'s per-entry loop, a
  `for relative in normative: _check_normative_row_path(entry_id, relative)` pass
  placed after the existing `standards_entry_version_invalid` check (no existing test
  carries both defects, so refusal order vs that check is unpinned; this placement
  keeps every pinned behavior stable).
- **Call site 2 — dev rows:** inside `_load_dev_head`'s existing per-path containment
  loop, AFTER the `dev_path_outside_head` containment check. Containment stays the
  dev-specific authority (a plain backslash dev row keeps refusing
  `dev_path_outside_head` exactly as today); the lexical mirror catches only what
  containment genuinely misses — the tail-backslash form
  (`standards/<id>/<v>-dev/a\b.json` passes `startswith(head_prefix)` and resolves
  deeper into the head on Windows).
- **Imports:** `PurePosixPath, PureWindowsPath` join the existing `pathlib.Path`
  import. No other module changes. `validate_manifest` needs nothing: it consumes an
  already-loaded `StandardsManifest`, so spoofed rows are unreachable past load.

**Why load, not validate:** `load_manifest` is the boundary every consumer crosses —
`export_bundle`, `validate_manifest` callers, and repin's classifier
(`_regenerable_paths` calls `load_manifest`, and its own `continue` branch for
non-`standards/`-prefixed rows is the same silent pass). The corpus twins
(`declared_dev_head`) route through `_load_dev_head`, so the refusal rides there
automatically; `active_version_from_corpus` reads only `version` and never opens a
normative path (not exposed).

**Error shape:** typed `StandardsError(ValueError)`, machine-matchable prefix
`normative_path_escape: {entry_id}: {relative}` — the `normative_*` naming family
(`missing_normative_file`, `normative_not_in_corpus_manifest`,
`normative_hash_mismatch`, `normative_bundle_path_collision`) with the entry named,
mirroring repin's `pin_path_escape` vocabulary for the same lexicon on the corpus-row
surface. Two surfaces, two prefixes, deliberately: each is matchable in its own
lane, and repin's prefix is its own pinned vocabulary. A shared core could be
extracted later (deferral D4) — not in this slice; repin is untouched.

**Assessment of the export-detector dual-separator split (the brief's question):**
**redundant — do not add.** With load-side refusal, `export_bundle` (which calls
`load_manifest` first) can never reach `_entry` with a spoofed row, so a
dual-separator split in the detector's `-dev` predicate would guard an unreachable
state; as an export-level TEST arm it is not even constructible (the planted export
would refuse at load before `_entry` runs). `test_export_carries_no_dev_head_bytes`
**stays as-is** — it remains the pin that export iterates the active spine, and it is
now backed by a production refusal instead of standing alone. The honest residual the
detector still only PIN-tests (production does not guard) is named in D2.

## 3. Minimal first slice

Production: the helper + two call sites in `manifest.py` (~20 lines with comment).
Tests (all in the established planted-tree idioms of `tests/standards/`):

1. `tests/standards/test_manifest.py::test_backslash_active_normative_row_refuses_at_load`
   — headless planted tree (`_planted_tree` shape), active normative
   `["standards\\demo\\0.2.2-dev\\demo.schema.json"]` (the issue's laundering shape on
   the invented `demo` id); expect
   `pytest.raises(StandardsError, match=r"normative_path_escape: demo:")` on
   `load_manifest`. No file need exist — load does no filesystem access; today this
   loads clean (RED = "DID NOT RAISE").
2. `tests/standards/test_manifest.py::test_traversal_active_normative_row_refuses_at_load`
   — `["src/../standards/demo/0.2.2-dev/demo.schema.json"]`, same expectation. This is
   the platform-independent form from §1 — the arm that pins the scope correction.
3. `tests/standards/test_manifest.py::test_backslash_tail_dev_normative_row_refuses_at_load`
   — `_dev_head_tree` with dev-block normative
   `["standards/demo/0.2.2-dev/a\\b.json"]` (passes containment, fails the mirror);
   expect `normative_path_escape`. The discriminating dev shape — the plain-backslash
   dev row already refuses `dev_path_outside_head` (containment order, §2).
4. `tests/standards/test_manifest.py::test_non_standards_parity_shaped_row_still_loads`
   — discrimination arm: a planted manifest whose normative lists BOTH a
   `standards/...` row and a relative posix row outside `standards/` (the parity
   row's shape) loads clean. Guards against an over-broad refusal; green before AND
   after the fix.
5. `tests/standards/test_export.py::test_export_refuses_a_separator_spoofed_normative_row`
   — the launderer's own lane: `shutil.copytree` the real corpus + parity file (the
   `test_export_refuses_a_tampered_carried_version_corpus_row` idiom), append the
   backslash row to otdp's active normative, expect
   `pytest.raises(StandardsError, match="normative_path_escape")` from
   `export_bundle` and `not (tmp_path/"out").exists()` (fail before any write).
6. `tests/standards/test_repin.py` — one pin arm for the precedent itself:
   `pin_path_escape` currently has exactly one repo-wide occurrence (the raise site,
   `repin.py:217`); no test pins it. Plant a corpus row with a backslash path, expect
   `pytest.raises(StandardsError, match="pin_path_escape")` from `repin_manifest`.
   Test-only; green on arrival, with the mutation note that deleting `_check_row_path`'s
   call reddens it (its toggle-off equivalent — it pins existing behavior, it is not a
   fix).

Docs: the CON-7 amendment in `docs/internal/invariants.md` (§5) and this record.
**Zero bytes move under `standards/`** — the tripwire
(`git diff origin/main...HEAD -- standards/`) stays EMPTY, no corpus rows repin, the
export is byte-identical (`test_export_is_byte_identical_across_runs` unchanged).

## 4. The negative proof — no legitimate bytes carry these forms

A refusal that fires on legitimate bytes is worse than the gap, so the negative was
proven, not assumed:

- **Committed `standards/standards-manifest.json`:** read whole — every normative row
  is posix-form; the single non-`standards/` row is the parity live source
  (`src/benchweave/presentation/contracts.py`); no backslash, no `..`, no absolute
  forms, no `-dev` segment (also machine-scanned: zero hits).
- **Committed `standards/corpus-manifest.json`:** all 226 rows machine-scanned at
  HEAD — zero backslash paths, zero backslash `lineage` values, every row
  slash-separated under the six standard id prefixes.
- **No in-tree writer constructs OS-form rows:** the repo-wide `as_posix` survey
  shows the "'/'-separated (#138)" discipline at every site that turns a filesystem
  path into a manifest key or row (`repin.py:259`, `check.py:391`, the dev-head state
  derivation `dependency.py:1964`, and the fixtures). No `str(path)` writer of
  manifest rows exists; the standards manifest is hand-authored under governance and
  repin rewrites digests only (CON-7), so a backslash row could only ever enter by the
  hand-corruption this slice refuses.
- **Fixture survey:** the planted trees in `tests/standards/`, `tests/control/`,
  `tests/contracts/` all write posix-form rows (surveyed via the same scan).

## 5. Invariant and cross-surface impacts

- **New refusal prefix** `normative_path_escape:` on the load boundary — proposed as an
  **amendment to CON-7** (`docs/internal/invariants.md`), whose amendment chain already
  carries the load-refusal family (`standards_entry_invalid`,
  `dev_target_not_greater`, `dev_head_stale`, pure-semver active). Amendment text
  (keyword-free): the load boundary refuses separator-spoofed normative rows in both
  the active and dev lists, mirroring repin's row-path lexicon, because a row that
  dodges the `standards/` prefix dodges the corpus-pin second authority, and
  Windows-form rows resolve into the dev tree where the export's basename mapping
  launders the bytes; committed bytes carry none of these forms.
- **CON-7's own clauses are untouched** (repin unchanged); CON-8's identity machinery
  untouched (its duplicate-id guard sits past `load_manifest`, before the row loop —
  ordering unaffected).
- **Surfaces that do NOT move:** MCP tools, REST/openapi, CLI (the new
  `StandardsError` propagates through the existing `standards export error:` styling),
  operator docs (no CLI-surface change), the SDK repo (no submodule pointer, no
  vendored bytes — the bundle is byte-identical), the fixture lattice, CI jobs. CI
  cost: +6 tests in existing lanes; fast lane per commit (bare ruff, fresh-cache bare
  mypy, focused pytest), full battery once before push.
- **Standards-governor mandate:** NOT triggered — no `standards/` corpus bytes, no
  manifests, no plugin contract locks, no SDK vendored tree, no standard-version
  strings in the diff. The review states this explicitly alongside the empty-tripwire
  result.
- **On-disk formats/schemas:** none change (the refusal reads the existing manifest
  format; no schema or persisted-format surface is touched — the Tier-3
  persisted-format path rules do not fire; see §8).

## 6. Acceptance — pre-committed

Metric: deterministic pytest outcomes on named arms (no sampling; counts read from
`--junitxml` attributes or exit codes, never an output-filter summary line). The RED
run IS the measurement; this record exists before it.

**RED (production fix withheld, tests present) — each must fail with "DID NOT RAISE"
on the refusal match, not fail for an unrelated reason:**
- `tests/standards/test_manifest.py::test_backslash_active_normative_row_refuses_at_load`
- `tests/standards/test_manifest.py::test_traversal_active_normative_row_refuses_at_load`
- `tests/standards/test_manifest.py::test_backslash_tail_dev_normative_row_refuses_at_load`
- `tests/standards/test_export.py::test_export_refuses_a_separator_spoofed_normative_row`
  (before the fix the export SUCCEEDS and ships the row — the arm also asserts the
  refusal precedes any write).

**GREEN (fix applied):** the four arms above, plus
`test_non_standards_parity_shaped_row_still_loads` and the repin `pin_path_escape`
pin arm (green on arrival), plus the FULL battery
(`uv run pytest`, `tests/faults/` included per convention for `control/`-adjacent
work — not strictly required here, cheap to include) with zero failures, and
`test_export_is_byte_identical_across_runs` still green (bundle unchanged).

**Toggle-off check:** revert ONLY the `manifest.py` helper and its two call sites
(tests kept) → the four RED arms go RED again; the discrimination arm and the
existing suite stay green. The repin pin arm reddens only if `_check_row_path`'s call
is deleted (its own toggle-off, noted in §3.6).

**SHIP if:** four arms red→green exactly as named; full battery green; tripwire
empty; every existing manifest-planting test still loads (the §4 negative proven
dynamically, not just by scan).

**KILL if:** any pre-existing test reddens with `normative_path_escape` (the refusal
is over-broad — a legitimate row form exists that the scan missed; rescope rather
than widen the exemption), or any arm's RED is a wrong-reason failure (a planted-tree
shape error firing a different prefix — e.g. `dev_block_invalid` — means the arm does
not discriminate; repair the arm before reading anything into it).

**UNDERPOWERED (the measurement-is-broken branch):** if the export arm cannot be
constructed without tripping an unrelated export refusal first, drop that arm
honestly and keep the claim at the load boundary only — do not tune the fixture until
it passes; report the interference.

## 7. Top risks, each with its falsifier

1. **Over-broad refusal on a future legitimate row** (e.g. a second parity-style live
   source, or a Windows contributor hand-authoring rows). Falsified today by §4; the
   discrimination arm holds the line. If it ever fires legitimately, the error text
   names the remediation ('/'-separated repo-relative rows) — a loud, correctable
   refusal, never a silent pass.
2. **Refusal-order drift** (`normative_path_escape` firing where a test expects
   `dev_path_outside_head`). Containment-before-mirror ordering (§2) preserves every
   existing prefix outcome; no current test pins a row carrying both defects. If a
   refute lane finds one, the ordering flips per that test — behavior equal, prefix
   vocabulary preserved.
3. **The refusal is lexicon-only** (what it does NOT catch, per claim discipline):
   a well-formed posix ACTIVE row naming an open dev head's directory launders TODAY
   with no separator trick (the open head's own corpus row supplies the matching pin;
   `_entry` ships it; only the planted detector test pins the shape). Deferred (D2),
   not silently absorbed. Also uncaught: the direct-parse consumers that bypass
   `load_manifest` (D1) and resolution-level escapes on `standards/`-prefixed rows
   (covered by digest-pin equality, and repin's symlink refusal — unchanged).
4. **Bundle-path collision masking in the export arm** — if the planted basename
   collides with a real corpus file the export refuses `normative_bundle_path_collision`
   instead; the arm uses `leak.json` (no corpus collision) to keep the refusal under
   test the load-side one. A collision in CI would be a wrong-reason RED (§6's
   underpowered branch).

## 8. Review tier and the Step-1 keyword scan (#254)

**Tier 2.** Trigger: production code under `src/` plus test code under `tests/` —
the Tier-2 rule. No Tier-3 path rule fires: no `src/benchweave/contracts/` byte, no
corpus `standards/` content (the rubric's `standards/` names the machine-artifact
home — manifests and schemas — none touched), no JSON Schema file, no registry/
discovery change, no fixture lattice, no dependency motion, no submodule pointer.
**Keyword scan over the whole expected diff** (manifest.py helper + call sites, three
manifest test arms, one export test arm, one repin pin arm, the CON-7 amendment, this
record — docs and code alike):

- `threading` 0 · `asyncio` 0 · `subprocess` 0 · `sha256` 0 · `hashlib` 0 ·
  `migrate` 0 · `recovery` 0 · `protection` 0

This record is deliberately written within that vocabulary budget (digest pins, not
digest-algorithm names) so the stated counts are true, not gamed after the fact. The
review re-derives the tier independently over the ACTUAL diff; if a fold wave
introduces a keyword, the tier re-fires at that point and the deep lane runs — the
counts above cover this record's expected diff only.

## 9. Precedent

- **Nearest in-tree refusal mirrored:** `src/benchweave/standards/repin.py:201`
  `_check_row_path` — the identical lexicon (empty / posix-absolute /
  windows-absolute / drive / backslash / `..`) for corpus-manifest rows, refusing
  `pin_path_escape` (repin.py:217), applied to every row AND its `lineage` value.
  This slice extends that proven lexicon to the standards-manifest surface at its own
  load boundary; it invents nothing.
- **Load-boundary refusal family:** `load_manifest` / `_load_dev_head`'s existing
  structural refusals (`standards_entry_duplicate`, `standards_entry_version_invalid`,
  `dev_path_outside_head`, `dev_target_retired`) — every bad state unloadable, never
  warned about; this slice joins that family.
- **Test idioms:** the planted trees of `tests/standards/test_manifest.py`
  (`_planted_tree`, `_dev_head_tree`) and the copytree-then-corrupt export idiom of
  `tests/standards/test_export.py`
  (`test_export_refuses_a_tampered_carried_version_corpus_row`).

## 10. Deferrals

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | The direct-parse seam: consumers reading `standards-manifest.json` WITHOUT `load_manifest` carry the same prefix-spoof shape — verified `control/documents.py:657 _otdp_normative_path` and `control/provider_settings.py:133 provider_contract_validator` (both filter `entry["normative"]` by `Path(relative).name` and strip `removeprefix("standards/")`); checkout-Windows exposure, wheel-side has no dev tree. Sweep = route both through a shared loader or apply the same lexicon at their resolution points. | follow-on issue (to be filed by the coordinator from this row) | the issue is filed and picked up (assignment or in-progress note); or any descriptor/provider-schema resolution whose basename-matched row resolves into a `-dev` directory |
| D2 | The well-formed posix laundering form: an ACTIVE row naming an open dev head's directory passes every lexicon check and pins against the open head's own corpus row; production export ships it (only the planted detector test pins the shape). Mechanism: refuse `-dev` SEGMENTS in ACTIVE normative rows at load (repin's lineage idiom `any(part.endswith("-dev") ...)`, repin.py:199-207); committed bytes scan clean (zero `-dev` segments), so the refusal is safely landable — it is deferred because it tightens manifest semantics beyond the owner's called pin and deserves its own RED arms and a governor glance. | follow-on issue (same filing) | the next dev-head-opening corpus train lands (a `standards/<id>/<v>-dev/` directory with corpus rows appears on main), or the owner calls for it |
| D3 | Sharing one lexicon core between `repin._check_row_path` and the new helper (dedup; two prefixes stay two vocabularies). | documentation here (this record's §2) | a third surface needs the same lexicon (the D1 sweep is the likely carrier) |
| D4 | A `standards/GOVERNANCE.md` sentence stating the '/'-separated row rule at authoring time — deliberately NOT ridden: editing it moves `standards/` bytes, tripping the standards-byte gate for a doc nicety. | documentation here | the next governance-doc-touching train (any bump that edits GOVERNANCE.md anyway) |

## 11. What the coordinator should decide

1. Confirm the full-mirror scope (backslash + traversal + absolute/drive) as the
   reading of the owner's "refuse `\` … mirroring `_check_row_path`" — the traversal
   arm is outside the issue's letter but inside its class, and is the
   platform-independent half (§1).
2. File D1/D2 as their own issue (or fold D2 into this slice if the owner prefers the
   stronger pin now — one extra condition, two extra arms; the committed-bytes scan
   already clears it).
3. The tier call in §8 governs review depth; if the owner prefers the deep lane
   regardless (the refusal sits in the standards trust boundary's approach path), the
   Tier-3 refute is cheap to add and nothing in this design depends on the tier.


## Addendum 2026-10-03 — lane B HIGH fold: the `./` class and the normpath-identity closure

Lane B's refute reproduced a HIGH on the shipped fix, end-to-end on POSIX: a
LEADING `./` segment dodges every predicate of `_check_normative_row_path`
(`PurePosixPath('./standards/x').parts == ('standards', 'x')` — pathlib
collapses `.` parts), while the RAW string fails `startswith('standards/')`,
so `_check_normative_path` early-returns (no corpus-pin authority) and
`_entry`'s basename mapping launders the row. Captured repros: a row
`./standards/otdp/0.2.0-dev/leak.json` on otdp's active normative exported
successfully and shipped `otdp/leak.json` with the planted dev body; a row
`./operator-notes.txt` (no `standards/` segment, no `-dev`, no corpus row)
shipped `interface/operator-notes.txt` — an arbitrary unpinned checkout file
under a standards id. The dev loop admitted the same class (F3): a
`./`-prefixed dev row passes containment (normpath collapses it into the head
prefix) and the parts-based mirror saw no `..`.

This corrects section 2's claim that export "can never reach `_entry` with a
spoofed row": that held for the forms the section-2 lexicon covered
(backslash, traversal, `..`, absolute) and the `./` form sat outside it — the
class is bigger than the lexicon, the claim's mechanism was not wrong. The
fold adds ONE identity predicate to the same helper — refuse when
`posixpath.normpath(relative) != relative` — closing `.`, `./`, `//`,
interior `./` and trailing-slash forms at once. Committed bytes are canonical
(machine check at the fold: 60 standards-manifest normative rows + 226 corpus
rows, zero non-canonical), so nothing legitimate fires; the discrimination
arm and every existing planted-tree test still load. The refusal prefix
`normative_path_escape` is unchanged; the message enumeration now names
non-canonical forms honestly. Four RED arms pin the class (three load arms —
an active `./` row, an arbitrary-file `./` row, a `./` dev row — plus the
end-to-end export arm; all four DID NOT RAISE pre-patch, all green
post-patch). The eight Step-1 keywords: zero occurrences in this addendum and
the fold diff, stated under the same budget discipline as section 8. The
CON-7 amendment is reworded in the same fold: the helper now EXCEEDS repin's
lexicon (repin has no identity predicate — a potential repin follow-up, not
folded here: repin's rows are machine-written canonical by construction,
section 4), and "separator-spoofed" alone under-describes the dodge set.

## Addendum 2026-10-03 (second) — lane A corrections: case camouflage, scan honesty, residual disclosure

Three corrections from adversary lane A, folded same-branch:

1. **Case-camouflaged prefix (lane A MEDIUM).** `'Standards/...'` dodges
   the raw prefix everywhere and, on case-insensitive hosts (APFS, default
   NTFS), still resolves into the standards tree — lane A captured the
   export shipping it at the pre-fold tip on macOS. `posixpath.normpath`
   cannot catch it (identity holds), so the helper gains its own
   predicate: refuse when `relative.lower().startswith("standards/")` and
   not `relative.startswith("standards/")`. One RED arm pins it
   (`test_case_camouflaged_prefix_row_refuses_at_load`; the end-to-end
   laundering is case-insensitive-host-only, so the load arm is the
   portable pin). Case-sensitive hosts previously refused the row at
   validate as `missing_normative_file`; the load boundary now closes it
   for all hosts.
2. **Section 8 scan honesty (lane A LOW, G4).** The record's keyword scan
   claimed `sha256: 0` over its named expected diff; the diff carries one
   genuine added-line hit — the `test_repin.py` fixture's
   `"sha256": "0" * 64` corpus-row key, unavoidable by format. Honest
   count: 1, wrong at writing time (the record's prose avoided the word;
   the fixture could not). Tier call unaffected — a test-fixture dict key,
   not digest machinery — and re-derived over the fold diffs: still 1.
3. **Residual disclosure and blast radius (lane A MEDIUM mechanism note +
   NIT).** Repin's mirrored precedent carries filesystem backstops
   (`pinned_file_absent`, `corpus_file_unpinned`) that the load boundary
   structurally lacks (load does no filesystem access, by design); the
   load lexicon + identity + case predicates are therefore weaker than
   repin's surface for rows that pass every lexical check yet name
   unpinned bytes — those remain caught at validate
   (`missing_normative_file` on case-sensitive hosts) and by export's
   bundle-path collision check. Separately, the pre-fix blast radius was
   understated: one planted non-standards row multiplies into EVERY
   carried row of its entry via export's live-source listing (lane A
   captured the otdp leak row in all three carried versions' bundle
   rows), not only the active row.
