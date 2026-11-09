# Design: #606 second attempt — close the mint's arbitrary-state door (candidate B)

- **Issue:** gateway #606, refute-lane HIGH-1 (first attempt's design record §11 is the
  correction of record for what the first fix left open)
- **Tree read and verified:** branch `fix/606-dataset-id-mint` at `ce4a4b44`
  (= `origin/main` `5f4256c1` + the first fix `656114f8` + the capture-idiom commit
  `a2be59f9` + the §11 addendum)
- **Tier (#254):** Tier 3 by dispatch — identity on the admission path. The code diff's
  Step-1 path rules fire none (no `contracts/`, `standards/`, persisted-format,
  `registry/`, fixture-lattice, dependency, or submodule motion), and the diff text
  carries zero Step-1 keyword hits; the tier is taken by dispatch, review re-derives.

## 1. The two candidates, and the pick

The refute lane's HIGH-1 exploit needs one thing beyond the context rewrite: controller
state under an operation id the host never dispatched. Verified at source — `_operations`
has exactly two writers: `mint_dataset_id` (host-only; its single `src/` caller is the
bridge's I6 gate) and `mint_payload_id`'s out-of-dispatch fallback, which CREATES state
under any operation id a member call names. The fallback's justification comment
("host-side routing in publish") has no live `src/` caller; its only dependents are the
exploit and one unit test.

- **Candidate A — dispatch-scoped binding** (the SDK's `_SURFACE` shape: a host-set
  scope around the adapter call; `admit` reads identity from it and stops reading the
  context). Removes the operation id from identity entirely. Costs: one new mechanism
  (no `ContextVar` exists anywhere in this tree's `src/` — verified), a publish outside
  any host dispatch refuses, and a seam through every direct publish/payload call in
  the unit harness (~30 call sites) plus the fixture lattice that follows.
- **Candidate B — close the arbitrary-state door**: `mint_payload_id` refuses when no
  mint exists for the operation (the fallback is removed). A rewritten `operation_id`
  then yields `dispatch_state(...) is None` and the EXISTING no-mint refusal — the one
  `656114f8` already reworded for exactly this firing condition — does the work.

**Pick: B.** Evidence:

1. **B completes the in-tree mechanism.** The first fix already reads the mint record
   and refuses on its absence; the exploit survived only because a member could append
   to the mint domain at runtime. B makes the domain append-only-by-host and the
   existing refusal becomes the operative guard — no new machinery (CLAUDE.md
   principle 9).
2. **Measured blast radius.** B's behavior change (payload staging outside a
   host-dispatched operation refuses) breaks exactly one test's fixtures
   (`test_controller_abort_open_and_sweep_reclaim`, `op-x`/`op-y` — minted in the
   update). A's seam would touch every direct call in the unit harness.
3. **B is necessary in both candidate worlds.** Arbitrary member-created controller
   state is wrong independent of the identity design; A-without-B leaves it standing.
   B-first is the intersection; A composes on top if ever taken.

## 2. What B does NOT close (stated, not hidden)

The adapter still SELECTS among the run's host-minted operation ids: during operation
X's execute it may publish under a PAST, minted-but-unadmitted operation P of the same
run by naming P on the context. Bounded by M10 correlation only when P's action
declares `configuration_id`/`acquisition_id` (an action declaring neither — the
permissive-output class — has no structural bound), and by M11 for artifact-backed
variables (inline-value manifests reference nothing). This is misattribution WITHIN the
run's host-authored id set — id selection, not id introduction: no id the host did not
mint can ever be filed under. CTL-13's "the adapter cannot choose its dataset id"
becomes true in the introduction sense and remains non-structural in the selection
sense. **Candidate A is the named completion for the selection residual** — not taken
here, with its cost stated (§1); take it when the within-run misattribution is judged
to cross a line. The exploit actually demonstrated (#606's HIGH-1 and its D1/D2
front-door) is closed by B: both required state under a name the host never dispatched.

## 3. Why capture-before is not needed in this tree (the SDK question)

The SDK's inline path was clean because the id is captured before the adapter runs.
This tree already has that capture: the host mints and records the dataset id at the
I6 gate BEFORE `execute` runs, and the first fix made admission read the record. The
exploit worked not because identity read an adapter-supplied value (closed by
`656114f8`) but because a member could MANUFACTURE a new record at runtime. B makes the
record's key set exactly the host-dispatched operations — the same guarantee
capture-before buys, arrived at through the record's authorship rather than a scope.
What capture-before would still add beyond B is pinning WHICH captured id a given
publish speaks for; that is §2's selection residual, named above.

## 4. The mechanism (the whole production diff)

`mint_payload_id` (`src/benchweave/content/dataset_services.py`): the fallback branch
is replaced by a refusal — staging requires a host-minted operation; an operation the
host never dispatched refuses, no state is created. `admit`'s own routing call
(`mint_payload_id` at the admission tail) is unaffected: identity has already passed,
so the operation's state exists. Docstrings updated in the same commit
(`mint_payload_id`'s contract; the class-level ordering prose already names the
no-mint refusal).

Adapter-visible behavior: `payload_create` under an unminted operation now refuses
with `DatasetServiceRejected`. No ruled flow regresses — payload staging lives inside
invoke dispatches (upload actions are invoke actions); the guide never instructs
out-of-dispatch staging (obligation 3 walked, zero motion, disclosed).

## 5. Arms (RED-first)

1. **ARM-2c** (`test_gw1_arm2c_operation_rewrite_poisons`, written beside ARM-2b in
   `tests/unit/test_otdp_bridge.py` at the refute lane's direction): the adapter
   rewrites `context.operation_id = "attacker"`, calls `payload_create` (the fallback's
   door), returns a manifest carrying `ds:attacker`; asserts UNKNOWN +
   `admitted_by_dataset_id("ds:attacker") is None`. RED on `ce4a4b44` (quoted in the
   commit message).
2. **The door's own pin** (`test_payload_create_outside_a_minted_operation_refuses`,
   `tests/unit/test_dataset_services.py`): `payload_create` under an unminted
   operation refuses `DatasetServiceRejected` AND `dispatch_state` stays `None` — no
   state created. RED pre-fix (today it silently creates state and returns an id).
3. **Fixture update (one test):** `test_controller_abort_open_and_sweep_reclaim` mints
   `op-x`/`op-y` — the only fallback-dependent test (surveyed: every other payload op
   in the suite runs under a minted operation).
4. **Unchanged and must stay green without edits:** everything from the first
   attempt's §5.5 set (ARM-1..ARM-8 + 2b, I6, one-core, R2/R2b, R8, W2, quota,
   read-allowlist, publishing-adapter OK), the R15 prior-operation M11 arm, and the
   capture-evidence policy pair.

## 6. Pre-committed acceptance rule

- **Metric:** binary, over the enumerated set: {ARM-2c, the door's pin} RED on
  `ce4a4b44` and GREEN after; the §5.4 pin set green with no edits beyond the one
  named fixture update; one cold full battery at the slice head, counts from
  `--junitxml` attributes or exit codes.
- **Ship if:** ARM-2c's pre-fix failure is the HIGH-1 signature (OK + honored
  rewrite), post-fix UNKNOWN with nothing admitted under the forged id; battery,
  ruff, fresh-cache bare mypy green; win_core manifest refreshed through the script's
  own `--refresh` (two totals move — one new test per file), nothing else.
- **Kill (fix wrong):** a §5.4 pin fails for a reason the one fixture update does not
  honestly cover — a ruled behavior narrowed; stop and report, do not patch the test.
- **Kill (hole unreachable):** ARM-2c pre-fix passes — already disproven by the refute
  lane and re-run by the build lane; listed for completeness.
- **Underpowered:** a RED run with zero collected / exit 5, or counts read from a
  filtered summary line — void evidence; re-run before any decision.

## 7. Obligations and drift

1/2 no (no MCP tool, no API surface — the new refusal rides the existing
`DatasetServiceRejected` channel). 3 satisfied with zero motion (§4's disclosure). 8
no (adapter protocol shape unchanged — same members, one refusal condition narrowed).
5/6/7 no (fixture lattice here means `fixtures/registry/` — untouched; no vendored
bytes; no submodule motion; the win_core count registry moves through its own
`--refresh` path and is disclosed). 23 no. No corpus/standards motion; no SDK pointer
motion — the SDK's member-path half of #606 stays open on the issue (`Refs`, not
`Closes`). CTL-13's amendment is already bounded by record §11 (value, not key); B
makes the key set host-authored, and the selection residual stays named in §2 until
A, if ever.

## 8. Deferrals, named

- Candidate A (dispatch-scoped binding) — the selection residual's structural
  completion; composable on top of B; not taken (cost in §1).
- The `operation_id`-rewrite's member-path surface beyond admission (M10/M11's own
  keying) — bounded analysis in §2; moves with A if A is ever taken.
- The SDK standalone host's explicit member path — the open half of #606; same
  two-candidate analysis applies there, and its inline path already demonstrates the
  capture-before principle.
- Cross-principal dataset authorization — the standing deferral, untouched.
