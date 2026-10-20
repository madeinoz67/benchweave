# Issue #459 — the release-train pre-flight gate: design record

Date: 2026-10-20 · Branch: `feat/459-train-preflight-design` (base `origin/main` 2349abd2)
· Issue: madeinoz67/benchweave#459 · Verdict: **BUILD (narrow)** — see §9.

## 0. What this record corrects before it designs

The issue's census row 4 says the docs-literal baseline was "blind to
develop-your-device.md … no gate sees the file", and the remediation commit
`9b879cf8` (2026-10-14) says the file "is absent from
docs-literal-baseline.json". **Both statements are mechanically false at the
commit they describe.** At `9b879cf8^` the baseline records the file with
pins `{"0.1.1": 1, "0.2.0": 8, "0.2.2": 1}` — the file was scanned, its
literals counted, and the gate was GREEN over it, because the tree matched
the snapshot exactly. The miss was not absence; it was that line 7's claim
"Version 0.2.2 is active" was **false** (OTDP 0.2.3 was active) while being
byte-pinned as correct. The OTDP 0.2.3 bump never touched the file, so the
motion ratchet — which refuses only (file, literal) *motion* in either
direction — had nothing to refuse.

This correction is load-bearing: a design that "adds develop-your-device.md
to the baseline" would fix nothing. The unowned surface is **truth, not
motion**: no mechanism derives docs prose version claims from the standards
manifest. That is the one new check this increment builds (§3).

## 1. Root cause, traced

The two-day trains were not days of missing checks. Every surface named in
the issue's census has an owner that existed at train time:

- The `f32a98c` follow-up (mirror left at 0.9.0 against the pinned lock's
  0.11.0) was refused by `benchweave.standards check` — post-push.
