# Issue #187 class closure — the `compatibility.sdk` ground-truth anchor

Design record for the class-closure increment of gateway issue #187 (RCA comment
5808047218, fix-path item 3). Date 2026-09-24. Status: designed, not built.

**Verdict: BUILD.** The anchor's truth source — the pinned SDK commit's own
`pyproject.toml` — is reachable at check time through exactly the mechanism the
mirror lane already trusts (the submodule working tree, proven to BE the gitlink
pin by `_submodule_state_failures`). The premise was verified against the live
tree, not assumed; see §2.

This record is committed before any implementation runs, so the acceptance rule
in §8 is provably pre-committed.

---

## 1. Root cause (established, not assumed)

`compatibility.sdk` had **no writer contract enforced against ground truth**:

- Write side: the SDK's sync writer stamps the field from the SDK's own
  pyproject — `standards_sync.py::_write_vendored` builds
  `lock["compatibility"]["sdk"] = _sdk_version(sdk_root)`
  (`packages/sdk/src/benchweave_sdk/standards_sync.py:565-664`, `_sdk_version`
  at :667-676). A lock regenerated at sync time always carries the then-current
  SDK version.
- Check side: `run_check` compared only committed artifacts against each other —
  `_compare_lock` (manifest ↔ lock rows), `_compare_tree` (vendored bytes ↔
  export), `_compare_mirror` (manifest `sdk_compatibility` mirror ↔ lock
  `compatibility` block) — `src/benchweave/standards/check.py:37-53`. Nothing
  anywhere compared either side to the pinned SDK's actual version.

So when the SDK package bumped to 0.2.0 and the lock was **not** regenerated,
lock and mirror staled *together*: `sdk_compatibility_drift` stays green because
both sides say 0.1.0, `_compare_lock` stays green because no standards row
moved, and CI was green over a broken pairing. The instance was closed by PR
#189 (merge `4d7f6bc`: lock regenerated to 0.2.0 at pin `fc7f05c`, mirror +
rendered matrix moved with the pointer). The **class** — "a derived pairing
with no anchor to its producer" — is what this increment closes.

Why the wrong belief persisted: the SDK repo's own release-review record still
carries the pre-fork-(a) rationale — `packages/sdk/docs/internal/release-review-matrix.md:82`:
"`standards-lock.json` `compatibility.sdk` stays 0.1.0 = sync provenance,
untouched by a package-version bump." Fork (a) of the #187 RCA ruled the
opposite (`sdk` = the version this lock state is certified for) and PR #189
implemented it; this prose was never corrected. It is the recorded decision the
defect grew from. Disposition: deferral D1 (§7) — it is SDK-repo bytes.

Fork (a) is the governing decision; this design implements it, it does not
re-open it. No A01–A14 decision is re-proposed (the mirror/lock surfaces postdate
the decision record; `docs/smart-test-gateway-decisions.md` has no
`sdk_compatibility` content — verified by corpus-wide text search, 2026-09-24).

## 2. Truth-source reachability (the DON'T-BUILD question, answered)

The anchor must read the pinned commit's pyproject at check time. Three
postures, all verified today:

| Posture | Pyproject reachable? | Behavior |
|---|---|---|
| CI (`gates`, `package` jobs; submodules recursive) | Yes — working tree initialized at the gitlink | Anchor runs and decides |
| Local, submodule initialized at the pin | Yes | Anchor runs and decides |
| Local, submodule deinitialized (standing posture) | No — but `run_check` is **already red** here through existing lanes | Anchor never reached; the state refusal fires (see §6) |

Verified live state (2026-09-24): main at `37d62e7`, gitlink
`fc7f05c44947af86186c32f04f840fe3087d2a21` = standalone SDK checkout HEAD
(`fc7f05c fix(standards): regenerate compatibility.sdk = 0.2.0`); the pinned
commit's `pyproject.toml` says `version = "0.2.0"`; the lock's
`compatibility.sdk` says `"0.2.0"`. The current tree is a **true pairing** —
the anchor greens on it. An anchor that reds the healthy tree would falsify
the premise (kill direction, §8).

## 3. Piece 1 — the anchor in `benchweave.standards check`

**Mechanism.** One new comparison function in
`src/benchweave/standards/check.py`, wired into `run_check` behind the
existing submodule-state gate:

