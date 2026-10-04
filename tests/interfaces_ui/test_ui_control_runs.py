"""The G3b runs control surface (issue #304, design record §2.4/§2.5,
acceptance arms E–J) — the run half of GW-10's eight.

Pure-function arms first (this file's opening block — the trip
predicate's matrix and the energy classifier's, with the record's
disclosed boundaries pinned), then the route arms over a REAL composed
gateway with a MUTABLE injected clock, each behavior proven RED before
its implementation (the verbatim failure text rides the commit message
and the run report).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from g3b_lattice import author_g3b_lattice
from starlette.testclient import TestClient
from ui_gateway_support import LIMITS, NOW_EPOCH, SECRET

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import SessionStore
from benchweave.interfaces.ui_control import energy_sourcing, trip_active
from benchweave.state.store import Store

_FIXTURES_PROCEDURE = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "fixtures"
    / "execution"
    / "procedure-voltage-check.json"
)


def _event(kind: str, sequence: int) -> dict[str, Any]:
    return {"kind": kind, "sequence": sequence, "at": "2026-10-03T00:00:00Z"}


# --- §2.5: the trip predicate (GW-43/54's wire-honest core) -----------------------


def test_no_trip_lifecycle_events_composes_no_protection() -> None:
    """Boundary (c): retention dropped (or never carried) any
    trip-lifecycle row — no verdict, never protection-active."""
    assert trip_active([]) is False
    assert trip_active([_event("run_changed", 1), _event("lease_changed", 2)]) is False


def test_newest_trip_lifecycle_event_decides() -> None:
    """Newest → oldest by sequence: the newest trip-lifecycle row's kind
    decides — a ``trip`` is protection-active; a ``bench_changed`` (the
    only wire shadow an applied trip_reset has) clears it."""
    assert trip_active([_event("trip", 5)]) is True
    assert trip_active([_event("trip", 5), _event("bench_changed", 7)]) is False
    assert trip_active([_event("bench_changed", 3), _event("trip", 5)]) is True
    assert trip_active([_event("trip", 5), _event("bench_changed", 7), _event("trip", 9)]) is True


def test_trip_predicate_is_order_agnostic() -> None:
    """The verdict keys on sequence, never list order — an adapter may
    hand the rows in either direction."""
    rows = [_event("run_changed", 1), _event("trip", 5), _event("bench_changed", 7)]
    assert trip_active(rows) is False
    assert trip_active(list(reversed(rows))) is False
    rows = [_event("bench_changed", 7), _event("run_changed", 1), _event("trip", 9)]
    assert trip_active(rows) is True
    assert trip_active(list(reversed(rows))) is True


def test_boundary_b_admin_change_after_a_trip_clears() -> None:
    """Disclosed boundary (b): an admin configuration activation after a
    trip also emits ``bench_changed`` and therefore ALSO clears the
    marker — the closed event def has no channel for the change kind
    (the record §2.5b err-clear boundary, pinned as disclosed)."""
    rows = [_event("trip", 5), _event("bench_changed", 7)]
    assert trip_active(rows) is False


# --- GW-52: the energy classification ---------------------------------------------


def _variant(tmp_path: Any, name: str, **kwargs: Any) -> dict[str, Any]:
    directory, _binding_sha = author_g3b_lattice(tmp_path, name=name, **kwargs)
    procedure_path = directory / "procedure-voltage-check.json"
    parsed: dict[str, Any] = json.loads(procedure_path.read_text())
    return parsed


def test_enable_true_is_energy_sourcing(tmp_path: Any) -> None:
    """R-ENERGISE-1's enabling clause: any ``invoke`` step whose input
    carries ``enabled: true`` makes the procedure energy-sourcing."""
    assert energy_sourcing(json.loads(_FIXTURES_PROCEDURE.read_text())) is True
    assert energy_sourcing(_variant(tmp_path, "energise", enabled=True)) is True


def test_explicit_false_is_de_energising(tmp_path: Any) -> None:
    """An explicit ``enabled: false`` is the de-energising class (the
    record's own shape: manual + explicit false)."""
    assert energy_sourcing(_variant(tmp_path, "deenergise", enabled=False)) is False


def test_absent_enable_field_is_de_energising(tmp_path: Any) -> None:
    """A procedure with no enable-true step (including the enable step
    with the field absent) is the de-energising class."""
    assert energy_sourcing(_variant(tmp_path, "absent", enabled="absent")) is False


def test_nested_enable_steps_are_classified(tmp_path: Any) -> None:
    """The scan recurses into ``if.then`` / ``repeat.steps`` bodies — an
    author cannot hide an enable from the classifier by nesting it."""
    base = json.loads(_FIXTURES_PROCEDURE.read_text())
    nested = {
        "id": "wrap",
        "kind": "if",
        "predicate": {"sample": "voltage", "minimum": 0.0, "maximum": 1.0},
        "then": [step for step in base["steps"] if step.get("id") == "enable"],
        "else": [],
    }
    procedure = dict(base)
    procedure["steps"] = [nested]
    assert energy_sourcing(procedure) is True
    looped = dict(base)
    looped["steps"] = [
        {
            "id": "loop",
            "kind": "repeat",
            "count": 1,
            "steps": [step for step in base["steps"] if step.get("id") == "enable"],
        }
    ]
    assert energy_sourcing(looped) is True


def test_the_setpoint_clause_is_not_derived() -> None:
    """Disclosed boundary (G3-D2): a WRITE step raising a setpoint of a
    currently-energised output is NOT classified — the clause needs live
    device state the documents are silent on, and the classifier errs
    only by rule change, never silently."""
    write_only = {
        "id": "p",
        "version": "0.1.0",
        "mode": "manual",
        "steps": [
            {
                "id": "raise",
                "kind": "write",
                "role": "supply",
                "parameter": "voltage_setpoint_v",
                "value": 5.5,
                "timeout_ms": 500,
            }
        ],
    }
    assert energy_sourcing(write_only) is False


# --- the composed-gateway rig ------------------------------------------------------


_BENCH = "sim-bench"
_CLIENT_BASE = "http://testserver:8125"
CONTROL = frozenset({"stg:observe", "stg:control"})
OBSERVE = frozenset({"stg:observe"})
_BINDING_REQUEST_ID = "req-g3b-energise"  # the variant binding's own §9 id


class _Clock:
    """One mutable epoch cell; ``iso`` renders the same instant."""

    def __init__(self) -> None:
        self.epoch = NOW_EPOCH

    def epoch_s(self) -> int:
        return self.epoch

    def iso(self) -> str:
        from datetime import UTC, datetime

        return datetime.fromtimestamp(self.epoch, tz=UTC).isoformat().replace(
            "+00:00", "Z"
        )

    def advance(self, seconds: int) -> None:
        self.epoch += seconds


def _compose(data_dir: Any, name: str, clock: _Clock, lattice_dir: Any) -> Any:
    store = Store.open(str(data_dir / f"state-{name}.sqlite"), check_same_thread=False)
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-test",
        fixtures_dir=lattice_dir,
        now_iso=clock.iso,
        now_epoch=clock.epoch_s,
    )
    app.state.g3b_store = store
    return app


