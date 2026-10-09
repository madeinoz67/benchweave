# Issue #422 increment 4 — `doctor` + `logs` (design record, NO CODE)

**Date:** 2026-10-09
**Issue:** madeinoz67/benchweave#422 (increment 4 of 4: env autoload → supervision
record → lifecycle verbs → **this record**)
**Verdict:** BUILD — a thin, read-only triage verb and a log-tail verb, both composed
almost entirely from mechanisms inc3 already landed
**Status:** design record — the acceptance-rule authority for increment 4's build
**Grounded on:** main @ `dfca5fe9` (inc3 merged as PR #431); every code claim below was
read at that tree. Gortex facade served `cli/lifecycle.py`, `supervision.py`,
`cli/commands.py`, `interfaces/supervision.py`, `cli/atrest.py` (content-exact —
the draft's "no line numbers" claim dropped by the R8 fold: the body line-cites
throughout, spot-checked accurate); the SDK standalone
checkout is OUTSIDE every indexed root (GORTEX UNAVAILABLE there, native reads
disclosed); the benchweave MuninnDB vault was unreachable during grounding (socket
closed, twice) — prior train state was taken from the committed inc1/inc2 records and
the tracker, which are the authoritative sources anyway.

---

## 0. Premise corrections the code forced (read this first)

1. **The pidfile's `log_destination` never says `"journal"` — the record's own §2.4
   vocabulary was narrowed in build.** The inc2 record pinned the field as
   `"journal|<path>|stderr"`. The landed implementation
   (`interfaces/supervision.py::SupervisionSurface.log_destination()`) returns
   `os.environ.get("BENCHWEAVE_LOG_DESTINATION", "stderr")` — `start` sets that env var
   to the `<dir>.log` path (`cli/lifecycle.py:496`), foreground leaves it unset, and
   **under systemd it is also unset**: the unit template sets no such variable
   (`deploy/systemd/benchweave.service.template` carries only `EnvironmentFile`), so a
   journald-supervised daemon records `"stderr"` today. `logs` cannot distinguish
   "journal" from "the operator's dead terminal session" from the pidfile as shipped.
   Increment 4 completes the pinned vocabulary at the writer, resolution order env
   var FIRST then journal (R2 fold, lane-1 — the draft's journal-first order SHADOWS
   the env var `start` itself sets: reproduced `JOURNAL_STREAM=8:12345` +
   `BENCHWEAVE_LOG_DESTINATION=data.log` → `"journal"` while stderr goes to the
   file, reachable via `benchweave start` from any journal-connected systemd
   context): `log_destination()`
   returns the env path when `BENCHWEAVE_LOG_DESTINATION` is set (the `start`-written
   value), else `"journal"` when systemd's `JOURNAL_STREAM` is present in the environment
   (set by systemd exactly when stderr is connected to the journal — the semantically
   precise indicator; `INVOCATION_ID` is the coarser twin), else `"stderr"`. This is completing the inc2 record's own spec, not new architecture;
   pidfile `schema` stays 1 and an old `"stderr"` pidfile keeps today's honest
   handling. Spoofing disclosure: an operator who exports `JOURNAL_STREAM` by hand
   gets a pidfile that says `journal` and a `logs` that then tries `journalctl` —
   degrading typed where journalctl is absent; on a real systemd host, where
   journalctl exists, the residual is journalctl's SILENT EMPTY OUTPUT (exit 0, no
   typed refusal) — §7 R5, re-scoped by the lane-1 R2 fold. The env-first order is
   what makes the spoof require clobbering `start`'s own variable in the `start`
   path (the residual window is foreground/hand-run serve, where that variable is
   unset).
2. **launchd was never a named destination, and the rendered plist discards stderr.**
   The inc2 record §2.3 named three destinations (start → `<dir>.log`; systemd →
   journald; foreground → terminal). The rendered launchd plist
   (`deploy/launchd/com.benchweave.gateway.plist.template`) sets **no
   `StandardErrorPath`** — a LaunchDaemon's stderr defaults to the console/nowhere,
   so under launchd the daemon's log is lost by construction today. The tempting
   two-line fix (render `StandardErrorPath` → `<dir>.log`) is NOT taken, because the
   plist runs as root (no `UserName` key) and a root-owned 0600-pattern log beside an
   operator-owned data dir breaks `logs` readability and starts a permissions fork
   this increment does not own. Disposition: **doctor discloses the gap loudly**
   (§1 D5) and the fix is a deferred issue with a condition-shaped trigger (§8).
3. **`status --data-dir` already exists and is the composition point.** Fork F1 was
   adopted and landed: `status` is polymodal (`cli/commands.py:1119-1131` —
   exclusive-flags typed refusal) and `status_lifecycle` (`cli/lifecycle.py:590-610`)
   already derives the pid identity verdict, hold + holder, and log destination.
   Doctor does not re-derive any of that: it CALLS `status_lifecycle` and maps its
   fields onto check rows — one spelling, so `status` and `doctor` can never
   disagree. The inc2 §5 table granted doctor as its own deferred affordance:
   doctor is a separate verb; status stays as landed.
4. **The CI wall-clock constraint shapes the arms, not just the review.** The inc3
   close flagged "split lifecycle arms onto their own CI lane" as a retrospective
   row. This record adds **zero new real-subprocess arms**: every doctor/logs arm is
   either a hand-staged-sidecar `CliRunner` arm (the `test_lifecycle.py` L6 pattern:
   `_write_pidfile` / `_hold_with_body` / `_live_child`) or an in-process composition
   (`supervision.write_pidfile` names the TEST process's own pid — probe and ticks
   both resolve, verdict OURS, no daemon). The one live-daemon property that matters
   (doctor works while the store is held) is proven by holding a REAL `StoreHold` in
   the test process, not by booting one.