- The matrix re-render misses (#456, the s2 branch) were refused by
  `matrix --check` — post-push.
- The develop-your-device miss sailed through green (§0) and was caught by
  the governor's review sweep — a human pass.

The structural cause is timing, not coverage: the #408 order splits one
release into six sequential steps, every owner runs in CI **after** push on
a ~15-minute cycle, and the pre-push aggregate exists only in a maintainer's
head — five commands across two repos that must be known, ordered, and run
by hand before a pointer commit. Red-CI remediation was this discovery loop
executed at CI latency. The increment therefore has exactly two jobs: put
the aggregate in one local command (§4), and close the one truth gap no
owner covers (§3).

## 2. Surface-by-surface ownership table

Read from the mechanisms, not the issue text. "Catches when" is the honest
column: every owner today fires post-push (or at release-cut, or never).

| # | Derived surface (stale pattern) | Owning mechanism today | Runs where | Catches when | Verdict |
|---|---|---|---|---|---|
| 1 | `.gitmodules` `pin` ↔ gitlink | `scripts/check_sdk_submodule_drift.py` (exit 0/1/2, fail-closed) | ci.yml `sdk-drift`, every PR | post-push | OWNED |
| 2 | `sdk_compatibility` mirror ↔ SDK lock block | `standards check` → `sdk_compatibility_drift:` (`src/benchweave/standards/check.py:451-459`) | `gates` via `make check-sdk-standards`; `package` | post-push | OWNED |
| 3 | lock `compatibility.sdk` ↔ pyproject@pin | `standards check` anchor (`check.py` `_compare_anchor`; `sdk_version_unanchored:`) | `gates` | post-push | OWNED |
| 4 | main standards ↔ SDK lock ↔ vendored tree | `make check-sdk-standards` (re-export compare; `Makefile:34-37`) | `gates`, `package` | post-push | OWNED |
| 5 | `docs/compatibility-matrix.md` re-render | `standards matrix --check` (committed-state render, CON-12) | `gates` (`Makefile:36`) | post-push | OWNED |
| 6 | served set / dependency-policy mirror | `served_set_drift:` (`check.py:278-322`), `policy_mirror_drift:` (`check.py:364`) | `gates` | post-push | OWNED |
| 7 | plugin contract locks | `plugin_lock_drift:` (`check.py:140-144`) | `gates` | post-push | OWNED |
| 8 | executable version literals, five scopes | `scripts/standards/count_version_literals.py` zero-mode (all scopes; register + value pins) | `gates` (pytest `test_zero_literal_gate`), `device-plugins` (`--scope plugins,docs`), `check-sdk-standards` (sdk) | post-push | OWNED |
| 9 | docs prose literal **motion** (growth/shrinkage/new file) | counter docs scope: exact-content snapshot + in-gate file census (`_check_docs_ratchet`) | `device-plugins`, `gates` | post-push | OWNED (motion only) |
| 10 | docs prose version-claim **truth** vs the manifest (the five baseline sites; "X is active / remains served") | **nothing** — §0's proof: a green pin over a false claim | — | never | **UNOWNED** |
| 11 | website stamps (3-component literals, token substitution) | `tests/contract/test_website_stamps.py` + assembly `verify_tree` (CON-13) | `gates` pytest; `docs.yml` | post-push | OWNED |
| 12 | `docs/README.md` validation-report rows | family pin tests (CON-11) | `gates` | post-push | OWNED |
| 13 | adapter identity touch-set | agreement test + check derivations (CON-8/REG-4) | `gates` | post-push | OWNED |
| 14 | SDK README/hero/tagline/lock anchor | `scripts/release_cut.py` `DECLARED_SURFACES` + `validate_occurrences` + `cmd_verify` (SDK repo) | release-cut time | at cut (discipline-gated) | OWNED |
| 15 | SDK website/README/guide prose literals | SDK twin prose scope (benchweave-sdk#182, merged 2026-10-19: count pins, file census, great-docs-derived index expectation) | SDK repo CI | post-push | OWNED (counts; value drift is the SDK's own V1 deferral) |
| 16 | SDK scaffold fixtures (T1/T2) | release-cut regen step + byte-parity suite | SDK CI | post-push | OWNED |
| 17 | `great-docs.yml` registration ordering | phase-2 staged patch + `--verify` apply/recompute checks | at cut | release-cut | OWNED |
| 18 | **merge-result coherence** (base and head each green; the merge stale) | nothing pre-merge — `gates` runs on `push: main` and reds **after** the merge | — | post-merge, red on main | **UNOWNED** (process; deferred, D1) |
| 19 | **pre-push aggregate** (one command before a pointer commit) | nothing — five commands across two repos, hand-ordered | — | never | **UNOWNED** (this increment, §4) |

Headline: **16 of 19 rows are owned by existing mechanisms; 3 are not.**
Of the three: row 10 is a missing *check* (new logic, §3); row 19 is missing
*orchestration* (no new logic, §4); row 18 is a process gap whose remedy is
the issue's own recommendation 2, not a script — deferred with a reopen
trigger (D1). The owner's comment governs scope: "The new script must use
the checks that exist. It must not add a second copy of them." — rows 1-9,
11-17 are delegated, never re-implemented.

## 3. The new check: the docs claim register

**Mechanism.** `scripts/standards/train_preflight.py` carries a `CLAIMS`
register — the DECLARED_SURFACES shape (`scripts/release_cut.py:60-116`, the
proven in-tree precedent for "a declared surface with an anchored pattern
and an expected value") pointed at docs prose instead of release stamps. A
row is `(file, anchor regex with one capture, standard id, kind)` where
`kind ∈ {active, served}`. The checker reads the file, finds the anchor,
extracts the literal, and derives the expectation:

- `active` → the standards manifest's active version for that id. Read the
  same way the counter already reads it (`_pin_standard_ids`: plain
  `json.loads` of `standards/standards-manifest.json` — stdlib-only, the
  counter's own deployment posture, since `device-plugins` runs it before
  `uv sync`).
- `served` → the captured literal names a version carried by the
  dependency-policy block's retained set for that id (same manifest file).

Refusals, named, in the house prefix style:
`docs_claim_stale: docs/develop-your-device.md:7 claims otdp 0.2.2 active,
standards-manifest.json says 0.2.3 — sweep the claim in-arc` and
`docs_claim_anchor_lost: <file> — the anchor moved; re-anchor the register
row (a moved claim site is a reviewable edit, never a silent pass)` — the
counter register's anti-laundering shape: a new or moved claim site fails
until the row is edited, visibly.

**The 18 founding rows** (each site verified at HEAD):

- `docs/device-developer-guide.md:13` — `**Baseline:**` sentence: OTDP,
  registry, execution, interface (4 rows).
- `docs/ai-device-reviewer.md:64` — "The current project baseline is …"
  sentence: same four (4 rows).
- `docs/development.md:182` — "`docs/` retains …" sentence: same four
  (4 rows).
- `docs/smart-test-gateway-architecture-v1.5.md:331` — "STG 1.5
  consolidates …" sentence: same four (4 rows).
- `docs/develop-your-device.md:7` — `Version X is active` (1 row, active)
  and `version Y remains served` (1 row, served) (2 rows).

Adapter-API ("1.1") and architecture ("1.5") claims are two-component and
outside this increment (D2 carries widening). Anchors key on the minimal
stable tokens (`Baseline:**`, `is active`, `remains served`), not whole
sentences, so ASD-STE100 rewrites that preserve the claim tokens do not
break rows.

**What it delegates.** Everything else. The register adds the only checking
logic in this increment; it does not touch the counter, the snapshot, or
any CI lane's existing behavior.

## 4. The orchestrator: one local command

`scripts/standards/train_preflight.py` runs, in one process, in this order,
each a subprocess of the existing command (stdlib `subprocess`, exit codes
and refusal prefixes surfaced verbatim):

| Step | Delegated command | Surface named on refusal |
|---|---|---|
| 1 | `python3 scripts/check_sdk_submodule_drift.py` | packages/sdk pointer pin ↔ gitlink |
| 2 | `uv run python -m benchweave.standards check` | mirror (`sdk_compatibility_drift:`), anchor (`sdk_version_unanchored:`), served set, policy mirror, plugin locks |
| 3 | `uv run python -m benchweave.standards matrix --check` | compatibility-matrix render |
| 4 | `uv run python scripts/standards/count_version_literals.py --scope gateway,plugins,docs,scripts` (+ `sdk` when the submodule tree is present; an absent requested tree is reported as the counter names it, `sdk_tree_absent:` — never a crash) | version literals, per scope |
| 5 | the claim register, in-process (§3) | docs version claims, per file |

Output: one row per surface, `[ok]`/`[UNMOVED]`, the owning refusal line
indented under any failure, and a summary line
`train-preflight: N surfaces checked, M unmoved`. Exit 0 only when every
surface is ok. `--claims-only` runs step 5 alone (the CI arm);
`--root <dir>` redirects the tree root (the test arm). The script is
stdlib-only apart from the two `uv run` delegations, which need the project
environment — the same requirement `make check-sdk-standards` already makes,
and the preflight requires an initialized submodule for steps 2-4 exactly as
`gates` does (check.py already refuses by name when it is not).

**Where it runs.**

- **Locally, before any pointer commit and before pushing any
  standards-touching branch** — the maintainer command:
  `UV_PROJECT_ENVIRONMENT=venv uv run python scripts/standards/train_preflight.py`
  (the Makefile convention). Runtime: seconds; every delegated check is
  offline, committed-state-pure (CON-12's own clause).
- **In CI: the claim check rides `gates` via a new pytest module**
  (`tests/standards/test_docs_claims.py`), which subprocesses
  `train_preflight.py --claims-only` over the real tree and asserts exit 0 —
  the `test_zero_literal_gate` precedent exactly. **No new workflow lane.**
  The issue's "runs in CI on every standards-touching PR" is already
  structurally true for rows 1-9 and 11-13 (every PR runs `gates`,
  `device-plugins`, `sdk-drift`); duplicating them inside a preflight lane
  would be a second source of timing, not truth. The increment adds the one
  missing check to the existing per-PR lanes and keeps orchestration local.
- The full preflight is NOT a CI job. Its delegated halves are the CI jobs.

## 5. Proof: pre-committed acceptance rule

Written before any output was looked at. This is a deterministic gate, not
a statistical measurement — the sample is the arm set below, one plant per
class, run once on the landing branch.

**Metric:** exit code of `scripts/standards/train_preflight.py` (and
`--claims-only` where the arm says so) over each planted state; the surface
name must appear in the output of every RED arm.

**Arms — every arm must hold; any failing arm means the slice does not ship
as designed:**

- **A1 — claim RED, the differential control (the class nothing owns).**
  Replant the `9b879cf8` miss exactly: set the "is active" literal on
  `docs/develop-your-device.md:7` back one OTDP version, then run
  `count_version_literals.py --refresh-docs-baseline` (blessing the ratchet,
  as a train legitimately would). Expected: the counter's docs scope alone
  exits **0** (proving the miss class invisible to every existing gate),
  while `train_preflight.py --claims-only` exits **non-zero** naming
  `docs/develop-your-device.md` and the manifest's active version. Revert;
  both exit 0.
- **A2 — claim GREEN / the simulated complete bump.** Clean tree at the
  slice's merge-base — a landed, coherent train tip (the interface-0.1.1
  pairing era) — `--claims-only` exits 0, all 18 rows verified. A clean-tree
  red here means the register rows were mis-derived: the slice fails; rows
  are not tuned after looking at output.
- **A3 — mirror RED.** Plant the `f32a98c` shape: edit
  `standards/standards-manifest.json` `sdk_compatibility.sdk` to an adjacent
  version. Full preflight exits non-zero naming the mirror surface
  (a `sdk_compatibility_drift:`/anchor line indented). Revert → 0.
- **A4 — matrix RED.** Append one byte inside a rendered row of
  `docs/compatibility-matrix.md`. Preflight non-zero naming the matrix
  (via `matrix --check`). Revert → 0.
- **A5 — pointer RED.** Edit `.gitmodules` `pin` to a different tag.
  Preflight non-zero naming the pointer (drift script exit 1 or 2). Revert → 0.
- **A6 — literal RED.** Plant `X = "9.9.9"` in an ungated `src/benchweave/`
  file. Preflight non-zero naming the gateway literal scope. Revert → 0.

**Kill directions.** If A1's counter-alone half is RED (an existing gate
already catches the blessed stale claim), the claim register is redundant:
record the honest negative, cut §3, ship §4 only. If any planted miss in
A1-A6 shows exit 0 from the preflight, the gate does not own its class —
the slice fails. If A2 is non-zero, the row set is wrong — the slice fails.

**Underpowered clause.** An arm whose plant is refused by an *unrelated*
check (conflated refusals) is INCONCLUSIVE, not passed: re-plant isolating
the one surface; if a surface cannot be isolated, that class is recorded
unproven and its register rows / delegation row are cut from the slice
before merge rather than shipped unproven.

## 6. Minimal scope and deferrals

In scope: `scripts/standards/train_preflight.py` (register + orchestration),
`tests/standards/test_docs_claims.py` (the A1/A2 arms as permanent pins),
the scripts-census pin bump in `tests/standards/test_zero_literal_gate.py:891`
(19 → 20 — the counter's own discipline makes the denominator move a
same-commit visible diff), the `drift-and-obligations.md` row (18(m) gains
its mechanical half; CI map note), and the
`docs/internal/release-process-family.md` row (obligation 28: release
machinery moves its family doc). No `standards/` bytes, no submodule
pointer, no SDK-repo changes.

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | merge-result coherence (row 18) and recommendation 2's coordinated landing | follow-on work under issue #459 (recommendation 2 stays open) | the next gateway standards train whose merge commit renders a matrix disagreeing with both parents' renders — the observed class — or the owner's explicit call to adopt a merge queue |
| D2 | widening the claim register past the 18 anchored rows (every docs literal derived; adapter-API and architecture two-component claims) | documentation here | a governor or review finding of a stale version claim at a docs site with no register row |
| D3 | SDK-side prose value drift (the twin's count-only pins) | the SDK repo's own #182 deferral V1 (noted here, owned there) | the next SDK release-review walk that corrects a badge or stamp by hand — the v0.16.0 `5-corr` class recurring |
| D4 | the windows evidence baseline | issue #457 | that issue's own work starting |

## 7. Invariant and drift impacts

- No CTL/STO/CON/REG invariant changes or amendments. CON-12/CON-13 are
  consumed as-is (the orchestrator invokes their mechanisms; it adds no
  render or stamp logic).
- `docs/internal/drift-and-obligations.md`: row 18(m) gains its mechanical
  half (the register is the tripwire the in-arc sweep was missing); the CI
  map's `gates` row gains the claim-check clause.
- `docs/internal/release-process-family.md` moves (obligation 28) — the
  preflight is release machinery.
- No on-disk format or schema is introduced or changed (the register is
  in-script data; the docs snapshot is untouched). Per the review rubric
  this keeps the slice OUT of the persisted-format Tier-3 path rule; the
  tier below comes from the keyword rule instead.
- Surfaces that must NOT move and do not: MCP tools, REST/openapi, CLI,
  operator docs (the preflight is maintainer tooling, not operator-facing),
  vendored standards, fixture lattice, the SDK repo.
- CI cost: one pytest module in `gates` (seconds, offline). No new lanes,
  no workflow edits.

## 8. Review tier and the Step-1 keyword scan (#254)

**Tier 3**, by the keyword rule: the expected diff text contains
`subprocess` — in this record at §4 (the delegation layer) and §10
(lineage), and again in the expected code text of `train_preflight.py`
itself (the import plus the delegation calls) and the test module's
invocation arms; every occurrence is the orchestration mechanism, not
concurrency. The other seven keywords over the whole expected diff (docs
and code alike — the five files of §6 plus this record) appear ONLY inside
this scan statement itself (§8's own lines naming them — the rubric's
intended self-fire; text that mentions the keywords still takes the deep
lane). Counts outside §8 in this record, verified by scan before commit:
`threading` 0, `asyncio` 0, `sha256` 0, `hashlib` 0, `migrate` 0,
`recovery` 0, `protection` 0. Path rules alone would say Tier 2
(`scripts/`, `tests/`, internal docs only); the keyword rule buys the deep
lane and this record states it at design time per #254 — the review
re-derives both independently. The standards-governor mandate also fires:
the diff carries standard-version strings (register rows, test plants), so
the governor pass is required regardless of tier.

## 9. Top risks and verdict

**Risks, each with its falsifier:**

1. **Anchor fragility** — a prose rewrite moves a claim sentence; the row
   reds with `docs_claim_anchor_lost:` and demands a re-anchor (a visible
   editorial diff, the counter register's own shape — not a silent pass).
   Falsifier: the five sites' edit history — every motion in the last month
   was a version bump riding an in-arc sweep, which will now also re-derive
   cleanly; if a purely stylistic edit ever breaks an anchor, keying on
   claim tokens was the wrong row shape.
2. **The refresh-blessing path stays open off-register** — a NEW file with
   wrong values plus a refresh still passes; the register only verifies
   declared sites. The closing clause mirrors obligation 18's: a new claim
   site gets a row or is a defect (D2's trigger is the tripwire).
3. **Environment sensitivity** — steps 2-4 need the project env and an
   initialized submodule; preflight names the state (the counter's
   `sdk_tree_absent:` and check.py's submodule-state refusals) rather than
   crashing. A deinitialized worktree is out of preflight's scope the same
   way it is out of `gates`'.
4. **Claim-gate reds reach every PR, not just trains** — intended: a stale
   claim is stale regardless of which PR reveals it; this converts
   obligation 18(m)'s review-carried sweep into a machine gate, which is
   the issue's stated purpose.

**Verdict: BUILD (narrow).** Strongest single reason: the ownership table
shows exactly one unowned *check* — row 10, where a green, correctly-pinned
baseline sat over a false "is active" claim for a full train cycle and only
a human review caught it — and the increment closes precisely that gap plus
the pre-push aggregation (row 19) while delegating all 16 owned surfaces
unchanged. A DON'T-BUILD verdict would have been right had the table shown
every surface owned and the defect purely review discipline; it does not:
row 10's miss was structurally invisible to every existing gate, proven by
the A1 differential control.

## 10. Lineage

- Issue #459 (filed 2026-10-14, owner comment 2026-10-14: recommendation 1
  scope, use existing checks, surface-by-surface ownership).
- The `9b879cf8` governor finding (corrected mechanism, §0) and the
  benchweave-sdk #182 F5 correction (the v0.16.0 badge walk: four of seven
  stale under a "walk confirms" record — the review-discipline failure
  class this gate retires, in our own audit record).
- Precedents extended: `release_cut.py` DECLARED_SURFACES (declared
  surface, anchored pattern, expected value); the counter's
  `_pin_standard_ids` (stdlib manifest read, derivation from committed
  authority); `test_zero_literal_gate`'s subprocess-over-the-real-tree
  pytest shape.
