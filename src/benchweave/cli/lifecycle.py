"""The lifecycle verb implementations (issue #422 increment 3).

``stop`` / ``start`` / ``restart`` / ``status --data-dir`` / ``service
install`` — the operator surface over :mod:`benchweave.supervision` (the
protocol) and the daemon's doorbell. The design authority is
``.claude/deep-review/2026-10-08-issue422-inc2-supervision-design.md``
§3-§4; the acceptance arms are ``tests/cli/test_lifecycle.py``.

Division of truth, restated where it bites the CLI: the daemon owns every
numeric authority (the protective deadline is computed from commissioned
documents in the daemon and STATED in its verdict — the CLI waits to that
plus a margin, never re-derives it; A02). The CLI owns the journal
(``.supervision.jsonl`` has exactly one writer per file — F2 fold) and
the escalation rung 3 (SIGKILL), whose intent row is written BEFORE the
kill, proceed-on-failure, with the non-zero exit disclosing a failed
append (F9 fold).
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from benchweave import supervision
from benchweave.cli.atrest import DB_NAME
from benchweave.state.hold import StoreHeldError, daemon_holds, holder_info

#: The CLI's verdict-wait bound (the daemon's poll cadence is ≤1 s; the
#: decision itself is sub-second). A service parameter, not a bench
#: envelope (A02 governs the protective window, which the DAEMON states).
VERDICT_WAIT_S = 15.0

#: The in-tree drain's join window — the lifespan's own
#: ``worker.join(timeout=5.0)`` (record §0.1) — one addend of the
#: plain exit-wait formula below (G10).
DRAIN_JOIN_S = 5.0

#: Schedule slack — the second addend: process teardown beyond the join
#: and the connection close (atexit chains, sidecar removals) observed
#: well under this on the arms' hosts; the bound only decides the CLI's
#: typed stop_timeout, never a physical envelope (G10).
EXIT_SLACK_S = 15.0

#: The margin the CLI adds PAST the verdict-stated protective deadline
#: before escalating (record §3.3: "the CLI waits to that plus a margin").
PROTECTIVE_MARGIN_S = 10.0

#: The post-deadline drain allowance before the SIGKILL rung fires, and
#: the bounded exit-wait after the kill.
KILL_WINDOW_S = 30.0

#: ``start``'s readiness window (record §4.1: bounded, 30 s).
START_READINESS_S = 30.0

#: The conventional unit/plist destinations (root-owned; an unprivileged
#: render refuses truthfully and names ``--unit-output``).
UNIT_DEFAULT = Path("/etc/systemd/system/benchweave.service")
PLIST_DEFAULT = Path("com.benchweave.gateway.plist")


def _template(name: str) -> Path:
    """A deploy template, checkout-first then the packaged copy (the
    vendoring.py pattern, applied to the deploy tree): the checkout's
    ``deploy/`` is the editable source; a wheel install carries the two
    templates under ``benchweave/_vendored/deploy/`` (the force-include
    rows in pyproject)."""
    checkout = Path(__file__).resolve().parents[3] / "deploy"
    for root in (checkout, _packaged_deploy_root()):
        if root is None:
            continue
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise LifecycleError(
        f"service_install_refused_template_missing: the {name} template "
        "resolves from neither the checkout's deploy/ tree nor the "
        "packaged copy — reinstall the distribution"
    )


def _packaged_deploy_root() -> Path | None:
    from importlib.resources import files

    return Path(str(files("benchweave") / "_vendored" / "deploy"))


def unit_template() -> Path:
    """The systemd unit template (tests and the CI rehearsal read it too)."""
    return _template("systemd/benchweave.service.template")


def plist_template() -> Path:
    """The launchd plist template."""
    return _template("launchd/com.benchweave.gateway.plist.template")
#: The unit's EnvironmentFile default (the deploy example's path).
UNIT_ENV_FILE = "/etc/benchweave/benchweave.env"

_POSIX = sys.platform != "win32"


class LifecycleError(RuntimeError):
    """A typed lifecycle refusal (the message carries the prefix)."""


def _db(data_dir: Path) -> Path:
    return Path(data_dir) / DB_NAME


def _pid_alive(pid: int) -> bool:
    return supervision.probe_process(pid) == "running"


def _still_owns(db: Path, pid: int) -> bool:
    """Post-kill liveness: probe AND pidfile AND the hold — a SIGKILLed
    process releases the flock even before its parent reaps it, so a
    zombie (probe reads running) with a free hold is DEAD for every
    purpose that matters here."""
    return (
        _pid_alive(pid)
        and supervision.pid_path(db).exists()
        and daemon_holds(db)
    )


def _wait_verdict(db: Path, timeout: float) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = supervision.read_stop_file(db)
        if record is not None and "status" in record:
            return record
        time.sleep(0.2)
    return None


def plain_exit_wait_s(verdict: dict[str, Any]) -> float:
    """The plain-stop exit-wait bound, DERIVED per the formula the record
    documents (G10): the daemon's stated graceful-shutdown timeout
    (``graceful_timeout_s`` in the accepted verdict — the commissioned
    ceiling + 30 s, else the 90 s manager default; the numeric authority
    stays in the daemon, A02) plus the in-tree drain join (5 s) plus
    schedule slack. A verdict without the field (an older daemon, a
    hand-driven verdict) falls back to the manager-default arithmetic.
    The retired fixed ``120 s`` sat inside a 100 s graceful timeout plus
    the join with nothing left for slack — the false-``stop_timeout``
    class above ~70 s commissioned ceilings."""
    stated = verdict.get("graceful_timeout_s")
    graceful = (
        float(stated)
        if isinstance(stated, (int, float)) and not isinstance(stated, bool)
        else float(MANAGER_DEFAULT_STOP_S + TIMEOUT_STOP_MARGIN_S)
    )
    return graceful + DRAIN_JOIN_S + EXIT_SLACK_S


def _copy_terminal_observations(
    db: Path, verdict: dict[str, Any], seen: set[str]
) -> None:
    """Journal the verdict's terminal_observed fields as they appear (the
    CLI is the sole journal writer — rung 2's quote, copied on
    observation, F1/F2 folds)."""
    for row in verdict.get("terminal_observed", []) or []:
        run_id = str(row.get("run_id", ""))
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        supervision.journal_append(
            db,
            "terminal_observed",
            run_id=run_id,
            outcome=row.get("outcome"),
            safe_state=row.get("safe_state"),
            source=str(row.get("source", "")),
        )


def _copy_protective_cancel(
    db: Path, verdict: dict[str, Any], seen: set[str]
) -> None:
    """G15(a): journal the verdict's `protective_cancel` fields like
    terminal_observed — on EVERY verdict refresh, once per run. The
    daemon's cancel set lands in a LATER verdict write than the accepted
    verdict (the cancels happen between them), so a CLI that journals
    only the first read misses the row entirely."""
    cancel = verdict.get("protective_cancel") or {}
    ids = [str(r) for r in cancel.get("run_ids", [])]
    fresh = [r for r in ids if r not in seen]
    if not fresh:
        return
    seen.update(fresh)
    supervision.journal_append(db, "protective_cancel", run_ids=sorted(fresh))


# --- stop (record §3.3) ------------------------------------------------------------


def stop(data_dir: Path, *, protective: bool = False) -> dict[str, Any]:
    """The stop verb: the three paths over the doorbell protocol.

    Returns the report payload; raises :class:`LifecycleError` on every
    typed refusal (the CLI renders the message and exits non-zero)."""
    data_dir = Path(data_dir)
    db = _db(data_dir)
    identity = supervision.verify_gateway_identity(db)
    if identity.verdict == "absent":
        if daemon_holds(db):
            holder = holder_info(db) or {}
            label = str(holder.get("label", ""))
            # G9: the holder-label verdict is LABEL-AWARE — a demo or
            # evidence composition is an unsupervised lifespan holder
            # (record §3.2's F4 fold); its stop story is its own command,
            # never a service manager's.
            if label.startswith(("gw-cli-demo", "gw-cli-evidence")):
                hint = (
                    " — stop the demo/evidence command that holds it (its "
                    "own process; it is not a supervised gateway)"
                )
            else:
                hint = (
                    " — if a service manager owns this gateway, stop it "
                    "there (e.g. systemctl stop benchweave)"
                )
            raise LifecycleError(
                "supervision_hold_held: the store is held by "
                f"{label or 'an unidentified live holder'} but no pidfile "
                f"exists{hint}; nothing was signaled"
            )
        supervision.journal_append(db, "stop_noop", reason="no pidfile")
        return {"stopped": False, "status": "not_running"}
    if identity.verdict == "dead":
        supervision.remove_pidfile(db)
        stop_file = supervision.stop_path(db)
        try:
            stop_file.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        supervision.journal_append(db, "stale_sidecars_cleared")
        return {"stopped": False, "status": "not running (cleared stale sidecars)"}
    if identity.verdict != "ours":
        raise LifecycleError(identity.detail)

    pid = int(identity.pid or 0)
    mode = "protective" if protective else "plain"
    supervision.write_stop_request(
        db,
        mode=mode,
        actor_pid=os.getpid(),
        # S1's era binding (the shared shape the sdk lane flagged): the
        # request names the launch it targets — the next daemon over
        # this data dir refuses to consume it, and `start` clears any
        # unconsumed leftover before spawning.
        target_pid=pid,
    )
    signal_name = "file-poll-only"
    if _POSIX:
        supervision._signal_pid(pid, signal.SIGTERM)
        signal_name = "SIGTERM"
    supervision.journal_append(
        db, "stop_requested", mode=mode, target_pid=pid, signal_name=signal_name
    )

    verdict = _wait_verdict(db, VERDICT_WAIT_S)
    if verdict is None:
        raise LifecycleError(
            f"{supervision.STOP_TIMEOUT} no verdict within {VERDICT_WAIT_S:.0f}s "
            f"of the request ({supervision.stop_path(db)}) — the daemon may "
            "be wedged; verify before acting further"
        )
    status = str(verdict.get("status"))
    consumed = str(verdict.get("mode", mode))
    note = ""
    if consumed != mode:
        note = (
            f" {supervision.STOP_MODE_SUPERSEDED} this CLI requested {mode} "
            f"but the consumed request was {consumed}; exactly one action "
            "occurred"
        )

    if status == "refused":
        run_ids = [str(r) for r in verdict.get("run_ids", [])]
        states = verdict.get("states", {})
        supervision.journal_append(db, "refusal_observed", run_ids=run_ids)
        raise LifecycleError(
            f"{supervision.STOP_REFUSED_RUN_ACTIVE} runs {run_ids} are live "
            f"({states}); the gateway is still serving and nothing was "
            f"stopped or recorded{note}"
        )
    if status != "accepted":
        raise LifecycleError(
            f"{supervision.STOP_TIMEOUT} the daemon answered an unexpected "
            f"verdict status {status!r}{note}"
        )

    if consumed == "protective":
        cancel_seen: set[str] = set()
        _copy_protective_cancel(db, verdict, cancel_seen)
    else:
        cancel_seen = set()
    seen: set[str] = set()
    _copy_terminal_observations(db, verdict, seen)

    # The exit wait: bounded by the mode's own arithmetic. Exit is the
    # pidfile GONE or the probe dead — an unreaped child of some other
    # parent reads "running" to signal-0 as a zombie, but a clean shutdown
    # removed its own pidfile (the record's disclosed zombie note).
    if consumed == "protective":
        deadline_wall = str(verdict.get("protective_deadline_wall", ""))
        try:
            from datetime import UTC, datetime

            parsed = datetime.fromisoformat(deadline_wall.replace("Z", "+00:00"))
            bound = (
                parsed - datetime.now(UTC)
            ).total_seconds() + PROTECTIVE_MARGIN_S + KILL_WINDOW_S
        except ValueError:
            bound = plain_exit_wait_s(verdict)
        bound = max(bound, PROTECTIVE_MARGIN_S)
    else:
        bound = plain_exit_wait_s(verdict)
    deadline = time.monotonic() + bound
    exited = False
    while time.monotonic() < deadline:
        # Battery-caught ordering fix (the G15(a) family): read the
        # refreshed verdict BEFORE the exit check in every iteration —
        # the exit observation (pidfile gone / probe dead) can only
        # follow the daemon's final verdict write, so a check-first
        # loop could break past a write it never read under load.
        refreshed = supervision.read_stop_file(db)
        if refreshed is not None and "status" in refreshed:
            verdict = refreshed
            _copy_terminal_observations(db, verdict, seen)
            _copy_protective_cancel(db, verdict, cancel_seen)
        if not supervision.pid_path(db).exists() or not _pid_alive(pid):
            exited = True
            break
        time.sleep(0.2)
    if exited:
        # The post-loop final read closes the nano-window: a verdict
        # written between the last in-loop read and the exit observation
        # is still ON DISK (the daemon never deletes the stop file) and
        # is journaled here, never skipped.
        final = supervision.read_stop_file(db)
        if final is not None and "status" in final:
            verdict = final
            _copy_terminal_observations(db, verdict, seen)
            _copy_protective_cancel(db, verdict, cancel_seen)

    if not exited:
        if consumed != "protective":
            raise LifecycleError(
                f"{supervision.STOP_TIMEOUT} the daemon accepted but did not "
                f"exit within {bound:.0f}s ({supervision.pid_path(db)}); "
                "verify the gateway before acting further"
            )
        # Rung 3 (§3.5): the intent row BEFORE the kill (PLANNED class,
        # F9 fold), then one kill, then a bounded exit-wait.
        raise _rung3_kill(db, pid, verdict)

    # Exited: verify the hold released and the sidecar cleaned.
    if daemon_holds(db):
        raise LifecycleError(
            f"{supervision.HOLD_DESYNC} the daemon exited but the store "
            "hold is still held — verify no second process owns the bench"
        )
    supervision.journal_append(db, "stopped", mode=consumed)
    payload: dict[str, Any] = {
        "stopped": True,
        "status": "accepted",
        "mode": consumed,
        "pid": pid,
        "deadline": verdict.get("protective_deadline_wall"),
    }
    if verdict.get("deadline_exceeded"):
        payload["deadline_exceeded"] = True
    if verdict.get("sweep_disclosure"):
        payload["sweep_disclosure"] = verdict["sweep_disclosure"]
    if note:
        payload["note"] = note.strip()
    return payload


# --- start / restart (record §4.1) --------------------------------------------------


def _rung3_kill(db: Path, pid: int, verdict: dict[str, Any]) -> LifecycleError:
    """Rung 3 (§3.5, G6 fold): the intent row BEFORE the kill (PLANNED
    class, F9), then ONE kill — POSIX ``SIGKILL``, Windows
    ``os.kill(pid, 9)`` (the OS routes it to TerminateProcess: the
    capability exists, so the kill is SENT on every platform, never
    skipped-while-asserted) — then the bounded exit-wait; the row's
    signal field names what actually went out."""
    run_ids = [str(r) for r in verdict.get("run_ids", [])]
    signal_name = supervision.sigkill_signal_name()
    append_failed = False
    try:
        supervision.journal_append(
            db,
            "sigkill_sent",
            target_pid=pid,
            run_ids=run_ids,
            run_ids_source="last_verdict" if run_ids else "unknown",
            reason="protective_deadline_exceeded",
            signal_name=signal_name,
        )
    except OSError:
        append_failed = True
    try:
        sent = supervision.send_sigkill(pid)
    except ProcessLookupError:
        # G15(b): the daemon exited between the CLI's check and the kill
        # — a TYPED disclosure, never a raw ProcessLookupError traceback.
        # The non-zero exit stands: the deadline was exceeded with no
        # terminal record observed, and the next boot's sweep owns the
        # run's outcome.
        return LifecycleError(
            "supervision_sigkill: the protective deadline "
            f"({verdict.get('protective_deadline_wall')}) passed with no "
            f"terminal record, and the process exited before the kill "
            f"could land (pid {pid}) — the run stays non-terminal in "
            "the store and the NEXT boot's sweep records it interrupted"
            + ("; the journal append FAILED before the kill" if append_failed else "")
        )
    kill_deadline = time.monotonic() + KILL_WINDOW_S
    while time.monotonic() < kill_deadline and _still_owns(db, pid):
        time.sleep(0.2)
    still = _still_owns(db, pid)
    return LifecycleError(
        "supervision_sigkill: the protective deadline "
        f"({verdict.get('protective_deadline_wall')}) passed with no "
        f"terminal record; the CLI sent {sent} to pid {pid} (reason: "
        "protective_deadline_exceeded) — the run stays non-terminal in "
        "the store and the NEXT boot's sweep records it interrupted"
        + ("; the journal append FAILED before the kill" if append_failed else "")
        + ("; the process is STILL ALIVE" if still else "")
    )


def start(data_dir: Path, *, host: str, port: int) -> dict[str, Any]:
    """The start verb: pre-spawn gates, detached spawn, hold-acquired
    readiness with liveness polling and the end-of-wait re-check (F5/F8
    folds)."""
    # W7: resolve --data-dir to absolute BEFORE deriving/recording the log
    # destination, so the recorded log_destination field is absolute by
    # construction — a same-named file at a later ``logs``-invoker's cwd
    # can never be silently tailed through a relative recorded field.
    data_dir = Path(data_dir).resolve()
    db = _db(data_dir)
    identity = supervision.verify_gateway_identity(db)
    if identity.verdict == "ours":
        raise LifecycleError(
            f"{supervision.ALREADY_RUNNING} the pidfile verifies pid "
            f"{identity.pid} as this gateway ({supervision.pid_path(db)})"
        )
    if identity.verdict in ("unknown", "desync"):
        raise LifecycleError(identity.detail)
    if daemon_holds(db):
        holder = holder_info(db) or {}
        hint = ""
        if Path("/etc/systemd/system/benchweave.service").exists():
            hint = " — a systemd unit is installed; use systemctl"
        raise LifecycleError(
            "supervision_hold_held: the store is held by "
            f"{holder.get('label', 'an unidentified live holder')}"
            f" (pid {holder.get('pid', '?')}) and no pidfile names a "
            f"startable gateway{hint}; refusing to spawn a second contender"
        )
    if not db.is_file():
        raise LifecycleError(
            f"no store at {db} — run `benchweave setup --data-dir "
            f"{data_dir}` first (a data-dir with no {DB_NAME} must not "
            "silently create a fresh store)"
        )
    stale = supervision.read_stop_file(db)
    if stale is not None and "status" not in stale:
        # S1's era binding, the start leg: a request a dead launch never
        # consumed is not the next launch's to honor — clear it (typed
        # journal note) so the boot is clean; a stale VERDICT is not a
        # request and stays (the next stop's request write replaces it).
        with contextlib.suppress(OSError):
            supervision.stop_path(db).unlink()
        supervision.journal_append(
            db,
            "stale_stop_request_cleared",
            target_pid=stale.get("target_pid"),
        )
    log = supervision.log_path(db)
    supervision.journal_append(
        db, "start_requested", host=host, port=port, log=str(log)
    )
    env = os.environ.copy()
    # §2.3: under start, <dir>.log is THE named daemon log destination.
    env["BENCHWEAVE_LOG_DESTINATION"] = str(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(
        log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
    )
    try:
        proc = subprocess.Popen(  # noqa: S603 — fixed argv, this interpreter
            [
                sys.executable,
                "-m",
                "benchweave",
                "serve",
                "--data-dir",
                str(data_dir.resolve()),
                "--host",
                host,
                "--port",
                str(port),
            ],
            start_new_session=True,  # §4.1: parented by init, not this CLI
            stdout=subprocess.DEVNULL,
            stderr=handle,
            env=env,
            cwd=str(Path.cwd()),
        )
    finally:
        os.close(handle)  # the child holds its own copy; the parent's closes
    deadline = time.monotonic() + START_READINESS_S
    last = "the pidfile never appeared"
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                tail = _log_tail(log)
                supervision.journal_append(
                    db, "start_failed", pid=proc.pid, rc=proc.returncode
                )
                raise LifecycleError(
                    f"start_failed: the serve child exited rc="
                    f"{proc.returncode} before readiness; log tail: {tail}"
                )
            record = supervision.read_pidfile(db)
            if record is not None and int(record["pid"]) == proc.pid:
                # F5 fold: end-of-wait liveness re-check before exit 0 —
                # a boot refusing admission seconds later must not leave a
                # success message over a dead child.
                if proc.poll() is not None:
                    raise LifecycleError(
                        "start_failed: the child died immediately after "
                        f"writing its pidfile (rc={proc.returncode}); log "
                        f"tail: {_log_tail(log)}"
                    )
                supervision.journal_append(db, "started", pid=proc.pid)
                return {
                    "started": True,
                    "pid": proc.pid,
                    "log": str(log),
                    "host": host,
                    "port": port,
                }
            last = f"pidfile names {record.get('pid') if record else None}"
            time.sleep(0.2)
        supervision.journal_append(db, "start_failed", pid=proc.pid, rc=None)
        raise LifecycleError(
            f"start_failed: no readiness within {START_READINESS_S:.0f}s "
            f"({last}); log tail: {_log_tail(log)}"
        )
    except BaseException:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        raise


def restart(data_dir: Path, *, host: str, port: int) -> dict[str, Any]:
    """stop-then-start; a stop refusal propagates (nothing starts)."""
    stopped = stop(data_dir)
    started = start(data_dir, host=host, port=port)
    return {"stopped": stopped, "started": started}


def _log_tail(path: Path, size: int = 2000) -> str:
    try:
        return path.read_text(errors="replace")[-size:].strip() or "(empty)"
    except OSError:
        return "(unreadable)"


# --- status --data-dir (fork F1) ----------------------------------------------------


def status_lifecycle(data_dir: Path) -> dict[str, Any]:
    """The lifecycle verdicts: pid identity + hold verdict + holder + log
    destination (unit presence deepens in increment 4's doctor)."""
    data_dir = Path(data_dir)
    db = _db(data_dir)
    identity = supervision.verify_gateway_identity(db)
    holder = holder_info(db)
    return {
        "data_dir": str(data_dir),
        "pid": {
            "verdict": identity.verdict,
            "pid": identity.pid,
            "gateway_id": (identity.pidfile or {}).get("gateway_id"),
            "detail": identity.detail,
        },
        "hold": {
            "held": daemon_holds(db),
            "holder": holder,
        },
        "log_destination": (identity.pidfile or {}).get("log_destination"),
    }


# --- service install (record §4.3, arm L10) ------------------------------------------


#: The margin added to the commissioned protective ceiling (the record's
#: TimeoutStopSec derivation: max safe_transition.max_duration_ms + 30 s).
TIMEOUT_STOP_MARGIN_S = 30

#: The manager default rendered when the store commissions no ceiling.
MANAGER_DEFAULT_STOP_S = 90


def commissioned_protective_max_ms(store: Any, content: Any) -> int | None:
    """Max over the store's commissioned ``safe_transition.max_duration_ms``
    (each bench's pinned policy, resolved through the content store — the
    A02 discipline: the number protects a COMMISSIONED budget when one
    exists; it is not itself a bench limit)."""
    best: int | None = None
    offset = 0
    while True:
        items, has_more = store.list_benches(limit=1000, offset=offset)
        for bench in items:
            try:
                configuration = json.loads(str(bench.get("configuration_json") or "{}"))
            except json.JSONDecodeError:
                continue
            pin = configuration.get("policy") if isinstance(configuration, dict) else None
            if not isinstance(pin, dict):
                continue
            envelope = content.get_document(str(pin.get("sha256", "")))
            document = (
                envelope.get("content") if isinstance(envelope, dict) else None
            )
            if not isinstance(document, dict):
                continue
            transition = document.get("safe_transition")
            value = (
                transition.get("max_duration_ms")
                if isinstance(transition, dict) else None
            )
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and (best is None or value > best)
            ):
                best = value
        if not has_more:
            return best
        offset += len(items)


