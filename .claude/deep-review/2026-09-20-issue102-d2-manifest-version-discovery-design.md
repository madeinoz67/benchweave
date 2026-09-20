# Issue #102 D2 — manifest-driven version discovery in `check_devices.py` + the report pin

- Date: 2026-09-20
- Status: design (pre-implementation; committed on `feat/issue102-d2-manifest-version-discovery` before the fix commits)
- References: gateway issue #102 (D2, named the structural closer by PR #101), issue #97 re-scope comment 5748876078 ("Order: 1 first — it binds immediately and changes what 2 is worth"; #118 merged as 1, `4199b63f`)
- Severity: mechanical-defect-class removal; no corpus bytes, no manifest rows, no invariants change

## 1. The defect class, measured

A bump's `OUT`/`REPORT_PATH`/title hand-moves are convention, not mechanism — the
#79 design record disclosed it, #102 D2 carries it, and GOVERNANCE.md's bump-mechanics
paragraph names it ("this is a convention, not a mechanism"). Today's literal sites
(MEASURED at `a87006e`):

- `scripts/architecture/check_devices.py:23` — `OUT = STANDARDS / "otdp/0.2.0"`
- `scripts/architecture/check_devices.py:412` — `REPORT_TITLE = "# OTDP 0.2.0 specification verification"`
- `tests/contracts/test_architecture.py` — the pin test's report path names
  `standards/otdp/0.2.0/validation-report.md` (the exact line verified during build)

A bump that forgets the moves leaves both pin sides frozen green while the active
version's report is unpinned — the sweep-miss defect class the #97 re-scope says this
closes ("roughly halves what each bump costs and removes a sweep-miss defect class").

## 2. Mechanism

One source of truth: `standards/standards-manifest.json` already declares otdp's active
version (the CON-8 identity check pins manifest↔schema↔identity agreement, so the
manifest is machine-verified, not prose).

- `check_devices.py` loads the manifest (`json.loads` on `standards/standards-manifest.json`),
  reads the otdp entry's version + status, and derives `OUT` and `REPORT_TITLE` from it.
  Refusal on absence/mismatch is loud and prefixed (`otdp_manifest_absent:` /
  `otdp_manifest_version_unreadable:` family), matching the script's existing failure shape.
- The pin test's report path derives from the same manifest read (the test already imports
  from the repo; one shared helper or a direct manifest read — decided at build for
  minimal diff).
- The bump-mechanics sentence in GOVERNANCE.md that names the convention residual is
  updated to state the mechanism now derives the paths (the convention paragraph shrinks
  to the D2-closed form), and #102's D2 bullet closes when this lands.

**Not in this increment (explicit deferrals, per the two-repo discipline):** the SDK-side
literals the #97 re-scope also names under D2 — `packages/sdk/src/benchweave_sdk/__init__.py`'s
`OTDP_VERSION`, the validation tuples, scaffold literals. Those derive from the SDK's
vendored lock, not the gateway manifest; they are a separate SDK-side row (SDK PR +
pointer, own design) and are named here so the re-scope's D2 language is not silently
narrowed.

## 3. Minimal first increment

1. Commit 1 — this design record.
2. Commit 2 — RED: a test that pins the derivation (mutate the manifest's otdp version
   in a tmp copy → the script's derived paths follow; and at `a87006e` the literals are
   hardcoded → the derivation test fails). Watched failing.
3. Commit 3 — GREEN: the derivation in `check_devices.py`, the pin-path derivation, the
   GOVERNANCE sentence update, and the report regenerated IF its bytes change (they must
   not — same active version; the pin proves stability).

## 4. Measurable proof — pre-committed acceptance rule

- RED: the new derivation test fails at the pre-change tree with the literal-vs-derived
  mismatch (not a collection error; `--collect-only` shows the arms).
- GREEN: the derivation test passes; `tests/contracts/test_architecture.py` (the CON-11
  pin) passes UNCHANGED in bytes — the report must not regenerate differently, proving
  the derivation is byte-stable for the same active version; the full standards +
  contracts lanes green; ruff clean; scoped strict mypy on touched files clean.
- Kill-direction: if the pin test requires a report regen to pass, the derivation
  changed the rendered bytes — kill and inspect; a path-derivation must be
  representation-stable.

## 5. Top risks

1. **The manifest read is a new runtime dependency of the script** — the script already
   reads the corpus from `standards/`; reading the manifest adds no new root. Failure
   is loud (prefixed refusal), never a silent fallback to a hardcoded default.
2. **Status fields** (`status: stable` etc.) — the derivation reads the ACTIVE version
   the manifest declares, not "newest dir on disk"; if the manifest ever carries
   multiple-version rows (it does not today — verify at build), the active entry wins.

## 6. DON'T-BUILD check

Not triggered: the mechanism is one manifest read replacing two literals and one test
path; no new architecture, no lockfile, no resolver — everything the #97 re-scope
withdrew stays withdrawn.

## 7. Review corrections (fold wave, appended)

- §2's second refusal name `otdp_manifest_version_unreadable:` never materialized:
  the implementation uses one prefix (`otdp_manifest_absent:`) for both absence
  modes, with disambiguating message text. An unparseable manifest raises
  `json.JSONDecodeError` — loud, but outside the named family; accepted residual,
  not silently claimed (code-review F2/F5).
- The two devices regression-fixture params (schema + derivation-vectors paths)
  were still hardcoded `otdp/0.2.0` — post-bump they would mutate the retained
  version nothing reads, record zero failures, and break hint-free: the exact
  sweep-miss class this increment closes, surviving in the same file. Now derived
  from the same manifest read, with the derivation-vectors byte-pattern obligation
  stated inline (code-review F1). GOVERNANCE's clause reworded to drop the stale
  "by convention" lead-in and scope the claim: OUT/title/pin/fixtures derive; the
  README row remains a conventional move, caught by the pin's exactly-once assert.
- `_active_report_path` now mirrors the script's isinstance/version guard and
  states the first-match residual inline (code-review F3).
- `docs/internal/invariants.md` CON-11's parenthetical literal and
  drift-and-obligations row 13's literal stay (both currently true; both move at
  the next bump per the ordinary obligation — the governor deferred, noted).