def _session(
    app: Any, *, principal: str = "ui-operator", scopes: frozenset[str], ttl_s: int = 3600
) -> Any:
    sessions: SessionStore = app.state.ui_sessions
    code = sessions.mint_login_code(
        Identity(
            principal=principal,
            audience="stg",
            scopes=scopes,
            expires_at=NOW_EPOCH + 12 * 3600,
        ),
        ttl_seconds=ttl_s,
    )
    return sessions.exchange(code)


@pytest.fixture()
def energise_rig(tmp_path: Any) -> Any:
    """One composed gateway on the manual+enable-true (energy-sourcing)
    lattice, its own clock, one control-scope session."""
    clock = _Clock()
    lattice_dir, binding_sha = author_g3b_lattice(
        tmp_path, mode="manual", enabled=True, request_id=_BINDING_REQUEST_ID
    )
    app = _compose(tmp_path, "g3b-energise", clock, lattice_dir)
    with TestClient(app, base_url=_CLIENT_BASE) as client:
        record = _session(app, scopes=CONTROL)
        yield SimpleNamespace(
            app=app,
            client=client,
            clock=clock,
            binding_sha=binding_sha,
            record=record,
        )


def _get(rig: Any, path: str, record: Any) -> Any:
    return rig.client.get(
        path, cookies={"bw_session": record.session_id}, follow_redirects=False
    )


def _post(rig: Any, path: str, record: Any, data: dict[str, str]) -> Any:
    return rig.client.post(
        path,
        cookies={"bw_session": record.session_id},
        data=data,
        headers={"X-CSRF-Token": record.csrf_token},
    )


