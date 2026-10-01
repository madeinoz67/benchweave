# Issue #207 — Windows deterministic platform expectations (the five-item census batch)

Design record for the remainder of the #207 Windows census: the five
deterministic failures that survive PR #237 (`b4708f7`, 2026-09-27 — the
separator/CRLF family, the docstring escape, and the preview-server fixture
containment all landed there). This batch is #237's direct successor: same
style — platform-aware expectations that keep the pinned property on every
platform — plus one two-line src fix whose whole point is that a rendered
value stops depending on the host.

Tree: `origin/main` at `5c5b505` (2026-10-01), primary checkout. Branch:
`feat/issue207-windows-platform-expectations`; this record is commit 1.
Standards tripwire: this design moves no `standards/` bytes and no version
strings (`git diff origin/main...HEAD -- standards/` expected empty, asserted
at push). No SDK surface, no fixture lattice, no workflow bytes.

**Pre-commitment protocol.** The acceptance rules (§5) were fixed before any
of the new measurements ran. The only numbers quoted as inputs are the two
contributor Windows reds carried in the issue (1724.55 / 1734.19 ms against
the 1700 ms bound — two measured reds on one Windows development checkout)
and in-tree line anchors. No mechanism below was sized from a number it also
promises to deliver: the one numeric bound this batch touches (the row-B
ceiling) takes its `+300` slop from the pre-committed #241 D-rowB row, which
pre-dates the Windows evidence.

## 0. State established from the code, not assumption

### 0.1 The five items, root-caused at `5c5b505`