## 1. `benchweave doctor` — the read-only triage probe

### 1.1 The boundary: read-only, never a hold-taker, works while LIVE

At-rest commands are defined by taking the store hold (`cli/atrest.py` module
docstring; STO-3's site list). **Doctor deliberately takes no hold, opens no `Store`,
runs no migrations, and writes no supervision or benchweave-owned file; the mode=ro
store probe may materialize the empty SQLite sidecar pair (`-shm`/`-wal`) — verify's
own at-rest behavior, and atrest `_UNLISTED_OK` already tolerates them as live-state
(R1 fold, lane-1 + lane-2, double-confirmed: connect alone creates nothing, the
first read materializes `state.sqlite-shm` 32 KB + `state.sqlite-wal` 0 B, and the
pair persists after close).** Its whole point is triage DURING
an incident, which usually means while a gateway is live. The store read is the
`verify` command's own precedent: `_integrity_problems` opens
`sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)` and runs
`PRAGMA integrity_check` — read-only, WAL-compatible while a same-user writer holds
the flock (the `-shm`/`-wal` sidecars exist and are readable; a doctor run as a
DIFFERENT user than the daemon gets an honest typed failure naming the permission —
that is a correct triage finding, not a defect, and arm D3 pins the same-user live
case). Doctor never calls `Store.open` (that path migrates); it never journals (the
journal's writers are the lifecycle verbs — a `doctor_run` row would be noise from a
read-only surface); it emits to stdout/`--json` only. Structural read-only-ness is
pinned by an arm asserting, over the ENUMERATED sidecar family, that existing
files' mtimes are unchanged and no file appears beyond the disclosed empty
`-shm`/`-wal` pair across a doctor run (G2's pin, re-scoped by the R1 fold).

### 1.2 The check set (seven checks, each a typed row)

Payload: `{"data_dir": …, "ok": bool, "checks": [row, …]}` through `emit()`
(`--json` the machine contract, the CLI-wide convention). Plain output is one
`doctor: <check> <verdict> <detail>` line per row (the `verify` command's stderr-line
precedent) plus a summary. Row shape: `{"check", "verdict": "pass"|"fail"|"unknown",
"detail", …check-specific fields}`.

| # | Check | Mechanism (all in-tree) | Verdict rules |
|---|---|---|---|
| D1 | store | `state.sqlite` present; `_integrity_problems`-shaped mode=ro `PRAGMA integrity_check` (same helper discipline, cited not imported-from-verify — a small local function over the same `as_uri()?mode=ro` idiom) | missing / unopenable / not-`ok` → **fail** (detail names perms when the open refuses); else **pass** |
| D2 | hold | `daemon_holds(db)` + `holder_info(db)` (the `status_lifecycle` block) | informational: held-or-free both **pass**; holder label carried (gateway label / at-rest label like `service-install` / `backup pid …`); held-with-unreadable-body → **pass** with note (the body is advisory; the flock is the truth — STO-3) |
| D3 | pid | the full §2.4 lattice via `verify_gateway_identity` (`supervision.py:414-500`), embedded from `status_lifecycle`'s payload | `ours` → pass; `absent` → pass (note: never served or cleanly stopped — foreground writes a PRESENT stderr pidfile; a fresh `start`'s ≤30 s pidfile window can transiently read absent — R5 fold, lane-2); `dead` → pass (note: stale sidecars present, `stop` clears them); `not-ours` → **fail** (`supervision_stale_pid:` detail); `desync` → **fail** (`supervision_hold_desync:` detail naming both pids); `unknown` → **unknown** (`supervision_pid_unknown:` detail) |
| D4 | env file | `<data-dir>/benchweave.env` (`atrest.CREDENTIAL_FILE`): if present, the SAME validation call serve makes — `parse_env_file(path, serve_env_file_keys(), excluded=ENV_FILE_EXCLUDED_KEYS)` (`cli/commands.py` serve body; `parse_env_file`, NOT `load_env_file` — the apply variant would put the secret into the doctor process's own env, R7 fold) — plus POSIX mode 0600 (Windows: ACL note, the atrest #137 posture — skip-with-disclosure) | absent → **pass** (note: autoload is optional; process env / unit EnvironmentFile is the deploy path); wrong perms / unparseable / non-allowlisted key → **fail** (the `env_file:` prefix family surfaces verbatim — doctor previews the next boot's own refusal). **Key NAMES only in output, never values** (the inc1 discipline) |
| D5 | unit | systemd: `UNIT_DEFAULT` (`/etc/systemd/system/benchweave.service`, `cli/lifecycle.py:64`) statable; macOS: the `PLIST_DEFAULT` path under `~/Library/LaunchDaemons` | informational **pass** either way: unit statable → note "restart-on-crash belongs to the service manager"; absent → note "no service manager unit — `start`/pidfile mode". D5 never asserts supervision from statability (R6 fold, lane-2, hedges the draft's over-claim): a statable plist means exactly that — load state is launchctl's, not the filesystem's — and the default path (`~/Library/LaunchDaemons`) is OUTSIDE launchd's scan paths (/Library/LaunchDaemons, /Library/LaunchAgents, ~/Library/LaunchAgents); the deferred launchd issue carries the gap (§8.3). On darwin with a plist statable AND the pidfile's destination `stderr` → note names the launchd stderr gap (§0.2) and the operator action |
| D6 | log destination | derived: pidfile's `log_destination` field; pidfile absent → the `<dir>.log` sibling's existence | informational **pass**: path statable → pass (path carried); path missing → note (created at next `start`); `journal` → pass (unit name carried); `stderr` → note (foreground; `logs` will refuse, §2); any OTHER value (out-of-vocab — a tampered or hand-written pidfile) → **unknown** row naming the raw value, which feeds the exit-1 contract (R7 fold) |
| D7 | supervision sidecars | `<dir>.stop`: a request-shaped file (no `status`) whose `target_pid` is dead or absent → stale (start clears; era-bound, inert — `supervision.py:534-540`); an UNREADABLE `.stop` → note (inert daemon-side — the daemon's stop-check treats an unreadable request as no request); `<dir>.supervision.jsonl`: every line JSON-parses; an UNREADABLE journal (OSError on open/read) → the row goes **unknown** and triage CONTINUES — never a mid-run crash (the unreadable cells are the R7 fold) | stale stop request → **pass** with note naming the cleaner; unreadable `.stop` → **pass** with note (inert daemon-side); journal all-parses → pass; journal unreadable → **unknown** (`supervision_journal_unreadable:` detail); **torn FINAL line** → pass with note (the known crash-tear shape — appends are single-write+fsync, a crash can tear exactly the last line); **unparseable non-final line** → **fail** (only reachable by tampering — mid-file tears cannot occur by construction, so the row says so) |

`ok` = no `fail` AND no `unknown` row. **Exit contract: 0 iff `ok`, else 1**
(`raise click.exceptions.Exit(1)`, the `verify` command's convention). The
UNKNOWN-exits-1 ruling, with its reason inline (G4 discipline): scripts gate actions
on doctor — a pre-`start` gate that reads `unknown` as healthy invites spawning a
second contender over an unverifiable pidfile, which is exactly the refusal
`start` itself makes (`cli/lifecycle.py:458-459` refuses on `unknown`/`desync`).
Operators read the verdict WORDS (rows keep `fail` ≠ `unknown` distinct); scripts
read the exit code / `ok`. One contract, both consumers — no `--strict` flag.
`unknown` is reachable through D3's identity lattice, D6's out-of-vocab
destination, and D7's unreadable journal — the three genuinely three-valued inputs
(the D6/D7 legs are the R7 fold; every other check's inputs are binary at-rest
facts).

**What doctor deliberately does NOT check** (a guard states what it does not catch):
no live-process environment cross-check — declined on every platform for a
universal reason (re-scoped by the R6 fold: "structurally unreadable on darwin"
was a one-platform reason justifying an every-platform refusal; on Linux
`/proc/<pid>/environ` is readable, and the check is declined there too — the env
check is at-rest only, and a per-platform-readable row would mean different things
on different hosts); no schema-drift verdict (D1 reports integrity only — a
store newer than the binary is serve's migration story, not a triage failure; named
non-goal); no run enumeration (the run plane belongs to the daemon's live
projection and `status --gateway` — doctor is supervision-plane triage); no
manifest-digest verification (`verify` owns that, and live data dirs carry no
`manifest.json`); no log-content parsing — the inc2 record's pinned sentence
(§2.3): *serve's stderr prose is not an interface*; doctor re-derives state from
inputs (pidfile, hold, store-at-rest, supervision rows) and never reads `<dir>.log`
for meaning. `logs` (§2) RENDERS log bytes; it derives no verdicts from them.

### 1.3 Command surface

`benchweave doctor --data-dir DIR [--json]` — required `--data-dir`
(`envvar=BENCHWEAVE_DATA_DIR`), the at-rest convention. Implementation module:
`src/benchweave/cli/diagnose.py` (~both verbs; `cli/lifecycle.py` stays the verbs),
registered as two top-level Click commands in `cli/commands.py`. Command budget after
this increment: 18 top-level commands/groups (16 today + `doctor` + `logs`), inside
the issue's ~20 breadth refusal line — stated so the budget rule is auditable.

## 2. `benchweave logs` — tail the named destination

`benchweave logs --data-dir DIR [--lines N]` (default 50; `N` a positive int —
zero or negative is a typed `logs_lines_domain:` refusal, R8 fold). Resolution
ladder, in order, from inputs only:

1. **pidfile present** → its `log_destination` field:
   - a path → the credential guard FIRST (R3 fold, lane-2): the resolved
     destination is compared against the surface's known credential file (gateway:
     `<data-dir>/benchweave.env`; SDK twin: `<bindings>.tokens`) and an exact match
     is a typed `logs_destination_credential:` refusal naming the file class — the
     pidfile field is operator-steerable through the process env
     (`BENCHWEAVE_LOG_DESTINATION` gateway-side, `BENCHWEAVE_SDK_LOG_DESTINATION`
     in the twin), and pointed at a credential file rung 1 would otherwise tail the
     secret (the env-FILE vector is closed — no such key in `serve_env_file_keys`
     — the process-env vector was open). Then: tail that file (`<dir>.log` under
     `start`); seek-based tail bounded by
     `lines` (windowed read from `max(0, size - 64 KiB)`, doubling on undercount —
     never a whole-file read; decode `errors="replace"`, the `_log_tail` DECODE
     policy only, `cli/lifecycle.py:580-584` — that helper reads whole-file and
     slices; the windowed tail here improves on it, R8 fold). Unreadable → typed
     `logs_unreadable:` refusal.
   - `"journal"` → `journalctl --no-pager -n <N> -u benchweave` as a fixed-argv
     subprocess (the atrest `whoami`/`icacls` in-tree subprocess precedent: absolute
     or PATH-resolved binary, fixed arguments, bounded timeout). `journalctl` not
     resolvable on the host → typed `logs_journal_unavailable:` refusal naming the
     unit — the inc2 record's "implement or degrade loudly", degraded loudly.
   - `"stderr"` → typed `logs_destination_stderr:` refusal: the daemon was started
     foreground (its bytes went to a terminal this command cannot recover), or the
     pidfile predates §0.1's journal detection; the refusal names `journalctl -u
     benchweave` as the thing to try under systemd.
2. **pidfile absent** — absent means never-served or cleanly-stopped (R5 fold,
   lane-2: a crash LEAVES the pidfile behind for `stop`'s stale path to clear, and
   foreground serve writes a PRESENT stderr pidfile, so foreground is not absent's
   signature either) → if `<dir>.log` exists, tail it and REPORT the resolution as
   post-mortem (the sibling
   file is still the honest post-mortem source when it exists). Momentary-window
   caveat: a fresh `start` inside its ≤30 s pidfile-absence window can transiently
   land here — the tail is of a STARTING daemon reported post-mortem; re-run once
   the pidfile lands. Else typed
   `logs_no_destination:` refusal.

Output: the tail's lines to stdout; `--json` wraps `{"destination": …, "unit"?…,
"lines": […]}`. **No `--follow`** (§8 defers it: streaming needs subprocess
lifecycle + interrupt semantics + a Windows story; `tail -f` / `journalctl -f` exist
and the operator has them). **The token-file exclusion, structurally (re-mechanized by the R3 fold, lane-2)**:
the destination candidate set is exactly {pidfile `log_destination`, `<dir>.log`} —
but "never a candidate" alone was NOT a working mechanism, because the pidfile
field itself is operator-steerable through the process env
(`BENCHWEAVE_LOG_DESTINATION` gateway-side, `BENCHWEAVE_SDK_LOG_DESTINATION` in
the SDK twin): pointed at `benchweave.env` or `<bindings>.tokens`, rung 1 would
tail the credential. The env-FILE vector is closed (no such key in
`serve_env_file_keys`); the process-env vector is closed by rung 1's typed
`logs_destination_credential:` refusal. Obligation 11 pins the prose; the refusal
is the mechanism that makes it true. Arms pin both branches (X6 gateway rung 1,
S8 SDK rung 2).

## 3. The SDK twins (`benchweave_sdk_server doctor` / `logs`)

One standard, per-surface application (inc2 §5's table deferred doctor/logs for BOTH
surfaces; the twin lands in the SDK repo's `lifecycle.py`, wired like its siblings —
`cli.py`'s start/stop/status pattern: `bindings_path(bindings)`, payload JSON to
stdout, `LifecycleError` → stderr + exit 1):

- **`doctor`** — five checks (the R4 fold, lane-2, widened it from four: `.stop`
  sits inside the family's own cited range, and the stale-request shape is the
  twin's known S1 class) over the twin family (`<bindings>.pid/.log/.tokens/.stop/
  .supervision.jsonl`, `sdk lifecycle.py:103-120`): pid identity (the twin lattice
  `verify_identity`, `sdk lifecycle.py:311-335` — no hold exists to cross-check, so
  `unknown` is ticks-unobtainable on either side), log destination resolvability
  (pidfile field / `<bindings>.log` sibling), **tokens-file 0600** (the ONE
  credential-carrying exception in the family's orbit — the perms check is the whole
  reason this check exists SDK-side; wrong perms → fail; the bearer VALUE is never
  in output, key names and paths only), journal parseability (D7's rule), and the
  stale stop request — a `<bindings>.stop` whose target pid is dead or absent →
  **pass** with note naming `start` as the cleaner (the gateway D7 rule; the
  twin's D7-analogue — R4 fold, lane-2). Same
  exit contract (0 iff no fail/unknown; the twin lattice's `not-ours` → fail,
  `unknown` → unknown/exit 1). No store/hold/env/unit checks — nothing to probe
  (the recorded divergences: no store, no service install).
- **`logs <project> [--bindings …] [--lines N]`** (`N` the same positive-int domain,
  R8 fold) — resolution: pidfile
  `log_destination` path → the same credential guard first (a resolved destination
  equal to `<bindings>.tokens` → typed `logs_destination_credential:` refusal
  naming the tokens class — R3 fold, lane-2; `BENCHWEAVE_SDK_LOG_DESTINATION` is
  operator-steerable the same way); then tail; `"stderr"` → typed refusal (no journal leg in the
  twin: `service install` is refused on this surface, so no unit name exists to
  query); pidfile absent + `<bindings>.log` exists → post-mortem tail (absent =
  never-served or cleanly-stopped, the R5 fold); else typed
  refusal. The tokens file is refused as a destination even when named (S8's arm
  plus the R3 refusal).

## 4. Invariant walk

- **CTL-1..10, CTL-11: UNTOUCHED.** No ladder motion, no verdict writes, no
  terminal-record adjacency. Doctor reads the sidecar family; `logs` renders one
  file or one fixed-argv subprocess. CTL-11's outcome-blind clause gains nothing to
  obey — nothing in inc4 acts.
- **STO-3: EXTENDED by a one-clause rider** (lands with inc4's diff): doctor and
  logs are read-only, non-hold-taking readers of the store-at-rest and the
  supervision family — doctor's store read is the `verify`-precedent `mode=ro`
  probe, deliberately NOT an at-rest hold acquisition, so triage works while a live
  coordinator holds the store; neither writes any supervision or benchweave-owned
file — the mode=ro probe may materialize the empty SQLite sidecar pair
(`-shm`/`-wal`), verify's own at-rest behavior, already tolerated by atrest
`_UNLISTED_OK` (R1 fold, lane-1 + lane-2 — NEVER land "neither writes any file" as
the rider's literal text in invariants.md; the sidecar pair makes that claim false).
(The existing rider already
  names `stop`/`status`; this adds the two new readers by name.)
- **STO-1/2/4/5/6, CON-*, REG-*: UNTOUCHED.** No transport, contract, corpus,
  manifest, schema, registry, or standards bytes; the standards tripwire stays green
  (zero `standards/` motion — checked against the standing tripwire).
- **A02: no numeric envelope enters.** `--lines` and the tail window are service
  parameters (like `VERDICT_WAIT_S`), not bench limits; no commissioned value is
  read, derived, or second-guessed.
- **A04: nothing new depends on judgement.** Doctor is diagnostics; it gates
  nothing itself (scripts may gate on its exit code — their choice, over typed
  rows).
- **A06/A07: doctor writes no supervision or benchweave-owned file** — no journal
  rows, no sidecar touches; the disclosed empty `-shm`/`-wal` pair excepted (R1
  fold, lane-1 + lane-2); the audit trail is not a dependency of triage and triage
  is not an audit event.
- **G0 discipline:** doctor/logs never print env-file VALUES or token material
  (key names and paths only); arms assert the secret/token strings are ABSENT from
  combined output (G7, X6, S6).

## 5. Pre-committed acceptance rule for increment 4

Written BEFORE any increment-4 code exists. Counts from `--junitxml` attributes or
exit codes, never an output-filter summary. Every arm names its expected TYPED
outcome. All gateway arms are staged-sidecar `CliRunner` or in-process compositions
(§0.4) — zero new real-subprocess daemons.

**Gateway arms** (`tests/cli/test_diagnose.py`; harness patterns from
`tests/cli/test_lifecycle.py`):

| # | Arm | Expected typed outcome |
|---|---|---|
| G1 | empty `--data-dir` (no store) | D1 row `fail`; exit 1; `ok=false` |
| G2 | healthy at-rest (real `atrest.setup` store: env file 0600, no pidfile, hold free) | every row `pass` (notes on D4/D5/D6); exit 0; the ENUMERATED family {`state.sqlite`, `state.sqlite-wal`, `state.sqlite-shm`, `<dir>.pid`, `<dir>.stop`, `<dir>.log`, `<dir>.supervision.jsonl`, `benchweave.env`}: existing files' mtimes UNCHANGED and NO new file beyond the disclosed empty `-shm`/`-wal` pair across the run (structural read-only pin — R1 fold, lane-1 + lane-2) |
| G3 | coherent live, in-process: real `supervision.write_pidfile` naming the test pid (log_destination=a staged log path) + `StoreHold` with a `gateway ` label whose pid matches | D3 `ours` pass; D2 held pass; D1 integrity pass UNDER the held flock (the works-while-live boundary); exit 0 |
| G4 | desync: pidfile self + gateway-label hold naming a DIFFERENT pid | D3 `fail`, detail carries `supervision_hold_desync:` naming both pids; exit 1 |
| G5 | not-ours: pidfile names `live_child` with a MISMATCHED ticks value | D3 `fail` (`supervision_stale_pid:`); exit 1 |
| G6 | unknown: pidfile names `live_child`, ticks monkeypatched to `None`, hold free | D3 `unknown`; **exit 1** — the unknown-exits-nonzero pin, the load-bearing exit-contract arm |
| G7 | env file chmod 0644 | D4 `fail`; the setup-written SECRET string absent from combined output |
| G8 | env file carrying a non-allowlisted key | D4 `fail`, detail carries the `env_file:` prefix family (doctor previews serve's own refusal) |
| G9 | corrupt store: garbage bytes as `state.sqlite` | D1 `fail` (cannot-open/integrity path); exit 1 |
| G10 | journal: valid rows + torn FINAL line → note, exit 0; torn NON-final line → `fail`, exit 1 | D7 both cells |
| G11 | stale stop request targeting a dead pid | D7 note naming `start` as the cleaner; exit 0 |
| X1 | staged `<dir>.log` (larger than the tail window) + pidfile with path destination, `--lines 100` | exactly the last 100 lines; `--json` shape `{destination, lines}` |
| X2 | pidfile ABSENT + `<dir>.log` present | post-mortem tail; resolution reported as post-mortem |
| X3 | destination `stderr` | typed `logs_destination_stderr:` refusal; exit 1 |
| X4 | destination `journal`, journalctl resolver stubbed present → the EXACT fixed argv asserted; stubbed absent → typed `logs_journal_unavailable:` refusal | argv pin + degrade-loudly |
| X5 | destination path with mode 000 | typed `logs_unreadable:` refusal, never a traceback |
| X6 | staged pidfile whose `log_destination` names the env file (`<data-dir>/benchweave.env`) | typed `logs_destination_credential:` refusal naming the env-file class; the SECRET absent from combined output; exit 1 (R3 fold, lane-2) |

**SDK arms** (`tests/server/test_lifecycle.py` additions): S5 doctor happy path
(staged pidfile self + log + tokens 0600 → all pass, exit 0) · S6 tokens file chmod
0644 → `fail` row, bearer VALUE absent from output · S7 logs tails a staged
`<bindings>.log` · S8 logs with a POISONED tokens file (read_text raising on it via
monkeypatch) still completes — the tokens file is structurally never a destination
candidate at rung 2 (S8's scope after the R3 fold) · S9 doctor on a stale
`<bindings>.stop` request targeting a dead pid → note naming `start` as the
cleaner; exit 0 (R4 fold, lane-2).

**RED controls (the fluff-proof part), neutralize at ONE site each:** (a) the 0600
perms check → G7 and S6 must FAIL; (b) the integrity probe (force `[]`) → G9 must
FAIL; (c) the identity verdict (force `ours`) → G4/G5/G6 must FAIL; (d) destination
resolution (force the `.log` path) → X3/X4 must FAIL; (e) SDK-side, the tokens-perms
check → S6 must FAIL; (f) the credential-destination refusal (neutralize the guard —
force the path open) → X6 must FAIL (R3 fold, lane-2); (g) the D7 journal-parse
check → G10 must FAIL (R7 fold). Restored, all pass.

**SHIP =** G1-G11 + X1-X6 + S5-S9 green with typed outcomes as tabled; all seven
RED controls (a)-(g) red-then-green; fast lane + full battery green in BOTH repos; the docs
obligations walked in the same train (operator-guide CLI reference + README command
list, gateway repo — including correcting the stale "Twelve commands" module
docstring the build's docs motion inherits, R8 fold; the SDK repo's own docs/README
rows; obligation 11's
`logs`-never-displays-tokens prose is already committed and inc4 makes it
mechanically true); standards tripwires green. **KILL =** any arm failing after one
fluke re-run; any control staying green while neutralized (the arm tests nothing —
redesign, do not merge); a secret or token value EVER appearing in doctor/logs
output (G0 class — kill on sight); doctor ever taking the hold or writing any supervision
file — the disclosed empty `-shm`/`-wal` sidecar pair excepted (R1 fold, lane-1 +
lane-2; G2's pin failing beyond that pair is this kill firing). **UNDERPOWERED =** the real
journalctl READ cannot run in CI (no systemd user session in the containers): the
journal leg's evidence is X4's fixed-argv pin plus the typed-refusal arm, the
degradation disclosed on the PR, and the first real systemd deployment is the
corroboration venue (the W1 posture inverted: operator-corroborated, not CI —
named here so nobody calls X4 a journal test).

## 6. Review tier + Step-1 keyword scan (#254)

**Tier 3.** Path rules do not fire (no `contracts/`, `standards/`, `state/`
migrations, registry, fixtures, deps, submodule-pointer bytes beyond the pointer
commit itself — which DOES fire the submodule-pointer rule on the gateway PR: the
SDK twin requires the two-repo discipline, SDK PR merged first, then the gateway
pointer PR advancing gitlink + `.gitmodules` pin in the same commit per #408).
Keyword rules fire on the expected diff regardless: the journalctl leg and the
tests carry `subprocess`, and the docstrings carry the supervision vocabulary.
Two-lane adversary mandatory (the 2026-09-24 standing rule for Tier 3).

Keyword legend (numbered so this table does not perturb its own counts):
1=`threading` 2=`asyncio` 3=`subprocess` 4=`sha256` 5=`hashlib` 6=`migrate`
7=`recovery` 8=`protection`.

Scan result, MEASURED over this record at design time
(`grep -oiw <kw> <record> | wc -l`, the legend's one occurrence per keyword
excluded): **1: 0 · 2: 0 · 3: 9 · 4: 0 · 5: 0 · 6: 0 · 7: 0 · 8: 0.**
(disclosure, the F11 discipline: the pre-measurement draft guessed 3: 5 and
7: 1 · 8: 1 — the measured counts are 9 and 0/0; raw counts before the legend
exclusion are 1/1/10/1/1/1/1/1. First-match-wins on keyword 3 either way.)
First-match-wins: keyword
3 fires → Tier 3. Increment 4's build record re-measures and states its OWN scan
over its real diff — that number gates.

## 7. Top risks, each with its falsifier

- **R1 mode=ro on a LIVE WAL store fails cross-user** (doctor run as a different uid
  than the daemon; mechanism reworded by the R7 fold: an unreadable `-shm` alone
  does NOT refuse the open — SQLite ≥3.22 falls back to the heap wal-index when
  the shm cannot be mapped — so cross-user honesty rides the MAIN db file's perms,
  not the shm's). This is a CORRECT
  triage finding (the detail names the permission and the daemon's uid), not a
  defect; same-user live is pinned green by G3. Falsifier: G3 red on any
  same-user host would be a real defect — kill.
- **R2 unknown-exits-1 annoys a script on a ticks-unobtainable platform** (a sandbox
  where the ticks read fails). The row carries the reason and `status` gives the
  same lattice for free; the conservative direction is the deliberate choice (§1.2).
  Falsifier: none in-tree — the posture note IS the disposition (an adversary lane
  is invited to disagree; fork F1 carries it).
- **R3 journalctl argv/behavior drift across systemd versions.** `-n`, `--no-pager`,
  `-u` are stable flags; the argv is pinned literally by X4 so drift is a visible
  red, not a silent behavior change. Falsifier: X4.
- **R4 doctor's env check fails a hand-placed env file serve would also refuse.**
  Feature, not bug — same validator, one spelling; doctor previews the boot. A
  divergence between doctor's D4 verdict and serve's actual boot behavior on the
  same file would be a real defect; G8 pins the shared call site.
- **R5 `JOURNAL_STREAM` spoofed by hand produces a `journal` pidfile.** NOT
  harmless on a real systemd host (re-scoped, lane-1 R2 fold): journalctl exists
  there, and the spoofed destination yields journalctl's SILENT EMPTY OUTPUT
  (exit 0, no typed refusal) — `logs` reports an empty tail for a daemon that is
  not that unit. On a non-systemd host the degradation is the typed
  `logs_journal_unavailable:` refusal; doctor's D6 passes with the unit name
  carried either way. The env-first resolution order (§0.1) is what makes the
  spoof require clobbering `start`'s own `BENCHWEAVE_LOG_DESTINATION` variable in
  the `start` path — the residual window is foreground/hand-run serve, where that
  variable is unset. Disclosed here.
- **R6 the exit contract invites gating `start` on doctor**, and doctor's verdict is
  a snapshot (a gateway can start between doctor and the gated action). Doctor gates
  nothing itself; `start`'s own pre-spawn gates (§4.1) remain the authority — doctor
  is triage, not a lock. The operator guide row says so.

## 8. Ships, defers — and what closing #422 itself requires

**Ships (this increment):** `cli/diagnose.py` (doctor + logs) + two Click commands;
the `log_destination()` journal completion (§0.1, ~5 lines in
`interfaces/supervision.py`); the SDK twins in the SDK repo's `lifecycle.py` +
`cli.py`; `tests/cli/test_diagnose.py` + SDK test additions; the docs motion
(operator-guide CLI reference, README command list, SDK docs); the STO-3 rider
sentence. Nothing else — no template bytes, no standards bytes, no daemon behavior
beyond the pidfile field's value.

**DEFERRED, each with its issue home and condition-shaped trigger** (the deferral
rule — this is the train's last increment, so nothing leaves without one):

1. **`logs --follow`** → gateway issue, label `gateway`: streaming needs subprocess
   lifecycle + Ctrl-C semantics + the Windows story; trigger: the first operator
   request for live tailing during an incident review (the tracker row is the
   trigger's venue).
2. **Log rotation for `<dir>.log`** (inc2 §10 deferred it "revisit with doctor") →
   gateway issue: unbounded growth under a long-lived deployment; trigger: the first
   deployment where `<dir>.log` exceeds ~100 MB or runs past 30 days continuously —
   whichever comes first. A02 note rides the issue: any size/age policy is a service
   parameter, never a bench envelope.
3. **The launchd stderr gap + the scan-path gap** (§0.2; the scan-path half is the
   R6 fold, lane-2) → gateway issue: render `StandardErrorPath`
   (+ the `UserName` question it forces) into the plist template, AND resolve that
   the default install path (`~/Library/LaunchDaemons`) is outside launchd's scan
   paths (/Library/LaunchDaemons, /Library/LaunchAgents, ~/Library/LaunchAgents) —
   the honest options are (i) document `launchctl load` as the required manual
   step, or (ii) move the default install path into a scanned location; trigger:
   the first darwin launchd deployment (until then doctor's D5 note is the honest
   disclosure, and D5 no longer asserts supervision from statability).
4. **Doctor schema-drift reporting** (store vs binary version) — named NON-goal, no
   issue: serve's migration story owns it; D1 reports integrity only by design.

**Closing #422 after this increment:** (a) the SDK doctor/logs PR merges, then the
gateway PR (code + pointer advancing gitlink and `.gitmodules` pin in one commit —
the #408 order; whether the pin names the new tag or the merge SHA rides the
sdk-drift lane's pairing rules, green-with-`pairing pending` being the disclosed
in-between state); (b) the three deferral issues above are FILED (the train's
deferral ledger lives in the tracker, not in this record); (c) the issue closes
after the last merge (its own text); (d) the inc3 retrospective row ("split
lifecycle arms onto their own CI lane") stays a CI question — this record adds zero
real-subprocess arms and therefore does not aggravate the windows rollup it names.

## 9. Forks needing the owner's call

> **Dispositions (2026-10-09, owner standing cadence — adopt recommendations and
> disclose):** F1 ADOPTED — `unknown` exits 1 (scripts gating actions on doctor must
> not read an unverifiable pidfile as healthy; mirrors `start`'s own refusal shape).
> F2 ADOPTED — the launchd stderr gap is disclosed loudly in D5 with a deferred
> issue home (rendering `StandardErrorPath` under a root-run plist opens a
> permissions fork this increment does not own). F3 ADOPTED — the SDK doctor
> twin (one standard, per-surface application; four checks at fork time, widened
> to five by the lane-2 R4 fold). Redirect open until the build dispatches.

- **Fork 1 — does `unknown` exit 1?** Recommended: YES (§1.2 — the conservative
  gate; scripts gating `start` on doctor must not read an unverifiable pidfile as
  healthy). Alternative: `unknown` → exit 0 with `ok=false`-but-zero (scripts
  friendlier on ticks-unobtainable platforms; weaker).
- **Fork 2 — the launchd stderr gap.** Recommended: disclose-only + issue home
  (§8.3). Alternative: render `StandardErrorPath` (+ `UserName`) into the plist NOW
  — closes the gap structurally but opens the root-owned-log permissions fork inside
  the train's last increment.
- **Fork 3 — SDK doctor breadth.** Recommended: the twin (§3 — cheaper
  than a recorded refusal reason, and the tokens-perms check is genuinely useful;
  four checks at fork time — the lane-2 R4 fold adds the stale-`.stop` check as
  the fifth).
  Alternative: refuse `doctor` on the SDK surface like `service install` (one less
  twin; needs its recorded divergence reason).

---

## 10. Fold changelog (2026-10-09, both refute lanes)

Second commit on `cli/diagnose-design`: the two-lane adversary pass folded into
this record before any increment-4 code exists. Row dispositions DECIDED by the
owner; every site carries its row mark inline, and nothing outside this record
changed in the commit. R1 was double-confirmed (both lanes reproduced the sidecar
materialization independently); R2 is lane-1; R3-R6 are lane-2; R7 (cells +
controls) and R8 (NITs) carry no single-lane attribution in the fold brief and are
marked by row only. The acceptance rule's arm count moved G1-G11 + X1-X5 +
S5-S8 → G1-G11 + X1-X6 + S5-S9 and RED controls (a)-(e) → (a)-(g); the §5 table,
not this changelog, is the build's authority.

- **R1 — the read-only claim was FALSE as written (double-confirmed, both lanes).**
  The mode=ro probe materializes the empty SQLite sidecar pair
  (`state.sqlite-shm`, 32 KB, + `state.sqlite-wal`, 0 B) on the first read —
  connect alone creates nothing — and the pair persists after close. Four sites
  fixed: §1.1's claim, the STO-3 rider (with the NEVER-land-"neither writes any
  file" note for invariants.md), the KILL criterion (supervision files; the
  disclosed pair excepted), and G2's pin (the ENUMERATED family,
  mtimes-unchanged-for-existing AND no-new-file-beyond-the-pair). §4's A06/A07
  line and §1.1's arm sentence aligned as consequences.
- **R2 — §0.1's completion order was WRONG (lane-1 MEDIUM).** Journal-first
  shadows the env var `start` itself sets (reproduced: `JOURNAL_STREAM=8:12345` +
  `BENCHWEAVE_LOG_DESTINATION=data.log` → `"journal"` while stderr goes to the
  file, reachable via `benchweave start` from any journal-connected systemd
  context). Order is now env var FIRST, then JOURNAL_STREAM, else `"stderr"`;
  §0.1's spoofing disclosure and §7 R5 re-scoped accordingly (a spoof on a real
  systemd host yields journalctl's SILENT EMPTY OUTPUT — exit 0, no typed refusal
  — not harmless; the env-first order is what makes the spoof require clobbering
  `start`'s own variable).
- **R3 — the credential-exclusion had NO working mechanism (lane-2 MEDIUM).** The
  process env can point the pidfile's `log_destination` at `benchweave.env` or
  `<bindings>.tokens` (`BENCHWEAVE_LOG_DESTINATION` /
  `BENCHWEAVE_SDK_LOG_DESTINATION`); rung 1 gains the typed
  `logs_destination_credential:` refusal (gateway AND twin), X6 pins it, RED
  control (f) neutralizes it, S8 stays the rung-2 branch, and §2's structural
  paragraph now names the refusal — not candidature — as the mechanism.
- **R4 — the SDK family is FIVE members (lane-2 MEDIUM).** `.stop` sits inside the
  record's own cited range; the twin doctor gains the stale-request check (its
  known S1 class, the D7-analogue), S9 pins it, §3's enumeration and Fork 3
  updated to five checks.
- **R5 — "absent = never started or foreground" was FALSE (lane-2 M4).** Foreground
  serve writes a PRESENT stderr pidfile. Both sites (D3's absent-note, §2 rung 2)
  now read never-served or cleanly-stopped, each with the fresh-`start` ≤30 s
  momentary-window caveat.
- **R6 — D5-darwin asserted supervision over a path launchd never scans (lane-2
  M5).** `~/Library/LaunchDaemons` is outside launchd's scan paths
  (/Library/LaunchDaemons, /Library/LaunchAgents, ~/Library/LaunchAgents); the D5
  note is hedged (statable is statable; load state is launchctl's), §8.3's
  deferral issue carries the scan-path gap with the two honest options (document
  `launchctl load`, or move the default install path), and §1.2's live-env
  cross-check decline is re-scoped from a darwin-only reason to a universal one.
- **R7 — cells + controls.** D7 gains an unreadable-journal cell (**unknown**, triage
  continues — never a mid-run crash) and an unreadable-`.stop` cell (**pass**,
  inert daemon-side); D6 gains the out-of-vocab destination cell (**unknown**,
  exit 1); §1.2's "unknown only through D3" sentence updated as a consequence; D4
  pins `parse_env_file` over `load_env_file` (the apply variant would put the
  secret into the doctor process env); §7 R1's mechanism reworded (an unreadable
  `-shm` falls back to the heap wal-index on SQLite ≥3.22 — cross-user honesty
  rides the MAIN db's perms, not the shm's); RED control (g) added for the
  journal check.
- **R8 — NITs.** The `_log_tail` citation narrowed to the decode policy only (its
  read is whole-file-and-slice; the record's windowed tail improves on it);
  Appendix B's D6-mapping claim softened (the absent branch derives beyond the
  payload); the grounding note's "no line numbers" sentence dropped (the body
  line-cites throughout, spot-checked accurate); `--lines` domain pinned (positive
  int, typed `logs_lines_domain:` refusal otherwise — gateway and twin); the
  stale "Twelve commands" module docstring named on the build's docs-motion list
  in the SHIP obligations.

---

## Appendices

### A. Command-count audit (the ~20 breadth rule)

Today (main @ dfca5fe9): `setup backup restore verify demo report retention dispose
serve evidence ui-login stop start restart status service` = 16 top-level entries
(`evidence` and `service` are groups). After inc4: +`doctor` +`logs` = **18**. The
issue's refusal line ("no breadth past ~20 commands") stays respected with 2 slots
of headroom, none planned.

### B. Why doctor composes `status_lifecycle` instead of re-deriving

`status_lifecycle` (`cli/lifecycle.py:590-610`) already computes the identity
verdict (`verify_gateway_identity`), hold + holder, and log destination in one
payload with one spelling. Doctor's D2/D3 rows and D6's pidfile-present branch are
MAPPINGS of that payload — D6's absent branch (the `<dir>.log` sibling probe)
derives in `diagnose.py` beyond the payload, so the original all-three claim is
softened (R8 fold); two surfaces over one derivation can never disagree where they
share it (G4: a set named in prose is
regenerable from a mechanism). Re-deriving in `diagnose.py` would fork the lattice
call sites for zero gain; the composition IS the precedent extension (§0.3).