def _spy(rig: Any, name: str) -> list[str]:
    calls: list[str] = []
    operations: Operations = rig.app.state.ui_operations
    real = getattr(operations, name)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls.append(name)
        return real(*args, **kwargs)

    setattr(operations, name, wrapper)
    return calls


def _generation(rig: Any, record: Any) -> int:
    response = _get(rig, f"/ui/benches/{_BENCH}", record)
    assert response.status_code == 200
    import re

    match = re.search(r'data-bw-bench-generation>(\d+)<', response.text)
    assert match is not None, response.text[:2000]
    return int(match.group(1))


def _stage(rig: Any, record: Any, *, sha: str | None = None) -> Any:
    return _post(
        rig,
        f"/ui/benches/{_BENCH}/staging",
        record,
        data={"binding_sha256": sha or rig.binding_sha},
    )


# --- GW-50: staging (the binding selection) ----------------------------------------


def test_staging_records_the_cycle_and_the_panel_shows_it(energise_rig: Any) -> None:
    """Staging a binding records the cycle server-side; the panel marks
    it staged (§F) and shows the binding's own request id — the id every
    mutating form of this cycle will carry (GW-13's fixed id)."""
    rig = energise_rig
    response = _stage(rig, rig.record)
    assert response.status_code == 200, response.text[:500]
    assert 'data-bw-staged="true"' in response.text
    assert rig.binding_sha[:16] in response.text
    assert _BINDING_REQUEST_ID in response.text


def test_re_staging_the_same_binding_keeps_the_request_id(energise_rig: Any) -> None:
    """The staging cycle's id is the binding's own — a same-binding
    re-stage (a post-refusal retry's re-render) cannot change it."""
    rig = energise_rig
    first = _stage(rig, rig.record)
    second = _stage(rig, rig.record)
    assert first.text.count(_BINDING_REQUEST_ID) >= 1
    assert second.text.count(_BINDING_REQUEST_ID) >= 1


def test_staging_a_garbage_digest_refuses_pre_send(energise_rig: Any) -> None:
    rig = energise_rig
    response = _stage(rig, rig.record, sha="not-a-digest")
    assert response.status_code == 400, response.text[:500]
    assert 'data-bw-failure="invalid_request"' in response.text
    store: SessionStore = rig.app.state.ui_sessions
    assert store.staged_start(rig.record.session_id, _BENCH) is None


# --- GW-51: check precedes start, a staged change invalidates ----------------------


def test_check_records_the_verdict_and_the_start_gates_on_it(energise_rig: Any) -> None:
    """The check records {valid, generation, findings} for the CURRENT
    staged set; the staged start handler refuses pre-send when no check
    is on record (the §C.3 invalid_request row, no seam write)."""
    rig = energise_rig
    _stage(rig, rig.record)
    calls = _spy(rig, "run_start")
    start_response = _post(
        rig,
        f"/ui/benches/{_BENCH}/run-starts",
        rig.record,
        data={
            "request_id": _BINDING_REQUEST_ID,
            "expected_generation": str(_generation(rig, rig.record)),
        },
    )
    # RED-to-GREEN note: before the route exists this is a 404; after,
    # the no-check guard refuses pre-send — either way the run never
    # starts.
    assert "run_start" not in calls
    assert start_response.status_code == 400, start_response.text[:500]
    assert 'data-bw-failure="invalid_request"' in start_response.text

    check_response = _post(
        rig, f"/ui/benches/{_BENCH}/run-checks", rig.record, data={}
    )
    assert check_response.status_code == 200, check_response.text[:500]
    assert 'data-bw-check-state="valid"' in check_response.text
    # The start control enables only now — the no-check guard no longer
    # fires (the arm leg proceeds to its own guards below).
    store: SessionStore = rig.app.state.ui_sessions
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.check is not None
    assert staged.check["valid"] is True


def test_staged_change_clears_the_recorded_check(energise_rig: Any) -> None:
    """GW-51's invalidation: any staged change clears the recorded check
    (the record re-stages with ``check=None`` and un-arms)."""
    rig = energise_rig
    _stage(rig, rig.record)
    _post(rig, f"/ui/benches/{_BENCH}/run-checks", rig.record, data={})
    store: SessionStore = rig.app.state.ui_sessions
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.check is not None
    _stage(rig, rig.record)  # same binding, a deliberate re-stage
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None
    assert staged.check is None
    assert staged.armed is False


