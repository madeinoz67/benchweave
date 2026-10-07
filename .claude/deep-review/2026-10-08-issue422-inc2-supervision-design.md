# Issue #422 increment 2 — supervision model + stop semantics + serve-surface declaration (design record, NO CODE)

**Date:** 2026-10-08
**Issue:** madeinoz67/benchweave#422 (increment 2 of 4: env autoload → **this record** → lifecycle verbs → doctor/logs)
**Verdict:** BUILD — the record itself is the deliverable; it commits stop semantics BEFORE any command skeleton ships (the issue's review gate)
**Status:** design record — the stop-gate authority for increments 3 and 4
**Grounded on:** main @ `6806b6f7` (increment 1 merged); every code claim below was read at that tree

---

## 0. Premise corrections the code forced (read this first)

The issue and the dispatch brief describe a gateway with "no stop semantics". Reading
the tree corrects four load-bearing details — the increment 3 build is *thinner* than
the issue implies, and one part of the council's ladder *already exists* as in-process
behavior:

1. **The lifespan already owns recovery-before-serving, bounded drain, and hold
   release.** `src/benchweave/interfaces/app.py:1013-1060` (`_lifespan`): acquire
   `StoreHold` → `admit_startup_bench` + `_recover_interrupted_runs` → `worker.start()`
   → serve → on shutdown `worker.stop()` + `worker.join(timeout=5.0)` (a failed drain
   logs the CTL-9-honest line "outstanding runs are recorded interrupted at next
   startup") → `hold.release()`. Increment 3 does not build any of this; it builds the
   **supervision layer that decides WHEN this machinery may run and audits the rungs
   that bypass it**.
2. **A graceful-stop contract already exists implicitly — uvicorn's.** `serve`
   (src/benchweave/cli/commands.py, the `serve` body after the increment-1 autoload)
   ends with `uvicorn.run(app, ...)`. uvicorn installs SIGTERM/SIGINT handlers that
   trigger graceful shutdown: stop accepting, drain connections, run the lifespan
   shutdown above. So SIGTERM-to-idle-serve already drains and releases the hold
   today — CORRECTED (lane-1 F2 fold): true only while no connection outlives the
   drain. uvicorn waits for connections BEFORE the lifespan shutdown,
   `timeout_graceful_shutdown` defaults to None, and serve does not override it —
   a single open UI SSE stream (the Events view) hangs the shutdown forever
   today, and a second SIGTERM is a no-op. Increment 3 bounds it: serve passes an
   explicit `timeout_graceful_shutdown` (derived with the same discipline as
   `TimeoutStopSec`), the stop decision closes live SSE streams, and the
   plain-stop CLI's verdict-wait and exit-wait are BOUNDED (the idle bound = the
   join window plus the connection-close bound); L1 asserts the wall-time bound
   R9 names.
   What does NOT exist: refusal when a run is active (a SIGTERM mid-run waits at most
   the 5 s join, then abandons the run — nothing names it, nothing audits it), the
   protective routing, the escalation audit, and every pidfile/status affordance.
3. **The systemd unit template has no `ExecStop` — and no `KillSignal`/`TimeoutStopSec`
   either.** `deploy/systemd/benchweave.service.template`: `Type=simple`,
   `Restart=on-failure`, `RestartSec=2`, `ExecStart=/usr/bin/python3 -m benchweave
   serve`. Today `systemctl stop` relies on systemd's default ladder (SIGTERM →
   `TimeoutStopSec` 90 s → SIGKILL to the cgroup). The issue's "graceful ExecStop" is a
   template change increment 3 makes — obligation 9 (the `systemd` CI job's
   render-and-`systemd-analyze verify` rehearsal + the `{{`-absence test in
   `tests/cli/test_serve.py`) moves with it.
4. **`run_cancel` exists end-to-end but cannot cancel a QUEUED run.**
   `Operations.run_cancel` (`src/benchweave/interfaces/operations.py:752`) →
   `RunWorker.cancel` (`src/benchweave/interfaces/worker.py`) → forwards to the ACTIVE
   coordinator only; "a queued-but-unstarted or finished run has no coordinator; the
   request is dropped and the run's own lifecycle decides". `RunCoordinator.cancel`
   (`src/benchweave/control/coordinator.py:813`) honors the request "at the next
   monitor tick while the body is still dispatchable … Once the body has ended, the
   safe transition is already running under its own protective authority and the
   terminal outcome stands (§5: cancellation cannot suppress the transition)". The
   interface contract says the same in corpus words — `standards/interface/0.1.0/
   interface-contract.md:62`: run_cancel "requests body termination and protection, not
   reversal of device commands or immediate physical safety … independent/local
   protective mechanisms remain available without that caller." That last clause is the
   contract's own invitation for this record's local stop path.

One more disposition, ruled up front: **increment 3 changes ZERO bytes in
`control/protection.py` and zero bytes in the protective seam.** The protective stop
ROUTES the existing engine; it does not add a second way to enter protecting.

## 1. Root cause, traced

A session drop (laptop sleep, SSH cut) kills the `serve` process mid-procedure. What
happens today, step by step in the code:

- The OS releases the store's `flock` (`state/hold.py` module docstring; STO-3: "the
  lock itself — never the lockfile body — is the truth"; `fcntl.flock`/`msvcrt.locking`
  die with the process). So the store never stays falsely held — this part is sound.
