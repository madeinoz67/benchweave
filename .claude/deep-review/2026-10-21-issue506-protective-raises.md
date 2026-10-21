# Issue #506 — protective-transition raise containment: engine dispatch containment + coordinator belt

- **Tracker:** madeinoz67/benchweave#506 (this repo's single issue stream; no SDK-side
  issue exists by design — gateway-only diff).
- **Branch:** `fix/506-protective-raise-containment` (worktree `.wt/ap-protect-3k7q`), cut
  from `origin/main` at `b905b19a`; branch HEAD at authoring is `05958386` (two later
  commits touch neither `src/benchweave/control/`, `src/benchweave/interfaces/`, nor
  `tests/faults/` — `git diff --stat b905b19a..HEAD` over those paths is empty).
- **Date:** 2026-10-21. This record lands as the arc's FIRST commit, before any test or
  measurement in this increment has run.
- **Record note:** retitled and moved from its authoring path
  (`2026-10-21-issue506-protective-raise-containment.md`, the arc's first commit
  `c309a482`) by the designer's amendment after the arc shipped. The pre-commitment
  proof is the authoring commit's position in history — BEFORE the A1-A3 measurement
  runs — reachable on this path via `git log --follow`.
- **Evidence basis:** every file:line cite below was read this session against THIS
  worktree's bytes (native reads; the gortex daemon served the file bodies but returned no
  `freshness`/`actual_view` object, so view identity is established by the empty diff above
  over the involved paths, and all cites were confirmed on the worktree bytes directly).

## 1. Finding (confirmed at source, plus one site the audit missed)

An exception RAISED out of a plugin dispatch inside the protective transition escapes the
engine and, one layer up, aborts the coordinator's terminalisation path. Four sites:

1. **`protection.py:286`** — `plugin.dispatch` in `_dispatch_actions` has no try/except.
   A raise aborts the remaining safe actions and `_verify`; `enter`
   (`protection.py:246-265`) is try/FINALLY only — `_in_transition` resets and the raise
   propagates. The module's own contract ("a failed or unknown safe action is recorded,
   and the remaining non-conflicting actions are still attempted") is therefore untrue for
   the raising case: nothing is recorded and nothing further is attempted.
2. **MISSED BY THE AUDIT: `protection.py:143`** — `plugin.dispatch` in
   `read_signal_values` is the same unguarded call. It serves BOTH the verify loop's
   signal reads and the monitor tick's; a plugin that raises during verify escapes
   identically. The function's docstring already promises "a missing device, failed read,
   non-numeric value, bad quality or lapsed freshness marks the signal invalid" — a raise
   is a failed read, and the promise should hold by one derivation for both callers.
3. **`coordinator.py:1294`** — `engine.enter` sits OUTSIDE `_finish_run`'s only
   try/except (which wraps `_run_and_record` at `coordinator.py:1269-1283`, the A04 body
   belt). A raise out of `enter` skips `build_terminal_record` (`:1314`),
   `finalize_run` (`:1327`), `release` (`:1328`) and the pending re-raise (`:1329-1330`);
   the monitor stays `phase="protecting"` with `on_violation` armed (`:1291-1292`) and
   `_active_monitor` uncleared (`:1297` skipped), and the lease is held to horizon
   (STO-4). With no restart before lease expiry, both recovery legs skip over the run —
   a permanently non-terminal run row.
4. **Downstream containment is partial only:** `worker.py:254-286` (`_drain_with`'s poison
   guard) converts the escape into a terminal PROJECTION with no durable terminal record,
   and `app.py:482-494` (`_RetainingCoordinator.start_run`) closes bridges only in its
   finally. Outside the worker the raise reaches the caller raw.