# --- GW-52: the arm step composes the confirm from the documents -------------------


def _check(rig: Any, record: Any) -> Any:
    return _post(rig, f"/ui/benches/{_BENCH}/run-checks", record, data={})


def test_arm_composes_the_armed_confirm_from_the_documents(energise_rig: Any) -> None:
    """Arm (H): the armed fragment states the effect, the exact values
    with units, and the target — composed from the documents per §E.1's
    armed-text shape — and no seam MUTATION ran (reads only)."""
    rig = energise_rig
    _stage(rig, rig.record)
    # Two named live lists, asserted separately: ``_spy`` returns the list
    # it appends to, and concatenating two spy results snapshots dead empty
    # copies — the repaired shape keeps each assertion live (kill rule: an
    # assertion that cannot fail polices nothing).
    calls_start = _spy(rig, "run_start")
    calls_lease = _spy(rig, "lease_create")
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 200
    assert 'data-bw-confirm="armed"' in response.text
    assert "the output will be energised" in response.text
    assert "5 V" in response.text
    assert "psu ch1" in response.text
    assert "Confirm to proceed." in response.text
    assert "Confirm: Start run" in response.text
    assert ">Cancel</button>" in response.text
    assert not calls_start
    assert not calls_lease


def test_arm_records_the_armed_flag(energise_rig: Any) -> None:
    rig = energise_rig
    _stage(rig, rig.record)
    _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    store: SessionStore = rig.app.state.ui_sessions
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.armed is True
    # GW-51's invalidation reaches the arm too: a staged change un-arms.
    _stage(rig, rig.record)
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.armed is False


def test_disarm_keeps_the_staged_set_and_clears_the_arm(energise_rig: Any) -> None:
    """No auto-disarm has an inverse: the operator's Cancel (the disarm
    POST) clears the armed flag and keeps the staged binding and the
    recorded check (the staged intent is never silently discarded)."""
    rig = energise_rig
    _stage(rig, rig.record)
    _check(rig, rig.record)
    _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/disarm", rig.record, data={})
    assert response.status_code == 200
    store: SessionStore = rig.app.state.ui_sessions
    staged = store.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None
    assert staged.armed is False
    assert staged.check is not None
    assert 'data-bw-staged="true"' in response.text


def test_arm_with_nothing_staged_refuses_pre_send(energise_rig: Any) -> None:
    rig = energise_rig
    calls_start = _spy(rig, "run_start")
    calls_check = _spy(rig, "run_check")
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 400
    assert 'data-bw-failure="invalid_request"' in response.text
    assert not calls_start
    assert not calls_check


def test_arm_with_an_unstored_binding_refuses(energise_rig: Any) -> None:
    """An unstored digest stages fine (run_check will report the
    finding), but the arm's document chain refuses ``not_found`` — the
    honest §C.3 row, rendered."""
    rig = energise_rig
    _stage(rig, rig.record, sha="e" * 64)
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 404
    assert 'data-bw-failure="not_found"' in response.text


# --- GW-56 at arm (the J-family guard fires on the arm step too) -------------------


def _take_lease(
    rig: Any, record: Any, *, duration_ms: int, generation: int | None = None
) -> Any:
    resolved = generation if generation is not None else _generation(rig, record)
    return _post(
        rig,
        f"/ui/benches/{_BENCH}/leases",
        record,
        data={"duration_ms": str(duration_ms), "expected_generation": str(resolved)},
    )


def test_gw56_refuses_the_arm_when_the_bound_exceeds_attention(
    energise_rig: Any,
) -> None:
    """Manual mode, bound (max_body_ms + max_protection_ms = 10 000 ms)
    vs attention remaining: with a live held lease with 5 000 ms
    remaining (session hours), the bound exceeds the attention remainder
    — the arm refuses PRE-SEND (no mutating seam call), rendering the
    bound, both remaining figures, and the clearing actions."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=5_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    calls_start = _spy(rig, "run_start")
    calls_lease = _spy(rig, "lease_create")
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 403, response.text[:800]
    assert 'data-bw-failure="policy_denied"' in response.text
    assert "10000" in response.text
    assert "5000" in response.text
    assert "benchweave ui-login" in response.text
    assert not calls_start
    assert not calls_lease


def test_gw56_arm_boundary_equal_is_allowed(energise_rig: Any) -> None:
    """The boundary: bound exactly equal to the attention remainder is
    allowed — the arm composes (the seam still decides the start)."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=10_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    response = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert response.status_code == 200, response.text[:500]
    assert 'data-bw-confirm="armed"' in response.text