def render_unit(data_dir: Path, *, max_ms: int | None) -> str:
    """Render the systemd unit: today's directives plus ExecStop (plain
    stop, fork F2) and the DERIVED TimeoutStopSec (commissioned max + 30 s
    — or the manager default with the disclosed comment when the store
    commissions no ceiling)."""
    text = unit_template().read_text(encoding="utf-8")
    text = text.replace("{{DATA_DIR}}", str(Path(data_dir).resolve()))
    text = text.replace("{{ENV_FILE}}", UNIT_ENV_FILE)
    if max_ms is not None:
        timeout = f"{max_ms // 1000 + TIMEOUT_STOP_MARGIN_S}s"
        text = text.replace("{{TIMEOUT_STOP_SEC}}", timeout)
    else:
        text = text.replace(
            "TimeoutStopSec={{TIMEOUT_STOP_SEC}}",
            "# TimeoutStopSec: no commissioned safe-transition ceiling in the\n"
            "# store — systemd's manager default applies (there is no\n"
            "# protective envelope to respect)",
        )
    return text


def render_plist(data_dir: Path, *, max_ms: int | None) -> str:
    """The launchd analogue with the mapping comments (§4.3): what launchd
    cannot express — ExecStop, TimeoutStopSec enforcement, RestartSec — is
    named IN the rendered file, with the doorbell named as the stop path."""
    text = plist_template().read_text(encoding="utf-8")
    text = text.replace("{{DATA_DIR}}", str(Path(data_dir).resolve()))
    note = (
        f"derived: commissioned max {max_ms} ms + 30 s"
        if max_ms is not None
        else "no commissioned ceiling; no value derived"
    )
    return text.replace("{{TIMEOUT_NOTE}}", note)