- The run's durable row stays non-terminal. Nothing finalizes it until a NEXT boot's
  `_recover_interrupted_runs` (`interfaces/app.py:287`) sweeps: leases held by
  `run:{run_id}` (crashed between `create_run` and `finalize_run`), queued ghosts
  (issue #156's run-state-aware leg), and dangling §9 request keys
  (`Store.reconcile_dangling_requests`). Recovery constructs NO plugins — it never
  touches a device (`app.py` docstring) — so the interrupted record it writes carries
  `safe_state="unknown"`, honestly.
- Until that next boot: there is no pidfile (nothing to signal or probe), no answer to
  "is the hold held?" short of knowing `daemon_holds` exists, no restart-on-crash, and
  — the part this record owns — **no operator verb that stops the gateway without
  either abandoning an active run silently (SIGTERM + 5 s join) or hand-crafting a
  kill**. The bench may be left energized by the dead run's last dispatch, and the
  evidence trail says only "interrupted, unknown" at some later boot.

The supervision gap is therefore precise: the in-process machinery (recovery, drain,
hold, cancel seam, protective engine) exists and is pinned by `tests/faults/`; what is
missing is the **process-level protocol** — identity, doorbell, refusal, bounded
protective routing, audited escalation — between an operator (or a service manager) and
that machinery.

## 2. Supervision model

### 2.1 The lifecycle state machine

```
                 ┌──────────────────────────────────────────────────────┐
                 │ service manager (systemd/launchd) or `benchweave start│
                 └──────────────────────────────────────────────────────┘
                                          │ spawn (Type=simple / detached)
                                          ▼
    BOOT ── env-file autoload (inc1) ──► HOLD-ACQUIRE ──► RECONCILE ──► SERVING
    (cli parses)        (build)          StoreHold          admit_startup_bench
                                          flock              + _recover_interrupted_runs
                                          │ write pidfile          │ worker.start()
                                          ▼                        ▼
                                        FAIL ◄── refused boot   SERVING ◄────────────┐
                                        (non-zero exit;             │                │
                                         systemd start-limit        │ stop request   │
                                         contains the loop)         ▼                │
                                                              DRAIN-AND-STOP      │
                                                              cancel? → wait      │
                                                              terminal (bounded)  │
                                                              worker.stop+join    │
                                                              hold.release        │
                                                              remove pidfile      │
                                                              exit 0              │
                                                                   │              │
                                                  refused (run active) ────────────┘
                                                   verdict written, still SERVING

    KILLED (SIGKILL / crash / power) ── OS releases flock ──► sidecars remain
                                          next BOOT's RECONCILE finalizes interrupted
```

Transition ownership, exactly:

| Transition | Owner | Mechanism |
|---|---|---|
| spawn | CLI `start` (detached subprocess, `start_new_session=True`) OR service manager (`Type=simple`) | `subprocess.Popen` / `ExecStart` |
| env preparation | the Python process (inc1 autoload — already shipped) | `cli/env_file.py` |
| hold acquisition | the Python process (`_lifespan`) | `StoreHold.acquire()` — refuses naming holder |
| pidfile write | the Python process (lifespan startup, immediately after hold acquire) | sibling file, §2.3 |
| recovery-before-serving | the Python process (`_lifespan`, before `worker.start()` and before the first `yield`) | `_recover_interrupted_runs` — A06's gate lives HERE, not in any CLI verb |
| serving | the Python process (uvicorn + worker thread) | unchanged |
| graceful stop entry | CLI `stop` (doorbell) OR service manager (`ExecStop`/`KillSignal`) | §3 |
| drain, terminal waits, hold release, pidfile removal | the Python process (lifespan shutdown — already in-tree) | `_lifespan` finally-arms |
| SIGKILL last resort | CLI `stop --protective` ladder rung 3 (pidfile mode) OR systemd `TimeoutStopSec` | §3.5 |
| restart-on-crash, boot-time start | service manager ONLY (`Restart=on-failure`) | never the CLI |

**The division the council ruled, made concrete:** the Python process guarantees
recovery-before-serving, the one-writer hold, the bounded protective authority, honest
terminal records, and clean drain/release on every exit it controls. systemd/launchd
guarantee process identity (cgroups/labels), restart-on-crash within rate limits, boot
ordering, and the outer SIGKILL bound (`TimeoutStopSec`). Neither asks the other for
help it cannot give: the CLI never writes terminal records, and the service manager
never interprets run state.

A04 consequence, stated: because the reconciliation gate lives in the composition, a
`Restart=on-failure` revival — which has NO CLI body, no human, no agent — passes the
identical gate a hand-typed `start` does. Protection and completion do not depend on
continued AI judgement; they depend on `_lifespan` running, which depends on nothing
but the process starting.

### 2.2 What each guarantee rests on (and what it does NOT rest on)

- **One coordinator:** the flock (STO-3). `start`'s pre-spawn probe and `stop`'s
  identity checks are CONVENIENCES over this truth, never substitutes: any supervision
  verdict that disagrees with `daemon_holds` is a disclosed desync, not an override.
- **No restart loop on a refused boot:** a boot that cannot acquire the hold (or
  refuses on secret posture) exits non-zero; systemd's default start-rate limit
  (5 starts / 10 s) contains the resulting `Restart=on-failure` retries into the
  `failed` state. The unit does not add `StartLimit*` tuning in increment 3 (named
  deferral, §10) — the default containment is the honest posture and muninndb's
  dual-ownership race (their `lifecycle.go` pebble-lock comment) is prevented earlier,
  by `start`'s `daemon_holds` pre-check (§4.1) refusing to spawn at all.
- **Windows:** `fcntl`/signals differ. The doorbell protocol (§3.2) is
  platform-independent BY DESIGN — the file is the protocol; POSIX signals are a
  latency optimization on top. The Windows CI leg corroborates the file path (W1);
  the signal path is POSIX-only and named as such in every arm that exercises it.

### 2.3 The supervision file family (one derivation, four siblings)

All supervision state lives BESIDE the data directory, derived exactly the way
`hold_path` derives `<dir>.hold` (`state/hold.py::hold_path`): resolve the data dir,
then `<parent>/<name><suffix>`. The sibling placement is load-bearing for the same
reason it is for the hold: `restore` swaps the whole data directory with `os.replace`,
so a file INSIDE the dir can be swapped away from a live reference — a sibling cannot.
One shared helper (`hold_path` refactored to `sibling_path(db_path, suffix)` with
`hold_path` as a thin wrapper — single spelling, no behavior change to the hold) feeds
the whole family:

| File | Writer | Reader | Shape | Removed by |
|---|---|---|---|---|
| `<dir>.hold` | StoreHold (in-tree) | at-rest commands, `daemon_holds` | pid/label/acquired_at JSON (advisory body; the flock is the truth) | OS on process death (the file remains; the LOCK releases) |
| `<dir>.pid` | serve, at lifespan startup (after hold acquire) | `stop`, `status`, doctor | JSON §2.4 | serve at clean shutdown; `stop` after verified-stale |
| `<dir>.stop` | `stop` (request shape) → serve (verdict shape, atomic replace) | `stop` polls; doctor | JSON §3.3 | serve consumes/rewrites; `stop` clears when stale |
| `<dir>.log` | serve's stderr (fd inherited from `start`) | `logs` (inc4), operator | text | never auto-removed |
| `<dir>.supervision.jsonl` | the lifecycle VERBS (start/stop/restart/service) — never the daemon | `logs`/doctor (inc4), operator | append-only typed rows §3.5 | never auto-removed |

Mode 0600 on write, POSIX; Windows owner-restricted (the atrest precedent,
`cli/atrest.py` Windows ACL posture). None of these files ever carries a secret, a
token, or credential material (G0 discipline; pids, run ids, paths, timestamps, and
outcome words only) — obligation 11's drift row says so in prose when increment 3
lands.

Foreground `serve` and systemd `serve` write the pidfile and the `.stop` verdicts the
same way — the daemon does not know who spawned it. `start` additionally redirects the
child's stderr to `<dir>.log` (the muninndb `runStart` pattern: parent opens the log,
child inherits the fd, parent closes its copy) — **that file is THE named daemon log
destination** this record owes increment 4:

- under `start`: `<dir>.log` (sibling, append, 0600);
- under systemd: journald (the unit sets no `StandardError` → journal; `logs` reads
  `journalctl -u benchweave` — increment 4 implements or degrades loudly);
- foreground: the terminal (today's bytes).

**Increment 2's sentence, pinned:** *serve's stderr prose is not an interface.* Doctor
(increment 4), `logs`, and every future consumer re-derive state from inputs — pidfile,
hold state, store-at-rest, supervision rows — and never parse serve's stderr. The
stderr lines increment 1 added (`loaded <path> …`, the absent-file note) are
human-facing narration, nothing more.

### 2.4 Pidfile format + identity verification protocol

The pidfile is the SIGNALING HANDLE, never the truth (the hold is). JSON, written once
at lifespan startup:

```json
{"pid": 1234, "gateway_id": "gw-…", "data_dir": "/var/lib/benchweave",
 "started_wall": "2026-10-08T04:11:02Z", "started_ticks": 987654321,
 "log_destination": "journal|<path>|stderr", "schema": 1}
```

`started_ticks` is the OS process start time (Linux: `/proc/<pid>/stat` field 22;
macOS: `sysctl(KERN_PROC_PID).p_starttime`; Windows: process creation time via
`GetProcessTimes`, else absent). Identity verification — the discipline muninndb
lacks (their signal-0 probe reads a recycled pid as "running") — is a THREE-valued
verdict plus one cross-check:

1. **probe** (muninndb's `probeProcessNative` discipline, adopted): signal-0-equivalent
   liveness → running / dead / unknown (EPERM reads RUNNING; unresolvable reads
   UNKNOWN — "anything else is indeterminate and must not be read as absence").
2. **identity**: if running, compare the live process's start time to
   `started_ticks`. Match → OURS. Mismatch or unobtainable-and-pid-reuse-plausible →
   NOT-OURS (stale handle: the named process is not this gateway).
3. **cross-check vs the hold** (the truth), label-first (lane-1 F6 fold): when
   `daemon_holds(db)` is true, consult the holder's LABEL — a non-gateway label
   (`service-install`, `backup pid …`, `restore pid …`) means an at-rest command
   holds a store no daemon owns: the pidfile stands on probe alone and NO desync
   fires. A gateway-label holder whose pid disagrees with the pidfile pid is a typed
   desync (`supervision_hold_desync:`) — `stop` signals NOTHING
   and says both numbers. When the hold is free, a NOT-OURS pidfile is stale:
   sidecars may be cleared, nothing signaled.
   Verdict lattice, every cell defined (lane-1 F7 fold): identity MISMATCH (live
   process, different start time) ⇒ NOT-OURS; ticks unobtainable ⇒ the hold
   decides — hold free ⇒ UNKNOWN (refuse, name the file); hold held by a gateway
   label whose pid equals the pidfile pid ⇒ the hold vouches: signal (the hold is
   the truth); any other held shape ⇒ refuse. Zombies (probe and start-time both
   succeed on an unreaped child) read OURS; the signal no-ops and the CLI's
   bounded wait discloses it — low reach (init/systemd reap), disclosed.

Acting rule (the conservative direction everywhere): signal only on OURS (+hold
agreement when the hold is held). DEAD → clear sidecars, report "not running".
UNKNOWN or desync → refuse, name the file, tell the operator what to verify — the
muninndb `processUnknown` refusal discipline, quoted into our typed vocabulary
(`supervision_pid_unknown:`, `supervision_hold_desync:`). A second `start` while the
pidfile verifies OURS refuses `supervision_already_running:` naming the pid; while the
hold is held with NO pidfile it refuses naming the holder and pointing at the service
manager (muninndb's `readPID` hint posture) — that is the "systemd owns it" case.

## 3. Stop semantics — precise enough to implement from

### 3.1 What "idle" means

**Idle ⇔ zero runs in `LIVE_RUN_STATES`** (`src/benchweave/interfaces/operations.py:81`
— `frozenset({"accepted", "running", "protecting")}`), judged BY THE DAEMON over its
own live projection. The predicate is regenerable from a mechanism (that frozenset),
matches the §5 busy oracle, and errs safe: a held-but-queue-empty, no-active-run
gateway IS idle (the hold alone never blocks a stop — draining and releasing it is the
plain stop's whole job); a queued-but-unstarted run (`accepted`) is NOT idle —
abandoning it is an interruption, and the refusal says so. Pending scheduled
observations inside an active procedure are part of that run's monitored body — they
are covered by the run being live, not counted separately.
The predicate is TOCTOU-closed (lane-1 F4 fold): the stop decision FIRST sets a
stopping flag under the run-start write gate (the gate run_start already takes; a
start arriving after the flag refuses typed `stop_in_progress:`), THEN reads live
states — set-then-check, so a run accepted mid-decision can never be silently
abandoned under an `accepted` verdict; arm L13 pins the concurrent-start shape.

### 3.2 The doorbell protocol (request file + signal fast-path)

`stop` cannot read the store (single-writer discipline: at-rest commands refuse while
a live coordinator holds the store, and `stop` is not exempt), and it must work
without a token (systemd runs `ExecStop` as the service user with no secret). So the
stop channel is a FILE plus a signal, and the daemon is the sole authority:

1. `stop` writes `<dir>.stop` atomically (temp + `os.replace`, the atrest/restore
   precedent): `{"schema":1, "mode":"plain"|"protective", "requested_wall":"…",
   "actor_pid":N}`.
2. `stop` signals the verified-OURS pid — SIGTERM on POSIX. On Windows (or any
   platform without a deliverable graceful signal) the signal is SKIPPED: the daemon's
   poll (step 3) is the doorbell of record.
3. serve polls `<dir>.stop` at a bounded cadence (≤ 1 s; an asyncio task mounted in
   the lifespan — it exists only while serving) AND (POSIX) installs a SIGTERM handler
   inside the lifespan startup (after uvicorn installs its own, capturing uvicorn's
   handler for delegation — the handler-delegation contract in §3.4). Either
   trigger SCHEDULES the same decision — the signal handler (or poll task) only
   sets an event / creates an asyncio task; the decision and the protective wait
   run ON the loop, never inside the handler, so serving, the doorbell poll, and
   further signals stay live for the whole commissioned window (lane-1 F12 fold —
   the protective path run inside the handler would freeze the loop for the
   window). **Arming is serve-command-scoped (F4 fold):** the
   doorbell, pidfile write, and handler mount are armed ONLY when the process was
   launched as the serve command — the serve CLI sets an internal arm flag before
   `uvicorn.run`; the `demo` and `evidence` compositions boot the REAL lifespan
   (uvicorn in a thread, flock held: `run_simulation`, the evidence generators) and
   leave the flag unset, so they inherit NO supervision surface and their behavior
   is unchanged. Their stop story is specified, not silent: a hold held by a
   non-daemon holder (label `gw-cli-demo` / `gw-cli-evidence`) with no pidfile is a
   typed `stop` verdict naming the holder label, nothing signaled — §2.4's
   hold-held-no-pidfile case applies to `stop` exactly as to `start`.
4. Before consuming, the daemon verifies the request file's OWNER (POSIX `st_uid`;
   Windows: the owner SID) equals its own effective identity — a foreign-owned
   request is NOT consumed and is answered with a typed
   `supervision_stop_foreign_owner:` verdict naming the file's owner (F3 fold: the
   poll-only doorbell is cross-uid reachable when the data dir's PARENT is writable
   by another uid, and a different-uid process cannot signal at all; ownership
   closes the forged-protective-stop hole in one check).
5. The daemon consumes the request by atomically rewriting the file into a VERDICT
   (§3.3) and acting on it. Consumption-by-rewrite makes the protocol single-shot:
   two concurrent `stop`s — the file records whichever request landed last; the
   daemon acts on the mode it consumed; a CLI whose mode disagrees with the consumed
   verdict learns that from the verdict shape (typed note, no second action). The
   consume (and the CLI's request write, step 1) RETRIES on `os.replace` failure at
   the poll cadence, bounded by the request deadline — Windows opens files without
   FILE_SHARE_DELETE and a replace onto the CLI's open read handle can fail
   transiently (F6 fold).

This is deliberately NOT a new network surface (no unauthenticated HTTP endpoint, no
token-less REST route), NOT stderr parsing (§2.3's pinned sentence), and NOT
store-reading while held. Local same-uid hostility is out of scope by posture, and
the honest argument for that is the credential file: a same-uid writer already reads
`<data-dir>/benchweave.env` (0600, the operator's own uid) and thus holds the tokened
REST surface including run_cancel — the doorbell grants nothing beyond what the uid
already has. Cross-uid writers are closed by the ownership check (step 4), not by
signal-equivalence (F3 fold, rewording R5's original false justification).

### 3.3 The three stop paths

**Plain stop, idle:** daemon rewrites the request to
`{"status":"accepted","mode":"plain",…}` and delegates to the captured uvicorn
shutdown handler → the in-tree lifespan drain (worker `stop`+`join(5.0)`, hold
release, pidfile removal) → exit 0. `stop` observes process exit, verifies
`daemon_holds` false, appends the supervision row, exits 0.

**Plain stop, run active (the refusal):** daemon rewrites the file to
`{"status":"refused","reason":"run_active","run_ids":["run-…"],"states":
{"run-…":"running"},…}` — the typed refusal `stop_refused_run_active:` naming the
run(s), source = the daemon's live projection (`LIVE_RUN_STATES` rows; run identity =
the durable run ids the seam already mints). It does NOT begin shutdown; serving
continues untouched. The CLI polls the verdict (bounded, §3.5), prints the typed
refusal, appends its supervision row, exits non-zero. The run is never lied about:
nothing was stopped, nothing was recorded, the bench is exactly as it was.

**`stop --protective` (any live state):** the daemon routes the approved safe
transition THROUGH the existing seams — there is no second way to enter protecting:

1. Rewrite the request to
   `{"status":"accepted","mode":"protective","protective_deadline_wall":"…","run_ids":["…"],…}`
   where the deadline is computed from the commissioned documents in the store —
   the same arithmetic family CTL-10/STO-4 pin for the run window
   (`acceptance + max_body_ms + max_protection_ms`, values from the run's
   binding/commissioning documents, never ambient guesses). The run_ids field is
   REQUIRED in the accepted shape (lane-1 F8 fold: the SIGKILL rung's audit row
   cites the last verdict's run ids — without them here, rung 3 logs empty by
   construction). The verdict STATES the deadline it acts under;
   the CLI waits to that plus a margin (the numeric authority stays in the daemon —
   A02: commissioned values, not CLI constants).
2. For the ACTIVE (`running`/`protecting`) run: call the coordinator cancel path —
   the SAME `RunWorker.cancel` → `RunCoordinator.cancel` forwarding the REST seam
   uses, invoked in-process. Honored at the next monitor tick while dispatchable; a
   run already in `protecting` is simply waited on (its transition is already running
   under its own fixed budget — CTL-1: never restarted, never extended). The body ends
   `cancelled`; the coordinator then runs the protective transition and writes the
   terminal record, exactly as every body end does (A12). No rung of this ladder ever
   writes or rewrites a terminal record, and none is an outcome authority: rung 2
   QUOTES the coordinator's terminal record verbatim into its verdict (source named)
   for the CLI to journal (F1/F2 fold). The in-process cancel carries principal
   `gateway-supervision` with a typed reason riding run_changed, so the store can
   distinguish an operator REST cancel from a protective-stop cancel (F15 fold).
3. For QUEUED (`accepted`, never-started) runs — the ORDERING here is load-bearing
   (lane-1 F1 fold: the worker's `queue.get` returns already-queued jobs regardless
   of its stopping flag, so the microsecond the active run finishes, the worker
   picks up the next queued run and starts dispatching — a sweep running then would
   finalize `interrupted` a run a live coordinator is dispatching, and the
   coordinator would write a SECOND terminal record over it: the exact CTL-9
   corruption this record exists to prevent): FIRST the worker enters a
   don't-pick-up mode (an inc3 mechanism this record hereby REQUIRES: a pickup gate
   that stops dequeuing new jobs while letting the active job finish), THEN cancel
   and wait the active run terminal, THEN confirm the queue is EMPTY under the
   gate, and only THEN run the sweep — scoped to the #156 queued-ghost leg
   (`interrupted`/`unknown`, occurrence ledger rebuilt from events, zero dispatches
   so zero identities) with the era reason reading `gateway stop: run was never
   started`. The sweep's `reclaim_orphans` and `reconcile_dangling_requests` legs
   are SKIPPED at stop time — their predicates assume a dead host and can race
   in-flight staging requests (lane-1 F13 fold), disclosed here. Reusing the
   recovery record shape (not
   inventing a "skipped" outcome) keeps CTL-9's vocabulary closed: a never-started
   run's honest outcome is `interrupted`. If the in-process sweep SKIPS (lattice
   admission fails — the recovery_skipped branch), the protective verdict and the
   exit both disclose "N queued runs left for next-boot recovery" rather than
   exiting 0 over silent `accepted` rows (F10 fold).
4. Drain, release, remove pidfile, exit 0. Supervision rows carry the story
   (cancel-requested, terminal-observed with its outcome word, exited).

**If the transition itself fails or times out mid-flight:** the ProtectionEngine's own
budget already bounds it (`protection.py`: deadline fixed at first entry, actions
capped at `min(action timeout, remaining)`, verification polls to continuous
stability or yields `unknown`). The terminal record lands with `safe_state:"unknown"`
— honest, never `verified` — and the stop proceeds to drain and exit. A terminal
record that never lands (wedged writer past the deadline) escalates: §3.5 rung 3.

### 3.4 The SIGTERM handler's contract (what the unit's ExecStop relies on)

POSIX: within the lifespan startup, serve captures uvicorn's installed SIGTERM handler
and installs its own that runs the decision code: request file present → act on its
mode; bare SIGTERM (no request file — systemd's `KillSignal`, an operator's
`kill $PID`) → the same three-way decision on live state: idle → trigger the
graceful shutdown DIRECTLY — set the captured server's `should_exit = True`; do
NOT re-raise into uvicorn's captured-signal replay (uvicorn 0.52.4 restores the
pre-uvicorn handlers at context exit and re-raises the captured SIGTERM, ending
the process by signal 15 AFTER a clean drain — failing L4's exit 0; lane-1 F3
fold);
run active → REFUSE (log one typed line, keep serving; systemd then waits
`TimeoutStopSec` and SIGKILLs — see §3.6). The contract ExecStop depends on:
*bare SIGTERM on an idle gateway produces the in-tree graceful drain and a clean
exit 0; on a busy gateway it produces a refusal, never a silent abandon.* SIGINT
(Ctrl-C, foreground) keeps uvicorn's behavior untouched — the foreground operator's
interrupt is today's behavior, and this record does not change the terminal session's
stop story (the daemonization fix is `start`, not a foreground signal redesign).
SIGHUP is UNHANDLED by design (uvicorn installs no handler; the default disposition
terminates without drain — reachable for foreground serve on a closing terminal):
it lands in the KILLED class, and `start`'s detached session and systemd both
remove the exposure (lane-1 F11 fold).

### 3.5 The escalation ladder, with each rung's audit event (A07)

| Rung | Actor | Trigger | Bound | Audit event (supervision.jsonl row) | Run record |
|---|---|---|---|---|---|
| 1. SIGTERM | `stop` / systemd | always first | daemon verdict cadence ≤1 s; CLI waits for verdict/exit (bounded by the accepted verdict's own deadline) | `stop_requested` {mode, target_pid, signal: "SIGTERM"\|"file-poll-only"} — the row records the REQUEST; on Windows the signal leg is skipped and the row must not assert a signal that was not sent (F12 fold) | none written by any rung — ever |
| 2. protective deadline | daemon (mode=protective) — the daemon writes these as VERDICT-file fields (§3.3); the CLI is the SOLE journal writer, copying them into `.supervision.jsonl` on observation (F2 fold: one writer per file; no cross-process JSONL append, which Windows does not guarantee) | cancel + wait-terminal | commissioned window (verdict-stated) | verdict fields `protective_cancel` {run_ids} and `terminal_observed` {run_id, outcome, safe_state, source: "coordinator_terminal_record"} — the observation QUOTES the coordinator's terminal record verbatim with its source named; it is an observation, not an outcome authority (F1 fold) | the COORDINATOR's own §5 record (`cancelled`/body-end + transition truth) |
| 2b. refusal | daemon (plain) | run active | immediate | verdict `run_active` + CLI row `refusal_observed` {run_ids} | none — the run continues |
| 3. SIGKILL | CLI (`stop --protective` only) or systemd | protective deadline passed with NO terminal record | one kill, then bounded exit-wait | `sigkill_sent` {target_pid, run_ids_from_last_verdict, reason:"protective_deadline_exceeded"} — the CLI cannot read the store (§3.2), so the row's run ids are the LAST VERDICT's ids (the daemon's own projection), or `[]` with a `run_ids_source:"unknown"` marker when no verdict was ever observed | NONE by the rung — the run stays non-terminal; the NEXT boot's sweep records `interrupted` (the honest outcome; `safe_state:"unknown"`) |

The guarantee, stated as the review gate will enforce it: **no rung manufactures a
completion.** Rungs write supervision rows (decisions and observations) and signals —
never terminal records, and no rung MINTS outcome words for runs: rung 2 quotes the
coordinator's own outcome verbatim with its source named, which is an observation,
not an authority (F1 fold). The only writers of terminal
records remain the coordinator (live §5 endings) and the recovery sweep (interrupted).
SIGKILL under `stop --protective` exits NON-ZERO disclosing the kill; under systemd,
SIGKILL is the manager's `TimeoutStopSec` behavior and the journal plus the next
sweep carry the evidence. A07 is honored in both directions: the audit never blocks
the protective action (evidence storage is not a dependency of protection), and the
audit row is written even for the rung that bypasses everything else.

**Durability, enumerated (F9 fold — which rows are guarantees and which are
best-effort):** DURABLE (the CLI's journal rows — written by the only journal
writer, before its own exit) · BEST-EFFORT (the verdict-file fields the CLI copies —
the daemon's verdict rewrite is atomic but unjournaled until a CLI observes it) ·
PLANNED (rung 3 writes its intent row BEFORE the kill, proceed-on-failure, with the
non-zero exit disclosing a failed append). Stated plainly: on the non-systemd leg a
failed rung-3 append leaves no secondary machine-readable record (there is no
journal under `start`-spawned daemons whose stderr goes to `<dir>.log`, which §2.3
pins as not-an-interface); the pre-kill intent row is the ordering that makes the
strongest action not have the weakest evidence. Rung 1 on non-CLI paths (operator
`kill $PID`, systemd KillSignal) has NO journal writer and therefore NO row — the
daemon's verdict file and the OS's own evidence carry those events.

### 3.6 Division under systemd (the no-human paths)

- `systemctl stop` → `ExecStop=benchweave stop …` (plain): idle → graceful exit.
  Run active → ExecStop exits non-zero with the typed refusal (visible in
  `systemctl status`), systemd then applies its own SIGTERM (refused again, logged)
  → `TimeoutStopSec` → SIGKILL → the run finalizes `interrupted` at the next boot.
  A stop JOB suppresses `Restart=on-failure` (the manager's guarantee) — no
  stop-restart ping-pong.
- `TimeoutStopSec` is DERIVED AT INSTALL (`service install`, §4.3) from the
  commissioned protective ceilings (max over the store's commissioned
  `safe_transition.max_duration_ms` + 30 s margin) so the unit can never cut a
  commissioned transition's legs out from under it; with no commissioned value in the
  store, the unit renders systemd's default with a disclosed comment (there is no
  protective envelope to respect — A02 read honestly: the number protects a
  commissioned budget when one exists; it is not itself a bench limit).
- Crash (`SIGSEGV`, OOM-kill) → `Restart=on-failure` after `RestartSec=2` → the new
  process acquires the free flock (the old one died with its process — STO-3) and its
  lifespan RECONCILES before serving (§2.1). An in-flight transition killed by the
  crash does not resume — its run sweeps to `interrupted`/`unknown` (A04: "Trips and
  gateway restarts do not automatically resume or re-arm runs").

## 4. Start-time reconciliation gate (A06) + `start` + `service install`

### 4.1 `start` (detached, quick-bench surface)

Pre-spawn gates, in order, each a typed refusal: (1) pidfile verifies OURS →
`supervision_already_running:`; (2) `daemon_holds(db)` true → refusal naming the
holder (holder_info) and pointing at systemctl if a unit is stat-able — this is the
dual-ownership guard that prevents the systemd restart-race muninndb's comment
warns about; (3) the inc1 store-exists guard already lives in serve's locator
(`commands.py` serve: the named-locator boot refuses a data-dir with no
`state.sqlite`). Then: `subprocess.Popen([sys.executable, "-m", "benchweave",
"serve", …], start_new_session=True, stdout=devnull, stderr=<dir>.log)`,
env carried from the operator's invocation (the inc1 locator/autoload story needs no
change — the child re-derives from `--data-dir`). `start` then waits (bounded, 30 s)
for readiness = **the pidfile appears and names the child pid** — named honestly:
this is HOLD-ACQUIRED readiness, not serving readiness (the pidfile lands before
admission completes). During the window `start` polls the child's liveness
(`proc.poll()`, the live-leg precedent in tests/cli/test_serve.py): a child dying
before or after the pidfile → non-zero with the log tail hint, never a hung window
and never an exit-0-over-a-dead-daemon (F8 fold; a boot failing admission after the
pidfile — poisoned lattice — surfaces through the same liveness poll). Readiness
reporting re-checks liveness at END-of-wait before exit 0 (lane-1 F5 fold: a boot
refusing admission seconds after the window would otherwise leave start's success
message over a dead child; the stale pidfile such a boot leaves behind is stop's
stale-path business, disclosed). No new HTTP
surface; no daemonizing-interpreter
tricks: the child is the same foreground-capable `serve`, merely parented by init.

`start` does NOT re-implement reconciliation: the boot sweep inside the child's
lifespan IS the gate. What "refuses new energising actions until interrupted runs
recover" concretely means: `_recover_interrupted_runs` runs inside the lifespan
BEFORE `worker.start()` and before the first `yield` — the seam cannot accept a run
before the sweep has finalized every recoverable run and released every stale lease
(A06's "recovery reconciles before dependent actions proceed", already in-tree and
pinned; increment 3's arm L7 pins the ORDERING, which is the part no test currently
names against the supervision surface).

### 4.2 The boot-time variant (Restart=on-failure)

Identical by construction — §2.1's table. The record's claim increment 3 must leave
true: nothing in the lifecycle verbs becomes a precondition for correct recovery.

### 4.3 `service install` (and the template change)

Writes the systemd unit (and the launchd plist analogue on macOS — same rendered
directives mapped to `KeepAlive`/`RunAtLoad` semantics, divergence tabled in §5 for
what launchd cannot express). The rendered unit carries today's nine hardening
directives plus: `ExecStop=` (plain `benchweave stop`, §3.6), the derived
`TimeoutStopSec` (§3.6), `Restart=on-failure`, `RestartSec=2` — i.e. the TEMPLATE
gains `ExecStop`/`TimeoutStopSec` placeholders and the CI rehearsal (obligation 9:
the `systemd` job's render + `systemd-analyze verify`, and the `{{`-absence test)
extends to the generated unit. `service install` itself runs at-rest: it takes the
StoreHold (label `service-install`), reads the commissioned ceilings, renders, and
REFUSES while a live gateway holds the store (install-time is stopped-time).
launchd's lack of an ExecStop analogue is named in the unit's rendered comments:
under launchd the doorbell path IS the stop path (`benchweave stop` directly; the
manager's own kill is `launchctl remove`).

## 5. Serve-surface declaration — one standard, per-surface application

The adopted pattern is ONE standard across both CLIs. The gateway daemon is the
supervised surface (it owns procedures and the protective transition). The standard's
affordances, applied:

| Affordance | Gateway daemon (`benchweave serve` under start/systemd/foreground) | Gateway at-rest commands (`report`/`retention`/`dispose`/`backup`/`restore`/`verify`/`setup`) | SDK surface (`benchweave_sdk_server serve`) |
|---|---|---|---|
| `start` | **Granted** (inc3): detached spawn, §4.1 gates | **Refused** — at-rest commands are one-shot; there is nothing to supervise (reason recorded: they already self-terminate). `demo`/`evidence` are ALSO unsupervised (F4 fold): real lifespan holders, doorbell unarmed by the arm flag, stop-on-their-hold is the typed holder-label verdict | **Granted** (inc3): same pattern, twin implementation — with the token-delivery file (F5 fold): SDK serve prints per-launch bearer tokens to stdout, so started-mode spawns write them to a 0600 `<bindings>.tokens` sibling (the serial transport's `_deliver_operator_action_token` precedent) instead of destroying them in devnull or leaking them into `<dir>.log`; that file is the ONE documented credential-carrying exception to §2.3's no-secrets sentence, and `logs` never displays it |
| `stop` (plain) | **Granted** (inc3): §3.3 — idle drains+releases; active refuses typed | **Refused** — not a supervised process | **Granted** (inc3): pidfile + SIGTERM/doorbell + bounded wait; NO refusal machinery |
| `stop --protective` | **Granted** (inc3): §3.3 routing | n/a (refused with the surface) | **Refused — reason recorded**: the SDK serve has no procedures, no store, no commissioned safe transition; there is nothing for a protective ending to route. The flag does not exist on that CLI |
| Escalation to SIGKILL | **Granted** (inc3): §3.5 rung 3, audited | n/a | **Granted** (inc3): wedge-only ladder (rung 1 + rung 3; no rung 2 by construction), audited in its own supervision file |
| `restart` | **Granted** (inc3): stop-then-start, refusal propagates | Refused | **Granted** (inc3) |
| `status` (lifecycle) | **Granted** (inc3): pid identity verdict + hold verdict + holder + log destination (+ unit presence, inc4 doctor deepens) | n/a (their own output is their status) | **Granted** (inc3): twin |
| Pidfile + identity verification | **Granted** (inc3): §2.4 | n/a | **Granted** (inc3): twin format, its own sibling file |
| Start-time reconciliation gate | **In-tree already** (lifespan); inc3 pins the ordering | n/a | **Not applicable — reason recorded**: no store, no runs, nothing to reconcile (the gate degrades to "process starts and serves") |
| `service install` | **Granted** (inc3): §4.3 | n/a | **Refused — reason recorded**: a plugin-author preview server is not a boot daemon; no commissioned policy, no procedures; an operator who wants it supervised writes their own unit (documented) |
| Supervision JSONL | **Granted** (inc3): `<dir>.supervision.jsonl` | n/a | **Granted** (inc3): twin file beside its bindings dir |
| env-file autoload | **Shipped** (inc1) | n/a (their own flags) | **Shipped** (inc1, `--env-file`) |
| `doctor` / `logs` | **Deferred to increment 4** (named) | deferred | **Deferred to increment 4** (named) |

**Divergences from the one standard, each with its recorded reason:** (1) the SDK
stop has no refusal and no `--protective` — nothing is ever at stake (no runs); its
ladder is SIGTERM → bounded wait → SIGKILL, audit rows identical in shape.
(2) The SDK has no reconciliation gate — no store. (3) The SDK refuses `service
install` — preview surface, not a daemon. (4) launchd cannot express `ExecStop` /
`Restart=on-failure` semantics exactly — the rendered plist carries the mapping and
its limits in comments. Everything else is byte-identical doctrine (twin literal
tests, the CON-14 twin-repo pattern).

## 6. Invariant walk

- **CTL-1/2/3 (protective deadline, budget, safe-action authority): UNTOUCHED, newly
  load-bearing.** Zero bytes move in `control/protection.py`. `stop --protective`
  routes the engine; the ladder's rung-2 bound IS the engine's fixed budget. The
  record's §3.3 step 2 is the citation.
- **CTL-8 (cancellation window): UNTOUCHED.** The protective stop uses the existing
  cancel seam and its window semantics verbatim; a run past dispatchability is waited
  on, not forced.
- **CTL-9 (one coordinator owns the run; interrupted never fabricated): EXTENDED by
  amendment.** New clause: the supervision ladder never writes terminal records —
  only the coordinator's §5 ending or the recovery sweep do; a PLAIN stop with any
  live run refuses typed naming the run. Anchored on the new supervision module +
  §3.5. (F1 fold: "PLAIN" — same correction as CTL-11.)
- **CTL-10 / STO-4 (commissioned window arithmetic): UNTOUCHED, re-cited.** The
  protective wait bound and the install-time `TimeoutStopSec` derive from the same
  commissioned values (A02).
- **STO-1/2 (single-writer store, sequences): UNTOUCHED.** No lifecycle verb writes
  the store — the supervision JSONL is a sidecar, not a store table (deliberate:
  store writes from a non-coordinator process would violate STO-3's writer rule).
- **STO-3 (one coordinator per store, flock is the truth): EXTENDED by amendment.**
  New clauses: the supervision file family derives from the SAME resolved-sibling
  rule as `hold_path`; `stop`/`status` treat `daemon_holds` as the truth and the
  pidfile as the signaling handle; a pid/hold disagreement is a typed desync, never
  an override. The sibling-name collision class (a data dir X beside a directory
  named X.pid/X.stop/X.log refuses the boot with EISDIR after hold acquire — the
  preexisting X.hold shape, surface ×4 with the family) is named here, not
  discovered later (F13 fold).
- **STO-5/6 (dispositions): UNTOUCHED.**
- **CON-1..15: UNTOUCHED.** No transport, contract, corpus, manifest, or schema
  bytes. The stop path adds NO REST/MCP operation (the run_cancel seam already
  exists for remote callers; the local stop path is deliberately not a transport).
  The standards tripwire stays green.
- **REG-1..5b: UNTOUCHED.**
- **A04: newly load-bearing in three places** — reconciliation in-composition (§4.2),
  the protective route being commissioned policy rather than judgement (§3.3), and
  restarts never resuming runs (§3.6, quoted).
- **A06: newly load-bearing** — the boot sweep precedes serving; the ladder's
  SIGKILL rung leaves the honest ambiguity (`interrupted`/`unknown`) for the next
  reconciliation instead of guessing an outcome.
- **A07: newly load-bearing** — §3.5's audit rows; evidence storage is never a
  dependency of the protective action (the refusal and the transition proceed
  regardless of the JSONL append's fate — the row is best-effort at the rung that
  must not be blocked, and the DISCLOSURE is that a failed append leaves the journal
  as the secondary record).
- **New invariant proposed (CTL-11, lands with inc3's diff):** *the supervision
  ladder is outcome-blind by construction — no rung writes or rewrites a terminal
  record and none is an outcome authority (rung 2 quotes the coordinator's record
  verbatim, source named); a PLAIN stop over a live run is a typed refusal naming
  the run; the pidfile is a
  signaling handle whose verdicts yield to the store hold, never override it.*
  Testable by §7's arms L2/L5/L6/L9. (F1 fold: "PLAIN" and the quote-not-authority
  clause — the unqualified sentence condemned the record's own §3.3 protective path.)

## 7. Pre-committed acceptance rule for increment 3

Written BEFORE any increment-3 code exists. Counts read from `--junitxml` attributes
or exit codes, never an output-filter summary (the rtk rule). Every arm below names
its expected TYPED outcome; the RED control is named once and applies per bank.

**Gateway arms** (new `tests/cli/test_lifecycle.py` + fault arms in
`tests/faults/test_lifecycle_faults.py`, real-subprocess pattern from
`tests/cli/test_serve.py`'s live leg and `tests/faults/_kill_child.py`):

| # | Arm | Expected typed outcome |
|---|---|---|
| L1 | idle stop: real serve subprocess holds a set-up store, no live runs → `benchweave stop` | exit 0; verdict `accepted`; process exited; `daemon_holds` false; pidfile gone; supervision rows `sigterm_sent`+`stopped`; hold released |
| L2 | active refusal: live run in body (sim fixtures) → plain `stop` | verdict `refused`/`run_active`; typed `stop_refused_run_active:` naming the run id; process STILL serving (a follow-up read succeeds); run continues to its own terminal |
| L3 | protective: live run → `stop --protective` | run terminal `cancelled` with the transition's safe_state; verdict `accepted`+deadline; exit 0; hold released; rows `protective_cancel`+`terminal_observed` |
| L4 | bare SIGTERM on idle serve (no request file) — the ExecStop contract | graceful lifespan drain; exit 0; hold released; NO "did not drain" log line |
| L5 | SIGKILL rung: protective with fault-injected wedged terminalization (stall `finalize_run` in the test daemon) | after the verdict-stated deadline: one SIGKILL; supervision row `sigkill_sent` with reason `protective_deadline_exceeded`; run left NON-terminal in the store; `stop` exits non-zero disclosing the kill |
| L6 | stale pid: (a) pidfile names a dead pid (write the pid of an exited child); (b) identity mismatch — pidfile names a pid that is ALIVE but whose recorded start time differs (write a live unrelated child's pid + a MISMATCHED ticks value — writing the child's own start time would match and signal; lane-1 F9 fold); (c) pid alive, `started_ticks` unobtainable on the platform, hold free | (a) `not running (cleared stale sidecars)` + rows; (b) NOT-OURS verdict, NOTHING signaled, typed `supervision_stale_pid:`; (c) UNKNOWN verdict, nothing signaled, typed `supervision_pid_unknown:` |
| L7 | reconciliation ordering (A06): store carrying a non-terminal run → boot → the sweep's `interrupted` records exist BEFORE the seam accepts any run (ordering-intercept arm over the real composition) | ordering assertion holds; a run_start arriving at readiness sees the recovered terminal state |
| L8 | boot recovery, no human: SIGKILL a serving gateway mid-run → restart via `start` | new pidfile names the new pid; the run finalizes `interrupted`/`unknown`; gateway serves; old sidecars replaced |
| L9 | hold desync: pidfile pid ≠ holder pid (hand-written sidecar) | typed `supervision_hold_desync:` naming both; nothing signaled |
| L10 | `service install` render: commissioned store → unit bytes | `ExecStop` present; `TimeoutStopSec` = commissioned max + 30 s; `systemd-analyze verify` green in the CI rehearsal (obligation 9 extension); uncommissioned store → default with the disclosed comment |
| L11 | two concurrent stops, one plain one protective, against one busy gateway (the R7 promised arm, F7 fold — named so it cannot be quietly dropped) | exactly ONE action occurs (the consumed mode); both CLIs exit with truthful reports (the loser observes the mode mismatch as a typed note) |
| L12 | foreign-owned request file: write `<dir>.stop` and chown it to a nonexistent uid (test-side `os.chown`) | typed `supervision_stop_foreign_owner:` verdict; the request is NOT consumed; the run is untouched (F3 fold's machine check) |
| L3b | active + queued: run A live, run B accepted → `stop --protective` (lane-1 F1's arm) | B never dispatches (the pickup gate held); B finalizes `interrupted` via the scoped sweep; exactly ONE writer ever terminalizes each run; A ends `cancelled` with its transition truth |
| L13 | run_start concurrent with an idle plain stop (lane-1 F4's arm: the start's body in flight as the stop decision reads live states) | the start refuses typed `stop_in_progress:` (set-then-check under the write gate); NO run is abandoned under an accepted verdict |

**SDK arms** (`tests/server/test_lifecycle.py`): S1 start/stop/status happy path
(pidfile verifies, log file written, exit 0) · S2 wedge → bounded wait → SIGKILL row ·
S3 `--protective` is ABSENT from the CLI surface (help enumeration arm — the
divergence is pinned, not assumed).

**RED control (the fluff-proof part):** neutralize at ONE site each — (a) the
doorbell wiring (bypass the request-file/poll mount in the lifespan): L1, L2, L3, S1
must FAIL; (b) the identity comparison (skip the start-time check): L6(b) must FAIL
(it would signal); (c) the recovery-ordering mount: L7 must FAIL; (d) the kill rung
(never send SIGKILL): L5 must FAIL (it would hang or exit clean-lie). Restored, all
pass.

**SHIP =** all 14 gateway arms (L1-L13 + L3b) + 3 SDK arms green with typed outcomes as tabled, all
four RED controls red-then-green, fast lane + full battery green both repos (where
the SDK twin lands), the systemd rehearsal extended and green. L8's determinism is
specified, not hoped (F14 fold): the arm observes LIVE state before its SIGKILL
(sim body length sized so the run is verifiably in-body under CI load), and a
SECOND consecutive flake on the same arm is a KILL, not another re-run. **KILL =** any arm
failing after one fluke re-run; or any control staying green while neutralized (the
arm tests nothing — redesign the arm, do not merge); or L2's refusal ever
accompanied by a terminal-record write (a manufactured outcome — kill on sight).
**UNDERPOWERED =** a real-subprocess arm cannot run in a lane's sandbox (no
signalable processes): that arm rides the POSIX CI leg only, the rule degrades by
exactly that arm with the degradation disclosed on the PR — never silently dropped;
L7's in-process variant (composition-level ordering assert) substitutes if the
end-to-end shape cannot run at all.

## 8. Review tier + Step-1 keyword scan (#254)

**Increment 3 (the implementer): Tier 3.** Triggers, measured against the expected
diff: the keyword rule fires multiple times (`subprocess` in the spawn + tests;
`recovery` in the reconciliation prose/tests; `protection`/`protective` throughout;
likely `threading` if worker.py is touched) AND `tests/faults/` additions ride the
Tier-3 G2 clause. Two-lane adversary mandatory (2026-09-24 retro R3 standing rule).
**This increment 2 PR (docs-only): Tier 3 by the keyword-rule interplay clause** — a
docs-only diff whose text carries protective-behavior words takes the deep lane; the
adversary lanes here review THE RECORD itself, which is the point of a stop-gate
authority.

Keyword legend (numbered so this table does not perturb its own counts):
1=`threading` 2=`asyncio` 3=`subprocess` 4=`sha256` 5=`hashlib` 6=`migrate`
7=`recovery` 8=`protection`.

Scan result, MEASURED over this record at design time
(`grep -oiw <kw> <record> | wc -l`, the legend's one occurrence per keyword
excluded): 1: 1 · 2: 1 · 3: 7 · 4: 0 · 5: 0 · 6: 0 · 7: 16 · 8: 7.
(F11 fold, disclosure: the pre-fold draft's count for keyword 7 did not reproduce
under the stated method — 17, not 16. FINAL MEASURE at commit time, post both
fold waves: 1: 1 · 2: 2 · 3: 7 · 4: 0 · 5: 0 · 6: 0 · 7: 17 · 8: 7 —
first-match-wins fires on keyword 3, Tier 3 unchanged. Increment 3's build
record re-measures and states its OWN scan over its real diff, which is the number
that gates.)
First-match-wins: keyword 3 fires → Tier 3 (keywords 7 and 8 fire too). Expected
increment-3 code diff: all of 3/7/8 present (spawn, reconciliation, protective) plus
1 if worker.py moves; the counts are re-measured by increment 3's own build record
over its real diff — that record states its own scan, per #254.

## 9. Top risks, each with its falsifier

- **R1 Stop-vs-protective-transition deadlock** (the drain waits on a transition
  that waits on a device that never verifies). Bounded by the commissioned window —
  the verdict states its deadline; past it, rung 3. Falsifier: L5 (must SIGKILL, not
  hang; a hanging L5 is a KILL).
- **R2 Hold release on SIGKILL — who releases the flock when the process died?**
  The OS does (`hold.py`'s design premise; STO-3; pinned by
  `test_stale_marker_reads_free`). The SIDEcars (pid/log/supervision) legitimately
  remain — clearing them is `stop`'s stale-path job, never the dead process's.
  Falsifier: L5 + L8.
- **R3 Service-manager restart racing an in-flight transition.** The flock died with
  the old process; the new lifespan reconciles under the new hold before serving; a
  killed transition never resumes (A04). Falsifier: L8.
- **R4 Pid reuse.** Start-time identity + the hold cross-check; a recycled pid reads
  NOT-OURS, nothing is signaled. Falsifier: L6(b), L9.
- **R5 Request-file spoofing (a local process writes a stop/protective request).**
  The file grants nothing the same uid could not do with `kill` anyway; loopback
  single-operator posture; disclosed, not mitigated. Falsifier: none in-tree — the
  posture note IS the disposition (an adversary lane is invited to disagree).
- **R6 Windows signal semantics.** The file poll is the doorbell of record; signals
  are a POSIX optimization; W1 CI-corroborated on the Windows leg. Falsifier: S1/L1
  equivalents green on the Windows CI leg (the poll path), with the signal-path arms
  POSIX-scoped and disclosed.
- **R7 Two concurrent stops / mode conflict.** Atomic request write + consume-by-
  rewrite: one request wins, the verdict names the mode acted on, the losing CLI
  observes the mismatch as a typed note. Falsifier: a dedicated concurrency arm in
  increment 3's bank (named here so it cannot be quietly dropped): two stops, one
  plain one protective, against one busy gateway — exactly one action, both CLIs
  exit with truthful reports.
- **R8 `TimeoutStopSec` undercutting a commissioned transition under systemd.**
  Derived at install from the commissioned ceilings. Falsifier: L10's derivation
  arm + the rendered-comment fallback arm.
- **R9 The drain bound regresses** (someone re-bounds `worker.join` to unbounded,
  hanging every stop). The join bound stays 5 s for the PLAIN drain; the protective
  wait is the only long wait and is deadline-stated. Falsifier: L1's wall-time
  bound.

## 10. What this increment (2) ships — and DEFERS

Ships: THIS RECORD, committed on a branch as a design-only PR referencing #422
(single issue stream; no SDK-side motion — the SDK rows of §5 are doctrine this
record commits, not bytes any SDK PR carries). Nothing else. No code, no template
bytes, no docs-tree motion beyond this file.

DEFERRED, each named to its owner: the entire increment 3 implementation (lifecycle
verbs, supervision module, template ExecStop/TimeoutStopSec, twin SDK surface,
invariant CTL-11 + the STO-3/CTL-9 amendments as inc3 diff riders) · doctor + logs
(increment 4, which reads §2.3's named destinations and §3.5's rows) · `StartLimit*`
tuning in the unit (default containment disclosed, §2.2) · log rotation for
`<dir>.log` (loopback single-operator; revisit with doctor) · an unauthenticated
HTTP lifecycle endpoint (refused — recorded as the rejected alternative to the
doorbell) · the launchd plist renderer's full directive parity audit (inc3's
document-writer leg covers the rendered prose; deep parity rides its own review) ·
SDK `mcp` subcommand lifecycle affordances (none planned; the serve surface is the
SDK's supervised surface, full stop).

## 11. Forks needing the owner's call before the record commits

> **Dispositions (2026-10-08, owner standing cadence — adopt recommendations and
> disclose):** F1 ADOPTED — polymodal `status` (`--data-dir` → lifecycle verdicts,
> `--gateway` → today's live view; exclusive flags, typed refusal on neither/both).
> F2 ADOPTED — unit `ExecStop` is plain `stop`; `--protective` stays a deliberate
> human verb; systemd's own SIGTERM → derived `TimeoutStopSec` → SIGKILL ladder is
> the unattended backstop. F3 ADOPTED — queued runs finalize in-process via the
> #156 recovery shape. F4 ADOPTED — SDK lifecycle twins (start/stop/restart/status
> + pidfile + log + wedge-ladder). Redirect stays open until increment 3's build
> dispatches.

- **Fork 1 — `status` verb shape.** The issue's train names `status`, but
  `benchweave status` EXISTS as the live-gateway REST view (`--gateway`+`--token`).
  Recommended: make `status` polymodal — `--data-dir` → lifecycle verdicts
  (pid/hold/log/unit), `--gateway` → today's live view; exclusive flags, typed
  refusal on neither/both. Alternative: a separate `benchweave daemon status` verb
  (cleaner separation, one more command against the ~20 budget).
- **Fork 2 — unit `ExecStop` mode.** Recommended: plain `stop` (the refusal surfaces
  in `systemctl status`; `--protective` stays a deliberate human verb; systemd's own
  SIGTERM→TimeoutStopSec→SIGKILL is the unattended backstop with the derived
  timeout). Alternative: `ExecStop` routes `--protective` (an unattended safe ending
  on every service stop — A04-conform since the transition is commissioned policy,
  but it cancels long unattended procedures on routine host maintenance).
- **Fork 3 — queued runs under `--protective`:** finalize in-process via the #156
  recovery shape (recommended — honest `interrupted` immediately, no stale live
  projections while stopped) vs leave them for next-boot recovery (smaller diff; the
  store transiently shows live runs with no process — doctor-disclosed).
- **Fork 4 — SDK lifecycle breadth:** start/stop/restart/status + pidfile + log +
  wedge-ladder (recommended — one standard, cheap twins) vs refusing lifecycle verbs
  on the SDK entirely (preview surfaces die with their terminal; `start` is
  convenience only).

---

## 12. Refute fold (2026-10-08)

The record was attacked by two adversary lanes BEFORE committing (its own §8 tier
call). Lane 2 (operational + invariant audit) returned F1-F15; every finding is
folded above at its site, marked "(Fn fold)". Lane 1 (code-claim audit) was still
running at fold time; its findings fold as a second commit on this branch before
merge (the owner's late-findings rule) or become increment 3 build constraints.

Dispositions: F1-F7 (MEDIUM+) all FIXED in place — PLAIN-stop wording in CTL-9/CTL-11
plus the quote-not-authority clause; one-writer-per-file journaling (daemon verdict
fields, CLI sole journal writer); request-file ownership check + honest R5 posture;
serve-command-scoped doorbell arming with the demo/evidence holder-label verdict;
the SDK token-delivery file; bounded replace-retry on the consume; L11 and L12 arms
added with the SHIP count at 12. F8-F15 (LOW) folded as: F8 readiness honesty +
liveness polling; F9 durability enumeration + pre-kill intent row; F10 skip-path
disclosure; F11 count disclosure (numbers re-measured by inc3's build record);
F12 `stop_requested` vocabulary; F13 sibling-collision naming in STO-3; F14 L8
determinism + second-flake-is-KILL; F15 cancel principal named.

Lane 2's nulls worth carrying into inc3 unchanged: the SDK's atomic-write
discipline survives SIGKILL mid-write (torn parts inert); restore-vs-stop fd
interactions are structurally moot (sibling placement + hold refusal); L5's fault
injection fits the established test-child pattern (Store's kill-window seams).

**Lane 1 (code-claim audit) — folded as this branch's second commit (the owner's
late-findings rule).** 13 findings (1 HIGH, 4 MEDIUM, 3 LOW-MED, 5 NIT), every
§0 file:line premise verified accurate, dispositions:

- F1 (HIGH) FIXED: §3.3's protective path reordered — worker pickup-gate (a
  REQUIRED inc3 mechanism: stop dequeuing, let the active job finish) → cancel +
  wait-terminal → confirmed queue-empty → sweep scoped to the #156 queued-ghost
  leg only (reclaim/reconcile legs skipped at stop time, F13) → drain/release.
  The dual-writer terminalization race (worker picks up a queued run the sweep is
  finalizing) is the CTL-9 corruption class; arm L3b added.
- F2 (MEDIUM-HIGH) FIXED: §0.2 corrected (the drain hangs on an open SSE stream
  today — `timeout_graceful_shutdown` None); inc3 passes an explicit timeout,
  closes live SSE at the stop decision, bounds the plain-stop waits; L1 carries
  the wall-time assert R9 names.
- F3 (MEDIUM) FIXED: §3.4 sets `should_exit` directly — uvicorn's captured-signal
  replay would exit by signal 15 after a clean drain, failing L4's exit 0.
- F4 (MEDIUM) FIXED: §3.1 TOCTOU-closed (set-then-check under the run-start write
  gate, typed `stop_in_progress:` refusal); arm L13 added.
- F5 (MEDIUM) FIXED: §4.1 end-of-wait liveness re-check before readiness exit 0.
- F6/F7 FIXED: §2.4 label-first hold cross-check (no false desync on at-rest
  holders) + the verdict lattice fully defined (ticks-unobtainable defers to the
  hold; hold-agreement vouches; zombies disclosed).
- F8 FIXED: protective accepted verdict carries run_ids (rung 3's audit source).
- F9 FIXED: L6(b)'s fixture writes a MISMATCHED ticks value.
- F10 FIXED: §8 re-measured at commit time (final numbers in place).
- F11 FIXED: SIGHUP named — unhandled by design, lands in the KILLED class.
- F12 FIXED: §3.2 — the trigger schedules; decision and protective wait run on
  the loop, never in the handler.
- F13 FIXED: scoped sweep (F1 above).

Lane 1's nulls carried forward: no cancel-deadlock shape exists; no torn verdict
reads; SIGTERM capture-then-replace is temporally sound; projection states are
complete outside F4's (now-closed) window; the §0 template and contract quotes
byte-verified. SHIP count is now 14 gateway arms (L1-L13 + L3b) + 3 SDK arms.