The returned-FAILURE half of site 1 is already pinned by
`tests/faults/test_protection.py:444-482` (one failing safe action never suppresses the
rest); the raising half is unpinned everywhere. Precedent for the fix shape:
`executor.py:809-828` — `run_body`'s `except Exception` ("L2-F1(c), the A04 family … a
plugin dispatch that raised"), reason format `uncaught_body_exception:
{type(exc).__name__}: {exc}` — plus `_finish_run`'s own `except BaseException` body belt
at `coordinator.py:1271-1283`.

## 2. Mechanism — one increment, two arms, both extending the named precedent

### Arm 1 — engine-local containment (`protection.py`), Exception-width like `run_body`

- **`_dispatch_actions` (`:286`):** wrap the dispatch. On raise, the action record keeps
  its initialised `status: "error"` and gains `error:
  "INTERNAL_ERROR: {type(exc).__name__}: {exc}"` (the record's existing
  `{code}: {message}` error shape); the loop CONTINUES to the remaining safe actions, and
  the existing reason-append (`safe_action {id}: error`, `:293-294`) fires unchanged.
  `_verify` still runs.
- **`read_signal_values` (`:143`):** wrap the dispatch. On raise the reading stays
  `None` → the signal is INVALID by the function's existing derivation — one code path
  covering verify reads and monitor ticks alike. The poll loop continues (dirty poll →
  stability window reset), so a persistently raising read yields `unknown`, never
  `verified`.
- **Width:** `Exception`, exactly like the `run_body` precedent. A `BaseException` out of
  either site still propagates — deliberately: process-control signals are contained one
  layer up by arm 2, whose record-then-reraise contract is the A04 belt's own.
- **Docstrings:** the module contract sentence and `read_signal_values`'s docstring are
  edited so both halves name the raising case — the promise becomes true in both halves.

### Arm 2 — coordinator protection belt (`coordinator.py` `_finish_run`), BaseException-width, the body belt's exact shape

Wrap `engine.enter` plus the monitor cleanup (`:1294-1297`) — cleanup in a `finally`, so
it lands on both paths:

- On raise: `pending = exc`; synthesize a `ProtectionResult` with `safe_state="unknown"`
  (the transition did not complete — uncertainty, never a fabricated `verified`), reason
  `uncaught_protection_exception: {type(exc).__name__}: {exc}`, `actions=[]` (a partial
  transition's action records are not salvaged; the belt's job is the terminal record,
  and the failure rides the open reasons), `entered_at_ns` as captured and `deadline_ns`
  mirroring `enter`'s own arithmetic (`entered_at_ns + max_duration_ms·1e6` from the
  admitted policy).
- The record, `finalize_run` and `release` then proceed exactly as for a body belt catch,
  and a non-Exception `pending` re-raises AFTER the record lands (`:1329-1330`
  unchanged) — the process-control signal is not swallowed, but the record exists either
  way.
- **Pending priority (committed here, before the tests):** the belt overwrites a standing
  body-belt `pending` only when it is `None` or an `Exception`. Unconditional
  overwrite would let a later protection `Exception` displace a body
  `KeyboardInterrupt` and swallow the process-control re-raise — the exact swallow the
  body belt's comment forbids. First-wins for non-Exception pendings; the protection
  exception is recorded in the reasons either way.

**Invariant motion:** CTL-9 amendment — the ending family gains the protection belt and
the open-list reason prefix `uncaught_protection_exception:` (run-record schema
untouched: reasons are open strings, and `ProtectionResult.actions` never enters the
record). CTL-2's terminal truth table math is unchanged (a synthesized `unknown` maps by
the existing rows). No STO/CON/REG motion, no on-disk schema change.

## 3. Deferrals

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| D1 | The worker poison guard's no-terminal-record shape (a contained escape still produces no durable terminal row, only the projection + gateway log) | Follow-on issue, filed at PR-open (the PR body maps it; the number is assigned at open, not invented here) | A second gateway-log `run_worker poison` line over a run with no durable terminal row |
| D2 | `stream_host.py` `:216`/`:303` unguarded arm/teardown dispatches (contained today via the body belt; arm 2 adds a second net, the sites themselves stay unguarded) | Documentation here | An arm/teardown raise reaching the poison guard |
| D3 | Body-phase tick semantics change — a raising signal read during the BODY now degrades to invalid-signal/trip rather than `execution_error` (arm 1's one-derivation rule reaches the monitor tick too) | Documentation here | A run recording `safe_state: verified` over a signal whose read raises every poll |

Homes follow the repo's cap of one follow-on issue per merged PR: only D1 rides an
issue; D2 and D3 live in this record.

## 4. Proof plan (tests/faults/, the `_FaultPsu`/`TestClock` forges)

- **A1 (arm 1, `:286`):** a RAISING first safe action → `enter` returns; BOTH actions
  recorded; the second physically dispatched (`disable_dispatches()`); the first carries
  `INTERNAL_ERROR: RuntimeError: …`; the reason-append fired; verify ran and decided the
  safe state.
- **A2 (arm 1, `:143`):** a raising verify read → `safe_state: "unknown"`, no escape,
  the full budget lapsed on the injected clock.
- **A3 (arm 2):** monkeypatched `ProtectionEngine.enter` raising → `start_run` RETURNS
  an `outcome_unknown` record carrying the belt reason; lease released
  (`get_active_lease` `None`); monitor back to `phase="idle"`, `on_violation None`,
  `_active_monitor` cleared. Harness note: the audit named `test_state_recovery.py` as
  the harness source, but that module is store-level (its imports are
  `benchweave.state.*` only — no coordinator anywhere); A3 lifts `_harness()` from
  `test_protection.py` itself, which is also A1/A2's home.
- **Unchanged:** `tests/faults/test_protection.py:444-482` pins byte-for-byte as it
  stands (the returned-failure half). CTL-1/2/9 pins must stay green.

## 5. Pre-committed acceptance rule

- **SHIP** iff each arm goes RED under revert-only-that-arm (a `cp` backup of the
  production file, collected count ≥ 1 in the RED run) and then GREEN with the arm
  restored; the focused suites plus fresh-cache bare `uv run mypy` plus bare
  `uv run ruff check .` are green; the existing `:444` test is unchanged.
- **KILL** if any arm passes pre-fix (fluff), or any CTL-1/CTL-2/CTL-9 pin reddens.
- **UNDERPOWERED** if A3 needs new production seams — then A3 joins D1's follow-on
  issue, arms 1-2 ship, and the shortfall is disclosed in the report.