| # | test | anchor | root cause (verified in code) |
|---|---|---|---|
| 1 | `test_fw5_naive_stamps_anchor_unresolved_and_never_host_local` | `tests/cli/test_retention.py:753`; the `time.tzset()` calls at `:787-795` | `time.tzset` is a Unix-only CPython API (it does not exist on Windows), so the first call raises `AttributeError`; the same three bare attribute accesses are the 3 Windows-mypy `attr-defined` errors (mypy on Windows resolves Windows stdlib stubs, where the attribute is absent) |
| 2 | `test_fold2_wedge_exhaustion_beyond_domain_renders_decidable_output` | `tests/cli/test_retention.py:1585`; failing assert `:1647` (`fatpipe["exhaustion_at"] is not None`) | `src/benchweave/cli/retention.py:866` renders the instant via `datetime.fromtimestamp(now_dt.timestamp() + tte, tz=now_dt.tzinfo)`. The `except (OverflowError, OSError, ValueError)` at `:870` catches BOTH families: true datetime-domain overflow (year > 9999 — the fw3 posture's target) AND a conversion-machinery refusal. On Windows `fromtimestamp` only converts what the C runtime supports (roughly through year 3001), so the fatpipe fixture's year-~5200 instant — INSIDE the datetime domain — renders absent there, with the "beyond the datetime domain (year 9999)" disclosure, which is false for that date. On POSIX the same test is green (CI), which isolates the divergence to that call |
| 3 | `test_fold1_fsync_chain_covers_the_target_and_its_parent` | `tests/cli/test_dispose.py:1241`; failing asserts `:1280-1289` | `_fsync_dir` (`src/benchweave/cli/dispose.py:222`) is deliberately a no-op when the directory open raises `PermissionError` — exactly Windows' documented behavior — so no directory fd is ever opened or fsynced there; the test asserts the target and parent directories WERE fsynced |
| 4 | `test_fold2_durability_errors_refuse_typed_never_laundered` | `tests/cli/test_dispose.py:1292`; failing at `:1326` (`DID NOT RAISE`) | the injected EIO rides the objects-directory fsync (`:1315-1318`); with the directory open refused before any fd exists, the injection point is structurally unreachable, so the typed refusal never fires |
| 5 | `test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot` | `tests/unit/test_otdp_bridge.py:2641`; the band at `:2687` (`1300 <= busy_wait_ms <= 1700`) | the busy-wait's wall duration is the clamp value plus host scheduling slop; the absolute ceiling 1700 assumes POSIX-class slop. Two Windows reds (1724.55, 1734.19) — the #241 slice-3 D-rowB reopen trigger |

### 0.2 The fork is resolved by the code's own semantics (items 3+4)

The filing asks: platform-aware expectation, or a Windows skip that says
why — "whichever matches what `_fsync_dir` promises on Windows." The code
already answers, in the review-wave-vetted docstring at `dispose.py:222`:

> fsync a directory entry so placed names survive power loss. On a platform
> that cannot open a directory for fsync at all (Windows raises
> `PermissionError` on the open) this is a no-op — the platform offers no
> directory-durability primitive to lose. Every OTHER failure on the open or
> the fsync propagates as a typed `archive_target:` refusal: a durability
> error must never be laundered into a committed trail that asserts
> preservation.

That is a promise with two platform-stable parts and one platform-conditional
part, and it picks the option:

- **Platform-conditional** (the chain-coverage property fold1 pins): where
  directory fsync exists, the chain covers target + parent + the new
  ancestors; where it does not, the branch is a CLEAN no-op — the invocation
  still completes, still refuses nothing, and the FILE-level durability
  discipline (each object's fsync, the manifest's fsync) is unchanged. The
  tests must assert exactly that shape per platform — not skip, and not a
  weaker universal assertion.
- **Platform-stable** (the typed-refusal property fold2 pins): every failure
  other than the no-op predicate refuses typed. The fsync-side EIO arm needs
  a directory fd (POSIX-shaped); the OPEN-side non-`PermissionError` OSError
  arm is reachable on EVERY platform, because the open is attempted on
  Windows too and only `PermissionError` is swallowed. The every-platform
  arm becomes the property's primary carrier.

A skip would leave both properties unpinned on the platform where the
project explicitly keeps the suite runnable (`state/hold.py`'s Windows arm
exists so "the gateway remains importable and the suite runnable on Windows
development checkpoints"). Changing the durability mechanism (a real Windows
directory-durability primitive) would be new architecture with no way to
prove it here — §2 defers it with a trigger. **Verdict: platform-aware
expectation.** No genuine product fork remains; the evidence admits one
defensible shape.

### 0.3 The verifiability constraint — and the simulation doctrine

There is no Windows CI leg and no local Windows execution. Per the standing
evidence rule, every platform-conditional expectation in this batch is proven
POSIX-side by driving the SAME branch predicate Windows takes:

- **dispose (items 3+4):** a monkeypatched `os.open` wrapper that raises
  `PermissionError` for read-opens of directories and passes everything else
  through (files, the hold marker, sqlite's C-level opens are untouched). That
  is the exact predicate `_fsync_dir` branches on. Precedent: fold1/fold2
  already monkeypatch `os.open`/`os.fsync` this way in the same file.
- **fw5 (item 1):** `monkeypatch.delattr(time, "tzset")` makes the guarded
  accessor take the no-`tzset` branch on POSIX.
- **wedge (item 2):** monkeypatching `datetime.fromtimestamp` (as referenced
  by the retention module) to refuse out-of-CRT-range timestamps reproduces
  the Windows conversion refusal — and the committed pin keeps that
  monkeypatch permanently, so the rendered instant is proven independent of
  the conversion machinery forever after.

AR-1 (§5) is the batch's load-bearing falsifier: each simulation must
reproduce the contributor's exact failure signature against the OLD test
text. A simulation that produces a different signature falsifies the
same-branch premise and stops the batch.

### 0.4 The #241 cross-checks

**D-rowB, quoted verbatim from the slice-3 record's deferral table**
(`.claude/deep-review/2026-10-01-issue241-slice3-retry-honest-pins-cell-belt-design.md` §2):

> | D-rowB | row-B `busy_wait` ceiling [1300,1700]: relativize to the recorded clamp value (`busy_wait_ms <= clamp_value + 300`, the same +300 slop `fail_delta_ms` already uses — capture the clamp via a recording `busy_timeout_window` wrapper, the shape `test_row_b_sweep_and_startup_reclaim_never_enter_a_window` already uses at :2703) | issue #241 (with or after slice 4) | a CI-verified red of `test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot` (the brief-reported 1732.5 is unlocated — Evidence D — and would be the id's FIRST flake; sweep row 16 = keep-and-document) |

**Still applies as specified:** verified at `5c5b505` — the band is at
`:2687`, the `fail_delta_ms <= 1500 + pre_begin_ms + 300` precedent at
`:2685`, the recording `busy_timeout_window` wrapper shape at `:2703-2709`
(in `test_row_b_sweep_and_startup_reclaim_never_enter_a_window`). Slice 3's
de-clocking touched `tests/integration/test_cross_instance_continuity.py`
only (its §8 file list), so nothing here moved.

**Trigger reading, disclosed:** the row's letter says "a CI-verified red";
with no Windows CI lane existing, the letter can never fire on Windows
evidence. The mechanism reading — an evidenced red of the named id — governs
(the row's own Evidence D treated an unlocated single report as insufficient;
two located, measured reds in the issue are a different evidentiary class).
This batch executes the payload under #207; the #241 outcome comment closes
the row as folded-by-trigger with a pointer here.

**test_f5 finding (for the PR body):**
`tests/integration/test_run_activation.py:1188`
`test_f5_measurement_seams_tick_times_and_saturated_polls` was created by
`5feed9a` (2026-09-23, the issue #167 review wave) and the file's last touch
is `4176431` (2026-09-26, #146 slice 3) — BEFORE every #241 slice. No #241
slice record mentions it and no slice commit touches the file. **Not
addressed by #241 slices 1-3.** It is not `timing`-marked (it runs in the
`gates` partition), so it rides #241's unmarked-real-clock family, not the
timing lane's. The PR body states exactly this; the item stays with #241.

## 1. Mechanism, item by item

### 1.1 Item 2 — the wedge instant becomes host-independent (the only src change)

`retention.py:862-871` today renders the instant through the platform's
timestamp conversion. Replace the one expression with pure datetime
arithmetic:

```python
exhaustion_at = _iso(now_dt + timedelta(seconds=tte))
```

`timedelta` is already imported (`retention.py:105`). Everything else in the
block is untouched: the `except (OverflowError, OSError, ValueError)` tuple
stays as the belt (the addition itself raises `OverflowError` for true domain
overflow — the year-~178000 trickle fixture — and `timedelta(seconds=tte)`
construction raises it for extreme `tte` beyond `timedelta.max`), so the
disclosed beyond-domain bucket keeps its exact POSIX behavior and becomes
TRUE when it fires: absence + disclosure now mean "past year 9999", on every
host, which is what `docs/operator-guide.md:479-481` already promises ("A
forecast whose exhaustion instant falls beyond the datetime domain keeps
`time_to_exhaustion_s` (the honest figure) and renders the instant absent,
disclosed"). The current Windows behavior contradicts that sentence for
in-domain dates; this fix delivers the documented contract everywhere. The
conversion-machinery refusal family (`OSError` from `fromtimestamp`) becomes
unreachable by construction.

This DELETES a platform dependency instead of adding a platform seam — no
`sys.platform` branch anywhere (the in-tree seams in `state/hold.py:38` and
`cli/atrest.py:166` are the precedent for when a platform branch IS the right
answer; this is not that case, and not adding one is the smaller change).

### 1.2 Item 1 — fw5: guard the Unix-only stressor, keep the property everywhere

Restructure the test body into a module-level helper
`_fw5_report_bytes(tmp_path, *, tzset)`:

- `tzset = getattr(time, "tzset", None)` — no bare `time.tzset` attribute
  access anywhere in the file, which is both the runtime guard and the
  Windows-mypy fix (the 3 `attr-defined` errors are the three bare accesses
  at `:788/:791/:795`).
- The property arm — the naive row is `anchor_unresolved` with
  `disposal_date: None` — runs in EVERY mode. It is platform-independent
  string handling (`_parse_utc` returns `None` for offset-less stamps).
- The TZ-flip byte-identity arm (`TZ=Australia/Perth` vs `TZ=UTC`, reports
  byte-equal) runs only in `tzset` mode: flipping the process-local timezone
  in-process is structurally impossible on Windows, and pretending otherwise
  would be a fake stressor. In no-`tzset` mode the helper asserts the flip
  arm was bypassed by the guard (a sentinel/marker, so the bypass is itself
  pinned, not silent).

The existing test id calls the helper with the real `time.tzset` (POSIX CI
behavior byte-identical to today). One new test drives the Windows branch on
POSIX: `monkeypatch.delattr(time, "tzset")`, then the helper must take the
no-`tzset` path and the property arm must still hold. One committed sabotage
arm (the slice-3 classifier-arm precedent) monkeypatches
`benchweave.cli.retention._parse_utc` to the pre-fix localized guess and
asserts the property assertions RED in BOTH modes — the guard must not buy
platform coverage by losing the regression teeth.

### 1.3 Items 3+4 — dispose: capability-probed expectations plus the every-platform typed-refusal arm

A module-level runtime probe (function-local imports, matching the file's
style):

```python
def _dir_fsync_available(tmp_path: Path) -> bool:
    # probe, don't guess: open+fsync a directory and let the platform answer
```

- **fold1** (`:1241`) keeps its id and fixture and becomes platform-aware in
  one body: when the probe is True, today's assertions unchanged (target,
  parent, `objects/`, `manifests/` all in `fsynced`); when False, the no-op
  shape: `model["counts"]["archived"] == 4` (the invocation completes), NO
  directory path appears in `fsynced` (the branch taken cleanly), and the
  manifest FILE path IS in `fsynced` (file-level durability unchanged). On
  any given host exactly one branch runs, and both are meaningful asserts —
  no skip.
- **fold2** (`:1292`) keeps the fsync-side EIO arm under the probe (it needs
  a directory fd) and gains the every-platform arm as the property's primary
  carrier: the spy's `os.open` raises `OSError(errno.EIO)` for the
  objects-directory open itself (matched by `Path(str(path)).is_dir()` and
  name, not by a `'/'` literal — the #237 lesson), which on every platform
  including Windows reaches `_fsync_dir`'s `except OSError` →
  `ArchiveTargetRefused` with the store untouched (the existing
  `_snapshot_all` + zero-invocation asserts cover the never-laundered half).
- **One new simulation test** installs the dir-open `PermissionError`
  wrapper (read-opens of directories raise; every other open passes through
  to the real `os.open`) and pins the Windows shape on POSIX: the full
  `--execute` with an archive target completes, archives 4, raises nothing,
  fsyncs no directory, and still fsyncs the manifest file. This is the arm
  that would catch a future "no-op that isn't clean" regression (for
  example a `PermissionError` swallow that also swallowed the follow-up
  failure, or a refactor that starts refusing on the no-op platform).

Why a runtime probe rather than `sys.platform == "win32"`: the probe measures
the actual predicate the branch keys on (can this host open a directory for
fsync), stays truthful on exotic POSIX filesystems that refuse directory
opens, and — decisively — is the same predicate the simulation falsifies, so
POSIX executes the Windows branch through the probe's own False path. The
#237 `test_backslash_asset_paths_are_rejected_on_every_platform` arm is the
in-tree precedent for every-platform test construction over
platform-conditional reality.

### 1.4 Item 5 — row-B: execute the D-rowB payload verbatim

In `test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot`:

- install the recording `busy_timeout_window` wrapper (the `:2703-2709`
  shape, with the `# type: ignore[method-assign]` the sibling tests carry)
  before the dispatch;
- pin the recorded clamp: exactly ONE window entered, and
  `1300 <= clamp <= 1500` (entry-time remaining of a 1500 ms deadline at
  bracket entry — pins that a clamp near the deadline was actually applied,
  never the 5000 ms open default; this assertion is what keeps the
  relativized ceiling non-vacuous);
- the ceiling becomes `busy_wait_ms <= clamp + 300` (the D-rowB letter, the
  same `+300` slop `fail_delta_ms` uses at `:2685`);
- the floor `1300 <= busy_wait_ms` stays absolute and unchanged (the
  load-safe direction — host load inflates waits, never shortens them; the
  slice-3 doctrine);
- the `timing` marker stays; nothing else in the test moves.

Worst observed Windows red 1734.19 against `clamp + 300` = 1800 leaves 66 ms
of headroom — disclosed, not tuned: the slop was pre-committed by the
deferral row before the Windows numbers existed, and widening it after
seeing them is exactly the failure this repository guards against. If the
corroborating Windows rerun still reds INSIDE the new bound, that is the
owner fork the record names (§2 D4), not a silent re-band.

## 2. Minimal first increment scope and deferrals

Build order (one RED-provable slice per commit, fast triple per commit,
full battery once before push):

1. Commit 1: this design record.
2. Commit 2 — item 2 (src): the arithmetic change + the committed
   conversion-independence pin (RED-first: the pin reds against pre-change
   `retention.py`, greens with the fix — §5 AR-3).
3. Commit 3 — item 1 (fw5): the helper restructure + the no-`tzset` shape
   test + the sabotage arm.
4. Commit 4 — items 3+4 (dispose): the probe, the platform-aware fold1/fold2,
   the simulation test, the open-side typed-refusal arm.
5. Commit 5 — item 5 (row-B): the D-rowB execution, with the in-place
   clamp-off RED demonstration recorded in the commit message.
6. Commit 6 — docs: one sentence in the testing-conventions list
   (`docs/internal/drift-and-obligations.md`) + review folds.

### Deferral table

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | a real Windows directory-durability primitive behind `_fsync_dir` (backup-semantics handle + volume flush) — new architecture, unprovable without a Windows lane | this record; noted in the #207 outcome comment | a Windows operator reporting post-crash archive loss, or the Windows CI lane's arrival |
| D2 | a Windows CI leg (or standing contributor rig) — converts every simulated-Windows proof in this batch into lane evidence, and gives the two intermittent `sqlite3.OperationalError` disk-I/O items (`test_kill_mid_disposition_leaves_neither_audit_nor_deletion`, the ar5a item) a place to be reproduced | issue #207 (owner call on close, §5 AR-8) | owner/team decision |
| D3 | `mypy --platform win32` over the whole tree as a standing lane — the touched-file delta is proven this batch (AR-6); the rest of the tree's Windows-stub finding count is unknown and not this batch's to open | issue #207 outcome comment; revisit with D2 | the Windows lane |
| D4 | D-rowB-2: if the corroborating Windows rerun reds INSIDE `clamp + 300`, raising the slop vs de-clocking the clamp cell is an owner fork — never silently re-tuned | this record + #241 outcome comment | a Windows red of `test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot` inside the new bound |
| D5 | `test_f5_measurement_seams_tick_times_and_saturated_polls` (unmarked real-clock family, `gates` partition) — NOT addressed by #241 slices 1-3 (§0.4) | issue #241 | #241's own census rows |
| D6 | invariant candidate: "rendered projection instants are host-independent — pure datetime arithmetic, never platform-ranged conversion" as an amendment to `docs/internal/invariants.md` | this record; owner call | owner call (no invariant file edit in this slice) |

Out of scope entirely, per the filing: the two intermittent disk-I/O faults
(evidence-tracked in #207 until D2), the 1-in-15 Linux poc_acceptance flake
(#241 family), and test_f5 (D5).

## 3. Precedent (all in-tree, extended not invented)

- **PR #237 (`b4708f7`)** — the established platform-fix style this batch
  extends: expectations built from `Path` rather than `/` literals,
  `as_posix()` for canonical listings, `newline="\n"` for byte-exact
  fixtures, and every-platform arms over skips
  (`test_backslash_asset_paths_are_rejected_on_every_platform`).
- **fold1/fold2's own spy pattern** (`test_dispose.py:1260-1270`,
  `:1310-1321`) — the `os.open`/`os.fsync` monkeypatch with an fd→path map;
  the simulation wrapper and the open-side injection extend it.
- **`state/hold.py:38`** — the in-tree platform-seam precedent and its
  disclosure discipline (the suite stays runnable on Windows development
  checkouts); cited as posture, NOT extended — this batch adds no src
  platform branch.
- **The in-run-relative band precedent** — `fail_delta_ms <= 1500 +
  pre_begin_ms + 300` (`test_otdp_bridge.py:2685`) and the recording
  `busy_timeout_window` wrapper (`:2703-2709`): the two mechanisms D-rowB
  composes, both already proven in the same file.
- **The committed sabotage/regression arm** (slice 3's classifier-arm shape)
  and the **in-place RED demonstration recorded in a commit message**
  (slice 3's AR-2(b) shape) — the two teeth-proof vehicles this batch uses.
- **The capability-probe-over-platform-string choice** — probe the predicate
  the branch keys on (#237's every-platform construction is the test-side
  precedent; the hold marker's read-only probe in `daemon_holds` is the
  src-side "measure, don't guess" precedent).

## 4. Invariant and drift impacts; tier and the Step-1 keyword scan

- **No CTL/STO/CON/REG invariant is touched.** Phase-A ordering (STO-6's
  lane), the store hold, the single-writer rule, the executor — untouched.
  The only src change makes a rendered projection value host-independent,
  which SERVES the architecture promise ("checks whose results mean the same
  thing no matter which host ran them") rather than amending any invariant.
  The candidate amendment is D6, deliberately not taken in this slice.
- **Obligations walked (G5):** 1-3, 5-22 — none fire (no interface bytes, no
  plugin-visible behavior, no lattice, no dependency, no pointer). Obligation
  4 (CLI behavior → operator docs): the operator guide at `:479-481` already
  documents the behavior item 2 delivers; no doc motion. The one docs edit
  is the testing-conventions sentence in `docs/internal/drift-and-obligations.md`
  (commit 6). CI map unchanged — no job shape moves; the new ids ride the
  existing `gates` partition and the row-B edit rides the existing `timing`
  job.
- **Standards tripwire:** `git diff origin/main...HEAD -- standards/` is
  expected EMPTY and asserted at push; no version strings move; the
  version-literal zero gate's denominators are untouched (`tests/` is
  outside the gated scopes; the src change adds no literals).
- **Tier and the Step-1 keyword scan (#254).** Expected diff: this record,
  `tests/cli/test_retention.py` (helper restructure + 3 new ids),
  `src/benchweave/cli/retention.py` (one expression + comment),
  `tests/cli/test_dispose.py` (probe + 2 modified tests + 2 new ids),
  `tests/unit/test_otdp_bridge.py` (wrapper + band edit),
  `docs/internal/drift-and-obligations.md` (one sentence). Design-time scan,
  partitioned because this statement line self-carries every keyword it
  names (the rubric's own self-fire clause, intended):
  (a) over the expected CODE/DOCS hunks, excluding this record — the
  keyword `threading` appears 2 (both in the row-B hunk's context lines:
  the test's two event-setup calls that bracket every possible
  wrapper-insertion point); each of the other seven keywords 0.
  (b) this record itself — `threading` 3 (this statement's own three
  mentions, in parts (a), (b), and the totals line; the word occurs nowhere
  else in the record), each other keyword exactly 1 (this statement line
  only, self-referential). Whole-expected-diff totals: `threading` 5, each
  other keyword 1. Per-slice: the item 1-4 slices are Tier 2 by
  path (test code + `src/benchweave/cli/`) with clean code-hunk scans; the
  item-5 slice is Tier 3 by keyword via its hunk context. **Maximum tier
  across slices: TIER 3** — the refute battery runs two independent
  adversary lanes per the standing Tier-3 rule. The review re-derives the
  tier over the real diff; the builder re-runs the scan pre-PR and records
  the counts (plain integers, partitioned the same way).

## 5. Measurable proof and the pre-committed acceptance rules

All rules are executable on macOS/Linux. Sample sizes and both kill
directions are fixed here, before any new measurement runs.

### 5.1 Build-time (PR) acceptance

- **AR-1 (same-branch reproduction — the batch's load-bearing falsifier).**
  Against the OLD test text (checked out in place or stashed), each POSIX
  simulation must reproduce the contributor's exact failure signature, pasted
  in the PR body: (a) old fold1 + dir-open `PermissionError` simulation →
  the `:1280` "target directory itself must be fsynced" assert reds; (b) old
  fold2 + simulation → `Failed: DID NOT RAISE` at `:1326`; (c) old fw5 +
  `monkeypatch.delattr(time, "tzset")` → `AttributeError` on the first
  `tzset` call; (d) old wedge test + `fromtimestamp` refusing timestamps
  beyond the Windows CRT range → the `:1647` `is not None` assert reds.
  Count: 4 reproductions, each pasted. **KILL:** any simulation producing a
  DIFFERENT signature than the contributor reported — the same-branch
  premise is false, the batch stops, and the divergence is reported to the
  issue. (This is the conclusive-vs-underpowered split: a different
  signature is a wrong-premise result, not a flaky one.)
- **AR-2 (both branches green on POSIX).** All modified and new tests green
  with simulations off (natural POSIX) and the simulation tests green (they
  self-install). Collected-count check from junitxml attributes, reported as
  before/after per file: `tests/cli/test_retention.py` +3 ids, 
  `tests/cli/test_dispose.py` +2 ids, `tests/unit/test_otdp_bridge.py` +0
  (modified in place), suite total +5. **KILL:** any count delta other than
  +5, or any pre-existing id lost.
- **AR-3 (src-fix RED→GREEN, the G3 gate for item 2).** The committed
  conversion-independence pin (monkeypatch `fromtimestamp` as referenced by
  the retention module to refuse; assert the in-domain instant still renders
  and only the true domain-overflow key discloses) must RED against
  pre-change `retention.py` and GREEN with the fix. Both pasted; the
  collected count shown (a `no tests ran` is a failed check). **KILL:** the
  pin greens against the old src (vacuous pin — fix before merge).
- **AR-4 (teeth).** (a) The fw5 sabotage arm reds in BOTH tzset modes
  (committed). (b) The row-B relativized ceiling reds under an in-place
  clamp-off demonstration (dispatch clamp neutralized → the busy-wait runs
  at the open default → far past `clamp + 300`), recorded in the commit
  message — the slice-3 AR-2(b) vehicle. **KILL:** either arm failing to
  red.
- **AR-5 (POSIX identity of the src change).** The retention model JSON for
  the fold2 wedge fixture AND the `_seed_growth` fixture, generated
  pre-change and post-change on POSIX, byte-compared. Pre-committed
  tolerance: byte-identical, OR differences confined to at most 1 µs inside
  `exhaustion_at` strings (float rounding between the two quantizations)
  with nothing else moved and the diff disclosed. **KILL:** any other
  difference — a moved date or any other field is a defect, fix or revert.
  (No test pins an exact `exhaustion_at` string — verified: the pins are
  inequality-at-`:400`, `None`-at-`:1210/:1444`, and year-prefix at
  `:1648/:1652` — so the suite cannot silently absorb a real change here.)
- **AR-6 (mypy, both platform contexts).** Bare fresh-cache `uv run mypy`
  green (the G1 gate, unchanged). Supplementary evidence, not a gate:
  `uv run mypy --platform win32 tests/cli/test_retention.py` shows ZERO
  `attr-defined` errors post-change, with the pre-change run on the same
  invocation showing the 3 (file-scoped, disclosed: the whole-tree
  `--platform win32` count is unknown and is D3's to carry, not claimed).
  **KILL:** any remaining `attr-defined` on the touched file.
- **AR-7 (gates).** Fast triple per commit (bare ruff, fresh-cache bare
  mypy, focused pytest; `tests/faults/` rides the full battery); full
  battery + both tripwires once before push; the `timing` job green in the
  complete `gh pr checks` rollup (`scripts/merge-verified.sh`); merge on the
  full rollup only.
- **AR-8 (Windows corroboration, out of band).** The PR body requests a
  contributor Windows rerun of the five ids plus the AR-6 file-scoped mypy
  check. **SHIP-corroboration:** all five green on Windows and 0 attr-defined
  on the file. **REOPEN:** any of the five redding with a signature not
  already explained (a red INSIDE the new row-B bound is D4's trigger, not a
  mystery). **UNDERPOWERED, stated honestly:** contributor reruns are an
  uncontrolled cadence — this is a one-shot corroboration, not a sampled
  rate, and no claim stronger than "corroborated / not yet corroborated" is
  made from it. Until a rerun happens the POSIX-simulation proofs are the
  acceptance evidence, and the issue says so.

### 5.2 Post-merge

No lane exists to sample post-merge; the pre-committed post-merge rule is
AR-8's corroboration plus the deferral triggers in §2. The two intermittent
disk-I/O items remain evidence-tracked in #207 regardless of this batch
(they are not deterministic and are not claimed fixed by anything here).
Whether #207 closes at merge (with a follow-up filed for the disk-I/O items
and the rerun request) or stays open until the rerun lands is an owner call,
named in the outcome comment either way.

## 6. Evidence appendix (anchors verified at `5c5b505`, this session)

- `tests/cli/test_dispose.py:1241-1333` — fold1/fold2 bodies, spy pattern,
  asserts as cited. `src/benchweave/cli/dispose.py:222-240` — `_fsync_dir`
  with the no-op docstring; call sites `:197-201`, `:443`, `:495`.
- `tests/cli/test_retention.py:753-801` — fw5 with the three `tzset` calls;
  `:1585-1652` — the wedge test; `:1647-1648` the failing fatpipe asserts.
- `src/benchweave/cli/retention.py:862-871` — the exhaustion block;
  `:105` the existing `timedelta` import.
- `tests/unit/test_otdp_bridge.py:2641-2690` — the row-B test; `:2685` the
  `fail_delta_ms` precedent; `:2687` the band; `:2701-2709` the recording
  wrapper. `src/benchweave/host/otdp_bridge.py:29-49` — the entry-time-
  remaining clamp docstring; `:372-381` the `dispatch_clamp` bracket.
- `docs/operator-guide.md:479-481` — the documented exhaustion contract.
- The contributor Windows census (issue #207): two measured row-B reds
  (1724.55, 1734.19 ms vs the 1700 ms ceiling) and the four failure
  signatures reproduced in §5.1 AR-1. Windows `fromtimestamp` range and the
  Unix-only status of `time.tzset` are CPython-documented platform behavior,
  cited as mechanism, consistent with every observed signature; neither is
  claimed as a local measurement.

## 7. Top risks and their falsifiers

1. **A simulation is not the platform.** The dir-open wrapper raises
   `PermissionError` for read-opens of directories; if real Windows ever
   surfaces a different exception class for some path shape, the no-op
   predicate would not fire there and the platform-aware branch would assert
   the wrong shape. Mitigated: the docstring's predicate claim is
   review-wave-vetted; AR-1 ties each simulation to the observed signature;
   AR-8 corroborates. Falsifier: an AR-8 rerun signature that diverges.
2. **The arithmetic is not perfectly identical to the conversion on POSIX**
   (µs quantization). Pre-committed tolerance in AR-5; no exact-string pin
   exists (verified §5.1). Falsifier: an AR-5 difference beyond the
   tolerance.
3. **The row-B margin is thin** (66 ms on the worst observed Windows red).
   Accepted and disclosed (§1.4): the slop is pre-committed, and re-tuning
   it post-hoc is the anti-pattern; D4 carries the owner fork. Falsifier: a
   Windows red inside `clamp + 300`.
4. **The fw5 guard could silently weaken the stressor** (a future edit makes
   the flip arm conditional on something weaker than `tzset` presence). The
   no-`tzset` test pins the bypass sentinel; the sabotage arm pins the teeth
   in both modes. Falsifier: either arm greening when it should red.
5. **Monkeypatching `os.open` process-wide during the dispose tests** affects
   every in-process `os.open` caller for the test's duration. The fold tests
   already do exactly this in the same file; the wrapper is strictly
   narrower (directories, read flags only); sqlite's opens are C-level and
   unaffected. Falsifier: any unrelated test redding when the simulation
   tests run in the same process (the full battery would catch it).
6. **The wedge fix invites scope creep** ("fix every `fromtimestamp` in
   src"). Verified: `retention.py:866` is the only src site. One site, one
   change. Falsifier: a grep showing another site on a failing path — none
   exists today.

## 8. File-level change list

| file | change |
|---|---|
| `src/benchweave/cli/retention.py` | one expression at `:866` (`_iso(now_dt + timedelta(seconds=tte))`) + comment; nothing else |
| `tests/cli/test_retention.py` | fw5 restructured to the helper + guard; +3 ids (no-`tzset` shape; `_parse_utc` sabotage arm, both modes; conversion-independence pin) |
| `tests/cli/test_dispose.py` | the capability probe; fold1/fold2 platform-aware; +2 ids (Windows-shape simulation; open-side typed-refusal arm folded into fold2's file neighborhood) |
| `tests/unit/test_otdp_bridge.py` | row-B: the recording wrapper, the clamp pin, the relativized ceiling; no new id |
| `docs/internal/drift-and-obligations.md` | one testing-conventions sentence: platform-conditional expectations key on a runtime capability probe, assert the property in every branch, and pin the other platform's shape on POSIX by simulating the primitive's absence — never static reasoning alone |
| `.claude/deep-review/2026-10-01-issue207-windows-deterministic-platform-expectations.md` | this record, commit 1 |
| issue #207 | outcome comment: per-item verdicts, the D-rowB fold pointer, the f5 statement (§0.4), the AR-8 rerun request, the owner close call |

No `standards/` bytes. No workflow bytes. No dependency bytes. One numeric
bound moves — the row-B ceiling — and it moves exactly as the pre-committed
#241 D-rowB row specified, before any Windows number was seen by this
author.