```python
def _pinned_sdk_package_version(sdk: Path) -> str | None:
    """The SDK's own version in the working tree (= the pin, per the state gate).

    None when pyproject is absent or malformed — the caller refuses. The
    check-side dual of the SDK's _sdk_version (standards_sync.py:667): the
    writer degrades to "unknown" because it must write something; the checker
    degrades loudly because green must mean verified. A format change there
    must be mirrored here.
    """
    pyproject = sdk / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with pyproject.open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except (tomllib.TOMLDecodeError, KeyError):
        return None


def _compare_anchor(sdk: Path, lock: dict[str, Any], state: list[str]) -> list[str]:
    """compatibility.sdk must equal the pinned SDK's own pyproject version.

    The lock's ``sdk`` field is the writer contract (the SDK sync stamps its
    own version into it, issue #187 fork (a): the version this lock state is
    certified for). The state gate proved the working tree IS the gitlink pin,
    so the pyproject read here is the pinned commit's. Both sides staling
    together — mirror equal, lock stale — is exactly the state this refuses.
    Degrades loudly: unreadable pyproject or undeclared lock field is a
    failure, never a skip and never a degraded "unknown" comparison.
    """
```

Body: if `state` is non-empty return `[]` (the refusal already fired — the
anchor adds no line, §6); if the lock's `compatibility.sdk` is absent, null,
empty, or non-string → one failure line; if `_pinned_sdk_package_version` is
`None` → one failure line; if the two disagree → one failure line naming both
versions with the remediation (`make sync-sdk-standards`, land lock + mirror +
pointer together). Failure prefix: **`sdk_version_unanchored:`** — a new
family, deliberately NOT `sdk_compatibility_drift:`, because the two failures
have different meanings and different fixes (drift = "update the manifest
mirror"; unanchored = "regenerate the SDK lock").

**Gate wiring.** `run_check` computes the submodule state once and shares it:

```python
    state = _submodule_state_failures(root, sdk)
    failures.extend(state)
    failures.extend(_compare_mirror(root, sdk, lock, state))
    failures.extend(_compare_anchor(sdk, lock, state))
```

`_compare_mirror` drops its internal `_submodule_state_failures` call and
takes `state` as a parameter (`if state: return []`). Emitted lines are
byte-identical to today's for every existing posture — the moved-submodule
test that pins `len(failures) == 1` stays green. Private-helper signature
change only; no test calls `_compare_mirror` directly (verified:
`tests/standards/test_check.py` exercises `run_check`, `version_lines`,
`_pinned_sdk_sha` only).

**Contract edges, each pinned by its own test:**

- Lock `compatibility.sdk` undeclared (null/absent/empty/non-string) → refuse.
  The mirror side already requires a non-empty `sdk` string
  (`manifest.py::load_sdk_compatibility`, fields `sdk`/`main_project`), so an
  undeclared lock field is precisely the original defect shape.
- Pyproject at the pin absent or malformed → refuse by name. Never compare a
  degraded `"unknown"` (that is the writer's default for generated roots; a
  check that compared it would launder it).
- `sdk` = `"unknown"` in the lock against a readable pyproject → mismatch,
  refuse (the string comparison handles it; no special case).

**What does not change:** `matrix.py` (the render stays a pure function of
committed state — it never reads the SDK's pyproject; CON-12's render clause is
untouched); `version_lines`; the CLI's exit contract; the lock's schema.

## 4. Piece 2 — the guard tests (the repair is never refused again)

All in `tests/standards/test_check.py`. One fixture change: `_sdk_copy` gains
`shutil.copy2(source / "pyproject.toml", sdk / "pyproject.toml")` — it already
copies lock + vendored tree; the pyproject is the third input `run_check`
reads. The scenario fixtures need nothing:
`tests/standards/test_scenarios.py::_synced_sdk` **already** writes a pyproject
carrying the mirrored version into every synthetic SDK root (lines 62-77,
comment: "The throwaway root must carry the mirrored version, not 'unknown'"),
and the sync stamps lock = pyproject = mirror, so all scenario tests are
three-way-equal and stay green.

1. **The #187 replay (the RED).** `_sdk_copy` + `_standards_root`; set
   lock `compatibility.sdk = "0.1.1"` AND the manifest mirror's `sdk` to
   `"0.1.1"` (so CON-12's mirror lane is green — both sides staled together,
   the historical state); pyproject untouched at 0.2.0. Pre-increment:
   `run_check(...) == []` — demonstrated and recorded before implementation.
   Post-increment: exactly one `sdk_version_unanchored:` line naming 0.2.0 and
   0.1.1, and `sdk_compatibility_drift` NOT among the prefixes (the replay
   isolates the anchor: no existing lane catches this state).
2. **The green control (post-bump sync stays green).** lock `sdk` = mirror
   `sdk` = pyproject version → `run_check == []`. Pins that the anchor does
   not refuse a correct regenerated pairing — the false-positive guard for
   the #189 repair shape. `test_real_tree_is_clean` carries the same proof
   against the live tree in CI.
3. **Unreadable pinned pyproject.** Delete the copied pyproject →
   `sdk_version_unanchored` refusing by name ("cannot read"), never a pass.
4. **Undeclared lock sdk.** lock `compatibility.sdk = None` → anchor refuses
   (the mirror lane also drifts — both red is honest).
5. **State-gate inheritance.** On `_repo_with_uninitialized_submodule` and the
   moved-submodule fixture: no `sdk_version_unanchored` line, the single state
   refusal unchanged (extends the two existing posture tests).

RED protocol: tests 1, 3, 4 land first and are shown failing on pre-increment
code (`run_check == []` / missing prefix); the anchor implementation is the
GREEN commit. One RED→GREEN slice.

## 5. Piece 3 — the obligation/checklist wiring

The mechanical halves above catch the broken pairing **at the main-repo PR that
advances the pointer** (CI initializes the submodule at the new pin; pyproject
there says the new version; a stale lock reds `sdk_version_unanchored` before
merge). The checklist row covers what CI cannot see — the SDK PR ordering and
the push-before-pointer rule:

- **`docs/internal/drift-and-obligations.md`, obligation 7 (the `packages/sdk`
  pointer row)** gains the pairing clause: a pointer advance that moves the
  SDK's own version pairs the regenerated SDK lock, the moved
  `sdk_compatibility` mirror, and the re-rendered `docs/compatibility-matrix.md`
  in the same landing — the PR #189 shape (`4d7f6bc`: matrix + pointer +
  manifest + test in one merge) and the PR #154 shape (`18009ce`, closing
  issue #153: pointer + in-tree dependents together) — with
  `make check-sdk-standards` (now carrying the anchor) as the mechanical half.