def service_install(
    data_dir: Path,
    *,
    unit_output: Path | None,
    plist_output: Path | None,
) -> dict[str, Any]:
    """Install-time renders under the at-rest hold (label
    ``service-install``; a live gateway REFUSES — install-time is
    stopped-time)."""
    from benchweave.content.store import ContentStore
    from benchweave.state.hold import StoreHold
    from benchweave.state.store import Store

    data_dir = Path(data_dir)
    # A non-darwin --plist-output is a typed refusal, not a silent skip:
    # the plist render is darwin-gated (write_plist below), so on any
    # other host this flag combination writes NOTHING while exiting 0 —
    # and the journal row would still claim service_installed. Refusing
    # before the hold names the mismatch instead.
    if plist_output is not None and sys.platform != "darwin":
        raise LifecycleError(
            "service_install_refused_plist_non_darwin: --plist-output "
            "writes the launchd plist and service install renders the "
            f"plist only on darwin — this host is {sys.platform}; drop "
            "--plist-output (the systemd unit is the deploy target here) "
            "or render the plist on a Mac"
        )
    db = _db(data_dir)
    if not db.is_file():
        raise LifecycleError(
            f"no store at {db} — run `benchweave setup --data-dir {data_dir}` first"
        )
    try:
        hold = StoreHold(db, label="service-install")
        hold.acquire()
    except StoreHeldError as error:
        raise LifecycleError(
            "service_install_refused_store_held: install-time is stopped-"
            f"time — {error}"
        ) from error
    try:
        store = Store.open(db, check_same_thread=False)
        try:
            content = ContentStore(store)
            max_ms = commissioned_protective_max_ms(store, content)
        finally:
            store.close()
    finally:
        hold.release()
    unit_target = unit_output if unit_output is not None else UNIT_DEFAULT
    # Selection semantics: an explicit --plist-output alone renders the
    # plist only; the unit rides its own default ONLY when neither output
    # was named (the conventional both-files install).
    write_unit = unit_output is not None or plist_output is None
    write_plist = sys.platform == "darwin" and (
        plist_output is not None or (unit_output is None and plist_output is None)
    )
    plist_target = (
        plist_output
        if plist_output is not None
        else (Path.home() / "Library" / "LaunchDaemons" / PLIST_DEFAULT)
    )
    written: list[str] = []
    if write_unit:
        _write_output(unit_target, render_unit(data_dir, max_ms=max_ms))
        written.append(str(unit_target))
    if write_plist:
        _write_output(plist_target, render_plist(data_dir, max_ms=max_ms))
        written.append(str(plist_target))
    supervision.journal_append(
        db,
        "service_installed",
        unit=str(unit_target) if write_unit else None,
        commissioned_max_ms=max_ms,
    )
    return {
        "unit": str(unit_target) if write_unit else None,
        "plist": str(plist_target) if write_plist else None,
        "commissioned_max_ms": max_ms,
        "timeout_stop_sec": (
            f"{max_ms // 1000 + TIMEOUT_STOP_MARGIN_S}s"
            if max_ms is not None
            else f"manager default ({MANAGER_DEFAULT_STOP_S}s)"
        ),
        "written": written,
    }


def _write_output(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as error:
        raise LifecycleError(
            f"service_install_refused_unwritable: cannot write {path} "
            f"({error}) — pass an explicit --unit-output/--plist-output or "
            "run with the privileges the conventional path needs"
        ) from error
