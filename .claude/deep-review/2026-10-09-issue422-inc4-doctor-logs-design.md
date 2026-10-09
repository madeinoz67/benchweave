# Issue #422 increment 4 — `doctor` + `logs` (design record, NO CODE)

**Date:** 2026-10-09
**Issue:** madeinoz67/benchweave#422 (increment 4 of 4: env autoload → supervision
record → lifecycle verbs → **this record**)
**Verdict:** BUILD — a thin, read-only triage verb and a log-tail verb, both composed
almost entirely from mechanisms inc3 already landed
**Status:** design record — the acceptance-rule authority for increment 4's build
**Grounded on:** main @ `dfca5fe9` (inc3 merged as PR #431); every code claim below was
read at that tree. Gortex facade served `cli/lifecycle.py`, `supervision.py`,
`cli/commands.py`, `interfaces/supervision.py`, `cli/atrest.py` (content-exact, no line
numbers — symbol names cited per the invariants doc's own rule); the SDK standalone
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
   Increment 4 completes the pinned vocabulary at the writer: `log_destination()`
   returns `"journal"` when systemd's `JOURNAL_STREAM` is present in the environment
   (set by systemd exactly when stderr is connected to the journal — the semantically
   precise indicator; `INVOCATION_ID` is the coarser twin), else the env path, else
   `"stderr"`. This is completing the inc2 record's own spec, not new architecture;
   pidfile `schema` stays 1 and an old `"stderr"` pidfile keeps today's honest
   handling. Spoofing disclosure: an operator who exports `JOURNAL_STREAM` by hand
   gets a pidfile that says `journal` and a `logs` that then tries `journalctl` —
   and degrades typed when it is absent (harmless, disclosed).
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
runs no migrations, and writes nothing — anywhere.** Its whole point is triage DURING
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
pinned by an arm asserting the sidecar family's mtimes are unchanged across a doctor
run.

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
| D3 | pid | the full §2.4 lattice via `verify_gateway_identity` (`supervision.py:414-500`), embedded from `status_lifecycle`'s payload | `ours` → pass; `absent` → pass (note: never started or foreground); `dead` → pass (note: stale sidecars present, `stop` clears them); `not-ours` → **fail** (`supervision_stale_pid:` detail); `desync` → **fail** (`supervision_hold_desync:` detail naming both pids); `unknown` → **unknown** (`supervision_pid_unknown:` detail) |
| D4 | env file | `<data-dir>/benchweave.env` (`atrest.CREDENTIAL_FILE`): if present, the SAME validation call serve makes — `parse_env_file(path, serve_env_file_keys(), excluded=ENV_FILE_EXCLUDED_KEYS)` (`cli/commands.py` serve body) — plus POSIX mode 0600 (Windows: ACL note, the atrest #137 posture — skip-with-disclosure) | absent → **pass** (note: autoload is optional; process env / unit EnvironmentFile is the deploy path); wrong perms / unparseable / non-allowlisted key → **fail** (the `env_file:` prefix family surfaces verbatim — doctor previews the next boot's own refusal). **Key NAMES only in output, never values** (the inc1 discipline) |
| D5 | unit | systemd: `UNIT_DEFAULT` (`/etc/systemd/system/benchweave.service`, `cli/lifecycle.py:64`) statable; macOS: the `PLIST_DEFAULT` path under `~/Library/LaunchDaemons` | informational **pass** either way: unit statable → note "restart-on-crash belongs to the service manager"; absent → note "no service manager unit — `start`/pidfile mode". On darwin with a plist statable AND the pidfile's destination `stderr` → note names the launchd stderr gap (§0.2) and the operator action |
| D6 | log destination | derived: pidfile's `log_destination` field; pidfile absent → the `<dir>.log` sibling's existence | informational **pass**: path statable → pass (path carried); path missing → note (created at next `start`); `journal` → pass (unit name carried); `stderr` → note (foreground; `logs` will refuse, §2) |
| D7 | supervision sidecars | `<dir>.stop`: a request-shaped file (no `status`) whose `target_pid` is dead or absent → stale (start clears; era-bound, inert — `supervision.py:534-540`); `<dir>.supervision.jsonl`: every line JSON-parses | stale stop request → **pass** with note naming the cleaner; journal all-parses → pass; **torn FINAL line** → pass with note (the known crash-tear shape — appends are single-write+fsync, a crash can tear exactly the last line); **unparseable non-final line** → **fail** (only reachable by tampering — mid-file tears cannot occur by construction, so the row says so) |

`ok` = no `fail` AND no `unknown` row. **Exit contract: 0 iff `ok`, else 1**
(`raise click.exceptions.Exit(1)`, the `verify` command's convention). The
UNKNOWN-exits-1 ruling, with its reason inline (G4 discipline): scripts gate actions
on doctor — a pre-`start` gate that reads `unknown` as healthy invites spawning a
second contender over an unverifiable pidfile, which is exactly the refusal
`start` itself makes (`cli/lifecycle.py:458-459` refuses on `unknown`/`desync`).
Operators read the verdict WORDS (rows keep `fail` ≠ `unknown` distinct); scripts
read the exit code / `ok`. One contract, both consumers — no `--strict` flag.
`unknown` is reachable only through D3 (the identity lattice is the only
genuinely three-valued input; every other check's inputs are binary at-rest facts).

**What doctor deliberately does NOT check** (a guard states what it does not catch):
no live-process environment cross-check (structurally unreadable on darwin; the env
check is at-rest only); no schema-drift verdict (D1 reports integrity only — a
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

`benchweave logs --data-dir DIR [--lines N]` (default 50). Resolution ladder, in
order, from inputs only:

1. **pidfile present** → its `log_destination` field:
   - a path → tail that file (`<dir>.log` under `start`); seek-based tail bounded by
     `lines` (windowed read from `max(0, size - 64 KiB)`, doubling on undercount —
     never a whole-file read; decode `errors="replace"`, the `_log_tail` precedent
     `cli/lifecycle.py:580-584`). Unreadable → typed `logs_unreadable:` refusal.
   - `"journal"` → `journalctl --no-pager -n <N> -u benchweave` as a fixed-argv
     subprocess (the atrest `whoami`/`icacls` in-tree subprocess precedent: absolute
     or PATH-resolved binary, fixed arguments, bounded timeout). `journalctl` not
     resolvable on the host → typed `logs_journal_unavailable:` refusal naming the
     unit — the inc2 record's "implement or degrade loudly", degraded loudly.
   - `"stderr"` → typed `logs_destination_stderr:` refusal: the daemon was started
     foreground (its bytes went to a terminal this command cannot recover), or the
     pidfile predates §0.1's journal detection; the refusal names `journalctl -u
     benchweave` as the thing to try under systemd.
2. **pidfile absent** → if `<dir>.log` exists, tail it and REPORT the resolution as
   post-mortem (a crash leaves the pidfile behind — `stop`'s stale path clears it —
   so absent usually means never-started-in-`start`-mode or foreground; the sibling
   file is still the honest post-mortem source when it exists). Else typed
   `logs_no_destination:` refusal.

Output: the tail's lines to stdout; `--json` wraps `{"destination": …, "unit"?…,
"lines": […]}`. **No `--follow`** (§8 defers it: streaming needs subprocess
lifecycle + interrupt semantics + a Windows story; `tail -f` / `journalctl -f` exist
and the operator has them). **The token-file exclusion, structurally**: the
destination candidate set is exactly {pidfile `log_destination`, `<dir>.log`} — the
SDK's `<bindings>.tokens` (and any credential file) is never a candidate, so `logs`
cannot display it even by misconfiguration (obligation 11 already pins the prose;
this is the mechanism that makes it true). An arm pins it (S8).

## 3. The SDK twins (`benchweave_sdk_server doctor` / `logs`)

One standard, per-surface application (inc2 §5's table deferred doctor/logs for BOTH
surfaces; the twin lands in the SDK repo's `lifecycle.py`, wired like its siblings —
`cli.py`'s start/stop/status pattern: `bindings_path(bindings)`, payload JSON to
stdout, `LifecycleError` → stderr + exit 1):

- **`doctor`** — four checks over the twin family (`<bindings>.pid/.log/.tokens/
  .supervision.jsonl`, `sdk lifecycle.py:103-120`): pid identity (the twin lattice
  `verify_identity`, `sdk lifecycle.py:311-335` — no hold exists to cross-check, so
  `unknown` is ticks-unobtainable on either side), log destination resolvability
  (pidfile field / `<bindings>.log` sibling), **tokens-file 0600** (the ONE
  credential-carrying exception in the family's orbit — the perms check is the whole
  reason this check exists SDK-side; wrong perms → fail; the bearer VALUE is never
  in output, key names and paths only), and journal parseability (D7's rule). Same
  exit contract (0 iff no fail/unknown; the twin lattice's `not-ours` → fail,
  `unknown` → unknown/exit 1). No store/hold/env/unit checks — nothing to probe
  (the recorded divergences: no store, no service install).
- **`logs <project> [--bindings …] [--lines N]`** — resolution: pidfile
  `log_destination` path → tail; `"stderr"` → typed refusal (no journal leg in the
  twin: `service install` is refused on this surface, so no unit name exists to
  query); pidfile absent + `<bindings>.log` exists → post-mortem tail; else typed
  refusal. Tokens file never a candidate (S8's arm).

## 4. Invariant walk

- **CTL-1..10, CTL-11: UNTOUCHED.** No ladder motion, no verdict writes, no
  terminal-record adjacency. Doctor reads the sidecar family; `logs` renders one
  file or one fixed-argv subprocess. CTL-11's outcome-blind clause gains nothing to
  obey — nothing in inc4 acts.
- **STO-3: EXTENDED by a one-clause rider** (lands with inc4's diff): doctor and
  logs are read-only, non-hold-taking readers of the store-at-rest and the
  supervision family — doctor's store read is the `verify`-precedent `mode=ro`
  probe, deliberately NOT an at-rest hold acquisition, so triage works while a live
  coordinator holds the store; neither writes any file. (The existing rider already
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
- **A06/A07: doctor writes nothing** — no journal rows, no sidecar touches; the
  audit trail is not a dependency of triage and triage is not an audit event.
- **G0 discipline:** doctor/logs never print env-file VALUES or token material
  (key names and paths only); arms assert the secret/token strings are ABSENT from
  combined output (D7-gateway, S6-SDK).

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
| G2 | healthy at-rest (real `atrest.setup` store: env file 0600, no pidfile, hold free) | every row `pass` (notes on D4/D5/D6); exit 0; sidecar family mtimes UNCHANGED across the run (structural read-only pin) |
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

**SDK arms** (`tests/server/test_lifecycle.py` additions): S5 doctor happy path
(staged pidfile self + log + tokens 0600 → all pass, exit 0) · S6 tokens file chmod
0644 → `fail` row, bearer VALUE absent from output · S7 logs tails a staged
`<bindings>.log` · S8 logs with a POISONED tokens file (read_text raising on it via
monkeypatch) still completes — the tokens file is structurally never a destination
candidate.

**RED controls (the fluff-proof part), neutralize at ONE site each:** (a) the 0600
perms check → G7 and S6 must FAIL; (b) the integrity probe (force `[]`) → G9 must
FAIL; (c) the identity verdict (force `ours`) → G4/G5/G6 must FAIL; (d) destination
resolution (force the `.log` path) → X3/X4 must FAIL; (e) SDK-side, the tokens-perms
check → S6 must FAIL. Restored, all pass.

**SHIP =** G1-G11 + X1-X5 + S5-S8 green with typed outcomes as tabled; all five RED
controls red-then-green; fast lane + full battery green in BOTH repos; the docs
obligations walked in the same train (operator-guide CLI reference + README command
list, gateway repo; the SDK repo's own docs/README rows; obligation 11's
`logs`-never-displays-tokens prose is already committed and inc4 makes it
mechanically true); standards tripwires green. **KILL =** any arm failing after one
fluke re-run; any control staying green while neutralized (the arm tests nothing —
redesign, do not merge); a secret or token value EVER appearing in doctor/logs
output (G0 class — kill on sight); doctor ever taking the hold or writing any file
(G2's mtime pin failing is this kill firing). **UNDERPOWERED =** the real
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
  than the daemon: the `-shm` is unreadable → the open refuses). This is a CORRECT
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
- **R5 `JOURNAL_STREAM` spoofed by hand produces a `journal` pidfile on a
  non-systemd host.** Harmless: `logs` degrades typed at the missing journalctl;
  doctor's D6 passes with the unit name carried. Disclosed here.
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
3. **The launchd stderr gap** (§0.2) → gateway issue: render `StandardErrorPath`
   (+ the `UserName` question it forces) into the plist template; trigger: the first
   darwin launchd deployment (until then doctor's D5 note is the honest disclosure).
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
> permissions fork this increment does not own). F3 ADOPTED — the 4-check SDK
> doctor twin (one standard, per-surface application). Redirect open until the
> build dispatches. before the record commits

- **Fork 1 — does `unknown` exit 1?** Recommended: YES (§1.2 — the conservative
  gate; scripts gating `start` on doctor must not read an unverifiable pidfile as
  healthy). Alternative: `unknown` → exit 0 with `ok=false`-but-zero (scripts
  friendlier on ticks-unobtainable platforms; weaker).
- **Fork 2 — the launchd stderr gap.** Recommended: disclose-only + issue home
  (§8.3). Alternative: render `StandardErrorPath` (+ `UserName`) into the plist NOW
  — closes the gap structurally but opens the root-owned-log permissions fork inside
  the train's last increment.
- **Fork 3 — SDK doctor breadth.** Recommended: the four-check twin (§3 — cheaper
  than a recorded refusal reason, and the tokens-perms check is genuinely useful).
  Alternative: refuse `doctor` on the SDK surface like `service install` (one less
  twin; needs its recorded divergence reason).

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
payload with one spelling. Doctor's D2/D3/D6 rows are MAPPINGS of that payload —
two surfaces over one derivation can never disagree (G4: a set named in prose is
regenerable from a mechanism). Re-deriving in `diagnose.py` would fork the lattice
call sites for zero gain; the composition IS the precedent extension (§0.3).