- **Obligation 6** names the new refusal in its existing mirror sentence:
  `sdk_compatibility_drift` (mirror ↔ lock) and `sdk_version_unanchored`
  (lock ↔ pinned pyproject).
- **`docs/internal/invariants.md`, CON-12** — appended amendment (this file
  appends, never rewrites): *Amendment (2026-09-24, issue #187 class closure):
  the lock's `compatibility.sdk` is itself anchored — it must equal the pinned
  SDK's own `pyproject.toml` version, read through the working tree the state
  gate proved is the pin, refused by name when the pyproject is unreadable or
  the field undeclared (`sdk_version_unanchored`); the render's purity clause
  is unchanged — `render_matrix` still never reads the SDK's pyproject. The
  authority chain is pyproject@pin → lock → mirror.* CON-4's 2026-09-23
  amendment sentence ("the mirror is a derived copy whose authority stays with
  the lock") remains true and needs no edit.
- **`standards/GOVERNANCE.md`, identity paragraph** — one sentence: the lock's
  `sdk` field names the pinned SDK's own version (fork (a)); `benchweave.standards
  check` anchors it to the pinned pyproject. GOVERNANCE.md is not
  digest-pinned (zero corpus-manifest references — verified), so this moves no
  rows and needs no repin; the standards-governor lane applies to the touch.

## 6. The deinitialized-submodule ruling

**Refuse everywhere; no skip path exists or is added.**

- The check's module contract is "an empty failure list is the only clean
  state" — a skipped anchor would recreate exactly the silent-pass hole this
  increment closes.
- Precedent: `_submodule_state_failures` refuses (red, by name, no SHAs on the
  uninitialized shape) rather than skipping; `_compare_tree` refuses a missing
  tree; `_read_lock`'s empty-lock fallback makes every standard report
  unpinned. A deinitialized local run is *already* deeply red through these
  lanes — the anchor adds no new local burden and no new local behavior.
- The skip-with-name pattern (`version_lines`' `submodule unknown`) belongs to
  reporting surfaces, not gates; it is not used here.
- CI initializes submodules recursively, so the anchor always executes there —
  the environment where the pairing is actually load-bearing for `main`.

Where each behavior applies: **CI and any initialized-at-pin checkout** — the
anchor decides; **initialized away from the pin** (mid-train) — the state
refusal names both SHAs, the anchor stays silent (the lock being compared
belongs to the pinned commit; a deliberate ahead working tree is a state
question, not a compatibility verdict); **deinitialized** — the state refusal
plus the existing missing-lock/missing-tree lanes; the anchor is unreachable
and adds nothing.

## 7. Minimal first increment and deferrals

**Scope (one main-repo PR, no SDK PR, no pointer advance):**
`src/benchweave/standards/check.py` (state sharing + two functions),
`tests/standards/test_check.py` (fixture line + five tests),
`docs/internal/invariants.md` (CON-12 amendment),
`docs/internal/drift-and-obligations.md` (obligations 6/7),
`standards/GOVERNANCE.md` (one sentence). No schema, no corpus bytes, no
version bump, no lock byte changes — **Tier 3 by the review rubric's
letter.** Amendment (governor fold, 2026-09-24): this record originally
classified the increment "**not Tier 3**", reading the GOVERNANCE.md touch
as prose-carve-out; the rubric refutes that — first-match-wins classifies
"anything under `standards/`", and the #69 mandate's "(corpus, prose, or
either manifest)" includes prose. The Tier-3 slate ran in full: the
standards-governor lane, two independent adversary lanes, an independent
cold full suite (governor-supplied), and independently reproduced
RED-sanity. The owner holds a reserved ruling on whether to add an explicit
prose carve-out to the rubric; until then the letter governs. The increment
landed on `feat/issue187-sdk-anchor` (13d1c57 RED, 4538865 GREEN, ad96790
docs).

**Deferrals (explicit):**

| # | Deferred | Trigger / why |
|---|---|---|
| D1 | Correct `packages/sdk/docs/internal/release-review-matrix.md:82` (the pre-fork-(a) "sync provenance" rationale) | Next SDK-repo train of any kind. It is the recorded rationale that produced #187; the anchor makes the belief mechanically inert main-side, but the prose should not survive into another SDK release review. SDK bytes → cannot ride this main-only PR. |
| D2 | Anchoring `compatibility.main_project` (a `>=` range, hardcoded `">=0.1.0"` by the writer) | Needs range semantics and an SDK-side writer fix first; near-vacuous today. Not this increment's shape. |
| D3 | A `sdk package <version>` line in `version_lines`' shared-state glance | Serves the devstage glance, but reporting only; the anchor does not need it. |
| D4 | The SDK-side anchor (the SDK's own `--check` comparing its lock to its own pyproject, catching the staleness in the SDK PR itself) | Defense-in-depth; the main-repo gate already protects `main` at pointer-advance time. Rides the next SDK train touching `standards_sync`/check. |
| D5 | Reading the pinned pyproject via git objects (`git show <pin>:pyproject.toml`) instead of the working tree | Immune to a dirty working tree at HEAD==pin, but costs a subprocess and requires the submodule repo present; the working-tree read under the HEAD==pin gate is the established in-tree precedent for the lock bytes themselves. Revisit only if a dirt-at-pin false verdict is ever observed. |

## 8. Measurable proof and the pre-committed acceptance rule

Deterministic gate — the measurement is a fixture matrix, not a statistic:
one historical state, one healthy state, three malformed states, two
submodule-state postures (the latter two already pinned by existing tests).

**Written before implementation; both kill directions fixed:**

- **SHIP iff all five hold:**
  1. RED: on pre-increment code, `run_check` on the replay state (§4.1) returns
     `[]` — recorded in the PR body as the demonstrated hole.
  2. With the anchor: the replay yields exactly one `sdk_version_unanchored:`
     line naming both versions, and no `sdk_compatibility_drift` line.
  3. The live tree stays clean: `test_real_tree_is_clean` green in CI before
     and after (lock 0.2.0 = pyproject 0.2.0 at pin `fc7f05c`).
  4. The full standards suite (`tests/standards/`, `tests/sdk/`) green with no
     fixture change beyond the `_sdk_copy` pyproject line.
  5. Uninitialized and moved-submodule fixtures produce no
     `sdk_version_unanchored` family line beyond the single existing state
     refusal.
- **KILL if any of these:** the live tree reds under the anchor (the premise —
  pyproject@pin is the truth source and the current state is a pairing — is
  wrong; stop and re-derive); the replay state cannot be constructed without
  also tripping an existing prefix (the fixture is unsound — the measurement,
  not the code, is at fault); or the anchor proves unimplementable without
  reading git object storage (D5 forced into scope — redesign).
- **UNDERPOWERED, not conclusive, if:** the RED in (1) can only be shown with
  the mirror also drifting — that would mean CON-12 already closes the class
  and the increment is unnecessary (a DON'T-BUILD outcome, decided on evidence,
  not a signal to loosen the fixture until the test passes).

Post-merge canary: the next real pointer-advance PR (any SDK train) exercises
the anchor on genuine state; a red there with a genuinely-synced lock is a
false positive and reopens the increment.

## 9. Precedent

- `_compare_mirror` + `_submodule_state_failures` (`check.py:198-263`) — the
  gate-and-refuse-by-name mechanism this extends; landed for issue #158 as
  CON-12's amendment, with the same uninitialized/moved refusal tests this
  design inherits rather than duplicates.
- `standards_sync.py::_sdk_version` (:667) — the write-side stamp; the anchor
  is its read-side dual over the same input. The cross-repo mirror discipline
  is the repo's own pattern (`STAMP_LINE` mirrored in both files, pinned equal
  by `test_stamp_line_is_identical_in_checker_and_sdk`).
- `_compare_lock`'s `sdk_version_mismatch:` lane — the naming and one-line-per-
  failure format the new prefix follows.
- CON-11's shape — committed claims byte-pinned to a live re-derivation; the
  anchor applies that shape to `compatibility.sdk`.
- Obligation 6's mirror clause — added in place when CON-12 landed; obligation
  7's pairing clause follows the same in-place amendment pattern.

## 10. Invariant, drift and CI impact

| Surface | Moves? |
|---|---|
| CON-12 | Amendment (§5); CON-4 note unchanged |
| `docs/internal/drift-and-obligations.md` | Obligations 6 and 7 amended |
| `standards/GOVERNANCE.md` | One sentence (governor lane; no repin — not corpus-pinned) |
| MCP tools / REST / openapi / CLI commands | No change (new failure family inside an existing command's output contract) |
| Operator docs / device-developer guide | No change (failure prefixes are not enumerated there — verified by search) |
| Fixture lattice / SDK repo / corpus bytes / lock bytes | No change |
| CI | Zero new jobs; +~5 tests in existing lanes; `make check-sdk-standards` invocation unchanged (anchor rides `benchweave.standards check`, already in `gates` and `package` on both OSes; `tomllib` read is portable) |

Review lanes: the full Tier-3 slate (amended 2026-09-24, governor fold —
this section originally planned "ordinary code review + the
standards-governor lane for the GOVERNANCE.md touch only"; see the §7
amendment for the tier correction): the standards-governor lane (the
GOVERNANCE.md touch), two independent adversary lanes, an independent cold
full suite (governor-supplied), and independently reproduced RED-sanity.
The owner's reserved prose-carve-out ruling (§7) applies here identically.

## 11. Top risks, each with its falsifier

1. **The anchor reds a healthy contributor checkout** (e.g. a fork that syncs
   its own lock at a different SDK version). Falsified/caught by: acceptance
   rule (3) plus the canary; the failure line names both versions and the
   one-command remediation, so a false positive is diagnosable, not mysterious.
   A fork running its own standards sync out-of-band is already outside the
   supported posture (main-first direction, GOVERNANCE "Direction").
2. **Dirty working tree at HEAD==pin** produces a verdict about uncommitted
   pyproject bytes. Disclosed residual D5 — identical in class to the lock
   bytes themselves being read from the working tree today; no widening.
3. **Fixture fallout beyond `_sdk_copy`** (another harness building synthetic
   SDK roots without pyproject). Enumerated: `test_scenarios.py` is ready by
   construction; `change(operation:"tests")` at build time is the sweep. If an
   unknown harness appears, that is an implementation discovery, not a design
   change.
4. **The new prefix reads as actionable-by-manifest** (a contributor "fixes"
   `sdk_version_unanchored` by editing the mirror instead of re-syncing). The
   line's remediation names `make sync-sdk-standards` and the lock+mirror+pointer
   landing; the design considered and rejected folding into
   `sdk_compatibility_drift` precisely to keep the two fixes distinct.
5. **D1 prose outlives the increment** and a future SDK release review follows
   the stale row. Mitigated by the anchor (the belief no longer passes a gate)
   and by D1's trigger being the next SDK train of any kind; accepted residual
   until then, on record here.