# --- GW-42: observe sessions render the panel disabled with no-authority -----------


def test_observe_session_renders_the_panel_controls_disabled(energise_rig: Any) -> None:
    """§2.2's observe posture: every mutating control of the staging
    panel renders disabled with the §C.2 no-authority reason and its
    visible label."""
    rig = energise_rig
    observer = _session(rig.app, principal="ui-observer", scopes=OBSERVE)
    _stage(rig, rig.record)  # the operator stages; the observer only reads
    response = _get(rig, f"/ui/benches/{_BENCH}", observer)
    assert response.status_code == 200
    assert 'data-bw-disabled-reason="no-authority"' in response.text
    assert "No lease or policy authority" in response.text


# --- GW-12/13: double-submit and fire-time guards (arms E/G) ---------------------


def _run_started_id(response: Any) -> str:
    import re

    match = re.search(r'data-bw-run-started="([^"]+)"', response.text)
    assert match is not None, response.text[:800]
    return match.group(1)


def test_e_two_identical_confirms_start_exactly_one_run(energise_rig: Any) -> None:
    """Arm E (§6.E): Arm then two identical Confirm POSTs (same cookie,
    same request id): exactly one run exists in the store, both
    responses carry the same run id, the second being the §9 replay.
    The binding's own request id IS the staging cycle's §9 id (the
    keep-record-on-start ruled deviation: the staged record stays as
    the replay handle, so the second POST reaches the seam and replays
    instead of being refused by the guards)."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=10_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    payload = {
        "request_id": _BINDING_REQUEST_ID,
        "binding_sha256": rig.binding_sha,
        "expected_generation": str(generation),
    }
    first = _post(rig, f"/ui/benches/{_BENCH}/run-starts", rig.record, data=payload)
    assert first.status_code == 200, first.text[:800]
    second = _post(rig, f"/ui/benches/{_BENCH}/run-starts", rig.record, data=payload)
    assert second.status_code == 200, second.text[:800]
    store: Store = rig.app.state.g3b_store
    runs = store.list_run_states(_BENCH)
    assert len(runs) == 1, runs
    assert _run_started_id(first) == _run_started_id(second)


def test_g_a_trip_while_armed_refuses_the_confirm_without_a_seam_call(
    energise_rig: Any,
) -> None:
    """Arm G (§6.G), planted-event induction (labelled: the belt of the
    two inductions the record names — the seam's own events_get reads
    the same stream the row is planted on): Arm, then a planted trip
    row, then the Confirm POST — NO seam run_start call, the armed
    state re-rendered with the §E.1 protection-active disable and its
    guard note, no auto-disarm (Cancel stays enabled), and the armed
    flag survives (a departing guard re-enables on the next render)."""
    rig = energise_rig
    generation = _generation(rig, rig.record)
    _take_lease(rig, rig.record, duration_ms=10_000, generation=generation)
    _stage(rig, rig.record)
    _check(rig, rig.record)
    arm = _post(rig, f"/ui/benches/{_BENCH}/staging/arm", rig.record, data={})
    assert arm.status_code == 200, arm.text[:500]
    store: Store = rig.app.state.g3b_store
    store.append_event(
        f"bench.{_BENCH}",
        {
            "stream_id": f"bench.{_BENCH}",
            "at": rig.clock.iso(),
            "kind": "trip",
            "run_id": None,
            "evidence": {},
        },
    )
    calls_start = _spy(rig, "run_start")
    response = _post(
        rig,
        f"/ui/benches/{_BENCH}/run-starts",
        rig.record,
        data={
            "request_id": _BINDING_REQUEST_ID,
            "binding_sha256": rig.binding_sha,
            "expected_generation": str(generation),
        },
    )
    assert response.status_code == 200, response.text[:800]
    assert not calls_start
    assert 'data-bw-confirm="armed"' in response.text
    assert 'data-bw-disabled-reason="protection-active"' in response.text
    assert ">Cancel</button>" in response.text
    sessions: SessionStore = rig.app.state.ui_sessions
    staged = sessions.staged_start(rig.record.session_id, _BENCH)
    assert staged is not None and staged.armed is True
